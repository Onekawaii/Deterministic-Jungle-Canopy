"""
Session Store 🏪
Durable SQLite-backed session storage with optimistic locking
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from .models import (
    StoredSession,
    StoredEvent,
    StoredTimeline,
    StoredFrameHash,
    ClientConnection,
    SessionStatus,
    create_stored_session,
)


class SessionLock:
    """Session-level lock for concurrency control."""
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = threading.Lock()
    
    def __enter__(self):
        self._lock.acquire()
        return self
    
    def __exit__(self, *args):
        self._lock.release()


class SessionConflictError(Exception):
    """Raised when optimistic locking detects a conflict."""
    def __init__(self, session_id: str, expected_version: int, actual_version: int):
        self.session_id = session_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(f"Session {session_id} conflict: expected v{expected_version}, got v{actual_version}")


class SessionStore:
    """
    Durable SQLite-backed session storage.
    
    Features:
    - Transactional event commits
    - Optimistic version checking
    - Crash-safe writes
    - Session recovery on restart
    """
    
    def __init__(self, db_path: str = "canopy_sessions.db"):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode for better concurrency
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn.execute("PRAGMA journal_mode = WAL")
        return self._local.conn
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_database(self) -> None:
        """Initialize database schema."""
        with self.transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'active',
                    schema_version TEXT NOT NULL DEFAULT '2.0',
                    engine_version TEXT NOT NULL DEFAULT '1.0.0',
                    base_manifest TEXT NOT NULL DEFAULT '{}',
                    current_manifest TEXT NOT NULL DEFAULT '{}',
                    events TEXT NOT NULL DEFAULT '[]',
                    event_cursor INTEGER NOT NULL DEFAULT 0,
                    abandoned_future TEXT NOT NULL DEFAULT '[]',
                    parent_session_id TEXT,
                    fork_event_index INTEGER,
                    timeline TEXT,
                    frame_hashes TEXT NOT NULL DEFAULT '{}',
                    connections TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    closed_at TEXT,
                    version INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (parent_session_id) REFERENCES sessions(session_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
                CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
                
                CREATE TABLE IF NOT EXISTS schema_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS integrity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_type TEXT NOT NULL,
                    result TEXT NOT NULL,
                    details TEXT,
                    checked_at TEXT NOT NULL
                );
            """)
            
            # Record schema version
            conn.execute("""
                INSERT OR IGNORE INTO schema_version (version, applied_at) 
                VALUES ('2.0', ?)
            """, (datetime.now(timezone.utc).isoformat() + "Z",))
    
    def create_session(self, session_id: str, manifest: Dict[str, Any], 
                      parent_id: Optional[str] = None, 
                      fork_event_idx: Optional[int] = None) -> StoredSession:
        """Create a new session."""
        now = datetime.now(timezone.utc).isoformat() + "Z"
        session = create_stored_session(session_id, manifest)
        session.parent_session_id = parent_id
        session.fork_event_index = fork_event_idx
        
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO sessions (
                    session_id, status, schema_version, engine_version,
                    base_manifest, current_manifest, events, event_cursor,
                    abandoned_future, parent_session_id, fork_event_index,
                    timeline, frame_hashes, connections, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                session.status,
                session.schema_version,
                session.engine_version,
                json.dumps(session.base_manifest),
                json.dumps(session.current_manifest),
                json.dumps([]),
                session.event_cursor,
                json.dumps([]),
                session.parent_session_id,
                session.fork_event_index,
                None,
                json.dumps({}),
                json.dumps([]),
                session.created_at,
                session.updated_at,
                session.version,
            ))
        
        return session
    
    def get_session(self, session_id: str) -> Optional[StoredSession]:
        """Get a session by ID."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        return self._row_to_session(row)
    
    def _row_to_session(self, row: sqlite3.Row) -> StoredSession:
        """Convert database row to StoredSession."""
        return StoredSession(
            session_id=row["session_id"],
            status=row["status"],
            schema_version=row["schema_version"],
            engine_version=row["engine_version"],
            base_manifest=json.loads(row["base_manifest"]),
            current_manifest=json.loads(row["current_manifest"]),
            events=[StoredEvent.from_dict(e) for e in json.loads(row["events"])],
            event_cursor=row["event_cursor"],
            abandoned_future=[StoredEvent.from_dict(e) for e in json.loads(row["abandoned_future"])],
            parent_session_id=row["parent_session_id"],
            fork_event_index=row["fork_event_index"],
            timeline=StoredTimeline.from_dict(json.loads(row["timeline"])) if row["timeline"] else None,
            frame_hashes={int(k): StoredFrameHash.from_dict(v) for k, v in json.loads(row["frame_hashes"]).items()},
            connections=[ClientConnection.from_dict(c) for c in json.loads(row["connections"])],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            version=row["version"],
        )
    
    def save_session(self, session: StoredSession, expected_version: Optional[int] = None) -> None:
        """
        Save a session with optimistic version checking.
        
        Raises SessionConflictError if version mismatch.
        """
        # Check version if specified
        if expected_version is not None:
            current = self.get_session(session.session_id)
            if current and current.version != expected_version:
                raise SessionConflictError(session.session_id, expected_version, current.version)
        
        session.touch()
        
        with self.transaction() as conn:
            conn.execute("""
                UPDATE sessions SET
                    status = ?,
                    current_manifest = ?,
                    events = ?,
                    event_cursor = ?,
                    abandoned_future = ?,
                    timeline = ?,
                    frame_hashes = ?,
                    connections = ?,
                    updated_at = ?,
                    version = ?
                WHERE session_id = ?
            """, (
                session.status,
                json.dumps(session.current_manifest),
                json.dumps([e.to_dict() for e in session.events]),
                session.event_cursor,
                json.dumps([e.to_dict() for e in session.abandoned_future]),
                session.timeline.to_dict() if session.timeline else None,
                json.dumps({str(k): v.to_dict() for k, v in session.frame_hashes.items()}),
                json.dumps([c.to_dict() for c in session.connections]),
                session.updated_at,
                session.version,
                session.session_id,
            ))
    
    def append_event(self, session_id: str, event: StoredEvent,
                    new_manifest: Dict[str, Any]) -> Tuple[StoredSession, int]:
        """
        Append an event to a session atomically.
        
        Returns (updated_session, new_version).
        Raises SessionConflictError on version mismatch.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if session.is_closed():
            raise ValueError(f"Session is closed: {session_id}")
        
        # Clear any abandoned future if we're appending
        if session.has_abandoned_future():
            session.abandoned_future = []
        
        # Append event and update cursor
        session.events.append(event)
        session.event_cursor = len(session.events)
        session.current_manifest = new_manifest
        
        # Save with version check
        expected_version = session.version
        self.save_session(session, expected_version)
        
        return session, session.version
    
    def undo(self, session_id: str, count: int = 1) -> StoredSession:
        """Move cursor backward (undo)."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        new_cursor = max(0, session.event_cursor - count)
        
        if new_cursor < session.event_cursor:
            # Move events to abandoned future
            abandoned = session.events[new_cursor:session.event_cursor]
            session.abandoned_future = abandoned + session.abandoned_future
            session.event_cursor = new_cursor
        
        session.touch()
        self.save_session(session)
        
        return session
    
    def redo(self, session_id: str, count: int = 1) -> StoredSession:
        """Move cursor forward (redo)."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        new_cursor = min(len(session.events), session.event_cursor + count)
        
        if new_cursor > session.event_cursor:
            # Move events from abandoned future back
            to_restore = session.abandoned_future[:new_cursor - session.event_cursor]
            session.abandoned_future = session.abandoned_future[new_cursor - session.event_cursor:]
            session.events = session.events + to_restore
            session.event_cursor = new_cursor
        
        session.touch()
        self.save_session(session)
        
        return session
    
    def jump_to_event(self, session_id: str, event_index: int) -> StoredSession:
        """Jump to a specific event index."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        if event_index < 0 or event_index > len(session.events):
            raise ValueError(f"Invalid event index: {event_index}")
        
        if event_index < session.event_cursor:
            # Moving backward - save future
            abandoned = session.events[event_index:session.event_cursor]
            session.abandoned_future = abandoned + session.abandoned_future
        elif event_index > session.event_cursor:
            # Moving forward - restore from abandoned
            to_restore = session.abandoned_future[:event_index - session.event_cursor]
            session.abandoned_future = session.abandoned_future[event_index - session.event_cursor:]
            session.events = session.events + to_restore
        
        session.event_cursor = event_index
        session.touch()
        self.save_session(session)
        
        return session
    
    def fork_session(self, session_id: str, fork_event_index: int) -> StoredSession:
        """Create a fork of a session at a specific event index."""
        parent = self.get_session(session_id)
        if not parent:
            raise ValueError(f"Session not found: {session_id}")
        
        # Create new session with fork
        import uuid
        fork_id = str(uuid.uuid4())
        
        # Use events up to fork point
        fork_events = parent.events[:fork_event_index]
        
        fork_session = StoredSession(
            session_id=fork_id,
            parent_session_id=session_id,
            fork_event_index=fork_event_index,
            base_manifest=parent.base_manifest,
            current_manifest=parent.current_manifest if fork_event_index == len(parent.events) else parent.events[fork_event_index - 1].payload.get("manifest", parent.current_manifest),
            events=fork_events,
            event_cursor=len(fork_events),
        )
        
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO sessions (
                    session_id, status, schema_version, engine_version,
                    base_manifest, current_manifest, events, event_cursor,
                    abandoned_future, parent_session_id, fork_event_index,
                    timeline, frame_hashes, connections, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fork_session.session_id,
                fork_session.status,
                fork_session.schema_version,
                fork_session.engine_version,
                json.dumps(fork_session.base_manifest),
                json.dumps(fork_session.current_manifest),
                json.dumps([e.to_dict() for e in fork_session.events]),
                fork_session.event_cursor,
                json.dumps([]),
                fork_session.parent_session_id,
                fork_session.fork_event_index,
                None,
                json.dumps({}),
                json.dumps([]),
                fork_session.created_at,
                fork_session.updated_at,
                fork_session.version,
            ))
        
        return fork_session
    
    def list_branches(self, session_id: str) -> List[Dict[str, Any]]:
        """List all branches derived from a session."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT session_id, fork_event_index, status, created_at, updated_at
            FROM sessions
            WHERE parent_session_id = ?
            ORDER BY created_at
        """, (session_id,))
        
        return [
            {
                "session_id": row["session_id"],
                "fork_event_index": row["fork_event_index"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in cursor.fetchall()
        ]
    
    def get_active_sessions(self) -> List[StoredSession]:
        """Get all active sessions (for recovery)."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT * FROM sessions
            WHERE status = 'active'
            ORDER BY updated_at DESC
        """)
        
        return [self._row_to_session(row) for row in cursor.fetchall()]
    
    def close_session(self, session_id: str) -> StoredSession:
        """Close a session."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        session.status = SessionStatus.CLOSED.value
        session.closed_at = datetime.now(timezone.utc).isoformat() + "Z"
        session.touch()
        self.save_session(session)
        
        return session
    
    def save_frame_hash(self, session_id: str, frame_index: int,
                        frame_hash: StoredFrameHash) -> None:
        """Save a frame hash for a session."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        session.frame_hashes[frame_index] = frame_hash
        self.save_session(session)
    
    def get_frame_hash(self, session_id: str, frame_index: int) -> Optional[StoredFrameHash]:
        """Get a saved frame hash."""
        session = self.get_session(session_id)
        if not session:
            return None
        return session.frame_hashes.get(frame_index)
    
    def add_connection(self, session_id: str, connection: ClientConnection) -> None:
        """Add a client connection."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        
        session.connections.append(connection)
        self.save_session(session)
    
    def remove_connection(self, session_id: str, connection_id: str) -> None:
        """Remove a client connection."""
        session = self.get_session(session_id)
        if not session:
            return
        
        session.connections = [c for c in session.connections if c.connection_id != connection_id]
        self.save_session(session)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        conn = self._get_connection()
        
        cursor = conn.execute("SELECT status, COUNT(*) as count FROM sessions GROUP BY status")
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
        
        cursor = conn.execute("SELECT COUNT(*) as total FROM sessions")
        total = cursor.fetchone()["total"]
        
        cursor = conn.execute("SELECT COUNT(*) as active FROM sessions WHERE status = 'active'")
        active = cursor.fetchone()["active"]
        
        return {
            "total_sessions": total,
            "active_sessions": active,
            "by_status": by_status,
            "db_path": str(self.db_path),
            "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
        }
    
    def check_integrity(self) -> Dict[str, Any]:
        """Check storage integrity."""
        issues = []
        warnings = []
        
        conn = self._get_connection()
        
        # Check for null session_ids
        cursor = conn.execute("SELECT id FROM sessions WHERE session_id IS NULL")
        if cursor.fetchone():
            issues.append("Found sessions with NULL session_id")
        
        # Check for duplicate session_ids
        cursor = conn.execute("""
            SELECT session_id, COUNT(*) as cnt 
            FROM sessions 
            GROUP BY session_id 
            HAVING cnt > 1
        """)
        duplicates = cursor.fetchall()
        if duplicates:
            issues.append(f"Duplicate session_ids: {[d['session_id'] for d in duplicates]}")
        
        # Check for orphaned children (parent doesn't exist)
        cursor = conn.execute("""
            SELECT s.session_id, s.parent_session_id
            FROM sessions s
            WHERE s.parent_session_id IS NOT NULL
            AND s.parent_session_id NOT IN (SELECT session_id FROM sessions)
        """)
        orphans = cursor.fetchall()
        if orphans:
            warnings.append(f"Found {len(orphans)} orphaned child sessions")
        
        # Check event index consistency
        cursor = conn.execute("""
            SELECT session_id, events, event_cursor
            FROM sessions
            WHERE status = 'active'
        """)
        for row in cursor.fetchall():
            events = json.loads(row["events"])
            if len(events) != row["event_cursor"]:
                # This is OK - cursor can be behind events
                pass
        
        return {
            "integrity_valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "checked_at": datetime.now(timezone.utc).isoformat() + "Z",
        }
