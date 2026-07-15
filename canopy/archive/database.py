"""
The Archive of the Ancients 📜
Stores seeds, timestamps, and manipulation variables.
Never save heavy video files - only the mathematical seeds!
"""
import sqlite3
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from contextlib import contextmanager

# Import manifest for canonical storage
try:
    from ..manifest import Manifest
except ImportError:
    Manifest = None  # Type annotation fallback


class Archive:
    """
    Deterministic configuration archive.
    
    Instead of saving bloated video files, we save:
    - The sacred seed
    - Timestamp
    - Grid manipulation variables
    - Effect parameters
    - AND the canonical manifest for full reproducibility
    
    With these elements, we can ALWAYS reconstruct any visual state.
    """
    
    def __init__(self, db_path: str = "canopy_archive.db"):
        """
        Initialize the archive.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_conn(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_conn() as conn:
            # Check if we need to add manifest column (migration)
            cursor = conn.execute("PRAGMA table_info(canopy_states)")
            columns = [row[1] for row in cursor.fetchall()]
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canopy_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    config_json TEXT NOT NULL,
                    manifest_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    tags TEXT,
                    likes INTEGER DEFAULT 0,
                    views INTEGER DEFAULT 0
                )
            """)
            
            # Add manifest_json column if it doesn't exist
            if "manifest_json" not in columns:
                try:
                    conn.execute("ALTER TABLE canopy_states ADD COLUMN manifest_json TEXT")
                except sqlite3.OperationalError:
                    pass  # Column already exists
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON canopy_states(created_at DESC)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_seed 
                ON canopy_states(seed)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprint
                ON canopy_states(seed, substr(created_at, 1, 16))
            """)
            
            # Recreate FTS table (SQLite doesn't support ALTER for virtual tables)
            try:
                conn.execute("DROP TABLE IF EXISTS canopy_search")
            except:
                pass
            
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS canopy_search 
                USING fts5(name, tags, content=canopy_states, content_rowid=id)
            """)
            
            conn.commit()
    
    def save_state(self, name: str, state: dict, 
                   tags: Optional[List[str]] = None,
                   metadata: Optional[dict] = None,
                   manifest: Optional[Any] = None) -> int:
        """
        Save a configuration state to the archive.
        
        Args:
            name: Human-readable name for this state
            state: Full renderer state dict
            tags: Optional list of tags for searching
            metadata: Additional metadata
            manifest: Optional Manifest object for canonical storage
            
        Returns:
            Entry ID
        """
        entry_uuid = str(uuid.uuid4())
        seed = state.get("seed", 0)
        config_json = json.dumps(state)
        manifest_json = None
        if manifest is not None:
            if hasattr(manifest, 'to_json'):
                manifest_json = manifest.to_json()
            else:
                manifest_json = json.dumps(manifest)
        metadata_json = json.dumps(metadata) if metadata else None
        tag_string = ",".join(tags) if tags else None
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO canopy_states 
                (uuid, name, seed, config_json, manifest_json, metadata_json, created_at, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (entry_uuid, name, seed, config_json, manifest_json, metadata_json, 
                  datetime.now(timezone.utc).isoformat(), tag_string))
            
            entry_id = cursor.lastrowid
            
            # Update FTS index
            conn.execute("""
                INSERT INTO canopy_search (rowid, name, tags)
                VALUES (?, ?, ?)
            """, (entry_id, name, tag_string or ""))
            
            conn.commit()
        
        return entry_id
    
    def load_manifest(self, entry_id: int) -> Optional[Any]:
        """
        Load the canonical manifest for an entry.
        
        Args:
            entry_id: Database entry ID
            
        Returns:
            Manifest object or None
        """
        if Manifest is None:
            return None
            
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT manifest_json FROM canopy_states WHERE id = ?
            """, (entry_id,))
            
            row = cursor.fetchone()
            if row and row["manifest_json"]:
                try:
                    return Manifest.from_json(row["manifest_json"])
                except:
                    return None
        return None
    
    def load_state(self, entry_id: int) -> Optional[dict]:
        """
        Load a configuration state by ID.
        
        Args:
            entry_id: Database entry ID
            
        Returns:
            State dict or None if not found
        """
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT config_json FROM canopy_states WHERE id = ?
            """, (entry_id,))
            
            row = cursor.fetchone()
            if row:
                # Increment view count
                conn.execute("""
                    UPDATE canopy_states SET views = views + 1 WHERE id = ?
                """, (entry_id,))
                conn.commit()
                
                return json.loads(row["config_json"])
        
        return None
    
    def get_entry(self, entry_id: int) -> Optional[dict]:
        """Get entry metadata without loading full config."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, uuid, name, seed, created_at, tags, likes, views,
                       metadata_json
                FROM canopy_states WHERE id = ?
            """, (entry_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "uuid": row["uuid"],
                    "name": row["name"],
                    "seed": row["seed"],
                    "created_at": row["created_at"],
                    "tags": row["tags"].split(",") if row["tags"] else [],
                    "likes": row["likes"],
                    "views": row["views"],
                    "metadata": json.loads(row["metadata_json"]) if row["metadata_json"] else None
                }
        
        return None
    
    def search(self, query: Optional[str] = None,
               seed: Optional[int] = None,
               start_date: Optional[datetime] = None,
               end_date: Optional[datetime] = None,
               tags: Optional[List[str]] = None,
               limit: int = 20,
               offset: int = 0) -> List[dict]:
        """
        Search the archive with various filters.
        
        Args:
            query: Full-text search query
            seed: Filter by exact seed
            start_date: Filter by start date
            end_date: Filter by end date
            tags: Filter by tags (any match)
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of matching entries
        """
        conditions = []
        params = []
        
        # FTS search for text query
        if query:
            conditions.append("id IN (SELECT rowid FROM canopy_search WHERE canopy_search MATCH ?)")
            params.append(query)
        
        # Seed filter
        if seed is not None:
            conditions.append("seed = ?")
            params.append(seed)
        
        # Date range
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date.isoformat())
        
        if end_date:
            conditions.append("created_at <= ?")
            params.append(end_date.isoformat())
        
        # Tags
        if tags:
            tag_conditions = " OR ".join(["tags LIKE ?" for _ in tags])
            conditions.append(f"({tag_conditions})")
            params.extend([f"%{tag}%" for tag in tags])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
            SELECT id, uuid, name, seed, created_at, tags, likes, views
            FROM canopy_states
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        with self._get_conn() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        
        return [
            {
                "id": row["id"],
                "uuid": row["uuid"],
                "name": row["name"],
                "seed": row["seed"],
                "created_at": row["created_at"],
                "tags": row["tags"].split(",") if row["tags"] else [],
                "likes": row["likes"],
                "views": row["views"]
            }
            for row in rows
        ]
    
    def get_recent(self, limit: int = 10) -> List[dict]:
        """Get most recent entries."""
        return self.search(limit=limit)
    
    def get_popular(self, limit: int = 10) -> List[dict]:
        """Get most viewed entries."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT id, uuid, name, seed, created_at, tags, likes, views
                FROM canopy_states
                ORDER BY views DESC, created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
        
        return [
            {
                "id": row["id"],
                "uuid": row["uuid"],
                "name": row["name"],
                "seed": row["seed"],
                "created_at": row["created_at"],
                "tags": row["tags"].split(",") if row["tags"] else [],
                "likes": row["likes"],
                "views": row["views"]
            }
            for row in rows
        ]
    
    def like(self, entry_id: int) -> int:
        """Like an entry. Returns new like count."""
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE canopy_states SET likes = likes + 1 WHERE id = ?
            """, (entry_id,))
            conn.commit()
            
            cursor = conn.execute("""
                SELECT likes FROM canopy_states WHERE id = ?
            """, (entry_id,))
            row = cursor.fetchone()
            return row["likes"] if row else 0
    
    def delete(self, entry_id: int) -> bool:
        """Delete an entry from the archive."""
        with self._get_conn() as conn:
            # Remove from FTS
            conn.execute("DELETE FROM canopy_search WHERE rowid = ?", (entry_id,))
            
            # Remove main entry
            cursor = conn.execute("""
                DELETE FROM canopy_states WHERE id = ?
            """, (entry_id,))
            conn.commit()
            
            return cursor.rowcount > 0
    
    def get_stats(self) -> dict:
        """Get archive statistics."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_entries,
                    COUNT(DISTINCT seed) as unique_seeds,
                    SUM(views) as total_views,
                    SUM(likes) as total_likes,
                    MIN(created_at) as oldest,
                    MAX(created_at) as newest
                FROM canopy_states
            """)
            row = cursor.fetchone()
            
            return {
                "total_entries": row["total_entries"],
                "unique_seeds": row["unique_seeds"],
                "total_views": row["total_views"] or 0,
                "total_likes": row["total_likes"] or 0,
                "oldest": row["oldest"],
                "newest": row["newest"]
            }
    
    def export_entry(self, entry_id: int) -> Optional[dict]:
        """Export a single entry as a portable dict."""
        entry = self.get_entry(entry_id)
        if not entry:
            return None
        
        state = self.load_state(entry_id)
        
        return {
            "entry": entry,
            "state": state
        }
    
    def import_entry(self, data: dict, 
                     new_name: Optional[str] = None) -> int:
        """Import an exported entry."""
        entry = data["entry"]
        state = data["state"]
        
        return self.save_state(
            name=new_name or entry["name"],
            state=state,
            tags=entry.get("tags", []),
            metadata=entry.get("metadata")
        )
    
    def timeline(self, days: int = 7) -> List[dict]:
        """
        Get timeline of entries from the last N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of daily counts
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM canopy_states
                WHERE created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """, (cutoff,))
            rows = cursor.fetchall()
        
        return [
            {"date": row["date"], "count": row["count"]}
            for row in rows
        ]


