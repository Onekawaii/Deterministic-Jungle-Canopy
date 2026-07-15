"""
Canopy Schema Module 📜
Explicit schema definitions and validation for v2.0
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import math


# Schema version
CURRENT_SCHEMA_VERSION = "2.0"
SUPPORTED_SCHEMA_VERSIONS = ["1.0", "2.0"]


class SchemaError(Exception):
    """Schema validation error with structured details."""
    def __init__(self, message: str, path: str = "", value: Any = None, code: str = "SCHEMA_ERROR"):
        self.code = code
        self.message = message
        self.path = path
        self.value = value
        super().__init__(f"{path}: {message}" if path else message)


class EventType(str, Enum):
    """Valid event types."""
    SET_EFFECT = "set_effect"
    DISABLE_EFFECT = "disable_effect"
    ENABLE_EFFECT = "enable_effect"
    GRID_DEFORM = "grid_deform"
    SET_PARAMETER = "set_parameter"
    APPLY_PRESET = "apply_preset"
    SET_PALETTE = "set_palette"
    SET_SEED = "set_seed"
    TIMELINE_TRACK = "timeline_track"
    TIMELINE_KEYFRAME = "timeline_keyframe"


class InterpolationType(str, Enum):
    """Valid interpolation types."""
    STEP = "step"
    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"


class SessionStatus(str, Enum):
    """Valid session statuses."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    ARCHIVED = "archived"


@dataclass
class ManifestSchema:
    """Manifest schema v2.0"""
    schema_version: str = "2.0"
    engine_version: str = "1.0.0"
    seed: int = 42
    width: int = 256
    height: int = 256
    preset_name: Optional[str] = None
    effects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    grid_params: Dict[str, Any] = field(default_factory=dict)
    palette: Optional[List[str]] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestSchema":
        """Create from dict with validation."""
        validate_manifest(data)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EventSchema:
    """Event schema v2.0"""
    event_index: int
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0"
    timestamp: Optional[str] = None  # Optional, used for display only
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventSchema":
        """Create from dict with validation."""
        validate_event(data)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TimelineTrackSchema:
    """Timeline track schema v2.0"""
    track_id: str
    target: str  # e.g., "effects.glitch.intensity"
    interpolation: str = "linear"  # step, linear, smoothstep
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimelineTrackSchema":
        validate_timeline_track(data)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TimelineSchema:
    """Timeline schema v2.0"""
    schema_version: str = "2.0"
    duration_frames: int = 240
    fps: int = 30
    tracks: List[TimelineTrackSchema] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["tracks"] = [t.to_dict() for t in self.tracks]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimelineSchema":
        validate_timeline(data)
        tracks = [TimelineTrackSchema.from_dict(t) for t in data.get("tracks", [])]
        return cls(
            schema_version=data.get("schema_version", "2.0"),
            duration_frames=data.get("duration_frames", 240),
            fps=data.get("fps", 30),
            tracks=tracks
        )


@dataclass
class SessionSchema:
    """Session schema v2.0"""
    session_id: str
    status: str = "active"
    base_manifest: Dict[str, Any] = field(default_factory=dict)
    current_manifest: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    event_cursor: int = 0
    abandoned_future: List[Dict[str, Any]] = field(default_factory=list)
    parent_session_id: Optional[str] = None
    fork_event_index: Optional[int] = None
    timeline: Optional[Dict[str, Any]] = None
    selected_frame_hashes: Dict[str, str] = field(default_factory=dict)
    schema_version: str = "2.0"
    schema_version_session: str = "2.0"
    engine_version: str = "1.0.0"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSchema":
        validate_session(data)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ArchiveEntrySchema:
    """Archive entry schema v2.0"""
    session_id: str
    status: str = "active"
    base_manifest: Dict[str, Any] = field(default_factory=dict)
    current_manifest: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    timeline: Optional[Dict[str, Any]] = None
    schema_version: str = "2.0"
    archived_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────
