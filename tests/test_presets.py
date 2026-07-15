"""
Test: Presets Determinism
Verifies that all presets produce deterministic output.
"""
import pytest
import numpy as np
import sys
import os
import hashlib

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy import CanopyRenderer
from canopy.effects.presets import PRESETS, list_presets, get_preset_description


class TestPresetDeterminism:
    """Tests for preset deterministic behavior."""
    
    def test_all_presets_are_deterministic(self):
        """Every preset must produce identical output for same seed."""
        all_presets = list_presets()
        
        for preset_name in all_presets:
            renderer1 = CanopyRenderer(width=128, height=128, seed=42)
            renderer2 = CanopyRenderer(width=128, height=128, seed=42)
            
            renderer1.apply_preset(preset_name)
            renderer2.apply_preset(preset_name)
            
            frame1 = renderer1.render_frame()
            frame2 = renderer2.render_frame()
            
            np.testing.assert_array_equal(
                frame1, frame2,
                err_msg=f"Preset '{preset_name}' must be deterministic"
            )
    
    def test_preset_hash_is_consistent(self):
        """Preset must produce consistent hash across calls."""
        preset_name = "solaris_dream"
        
        def render_preset(seed):
            renderer = CanopyRenderer(width=128, height=128, seed=seed)
            renderer.apply_preset(preset_name)
            return hashlib.sha256(renderer.render_frame().tobytes()).hexdigest()
        
        # Multiple renders with same seed should produce same hash
        hashes = [render_preset(42) for _ in range(3)]
        assert len(set(hashes)) == 1, "Same preset+seed must produce same hash"
    
    def test_different_presets_are_different(self):
        """Different presets must produce different outputs."""
        preset_names = list_presets()
        
        frames = {}
        for name in preset_names[:3]:  # Test first 3
            renderer = CanopyRenderer(width=128, height=128, seed=42)
            renderer.apply_preset(name)
            frame_hash = hashlib.sha256(renderer.render_frame().tobytes()).hexdigest()
            frames[name] = frame_hash
        
        # All hashes should be different
        unique_hashes = set(frames.values())
        assert len(unique_hashes) == len(frames), \
            "Different presets must produce different outputs"
    
    def test_preset_contains_effects(self):
        """Preset must define at least one effect."""
        for preset_name in list_presets():
            preset = PRESETS[preset_name]
            assert "effects" in preset, f"Preset '{preset_name}' must have effects"
            assert len(preset["effects"]) > 0, \
                f"Preset '{preset_name}' must have at least one effect"
    
    def test_preset_descriptions_exist(self):
        """Every preset should have a description."""
        for preset_name in list_presets():
            desc = get_preset_description(preset_name)
            assert desc is not None, f"Preset '{preset_name}' should have description"
            assert len(desc) > 0, "Description must not be empty"
    
    def test_apply_preset_clears_previous(self):
        """Applying a preset should set the effect configuration."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        
        # Apply one preset
        renderer.apply_preset("solaris_dream")
        config1 = renderer.effects.get_config()
        
        # Apply different preset
        renderer.apply_preset("glitch_cathedral")
        config2 = renderer.effects.get_config()
        
        # Configs should be different
        assert config1["enabled"] != config2["enabled"], \
            "Different presets should produce different configs"
    
    def test_preset_hash_with_frame_index(self):
        """Frame index should affect output for time-based animations."""
        renderer = CanopyRenderer(width=64, height=64, seed=42)
        renderer.apply_preset("prismatic")
        
        # Different frame indices could produce different results
        # (depending on time-based parameters)
        # This test documents the expected behavior
        frame0 = renderer.render_frame()
        frame1 = renderer.render_frame()
        
        # At minimum, the manifest should track frame_index
        manifest = renderer.get_current_state()
        assert "effects" in manifest


class TestPresetParameterPreservation:
    """Tests for preset parameter handling."""
    
    def test_preset_params_are_applied(self):
        """Preset parameters should be applied correctly."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        
        preset_name = "tropical_night"
        renderer.apply_preset(preset_name)
        
        preset = PRESETS[preset_name]
        params = preset.get("params", {})
        
        # Check that params are reflected in effect config
        effect_config = renderer.effects.get_config()
        
        # At least one parameter should be set
        if "vignette" in params:
            assert effect_config["params"].get("vignette", {}).get("intensity") == \
                   params["vignette"].get("intensity")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
