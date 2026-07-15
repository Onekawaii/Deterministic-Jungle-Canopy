"""
Comparison Engine ⚖️
Multi-canvas deterministic comparison
"""
import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .hashing import hash_manifest, hash_event_log


@dataclass
class ComparisonSide:
    """One side of a comparison."""
    session_id: str
    frame_index: int
    pixel_hash: str
    manifest_hash: str
    event_log_hash: str
    timeline_hash: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class ComparisonResult:
    """Result of comparing two sessions."""
    left: ComparisonSide
    right: ComparisonSide
    identical_pixels: bool
    manifest_diff: List[Dict[str, Any]] = field(default_factory=list)
    event_diff: List[Dict[str, Any]] = field(default_factory=list)
    timeline_diff: List[Dict[str, Any]] = field(default_factory=list)
    difference_score: float = 0.0
    compared_at: str = ""
    
    def __post_init__(self):
        if not self.compared_at:
            self.compared_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RangeComparisonResult:
    """Result of comparing frame ranges."""
    left_session_id: str
    right_session_id: str
    start_frame: int
    end_frame: int
    frame_results: List[ComparisonResult]
    summary: Dict[str, Any] = field(default_factory=dict)
    compared_at: str = ""
    
    def __post_init__(self):
        if not self.compared_at:
            self.compared_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compare_events(left_events: List[Dict], right_events: List[Dict]) -> List[Dict[str, Any]]:
    """Compare two event logs and return differences."""
    diffs = []
    
    max_len = max(len(left_events), len(right_events))
    
    for i in range(max_len):
        left_event = left_events[i] if i < len(left_events) else None
        right_event = right_events[i] if i < len(right_events) else None
        
        if left_event is None:
            diffs.append({
                "index": i,
                "type": "right_only",
                "event": right_event
            })
        elif right_event is None:
            diffs.append({
                "index": i,
                "type": "left_only",
                "event": left_event
            })
        elif left_event != right_event:
            diffs.append({
                "index": i,
                "type": "different",
                "left": left_event,
                "right": right_event
            })
    
    return diffs


def compare_manifests(left: Dict, right: Dict, path: str = "") -> List[Dict[str, Any]]:
    """Compare two manifests and return differences."""
    diffs = []
    
    # Get all keys
    all_keys = set(left.keys()) | set(right.keys())
    
    for key in sorted(all_keys):
        current_path = f"{path}.{key}" if path else key
        
        if key not in left:
            diffs.append({
                "path": current_path,
                "type": "right_only",
                "value": right[key]
            })
        elif key not in right:
            diffs.append({
                "path": current_path,
                "type": "left_only",
                "value": left[key]
            })
        elif left[key] != right[key]:
            if isinstance(left[key], dict) and isinstance(right[key], dict):
                # Recurse into nested dicts
                nested_diffs = compare_manifests(left[key], right[key], current_path)
                diffs.extend(nested_diffs)
            else:
                diffs.append({
                    "path": current_path,
                    "type": "different",
                    "left": left[key],
                    "right": right[key]
                })
    
    return diffs


def compare_timelines(left: Dict, right: Dict) -> List[Dict[str, Any]]:
    """Compare two timelines."""
    diffs = []
    
    # Compare basic properties
    for prop in ["duration_frames", "fps"]:
        if left.get(prop) != right.get(prop):
            diffs.append({
                "type": "property",
                "property": prop,
                "left": left.get(prop),
                "right": right.get(prop)
            })
    
    # Compare tracks
    left_tracks = {t["track_id"]: t for t in left.get("tracks", [])}
    right_tracks = {t["track_id"]: t for t in right.get("tracks", [])}
    
    all_track_ids = set(left_tracks.keys()) | set(right_tracks.keys())
    
    for track_id in sorted(all_track_ids):
        if track_id not in left_tracks:
            diffs.append({
                "type": "track_right_only",
                "track_id": track_id
            })
        elif track_id not in right_tracks:
            diffs.append({
                "type": "track_left_only",
                "track_id": track_id
            })
        else:
            # Compare keyframes
            left_kf = {k["frame"]: k["value"] for k in left_tracks[track_id].get("keyframes", [])}
            right_kf = {k["frame"]: k["value"] for k in right_tracks[track_id].get("keyframes", [])}
            
            all_frames = set(left_kf.keys()) | set(right_kf.keys())
            
            for frame in sorted(all_frames):
                if frame not in left_kf:
                    diffs.append({
                        "type": "keyframe_right_only",
                        "track_id": track_id,
                        "frame": frame,
                        "value": right_kf[frame]
                    })
                elif frame not in right_kf:
                    diffs.append({
                        "type": "keyframe_left_only",
                        "track_id": track_id,
                        "frame": frame,
                        "value": left_kf[frame]
                    })
                elif left_kf[frame] != right_kf[frame]:
                    diffs.append({
                        "type": "keyframe_different",
                        "track_id": track_id,
                        "frame": frame,
                        "left": left_kf[frame],
                        "right": right_kf[frame]
                    })
    
    return diffs


