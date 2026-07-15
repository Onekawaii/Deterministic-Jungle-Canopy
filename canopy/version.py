"""
Canopy Version Module 📌
Tracks the engine version for deterministic manifest contracts.
"""
__version__ = "1.0.0"
__schema_version__ = "2.0"

# Canonical version tuple for compatibility checks
VERSION_TUPLE = (1, 0, 0, "stable")

# RNG algorithm identifier (for manifest)
RNG_ALGORITHM = "PCG64"

# Supported output formats
SUPPORTED_FORMATS = ["png", "gif", "mp4", "webp"]

# Effect schema version (for preset compatibility)
EFFECT_SCHEMA_VERSION = 2

# Release capabilities - v1.0.0 Sovereign Canopy Edition
CAPABILITIES = {
    "deterministic_rendering": True,
    "durable_sessions": True,
    "branching": True,
    "timeline_keyframes": True,
    "multi_canvas_comparison": True,
    "websocket_reconnect": True,
    "archive_migrations": True,
    "browser_receipts": True,
    "undo_redo": True,
    "import_validation": True,
    "backpressure_control": True,
    "metrics_observability": True,
}
