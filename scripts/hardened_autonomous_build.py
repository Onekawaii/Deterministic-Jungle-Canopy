#!/usr/bin/env python3
"""Composite red/green hardening gate for Canopy + PISS."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = ROOT / "receipts" / "hardened_autonomous_build"
LOG_ROOT = RECEIPT_ROOT / "logs"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path):
    if not path.exists() or not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())


def git_text(*args: str) -> str:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
            shell=False,
        )
        return (p.stdout or "").strip()
    except Exception:
        return ""


def run_step(name: str, argv: list[str], expected=None, timeout: int = 1800) -> dict:
    expected = set(expected or {0})
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            shell=False,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        output = proc.stdout or ""
        rc = proc.returncode
        error = None
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else ""
        rc = 124
        error = f"TimeoutExpired after {timeout}s"
    except Exception as exc:
        output = ""
        rc = 125
        error = f"{type(exc).__name__}: {exc}"

    elapsed = round(time.monotonic() - started, 3)
    raw = output.encode("utf-8", "replace")
    log_path = LOG_ROOT / f"{name}.log"
    log_path.write_bytes(raw)
    passed = rc in expected and error is None

    print(f"{'PASS' if passed else 'FAIL'} {name} rc={rc} duration={elapsed}s")
    if not passed and output:
        print(output[-4000:])

    return {
        "name": name,
        "type": "command",
        "argv": argv,
        "expected_returncodes": sorted(expected),
        "returncode": rc,
        "passed": passed,
        "duration_seconds": elapsed,
        "log": str(log_path.relative_to(ROOT)),
        "log_sha256": sha256_bytes(raw),
        "log_bytes": len(raw),
        "error": error,
    }


def static_check(name: str, passed: bool, details: str) -> dict:
    print(f"{'PASS' if passed else 'FAIL'} {name}: {details}")
    return {
        "name": name,
        "type": "static",
        "passed": bool(passed),
        "details": details,
    }


def version_tuple(text: str):
    nums = re.findall(r"\d+", text)
    return tuple(int(x) for x in nums[:3]) if nums else (0,)


def piss_hardening_checks(profile: str):
    checks = []
    runner_path = ROOT / "piss" / "runner.py"
    parser_path = ROOT / "piss" / "parser.py"
    cli_path = ROOT / "piss" / "cli.py"

    runner = runner_path.read_text(encoding="utf-8") if runner_path.exists() else ""
    parser_text = parser_path.read_text(encoding="utf-8") if parser_path.exists() else ""
    cli = cli_path.read_text(encoding="utf-8") if cli_path.exists() else ""

    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        piss = importlib.import_module("piss")
        version = getattr(piss, "__version__", "0.0.0")
    except Exception:
        version = "0.0.0"

    hardened = profile == "hardened"

    checks.append(static_check(
        "piss_version",
        version_tuple(version) >= (0, 2) if hardened else bool(version),
        f"version={version}; hardened requires >=0.2",
    ))
    checks.append(static_check(
        "piss_no_shell_true",
        "shell=True" not in runner if hardened else True,
        "card-driven execution must not use shell=True",
    ))
    checks.append(static_check(
        "piss_no_eval_exec",
        not any(token in runner for token in ("eval(", "exec(")),
        "runner contains no eval/exec",
    ))
    checks.append(static_check(
        "piss_adapter_registry",
        (ROOT / "piss" / "adapters").is_dir() if hardened else True,
        f"adapters_dir={(ROOT / 'piss' / 'adapters').exists()}",
    ))

    has_show = re.search(r'add_parser\(["\']show["\']\)', cli) is not None
    checks.append(static_check(
        "piss_cli_show",
        has_show if hardened else True,
        f"show_command={has_show}",
    ))

    verbs = ("WANT", "ACT", "DO", "RECKON", "REPAIR", "BURY")
    wadrrb = all(v in parser_text for v in verbs)
    checks.append(static_check(
        "piss_wadrrb_preserved",
        wadrrb,
        f"WADRRB verbs present={wadrrb}",
    ))
    return checks


def canopy_hardening_checks(profile: str):
    checks = []
    server_path = ROOT / "server.py"
    cli_path = ROOT / "cli.py"
    server = server_path.read_text(encoding="utf-8") if server_path.exists() else ""
    cli = cli_path.read_text(encoding="utf-8") if cli_path.exists() else ""

    wildcard_credentials = 'allow_origins=["*"]' in server and "allow_credentials=True" in server
    checks.append(static_check(
        "canopy_no_wildcard_credentials_cors",
        not wildcard_credentials if profile == "hardened" else True,
        f"wildcard_with_credentials={wildcard_credentials}",
    ))

    direct_wild_bind = 'host="0.0.0.0"' in server or 'default="0.0.0.0"' in cli
    checks.append(static_check(
        "canopy_loopback_default",
        not direct_wild_bind,
        f"wildcard_default_bind={direct_wild_bind}",
    ))
    return checks


def newest_receipt(directory: Path):
    files = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--require-clean", action="store_true")
    args = ap.parse_args()

    profile = "baseline" if args.baseline else "hardened"
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)

    commit = git_text("rev-parse", "HEAD")
    dirty_before = bool(git_text("status", "--porcelain"))
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()

    steps = []
    steps.append(run_step(
        "compileall",
        [sys.executable, "-m", "compileall", "-q", "canopy", "piss", "scripts"],
        timeout=180,
    ))
    steps.extend(canopy_hardening_checks(profile))
    steps.extend(piss_hardening_checks(profile))

    for card in (
        "cards/piss_on_the_world.piss",
        "cards/project_check.piss",
        "cards/intentional_failure.piss",
    ):
        steps.append(run_step(
            "piss_check_" + Path(card).stem,
            [sys.executable, "-m", "piss", "check", card],
            timeout=60,
        ))

    piss_receipts = RECEIPT_ROOT / "piss"
    piss_receipts.mkdir(parents=True, exist_ok=True)

    steps.append(run_step(
        "piss_run_world",
        [sys.executable, "-m", "piss", "run", "cards/piss_on_the_world.piss", "--receipts", str(piss_receipts)],
        timeout=60,
    ))
    steps.append(run_step(
        "piss_run_project_check",
        [sys.executable, "-m", "piss", "run", "cards/project_check.piss", "--receipts", str(piss_receipts)],
        timeout=120,
    ))
    steps.append(run_step(
        "piss_intentional_failure",
        [sys.executable, "-m", "piss", "run", "cards/intentional_failure.piss", "--receipts", str(piss_receipts)],
        expected={1},
        timeout=60,
    ))

    latest_piss = newest_receipt(piss_receipts)
    fail_receipt_ok = False
    if latest_piss:
        try:
            pdata = json.loads(latest_piss.read_text(encoding="utf-8"))
            fail_receipt_ok = pdata.get("status") == "FAIL"
        except Exception:
            pass

    steps.append(static_check(
        "piss_failure_receipt_exists",
        fail_receipt_ok,
        str(latest_piss.relative_to(ROOT)) if latest_piss else "missing",
    ))

    steps.append(run_step(
        "sovereign_release_gate",
        [sys.executable, "scripts/sovereign_release_gate.py"],
        timeout=2400,
    ))

    dirty_after = bool(git_text("status", "--porcelain"))
    if args.require_clean:
        steps.append(static_check(
            "git_worktree_clean",
            not dirty_after,
            f"dirty={dirty_after}",
        ))

    all_passed = all(step.get("passed", False) for step in steps)
    finished_at = datetime.now(timezone.utc).isoformat()

    release_manifest_path = ROOT / "dist" / "release_manifest.json"
    release_manifest = {}
    if release_manifest_path.exists():
        try:
            release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            release_manifest = {}

    receipt = {
        "schema_version": "hardened.autonomous.build/1.0",
        "profile": profile,
        "status": "PASS" if all_passed else "FAIL",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(time.monotonic() - start, 3),
        "git": {
            "commit": commit,
            "dirty_before": dirty_before,
            "dirty_after": dirty_after,
        },
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "steps": steps,
        "release": {
            "archive": release_manifest.get("archive"),
            "archive_sha256": release_manifest.get("archive_sha256"),
            "file_count": release_manifest.get("file_count"),
        },
        "inputs": {
            "server_sha256": sha256_file(ROOT / "server.py"),
            "piss_runner_sha256": sha256_file(ROOT / "piss" / "runner.py"),
            "piss_parser_sha256": sha256_file(ROOT / "piss" / "parser.py"),
            "autonomous_spec_sha256": sha256_file(ROOT / "docs" / "HARDENED_AUTONOMOUS_BUILD.md"),
        },
    }

    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt["receipt_sha256"] = sha256_bytes(canonical)

    out = RECEIPT_ROOT / (
        "hardened_autonomous_build_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + ".json"
    )
    out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("HARDENED AUTONOMOUS BUILD")
    print("=" * 72)
    print(f"PROFILE={profile}")
    print(f"COMMIT={commit}")
    print(f"RELEASE_ARCHIVE={receipt['release']['archive']}")
    print(f"RELEASE_SHA256={receipt['release']['archive_sha256']}")
    print(f"RECEIPT={out}")
    print("RESULT=" + ("PASS" if all_passed else "FAIL"))

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