# Validation Functions
# ─────────────────────────────────────────────────────────────────

def validate_manifest(data: Dict[str, Any]) -> None:
    """Validate manifest data."""
    if not isinstance(data, dict):
        raise SchemaError("Manifest must be a dictionary", code="INVALID_MANIFEST")
    
    # Schema version check
    schema_ver = data.get("schema_version", "1.0")
    if schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaError(
            f"Unsupported schema version: {schema_ver}",
            path="schema_version",
            value=schema_ver,
            code="UNSUPPORTED_SCHEMA"
        )
    
    # Required fields
    if "seed" not in data:
        raise SchemaError("Missing required field: seed", path="seed", code="INVALID_MANIFEST")
    
    seed = data["seed"]
    if not isinstance(seed, int) or seed < 0:
        raise SchemaError("seed must be a non-negative integer", path="seed", value=seed, code="INVALID_MANIFEST")
    
    # Width/height
    for field in ["width", "height"]:
        if field in data:
            val = data[field]
            if not isinstance(val, int) or val <= 0 or val > 4096:
                raise SchemaError(f"{field} must be 1-4096", path=field, value=val, code="INVALID_MANIFEST")
    
    # Effects validation
    if "effects" in data:
        if not isinstance(data["effects"], dict):
            raise SchemaError("effects must be a dictionary", path="effects", code="INVALID_MANIFEST")
        for name, params in data["effects"].items():
            if not isinstance(params, dict):
                raise SchemaError(f"Effect '{name}' params must be a dictionary", path=f"effects.{name}", code="INVALID_MANIFEST")
            for k, v in params.items():
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    raise SchemaError(f"Effect param '{k}' cannot be NaN or Infinity", path=f"effects.{name}.{k}", code="INVALID_MANIFEST")
    
    # Palette validation
    if "palette" in data and data["palette"]:
        palette = data["palette"]
        if not isinstance(palette, list):
            raise SchemaError("palette must be a list", path="palette", code="INVALID_MANIFEST")
        for i, color in enumerate(palette):
            if not isinstance(color, str) or not re.match(r'^#[0-9a-fA-F]{6}$', color):
                raise SchemaError(f"Invalid hex color: {color}", path=f"palette[{i}]", value=color, code="INVALID_MANIFEST")


def validate_event(data: Dict[str, Any]) -> None:
    """Validate event data."""
    if not isinstance(data, dict):
        raise SchemaError("Event must be a dictionary", code="INVALID_EVENT")
    
    # Required fields
    if "event_index" not in data:
        raise SchemaError("Missing required field: event_index", path="event_index", code="INVALID_EVENT")
    
    if "event_type" not in data:
        raise SchemaError("Missing required field: event_type", path="event_type", code="INVALID_EVENT")
    
    # Validate event_index
    idx = data["event_index"]
    if not isinstance(idx, int) or idx < 0:
        raise SchemaError("event_index must be non-negative integer", path="event_index", value=idx, code="INVALID_EVENT")
    
    # Validate event_type
    event_type = data["event_type"]
    valid_types = [e.value for e in EventType]
    if event_type not in valid_types:
        raise SchemaError(
            f"Invalid event_type: {event_type}",
            path="event_type",
            value=event_type,
            code="INVALID_EVENT"
        )
    
    # Payload validation
    if "payload" in data:
        if not isinstance(data["payload"], dict):
            raise SchemaError("payload must be a dictionary", path="payload", code="INVALID_EVENT")
        for k, v in data["payload"].items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                raise SchemaError(f"Payload key '{k}' cannot be NaN or Infinity", path=f"payload.{k}", code="INVALID_EVENT")


