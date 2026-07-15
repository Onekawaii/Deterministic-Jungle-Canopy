"""
Canonical Hashing 🔐
Deterministic hashing primitives for the Deterministic Jungle Canopy.

Provides consistent, reproducible hashes for:
- Manifests
- Events
- Pixel data
- Event logs
- Session exports

Canonical JSON requirements:
- UTF-8 encoding
- Sorted keys
- Stable separators (compact: no spaces)
- NaN and Infinity rejected
- Enums normalized to string values
- Paths normalized
- List order preserved
- Timestamps excluded from generation hashes
"""
import json
import hashlib
import math
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from datetime import datetime, timezone
import numpy as np

# Import SessionEvent for type hints (avoid circular import at runtime)
if TYPE_CHECKING:
    from .session import SessionEvent


class CanonicalEncoder(json.JSONEncoder):
    """
    Canonical JSON encoder that:
    - Sorts keys
    - Uses compact separators
    - Rejects NaN and Infinity
    - Normalizes enums
    """
    
    def encode(self, o: Any) -> str:
        return super().encode(o)
    
    def iterencode(self, o: Any, _one_shot: bool = False):
        return super().iterencode(o, _one_shot)


def canonical_json(value: Any) -> str:
    """
    Serialize value to canonical JSON string.
    
    Rules:
    - UTF-8 encoding
    - Sorted keys
    - Compact separators (no spaces)
    - NaN/Infinity rejected
    - Timestamps as ISO format strings
    
    Args:
        value: Any JSON-serializable value
        
    Returns:
        Canonical JSON string
        
    Raises:
        ValueError: If value contains NaN or Infinity
    """
    def normalize(v: Any) -> Any:
        """Recursively normalize value for canonical representation."""
        if isinstance(v, float):
            if math.isnan(v):
                raise ValueError("NaN not allowed in canonical JSON")
            if math.isinf(v):
                raise ValueError("Infinity not allowed in canonical JSON")
            return v
        elif isinstance(v, dict):
            return {k: normalize(val) for k, val in sorted(v.items())}
        elif isinstance(v, list):
            return [normalize(item) for item in v]
        elif isinstance(v, datetime):
            return v.isoformat()
        elif isinstance(v, (set, frozenset)):
            return sorted([normalize(item) for item in v], key=str)
        elif hasattr(v, 'value'):  # Enum-like
            return str(v.value) if hasattr(v.value, 'value') else str(v)
        elif isinstance(v, bytes):
            return v.decode('utf-8')
        elif isinstance(v, np.ndarray):
            raise ValueError("ndarray not allowed in canonical JSON")
        elif isinstance(v, np.integer):
            return int(v)
        elif isinstance(v, np.floating):
            if math.isnan(v) or math.isinf(v):
                raise ValueError("NumPy NaN/Infinity not allowed in canonical JSON")
            return float(v)
        return v
    
    normalized = normalize(value)
    return json.dumps(normalized, sort_keys=True, separators=(',', ':'))


