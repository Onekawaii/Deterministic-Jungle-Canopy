#!/usr/bin/env python3
"""One-command executable gate for GitHub issue #1."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:\n    sys.path.insert(0, str(ROOT))\n\nfrom canopy.version import __version__, __schema_version__\n\nRECEIPT_ROOT = ROOT / "receipts" / "release_gate"
LOG_ROOT = RECEIPT_ROOT / "logs"


def run_command(name: str, argv: list[str], timeout: int = 900) -> dict:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 72)
    print(f"GATE {name}")
    print("=" * 72)
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    output = proc.stdout or ""
    print(output)
    log_path = LOG_ROOT / f"{name}.log"
    log_path.write_text(output, encoding="utf-8")
    return {
        "name": name,
        "argv": argv,
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "log": str(log_path.relative_to(ROOT)),
    }


def latest_json(directory: Path) -> tuple[Path | None, dict | None]:
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None, None
    path = files[0]
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path, None


def summary_count(receipt: dict | None, key: str) -> int | None:
    if not receipt:
        return None
    summary = receipt.get("summary", {})
    value = summary.get(key)
    return int(value) if isinstance(value, (int, float)) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-browser", action="store_true", help="Explicitly skip the browser gate")
    args = parser.parse_args()

    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    steps = []

    units = run_command("unit_tests", [sys.executable, "-m", "pytest", "-q"], timeout=900)
    unit_match = re.search(r"(\d+) passed", (ROOT / units["log"]).read_text(encoding="utf-8"))
    unit_total = int(unit_match.group(1)) if unit_match else None
    steps.append(units)

    det_dir = RECEIPT_ROOT / "determinism"
    det = run_command(
        "determinism",
        [sys.executable, "scripts/determinism_live_trial.py", "--output", str(det_dir)],
        timeout=900,
    )
    steps.append(det)

    rec_dir = RECEIPT_ROOT / "recovery"
    rec = run_command(
        "load_recovery_integrity",
        [sys.executable, "scripts/recovery_integrity_trial.py", "--output", str(rec_dir)],
        timeout=900,
    )
    steps.append(rec)

    build = run_command("build_release", [sys.executable, "scripts/build_release.py"], timeout=900)
    steps.append(build)

    smoke_dir = RECEIPT_ROOT / "release_smoke"
    smoke = run_command(
        "api_release_smoke",
        [sys.executable, "scripts/release_smoke_trial.py", "--output", str(smoke_dir)],
        timeout=900,
    )
    steps.append(smoke)

    browser_dir = RECEIPT_ROOT / "browser"
    if args.skip_browser:
        browser = {
            "name": "browser_release_smoke",
            "argv": [],
            "returncode": None,
            "passed": False,
            "skipped": True,
            "log": None,
        }
    else:
        browser = run_command(
            "browser_release_smoke",
            [sys.executable, "scripts/browser_release_smoke.py", "--output", str(browser_dir)],
            timeout=900,
        )
        steps.append(browser)

    det_path, det_receipt = latest_json(det_dir)
    rec_path, rec_receipt = latest_json(rec_dir)
    smoke_path, smoke_receipt = latest_json(smoke_dir)
    browser_path, browser_receipt = latest_json(browser_dir)

    release_manifest_path = ROOT / "dist" / "release_manifest.json"
    release_manifest = (
        json.loads(release_manifest_path.read_text(encoding="utf-8"))
        if release_manifest_path.exists()
        else {}
    )

    all_required_passed = all(step.get("passed") for step in steps)
    if args.skip_browser:
        all_required_passed = False

    receipt = {
        "schema_version": "1.0",\n        "engine_version": __version__,\n        "manifest_schema_version": __schema_version__,\n        "gate": "sovereign_canopy_verified_distribution",
        "issue": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "working_directory": str(ROOT),
        "local_only_bind_default": "127.0.0.1",\n        "acceleration": {\n            "default": "cpu",\n            "selected": "cpu",\n            "optional_backend_request": os.environ.get("CANOPY_ACCELERATION"),\n        },\n        "steps": steps,
        "totals": {
            "unit_tests": unit_total,
            "determinism_total": summary_count(det_receipt, "total_tests"),
            "determinism_passed": summary_count(det_receipt, "passed"),
            "recovery_total": summary_count(rec_receipt, "total_assertions"),
            "recovery_passed": summary_count(rec_receipt, "passed"),
            "api_smoke_total": summary_count(smoke_receipt, "total_assertions"),
            "api_smoke_passed": summary_count(smoke_receipt, "passed"),
            "browser_total": summary_count(browser_receipt, "total_assertions"),
            "browser_passed": summary_count(browser_receipt, "passed"),
        },
        "determinism_receipt": str(det_path.relative_to(ROOT)) if det_path else None,
        "recovery_receipt": str(rec_path.relative_to(ROOT)) if rec_path else None,
        "api_smoke_receipt": str(smoke_path.relative_to(ROOT)) if smoke_path else None,
        "browser_smoke_receipt": str(browser_path.relative_to(ROOT)) if browser_path else None,
        "seed": (rec_receipt or {}).get("seed"),
        "manifest_hash": (rec_receipt or {}).get("manifest_hash"),
        "archive": release_manifest.get("archive"),
        "archive_sha256": release_manifest.get("archive_sha256"),
        "archive_file_count": release_manifest.get("file_count"),
        "release_forbidden_entries": release_manifest.get("forbidden_entries"),
        "all_passed": all_required_passed,
    }

    receipt_path = RECEIPT_ROOT / (
        "sovereign_release_gate_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + ".json"
    )
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("SOVEREIGN RELEASE GATE")
    print("=" * 72)
    print(f"UNIT_TESTS={unit_total}")
    print(f"DETERMINISM={receipt['totals']['determinism_passed']}/{receipt['totals']['determinism_total']}")
    print(f"RECOVERY={receipt['totals']['recovery_passed']}/{receipt['totals']['recovery_total']}")
    print(f"API_SMOKE={receipt['totals']['api_smoke_passed']}/{receipt['totals']['api_smoke_total']}")
    print(f"BROWSER={receipt['totals']['browser_passed']}/{receipt['totals']['browser_total']}")
    print(f"ARCHIVE={receipt['archive']}")
    print(f"ARCHIVE_SHA256={receipt['archive_sha256']}")
    print(f"RECEIPT={receipt_path}")
    print("RESULT=" + ("PASS" if all_required_passed else "FAIL"))

    return 0 if all_required_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
