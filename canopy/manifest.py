"""
The Generation Manifest 📜✨
A canonical recipe that captures ALL inputs required for deterministic regeneration.

This is not just a seed - it's the complete specification that,
when replayed, produces byte-identical output.
"""
import json
import hashlib
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .version import __version__, __schema_version__, RNG_ALGORITHM, SUPPORTED_FORMATS


@dataclass
class GridOperation:
    """A single grid deformation operation."""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {"type": self.type, "params": self.params}
    
    @classmethod
    def from_dict(cls, data: dict) -> "GridOperation":
        return cls(type=data["type"], params=data.get("params", {}))
    
    def __hash__(self) -> int:
        return hash((self.type, json.dumps(self.params, sort_keys=True)))


@dataclass
class EffectConfig:
    """An effect and its parameters."""
    name: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "params": self.params
        }
    
    @classmethod
    def from_dict(cls, data) -> "EffectConfig":
        if isinstance(data, str):
            return cls(name=data)
        return cls(
            name=data["name"],
            enabled=data.get("enabled", True),
            params=data.get("params", {})
        )


@dataclass
class Manifest:
    """
    The canonical generation manifest.
    
    This captures EVERYTHING needed to reproduce a visual exactly.
    Same manifest = same output. Always.
    """
    # Schema and version tracking
    schema_version: str = __schema_version__
    engine_version: str = __version__
    rng_algorithm: str = RNG_ALGORITHM
    
    # Core generation parameters
    seed: int = 0
    width: int = 1280
    height: int = 720
    frame_index: int = 0
    
    # Generation mode
    noise_type: str = "fbm"
    noise_params: Dict[str, Any] = field(default_factory=dict)
    
    # Grid operations (ordered list!)
    grid_operations: List[GridOperation] = field(default_factory=list)
    
    # Effect pipeline (ordered list!)
    effects: List[EffectConfig] = field(default_factory=list)
    
    # Preset reference (if any)
    preset_name: Optional[str] = None
    preset_version: int = 1
    
    # Output specification
    output_format: str = "png"
    
    # Metadata
    name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Ensure created_at is always a string
        if isinstance(self.created_at, datetime):
            self.created_at = self.created_at.isoformat()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "rng_algorithm": self.rng_algorithm,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "frame_index": self.frame_index,
            "noise_type": self.noise_type,
            "noise_params": self.noise_params,
            "grid_operations": [op.to_dict() for op in self.grid_operations],
            "effects": [eff.to_dict() for eff in self.effects],
            "preset_name": self.preset_name,
            "preset_version": self.preset_version,
            "output_format": self.output_format,
            "name": self.name,
            "created_at": self.created_at,
            "tags": self.tags,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        """Reconstruct from dictionary."""
        # Parse grid operations
        grid_ops = [GridOperation.from_dict(op) for op in data.get("grid_operations", [])]
        
        # Parse effect configs
        effect_configs = [EffectConfig.from_dict(eff) for eff in data.get("effects", [])]
        
        return cls(
            schema_version=data.get("schema_version", __schema_version__),
            engine_version=data.get("engine_version", __version__),
            rng_algorithm=data.get("rng_algorithm", RNG_ALGORITHM),
            seed=data.get("seed", 0),
            width=data.get("width", 1280),
            height=data.get("height", 720),
            frame_index=data.get("frame_index", 0),
            noise_type=data.get("noise_type", "fbm"),
            noise_params=data.get("noise_params", {}),
            grid_operations=grid_ops,
            effects=effect_configs,
            preset_name=data.get("preset_name"),
            preset_version=data.get("preset_version", 1),
            output_format=data.get("output_format", "png"),
            name=data.get("name", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            tags=data.get("tags", []),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "Manifest":
        """Reconstruct from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def fingerprint(self) -> str:
        """
        Generate a unique fingerprint for this manifest.
        
        This fingerprint captures the essential generation parameters
        in a deterministic order, allowing comparison of "same generation".
        """
        fp_data = {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "rng_algorithm": self.rng_algorithm,
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "noise_type": self.noise_type,
            "noise_params": self.noise_params,
            "grid_operations": [op.to_dict() for op in self.grid_operations],
            "effects": [eff.to_dict() for eff in self.effects],
        }
        return hashlib.sha256(
            json.dumps(fp_data, sort_keys=True).encode()
        ).hexdigest()[:16]
    
    def with_grid_op(self, op_type: str, **params) -> "Manifest":
        """Add a grid operation (builder pattern)."""
        new_ops = self.grid_operations + [GridOperation(type=op_type, params=params)]
        return Manifest(
            **{**asdict(self), "grid_operations": new_ops}
        )
    
    def with_effect(self, name: str, **params) -> "Manifest":
        """Add an effect (builder pattern)."""
        new_effects = self.effects + [EffectConfig(name=name, params=params)]
        return Manifest(
            **{**asdict(self), "effects": new_effects}
        )
    
    def validate(self) -> List[str]:
        """
        Validate the manifest.
        
        Returns list of validation errors (empty if valid).
        """
        errors = []
        
        # Version checks
        if self.schema_version != __schema_version__:
            errors.append(f"Schema version mismatch: {self.schema_version} != {__schema_version__}")
        
        # Dimension checks
        if self.width <= 0 or self.width > 8192:
            errors.append(f"Invalid width: {self.width}")
        if self.height <= 0 or self.height > 8192:
            errors.append(f"Invalid height: {self.height}")
        
        # Seed check
        if self.seed < 0:
            errors.append(f"Invalid seed: {self.seed}")
        
        # Format check
        if self.output_format not in SUPPORTED_FORMATS:
            errors.append(f"Unsupported format: {self.output_format}")
        
        # RNG algorithm check
        if self.rng_algorithm != RNG_ALGORITHM:
            errors.append(f"Unsupported RNG algorithm: {self.rng_algorithm}")
        
        return errors
    
    def __eq__(self, other: "Manifest") -> bool:
        """Two manifests are equal if they have the same fingerprint."""
        return self.fingerprint() == other.fingerprint()
    
    def __repr__(self) -> str:
        return f"Manifest(seed={self.seed}, {self.width}x{self.height}, effects={len(self.effects)})"


class ManifestBuilder:
    """
    Builder for constructing manifests programmatically.
    """
    
    def __init__(self, seed: int, width: int = 1280, height: int = 720):
        self._manifest = Manifest(seed=seed, width=width, height=height)
    
    def with_preset(self, preset_name: str, preset_version: int = 1) -> "ManifestBuilder":
        """Apply a preset."""
        self._manifest.preset_name = preset_name
        self._manifest.preset_version = preset_version
        return self
    
    def with_grid_op(self, op_type: str, **params) -> "ManifestBuilder":
        """Add a grid operation."""
        self._manifest.grid_operations.append(
            GridOperation(type=op_type, params=params)
        )
        return self
    
    def with_effect(self, name: str, enabled: bool = True, **params) -> "ManifestBuilder":
        """Add an effect."""
        self._manifest.effects.append(
            EffectConfig(name=name, enabled=enabled, params=params)
        )
        return self
    
    def with_noise(self, noise_type: str, **params) -> "ManifestBuilder":
        """Set noise generation parameters."""
        self._manifest.noise_type = noise_type
        self._manifest.noise_params = params
        return self
    
    def with_output(self, format: str) -> "ManifestBuilder":
        """Set output format."""
        self._manifest.output_format = format
        return self
    
    def with_metadata(self, name: str = "", tags: List[str] = None) -> "ManifestBuilder":
        """Set metadata."""
        self._manifest.name = name
        self._manifest.tags = tags or []
        return self
    
    def with_frame_index(self, index: int) -> "ManifestBuilder":
        """Set frame index for animation."""
        self._manifest.frame_index = index
        return self
    
    def build(self) -> Manifest:
        """Build the final manifest."""
        errors = self._manifest.validate()
        if errors:
            raise ValueError(f"Invalid manifest: {errors}")
        return self._manifest