def calculate_difference_score(manifest_diff: List, event_diff: List, 
                              timeline_diff: List) -> float:
    """
    Calculate a deterministic difference score.
    
    The score is based on the number and magnitude of differences.
    This is NOT perceptual - it's a simple deterministic calculation.
    """
    score = 0.0
    
    # Weight different types of differences
    for diff in manifest_diff:
        if diff["type"] == "different":
            # Calculate magnitude of difference for numeric values
            left = diff.get("left")
            right = diff.get("right")
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                diff_magnitude = abs(left - right)
                score += 1.0 + min(diff_magnitude, 100.0)
            else:
                score += 1.0
        else:
            score += 0.5
    
    for diff in event_diff:
        if diff["type"] == "different":
            score += 2.0
        else:
            score += 1.0
    
    for diff in timeline_diff:
        score += 0.5
    
    return round(score, 2)


def compare_sessions(
    left_session: Dict[str, Any],
    right_session: Dict[str, Any],
    left_frame: int = 0,
    right_frame: int = 0
) -> ComparisonResult:
    """
    Compare two sessions at specific frames.
    
    Returns a deterministic ComparisonResult.
    """
    left_events = left_session.get("events", [])
    right_events = right_session.get("events", [])
    
    left_manifest = left_session.get("current_manifest", {})
    right_manifest = right_session.get("current_manifest", {})
    
    left_timeline = left_session.get("timeline")
    right_timeline = right_session.get("timeline")
    
    # Build comparison sides
    left_side = ComparisonSide(
        session_id=left_session.get("session_id", ""),
        frame_index=left_frame,
        pixel_hash="",  # Would come from render
        manifest_hash=hash_manifest(left_manifest),
        event_log_hash=hash_event_log(left_events),
        timeline_hash=left_timeline.get("hash", "") if left_timeline else "",
    )
    
    right_side = ComparisonSide(
        session_id=right_session.get("session_id", ""),
        frame_index=right_frame,
        pixel_hash="",  # Would come from render
        manifest_hash=hash_manifest(right_manifest),
        event_log_hash=hash_event_log(right_events),
        timeline_hash=right_timeline.get("hash", "") if right_timeline else "",
    )
    
    # Compare manifests
    manifest_diff = compare_manifests(left_manifest, right_manifest)
    
    # Compare events
    event_diff = compare_events(left_events, right_events)
    
    # Compare timelines
    timeline_diff = []
    if left_timeline and right_timeline:
        timeline_diff = compare_timelines(left_timeline, right_timeline)
    elif left_timeline != right_timeline:
        timeline_diff = [{"type": "presence", "left": bool(left_timeline), "right": bool(right_timeline)}]
    
    # Calculate difference score
    difference_score = calculate_difference_score(manifest_diff, event_diff, timeline_diff)
    
    return ComparisonResult(
        left=left_side,
        right=right_side,
        identical_pixels=len(manifest_diff) == 0 and len(event_diff) == 0,
        manifest_diff=manifest_diff,
        event_diff=event_diff,
        timeline_diff=timeline_diff,
        difference_score=difference_score,
    )


def compare_frame_ranges(
    left_session: Dict[str, Any],
    right_session: Dict[str, Any],
    start_frame: int,
    end_frame: int
) -> RangeComparisonResult:
    """
    Compare two sessions over a range of frames.
    
    Returns a RangeComparisonResult with per-frame comparisons.
    """
    frame_results = []
    
    for frame in range(start_frame, end_frame + 1):
        result = compare_sessions(left_session, right_session, frame, frame)
        frame_results.append(result)
    
    # Calculate summary
    identical_count = sum(1 for r in frame_results if r.identical_pixels)
    avg_score = sum(r.difference_score for r in frame_results) / len(frame_results) if frame_results else 0
    
    return RangeComparisonResult(
        left_session_id=left_session.get("session_id", ""),
        right_session_id=right_session.get("session_id", ""),
        start_frame=start_frame,
        end_frame=end_frame,
        frame_results=frame_results,
        summary={
            "total_frames": len(frame_results),
            "identical_frames": identical_count,
            "different_frames": len(frame_results) - identical_count,
            "average_difference_score": round(avg_score, 2),
            "identical": identical_count == len(frame_results),
        }
    )


def generate_comparison_receipt(result: ComparisonResult) -> Dict[str, Any]:
    """Generate a receipt for a comparison result."""
    return {
        "schema_version": "1.0",
        "type": "comparison_receipt",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "result": result.to_dict(),
        "deterministic": True,
        "note": "Comparison score is deterministic based on manifest, event, and timeline differences"
    }