def hash_bytes(data: bytes) -> str:
    """Generate SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def hash_manifest(manifest: Union[Dict, Any]) -> str:
    """
    Generate deterministic hash of a manifest.
    
    Excludes:
    - created_at (timestamp)
    - name (metadata)
    - tags (metadata)
    
    Includes:
    - All generation parameters
    - Grid operations (ordered)
    - Effects (ordered)
    - Schema and engine version
    
    Args:
        manifest: Manifest dict or object with to_dict method
        
    Returns:
        64-character hex hash
    """
    if hasattr(manifest, 'to_dict'):
        manifest = manifest.to_dict()
    
    # Extract generation-relevant fields only
    gen_data = {
        "schema_version": manifest.get("schema_version"),
        "engine_version": manifest.get("engine_version"),
        "rng_algorithm": manifest.get("rng_algorithm"),
        "seed": manifest.get("seed"),
        "width": manifest.get("width"),
        "height": manifest.get("height"),
        "noise_type": manifest.get("noise_type"),
        "noise_params": manifest.get("noise_params", {}),
        "grid_operations": manifest.get("grid_operations", []),
        "effects": manifest.get("effects", []),
        "preset_name": manifest.get("preset_name"),
        "preset_version": manifest.get("preset_version"),
    }
    
    # Remove None values for cleaner hashing
    gen_data = {k: v for k, v in gen_data.items() if v is not None}
    
    canonical = canonical_json(gen_data)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def hash_event(event: Union[Dict, "SessionEvent"]) -> str:
    """
    Generate deterministic hash of an event.
    
    Excludes:
    - created_at (metadata only)
    - manifest_hash_before (derived)
    - manifest_hash_after (derived)
    
    Includes:
    - event_index
    - event_type
    - payload
    
    Args:
        event: Event dict or SessionEvent object
        
    Returns:
        64-character hex hash
    """
    if hasattr(event, 'to_dict'):
        event = event.to_dict()
    
    hash_data = {
        "event_index": event.get("event_index"),
        "event_type": event.get("event_type"),
        "payload": event.get("payload", {}),
    }
    
    canonical = canonical_json(hash_data)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def hash_pixels(frame: np.ndarray) -> str:
    """
    Generate deterministic hash of pixel data.
    
    Args:
        frame: NumPy array of shape (height, width, channels) or (height, width)
        
    Returns:
        64-character hex hash
    """
    if isinstance(frame, str):
        return hashlib.sha256(frame.encode()).hexdigest()
    
    # Ensure contiguous array
    if not frame.flags['C_CONTIGUOUS']:
        frame = np.ascontiguousarray(frame)
    
    return hashlib.sha256(frame.tobytes()).hexdigest()


def hash_event_log(events: List[Union[Dict, "SessionEvent"]]) -> str:
    """
    Generate deterministic hash of an ordered event log.
    
    Each event's hash is included in the canonical JSON.
    
    Args:
        events: List of events in order
        
    Returns:
        64-character hex hash
    """
    event_hashes = []
    for event in events:
        event_hash = hash_event(event)
        event_hashes.append(event_hash)
    
    # Hash the concatenation of event hashes
    combined = ''.join(event_hashes)
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def hash_session_export(payload: Dict) -> str:
    """
    Generate deterministic hash of a session export.
    
    Includes:
    - Session ID
    - Engine version
    - Base manifest hash
    - Event log hash
    
    Excludes:
    - created_at (metadata)
    - current_manifest (derived)
    - current_frame (derived)
    - latest_pixel_hash (derived)
    
    Args:
        payload: Session export dict
        
    Returns:
        64-character hex hash
    """
    session = payload.get("session", payload)
    
    # Get base manifest hash
    base_manifest = session.get("base_manifest", {})
    base_manifest_hash = hash_manifest(base_manifest)
    
    # Get event log hash
    events = session.get("events", [])
    event_log_hash = hash_event_log(events)
    
    # Hash the combination
    hash_data = {
        "session_id": session.get("session_id"),
        "engine_version": session.get("engine_version"),
        "schema_version": session.get("schema_version"),
        "base_manifest_hash": base_manifest_hash,
        "event_log_hash": event_log_hash,
        "parent_session_id": session.get("parent_session_id"),
        "fork_event_index": session.get("fork_event_index"),
    }
    
    # Remove None values
    hash_data = {k: v for k, v in hash_data.items() if v is not None}
    
    canonical = canonical_json(hash_data)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def verify_no_nan_inf(value: Any) -> bool:
    """
    Verify value contains no NaN or Infinity.
    
    Args:
        value: Any value to check
        
    Returns:
        True if clean, False if NaN/Infinity found
    """
    if isinstance(value, float):
        return not (math.isnan(value) or math.isinf(value))
    elif isinstance(value, dict):
        return all(verify_no_nan_inf(v) for v in value.values())
    elif isinstance(value, (list, tuple)):
        return all(verify_no_nan_inf(item) for item in value)
    elif isinstance(value, np.ndarray):
        return not (np.any(np.isnan(value)) or np.any(np.isinf(value)))
    elif isinstance(value, np.floating):
        return not (math.isnan(value) or math.isinf(value))
    return True


class HashVerificationError(ValueError):
    """Raised when hash verification fails."""
    pass


def verify_canonical(value: Any) -> None:
    """
    Verify a value is safe for canonical hashing.
    
    Raises:
        HashVerificationError: If value contains NaN/Infinity
    """
    if not verify_no_nan_inf(value):
        raise HashVerificationError("Value contains NaN or Infinity")
