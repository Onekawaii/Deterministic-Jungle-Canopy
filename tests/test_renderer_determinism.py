"""
Test: Renderer Determinism
Verifies that the CanopyRenderer produces identical output for the same manifest.
"""
import pytest
import numpy as np
import sys
import os
import hashlib
import tempfile
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy import CanopyRenderer
from canopy.manifest import Manifest, ManifestBuilder
from canopy.core.seeded_random import SeededRandom


class TestRendererDeterminism:
    """Tests for renderer deterministic behavior."""
    
    @pytest.fixture
    def base_renderer(self):
        """Create a base renderer for testing."""
        return CanopyRenderer(width=256, height=256, seed=42)
    
    def test_same_seed_same_frame(self, base_renderer):
        """Same seed must produce identical frames."""
        renderer1 = CanopyRenderer(width=256, height=256, seed=42)
        renderer2 = CanopyRenderer(width=256, height=256, seed=42)
        
        frame1 = renderer1.render_frame()
        frame2 = renderer2.render_frame()
        
        np.testing.assert_array_equal(frame1, frame2,
            err_msg="Same seed must produce identical frame")
    
    def test_frame_hash_is_deterministic(self):
        """Frame pixel hash must be deterministic."""
        def render_and_hash(seed):
            renderer = CanopyRenderer(width=128, height=128, seed=seed)
            frame = renderer.render_frame()
            return hashlib.sha256(frame.tobytes()).hexdigest()
        
        hash1 = render_and_hash(42)
        hash2 = render_and_hash(42)
        hash3 = render_and_hash(42)
        
        assert hash1 == hash2 == hash3, \
            "Same seed must produce same pixel hash"
    
    def test_different_seeds_different_frames(self):
        """Different seeds must produce different frames."""
        renderer1 = CanopyRenderer(width=128, height=128, seed=1)
        renderer2 = CanopyRenderer(width=128, height=128, seed=2)
        
        frame1 = renderer1.render_frame()
        frame2 = renderer2.render_frame()
        
        # Calculate how many pixels differ
        diff_count = np.sum(frame1 != frame2)
        diff_ratio = diff_count / frame1.size
        
        assert diff_ratio > 0.1, \
            f"Different seeds should produce significantly different frames " \
            f"(only {diff_ratio:.1%} differ)"
    
    def test_same_manifest_produces_same_frame(self):
        """Same manifest must produce identical frame."""
        manifest = ManifestBuilder(seed=12345, width=128, height=128) \
            .with_effect("vignette", intensity=0.5) \
            .with_effect("bloom", threshold=0.7) \
            .build()
        
        renderer1 = CanopyRenderer(width=manifest.width, height=manifest.height, seed=manifest.seed)
        renderer2 = CanopyRenderer(width=manifest.width, height=manifest.height, seed=manifest.seed)
        
        # Apply effects from manifest
        for effect in manifest.effects:
            if effect.enabled:
                renderer1.effects.enable(effect.name)
                renderer2.effects.enable(effect.name)
                for param, value in effect.params.items():
                    renderer1.effects.set_param(effect.name, param, value)
                    renderer2.effects.set_param(effect.name, param, value)
        
        frame1 = renderer1.render_frame()
        frame2 = renderer2.render_frame()
        
        np.testing.assert_array_equal(frame1, frame2,
            err_msg="Same manifest must produce identical frame")
    
    def test_reset_restores_initial_state(self):
        """Reset must restore the renderer to its initial configuration."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        
        # Render and get hash
        frame1 = renderer.render_frame()
        hash1 = hashlib.sha256(frame1.tobytes()).hexdigest()
        
        # Apply some modifications
        renderer.effects.enable("vignette")
        renderer.grid.add_turbulence()
        
        # Reset
        renderer.reset()
        
        # Render again
        frame2 = renderer.render_frame()
        hash2 = hashlib.sha256(frame2.tobytes()).hexdigest()
        
        assert hash1 == hash2, "Reset must restore exact initial state"
    
    def test_set_seed_changes_output(self):
        """Setting a new seed must change the output."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        frame1 = renderer.render_frame()
        hash1 = hashlib.sha256(frame1.tobytes()).hexdigest()
        
        renderer.set_seed(99)
        frame2 = renderer.render_frame()
        hash2 = hashlib.sha256(frame2.tobytes()).hexdigest()
        
        assert hash1 != hash2, "New seed must change output"
    
    def test_same_seed_after_set_produces_same(self):
        """Setting the same seed must produce the same output."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        
        renderer.set_seed(99)
        frame1 = renderer.render_frame()
        
        renderer.set_seed(99)
        frame2 = renderer.render_frame()
        
        np.testing.assert_array_equal(frame1, frame2,
            err_msg="Same seed must produce same frame")
    
    def test_effect_order_matters(self):
        """Effect application order must be preserved and deterministic."""
        # Create two renderers with effects in same order
        renderer1 = CanopyRenderer(width=64, height=64, seed=42)
        renderer2 = CanopyRenderer(width=64, height=64, seed=42)
        
        # Apply effects in specific order
        effects_order = ["vignette", "bloom", "noise"]
        
        for effect in effects_order:
            renderer1.effects.enable(effect)
            renderer2.effects.enable(effect)
        
        frame1 = renderer1.render_frame(effect_chain=effects_order)
        frame2 = renderer2.render_frame(effect_chain=effects_order)
        
        np.testing.assert_array_equal(frame1, frame2,
            err_msg="Same effect order must produce identical frames")
    
    def test_grid_deformation_is_deterministic(self):
        """Grid deformations must be deterministic."""
        renderer1 = CanopyRenderer(width=128, height=128, seed=42)
        renderer2 = CanopyRenderer(width=128, height=128, seed=42)
        
        # Apply same grid deformation
        renderer1.grid.add_turbulence(octaves=3)
        renderer2.grid.add_turbulence(octaves=3)
        
        frame1 = renderer1.render_frame()
        frame2 = renderer2.render_frame()
        
        np.testing.assert_array_equal(frame1, frame2,
            err_msg="Grid deformation must be deterministic")


class TestRendererImageOutput:
    """Tests for image output determinism."""
    
    def test_to_image_produces_deterministic_output(self):
        """to_image must produce deterministic pixel values."""
        renderer = CanopyRenderer(width=64, height=64, seed=42)
        frame = renderer.render_frame()
        
        # Convert to image twice
        img1 = renderer.to_image(frame)
        img2 = renderer.to_image(frame)
        
        np.testing.assert_array_equal(img1, img2,
            err_msg="to_image must be deterministic")
    
    def test_saved_file_is_identical(self):
        """Saved PNG files must be byte-identical for same seed."""
        renderer1 = CanopyRenderer(width=64, height=64, seed=42)
        renderer2 = CanopyRenderer(width=64, height=64, seed=42)
        
        frame1 = renderer1.render_frame()
        frame2 = renderer2.render_frame()
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f1:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f2:
                path1 = f1.name
                path2 = f2.name
        
        try:
            renderer1.to_image(frame1, path1)
            renderer2.to_image(frame2, path2)
            
            with open(path1, 'rb') as f:
                hash1 = hashlib.sha256(f.read()).hexdigest()
            with open(path2, 'rb') as f:
                hash2 = hashlib.sha256(f.read()).hexdigest()
            
            assert hash1 == hash2, \
                "Saved files must be byte-identical for same seed"
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestManifestRoundtrip:
    """Tests for manifest serialization and reconstruction."""
    
    def test_manifest_json_roundtrip(self):
        """Manifest must survive JSON serialization roundtrip."""
        original = ManifestBuilder(seed=42, width=128, height=128) \
            .with_preset("neon_jungle") \
            .with_grid_op("turbulence", octaves=4) \
            .with_effect("vignette", intensity=0.5) \
            .with_effect("bloom", threshold=0.7) \
            .with_metadata("Test Vision", tags=["test"]) \
            .build()
        
        json_str = original.to_json()
        restored = Manifest.from_json(json_str)
        
        assert original.fingerprint() == restored.fingerprint(), \
            "Manifest must survive JSON roundtrip"
    
    def test_manifest_validation(self):
        """Manifest validation must catch invalid parameters."""
        # Valid manifest
        valid = Manifest(seed=42, width=128, height=128)
        errors = valid.validate()
        assert len(errors) == 0, "Valid manifest should have no errors"
        
        # Invalid dimensions
        invalid = Manifest(seed=42, width=0, height=128)
        errors = invalid.validate()
        assert len(errors) > 0, "Invalid dimensions should produce errors"
        
        # Invalid format
        invalid = Manifest(seed=42, width=128, height=128, output_format="invalid")
        errors = invalid.validate()
        assert len(errors) > 0, "Invalid format should produce errors"
    
    def test_manifest_fingerprint(self):
        """Manifest fingerprint must be deterministic."""
        manifest = ManifestBuilder(seed=42, width=128, height=128) \
            .with_effect("vignette", intensity=0.5) \
            .build()
        
        fp1 = manifest.fingerprint()
        fp2 = manifest.fingerprint()
        
        assert fp1 == fp2, "Fingerprint must be deterministic"
        
        # Different seed should produce different fingerprint
        manifest2 = ManifestBuilder(seed=43, width=128, height=128) \
            .with_effect("vignette", intensity=0.5) \
            .build()
        
        assert manifest.fingerprint() != manifest2.fingerprint(), \
            "Different manifest should have different fingerprint"


class TestRendererIsolation:
    """Tests for ensuring renderers don't interfere with each other."""
    
    def test_parallel_renders_are_isolated(self):
        """Concurrent renders must not interfere."""
        import concurrent.futures
        
        def render_with_seed(seed):
            renderer = CanopyRenderer(width=64, height=64, seed=seed)
            return renderer.render_frame()
        
        # Render same seed in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(render_with_seed, 42) for _ in range(4)]
            frames = [f.result() for f in futures]
        
        # All frames must be identical
        for i in range(1, len(frames)):
            np.testing.assert_array_equal(frames[0], frames[i],
                err_msg="Parallel renders must produce identical results")
    
    def test_renderer_state_not_shared(self):
        """Renderer state must not leak between instances."""
        renderer1 = CanopyRenderer(width=64, height=64, seed=42)
        renderer2 = CanopyRenderer(width=64, height=64, seed=99)
        
        # Modify renderer1
        renderer1.effects.enable("vignette")
        
        # renderer2 should not have vignette enabled
        assert "vignette" not in renderer2.effects.get_config()["enabled"], \
            "Renderer state must not leak"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
