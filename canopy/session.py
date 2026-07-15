"""
The Session Engine 🌀
Live session management for the Deterministic Jungle Canopy.

Each session represents a deterministic rendering timeline that can be:
- Created from a manifest
- Modified through an ordered event log
- Rewound to any point in history
- Forked into independent branches
- Exported and imported
- Archived for later replay

Core invariant: Every visible frame is derivable from:
- canonical manifest
- session ID
- frame index
- ordered event log
- engine version
"""
import uuid
import json
import copy
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
import numpy as np

from .version import __version__, __schema_version__
from .manifest import Manifest, ManifestBuilder, GridOperation, EffectConfig
from .core.renderer import CanopyRenderer


class SessionStatus(str, Enum):
    """Session lifecycle status."""
    ACTIVE = "active"
    CLOSED = "closed"
    FAILED = "failed"


class EventType(str, Enum):
    """Types of events that can modify a session."""
    SET_SEED = "set_seed"
    APPLY_PRESET = "apply_preset"
    SET_EFFECT = "set_effect"
    GRID_DEFORM = "grid_deform"
    SET_PARAMETER = "set_parameter"
    ADVANCE_FRAME = "advance_frame"
    ADD_GRID_OP = "add_grid_op"
    ENABLE_EFFECT = "enable_effect"
    DISABLE_EFFECT = "disable_effect"


