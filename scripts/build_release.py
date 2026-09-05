#!/usr/bin/env python3
"""Build a clean, reproducible Sovereign Canopy release archive."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
PACKAGE_NAME = f"deterministic-jungle-canopy-v{VERSION}"
ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
RELEASE_DIR = DIST_DIR / PACKAGE_NAME

ROOT_FILES = [
    "server.py",
    "cli.py",
    "requirements.txt",
    "requirements-release.txt",
    "README.md",
    "RUN_CANOPY_WINDOWS.ps1",
    "RUN_CANOPY_WINDOWS.cmd",
    "VERIFY_SOVEREIGN_RELEASE.ps1",
    "PISS_ON_THE_WORLD.bat",
    "RUN_PROJECT_CHECK.bat",
    "VERIFY_PISS.bat",
    "PISS_RUNBOOK_WINDOWS.md",
    "PISS_BASELINE_v0.1.md",
]

DIRECTORIES = [
    "canopy",
    "static",
    "scripts",
    "piss",
    "cards",
    "schemas",
    "docs",
    "tests",
]

FORBIDDEN_PARTS = {".venv", "__pycache__", ".git", ".pytest_cache"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm"}


def source_epoch() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%ct"],
            cwd=ROOT,
            text=True,
        ).strip()
        return int(out)
    except Exception:
        return 315532800  # 1980-01-01, ZIP-safe deterministic fallback.


def should_ignore(path: Path) -> bool:
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return True
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    return False


def copy_tree_clean(src: Path, dst: Path) -> None:
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if should_ignore(rel):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_file_manifest() -> tuple[Path, int]:
    rows = []
    for path in sorted(RELEASE_DIR.rglob("*")):
        if path.is_file() and path.name != "FILE_MANIFEST.sha256.txt":
            rel = path.relative_to(RELEASE_DIR).as_posix()
            rows.append(f"{sha256_file(path)}  {rel}")
    manifest_path = RELEASE_DIR / "FILE_MANIFEST.sha256.txt"
    manifest_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return manifest_path, len(rows) + 1


def audit_release_tree() -> list[str]:
    bad = []
    for path in RELEASE_DIR.rglob("*"):
        rel = path.relative_to(RELEASE_DIR)
        if should_ignore(rel):
            bad.append(rel.as_posix())
    return sorted(bad)


def write_reproducible_zip(zip_path: Path, epoch: int) -> None:
    safe_epoch = max(epoch, 315532800)
    stamp = time.gmtime(safe_epoch)[:6]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(RELEASE_DIR.rglob("*")):
            if not path.is_file():
                continue
            rel = Path(PACKAGE_NAME) / path.relative_to(RELEASE_DIR)
            info = zipfile.ZipInfo(rel.as_posix(), date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            zf.writestr(info, path.read_bytes())


def run_build() -> Path:
    epoch = source_epoch()
    built_at = datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)

    for name in ROOT_FILES:
        src = ROOT / name
        if src.exists() and src.is_file():
            shutil.copy2(src, RELEASE_DIR / name)

    for name in DIRECTORIES:
        src = ROOT / name
        if src.exists() and src.is_dir():
            copy_tree_clean(src, RELEASE_DIR / name)

    (RELEASE_DIR / "receipts").mkdir(exist_ok=True)
    (RELEASE_DIR / "backups").mkdir(exist_ok=True)

    version_manifest = {
        "package": PACKAGE_NAME,
        "version": VERSION,
        "engine_version": VERSION,
        "schema_version": "2.0",
        "built_at": built_at,
        "source_date_epoch": epoch,
        "default_bind": "127.0.0.1",
        "local_only_default": True,
    }
    (RELEASE_DIR / "VERSION.json").write_text(
        json.dumps(version_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    _, file_count = build_file_manifest()
    forbidden = audit_release_tree()
    if forbidden:
        raise RuntimeError("Forbidden release artifacts: " + ", ".join(forbidden))

    zip_path = DIST_DIR / f"{PACKAGE_NAME}.zip"
    write_reproducible_zip(zip_path, epoch)
    archive_hash = sha256_file(zip_path)

    release_manifest = {
        **version_manifest,
        "archive": zip_path.name,
        "archive_sha256": archive_hash,
        "file_count": file_count,
        "forbidden_entries": forbidden,
    }
    (DIST_DIR / "release_manifest.json").write_text(
        json.dumps(release_manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (DIST_DIR / "RELEASE_SHA256.txt").write_text(
        f"{archive_hash}  {zip_path.name}\n",
        encoding="utf-8",
    )

    print(f"BUILD_ARCHIVE={zip_path}")
    print(f"BUILD_SHA256={archive_hash}")
    print(f"BUILD_FILES={file_count}")
    return zip_path


def smoke_zip(zip_path: Path) -> bool:
    with zipfile.ZipFile(zip_path, "r") as zf:
        bad = zf.testzip()
        names = zf.namelist()
    if bad:
        print(f"ZIP_BAD_ENTRY={bad}")
        return False

    forbidden = [
        name for name in names
        if any(part in FORBIDDEN_PARTS for part in Path(name).parts)
        or Path(name).suffix.lower() in FORBIDDEN_SUFFIXES
        or Path(name).name.lower() == ".env"
    ]
    if forbidden:
        print("ZIP_FORBIDDEN=" + ",".join(forbidden))
        return False

    required = {
        f"{PACKAGE_NAME}/server.py",
        f"{PACKAGE_NAME}/RUN_CANOPY_WINDOWS.ps1",
        f"{PACKAGE_NAME}/requirements.txt",
        f"{PACKAGE_NAME}/VERSION.json",
        f"{PACKAGE_NAME}/FILE_MANIFEST.sha256.txt",
    }
    missing = sorted(required - set(names))
    if missing:
        print("ZIP_MISSING=" + ",".join(missing))
        return False

    print("ZIP_SMOKE=PASS")
    return True


if __name__ == "__main__":
    try:
        archive = run_build()
        raise SystemExit(0 if smoke_zip(archive) else 1)
    except Exception as exc:
        print(f"BUILD_FAILED={type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
