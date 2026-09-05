"""
The FastAPI Gates 🚪
The jungle hears the outside world through these endpoints.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import io
import base64
import json
import zipfile
import numpy as np
from PIL import Image

from canopy import CanopyRenderer, Archive
from canopy.version import __version__
from canopy.effects.presets import PRESETS, list_presets, get_preset_description


# ─────────────────────────────────────────────────────────────────
# Initialize the Sacred Application
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="The Deterministic Jungle Canopy",
    description="Procedural image processing with deterministic seeds. "
                "Same seed = same output. Always.",
    version="1.0.0"
)

# CORS for web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize renderer and archive
renderer: Optional[CanopyRenderer] = None
archive: Optional[Archive] = None


def get_renderer() -> CanopyRenderer:
    """Get or create the renderer instance."""
    global renderer
    if renderer is None:
        renderer = CanopyRenderer(width=1280, height=720)
    return renderer


def get_archive() -> Archive:
    """Get or create the archive instance."""
    global archive
    if archive is None:
        archive = Archive()
        get_renderer().bind_archive(archive)
    return archive


# ─────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────

class SeedRequest(BaseModel):
    """Request to set a new seed."""
    seed: int = Field(..., description="The sacred seed value")
    width: int = Field(default=1280, description="Output width")
    height: int = Field(default=720, description="Output height")


class RenderRequest(BaseModel):
    """Request to render a frame."""
    seed: Optional[int] = Field(default=None, description="Seed (uses current if None)")
    width: int = Field(default=1280, description="Output width")
    height: int = Field(default=720, description="Output height")
    effects: List[str] = Field(default_factory=list, description="Effect chain")
    grid_deformation: Optional[str] = Field(default=None, description="Grid effect type")


class AnimationRequest(BaseModel):
    """Request to render an animation."""
    seed: int
    frames: int = Field(default=30, ge=1, le=300, description="Number of frames")
    fps: int = Field(default=30, ge=1, le=120, description="Frames per second")
    width: int = Field(default=1280)
    height: int = Field(default=720)
    effects: List[str] = Field(default_factory=list)


class EffectParamRequest(BaseModel):
    """Request to set an effect parameter."""
    effect: str = Field(..., description="Effect name")
    param: str = Field(..., description="Parameter name")
    value: Any = Field(..., description="Parameter value")


class PresetRequest(BaseModel):
    """Request to apply a preset."""
    preset_name: str = Field(..., description="Name of the preset to apply")


class ArchiveSaveRequest(BaseModel):
    """Request to save current state to archive."""
    name: str = Field(..., description="Name for this snapshot")
    tags: Optional[List[str]] = Field(default=None, description="Searchable tags")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class ArchiveSearchRequest(BaseModel):
    """Request to search the archive."""
    query: Optional[str] = Field(default=None, description="Text search query")
    seed: Optional[int] = Field(default=None, description="Filter by exact seed")
    start_date: Optional[datetime] = Field(default=None)
    end_date: Optional[datetime] = Field(default=None)
    tags: Optional[List[str]] = Field(default=None)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0)


class ConfigImportRequest(BaseModel):
    """Request to import a configuration."""
    config_json: str = Field(..., description="JSON configuration string")


# ─────────────────────────────────────────────────────────────────
# Core Endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    """The entrance to the jungle."""
    return {
        "name": "The Deterministic Jungle Canopy",
        "version": "1.0.0",
        "message": "Same seed = same output. Always.",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health():
    """Check if the jungle is alive."""
    r = get_renderer()
    return {
        "status": "healthy",
        "current_seed": r.rng.seed,
        "effects_enabled": r.effects.get_config()["enabled"],
        "archive_entries": get_archive().get_stats()["total_entries"]
    }


# ─────────────────────────────────────────────────────────────────
# Seed & Rendering Endpoints
# ─────────────────────────────────────────────────────────────────

@app.post("/api/seed")
async def set_seed(req: SeedRequest):
    """Set the sacred seed."""
    r = get_renderer()
    r.reset(seed=req.seed)
    
    return {
        "message": "Seed planted",
        "seed": req.seed,
        "width": req.width,
        "height": req.height
    }


@app.post("/api/render")
async def render_frame(req: RenderRequest):
    """Render a single frame and return as base64 image."""
    r = get_renderer()
    
    # Set seed if provided
    if req.seed is not None:
        r.set_seed(req.seed)
    
    # Set dimensions
    r.width = req.width
    r.height = req.height
    r.grid = r.grid.__class__(req.width, req.height, r.rng)
    
    # Apply grid deformation if specified
    if req.grid_deformation:
        if req.grid_deformation == "kaleidoscope":
            r.grid.add_kaleidoscope(segments=6)
        elif req.grid_deformation == "turbulence":
            r.grid.add_turbulence(octaves=4, intensity=0.05)
        elif req.grid_deformation == "wave":
            r.grid.add_wave(amplitude=0.02, frequency=10, direction="both")
    
    # Enable effects
    for effect in req.effects:
        r.effects.enable(effect)
    
    # Render
    frame = r.render_frame(effect_chain=req.effects)
    
    # Convert to image
    img = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
    
    # Encode as base64
    buffer = io.BytesIO()
    Image.fromarray(img).save(buffer, format="PNG")
    img_b64 = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "seed": r.rng.seed,
        "effects": req.effects,
        "image": f"data:image/png;base64,{img_b64}"
    }


@app.post("/api/render/gif")
async def render_gif(req: AnimationRequest):
    """Render an animation as GIF."""
    r = get_renderer()
    r.set_seed(req.seed)
    r.width = req.width
    r.height = req.height
    
    # Render frames
    frames = []
    for i in range(req.frames):
        # Time-varying parameters
        time = i / req.fps
        
        # Apply grid wave based on time
        if i == 0:
            r.grid.reset()
        r.grid.add_wave(
            amplitude=0.01 * np.sin(time * 2),
            frequency=5,
            direction="x"
        )
        
        frame = r.render_frame(effect_chain=req.effects)
        frames.append((np.clip(frame, 0, 1) * 255).astype(np.uint8))
    
    # Create GIF
    buffer = io.BytesIO()
    images = [Image.fromarray(f) for f in frames]
    images[0].save(
        buffer, 
        format="GIF", 
        save_all=True, 
        append_images=images[1:],
        duration=int(1000/req.fps),
        loop=0
    )
    
    gif_b64 = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "seed": req.seed,
        "frames": req.frames,
        "fps": req.fps,
        "gif": f"data:image/gif;base64,{gif_b64}"
    }


# ─────────────────────────────────────────────────────────────────
# Effect Endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/api/effects")
async def list_effects():
    """List all available effects."""
    r = get_renderer()
    return {
        "effects": list(r.effects._effects.keys()) if r else [],
        "presets": list_presets(),
        "presets_descriptions": {
            name: get_preset_description(name) 
            for name in list_presets()
        }
    }


@app.get("/api/effects/{effect_name}")
async def get_effect_info(effect_name: str):
    """Get information about a specific effect."""
    if renderer is None:
        raise HTTPException(404, "Renderer not initialized")
    
    if effect_name not in renderer.effects._effects:
        raise HTTPException(404, f"Effect '{effect_name}' not found")
    
    config = renderer.effects.get_config()
    return {
        "name": effect_name,
        "enabled": effect_name in config["enabled"],
        "params": config["params"].get(effect_name, {})
    }


@app.post("/api/effects/enable/{effect_name}")
async def enable_effect(effect_name: str):
    """Enable an effect."""
    r = get_renderer()
    if effect_name not in r.effects._effects:
        raise HTTPException(404, f"Effect '{effect_name}' not found")
    
    r.effects.enable(effect_name)
    return {"message": f"Effect '{effect_name}' enabled"}


@app.post("/api/effects/disable/{effect_name}")
async def disable_effect(effect_name: str):
    """Disable an effect."""
    r = get_renderer()
    r.effects.disable(effect_name)
    return {"message": f"Effect '{effect_name}' disabled"}


@app.post("/api/effects/param")
async def set_effect_param(req: EffectParamRequest):
    """Set a parameter for an effect."""
    r = get_renderer()
    if req.effect not in r.effects._effects:
        raise HTTPException(404, f"Effect '{req.effect}' not found")
    
    r.effects.set_param(req.effect, req.param, req.value)
    return {
        "effect": req.effect,
        "param": req.param,
        "value": req.value
    }


@app.post("/api/effects/preset")
async def apply_preset(req: PresetRequest):
    """Apply a preset configuration."""
    r = get_renderer()
    try:
        r.effects.apply_preset(req.preset_name)
        return {
            "message": f"Preset '{req.preset_name}' applied",
            "preset": req.preset_name,
            "description": get_preset_description(req.preset_name),
            "effects": r.effects.get_config()["enabled"]
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


# ─────────────────────────────────────────────────────────────────
# Grid Manipulation Endpoints
# ─────────────────────────────────────────────────────────────────

class GridDeformRequest(BaseModel):
    type: str = Field(..., description="Deformation type")
    params: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/grid/reset")
async def reset_grid():
    """Reset grid to identity transformation."""
    r = get_renderer()
    r.grid.reset()
    return {"message": "Grid reset"}


@app.post("/api/grid/deform")
async def apply_grid_deform(req: GridDeformRequest):
    """Apply a grid deformation."""
    r = get_renderer()
    
    deform_type = req.type
    params = req.params
    
    if deform_type == "wave":
        r.grid.add_wave(
            amplitude=params.get("amplitude", 0.02),
            frequency=params.get("frequency", 5),
            phase=params.get("phase", 0),
            direction=params.get("direction", "both")
        )
    elif deform_type == "radial_wave":
        r.grid.add_radial_wave(
            amplitude=params.get("amplitude", 0.02),
            frequency=params.get("frequency", 5),
            center=params.get("center")
        )
    elif deform_type == "turbulence":
        r.grid.add_turbulence(
            octaves=params.get("octaves", 4),
            persistence=params.get("persistence", 0.5),
            scale=params.get("scale", 1.0),
            intensity=params.get("intensity", 0.05)
        )
    elif deform_type == "kaleidoscope":
        r.grid.add_kaleidoscope(
            segments=params.get("segments", 6),
            center=params.get("center")
        )
    elif deform_type == "ripple":
        r.grid.add_ripple(
            amplitude=params.get("amplitude", 0.02),
            frequency=params.get("frequency", 10),
            center=params.get("center"),
            decay=params.get("decay", 0.5)
        )
    elif deform_type == "bulge":
        r.grid.add_bulge(
            amplitude=params.get("amplitude", 0.1),
            radius=params.get("radius", 0.3),
            center=params.get("center")
        )
    elif deform_type == "zoom":
        r.grid.add_zoom(
            factor=params.get("factor", 0.2),
            center=params.get("center")
        )
    elif deform_type == "shear":
        r.grid.add_shear(
            x_factor=params.get("x_factor", 0.1),
            y_factor=params.get("y_factor", 0.0)
        )
    elif deform_type == "rotation":
        r.grid.add_rotation(
            angle=params.get("angle", 0.1),
            center=params.get("center")
        )
    elif deform_type == "glitch_lines":
        r.grid.add_glitch_lines(
            density=params.get("density", 0.1),
            max_shift=params.get("max_shift", 0.05)
        )
    else:
        raise HTTPException(400, f"Unknown deformation type: {deform_type}")
    
    return {"message": f"Grid deformation '{deform_type}' applied"}


# ─────────────────────────────────────────────────────────────────
# Archive Endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/api/archive/stats")
async def get_archive_stats():
    """Get archive statistics."""
    return get_archive().get_stats()


@app.get("/api/archive/recent")
async def get_recent_entries(limit: int = Query(default=10, ge=1, le=50)):
    """Get recent archive entries."""
    return {"entries": get_archive().get_recent(limit)}


@app.get("/api/archive/popular")
async def get_popular_entries(limit: int = Query(default=10, ge=1, le=50)):
    """Get popular archive entries."""
    return {"entries": get_archive().get_popular(limit)}


@app.get("/api/archive/{entry_id}")
async def get_archive_entry(entry_id: int):
    """Get a specific archive entry."""
    entry = get_archive().get_entry(entry_id)
    if not entry:
        raise HTTPException(404, f"Entry {entry_id} not found")
    return entry


@app.post("/api/archive/search")
async def search_archive(req: ArchiveSearchRequest):
    """Search the archive."""
    results = get_archive().search(
        query=req.query,
        seed=req.seed,
        start_date=req.start_date,
        end_date=req.end_date,
        tags=req.tags,
        limit=req.limit,
        offset=req.offset
    )
    return {"results": results, "count": len(results)}


@app.post("/api/archive/save")
async def save_to_archive(req: ArchiveSaveRequest):
    """Save current state to archive."""
    r = get_renderer()
    entry_id = r.save_to_archive(req.name, req.metadata)
    
    if req.tags:
        # Update tags (simple approach)
        with archive._get_conn() as conn:
            conn.execute(
                "UPDATE canopy_states SET tags = ? WHERE id = ?",
                (",".join(req.tags), entry_id)
            )
            conn.commit()
    
    return {
        "message": "State saved to archive",
        "entry_id": entry_id
    }


@app.post("/api/archive/load/{entry_id}")
async def load_from_archive(entry_id: int):
    """Load state from archive and apply to renderer."""
    r = get_renderer()
    r.load_from_archive(entry_id)
    
    return {
        "message": "State loaded from archive",
        "entry_id": entry_id,
        "seed": r.rng.seed
    }


@app.post("/api/archive/like/{entry_id}")
async def like_entry(entry_id: int):
    """Like an archive entry."""
    likes = get_archive().like(entry_id)
    return {"entry_id": entry_id, "likes": likes}


@app.delete("/api/archive/{entry_id}")
async def delete_archive_entry(entry_id: int):
    """Delete an archive entry."""
    if get_archive().delete(entry_id):
        return {"message": f"Entry {entry_id} deleted"}
    raise HTTPException(404, f"Entry {entry_id} not found")


@app.get("/api/archive/timeline")
async def get_archive_timeline(days: int = Query(default=7, ge=1, le=90)):
    """Get archive timeline."""
    return {"timeline": get_archive().timeline(days)}


# ─────────────────────────────────────────────────────────────────
# Configuration Endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/api/config/export")
async def export_config():
    """Export current renderer configuration."""
    return {"config": get_renderer().export_config()}


@app.post("/api/config/import")
async def import_config(req: ConfigImportRequest):
    """Import a configuration."""
    r = get_renderer()
    r.import_config(req.config_json)
    return {"message": "Configuration imported", "seed": r.rng.seed}


@app.get("/api/config/current")
async def get_current_config():
    """Get current renderer state."""
    r = get_renderer()
    return r.get_current_state()


# ─────────────────────────────────────────────────────────────────
# Session API Endpoints
# ─────────────────────────────────────────────────────────────────

from canopy.session import (
    get_session_manager, Session, SessionEvent, SessionStatus, EventType
)
from canopy.hashing import (
    hash_manifest, hash_event_log, hash_pixels, hash_session_export
)


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    seed: int = Field(default=42, description="Random seed")
    width: int = Field(default=128, description="Frame width")
    height: int = Field(default=128, description="Frame height")
    preset_name: Optional[str] = Field(default=None, description="Initial preset")
    name: str = Field(default="", description="Session name")


class EventRequest(BaseModel):
    """Request to apply an event to a session."""
    event_type: str = Field(..., description="Event type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload")


class RewindRequest(BaseModel):
    """Request to rewind a session."""
    event_index: int = Field(..., description="Event index to rewind to")


class ForkRequest(BaseModel):
    """Request to fork a session."""
    event_index: int = Field(..., description="Event index to fork from")


class RenderFrameRequest(BaseModel):
    """Request to render a session frame."""
    width: int = Field(default=128, description="Frame width")
    height: int = Field(default=128, description="Frame height")


@app.post("/api/session", status_code=201)
async def create_session(req: CreateSessionRequest):
    """Create a new session from a manifest."""
    try:
        from canopy.manifest import ManifestBuilder
        
        # Build base manifest
        builder = ManifestBuilder(seed=req.seed, width=req.width, height=req.height)
        if req.preset_name:
            builder = builder.with_preset(req.preset_name)
        manifest = builder.build()
        
        # Create session
        session_manager = get_session_manager()
        session = session_manager.create_session(manifest)
        
        return {
            "session_id": session.session_id,
            "schema_version": session.schema_version,
            "engine_version": session.engine_version,
            "status": session.status.value,
            "base_manifest": session.base_manifest,
            "manifest_hash": hash_manifest(session.base_manifest),
            "created_at": session.created_at,
        }
    except Exception as e:
        raise HTTPException(422, f"Invalid manifest: {str(e)}")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session details."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    return {
        "session_id": session.session_id,
        "schema_version": session.schema_version,
        "engine_version": session.engine_version,
        "status": session.status.value,
        "base_manifest": session.base_manifest,
        "current_manifest": session.current_manifest,
        "manifest_hash": hash_manifest(session.current_manifest),
        "current_frame": session.current_frame,
        "event_count": len(session.events),
        "event_log_hash": hash_event_log(session.events),
        "latest_pixel_hash": session.latest_pixel_hash,
        "parent_session_id": session.parent_session_id,
        "fork_event_index": session.fork_event_index,
        "created_at": session.created_at,
    }


@app.post("/api/session/{session_id}/event")
async def apply_event(session_id: str, req: EventRequest):
    """Apply an event to a session."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(409, f"Session is {session.status.value}")
    
    # Validate event type before constructing or mutating anything.
    try:
        event_type = EventType(req.event_type)
    except ValueError:
        allowed = ", ".join(sorted(e.value for e in EventType))
        raise HTTPException(
            400,
            f"Unknown event type '{req.event_type}'. Allowed: {allowed}"
        )

    event = SessionEvent(
        event_index=len(session.events),
        event_type=event_type,
        payload=req.payload,
    )
    
    # Apply event
    success, error = session_manager.apply_event(session_id, event)
    
    if not success:
        raise HTTPException(409, error or "Failed to apply event")
    
    # Return updated session state
    return {
        "event_index": event.event_index,
        "event_type": event.event_type.value,
        "manifest_hash_before": event.manifest_hash_before,
        "manifest_hash_after": event.manifest_hash_after,
        "current_manifest": session.current_manifest,
        "manifest_hash": hash_manifest(session.current_manifest),
    }


