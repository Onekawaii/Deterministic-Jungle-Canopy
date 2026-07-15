"""
Metrics and Observability 📊
Runtime performance and health tracking
"""
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

from .version import __version__, __schema_version__, CAPABILITIES


@dataclass
class MetricsSnapshot:
    """Point-in-time metrics snapshot."""
    timestamp: str
    active_sessions: int
    active_ws_clients: int
    total_renders: int
    render_count_delta: int
    avg_render_latency_ms: float
    avg_event_latency_ms: float
    max_queue_depth: int
    reconnect_count: int
    dropped_renders: int
    archive_operations: int
    import_rejections: int
    integrity_failures: int
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MetricsCollector:
    """Collects and aggregates runtime metrics."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        
        # Counters
        self.render_count = 0
        self.render_count_last = 0
        self.event_count = 0
        self.archive_ops = 0
        self.import_rejections = 0
        self.integrity_failures = 0
        self.reconnect_count = 0
        self.dropped_renders = 0
        
        # Latencies (ms)
        self.render_latencies: List[float] = []
        self.event_latencies: List[float] = []
        self.max_render_latencies = 1000  # Keep last 1000
        
        # Gauges
        self.active_sessions = 0
        self.active_ws_clients = 0
        self.max_queue_depth = 0
        self.current_queue_depth = 0
        
        # Errors
        self.errors_by_code: Dict[str, int] = defaultdict(int)
    
    @contextmanager
    def measure_render(self):
        """Context manager to measure render latency."""
        start = time.perf_counter()
        try:
            yield
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self.render_count += 1
                self.render_latencies.append(latency_ms)
                if len(self.render_latencies) > self.max_render_latencies:
                    self.render_latencies = self.render_latencies[-self.max_render_latencies:]
    
    @contextmanager
    def measure_event(self):
        """Context manager to measure event commit latency."""
        start = time.perf_counter()
        try:
            yield
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self.event_count += 1
                self.event_latencies.append(latency_ms)
                if len(self.event_latencies) > self.max_render_latencies:
                    self.event_latencies = self.event_latencies[-self.max_render_latencies:]
    
    def record_render(self):
        """Record a render completion."""
        with self._lock:
            self.render_count += 1
    
    def record_event_commit(self):
        """Record an event commit."""
        with self._lock:
            self.event_count += 1
    
    def record_archive_op(self):
        """Record an archive operation."""
        with self._lock:
            self.archive_ops += 1
    
    def record_import_rejection(self):
        """Record an import rejection."""
        with self._lock:
            self.import_rejections += 1
    
    def record_integrity_failure(self):
        """Record an integrity failure."""
        with self._lock:
            self.integrity_failures += 1
    
    def record_reconnect(self):
        """Record a WebSocket reconnection."""
        with self._lock:
            self.reconnect_count += 1
    
    def record_dropped_render(self):
        """Record a dropped (superseded) render request."""
        with self._lock:
            self.dropped_renders += 1
    
    def record_error(self, error_code: str):
        """Record an error by code."""
        with self._lock:
            self.errors_by_code[error_code] += 1
    
    def set_active_sessions(self, count: int):
        """Set active session count."""
        with self._lock:
            self.active_sessions = count
    
    def set_active_ws_clients(self, count: int):
        """Set active WebSocket client count."""
        with self._lock:
            self.active_ws_clients = count
    
    def set_queue_depth(self, depth: int):
        """Set current queue depth."""
        with self._lock:
            self.current_queue_depth = depth
            if depth > self.max_queue_depth:
                self.max_queue_depth = depth
    
    def get_snapshot(self) -> MetricsSnapshot:
        """Get a point-in-time snapshot."""
        with self._lock:
            avg_render = sum(self.render_latencies) / len(self.render_latencies) if self.render_latencies else 0
            avg_event = sum(self.event_latencies) / len(self.event_latencies) if self.event_latencies else 0
            
            return MetricsSnapshot(
                timestamp=datetime.now(timezone.utc).isoformat() + "Z",
                active_sessions=self.active_sessions,
                active_ws_clients=self.active_ws_clients,
                total_renders=self.render_count,
                render_count_delta=self.render_count - self.render_count_last,
                avg_render_latency_ms=round(avg_render, 2),
                avg_event_latency_ms=round(avg_event, 2),
                max_queue_depth=self.max_queue_depth,
                reconnect_count=self.reconnect_count,
                dropped_renders=self.dropped_renders,
                archive_operations=self.archive_ops,
                import_rejections=self.import_rejections,
                integrity_failures=self.integrity_failures,
            )
    
    def reset_deltas(self):
        """Reset delta counters."""
        with self._lock:
            self.render_count_last = self.render_count


# Global metrics instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics


def snapshot() -> MetricsSnapshot:
    """Get current metrics snapshot."""
    return _metrics.get_snapshot()


# Health check data
def get_health_detail() -> Dict[str, Any]:
    """Get detailed health information."""
    from .storage import SessionStore
    from .migrations import verify_database_integrity
    import os
    
    metrics = _metrics.get_snapshot()
    
    # Database check
    db_path = os.environ.get("CANOPY_DB_PATH", "canopy_sessions.db")
    db_exists = os.path.exists(db_path)
    db_integrity = {"integrity_valid": True, "issues": [], "warnings": []}
    
    if db_exists:
        try:
            db_integrity = verify_database_integrity(db_path)
        except Exception as e:
            db_integrity = {
                "integrity_valid": False,
                "issues": [str(e)],
                "warnings": []
            }
    
    return {
        "status": "healthy" if db_integrity["integrity_valid"] else "degraded",
        "engine_version": __version__,
        "schema_version": __schema_version__,
        "capabilities": CAPABILITIES,
        "database": {
            "path": db_path,
            "exists": db_exists,
            "integrity": db_integrity,
        },
        "runtime": {
            "uptime_seconds": round(time.time() - _metrics._start_time, 2),
            "process_start": datetime.fromtimestamp(_metrics._start_time, tz=timezone.utc).isoformat() + "Z",
        },
        "metrics": metrics.to_dict(),
        "errors": dict(_metrics.errors_by_code),
    }


def get_health_simple() -> Dict[str, str]:
    """Simple health check."""
    return {"status": "ok"}
