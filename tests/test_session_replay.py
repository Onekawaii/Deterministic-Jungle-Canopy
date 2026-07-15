"""
Test: Session Replay Functionality
Comprehensive tests for session replay, manifest reconstruction, and hash verification.
"""
import pytest
import numpy as np
import sys
import os
import hashlib
import copy
import json
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.session import SessionManager, Session, SessionEvent, EventType, SessionStatus
from canopy.manifest import Manifest, ManifestBuilder
from canopy.hashing import (
    hash_manifest,
    hash_event_log,
    hash_pixels,
    hash_session_export,
    hash_bytes,
    canonical_json,
)
from canopy import CanopyRenderer


class TestSessionReplayBasics:
    """Basic session replay functionality tests."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    @pytest.fixture
    def base_manifest(self):
        """Create a base manifest for testing."""
        return ManifestBuilder(seed=42, width=64, height=64).build()

    @pytest.fixture
    def session_with_events(self, session_manager, base_manifest):
        """Create a session with multiple events applied."""
        session = session_manager.create_session(base_manifest)
        
        # Apply several events
        events = [
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            ),
            SessionEvent(
                event_index=1,
                event_type=EventType.SET_EFFECT,
                payload={"effect": "vignette", "params": {"intensity": 0.5}}
            ),
            SessionEvent(
                event_index=2,
                event_type=EventType.GRID_DEFORM,
                payload={"type": "turbulence", "params": {"octaves": 3}}
            ),
        ]
        
        for event in events:
            session_manager.apply_event(session.session_id, event)
        
        return session

    def test_create_session(self, session_manager, base_manifest):
        """Test that creating a session works correctly."""
        session = session_manager.create_session(base_manifest)
        
        assert session is not None
        assert session.session_id is not None
        assert session.status == SessionStatus.ACTIVE
        assert session.current_manifest == base_manifest.to_dict()
        assert session.base_manifest == base_manifest.to_dict()
        assert len(session.events) == 0

    def test_session_replay_reconstructs_manifest(self, session_manager, session_with_events):
        """Test that replay_events reconstructs the current manifest."""
        session = session_with_events
        session_id = session.session_id
        
        # Get the current manifest
        current_manifest = session.current_manifest
        
        # Replay events on base manifest
        replayed = session_manager.replay_events(
            session.base_manifest,
            session.events
        )
        
        # The replayed manifest should match the current manifest
        assert replayed["seed"] == current_manifest["seed"], \
            "Seed should be preserved through replay"
        assert len(replayed.get("effects", [])) == len(current_manifest.get("effects", [])), \
            "Effects count should match"
        assert len(replayed.get("grid_operations", [])) == len(current_manifest.get("grid_operations", [])), \
            "Grid operations count should match"

    def test_frame_render_idempotency(self, session_manager, session_with_events):
        """Test that rendering the same frame twice yields identical pixel hash."""
        session = session_with_events
        width, height = 64, 64
        
        # Render frame 0 twice
        frame1, hash1 = session_manager.render_session_frame(
            session, 0, width=width, height=height
        )
        frame2, hash2 = session_manager.render_session_frame(
            session, 0, width=width, height=height
        )
        
        # Hashes should be identical
        assert hash1 == hash2, "Same frame rendered twice should have identical hash"
        
        # Pixel data should be identical
        np.testing.assert_array_equal(
            frame1, frame2,
            err_msg="Same frame rendered twice should produce identical pixels"
        )

    def test_frame_render_deterministic_pixel_hash(self, session_manager, session_with_events):
        """Test that frame pixel hash is deterministic using hashlib."""
        session = session_with_events
        width, height = 64, 64
        
        # Render multiple times and verify hash consistency
        hashes = []
        for _ in range(5):
            frame, pixel_hash = session_manager.render_session_frame(
                session, 0, width=width, height=height
            )
            hashes.append(pixel_hash)
            
            # Also verify with hash_pixels function
            direct_hash = hash_pixels(frame)
            assert direct_hash == pixel_hash, "hash_pixels should match returned hash"
        
        # All hashes should be identical
        assert len(set(hashes)) == 1, "Multiple renders should produce identical hashes"


class TestSessionEventReplay:
    """Tests for event replay in various scenarios."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_event_sequence_replay(self, session_manager):
        """Test that replaying events in sequence produces correct state."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events in sequence
        events = [
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 42}),
            SessionEvent(event_index=1, event_type=EventType.SET_EFFECT, 
                        payload={"effect": "vignette", "params": {"intensity": 0.3}}),
            SessionEvent(event_index=2, event_type=EventType.SET_EFFECT,
                        payload={"effect": "bloom", "params": {"threshold": 0.6}}),
            SessionEvent(event_index=3, event_type=EventType.GRID_DEFORM,
                        payload={"type": "ripple", "params": {"amplitude": 0.5}}),
        ]
        
        for event in events:
            session_manager.apply_event(session.session_id, event)
        
        # Replay events on base
        replayed = session_manager.replay_events(session.base_manifest, session.events)
        
        # Verify all events were applied correctly
        assert replayed["seed"] == 42, "Seed event should set seed to 42"
        
        effects = replayed.get("effects", [])
        assert len(effects) == 2, "Should have 2 effects"
        assert any(e.get("name") == "vignette" for e in effects), "Should have vignette effect"
        assert any(e.get("name") == "bloom" for e in effects), "Should have bloom effect"
        
        grid_ops = replayed.get("grid_operations", [])
        assert len(grid_ops) == 1, "Should have 1 grid operation"
        assert grid_ops[0].get("type") == "ripple", "Grid operation should be ripple"

    def test_partial_event_replay(self, session_manager):
        """Test replaying only a subset of events."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply 4 events
        for i in range(4):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(event_index=i, event_type=EventType.SET_SEED, 
                           payload={"seed": i * 10})
            )
        
        # Replay only first 2 events
        partial_replay = session_manager.replay_events(
            session.base_manifest,
            session.events[:2]
        )
        
        assert partial_replay["seed"] == 10, "Partial replay should have seed from event 1"

    def test_replay_with_preset_application(self, session_manager):
        """Test replay when applying presets."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Add some effects first
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_EFFECT,
                        payload={"effect": "noise", "params": {"amount": 0.2}})
        )
        
        # Replay from scratch
        replayed = session_manager.replay_events(session.base_manifest, session.events)
        
        # Should have the noise effect
        effects = replayed.get("effects", [])
        assert any(e.get("name") == "noise" for e in effects), "Should have noise effect"


class TestSessionExportConsistency:
    """Tests for session export hash consistency."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    @pytest.fixture
    def session_with_complex_state(self, session_manager):
        """Create a session with complex state."""
        base_manifest = ManifestBuilder(seed=12345, width=64, height=64) \
            .with_effect("vignette", intensity=0.5) \
            .with_grid_op("turbulence", octaves=4) \
            .build()
        
        session = session_manager.create_session(base_manifest)
        
        # Add multiple events
        events = [
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 999}),
            SessionEvent(event_index=1, event_type=EventType.SET_EFFECT,
                        payload={"effect": "bloom", "params": {"threshold": 0.8}}),
            SessionEvent(event_index=2, event_type=EventType.GRID_DEFORM,
                        payload={"type": "warp", "params": {"scale": 1.5}}),
        ]
        
        for event in events:
            session_manager.apply_event(session.session_id, event)
        
        return session

    def test_identical_session_exports_hash_identically(self, session_manager, session_with_complex_state):
        """Test that exporting the same session twice produces identical hashes."""
        session = session_with_complex_state
        
        # Export twice
        export1 = session_manager.export_session(session.session_id)
        export2 = session_manager.export_session(session.session_id)
        
        assert export1 is not None
        assert export2 is not None
        
        # Hash both exports
        hash1 = hash_session_export(export1)
        hash2 = hash_session_export(export2)
        
        assert hash1 == hash2, "Identical sessions should export to identical hashes"

    def test_different_sessions_different_export_hashes(self, session_manager):
        """Test that different sessions produce different export hashes."""
        base_manifest1 = ManifestBuilder(seed=100, width=32, height=32).build()
        base_manifest2 = ManifestBuilder(seed=200, width=32, height=32).build()
        
        session1 = session_manager.create_session(base_manifest1)
        session2 = session_manager.create_session(base_manifest2)
        
        export1 = session_manager.export_session(session1.session_id)
        export2 = session_manager.export_session(session2.session_id)
        
        hash1 = hash_session_export(export1)
        hash2 = hash_session_export(export2)
        
        assert hash1 != hash2, "Different sessions should have different export hashes"

    def test_same_state_different_session_ids_different_hashes(self, session_manager):
        """Test that same state with different IDs produces different hashes."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        
        session1 = session_manager.create_session(base_manifest)
        session2 = session_manager.create_session(base_manifest)
        
        export1 = session_manager.export_session(session1.session_id)
        export2 = session_manager.export_session(session2.session_id)
        
        hash1 = hash_session_export(export1)
        hash2 = hash_session_export(export2)
        
        # Session IDs are different, so hashes should be different
        assert hash1 != hash2, "Different session IDs should produce different hashes"

    def test_import_export_roundtrip(self, session_manager, session_with_complex_state):
        """Test that import/export roundtrip preserves session state."""
        # Export
        original_export = session_manager.export_session(session_with_complex_state.session_id)
        original_hash = hash_session_export(original_export)
        
        # Import
        imported_session, error = session_manager.import_session(original_export)
        
        assert imported_session is not None, f"Import should succeed: {error}"
        assert error is None
        
        # Export imported session
        reimported_export = session_manager.export_session(imported_session.session_id)
        reimported_hash = hash_session_export(reimported_export)
        
        # Manifest hashes should match
        assert hash_manifest(imported_session.current_manifest) == \
               hash_manifest(session_with_complex_state.current_manifest), \
               "Import should preserve manifest state"


class TestPixelHashIdempotency:
    """Tests for pixel hash determinism and idempotency."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_render_frame_n_twice_identical_hash(self, session_manager):
        """Test that rendering frame N twice yields identical pixel hash."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Add an event
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_EFFECT,
                        payload={"effect": "vignette", "params": {"intensity": 0.4}})
        )
        
        # Render frame 0 twice
        _, hash1 = session_manager.render_session_frame(session, 0, width=32, height=32)
        _, hash2 = session_manager.render_session_frame(session, 0, width=32, height=32)
        
        assert hash1 == hash2, "Rendering same frame twice should yield identical hash"

    def test_same_manifest_different_sessions_same_pixel_hash(self, session_manager):
        """Test that same manifest produces same pixel hash across sessions."""
        base_manifest = ManifestBuilder(seed=777, width=32, height=32) \
            .with_effect("bloom", threshold=0.7) \
            .build()
        
        session1 = session_manager.create_session(base_manifest)
        session2 = session_manager.create_session(base_manifest)
        
        _, hash1 = session_manager.render_session_frame(session1, 0, width=32, height=32)
        _, hash2 = session_manager.render_session_frame(session2, 0, width=32, height=32)
        
        assert hash1 == hash2, "Same manifest should produce same pixel hash"

    def test_manifest_hash_deterministic(self, session_manager):
        """Test that manifest hash is deterministic."""
        manifest = ManifestBuilder(seed=42, width=32, height=32) \
            .with_effect("vignette", intensity=0.5) \
            .with_grid_op("turbulence", octaves=3) \
            .build()
        
        hash1 = hash_manifest(manifest)
        hash2 = hash_manifest(manifest)
        
        assert hash1 == hash2, "Manifest hash should be deterministic"
        
        # Verify it's a valid SHA-256 hex
        assert len(hash1) == 64, "Hash should be 64 hex characters (SHA-256)"

    def test_event_log_hash_deterministic(self, session_manager):
        """Test that event log hash is deterministic."""
        events = [
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 42}),
            SessionEvent(event_index=1, event_type=EventType.SET_EFFECT,
                        payload={"effect": "bloom", "params": {"threshold": 0.8}}),
        ]
        
        hash1 = hash_event_log(events)
        hash2 = hash_event_log(events)
        
        assert hash1 == hash2, "Event log hash should be deterministic"

    def test_pixel_hash_uses_hashlib_sha256(self, session_manager):
        """Test that pixel hash uses hashlib SHA-256."""
        renderer = CanopyRenderer(width=32, height=32, seed=42)
        frame = renderer.render_frame()
        
        # Get hash using hash_pixels
        hash_pixels_result = hash_pixels(frame)
        
        # Get hash using hashlib directly
        hashlib_result = hashlib.sha256(frame.tobytes()).hexdigest()
        
        assert hash_pixels_result == hashlib_result, \
            "hash_pixels should use SHA-256 from hashlib"


class TestSessionRewindAndFork:
    """Tests for session rewind and fork functionality."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_rewind_restores_manifest_state(self, session_manager):
        """Test that rewinding a session restores the correct manifest state."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 100})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=1, event_type=EventType.SET_SEED, payload={"seed": 200})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_SEED, payload={"seed": 300})
        )
        
        # Rewind to event index 1
        success, error = session_manager.rewind_session(session.session_id, 1)
        
        assert success, f"Rewind should succeed: {error}"
        assert session.current_manifest["seed"] == 200, "Should be rewound to seed 200"

    def test_fork_creates_independent_session(self, session_manager):
        """Test that forking creates an independent session with correct state."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 100})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=1, event_type=EventType.SET_SEED, payload={"seed": 200})
        )
        
        # Fork at event index 1
        fork_session, error = session_manager.fork_session(session.session_id, 1)
        
        assert fork_session is not None, f"Fork should succeed: {error}"
        assert fork_session.parent_session_id == session.session_id
        assert fork_session.fork_event_index == 1
        assert fork_session.current_manifest["seed"] == 200

    def test_fork_has_independent_history(self, session_manager):
        """Test that forked session has independent event history."""
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 100})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=1, event_type=EventType.SET_SEED, payload={"seed": 200})
        )
        
        # Fork at event index 1
        fork_session, _ = session_manager.fork_session(session.session_id, 1)
        
        # Add more events to original
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_SEED, payload={"seed": 300})
        )
        
        # Fork should still have only 2 events
        assert len(fork_session.events) == 2
        assert len(session.events) == 3


