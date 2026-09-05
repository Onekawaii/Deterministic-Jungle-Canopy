#!/usr/bin/env python3
"""Strict extracted-release smoke trial. HTTP errors never count as success."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    passed: bool
    details: str


def request_json(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 15):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"raw": body.decode("utf-8", "replace")}
        return exc.code, parsed


def run(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []
    work_dir = Path(tempfile.mkdtemp(prefix="canopy_release_smoke_"))
    server = None
    base_url = "http://127.0.0.1:18000"

    def record(name: str, passed: bool, details: str):
        checks.append(Check(name, passed, details))
        print(("PASS" if passed else "FAIL") + f" {name}: {details}")

    try:
        zip_path = ROOT / "dist" / "deterministic-jungle-canopy-v1.0.0.zip"
        if not zip_path.exists():
            result = subprocess.run([sys.executable, "scripts/build_release.py"], cwd=ROOT)
            if result.returncode != 0:
                record("build_release", False, f"exit={result.returncode}")
                return 1
        record("release_archive_exists", zip_path.exists(), str(zip_path))

        extract_root = work_dir / "release"
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            names = zf.namelist()
            record("zip_integrity", bad is None, f"bad_entry={bad}")
            zf.extractall(extract_root)

        children = list(extract_root.iterdir())
        release_root = children[0] if len(children) == 1 and children[0].is_dir() else extract_root

        forbidden = [
            n for n in names
            if any(part in {".venv", "__pycache__", ".git"} for part in Path(n).parts)
            or n.endswith((".pyc", ".db", ".db-wal", ".db-shm"))
            or any(token in n.lower() for token in ("secret", ".env"))
        ]
        record("release_excludes_forbidden_artifacts", not forbidden, ", ".join(forbidden[:10]) or "clean")

        doctor = release_root / "scripts" / "doctor.py"
        result = subprocess.run([sys.executable, str(doctor)], cwd=release_root, capture_output=True, text=True)
        record("doctor", result.returncode == 0, f"exit={result.returncode}")

        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "18000"],
            cwd=release_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        healthy = False
        for _ in range(80):
            if server.poll() is not None:
                break
            try:
                status, body = request_json(base_url + "/api/health/detail")
                if status == 200 and body.get("status") == "healthy":
                    healthy = True
                    break
            except Exception:
                pass
            time.sleep(0.25)
        record("server_local_bind_health", healthy, base_url)

        status, body = request_json(base_url + "/control-room")
        # urllib follows the redirect and attempts JSON, so use a raw request for HTML.
        try:
            with urllib.request.urlopen(base_url + "/control-room", timeout=10) as resp:
                html = resp.read()
                control_ok = resp.status == 200 and b"growJungleBtn" in html
        except Exception:
            control_ok = False
        record("control_room_real_html", control_ok, "Grow Jungle control present" if control_ok else "control room missing")

        status, created = request_json(base_url + "/api/session", "POST", {})
        sid = created.get("session_id")
        record("api_create_session", status in (200, 201) and bool(sid), f"http={status} sid={sid}")

        if sid:
            status, frame = request_json(base_url + f"/api/session/{sid}/frame/0")
            frame_ok = (
                status == 200
                and bool(frame.get("image_base64"))
                and bool(frame.get("pixel_hash"))
                and bool(frame.get("manifest_hash"))
            )
            record("api_render_frame", frame_ok, f"http={status} pixel_hash={frame.get('pixel_hash')}")

            status, exported = request_json(base_url + f"/api/export/session/{sid}")
            export_ok = status == 200 and "session" in exported
            record("api_export_session", export_ok, f"http={status}")

            if export_ok:
                status, imported = request_json(base_url + "/api/import/session", "POST", exported)
                import_ok = status == 200 and imported.get("imported") is True
            else:
                status, import_ok = 0, False
            record("api_import_session", import_ok, f"http={status}")

            try:
                with urllib.request.urlopen(
                    base_url + f"/api/export/session/{sid}/sequence?start_frame=0&end_frame=2",
                    timeout=30,
                ) as resp:
                    zip_bytes = resp.read()
                    sequence_status = resp.status
                with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                    seq_names = zf.namelist()
                    sequence_ok = (
                        sequence_status == 200
                        and "manifest.json" in seq_names
                        and any(n.startswith("frames/") and n.endswith(".png") for n in seq_names)
                    )
            except Exception:
                sequence_ok = False
            record("api_sequence_export", sequence_ok, "real ZIP with manifest and PNG frames" if sequence_ok else "sequence export failed")

        passed = sum(1 for c in checks if c.passed)
        failed = len(checks) - passed
        receipt = {
            "schema_version": "1.0",
            "engine_version": "1.0.0",
            "trial_type": "release_smoke",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "release_zip": str(zip_path),
            "bind_address": "127.0.0.1",
            "results": [asdict(c) for c in checks],
            "summary": {
                "total_assertions": len(checks),
                "passed": passed,
                "failed": failed,
                "all_passed": failed == 0,
            },
        }
        receipt_path = output_dir / (
            "release_smoke_trial_"
            + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"RECEIPT={receipt_path}")
        return 0 if failed == 0 else 1
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(work_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="receipts/release_gate/release_smoke")
    args = parser.parse_args()
    return run(Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
