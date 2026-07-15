#!/usr/bin/env python3
"""
Doctor Script - System Health Check 🩺
"""
import sys
import os

# Add parent directory to path for canopy import
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)


def run_doctor():
    """Run the system health check."""
    print("=" * 60)
    print("  🌿 CANOPY DOCTOR - System Health Check 🌿")
    print("=" * 60)
    
    issues = []
    warnings = []
    
    # Check Python version
    print("\n📋 Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        issues.append(f"Python 3.10+ required, found {version.major}.{version.minor}")
    else:
        print(f"  ✅ Python {version.major}.{version.minor}.{version.micro}")
    
    # Check dependencies
    print("\n📋 Checking dependencies...")
    deps = ["numpy", "PIL", "fastapi", "uvicorn", "websockets"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"  ✅ {dep}")
        except ImportError:
            issues.append(f"Missing dependency: {dep}")
    
    # Check database
    print("\n📋 Checking database...")
    db_path = "canopy_archive.db"
    if os.path.exists(db_path):
        print(f"  ✅ Database exists: {db_path}")
        
        # Check integrity
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM archive")
            count = cursor.fetchone()[0]
            print(f"  ✅ Archive entries: {count}")
            conn.close()
        except Exception as e:
            issues.append(f"Database error: {e}")
    else:
        warnings.append("Database does not exist (will be created on first use)")
        print(f"  ⚠️  Database not found: {db_path}")
    
    # Check receipts directory
    print("\n📋 Checking receipts directory...")
    receipts_dir = "receipts"
    if os.path.exists(receipts_dir):
        files = os.listdir(receipts_dir)
        print(f"  ✅ Receipts directory: {len(files)} files")
    else:
        os.makedirs(receipts_dir, exist_ok=True)
        print(f"  ✅ Created receipts directory")
    
    # Check schema version
    print("\n📋 Checking schema version...")
    try:
        from canopy.version import __version__, __schema_version__
        print(f"  ✅ Engine version: {__version__}")
        print(f"  ✅ Schema version: {__schema_version__}")
    except ImportError as e:
        issues.append(f"Cannot import canopy: {e}")
    
    # Check storage
    print("\n📋 Checking storage...")
    try:
        from canopy.storage import SessionStore
        test_db = "canopy_test_doctor.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        store = SessionStore(test_db)
        print(f"  ✅ Session store: OK")
        os.remove(test_db)
    except Exception as e:
        issues.append(f"Session store error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    
    if issues:
        print(f"\n  ❌ Issues found: {len(issues)}")
        for issue in issues:
            print(f"     - {issue}")
    
    if warnings:
        print(f"\n  ⚠️  Warnings: {len(warnings)}")
        for warning in warnings:
            print(f"     - {warning}")
    
    if not issues and not warnings:
        print("\n  ✅ All checks passed!")
        return 0
    
    if issues:
        print(f"\n  ❌ {len(issues)} issues must be resolved")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(run_doctor())
