"""
Security and Import/Export 🔒
Import validation and secure export
"""
import hashlib
import json
import zipfile
import io
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schema import validate_import, validate_session, SchemaError, CURRENT_SCHEMA_VERSION
from .errors import ImportTooLargeError, InvalidRequestError


# Security limits
MAX_IMPORT_SIZE = 10_000_000  # 10 MB
MAX_NESTING_DEPTH = 50
MAX_COLLECTION_LENGTH = 100_000
MAX_STRING_LENGTH = 1_000_000
MAX_FILENAME_LENGTH = 255
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_TOTAL_SIZE = 100_000_000  # 100 MB


@dataclass
class ImportValidationResult:
    """Result of import validation."""
    valid: bool
    errors: List[str] = None
    warnings: List[str] = None
    size_bytes: int = 0
    validated_at: str = ""
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if not self.validated_at:
            self.validated_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExportBundle:
    """Export bundle with manifest and metadata."""
    session_data: Dict[str, Any]
    manifest_data: Dict[str, Any]
    timeline_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = None
    files: List[Tuple[str, bytes]] = None  # (path, content) pairs
    
    def to_zip(self, deterministic_order: bool = True) -> bytes:
        """Create a ZIP bundle."""
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add session data
            zf.writestr(
                "session.json",
                json.dumps(self.session_data, indent=2, sort_keys=deterministic_order)
            )
            
            # Add manifest
            zf.writestr(
                "manifest.json", 
                json.dumps(self.manifest_data, indent=2, sort_keys=deterministic_order)
            )
            
            # Add timeline if present
            if self.timeline_data:
                zf.writestr(
                    "timeline.json",
                    json.dumps(self.timeline_data, indent=2, sort_keys=deterministic_order)
                )
            
            # Add metadata
            metadata = self.metadata or {}
            metadata["exported_at"] = datetime.now(timezone.utc).isoformat() + "Z"
            metadata["schema_version"] = CURRENT_SCHEMA_VERSION
            zf.writestr(
                "metadata.json",
                json.dumps(metadata, indent=2, sort_keys=deterministic_order)
            )
            
            # Add checksum manifest
            checksums = {}
            for name in zf.namelist():
                if name != "checksums.json":
                    data = zf.read(name)
                    checksums[name] = hashlib.sha256(data).hexdigest()
            
            zf.writestr(
                "checksums.json",
                json.dumps(checksums, indent=2, sort_keys=True)
            )
            
            # Add additional files in deterministic order
            if self.files:
                file_paths = sorted(self.files) if deterministic_order else self.files
                for file_path, content in file_paths:
                    safe_path = sanitize_zip_path(file_path)
                    if safe_path:
                        zf.writestr(safe_path, content)
        
        return buffer.getvalue()


def sanitize_zip_path(path: str) -> Optional[str]:
    """
    Sanitize a ZIP entry path to prevent path traversal.
    
    Returns None if the path is invalid.
    """
    # Normalize path
    path = path.replace("\\", "/")
    path = re.sub(r"/+", "/", path)  # Remove duplicate slashes
    path = path.strip("/")  # Remove leading/trailing slashes
    
    # Check for path traversal
    if ".." in path or path.startswith("/"):
        return None
    
    # Check length
    if len(path) > MAX_FILENAME_LENGTH:
        return None
    
    # Check for invalid characters (allow alphanumerics, dash, underscore, dot, slash for dirs)
    if not re.match(r'^[\w\-\./]+$', path):
        return None
    
    return path


def validate_zip_path(path: str) -> bool:
    """Check if a ZIP path is safe."""
    return sanitize_zip_path(path) is not None


