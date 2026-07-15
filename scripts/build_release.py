#!/usr/bin/env python3
"""
Build Release Script
Creates the release package for v1.0.0
"""
import os
import sys
import json
import zipfile
import hashlib
import shutil
from datetime import datetime, timezone


VERSION = "1.0.0"
PACKAGE_NAME = f"deterministic-jungle-canopy-v{VERSION}"
DIST_DIR = "dist"
RELEASE_DIR = os.path.join(DIST_DIR, PACKAGE_NAME)


def run_build():
    print("=" * 60)
    print(f"  BUILDING RELEASE {VERSION}")
    print("=" * 60)
    
    # Clean previous build
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    
    os.makedirs(RELEASE_DIR, exist_ok=True)
    
    # Copy canopy package
    print("\nIncluding canopy package...")
    if os.path.exists("canopy"):
        shutil.copytree("canopy", os.path.join(RELEASE_DIR, "canopy"))
    
    # Copy static files (they're in canopy/static, not inside the package)
    static_src = "static"
    static_dest = os.path.join(RELEASE_DIR, "canopy", "static")
    if os.path.exists(static_src) and os.listdir(static_src):
        os.makedirs(static_dest, exist_ok=True)
        for item in os.listdir(static_src):
            src_item = os.path.join(static_src, item)
            dest_item = os.path.join(static_dest, item)
            if os.path.isfile(src_item):
                shutil.copy2(src_item, dest_item)
            elif os.path.isdir(src_item):
                shutil.copytree(src_item, dest_item, dirs_exist_ok=True)
        print(f"  ✅ static/ ({len(os.listdir(static_src))} files)")
    
    # Copy root files
    for fname in ["server.py", "cli.py", "requirements.txt", "README.md"]:
        if os.path.exists(fname):
            shutil.copy2(fname, os.path.join(RELEASE_DIR, fname))
    
    # Copy scripts directory
    scripts_src = "scripts"
    if os.path.exists(scripts_src):
        scripts_dest = os.path.join(RELEASE_DIR, "scripts")
        shutil.copytree(scripts_src, scripts_dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "receipts", "dist"))
    
    # Create directories
    os.makedirs(os.path.join(RELEASE_DIR, "receipts"), exist_ok=True)
    os.makedirs(os.path.join(RELEASE_DIR, "backups"), exist_ok=True)
    
    # Create version manifest
    manifest = {
        "package": PACKAGE_NAME,
        "version": VERSION,
        "engine_version": VERSION,
        "schema_version": "2.0",
        "built_at": datetime.now(timezone.utc).isoformat() + "Z",
    }
    
    with open(os.path.join(RELEASE_DIR, "VERSION.json"), 'w') as f:
        json.dump(manifest, f, indent=2)
    
    # Create ZIP
    zip_path = os.path.join(DIST_DIR, f"{PACKAGE_NAME}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, DIST_DIR)
                zf.write(filepath, arcname)
    
    print(f"\nBuild complete: {zip_path}")
    return zip_path


def smoke_test(zip_path):
    print("\n" + "=" * 60)
    print("  SMOKE TEST")
    print("=" * 60)
    
    errors = []
    
    # Test ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad = zf.testzip()
            if bad:
                errors.append(f"Bad file: {bad}")
    except Exception as e:
        errors.append(f"ZIP error: {e}")
    
    # Check VERSION.json
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            version_path = f"{PACKAGE_NAME}/VERSION.json"
            if version_path in names:
                data = json.loads(zf.read(version_path))
                print(f"  Version: {data['version']}")
            else:
                errors.append("VERSION.json not found")
    except Exception as e:
        errors.append(f"VERSION check error: {e}")
    
    if errors:
        print("\nSMOKE TEST FAILED:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("  SMOKE TEST PASSED")
    return True


if __name__ == "__main__":
    zip_path = run_build()
    success = smoke_test(zip_path)
    sys.exit(0 if success else 1)