@app.get("/api/session/{session_id}/frame/{frame_index}")
async def render_session_frame(session_id: str, frame_index: int, 
                                req: RenderFrameRequest = None):
    """Render a frame for a session."""
    if req is None:
        req = RenderFrameRequest()
    
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    try:
        frame, pixel_hash = session_manager.render_session_frame(
            session, frame_index, req.width, req.height
        )
        
        # Update latest pixel hash
        session.latest_pixel_hash = pixel_hash
        
        # Convert to base64
        img = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(img).save(buffer, format="PNG")
        img_b64 = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "session_id": session_id,
            "frame_index": frame_index,
            "manifest_hash": hash_manifest(session.current_manifest),
            "event_log_hash": hash_event_log(session.events),
            "pixel_hash": pixel_hash,
            "image_base64": img_b64,
        }
    except Exception as e:
        raise HTTPException(500, f"Rendering failed: {str(e)}")


@app.post("/api/session/{session_id}/rewind")
async def rewind_session(session_id: str, req: RewindRequest):
    """Rewind a session to a previous event index."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    if session.status != SessionStatus.ACTIVE:
        raise HTTPException(409, f"Session is {session.status.value}")
    
    success, error = session_manager.rewind_session(session_id, req.event_index)
    
    if not success:
        raise HTTPException(409, error or "Rewind failed")
    
    return {
        "session_id": session_id,
        "rewound_to_event": req.event_index,
        "current_manifest": session.current_manifest,
        "manifest_hash": hash_manifest(session.current_manifest),
        "current_frame": session.current_frame,
        "events_retained": len(session.events),
    }


@app.post("/api/session/{session_id}/fork")
async def fork_session(session_id: str, req: ForkRequest):
    """Fork a session from a given event index."""
    session_manager = get_session_manager()
    
    new_session, error = session_manager.fork_session(session_id, req.event_index)
    
    if not new_session:
        raise HTTPException(409, error or "Fork failed")
    
    return {
        "session_id": new_session.session_id,
        "parent_session_id": new_session.parent_session_id,
        "fork_event_index": new_session.fork_event_index,
        "base_manifest": new_session.base_manifest,
        "current_manifest": new_session.current_manifest,
        "manifest_hash": hash_manifest(new_session.current_manifest),
        "created_at": new_session.created_at,
    }


@app.get("/api/session/{session_id}/export")
async def export_session(session_id: str):
    """Export a session as a portable JSON payload."""
    session_manager = get_session_manager()
    export_data = session_manager.export_session(session_id)
    
    if not export_data:
        raise HTTPException(404, f"Session {session_id} not found")
    
    # Add canonical hash
    export_data["export_hash"] = hash_session_export(export_data)
    
    return export_data


@app.post("/api/session/import", status_code=201)
async def import_session(payload: Dict[str, Any]):
    """Import a session from a portable JSON payload."""
    session_manager = get_session_manager()
    session, error = session_manager.import_session(payload)
    
    if not session:
        raise HTTPException(422, error or "Import failed")
    
    return {
        "session_id": session.session_id,
        "manifest_hash": hash_manifest(session.current_manifest),
        "event_count": len(session.events),
        "created_at": session.created_at,
    }


@app.delete("/api/session/{session_id}")
async def close_session(session_id: str):
    """Close a session."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    success = session_manager.close_session(session_id)
    
    if success:
        return {"message": f"Session {session_id} closed", "status": "closed"}
    raise HTTPException(500, "Failed to close session")


