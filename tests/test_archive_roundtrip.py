"""
Test: Archive Roundtrip
Verifies that archive save/load produces identical visual output.
"""
import pytest
import numpy as np
import sys
import os
import tempfile
import hashlib
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy import CanopyRenderer, Archive
from canopy.manifest import ManifestBuilder


class TestArchiveRoundtrip:
    """Tests for archive save/load determinism."""
    
    @pytest.fixture
    def temp_archive(self):
        """Create a temporary archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_archive.db")
        archive = Archive(db_path)
        yield archive
        shutil.rmtree(tmpdir)
    
    @pytest.fixture
    def renderer_with_archive(self, temp_archive):
        """Create renderer bound to archive."""
        renderer = CanopyRenderer(width=128, height=128, seed=42)
        renderer.bind_archive(temp_archive)
        return renderer
    
    def test_save_and_load_produces_identical_frame(self, renderer_with_archive):
        """Loading from archive must produce identical output."""
        # Configure renderer
        renderer_with_archive.effects.enable("vignette")
        renderer_with_archive.effects.enable("bloom")
        renderer_with_archive.grid.add_turbulence()
        
        # Save to archive BEFORE first render (to capture pre-render state)
        entry_id = renderer_with_archive.save_to_archive("Test Vision")
        
        # Reset to same seed and reconfigure
        renderer_with_archive.reset(seed=42)
        renderer_with_archive.effects.reset()
        renderer_with_archive.effects.enable("vignette")
        renderer_with_archive.effects.enable("bloom")
        renderer_with_archive.grid.add_turbulence()
        
        # Render original
        original_frame = renderer_with_archive.render_frame()
        original_hash = hashlib.sha256(original_frame.tobytes()).hexdigest()
        
        # Reset renderer to different seed
        renderer_with_archive.reset(seed=12345)
        
        # Load from archive
        renderer_with_archive.load_from_archive(entry_id)
        
        # Render again
        loaded_frame = renderer_with_archive.render_frame()
        loaded_hash = hashlib.sha256(loaded_frame.tobytes()).hexdigest()
        
        assert original_hash == loaded_hash, \
            "Loaded archive entry must produce identical frame"
    
    def test_archive_entry_contains_complete_manifest(self, renderer_with_archive):
        """Archive entry must contain all data needed for reproduction."""
        renderer_with_archive.effects.enable("vignette")
        renderer_with_archive.effects.set_param("vignette", "intensity", 0.7)
        renderer_with_archive.effects.enable("bloom")
        renderer_with_archive.grid.add_kaleidoscope(segments=6)
        
        # Save to archive
        entry_id = renderer_with_archive.save_to_archive("Complete Vision")
        
        # Get full entry
        entry = renderer_with_archive.archive.get_entry(entry_id)
        state = renderer_with_archive.archive.load_state(entry_id)
        
        assert entry is not None, "Entry must exist"
        assert state is not None, "State must be loadable"
        
        # Verify state contains expected data
        assert "seed" in state
        assert "grid" in state
        assert "effects" in state
        
        # Effects should be preserved
        effects_config = state["effects"]
        assert "vignette" in effects_config["enabled"]
        assert effects_config["params"]["vignette"]["intensity"] == 0.7
    
    def test_multiple_entries_are_isolated(self, renderer_with_archive):
        """Multiple saved entries must not interfere."""
        # Create and save entry 1
        renderer_with_archive.set_seed(1)
        renderer_with_archive.effects.enable("vignette")
        entry1_id = renderer_with_archive.save_to_archive("Vision 1")
        hash1 = hashlib.sha256(renderer_with_archive.render_frame().tobytes()).hexdigest()
        
        # Create and save entry 2
        renderer_with_archive.set_seed(2)
        renderer_with_archive.effects.disable("vignette")
        renderer_with_archive.effects.enable("bloom")
        entry2_id = renderer_with_archive.save_to_archive("Vision 2")
        hash2 = hashlib.sha256(renderer_with_archive.render_frame().tobytes()).hexdigest()
        
        # Load entry 1
        renderer_with_archive.load_from_archive(entry1_id)
        loaded1_hash = hashlib.sha256(renderer_with_archive.render_frame().tobytes()).hexdigest()
        
        # Load entry 2
        renderer_with_archive.load_from_archive(entry2_id)
        loaded2_hash = hashlib.sha256(renderer_with_archive.render_frame().tobytes()).hexdigest()
        
        assert hash1 == loaded1_hash, "Entry 1 must be preserved"
        assert hash2 == loaded2_hash, "Entry 2 must be preserved"
        assert hash1 != hash2, "Different entries must produce different results"
    
    def test_export_and_import_is_preserved(self, renderer_with_archive):
        """Export/import must preserve exact state."""
        # Configure
        renderer_with_archive.effects.apply_preset("solaris_dream")
        renderer_with_archive.grid.add_turbulence()
        
        # Export config BEFORE render
        original_config = renderer_with_archive.export_config()
        
        # Reset and reconfigure for "original" render
        renderer_with_archive.reset(seed=42)
        renderer_with_archive.effects.reset()
        renderer_with_archive.effects.apply_preset("solaris_dream")
        renderer_with_archive.grid.add_turbulence()
        
        original_hash = hashlib.sha256(
            renderer_with_archive.render_frame().tobytes()
        ).hexdigest()
        
        # Reset to different state
        renderer_with_archive.set_seed(99999)
        renderer_with_archive.reset()
        
        # Import original config
        renderer_with_archive.import_config(original_config)
        
        # Must produce same frame
        imported_hash = hashlib.sha256(
            renderer_with_archive.render_frame().tobytes()
        ).hexdigest()
        
        assert original_hash == imported_hash, \
            "Import must restore exact original state"
    
    def test_archive_search_by_seed(self, temp_archive):
        """Archive search must work with seed filter."""
        renderer = CanopyRenderer(width=64, height=64)
        renderer.bind_archive(temp_archive)
        
        # Save entries with different seeds
        for seed in [1, 2, 3, 2, 1]:
            renderer.set_seed(seed)
            renderer.save_to_archive(f"Seed {seed}")
        
        # Search for seed 2
        results = temp_archive.search(seed=2)
        
        assert len(results) == 2, "Should find exactly 2 entries with seed 2"
        
        for result in results:
            assert result["seed"] == 2, "All results must have seed 2"
    
    def test_archive_stats(self, temp_archive):
        """Archive stats must be accurate."""
        renderer = CanopyRenderer(width=64, height=64)
        renderer.bind_archive(temp_archive)
        
        # Save some entries
        for i in range(5):
            renderer.set_seed(i)
            renderer.save_to_archive(f"Entry {i}")
        
        stats = temp_archive.get_stats()
        
        assert stats["total_entries"] == 5, "Should have 5 entries"
        assert stats["unique_seeds"] == 5, "Should have 5 unique seeds"
        assert stats["total_views"] >= 0, "Views should be tracked"


class TestArchiveCorruption:
    """Tests for handling corrupt/invalid archive data."""
    
    @pytest.fixture
    def temp_archive(self):
        """Create a temporary archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_archive.db")
        archive = Archive(db_path)
        yield archive
        shutil.rmtree(tmpdir)
    
    def test_load_nonexistent_entry(self, temp_archive):
        """Loading nonexistent entry must fail gracefully."""
        state = temp_archive.load_state(99999)
        assert state is None, "Nonexistent entry must return None"
    
    def test_delete_nonexistent_entry(self, temp_archive):
        """Deleting nonexistent entry must fail gracefully."""
        result = temp_archive.delete(99999)
        assert result is False, "Delete of nonexistent must return False"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