def validate_timeline_track(data: Dict[str, Any]) -> None:
    """Validate timeline track data."""
    if not isinstance(data, dict):
        raise SchemaError("Timeline track must be a dictionary", code="INVALID_TIMELINE")
    
    # Required fields
    if "track_id" not in data:
        raise SchemaError("Missing required field: track_id", path="track_id", code="INVALID_TIMELINE")
    
    if "target" not in data:
        raise SchemaError("Missing required field: target", path="target", code="INVALID_TIMELINE")
    
    # Validate interpolation
    interp = data.get("interpolation", "linear")
    valid_interps = [i.value for i in InterpolationType]
    if interp not in valid_interps:
        raise SchemaError(
            f"Invalid interpolation: {interp}",
            path="interpolation",
            value=interp,
            code="INVALID_TIMELINE"
        )
    
    # Keyframes validation
    keyframes = data.get("keyframes", [])
    if not isinstance(keyframes, list):
        raise SchemaError("keyframes must be a list", path="keyframes", code="INVALID_TIMELINE")
    
    frame_positions = set()
    for i, kf in enumerate(keyframes):
        if not isinstance(kf, dict):
            raise SchemaError(f"Keyframe {i} must be a dictionary", path=f"keyframes[{i}]", code="INVALID_TIMELINE")
        
        if "frame" not in kf:
            raise SchemaError(f"Keyframe {i} missing frame", path=f"keyframes[{i}].frame", code="INVALID_TIMELINE")
        
        frame = kf["frame"]
        if not isinstance(frame, int) or frame < 0:
            raise SchemaError(f"Keyframe frame must be non-negative", path=f"keyframes[{i}].frame", value=frame, code="INVALID_TIMELINE")
        
        if frame in frame_positions:
            raise SchemaError(
                f"Duplicate keyframe at frame {frame}",
                path=f"keyframes[{i}].frame",
                value=frame,
                code="INVALID_TIMELINE"
            )
        frame_positions.add(frame)


def validate_timeline(data: Dict[str, Any]) -> None:
    """Validate timeline data."""
    if not isinstance(data, dict):
        raise SchemaError("Timeline must be a dictionary", code="INVALID_TIMELINE")
    
    # Duration validation
    if "duration_frames" in data:
        dur = data["duration_frames"]
        if not isinstance(dur, int) or dur <= 0 or dur > 100000:
            raise SchemaError("duration_frames must be 1-100000", path="duration_frames", value=dur, code="INVALID_TIMELINE")
    
    # FPS validation
    if "fps" in data:
        fps = data["fps"]
        if not isinstance(fps, int) or fps <= 0 or fps > 120:
            raise SchemaError("fps must be 1-120", path="fps", value=fps, code="INVALID_TIMELINE")
    
    # Tracks validation
    if "tracks" in data:
        if not isinstance(data["tracks"], list):
            raise SchemaError("tracks must be a list", path="tracks", code="INVALID_TIMELINE")
        for i, track in enumerate(data["tracks"]):
            try:
                validate_timeline_track(track)
            except SchemaError as e:
                e.path = f"tracks[{i}]." + e.path if e.path else f"tracks[{i}]"
                raise


