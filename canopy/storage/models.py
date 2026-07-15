"""
Storage Models 📦
Data models for durable session storage
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum


class SessionStatus(str, Enum):
    """Session status values."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


@dataclass
class StoredEvent:
    """Stored event with ordering."""
    event_index: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    hash: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredEvent":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StoredTimeline:
    """Stored timeline with tracks and keyframes."""
    duration_frames: int = 240
    fps: int = 30
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredTimeline":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StoredFrameHash:
    """Stored frame hash for quick verification."""
    frame_index: int
    pixel_hash: str
    manifest_hash: str = ""
    event_log_hash: str = ""
    computed_at: str = ""
    
    def __post_init__(self):
        if not self.computed_at:
            self.computed_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredFrameHash":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ClientConnection:
    """Client WebSocket connection metadata."""
    connection_id: str
    client_ip: str = ""
    user_agent: str = ""
    connected_at: str = ""
    last_sequence: int = 0
    last_ack: int = 0
    reconnect_token: str = ""
    
    def __post_init__(self):
        if not self.connected_at:
            self.connected_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConnection":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class StoredSession:
    """Complete session data for storage."""
    session_id: str
    status: str = SessionStatus.ACTIVE.value
    schema_version: str = "2.0"
    engine_version: str = "1.0.0"
    
    # Manifest data
    base_manifest: Dict[str, Any] = field(default_factory=dict)
    current_manifest: Dict[str, Any] = field(default_factory=dict)
    
    # Event history
    events: List[StoredEvent] = field(default_factory=list)
    event_cursor: int = 0  # Cursor position (for undo/redo)
    abandoned_future: List[StoredEvent] = field(default_factory=list)  # Future events after undo
    
    # Branch lineage
    parent_session_id: Optional[str] = None
    fork_event_index: Optional[int] = None
    
    # Timeline
    timeline: Optional[StoredTimeline] = None
    
    # Frame hashes
    frame_hashes: Dict[int, StoredFrameHash] = field(default_factory=dict)
    
    # Client connections
    connections: List[ClientConnection] = field(default_factory=list)
    
    # Metadata
    created_at: str = ""
    updated_at: str = ""
    closed_at: Optional[str] = None
    version: int = 0  # Optimistic locking version
    
    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat() + "Z"
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "session_id": self.session_id,
            "status": self.status,
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "base_manifest": self.base_manifest,
            "current_manifest": self.current_manifest,
            "events": [e.to_dict() for e in self.events],
            "event_cursor": self.event_cursor,
            "abandoned_future": [e.to_dict() for e in self.abandoned_future],
            "parent_session_id": self.parent_session_id,
            "fork_event_index": self.fork_event_index,
            "timeline": self.timeline.to_dict() if self.timeline else None,
            "frame_hashes": {str(k): v.to_dict() for k, v in self.frame_hashes.items()},
            "connections": [c.to_dict() for c in self.connections],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "version": self.version,
        }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StoredSession":
        events = [StoredEvent.from_dict(e) for e in data.get("events", [])]
        abandoned = [StoredEvent.from_dict(e) for e in data.get("abandoned_future", [])]
        
        frame_hashes = {}
        for k, v in data.get("frame_hashes", {}).items():
            frame_hashes[int(k)] = StoredFrameHash.from_dict(v)
        
        timeline = None
        if data.get("timeline"):
            timeline = StoredTimeline.from_dict(data["timeline"])
        
        connections = [ClientConnection.from_dict(c) for c in data.get("connections", [])]
        
        return cls(
            session_id=data["session_id"],
            status=data.get("status", SessionStatus.ACTIVE.value),
            schema_version=data.get("schema_version", "2.0"),
            engine_version=data.get("engine_version", "1.0.0"),
            base_manifest=data.get("base_manifest", {}),
            current_manifest=data.get("current_manifest", {}),
            events=events,
            event_cursor=data.get("event_cursor", 0),
            abandoned_future=abandoned,
            parent_session_id=data.get("parent_session_id"),
            fork_event_index=data.get("fork_event_index"),
            timeline=timeline,
            frame_hashes=frame_hashes,
            connections=connections,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            closed_at=data.get("closed_at"),
            version=data.get("version", 0),
        )
    
    def get_active_events(self) -> List[StoredEvent]:
        """Get events up to current cursor."""
        return self.events[:self.event_cursor]
    
    def has_abandoned_future(self) -> bool:
        """Check if there are abandoned future events."""
        return len(self.abandoned_future) > 0
    
    def is_closed(self) -> bool:
        """Check if session is closed."""
        return self.status in (SessionStatus.CLOSED.value, SessionStatus.ARCHIVED.value)
    
    def touch(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat() + "Z"
        self.version += 1


def create_stored_session(session_id: str, manifest: Dict[str, Any], seed: int = 42) -> StoredSession:
    """Factory function to create a new stored session."""
    return StoredSession(
        session_id=session_id,
        base_manifest=manifest,
        current_manifest=dict(manifest),
        events=[],
        event_cursor=0,
    )