@app.get("/api/session/{session_id}/verify")
async def verify_session(session_id: str):
    """Verify session integrity."""
    session_manager = get_session_manager()
    is_valid, errors = session_manager.verify_session_integrity(session_id)
    
    return {
        "session_id": session_id,
        "valid": is_valid,
        "errors": errors,
    }


# ─────────────────────────────────────────────────────────────────
# WebSocket for Session Updates
# ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/live/{session_id}")
async def session_websocket(websocket):
    """
    WebSocket for live session interaction.
    
    Client messages:
    - {"type": "event", "event": {"event_type": "...", "payload": {...}}}
    - {"type": "render", "frame_index": 12}
    - {"type": "rewind", "event_index": 4}
    
    Server messages:
    - {"type": "frame", "session_id": "...", "frame_index": 12, "pixel_hash": "...", "image_base64": "..."}
    - {"type": "event_applied", "event_index": N, "manifest_hash": "..."}
    - {"type": "error", "code": "...", "detail": "..."}
    """
    session_id = websocket.path_params.get("session_id")
    
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "event":
                # Apply event
                event_data = data.get("event", {})
                event = SessionEvent(
                    event_index=len(session.events),
                    event_type=EventType(event_data.get("event_type", "set_parameter")),
                    payload=event_data.get("payload", {}),
                )
                
                success, error = session_manager.apply_event(session_id, event)
                
                if success:
                    await websocket.send_json({
                        "type": "event_applied",
                        "event_index": event.event_index,
                        "manifest_hash_after": event.manifest_hash_after,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "code": "INVALID_EVENT",
                        "detail": error,
                    })
            
            elif msg_type == "render":
                # Render frame
                frame_index = data.get("frame_index", session.current_frame)
                width = data.get("width", 128)
                height = data.get("height", 128)
                
                try:
                    frame, pixel_hash = session_manager.render_session_frame(
                        session, frame_index, width, height
                    )
                    session.latest_pixel_hash = pixel_hash
                    
                    # Convert to base64
                    img = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
                    buffer = io.BytesIO()
                    Image.fromarray(img).save(buffer, format="PNG")
                    img_b64 = base64.b64encode(buffer.getvalue()).decode()
                    
                    await websocket.send_json({
                        "type": "frame",
                        "session_id": session_id,
                        "frame_index": frame_index,
                        "manifest_hash": hash_manifest(session.current_manifest),
                        "event_log_hash": hash_event_log(session.events),
                        "pixel_hash": pixel_hash,
                        "image_base64": img_b64,
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "code": "RENDER_ERROR",
                        "detail": str(e),
                    })
            
            elif msg_type == "rewind":
                # Rewind session
                event_index = data.get("event_index")
                
                if event_index is None:
                    await websocket.send_json({
                        "type": "error",
                        "code": "INVALID_REQUEST",
                        "detail": "event_index required",
                    })
                    continue
                
                success, error = session_manager.rewind_session(session_id, event_index)
                
                if success:
                    await websocket.send_json({
                        "type": "rewound",
                        "event_index": event_index,
                        "manifest_hash": hash_manifest(session.current_manifest),
                        "current_frame": session.current_frame,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "code": "REWIND_FAILED",
                        "detail": error,
                    })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "code": "UNKNOWN_MESSAGE",
                    "detail": f"Unknown message type: {msg_type}",
                })
    
    except Exception as e:
        # Log but don't terminate on malformed messages
        try:
            await websocket.send_json({
                "type": "error",
                "code": "PROTOCOL_ERROR",
                "detail": str(e),
            })
        except:
            pass