@dataclass
class SessionEvent:
    """A single event in the session timeline."""
    event_index: int
    event_type: EventType
    payload: Dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    manifest_hash_before: Optional[str] = None
    manifest_hash_after: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "event_index": self.event_index,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "payload": self.payload,
            "created_at": self.created_at,
            "manifest_hash_before": self.manifest_hash_before,
            "manifest_hash_after": self.manifest_hash_after,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionEvent":
        event_type = data.get("event_type")
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        return cls(
            event_index=data["event_index"],
            event_type=event_type,
            payload=data.get("payload", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            manifest_hash_before=data.get("manifest_hash_before"),
            manifest_hash_after=data.get("manifest_hash_after"),
        )


@dataclass
class Session:
    """
    A deterministic rendering session.
    
    Tracks the complete state evolution through an ordered event log.
    """
    session_id: str
    schema_version: str = __schema_version__
    engine_version: str = __version__
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: SessionStatus = SessionStatus.ACTIVE
    base_manifest: Dict[str, Any] = field(default_factory=dict)
    current_manifest: Dict[str, Any] = field(default_factory=dict)
    current_frame: int = 0
    events: List[SessionEvent] = field(default_factory=list)
    latest_pixel_hash: Optional[str] = None
    parent_session_id: Optional[str] = None
    fork_event_index: Optional[int] = None
    
    # Frame cache for idempotent rendering
    _frame_cache: Dict[int, str] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "created_at": self.created_at,
            "status": self.status.value if isinstance(self.status, SessionStatus) else self.status,
            "base_manifest": self.base_manifest,
            "current_manifest": self.current_manifest,
            "current_frame": self.current_frame,
            "events": [e.to_dict() for e in self.events],
            "latest_pixel_hash": self.latest_pixel_hash,
            "parent_session_id": self.parent_session_id,
            "fork_event_index": self.fork_event_index,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        status = data.get("status", "active")
        if isinstance(status, str):
            status = SessionStatus(status)
        events = [SessionEvent.from_dict(e) for e in data.get("events", [])]
        return cls(
            session_id=data["session_id"],
            schema_version=data.get("schema_version", __schema_version__),
            engine_version=data.get("engine_version", __version__),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=status,
            base_manifest=data.get("base_manifest", {}),
            current_manifest=data.get("current_manifest", {}),
            current_frame=data.get("current_frame", 0),
            events=events,
            latest_pixel_hash=data.get("latest_pixel_hash"),
            parent_session_id=data.get("parent_session_id"),
            fork_event_index=data.get("fork_event_index"),
        )


class SessionManager:
    """
    Manages all active sessions.
    
    Thread-safe session lifecycle management with deterministic replay.
    """
    
    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()
    
    def create_session(self, manifest: Manifest) -> Session:
        """
        Create a new session from a manifest.
        
        Args:
            manifest: The base manifest for this session
            
        Returns:
            New Session instance
        """
        with self._lock:
            session_id = str(uuid.uuid4())
            session = Session(
                session_id=session_id,
                base_manifest=manifest.to_dict(),
                current_manifest=manifest.to_dict(),
                current_frame=0,
                events=[],
                status=SessionStatus.ACTIVE,
            )
            self._sessions[session_id] = session
            return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)
    
    def close_session(self, session_id: str) -> bool:
        """Close a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.CLOSED
                return True
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def _hash_manifest(self, manifest_dict: dict) -> str:
        """Generate a stable hash of a manifest dict."""
        import hashlib
        # Create deterministic representation
        data = {
            "seed": manifest_dict.get("seed"),
            "width": manifest_dict.get("width"),
            "height": manifest_dict.get("height"),
            "noise_type": manifest_dict.get("noise_type"),
            "noise_params": manifest_dict.get("noise_params", {}),
            "grid_operations": manifest_dict.get("grid_operations", []),
            "effects": manifest_dict.get("effects", []),
        }
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
    
    def apply_event(self, session_id: str, event: SessionEvent) -> Tuple[bool, Optional[str]]:
        """
        Apply an event to a session.
        
        Args:
            session_id: Target session
            event: Event to apply
            
        Returns:
            Tuple of (success, error_message)
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False, "Session not found"
            if session.status != SessionStatus.ACTIVE:
                return False, f"Session is {session.status.value}"
            
            # Verify event index is next in sequence
            expected_index = len(session.events)
            if event.event_index != expected_index:
                return False, f"Invalid event index: expected {expected_index}, got {event.event_index}"
            
            # Capture manifest hash before
            hash_before = self._hash_manifest(session.current_manifest)
            event.manifest_hash_before = hash_before
            
            # Apply event to current_manifest
            new_manifest = self._apply_event_to_manifest(session.current_manifest, event)
            session.current_manifest = new_manifest
            
            # Capture manifest hash after
            hash_after = self._hash_manifest(new_manifest)
            event.manifest_hash_after = hash_after
            
            # Update frame if advance_frame
            if event.event_type == EventType.ADVANCE_FRAME:
                session.current_frame = session.current_frame + 1
            
            # Add event to timeline
            session.events.append(event)
            
            return True, None
    
    def _apply_event_to_manifest(self, manifest: dict, event: SessionEvent) -> dict:
        """Apply an event to a manifest dict, returning new manifest."""
        new_manifest = copy.deepcopy(manifest)
        payload = event.payload
        
        event_type = event.event_type
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        
        if event_type == EventType.SET_SEED:
            new_manifest["seed"] = payload.get("seed", 0)
            
        elif event_type == EventType.APPLY_PRESET:
            from .effects.presets import PRESETS
            preset_name = payload.get("preset_name")
            if preset_name and preset_name in PRESETS:
                preset = PRESETS[preset_name]
                new_manifest["effects"] = preset.get("effects", [])
                new_manifest["preset_name"] = preset_name
                
        elif event_type == EventType.SET_EFFECT:
            effect_name = payload.get("effect")
            params = payload.get("params", {})
            effects = new_manifest.get("effects", [])
            # Find and update or add
            found = False
            for i, eff in enumerate(effects):
                if eff.get("name") == effect_name:
                    effects[i] = {"name": effect_name, "params": params, "enabled": True}
                    found = True
                    break
            if not found:
                effects.append({"name": effect_name, "params": params, "enabled": True})
            new_manifest["effects"] = effects
            
        elif event_type == EventType.GRID_DEFORM:
            op_type = payload.get("type", "turbulence")
            params = payload.get("params", {})
            ops = new_manifest.get("grid_operations", [])
            ops.append({"type": op_type, "params": params})
            new_manifest["grid_operations"] = ops
            
        elif event_type == EventType.ADD_GRID_OP:
            op = payload.get("operation", {})
            ops = new_manifest.get("grid_operations", [])
            ops.append(op)
            new_manifest["grid_operations"] = ops
            
        elif event_type == EventType.ENABLE_EFFECT:
            effect_name = payload.get("effect")
            effects = new_manifest.get("effects", [])
            for eff in effects:
                if eff.get("name") == effect_name:
                    eff["enabled"] = True
            new_manifest["effects"] = effects
            
        elif event_type == EventType.DISABLE_EFFECT:
            effect_name = payload.get("effect")
            effects = new_manifest.get("effects", [])
            for eff in effects:
                if eff.get("name") == effect_name:
                    eff["enabled"] = False
            new_manifest["effects"] = effects
            
        elif event_type == EventType.SET_PARAMETER:
            param = payload.get("param")
            value = payload.get("value")
            if param in new_manifest:
                new_manifest[param] = value
        
        return new_manifest
    
    def replay_events(self, manifest: dict, events: List[SessionEvent]) -> dict:
        """Replay events on a manifest to reconstruct state."""
        current = copy.deepcopy(manifest)
        for event in events:
            current = self._apply_event_to_manifest(current, event)
        return current
    
    def render_session_frame(self, session: Session, frame_index: int, 
                              width: int = 128, height: int = 128) -> Tuple[np.ndarray, str]:
        """
        Render a frame for a session deterministically.
        
        Uses the session's event log to reconstruct the renderer state.
        Rendering never mutates the session.
        
        Args:
            session: The session to render
            frame_index: Which frame to render
            
        Returns:
            Tuple of (frame_array, pixel_hash)
        """
        # Reconstruct manifest from base + events up to frame_index
        manifest_dict = copy.deepcopy(session.base_manifest)
        events_to_apply = [e for e in session.events 
                          if e.event_type != EventType.ADVANCE_FRAME 
                          or session.events.index(e) < frame_index]
        manifest_dict = self.replay_events(manifest_dict, events_to_apply)
        
        # Create renderer from manifest
        manifest = Manifest.from_dict(manifest_dict)
        
        # Override dimensions if needed
        manifest.width = width
        manifest.height = height
        
        renderer = CanopyRenderer(width=width, height=height, seed=manifest.seed)
        
        # Apply grid operations
        for op in manifest.grid_operations:
            op_type = op.type if isinstance(op, GridOperation) else op.get("type")
            params = op.params if isinstance(op, GridOperation) else op.get("params", {})
            method_name = f"add_{op_type}"
            if hasattr(renderer.grid, method_name):
                getattr(renderer.grid, method_name)(**params)
        
        # Apply effects
        for eff in manifest.effects:
            if isinstance(eff, EffectConfig):
                name, params, enabled = eff.name, eff.params, eff.enabled
            else:
                name, params, enabled = eff.get("name"), eff.get("params", {}), eff.get("enabled", True)
            if enabled:
                renderer.effects.enable(name)
                for k, v in params.items():
                    renderer.effects.set_param(name, k, v)
        
        # Render frame
        frame = renderer.render_frame()
        
        # Generate pixel hash
        import hashlib
        pixel_hash = hashlib.sha256(frame.tobytes()).hexdigest()
        
        return frame, pixel_hash
    
    def rewind_session(self, session_id: str, event_index: int) -> Tuple[bool, Optional[str]]:
        """
        Rewind a session to a previous event index.
        
        Does NOT delete history - creates a checkpoint.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False, "Session not found"
            if session.status != SessionStatus.ACTIVE:
                return False, f"Session is {session.status.value}"
            
            if event_index < 0 or event_index >= len(session.events):
                return False, f"Invalid event index: {event_index}"
            
            # Reconstruct manifest at that point (include event at event_index)
            events_to_keep = session.events[:event_index + 1]
            session.current_manifest = self.replay_events(
                session.base_manifest, 
                events_to_keep
            )
            session.current_frame = event_index
            
            # Clear frame cache
            session._frame_cache.clear()
            
            return True, None
    
    def fork_session(self, session_id: str, event_index: int) -> Tuple[Optional[Session], Optional[str]]:
        """
        Fork a session from a given event index.
        
        Creates an independent deterministic branch.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None, "Session not found"
            
            # Fork from event_index
            if event_index < 0 or event_index > len(session.events):
                return None, f"Invalid event index: {event_index}"
            
            # Get events up to and including event_index
            fork_events = session.events[:event_index + 1]
            
            new_session_id = str(uuid.uuid4())
            fork_manifest = self.replay_events(session.base_manifest, fork_events)
            
            fork_session = Session(
                session_id=new_session_id,
                base_manifest=session.base_manifest,
                current_manifest=fork_manifest,
                current_frame=event_index,
                events=fork_events,
                status=SessionStatus.ACTIVE,
                parent_session_id=session_id,
                fork_event_index=event_index,
            )
            
            self._sessions[new_session_id] = fork_session
            return fork_session, None
    
    def export_session(self, session_id: str) -> Optional[dict]:
        """Export a session as a portable JSON payload."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            
            # Include all data needed for deterministic replay
            return {
                "export_version": "1.0",
                "engine_version": __version__,
                "session": session.to_dict(),
            }
    
    def import_session(self, payload: dict) -> Tuple[Optional[Session], Optional[str]]:
        """Import a session from a portable JSON payload."""
        try:
            session_data = payload.get("session", payload)
            session = Session.from_dict(session_data)
            
            # Validate it can be replayed
            test_manifest = self.replay_events(
                session.base_manifest,
                session.events
            )
            
            with self._lock:
                # Assign new session ID to avoid collisions
                session.session_id = str(uuid.uuid4())
                session.status = SessionStatus.ACTIVE
                self._sessions[session.session_id] = session
            
            return session, None
        except Exception as e:
            return None, str(e)
    
    def verify_session_integrity(self, session_id: str) -> Tuple[bool, List[str]]:
        """
        Verify a session's integrity.
        
        Checks:
        - Event indexes are contiguous
        - Manifest hashes are consistent
        - Parent/fork relationships are valid
        """
        errors = []
        
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False, ["Session not found"]
            
            # Check event index continuity
            for i, event in enumerate(session.events):
                if event.event_index != i:
                    errors.append(f"Event index discontinuity at position {i}: expected {i}, got {event.event_index}")
            
            # Check manifest hash consistency
            for i, event in enumerate(session.events):
                if i > 0:
                    prev_event = session.events[i - 1]
                    if prev_event.manifest_hash_after != event.manifest_hash_before:
                        errors.append(f"Manifest hash mismatch between events {i-1} and {i}")
            
            # Check parent session exists if this is a fork
            if session.parent_session_id:
                if session.parent_session_id not in self._sessions:
                    errors.append(f"Parent session {session.parent_session_id} not found")
            
            return len(errors) == 0, errors


# Global session manager
_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    """Get the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
