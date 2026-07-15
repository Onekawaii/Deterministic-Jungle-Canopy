"""
Timeline and Interpolation 🎬
Animation timeline with deterministic keyframe evaluation
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum

from .schema import SchemaError, InterpolationType


class Interpolation(str, Enum):
    """Interpolation methods."""
    STEP = "step"
    LINEAR = "linear"
    SMOOTHSTEP = "smoothstep"


@dataclass
class Keyframe:
    """A single keyframe in a track."""
    frame: int  # Frame number
    value: float  # Value at this frame
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Keyframe":
        return cls(frame=data["frame"], value=float(data["value"]))


@dataclass
class Track:
    """An animation track targeting a specific parameter."""
    track_id: str
    target: str  # e.g., "effects.glitch.intensity"
    interpolation: Interpolation = Interpolation.LINEAR
    keyframes: List[Keyframe] = field(default_factory=list)
    
    def __post_init__(self):
        # Sort keyframes by frame
        self.keyframes.sort(key=lambda k: k.frame)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "target": self.target,
            "interpolation": self.interpolation.value,
            "keyframes": [k.to_dict() for k in self.keyframes],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Track":
        interp = Interpolation(data.get("interpolation", "linear"))
        keyframes = [Keyframe.from_dict(k) for k in data.get("keyframes", [])]
        return cls(
            track_id=data["track_id"],
            target=data["target"],
            interpolation=interp,
            keyframes=keyframes,
        )
    
    def add_keyframe(self, frame: int, value: float) -> None:
        """Add or update a keyframe at the given frame."""
        # Remove existing keyframe at this frame
        self.keyframes = [k for k in self.keyframes if k.frame != frame]
        self.keyframes.append(Keyframe(frame=frame, value=value))
        self.keyframes.sort(key=lambda k: k.frame)
    
    def remove_keyframe(self, frame: int) -> bool:
        """Remove a keyframe at the given frame."""
        original_count = len(self.keyframes)
        self.keyframes = [k for k in self.keyframes if k.frame != frame]
        return len(self.keyframes) < original_count
    
    def evaluate(self, frame: int) -> Optional[float]:
        """Evaluate the track value at the given frame."""
        if not self.keyframes:
            return None
        
        if frame <= self.keyframes[0].frame:
            return self.keyframes[0].value
        
        if frame >= self.keyframes[-1].frame:
            return self.keyframes[-1].value
        
        # Find surrounding keyframes
        for i in range(len(self.keyframes) - 1):
            kf1 = self.keyframes[i]
            kf2 = self.keyframes[i + 1]
            
            if kf1.frame <= frame <= kf2.frame:
                # Interpolate
                t = (frame - kf1.frame) / (kf2.frame - kf1.frame)
                
                if self.interpolation == Interpolation.STEP:
                    return kf1.value
                elif self.interpolation == Interpolation.LINEAR:
                    return kf1.value + t * (kf2.value - kf1.value)
                elif self.interpolation == Interpolation.SMOOTHSTEP:
                    t_smooth = t * t * (3 - 2 * t)  # Hermite smoothstep
                    return kf1.value + t_smooth * (kf2.value - kf1.value)
        
        return None
    
    def get_hash(self) -> str:
        """Get deterministic hash of the track."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Timeline:
    """Complete animation timeline."""
    duration_frames: int = 240
    fps: int = 30
    tracks: List[Track] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_frames": self.duration_frames,
            "fps": self.fps,
            "tracks": [t.to_dict() for t in self.tracks],
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Timeline":
        tracks = [Track.from_dict(t) for t in data.get("tracks", [])]
        return cls(
            duration_frames=data.get("duration_frames", 240),
            fps=data.get("fps", 30),
            tracks=tracks,
        )
    
    def add_track(self, track: Track) -> None:
        """Add a new track."""
        # Check for duplicate track_id
        if any(t.track_id == track.track_id for t in self.tracks):
            raise ValueError(f"Track with id '{track.track_id}' already exists")
        self.tracks.append(track)
    
    def remove_track(self, track_id: str) -> bool:
        """Remove a track by ID."""
        original_count = len(self.tracks)
        self.tracks = [t for t in self.tracks if t.track_id != track_id]
        return len(self.tracks) < original_count
    
    def get_track(self, track_id: str) -> Optional[Track]:
        """Get a track by ID."""
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        return None
    
    def evaluate_frame(self, frame: int) -> Dict[str, float]:
        """Evaluate all tracks at a given frame."""
        values = {}
        for track in self.tracks:
            value = track.evaluate(frame)
            if value is not None:
                values[track.target] = value
        return values
    
    def get_hash(self) -> str:
        """Get deterministic hash of the timeline."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()
    
    def get_duration_seconds(self) -> float:
        """Get timeline duration in seconds."""
        return self.duration_frames / self.fps


def interpolate_step(t: float, v0: float, v1: float) -> float:
    """Step interpolation."""
    return v0 if t < 1.0 else v1


def interpolate_linear(t: float, v0: float, v1: float) -> float:
    """Linear interpolation."""
    return v0 + t * (v1 - v0)


def interpolate_smoothstep(t: float, v0: float, v1: float) -> float:
    """Smoothstep (Hermite) interpolation."""
    t_smooth = t * t * (3 - 2 * t)
    return v0 + t_smooth * (v1 - v0)


def interpolate_value(t: float, v0: float, v1: float, method: Interpolation) -> float:
    """Interpolate with specified method."""
    if method == Interpolation.STEP:
        return interpolate_step(t, v0, v1)
    elif method == Interpolation.LINEAR:
        return interpolate_linear(t, v0, v1)
    elif method == Interpolation.SMOOTHSTEP:
        return interpolate_smoothstep(t, v0, v1)
    return v0


def apply_timeline_to_manifest(manifest: Dict[str, Any], timeline: Timeline, 
                               frame: int) -> Dict[str, Any]:
    """
    Apply timeline values to a manifest at a given frame.
    
    Returns a new manifest dict with timeline values applied.
    """
    result = dict(manifest)
    values = timeline.evaluate_frame(frame)
    
    for target, value in values.items():
        # Parse target path (e.g., "effects.glitch.intensity")
        parts = target.split(".")
        
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Set the value
        current[parts[-1]] = value
    
    return result


def validate_keyframe_value(value: Any) -> float:
    """Validate and normalize a keyframe value."""
    import math
    
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            raise SchemaError(
                "Keyframe value cannot be NaN or Infinity",
                code="INVALID_TIMELINE"
            )
        return f
    raise SchemaError(
        f"Keyframe value must be numeric, got {type(value).__name__}",
        code="INVALID_TIMELINE"
    )
