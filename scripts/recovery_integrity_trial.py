#!/usr/bin/env python3
"""Strict recovery/integrity trial for Sovereign Canopy release gate."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy.core.renderer import CanopyRenderer
from canopy.manifest import ManifestBuilder
from canopy.session import EventType, SessionEvent, SessionManager
from canopy.version import __version__, __schema_version__


@dataclass
class Check:
    name: str
    passed: bool
    details: str


def run(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[Check] = []
    seed = 424242
    manager = SessionManager()

    def record(name: str, passed: bool, details: str) -> None:
        checks.append(Check(name, passed, details))
        print(("PASS" if passed else "FAIL") + f" {name}: {details}")

    manifest = ManifestBuilder(seed=seed, width=96, height=96).build()
    session = manager.create_session(manifest)
    manifest_hash = manager._hash_manifest(session.base_manifest)

    # Real deterministic render and valid event mutation.
    frame_a, hash_a = manager.render_session_frame(session, 0, 96, 96)
    event = SessionEvent(
        event_index=0,
        event_type=EventType.SET_SEED,
        payload={"seed": seed},
    )
    ok, error = manager.apply_event(session.session_id, event)
    record("valid_event_applies", ok and error is None and len(session.events) == 1,
           error or f"event_count={len(session.events)}")

    # Invalid event index must fail without mutating state.
    before_manifest = copy.deepcopy(session.current_manifest)
    before_events = [e.to_dict() for e in session.events]
    before_frame = session.current_frame
    bad = SessionEvent(
        event_index=99,
        event_type=EventType.SET_SEED,
        payload={"seed": seed + 1},
    )
    ok_bad, error_bad = manager.apply_event(session.session_id, bad)
    unchanged = (
        not ok_bad
        and session.current_manifest == before_manifest
        and [e.to_dict() for e in session.events] == before_events
        and session.current_frame == before_frame
    )
    record("invalid_event_no_mutation", unchanged, error_bad or "unexpected success")

    # Inject a real render failure and prove render path leaves session state untouched.
    before_manifest = copy.deepcopy(session.current_manifest)
    before_events = [e.to_dict() for e in session.events]
    before_frame = session.current_frame
    injected_seen = False
    try:
        with patch.object(CanopyRenderer, "render_frame", side_effect=RuntimeError("injected render interruption")):
            manager.render_session_frame(session, 0, 96, 96)
    except RuntimeError as exc:
        injected_seen = "injected render interruption" in str(exc)

    recovery_unchanged = (
        injected_seen
        and session.current_manifest == before_manifest
        and [e.to_dict() for e in session.events] == before_events
        and session.current_frame == before_frame
    )
    record("interrupted_render_recoverable", recovery_unchanged,
           "injected failure propagated and session state remained unchanged" if recovery_unchanged
           else "state changed or injected failure was not observed")

    # Real load exercise: create, mutate, and render multiple independent sessions.
    load_ok = True
    load_count = 12
    load_hashes = []
    try:
        for i in range(load_count):
            load_manifest = ManifestBuilder(seed=seed + 100 + i, width=64, height=64).build()
            load_session = manager.create_session(load_manifest)
            load_event = SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": seed + 100 + i},
            )
            load_event_ok, load_error = manager.apply_event(load_session.session_id, load_event)
            if not load_event_ok:
                load_ok = False
                break
            _, load_hash = manager.render_session_frame(load_session, 0, 64, 64)
            load_hashes.append(load_hash)
    except Exception:
        load_ok = False
    load_ok = load_ok and len(load_hashes) == load_count and len(set(load_hashes)) == load_count
    record(
        "real_load_sessions_and_renders",
        load_ok,
        f"sessions_rendered={len(load_hashes)}/{load_count} unique_hashes={len(set(load_hashes))}",
    )

    # Valid export/import must reproduce pixels.
    exported = manager.export_session(session.session_id)
    imported, import_error = manager.import_session(exported or {})
    if imported is not None:
        frame_b, hash_b = manager.render_session_frame(imported, 0, 96, 96)
        same_pixels = hash_a == hash_b and frame_a.tobytes() == frame_b.tobytes()
    else:
        hash_b = None
        same_pixels = False
    record("export_import_reproduces_pixels", same_pixels,
           f"before={hash_a} after={hash_b} error={import_error}")

    # Corrupt session data must fail closed and must not add an active session.
    count_before = len(manager._sessions)
    corrupt_payload = {
        "session": {
            "session_id": "corrupt",
            "status": "definitely-not-a-valid-status",
            "base_manifest": {},
            "current_manifest": {},
            "events": [],
        }
    }
    corrupt_session, corrupt_error = manager.import_session(corrupt_payload)
    count_after = len(manager._sessions)
    corrupt_closed = corrupt_session is None and bool(corrupt_error) and count_after == count_before
    record("corrupt_session_fails_closed", corrupt_closed,
           corrupt_error or "corrupt import unexpectedly succeeded")

    valid, integrity_errors = manager.verify_session_integrity(session.session_id)
    record("session_integrity", valid, "; ".join(integrity_errors) if integrity_errors else "integrity verified")

    passed = sum(1 for c in checks if c.passed)
    failed = len(checks) - passed
    receipt = {
        "schema_version": "1.0",
        "engine_version": __version__,
        "manifest_schema_version": __schema_version__,
        "trial_type": "recovery_integrity",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "manifest_hash": manifest_hash,
        "pixel_hash": hash_a,
        "results": [asdict(c) for c in checks],
        "summary": {
            "total_assertions": len(checks),
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0,
        },
    }
    path = output_dir / (
        "recovery_integrity_trial_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + ".json"
    )
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"RECEIPT={path}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="receipts/release_gate/recovery")
    args = parser.parse_args()
    return run(Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
