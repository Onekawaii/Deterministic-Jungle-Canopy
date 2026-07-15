"""
Canopy Migrations Module 🔄
Handles schema migrations with rollback capability
"""
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from .schema import migrate_from_v1_to_v2, can_migrate, get_schema_version, SchemaError


@dataclass
class MigrationReceipt:
    """Receipt for a completed migration."""
    timestamp: str
    from_version: str
    to_version: str
    records_migrated: int
    backup_path: str
    success: bool
    error: Optional[str] = None
    operations: List[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MigrationManager:
    """Manages schema migrations with backup and rollback."""
    
    def __init__(self, db_path: str, backup_dir: str = "backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def migrate_database(self) -> MigrationReceipt:
        """Migrate the database to current schema version."""
        timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        operations = []
        
        try:
            # Create backup first
            backup_path = self._create_backup()
            operations.append(f"Created backup at {backup_path}")
            
            # Get current schema version
            current_version = self._get_current_db_version()
            operations.append(f"Current DB version: {current_version}")
            
            # Migrate from 1.0 to 2.0
            if current_version == "1.0":
                records = self._migrate_v1_to_v2()
                operations.append(f"Migrated {records} records from v1.0 to v2.0")
                
                # Update version
                self._set_db_version("2.0")
                operations.append("Updated database version to 2.0")
            
            return MigrationReceipt(
                timestamp=timestamp,
                from_version=current_version,
                to_version="2.0",
                records_migrated=len(operations),
                backup_path=str(backup_path),
                success=True,
                operations=operations
            )
            
        except Exception as e:
            return MigrationReceipt(
                timestamp=timestamp,
                from_version=self._get_current_db_version(),
                to_version="2.0",
                records_migrated=0,
                backup_path="",
                success=False,
                error=str(e),
                operations=operations
            )
    
    def _create_backup(self) -> Path:
        """Create a backup of the database."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.db_path.stem}_{timestamp}{self.db_path.suffix}"
        backup_path = self.backup_dir / backup_name
        
        shutil.copy2(self.db_path, backup_path)
        return backup_path
    
    def _get_current_db_version(self) -> str:
        """Get current database schema version."""
        if not self.db_path.exists():
            return "2.0"  # New database starts at latest version
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            # Check if version table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='schema_version'
            """)
            
            if cursor.fetchone():
                cursor.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
                row = cursor.fetchone()
                return row[0] if row else "1.0"
            else:
                # Old schema - check if old tables exist
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='archive'
                """)
                if cursor.fetchone():
                    return "1.0"
                return "2.0"
        finally:
            conn.close()
    
    def _set_db_version(self, version: str) -> None:
        """Set database schema version."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        try:
            # Create version table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
            """)
            
            cursor.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat() + "Z")
            )
            
            conn.commit()
        finally:
            conn.close()
    
    def _migrate_v1_to_v2(self) -> int:
        """Migrate database from v1.0 to v2.0."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Add new v2.0 columns to sessions table
        new_columns = [
            ("event_cursor", "INTEGER DEFAULT 0"),
            ("abandoned_future", "TEXT DEFAULT '[]'"),
            ("schema_version_session", "TEXT DEFAULT '2.0'"),
            ("engine_version", "TEXT DEFAULT '1.0.0'"),
            ("timeline", "TEXT DEFAULT NULL"),
            ("selected_frame_hashes", "TEXT DEFAULT '{}'"),
        ]
        
        # Get existing columns
        cursor.execute("PRAGMA table_info(sessions)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        
        for col_name, col_def in new_columns:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE sessions ADD COLUMN {col_name} {col_def}")
        
        # Migrate sessions data
        cursor.execute("SELECT id, events FROM sessions")
        rows = cursor.fetchall()
        
        for row_id, events_json in rows:
            if events_json:
                try:
                    events = json.loads(events_json)
                    cursor.execute(
                        "UPDATE sessions SET event_cursor = ? WHERE id = ?",
                        (len(events), row_id)
                    )
                except json.JSONDecodeError:
                    pass
        
        # Create sessions table migration tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _sessions_migration (
                id INTEGER PRIMARY KEY,
                migrated_at TEXT,
                original_events TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        
        return len(rows)
    
    def rollback_to_v1(self, backup_path: str) -> bool:
        """Rollback to v1.0 using backup."""
        try:
            if not Path(backup_path).exists():
                raise FileNotFoundError(f"Backup not found: {backup_path}")
            
            # Replace current with backup
            shutil.copy2(backup_path, self.db_path)
            return True
        except Exception:
            return False
    
    def write_migration_receipt(self, receipt: MigrationReceipt, path: str = "receipts") -> Path:
        """Write migration receipt to file."""
        receipts_dir = Path(path)
        receipts_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"migration_{timestamp}.json"
        filepath = receipts_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(receipt.to_dict(), f, indent=2)
        
        return filepath


def migrate_manifest(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a single manifest."""
    if not can_migrate(data):
        raise SchemaError(
            f"Cannot migrate: unsupported version {get_schema_version(data)}",
            code="UNSUPPORTED_SCHEMA"
        )
    
    return migrate_from_v1_to_v2(data)


def migrate_session(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a session with all related data."""
    if not can_migrate(data):
        raise SchemaError(
            f"Cannot migrate session: unsupported version {get_schema_version(data)}",
            code="UNSUPPORTED_SCHEMA"
        )
    
    migrated = migrate_from_v1_to_v2(data)
    
    # Migrate events
    if "events" in migrated:
        migrated["events"] = [migrate_from_v1_to_v2(e) for e in migrated["events"]]
    
    # Migrate timeline
    if "timeline" in migrated and migrated["timeline"]:
        migrated["timeline"] = migrate_from_v1_to_v2(migrated["timeline"])
    
    return migrated


def verify_database_integrity(db_path: str) -> Dict[str, Any]:
    """Verify database integrity after migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    issues = []
    warnings = []
    
    try:
        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        
        required_tables = {"sessions", "archive", "schema_version"}
        for table in required_tables:
            if table not in tables:
                issues.append(f"Missing required table: {table}")
        
        # Check sessions integrity
        if "sessions" in tables:
            cursor.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]
            
            # Check for null session_ids
            cursor.execute("SELECT id FROM sessions WHERE session_id IS NULL")
            if cursor.fetchone():
                issues.append("Found sessions with NULL session_id")
            
            # Check for duplicate session_ids
            cursor.execute("""
                SELECT session_id, COUNT(*) as cnt 
                FROM sessions 
                GROUP BY session_id 
                HAVING cnt > 1
            """)
            duplicates = cursor.fetchall()
            if duplicates:
                issues.append(f"Duplicate session_ids: {[d[0] for d in duplicates]}")
        
        # Check archive integrity
        if "archive" in tables:
            cursor.execute("SELECT COUNT(*) FROM archive")
            count = cursor.fetchone()[0]
            
            cursor.execute("SELECT id FROM archive WHERE session_id IS NULL")
            if cursor.fetchone():
                issues.append("Found archived sessions with NULL session_id")
        
        # Check schema version
        if "schema_version" in tables:
            cursor.execute("SELECT version, applied_at FROM schema_version ORDER BY applied_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                warnings.append(f"Current schema version: {row[0]}, applied: {row[1]}")
        
    finally:
        conn.close()
    
    return {
        "integrity_valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc).isoformat() + "Z"
    }
