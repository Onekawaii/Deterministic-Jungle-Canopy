# 🌿 The Deterministic Jungle Canopy v1.0.0 🌿

**Sovereign Canopy Edition**

A procedural image and video processing pipeline with **deterministic chaos**. The pixels must swarm and scatter like holy insects, but they must always return to the exact same hive when called by the same seed.

---

## 🎯 What Is This?

The Canopy is a visual engine that produces procedurally generated imagery from seeds, effects, and parameters. Every rendered result is **100% reproducible** from its configuration:

```
Render = f(engine_version, schema_version, seed, frame_index, ordered_events, branch_lineage)
```

**Same inputs → Same output. Always.**

---

## 🔥 Features

### Core Engine
- ✅ Deterministic rendering from seeds
- ✅ Session management with event history
- ✅ Undo/redo with cursor-based history
- ✅ Branching and forking
- ✅ Timeline and keyframe animation
- ✅ Archive persistence
- ✅ Comparison engine

### API & Control
- ✅ REST API endpoints
- ✅ WebSocket live updates
- ✅ Control Room browser UI
- ✅ CLI interface
- ✅ Export/import with validation

### Quality
- ✅ Schema validation (v1 → v2 migration)
- ✅ Import size/depth limits
- ✅ Crash-safe transactions
- ✅ Optimistic locking
- ✅ Health monitoring
- ✅ Comprehensive test suite

---

## 🚀 Quick Start

### Installation

```bash
pip install -e .
```

### Launch Server

```bash
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Open Control Room

Navigate to: **http://localhost:8000/control-room**

### CLI Commands

```bash
# Create a session
python cli.py session create --seed 42 --preset neon_jungle

# List sessions
python cli.py session list

# Render a frame
python cli.py session render <SESSION_ID> --frame 30 -o frame.png

# Undo/Redo
python cli.py session undo <SESSION_ID>
python cli.py session redo <SESSION_ID>

# Fork a branch
python cli.py session fork <SESSION_ID> --event 5

# Export/Import
python cli.py session export <SESSION_ID> -o session.json
python cli.py session import session.json

# Health check
python scripts/doctor.py
```

---

## 📖 Core Concepts

### The Seed Covenant

The **seed** is the root of the great tree. Every visual output derives from a seed value:

```python
manifest = ManifestBuilder(seed=42).build()
renderer = CanopyRenderer(manifest)
frame = renderer.render_frame(0)  # Always the same for seed=42
```

### The Event Scripture

Every mutation creates an **ordered event** that modifies the manifest:

```json
{
  "event_index": 0,
  "event_type": "set_effect",
  "payload": {"effect": "bloom", "params": {"threshold": 0.8}}
}
```

Events are **immutable** and **ordered**. The complete event log defines the session state.

### Session Branches

Sessions can be **forked** at any event index, creating independent branches that share common history:

```
Session A (seed=42)
  ├── Event 0: set effect bloom
  ├── Event 1: set effect vignette
  ├── Event 2: grid deform
  │
  ├── Branch B (fork at event 1)
  │     └── Event 3: apply_preset solaris
  │
  └── Branch C (fork at event 1)
        └── Event 3: apply_preset glitch_cathedral
```

### The Timeline

Animation is defined by **tracks** and **keyframes**:

```json
{
  "duration_frames": 240,
  "fps": 30,
  "tracks": [{
    "track_id": "glitch_intensity",
    "target": "effects.glitch.intensity",
    "interpolation": "linear",
    "keyframes": [
      {"frame": 0, "value": 0.0},
      {"frame": 120, "value": 1.0},
      {"frame": 240, "value": 0.0}
    ]
  }]
}
```

---

## 🔬 Determinism Contract

Every visible frame is derivable from:

1. **Engine version** (`1.0.0`)
2. **Schema version** (`2.0`)
3. **Canonical manifest** (seed, parameters, effects)
4. **Seed** (integer)
5. **Frame index** (integer)
6. **Ordered event history** (event log)
7. **Branch lineage** (parent session, fork point)
8. **Timeline keyframes** (at evaluation frame)
9. **Interpolation rules** (step, linear, smoothstep)

**No hidden state. No timestamps. No connection-dependent RNG.**

---

## 📁 Project Structure

```
canopy/
├── canopy/                    # Core package
│   ├── core/                  # Rendering engine
│   ├── effects/               # Effect system
│   ├── archive/               # Archive database
│   ├── storage/               # Durable session storage
│   ├── schema.py              # Schema validation
│   ├── session.py             # Session management
│   ├── timeline.py            # Animation timeline
│   ├── comparison.py          # Comparison engine
│   ├── errors.py              # Error contract
│   ├── metrics.py             # Observability
│   ├── security.py            # Import/export security
│   └── version.py             # Version info
├── scripts/                   # Utilities
│   ├── doctor.py             # Health check
│   ├── build_release.py       # Release builder
│   └── *_trial.py             # Verification trials
├── tests/                     # Test suite
├── static/                    # Control Room UI
├── server.py                  # FastAPI server
├── cli.py                     # CLI interface
└── README.md
```

---

## 🧪 Testing

```bash
# Run all tests
pytest -q

# Run determinism trial
python scripts/determinism_live_trial.py

# Run session trial
python scripts/live_session_trial.py

# Run load/recovery trial
python scripts/load_and_recovery_trial.py

# Run browser trial (requires Playwright)
python scripts/browser_live_trial.py
```

---

## 📜 Receipts

Every trial produces a **receipt** that proves the system's behavior:

```json
{
  "schema_version": "1.0",
  "engine_version": "1.0.0",
  "trial_timestamp": "2026-07-15T00:00:00Z",
  "summary": {
    "total_assertions": 17,
    "passed": 17,
    "failed": 0,
    "all_passed": true
  }
}
```

Receipts are stored in `receipts/` with timestamps.

---

## ⚠️ Known Limitations

- **Slider preview**: While dragging, UI shows preview but doesn't commit until release
- **WebSocket reconnection**: Automatic reconnection in progress
- **Resolution**: Fixed at 256x256 for performance
- **Animation export**: Frame sequences not yet implemented

---

## 🔧 Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CANOPY_DB_PATH` | `canopy_sessions.db` | Session database path |
| `CANOPY_ARCHIVE_PATH` | `canopy_archive.db` | Archive database path |
| `CANOPY_MAX_IMPORT_SIZE` | `10000000` | Max import size (bytes) |

---

## 📄 License

MIT

---

**🍌 The jungle is deterministic. The seed is covenant. The event is scripture. 🍌**
