#!/usr/bin/env python3
"""Strict browser smoke for the real Banana Jungle Control Room."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy.version import __version__


@dataclass
class Check:
    name: str
    passed: bool
    details: str


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.status, json.loads(response.read())


def post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            parsed = json.loads(body) if body else {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body.decode("utf-8", "replace")}
        return exc.code, parsed


def wait_health(url: str, process: subprocess.Popen) -> bool:
    for _ in range(80):
        if process.poll() is not None:
            return False
        try:
            status, body = get_json(url + "/api/health/detail")
            if status == 200 and body.get("status") == "healthy":
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def canvas_rgb(page) -> tuple[bytes, str]:
    data_url = page.evaluate(
        "() => document.getElementById('liveCanvas').toDataURL('image/png')"
    )
    encoded = data_url.split(",", 1)[1]
    png = base64.b64decode(encoded)
    rgb = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
    return rgb, hashlib.sha256(rgb).hexdigest()


def api_rgb(api_frame: dict) -> tuple[bytes, str]:
    png = base64.b64decode(api_frame["image_base64"])
    rgb = Image.open(io.BytesIO(png)).convert("RGB").tobytes()
    return rgb, hashlib.sha256(rgb).hexdigest()


def render_ui(page, seed: int) -> str:
    page.goto("http://127.0.0.1:18080/control-room", wait_until="networkidle")
    page.wait_for_function(
        "() => document.getElementById('sessionIdInput').value.length > 0",
        timeout=20000,
    )
    page.fill("#seedInput", str(seed))
    page.click("#growJungleBtn")
    page.wait_for_function(
        """() => {
            const c = document.getElementById('liveCanvas');
            if (!c || c.width <= 0 || c.height <= 0) return false;
            const ctx = c.getContext('2d');
            const d = ctx.getImageData(0, 0, c.width, c.height).data;
            for (let i = 3; i < d.length; i += Math.max(4, Math.floor(d.length / 200))) {
                if (d[i] !== 0) return true;
            }
            return false;
        }""",
        timeout=30000,
    )
    return page.input_value("#sessionIdInput")


def run(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []
    seed = 424242
    base_url = "http://127.0.0.1:18080"
    server = None

    def record(name: str, passed: bool, details: str):
        checks.append(Check(name, passed, details))
        print(("PASS" if passed else "FAIL") + f" {name}: {details}")

    try:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--port",
                "18080",
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        healthy = wait_health(base_url, server)
        record("local_server", healthy, "127.0.0.1:18080 healthy" if healthy else "server did not become healthy")
        if not healthy:
            raise RuntimeError("server did not become healthy")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page1 = browser.new_page(viewport={"width": 1440, "height": 1000})
            sid1 = render_ui(page1, seed)
            rgb1, canvas_hash1 = canvas_rgb(page1)
            status1, frame1 = get_json(f"{base_url}/api/session/{sid1}/frame/0")
            api_bytes1, api_hash1 = api_rgb(frame1)
            transport_ok = status1 == 200 and rgb1 == api_bytes1
            record(
                "browser_image_transport",
                transport_ok,
                f"canvas_rgb_sha256={canvas_hash1} api_rgb_sha256={api_hash1}",
            )

            page2 = browser.new_page(viewport={"width": 1440, "height": 1000})
            sid2 = render_ui(page2, seed)
            rgb2, canvas_hash2 = canvas_rgb(page2)
            status2, frame2 = get_json(f"{base_url}/api/session/{sid2}/frame/0")
            api_bytes2, api_hash2 = api_rgb(frame2)
            deterministic = (
                status2 == 200
                and rgb1 == rgb2
                and api_bytes1 == api_bytes2
                and frame1.get("pixel_hash") == frame2.get("pixel_hash")
            )
            record(
                "two_browser_sessions_deterministic",
                deterministic,
                f"canvas1={canvas_hash1} canvas2={canvas_hash2} pixel={frame1.get('pixel_hash')}",
            )

            _, before = get_json(f"{base_url}/api/session/{sid1}")
            bad_status, _ = post_json(
                f"{base_url}/api/session/{sid1}/event",
                {"event_type": "definitely_invalid_event", "payload": {"seed": 1}},
            )
            _, after = get_json(f"{base_url}/api/session/{sid1}")
            unchanged = (
                bad_status >= 400
                and before.get("manifest_hash") == after.get("manifest_hash")
                and before.get("event_count") == after.get("event_count")
            )
            record(
                "invalid_event_no_browser_state_mutation",
                unchanged,
                f"http={bad_status} event_count={before.get('event_count')}->{after.get('event_count')}",
            )

            screenshot = output_dir / "browser_control_room.png"
            page1.screenshot(path=str(screenshot), full_page=True)
            record("browser_screenshot_receipt", screenshot.exists(), str(screenshot))

            browser.close()

        passed = sum(1 for c in checks if c.passed)
        failed = len(checks) - passed
        receipt = {
            "schema_version": "1.0",
            "engine_version": __version__,
            "trial_type": "browser_release_smoke",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "bind_address": "127.0.0.1",
            "listening_url": base_url,
            "browser": "chromium-headless",
            "canvas_rgb_sha256": canvas_hash1 if "canvas_hash1" in locals() else None,
            "api_pixel_hash": frame1.get("pixel_hash") if "frame1" in locals() else None,
            "results": [asdict(c) for c in checks],
            "summary": {
                "total_assertions": len(checks),
                "passed": passed,
                "failed": failed,
                "all_passed": failed == 0,
            },
        }
        receipt_path = output_dir / (
            "browser_release_smoke_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"RECEIPT={receipt_path}")
        return 0 if failed == 0 else 1
    except Exception as exc:
        record("browser_trial_exception", False, f"{type(exc).__name__}: {exc}")
        receipt = {
            "schema_version": "1.0",
            "engine_version": __version__,
            "trial_type": "browser_release_smoke",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "results": [asdict(c) for c in checks],
            "summary": {
                "total_assertions": len(checks),
                "passed": sum(1 for c in checks if c.passed),
                "failed": sum(1 for c in checks if not c.passed),
                "all_passed": False,
            },
        }
        receipt_path = output_dir / (
            "browser_release_smoke_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"RECEIPT={receipt_path}")
        return 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="receipts/release_gate/browser")
    args = parser.parse_args()
    return run(Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