# ─────────────────────────────────────────────────────────────────
# Legacy WebSocket for Live Updates (Compatibility)
# ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_endpoint(websocket):
    """
    Legacy WebSocket for real-time parameter streaming.
    Allows external processes to drive the canopy dynamically.
    """
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            msg_type = data.get("type")
            
            if msg_type == "set_seed":
                seed = data.get("seed")
                get_renderer().set_seed(seed)
                await websocket.send_json({
                    "type": "seed_set",
                    "seed": seed
                })
            
            elif msg_type == "set_param":
                effect = data.get("effect")
                param = data.get("param")
                value = data.get("value")
                get_renderer().effects.set_param(effect, param, value)
                await websocket.send_json({
                    "type": "param_set",
                    "effect": effect,
                    "param": param,
                    "value": value
                })
            
            elif msg_type == "render":
                # Render frame and send back
                frame = get_renderer().render_frame()
                img = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
                buffer = io.BytesIO()
                Image.fromarray(img).save(buffer, format="PNG")
                img_b64 = base64.b64encode(buffer.getvalue()).decode()
                
                await websocket.send_json({
                    "type": "frame",
                    "image": f"data:image/png;base64,{img_b64}"
                })
            
            elif msg_type == "grid_deform":
                # Apply grid deformation
                req_data = GridDeformRequest(**data.get("params", {}))
                # Apply the deformation...
                await websocket.send_json({
                    "type": "grid_deformed",
                    "params": data.get("params", {})
                })
    
    except Exception as e:
        await websocket.close(code=1011, reason=str(e))