class TestSessionIntegrity:
    """Tests for session integrity verification."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_verify_valid_session(self, session_manager):
        """Test verification of a valid session."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_SEED, payload={"seed": 100})
        )
        
        is_valid, errors = session_manager.verify_session_integrity(session.session_id)
        
        assert is_valid, f"Valid session should pass verification: {errors}"
        assert len(errors) == 0

    def test_verify_nonexistent_session(self, session_manager):
        """Test verification of a nonexistent session."""
        is_valid, errors = session_manager.verify_session_integrity("nonexistent-id")
        
        assert not is_valid, "Nonexistent session should fail verification"
        assert "not found" in errors[0].lower()


class TestHashFunctions:
    """Tests for hash utility functions."""

    def test_canonical_json_is_deterministic(self):
        """Test that canonical_json produces deterministic output."""
        data = {
            "b": 2,
            "a": 1,
            "c": [3, 1, 2],
        }
        
        result1 = canonical_json(data)
        result2 = canonical_json(data)
        
        assert result1 == result2, "Canonical JSON should be deterministic"

    def test_canonical_json_sorts_keys(self):
        """Test that canonical_json sorts keys."""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        
        result1 = canonical_json(data1)
        result2 = canonical_json(data2)
        
        assert result1 == result2, "Canonical JSON should produce same output regardless of key order"

    def test_hash_bytes_uses_sha256(self):
        """Test that hash_bytes uses SHA-256."""
        data = b"test data"
        
        result = hash_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        
        assert result == expected, "hash_bytes should use SHA-256"

    def test_hash_pixels_handles_different_shapes(self):
        """Test that hash_pixels handles different array shapes."""
        # 2D array
        frame_2d = np.zeros((32, 32), dtype=np.uint8)
        hash_2d = hash_pixels(frame_2d)
        
        # 3D array
        frame_3d = np.zeros((32, 32, 3), dtype=np.uint8)
        hash_3d = hash_pixels(frame_3d)
        
        # Different shapes should produce different hashes
        assert hash_2d != hash_3d, "Different shapes should produce different hashes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
