"""
The Sacred Renderer 🖼️
Main rendering engine that orchestrates deterministic visual generation.
"""
import numpy as np
from typing import Optional, Tuple, List, Dict, Any, Callable
from datetime import datetime, timezone
from pathlib import Path

from .seeded_random import SeededRandom
from .grid import GridManipulator
from ..effects.effects import EffectPipeline
from ..archive.database import Archive
from ..manifest import Manifest, ManifestBuilder


class CanopyRenderer:
    """
    The main deterministic rendering engine.
    
    Takes a seed and produces consistent, reproducible visuals.
    The same seed + same parameters = the same output.
    """
    
    def __init__(self, width: int = 1920, height: int = 1080, 
                 seed: Optional[int] = None):
        """
        Initialize the canopy renderer.
        
        Args:
            width: Output width
            height: Output height
            seed: Initial random seed (None for random)
        """
        self.width = width
        self.height = height
        
        # The deterministic RNG - root of the great tree
        self.rng = SeededRandom(seed)
        
        # The grid manipulator
        self.grid = GridManipulator(width, height, self.rng)
        
        # Effect pipeline
        self.effects = EffectPipeline(self.rng)
        
        # Archive for persistence
        self.archive: Optional[Archive] = None
    
    def bind_archive(self, archive: Archive) -> "CanopyRenderer":
        """Bind an archive for saving/loading configurations."""
        self.archive = archive
        return self
    
    def reset(self, seed: Optional[int] = None) -> "CanopyRenderer":
        """
        Reset the renderer to initial state.
        
        Args:
            seed: New seed (None keeps current seed)
        """
        if seed is not None:
            self.rng = SeededRandom(seed)
            self.grid.bind_rng(self.rng)
            self.effects.bind_rng(self.rng)
        else:
            self.rng.reset()
        self.grid.reset()
        self.effects.reset()
        return self
    
    def set_seed(self, seed: int) -> "CanopyRenderer":
        """Set a new deterministic seed."""
        self.rng = SeededRandom(seed)
        self.grid.bind_rng(self.rng)
        self.effects.bind_rng(self.rng)
        return self
    
    def get_current_state(self) -> dict:
        """Get current renderer state for serialization."""
        return {
            "seed": self.rng.seed,
            "rng_state": self.rng.get_state_dict(),
            "grid": self.grid.to_dict(),
            "effects": self.effects.get_config(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def save_to_archive(self, name: str, metadata: Optional[Dict] = None,
                        manifest: Optional[Manifest] = None) -> int:
        """
        Save current configuration to archive.
        
        Args:
            name: Name for this snapshot
            metadata: Additional metadata
            manifest: Optional Manifest object for canonical storage
            
        Returns:
            Archive entry ID
        """
        if not self.archive:
            raise RuntimeError("No archive bound. Call bind_archive() first.")
        
        state = self.get_current_state()
        state["name"] = name
        state["metadata"] = metadata or {}
        
        # Auto-generate manifest if not provided
        if manifest is None:
            manifest = self.to_manifest(name=name)
        
        return self.archive.save_state(name, state, manifest=manifest)
    
    def to_manifest(self, name: str = "") -> Manifest:
        """
        Convert current renderer state to a Manifest.
        
        Args:
            name: Optional name for the manifest
            
        Returns:
            Manifest object
        """
        from ..manifest import GridOperation, EffectConfig
        
        # Build grid operations
        grid_ops = []
        # Note: We'd need to track applied operations for full fidelity
        # For now, we capture the current state
        
        # Build effect configs
        effect_configs = []
        config = self.effects.get_config()
        for effect_name in config["enabled"]:
            params = config["params"].get(effect_name, {})
            effect_configs.append(EffectConfig(
                name=effect_name,
                enabled=True,
                params=params
            ))
        
        return Manifest(
            seed=self.rng.seed,
            width=self.width,
            height=self.height,
            grid_operations=grid_ops,
            effects=effect_configs,
            name=name,
            created_at=datetime.now(timezone.utc).isoformat()
        )
    
    def from_manifest(self, manifest: Manifest) -> "CanopyRenderer":
        """
        Apply a manifest to the renderer.
        
        Args:
            manifest: Manifest to apply
            
        Returns:
            Self for chaining
        """
        self.set_seed(manifest.seed)
        self.width = manifest.width
        self.height = manifest.height
        self.grid = GridManipulator(manifest.width, manifest.height, self.rng)
        
        # Apply effects
        self.effects.reset()
        for effect in manifest.effects:
            if effect.enabled:
                self.effects.enable(effect.name)
                for param, value in effect.params.items():
                    self.effects.set_param(effect.name, param, value)
        
        # Apply grid operations
        for op in manifest.grid_operations:
            method_name = f"add_{op.type}"
            if hasattr(self.grid, method_name):
                getattr(self.grid, method_name)(**op.params)
        
        return self
    
    def load_from_archive(self, entry_id: int) -> "CanopyRenderer":
        """
        Load configuration from archive.
        
        Args:
            entry_id: Archive entry ID
            
        Returns:
            Self for chaining
        """
        if not self.archive:
            raise RuntimeError("No archive bound. Call bind_archive() first.")
        
        state = self.archive.load_state(entry_id)
        if not state:
            raise ValueError(f"Archive entry {entry_id} not found")
        
        # Restore full RNG state (including any consumed random numbers)
        if "rng_state" in state:
            self.rng = SeededRandom.from_state_dict(state["rng_state"])
        else:
            # Fallback: just set seed
            self.set_seed(state["seed"])
        
        # Restore grid (displacement was generated using this RNG state)
        self.grid = GridManipulator.from_dict(state["grid"], self.rng)
        
        # Restore effects configuration
        self.effects.set_config(state["effects"])
        
        return self
    
    def search_archive(self, query: Optional[str] = None,
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None,
                       limit: int = 10) -> List[dict]:
        """
        Search the archive for matching entries.
        
        Args:
            query: Text search query
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum results
            
        Returns:
            List of matching entries
        """
        if not self.archive:
            raise RuntimeError("No archive bound. Call bind_archive() first.")
        
        return self.archive.search(query, start_date, end_date, limit)
    
    def generate_base_noise(self, noise_type: str = "fbm",
                             **kwargs) -> np.ndarray:
        """
        Generate base noise texture.
        
        Args:
            noise_type: Type of noise ('random', 'fbm', 'perlin', 'cells')
            **kwargs: Additional parameters for noise generation
            
        Returns:
            Generated noise array
        """
        if noise_type == "random":
            return self.rng.rand(self.height, self.width, **kwargs)
        
        elif noise_type == "fbm":
            return self.rng.fbm((self.height, self.width), **kwargs)
        
        elif noise_type == "perlin":
            return (self.rng.perlin_noise((self.height, self.width), **kwargs) + 1) / 2
        
        elif noise_type == "cells":
            # Voronoi-like cellular noise
            from scipy.spatial import Voronoi
            points = self.rng.rand(100, 2) * np.array([self.width, self.height])
            # Simplified cellular noise using nearest neighbor distances
            yy, xx = np.mgrid[0:self.height, 0:self.width]
            pixels = np.column_stack([xx.ravel(), yy.ravel()])
            dists = np.linalg.norm(pixels[:, np.newaxis] - points, axis=2)
            min_dists = np.min(dists, axis=1).reshape(self.height, self.width)
            return min_dists / (np.max(min_dists) + 1e-6)
        
        else:
            raise ValueError(f"Unknown noise type: {noise_type}")
    
    def render_frame(self, source: Optional[np.ndarray] = None,
                     effect_chain: Optional[List[str]] = None) -> np.ndarray:
        """
        Render a single frame.
        
        Args:
            source: Source image (None for procedural generation)
            effect_chain: List of effect names to apply (overrides enabled effects)
            
        Returns:
            Rendered frame
        """
        # Generate or use provided source
        if source is None:
            frame = self.generate_base_noise("fbm", octaves=4)
            if len(frame.shape) == 2:
                frame = np.stack([frame] * 3, axis=-1)
        else:
            frame = source.astype(np.float32) / 255.0 if source.max() > 1 else source.astype(np.float32)
        
        # Apply grid deformation
        frame = self.grid.apply_displacement((frame * 255).astype(np.uint8))
        frame = frame.astype(np.float32) / 255.0
        
        # Apply effect chain or all enabled effects
        if effect_chain:
            for effect_name in effect_chain:
                frame = self.effects.apply(effect_name, frame)
        elif self.effects._enabled_effects:
            frame = self.effects.apply_all(frame)
        
        return np.clip(frame, 0, 1)
    
    def render_animation(self, frames: int, fps: int = 30,
                          effect_chain: Optional[List[str]] = None,
                          time_varying: bool = True,
                          callback: Optional[Callable[[int, np.ndarray], None]] = None
                          ) -> List[np.ndarray]:
        """
        Render multiple frames as an animation.
        
        Args:
            frames: Number of frames
            fps: Frames per second
            effect_chain: List of effects to apply
            time_varying: Whether effects change over time
            callback: Optional progress callback
            
        Returns:
            List of rendered frames
        """
        rendered = []
        
        for i in range(frames):
            # Save RNG state for reproducible frame
            self.rng.save_state()
            
            # Apply time-based variations
            if time_varying:
                time = i / fps
                # Time-varying grid parameters could go here
                self.grid.add_wave(
                    amplitude=0.02 * np.sin(time),
                    frequency=5,
                    direction="x"
                )
            
            # Render frame
            frame = self.render_frame(effect_chain=effect_chain)
            rendered.append(frame)
            
            # Restore RNG state
            self.rng.restore_state()
            
            # Progress callback
            if callback:
                callback(i, frame)
        
        return rendered
    
    def apply_preset(self, preset_name: str) -> "CanopyRenderer":
        """Apply a named preset configuration."""
        self.effects.apply_preset(preset_name)
        return self
    
    def export_config(self) -> str:
        """Export current configuration as JSON string."""
        import json
        state = self.get_current_state()
        return json.dumps(state, indent=2)
    
    def import_config(self, config_json: str) -> "CanopyRenderer":
        """Import configuration from JSON string."""
        import json
        state = json.loads(config_json)
        
        # Restore full RNG state
        if "rng_state" in state:
            self.rng = SeededRandom.from_state_dict(state["rng_state"])
        else:
            self.set_seed(state["seed"])
        
        self.grid = GridManipulator.from_dict(state["grid"], self.rng)
        self.effects.set_config(state["effects"])
        
        return self
    
    def to_image(self, frame: np.ndarray, 
                  filepath: Optional[str] = None) -> Optional[np.ndarray]:
        """
        Convert frame to image format.
        
        Args:
            frame: Normalized frame [0, 1]
            filepath: Optional save path
            
        Returns:
            uint8 image array if no filepath, else None
        """
        img = (np.clip(frame, 0, 1) * 255).astype(np.uint8)
        
        if filepath:
            from PIL import Image
            Image.fromarray(img).save(filepath)
            return None
        
        return img
    
    def save_animation(self, frames: List[np.ndarray], 
                        filepath: str, format: str = "mp4") -> None:
        """
        Save animation to file.
        
        Args:
            frames: List of normalized frames
            filepath: Output file path
            format: Output format ('mp4', 'gif', etc.)
        """
        import imageio
        from PIL import Image
        
        # Normalize frames
        normalized = [(np.clip(f, 0, 1) * 255).astype(np.uint8) for f in frames]
        
        if format == "gif":
            images = [Image.fromarray(f) for f in normalized]
            images[0].save(filepath, save_all=True, append_images=images[1:],
                          duration=int(1000/30), loop=0)
        else:
            imageio.mimsave(filepath, normalized, fps=30)