# ─────────────────────────────────────────────────────────────────
# Static Files - Control Room UI
# ─────────────────────────────────────────────────────────────────

from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Mount static files - check multiple possible locations
server_dir = Path(__file__).parent
possible_static_paths = [
    server_dir / "static",                    # For development: server.py/static/
    server_dir / "canopy" / "static",        # For release: server.py/canopy/static/
    server_dir.parent / "canopy" / "static", # Alternative layout
]

static_path = None
for p in possible_static_paths:
    if p.exists() and p.is_dir():
        static_path = p
        break

if static_path:
    app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")


@app.get("/control-room")
async def control_room():
    """Redirect to the control room UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/control-room.html")


@app.get("/sessions/archive/search")
async def search_archived_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0)
):
    """Search archived sessions."""
    from canopy.archive.database import SessionArchive
    
    archive = SessionArchive()
    results = archive.search_sessions(limit=limit, offset=offset)
    
    return {"results": results, "count": len(results)}


@app.post("/api/session/{session_id}/archive")
async def archive_session_to_db(session_id: str):
    """Archive a session to the database."""
    from canopy.archive.database import SessionArchive
    
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    archive = SessionArchive()
    entry_id = archive.save_session(session)
    
    return {"message": "Session archived", "entry_id": entry_id}


# ─────────────────────────────────────────────────────────────────
# v1.0.0 - SOVEREIGN CANOPY EDITION ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    """Get current metrics snapshot."""
    from canopy.metrics import snapshot
    return snapshot().to_dict()


@app.get("/api/health/detail")
async def health_detail():
    """Get detailed health information."""
    from canopy.metrics import get_health_detail
    return get_health_detail()


# Undo/Redo endpoints
@app.post("/api/session/{session_id}/undo")
async def undo_session(session_id: str, count: int = Query(default=1, ge=1, le=100)):
    """Move cursor backward (undo)."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    session = session_manager.undo_session(session_id, count)
    
    return {
        "session_id": session.session_id,
        "event_cursor": session.event_cursor,
        "events_count": len(session.events),
    }


