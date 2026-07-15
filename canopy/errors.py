"""
Error Contract 📋
Unified error response format for the entire API
"""
import json
import uuid
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum


class ErrorCode(str, Enum):
    """Standard error codes."""
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_MANIFEST = "INVALID_MANIFEST"
    INVALID_EVENT = "INVALID_EVENT"
    INVALID_TIMELINE = "INVALID_TIMELINE"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_CLOSED = "SESSION_CLOSED"
    SESSION_CONFLICT = "SESSION_CONFLICT"
    BRANCH_CONFLICT = "BRANCH_CONFLICT"
    IMPORT_TOO_LARGE = "IMPORT_TOO_LARGE"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    ARCHIVE_INTEGRITY_FAILURE = "ARCHIVE_INTEGRITY_FAILURE"
    WEBSOCKET_BACKPRESSURE = "WEBSOCKET_BACKPRESSURE"
    RENDER_FAILURE = "RENDER_FAILURE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class ErrorDetail:
    """Detailed error information."""
    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    recoverable: bool = True
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat() + "Z"
        if not self.request_id:
            self.request_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_api_response(self) -> Dict[str, Any]:
        """Format for API response."""
        return {"error": self.to_dict()}


@dataclass
class ErrorReceipt:
    """Persistent error receipt for debugging."""
    error: ErrorDetail
    stack_trace: Optional[str] = None
    request_path: str = ""
    request_method: str = ""
    user_agent: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CanopyError(Exception):
    """Base exception for all Canopy errors."""
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        status_code: int = 400
    ):
        self.error_detail = ErrorDetail(
            code=code.value,
            message=message,
            details=details or {},
            recoverable=recoverable
        )
        self.status_code = status_code
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.error_detail.to_dict()
    
    def to_api_response(self) -> Dict[str, Any]:
        return self.error_detail.to_api_response()


# Specific exceptions
class InvalidRequestError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.INVALID_REQUEST, message, details, True, 400)


class InvalidManifestError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.INVALID_MANIFEST, message, details, False, 400)


class InvalidEventError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.INVALID_EVENT, message, details, False, 400)


class InvalidTimelineError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.INVALID_TIMELINE, message, details, False, 400)


class SessionNotFoundError(CanopyError):
    def __init__(self, session_id: str):
        super().__init__(
            ErrorCode.SESSION_NOT_FOUND,
            f"Session not found: {session_id}",
            {"session_id": session_id},
            True, 404
        )


class SessionClosedError(CanopyError):
    def __init__(self, session_id: str):
        super().__init__(
            ErrorCode.SESSION_CLOSED,
            f"Session is closed: {session_id}",
            {"session_id": session_id},
            True, 410
        )


class SessionConflictError(CanopyError):
    def __init__(self, session_id: str, expected_version: int, actual_version: int):
        super().__init__(
            ErrorCode.SESSION_CONFLICT,
            "The session changed before this operation could be completed",
            {
                "session_id": session_id,
                "expected_version": expected_version,
                "actual_version": actual_version
            },
            True, 409
        )


class BranchConflictError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.BRANCH_CONFLICT, message, details, True, 409)


class ImportTooLargeError(CanopyError):
    def __init__(self, size: int, max_size: int):
        super().__init__(
            ErrorCode.IMPORT_TOO_LARGE,
            f"Import payload too large: {size} bytes (max: {max_size})",
            {"size": size, "max_size": max_size},
            False, 413
        )


class UnsupportedSchemaError(CanopyError):
    def __init__(self, version: str, supported: list):
        super().__init__(
            ErrorCode.UNSUPPORTED_SCHEMA,
            f"Unsupported schema version: {version}",
            {"version": version, "supported_versions": supported},
            False, 400
        )


class ArchiveIntegrityError(CanopyError):
    def __init__(self, message: str, issues: list = None):
        super().__init__(
            ErrorCode.ARCHIVE_INTEGRITY_FAILURE,
            message,
            {"issues": issues or []},
            False, 500
        )


class WebSocketBackpressureError(CanopyError):
    def __init__(self, session_id: str, queue_depth: int):
        super().__init__(
            ErrorCode.WEBSOCKET_BACKPRESSURE,
            "Client send queue is full",
            {"session_id": session_id, "queue_depth": queue_depth},
            True, 503
        )


class RenderFailureError(CanopyError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.RENDER_FAILURE, message, details, False, 500)


class InternalError(CanopyError):
    def __init__(self, message: str = "Internal server error"):
        super().__init__(ErrorCode.INTERNAL_ERROR, message, {}, False, 500)


def handle_exception(exc: Exception, request_path: str = "", 
                     request_method: str = "") -> ErrorDetail:
    """Convert exception to ErrorDetail."""
    if isinstance(exc, CanopyError):
        return exc.error_detail
    
    # Unknown exception - log but don't leak details
    error_id = str(uuid.uuid4())
    
    # Log full traceback for debugging
    print(f"[ERROR {error_id}] {request_method} {request_path}")
    traceback.print_exc()
    
    return ErrorDetail(
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An internal error occurred",
        details={"error_id": error_id},
        recoverable=False,
        request_id=error_id
    )


def error_to_json(error: ErrorDetail) -> str:
    """Convert error to JSON string."""
    return json.dumps(error.to_api_response(), indent=2)


def create_receipt(error: ErrorDetail, request_path: str = "",
                   request_method: str = "", user_agent: str = "") -> ErrorReceipt:
    """Create an error receipt for persistence."""
    return ErrorReceipt(
        error=error,
        stack_trace=traceback.format_exc() if not error.recoverable else None,
        request_path=request_path,
        request_method=request_method,
        user_agent=user_agent
    )