def validate_session(data: Dict[str, Any]) -> None:
    """Validate session data."""
    if not isinstance(data, dict):
        raise SchemaError("Session must be a dictionary", code="INVALID_SESSION")
    
    # Schema version check
    schema_ver = data.get("schema_version_session", data.get("schema_version", "1.0"))
    if schema_ver not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaError(
            f"Unsupported session schema version: {schema_ver}",
            path="schema_version",
            value=schema_ver,
            code="UNSUPPORTED_SCHEMA"
        )
    
    # Required fields
    if "session_id" not in data:
        raise SchemaError("Missing required field: session_id", path="session_id", code="INVALID_SESSION")
    
    # Status validation
    status = data.get("status", "active")
    valid_statuses = [s.value for s in SessionStatus]
    if status not in valid_statuses:
        raise SchemaError(
            f"Invalid status: {status}",
            path="status",
            value=status,
            code="INVALID_SESSION"
        )
    
    # Event cursor validation
    cursor = data.get("event_cursor", 0)
    if not isinstance(cursor, int) or cursor < 0:
        raise SchemaError("event_cursor must be non-negative", path="event_cursor", value=cursor, code="INVALID_SESSION")
    
    # Events validation
    if "events" in data:
        if not isinstance(data["events"], list):
            raise SchemaError("events must be a list", path="events", code="INVALID_SESSION")
        for i, event in enumerate(data["events"]):
            try:
                validate_event(event)
            except SchemaError as e:
                e.path = f"events[{i}]." + e.path if e.path else f"events[{i}]"
                raise
        
        # Check for duplicate indexes
        indexes = [e.get("event_index") for e in data["events"]]
        if len(indexes) != len(set(indexes)):
            raise SchemaError("Duplicate event_index values found", path="events", code="INVALID_SESSION")
        
        # Check for gaps
        sorted_indexes = sorted(indexes)
        for i in range(1, len(sorted_indexes)):
            if sorted_indexes[i] - sorted_indexes[i-1] != 1:
                raise SchemaError(
                    f"Gap in event indexes: {sorted_indexes[i-1]} -> {sorted_indexes[i]}",
                    path="events",
                    code="INVALID_SESSION"
                )
    
    # Timeline validation if present
    if "timeline" in data and data["timeline"]:
        try:
            validate_timeline(data["timeline"])
        except SchemaError as e:
            e.path = "timeline." + e.path if e.path else "timeline"
            raise


def validate_import(data: Dict[str, Any], max_size: int = 10_000_000) -> None:
    """Validate import payload with size and depth limits."""
    import_size = len(json.dumps(data).encode())
    
    if import_size > max_size:
        raise SchemaError(
            f"Import payload too large: {import_size} > {max_size} bytes",
            code="IMPORT_TOO_LARGE"
        )
    
    # Recursive depth check
    def check_depth(obj, depth=0, max_depth=50):
        if depth > max_depth:
            raise SchemaError(
                f"Nesting too deep: {depth} levels",
                code="IMPORT_TOO_LARGE"
            )
        if isinstance(obj, dict):
            for v in obj.values():
                check_depth(v, depth + 1, max_depth)
        elif isinstance(obj, list):
            for item in obj:
                check_depth(item, depth + 1, max_depth)
    
    check_depth(data)


# ─────────────────────────────────────────────────────────────────
# Schema Migration
# ─────────────────────────────────────────────────────────────────

def migrate_from_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate data from schema 1.0 to 2.0."""
    if data.get("schema_version") == "2.0":
        return data  # Already migrated
    
    if data.get("schema_version") not in ["1.0", None, ""]:
        raise SchemaError(
            f"Cannot migrate from schema version: {data.get('schema_version')}",
            code="UNSUPPORTED_SCHEMA"
        )
    
    # Add new v2.0 fields
    migrated = dict(data)
    migrated["schema_version"] = "2.0"
    
    # Add engine version
    if "engine_version" not in migrated:
        migrated["engine_version"] = "1.0.0"
    
    # Add session-specific v2.0 fields
    if "session_id" in migrated:
        migrated["schema_version_session"] = "2.0"
        if "event_cursor" not in migrated:
            migrated["event_cursor"] = len(migrated.get("events", []))
        if "abandoned_future" not in migrated:
            migrated["abandoned_future"] = []
    
    # Add timeline structure if needed
    if "session_id" in migrated and "timeline" not in migrated:
        migrated["timeline"] = {
            "schema_version": "2.0",
            "duration_frames": 240,
            "fps": 30,
            "tracks": []
        }
    
    return migrated


def can_migrate(data: Dict[str, Any]) -> bool:
    """Check if data can be migrated."""
    version = data.get("schema_version", data.get("schema_version_session", None))
    if version is None or version == "1.0":
        return True
    return version == "2.0"


def get_schema_version(data: Dict[str, Any]) -> str:
    """Get schema version from data."""
    return data.get("schema_version", data.get("schema_version_session", "1.0"))