@app.post("/api/session/{session_id}/redo")
async def redo_session(session_id: str, count: int = Query(default=1, ge=1, le=100)):
    """Move cursor forward (redo)."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    session = session_manager.redo_session(session_id, count)
    
    return {
        "session_id": session.session_id,
        "event_cursor": session.event_cursor,
        "events_count": len(session.events),
    }


@app.post("/api/session/{session_id}/jump")
async def jump_to_event(session_id: str, event_index: int = Query(...)):
    """Jump to a specific event index."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    session = session_manager.jump_to_event(session_id, event_index)
    
    return {
        "session_id": session.session_id,
        "event_cursor": session.event_cursor,
    }


@app.get("/api/session/{session_id}/branches")
async def list_branches(session_id: str):
    """List all branches derived from a session."""
    session_manager = get_session_manager()
    branches = session_manager.list_branches(session_id)
    
    return {"branches": branches, "count": len(branches)}


@app.post("/api/session/{session_id}/branch")
async def create_branch(session_id: str, event_index: int = Query(...)):
    """Create a new branch (fork) from a session."""
    session_manager = get_session_manager()
    
    try:
        fork_session = session_manager.fork_session(session_id, event_index)
        return {
            "session_id": fork_session.session_id,
            "parent_session_id": fork_session.parent_session_id,
            "fork_event_index": fork_session.fork_event_index,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


# Timeline endpoints
@app.get("/api/session/{session_id}/timeline")
async def get_timeline(session_id: str):
    """Get the timeline for a session."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    timeline_data = session.timeline if hasattr(session, 'timeline') and session.timeline else None
    
    if not timeline_data:
        return {
            "duration_frames": 240,
            "fps": 30,
            "tracks": [],
        }
    
    return timeline_data.to_dict() if hasattr(timeline_data, 'to_dict') else timeline_data


@app.post("/api/session/{session_id}/timeline/track")
async def add_timeline_track(
    session_id: str,
    track_id: str = Query(...),
    target: str = Query(...),
    interpolation: str = Query(default="linear")
):
    """Add a new timeline track."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    from canopy.timeline import Track, Interpolation
    
    track = Track(
        track_id=track_id,
        target=target,
        interpolation=Interpolation(interpolation),
        keyframes=[],
    )
    
    # Add to session timeline (simplified - would need proper storage)
    return track.to_dict()


@app.post("/api/session/{session_id}/timeline/keyframe")
async def add_keyframe(
    session_id: str,
    track_id: str = Query(...),
    frame: int = Query(...),
    value: float = Query(...)
):
    """Add a keyframe to a track."""
    return {
        "track_id": track_id,
        "frame": frame,
        "value": value,
        "message": "Keyframe added (in-memory)"
    }


# Comparison endpoints
@app.post("/api/compare")
async def compare_sessions_endpoint(
    left_id: str = Query(...),
    right_id: str = Query(...),
    left_frame: int = Query(default=0),
    right_frame: int = Query(default=0)
):
    """Compare two sessions."""
    from canopy.comparison import compare_sessions
    
    session_manager = get_session_manager()
    left_session = session_manager.get_session(left_id)
    right_session = session_manager.get_session(right_id)
    
    if not left_session or not right_session:
        raise HTTPException(404, "One or both sessions not found")
    
    result = compare_sessions(
        left_session.to_dict() if hasattr(left_session, 'to_dict') else left_session,
        right_session.to_dict() if hasattr(right_session, 'to_dict') else right_session,
        left_frame,
        right_frame
    )
    
    return result.to_dict()


@app.post("/api/compare/range")
async def compare_range(
    left_id: str = Query(...),
    right_id: str = Query(...),
    start_frame: int = Query(default=0),
    end_frame: int = Query(default=30)
):
    """Compare two sessions over a frame range."""
    from canopy.comparison import compare_frame_ranges
    
    session_manager = get_session_manager()
    left_session = session_manager.get_session(left_id)
    right_session = session_manager.get_session(right_id)
    
    if not left_session or not right_session:
        raise HTTPException(404, "One or both sessions not found")
    
    result = compare_frame_ranges(
        left_session.to_dict() if hasattr(left_session, 'to_dict') else left_session,
        right_session.to_dict() if hasattr(right_session, 'to_dict') else right_session,
        start_frame,
        end_frame
    )
    
    return result.to_dict()


# Import/Export endpoints
@app.post("/api/import/validate")
async def validate_import(data: Dict[str, Any]):
    """Validate an import payload."""
    from canopy.security import validate_import_payload
    from canopy.errors import handle_exception
    
    try:
        result = validate_import_payload(data)
        return result.to_dict()
    except Exception as e:
        error = handle_exception(e)
        return JSONResponse(error.to_api_response(), status_code=400)


@app.post("/api/import/session")
async def import_session(data: Dict[str, Any]):
    """Import a session."""
    from canopy.security import validate_import_payload
    from canopy.errors import handle_exception
    
    try:
        # Validate first
        validation = validate_import_payload(data)
        if not validation.valid:
            return JSONResponse(
                {"error": {"code": "INVALID_REQUEST", "message": "Validation failed", "details": validation.errors}},
                status_code=400
            )
        
        # Import the validated portable payload. SessionManager accepts either
        # the export wrapper {"session": ...} or a raw session dictionary.
        session_manager = get_session_manager()
        session, import_error = session_manager.import_session(data)

        if session is None:
            return JSONResponse(
                {
                    "error": {
                        "code": "IMPORT_FAILED",
                        "message": import_error or "Session import failed",
                    }
                },
                status_code=400,
            )

        return {"session_id": session.session_id, "imported": True}
    except Exception as e:
        error = handle_exception(e)
        return JSONResponse(error.to_api_response(), status_code=400)


@app.get("/api/export/session/{session_id}")
async def export_session(session_id: str):
    """Export a session as JSON."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    return session_manager.export_session(session_id)


@app.get("/api/export/session/{session_id}/bundle")
async def export_bundle(session_id: str):
    """Export a session as a ZIP bundle."""
    from canopy.security import create_export_bundle
    
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    bundle = create_export_bundle(
        session.to_dict() if hasattr(session, 'to_dict') else session,
        session.current_manifest if hasattr(session, 'current_manifest') else {},
    )
    
    zip_data = bundle.to_zip()
    
    return StreamingResponse(
        io.BytesIO(zip_data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=session_{session_id}.zip"}
    )


@app.get("/api/export/session/{session_id}/frame/{frame}")
async def export_frame(session_id: str, frame: int):
    """Export a single frame as PNG."""
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    # Render frame and convert the canonical float image to PNG bytes.
    frame_data, _ = session_manager.render_session_frame(session, frame, 256, 256)
    image_data = (np.clip(frame_data, 0, 1) * 255).astype(np.uint8)

    buffer = io.BytesIO()
    Image.fromarray(image_data).save(buffer, format="PNG")
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename=frame_{frame}.png"}
    )


@app.get("/api/export/session/{session_id}/sequence")
async def export_frame_sequence(
    session_id: str,
    start_frame: int = Query(default=0, ge=0),
    end_frame: int = Query(default=30, ge=0, le=120),
    step: int = Query(default=1, ge=1, le=10)
):
    """
    Export a sequence of frames as a deterministic ZIP.
    
    The ZIP contains:
    - frames/0000.png, 0001.png, etc. (deterministic naming)
    - manifest.json (each frame's index and pixel hash)
    - metadata.json (export info)
    """
    session_manager = get_session_manager()
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(404, f"Session {session_id} not found")
    
    # Calculate frame count
    frame_indices = list(range(start_frame, end_frame + 1, step))
    max_frames = 120  # Limit for safety
    if len(frame_indices) > max_frames:
        raise HTTPException(400, f"Too many frames: {len(frame_indices)} (max: {max_frames})")
    
    # Create ZIP in memory
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        frame_manifest = []
        
        for i, frame_idx in enumerate(frame_indices):
            # Render frame. The manager returns (frame_array, pixel_hash).
            frame_data, pixel_hash = session_manager.render_session_frame(
                session, frame_idx, 256, 256
            )

            # Save PNG with deterministic name (zero-padded).
            image_data = (np.clip(frame_data, 0, 1) * 255).astype(np.uint8)
            png_buffer = io.BytesIO()
            Image.fromarray(image_data).save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()

            frame_name = f"frames/{i:04d}.png"
            zf.writestr(frame_name, png_bytes)

            # Record frame info.
            frame_manifest.append({
                "index": i,
                "original_frame": frame_idx,
                "pixel_hash": pixel_hash,
                "size_bytes": len(png_bytes)
            })
        
        # Write manifest
        manifest_data = {
            "session_id": session_id,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "step": step,
            "frame_count": len(frame_indices),
            "frames": frame_manifest,
            "deterministic": True
        }
        zf.writestr("manifest.json", json.dumps(manifest_data, indent=2, sort_keys=True))
        
        # Write metadata
        metadata = {
            "session_id": session_id,
            "engine_version": __version__,
            "schema_version": "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat() + "Z",
            "frame_count": len(frame_indices)
        }
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, sort_keys=True))
    
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=sequence_{session_id}_{start_frame}-{end_frame}.zip"
        }
    )


# Archive endpoints
@app.get("/api/archive/verify")
async def verify_archive():
    """Verify archive integrity."""
    from canopy.migrations import verify_database_integrity
    from canopy.archive.database import ArchiveDatabase
    
    try:
        db = ArchiveDatabase()
        integrity = db.verify_integrity()
        return integrity
    except Exception as e:
        return {"integrity_valid": False, "issues": [str(e)]}


@app.post("/api/migrate")
async def run_migration():
    """Run database migration."""
    from canopy.migrations import MigrationManager
    
    try:
        manager = MigrationManager("canopy_archive.db", "receipts")
        receipt = manager.migrate_database()
        
        if receipt.success:
            return {"success": True, "receipt": receipt.to_dict()}
        else:
            return JSONResponse(
                {"error": {"code": "MIGRATION_FAILED", "message": receipt.error}},
                status_code=500
            )
    except Exception as e:
        return JSONResponse(
            {"error": {"code": "MIGRATION_ERROR", "message": str(e)}},
            status_code=500
        )


# ─────────────────────────────────────────────────────────────────
# Run with: uvicorn server:app --reload --port 8000
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