def validate_import_payload(data: Dict[str, Any], max_size: int = MAX_IMPORT_SIZE) -> ImportValidationResult:
    """
    Validate an import payload for security.
    
    Checks:
    - Size limits
    - Nesting depth
    - Collection length
    - Invalid values (NaN, Infinity)
    - Unknown event types
    """
    errors = []
    warnings = []
    
    # Check size
    try:
        json_str = json.dumps(data)
        size = len(json_str.encode())
        
        if size > max_size:
            raise ImportTooLargeError(size, max_size)
    except ImportTooLargeError:
        raise
    except Exception as e:
        errors.append(f"Invalid JSON: {e}")
        return ImportValidationResult(False, errors, warnings, 0)
    
    # Check nesting depth
    def check_depth(obj, depth=0):
        if depth > MAX_NESTING_DEPTH:
            raise ImportTooLargeError(depth, MAX_NESTING_DEPTH, "Nesting too deep")
        if isinstance(obj, dict):
            for v in obj.values():
                check_depth(v, depth + 1)
        elif isinstance(obj, list):
            if len(obj) > MAX_COLLECTION_LENGTH:
                raise ImportTooLargeError(len(obj), MAX_COLLECTION_LENGTH, "Collection too large")
            for item in obj:
                check_depth(item, depth + 1)
    
    try:
        check_depth(data)
    except ImportTooLargeError as e:
        errors.append(str(e))
        return ImportValidationResult(False, errors, warnings, size)
    
    # Check for NaN/Infinity
    def check_invalid_values(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                check_invalid_values(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_invalid_values(item, f"{path}[{i}]")
        elif isinstance(obj, float):
            import math
            if math.isnan(obj) or math.isinf(obj):
                errors.append(f"Invalid numeric value at {path}: {obj}")
    
    check_invalid_values(data)
    
    # Validate schema
    if "events" in data or "session_id" in data:
        try:
            validate_session(data)
        except SchemaError as e:
            errors.append(f"Schema error: {e.message}")
    
    # Check for unknown event types
    if "events" in data and isinstance(data["events"], list):
        known_types = [
            "set_effect", "disable_effect", "enable_effect",
            "grid_deform", "set_parameter", "apply_preset",
            "set_palette", "set_seed", "timeline_track", "timeline_keyframe"
        ]
        for i, event in enumerate(data["events"]):
            if isinstance(event, dict) and "event_type" in event:
                if event["event_type"] not in known_types:
                    warnings.append(f"Unknown event type at index {i}: {event['event_type']}")
    
    return ImportValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        size_bytes=size
    )


def create_export_bundle(
    session: Dict[str, Any],
    manifest: Dict[str, Any],
    include_frames: bool = False,
    frame_hashes: Dict[int, str] = None
) -> ExportBundle:
    """Create an export bundle from session data."""
    timeline = session.get("timeline")
    
    metadata = {
        "session_id": session.get("session_id"),
        "engine_version": session.get("engine_version", "1.0.0"),
        "schema_version": session.get("schema_version", "2.0"),
        "parent_session_id": session.get("parent_session_id"),
        "fork_event_index": session.get("fork_event_index"),
        "event_count": len(session.get("events", [])),
    }
    
    if frame_hashes:
        metadata["frame_hashes"] = frame_hashes
    
    return ExportBundle(
        session_data=session,
        manifest_data=manifest,
        timeline_data=timeline,
        metadata=metadata,
    )


def extract_session_from_bundle(zip_data: bytes) -> Tuple[Dict, Dict, Optional[Dict]]:
    """
    Extract session data from a ZIP bundle.
    
    Returns (session, manifest, timeline).
    """
    session = None
    manifest = None
    timeline = None
    
    with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
        # Verify no path traversal
        for name in zf.namelist():
            if not validate_zip_path(name):
                raise InvalidRequestError(f"Unsafe path in bundle: {name}")
        
        # Read files
        if "session.json" in zf.namelist():
            session = json.loads(zf.read("session.json"))
        
        if "manifest.json" in zf.namelist():
            manifest = json.loads(zf.read("manifest.json"))
        
        if "timeline.json" in zf.namelist():
            timeline = json.loads(zf.read("timeline.json"))
        
        # Verify checksums
        if "checksums.json" in zf.namelist():
            stored_checksums = json.loads(zf.read("checksums.json"))
            
            for filename, expected_hash in stored_checksums.items():
                if filename not in zf.namelist():
                    raise InvalidRequestError(f"Missing file in bundle: {filename}")
                
                actual_hash = hashlib.sha256(zf.read(filename)).hexdigest()
                if actual_hash != expected_hash:
                    raise InvalidRequestError(f"Checksum mismatch for {filename}")
    
    if not session:
        raise InvalidRequestError("Bundle missing session.json")
    if not manifest:
        raise InvalidRequestError("Bundle missing manifest.json")
    
    return session, manifest, timeline


def verify_bundle_integrity(zip_data: bytes) -> Dict[str, Any]:
    """Verify the integrity of a ZIP bundle."""
    issues = []
    warnings = []
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            # Check for path traversal
            for name in zf.namelist():
                if not validate_zip_path(name):
                    issues.append(f"Unsafe path: {name}")
            
            # Check required files
            required = ["session.json", "manifest.json", "metadata.json"]
            for req in required:
                if req not in zf.namelist():
                    issues.append(f"Missing required file: {req}")
            
            # Verify checksums if present
            if "checksums.json" in zf.namelist():
                stored_checksums = json.loads(zf.read("checksums.json"))
                for filename, expected_hash in stored_checksums.items():
                    actual_hash = hashlib.sha256(zf.read(filename)).hexdigest()
                    if actual_hash != expected_hash:
                        issues.append(f"Checksum mismatch: {filename}")
            
            # Check total size
            total_size = sum(zf.getinfo(n).file_size for n in zf.namelist())
            if total_size > MAX_ZIP_TOTAL_SIZE:
                warnings.append(f"Bundle total size ({total_size}) exceeds recommended limit")
            
            # Check entry count
            if len(zf.namelist()) > MAX_ZIP_ENTRIES:
                warnings.append(f"Bundle has {len(zf.namelist())} entries, recommended max is {MAX_ZIP_ENTRIES}")
    
    except zipfile.BadZipFile as e:
        issues.append(f"Invalid ZIP file: {e}")
    except Exception as e:
        issues.append(f"Verification error: {e}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "verified_at": datetime.now(timezone.utc).isoformat() + "Z"
    }