# ─────────────────────────────────────────────────────────────────
# Session Archive
# ─────────────────────────────────────────────────────────────────

class SessionArchive:
    """
    Persistent storage for sessions.
    
    Stores:
    - Session metadata
    - Base manifest
    - Ordered event log
    - Final manifest
    - Manifest hash
    - Event-log hash
    - Selected frame hashes
    - Parent/fork relationship
    
    Does NOT store every rendered image.
    """
    
    def __init__(self, db_path: str = "canopy_sessions.db"):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _get_conn(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _init_db(self) -> None:
        """Initialize session archive schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS canopy_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    schema_version TEXT NOT NULL,
                    engine_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    base_manifest_json TEXT NOT NULL,
                    current_manifest_json TEXT NOT NULL,
                    events_json TEXT NOT NULL,
                    final_manifest_hash TEXT,
                    event_log_hash TEXT,
                    parent_session_id TEXT,
                    fork_event_index INTEGER,
                    frame_hashes_json TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_id 
                ON canopy_sessions(session_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_parent_session_id 
                ON canopy_sessions(parent_session_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at 
                ON canopy_sessions(created_at DESC)
            """)
            
            conn.commit()
    
    def save_session(self, session: "Session") -> int:
        """
        Save a session to the archive.
        
        Args:
            session: Session object to save
            
        Returns:
            Database entry ID
        """
        from ..hashing import hash_manifest, hash_event_log
        from ..session import Session
        
        if isinstance(session, Session):
            session_data = session.to_dict()
        else:
            session_data = session
        
        base_manifest = session_data.get("base_manifest", {})
        current_manifest = session_data.get("current_manifest", {})
        events = session_data.get("events", [])
        frame_hashes = session_data.get("frame_hashes", {})
        
        base_manifest_hash = hash_manifest(base_manifest)
        final_manifest_hash = hash_manifest(current_manifest)
        event_log_hash = hash_event_log(events)
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT OR REPLACE INTO canopy_sessions 
                (session_id, schema_version, engine_version, status,
                 base_manifest_json, current_manifest_json, events_json,
                 final_manifest_hash, event_log_hash, parent_session_id,
                 fork_event_index, frame_hashes_json, metadata_json,
                 created_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_data.get("session_id"),
                session_data.get("schema_version", "1.0"),
                session_data.get("engine_version"),
                session_data.get("status", "active"),
                json.dumps(base_manifest),
                json.dumps(current_manifest),
                json.dumps([e.to_dict() if hasattr(e, 'to_dict') else e for e in events]),
                final_manifest_hash,
                event_log_hash,
                session_data.get("parent_session_id"),
                session_data.get("fork_event_index"),
                json.dumps(frame_hashes),
                json.dumps(session_data.get("metadata", {})),
                session_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                session_data.get("closed_at"),
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def load_session(self, session_id: str) -> Optional[dict]:
        """
        Load a session from the archive.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            Session data dict or None
        """
        from ..session import Session
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM canopy_sessions WHERE session_id = ?
            """, (session_id,))
            
            row = cursor.fetchone()
        
        if not row:
            return None
        
        return {
            "session_id": row["session_id"],
            "schema_version": row["schema_version"],
            "engine_version": row["engine_version"],
            "status": row["status"],
            "base_manifest": json.loads(row["base_manifest_json"]),
            "current_manifest": json.loads(row["current_manifest_json"]),
            "events": json.loads(row["events_json"]),
            "final_manifest_hash": row["final_manifest_hash"],
            "event_log_hash": row["event_log_hash"],
            "parent_session_id": row["parent_session_id"],
            "fork_event_index": row["fork_event_index"],
            "frame_hashes": json.loads(row["frame_hashes_json"] or "{}"),
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
            "closed_at": row["closed_at"],
        }
    
    def search_sessions(self, query: Optional[str] = None,
                       tags: Optional[List[str]] = None,
                       limit: int = 20,
                       offset: int = 0) -> List[dict]:
        """
        Search sessions.
        
        Args:
            query: Text search query
            tags: Filter by tags
            limit: Max results
            offset: Results offset
            
        Returns:
            List of session summaries
        """
        results = []
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT session_id, engine_version, status,
                       final_manifest_hash, event_log_hash,
                       parent_session_id, created_at
                FROM canopy_sessions
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            for row in cursor.fetchall():
                results.append({
                    "session_id": row["session_id"],
                    "engine_version": row["engine_version"],
                    "status": row["status"],
                    "final_manifest_hash": row["final_manifest_hash"],
                    "event_log_hash": row["event_log_hash"],
                    "parent_session_id": row["parent_session_id"],
                    "created_at": row["created_at"],
                })
        
        return results
    
    def list_session_forks(self, session_id: str) -> List[dict]:
        """
        List all forks of a session.
        
        Args:
            session_id: Parent session ID
            
        Returns:
            List of fork session summaries
        """
        forks = []
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT session_id, fork_event_index, created_at
                FROM canopy_sessions
                WHERE parent_session_id = ?
                ORDER BY created_at ASC
            """, (session_id,))
            
            for row in cursor.fetchall():
                forks.append({
                    "session_id": row["session_id"],
                    "fork_event_index": row["fork_event_index"],
                    "created_at": row["created_at"],
                })
        
        return forks
    
    def verify_session_integrity(self, session_id: str) -> Tuple[bool, List[str]]:
        """
        Verify session integrity after archival.
        
        Checks:
        - Manifest hash matches stored hash
        - Event log hash matches stored hash
        - Parent session exists if applicable
        
        Args:
            session_id: Session to verify
            
        Returns:
            Tuple of (is_valid, error_list)
        """
        from ..hashing import hash_manifest, hash_event_log
        
        errors = []
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT * FROM canopy_sessions WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
        
        if not row:
            return False, ["Session not found"]
        
        # Verify manifest hash
        current_manifest = json.loads(row["current_manifest_json"])
        computed_hash = hash_manifest(current_manifest)
        stored_hash = row["final_manifest_hash"]
        
        if computed_hash != stored_hash:
            errors.append(f"Manifest hash mismatch: computed {computed_hash[:16]} vs stored {stored_hash[:16]}")
        
        # Verify event log hash
        events = json.loads(row["events_json"])
        computed_event_hash = hash_event_log(events)
        stored_event_hash = row["event_log_hash"]
        
        if computed_event_hash != stored_event_hash:
            errors.append(f"Event log hash mismatch: computed {computed_event_hash[:16]} vs stored {stored_event_hash[:16]}")
        
        # Verify parent exists
        parent_id = row["parent_session_id"]
        if parent_id:
            cursor = conn.execute("""
                SELECT session_id FROM canopy_sessions WHERE session_id = ?
            """, (parent_id,))
            if not cursor.fetchone():
                errors.append(f"Parent session {parent_id} not found")
        
        return len(errors) == 0, errors
    
    def close_session(self, session_id: str) -> bool:
        """Close a session in the archive."""
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE canopy_sessions
                SET status = 'closed', closed_at = ?
                WHERE session_id = ?
            """, (datetime.now(timezone.utc).isoformat(), session_id))
            conn.commit()
            return True
    
    def get_stats(self) -> dict:
        """Get session archive statistics."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed,
                    SUM(CASE WHEN parent_session_id IS NOT NULL THEN 1 ELSE 0 END) as forks
                FROM canopy_sessions
            """)
            row = cursor.fetchone()
        
        return {
            "total_sessions": row["total"] or 0,
            "active_sessions": row["active"] or 0,
            "closed_sessions": row["closed"] or 0,
            "total_forks": row["forks"] or 0,
        }
