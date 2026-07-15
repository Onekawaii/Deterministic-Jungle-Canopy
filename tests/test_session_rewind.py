"""
Test: Session Rewind Functionality
Comprehensive tests for session rewind behavior, manifest reconstruction,
event index validation, history preservation, and rewind-advance cycles.
"""
import pytest
import copy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.session import (
    SessionManager,
    Session,
    SessionEvent,
    EventType,
    SessionStatus,
)


class TestRewindManifestReconstruction:
    """Test that rewind correctly reconstructs earlier manifest states."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def session_with_multiple_events(self, session_manager):
        """Create a session with 5 seed-changing events for rewind testing."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply 5 events that change the seed
        seeds = [10, 20, 30, 40, 50]
        for i, seed_value in enumerate(seeds):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": seed_value}
                )
            )
        
        return session, seeds

    def test_rewind_reconstructs_earlier_manifest(self, session_manager, session_with_multiple_events):
        """Test that rewinding reconstructs the manifest at that event index."""
        session, seeds = session_with_multiple_events
        
        # Rewind to event index 2 (seed should be 30)
        success, error = session_manager.rewind_session(session.session_id, 2)
        
        assert success, f"Rewind should succeed: {error}"
        assert session.current_manifest["seed"] == seeds[2], \
            f"Rewound manifest seed should be {seeds[2]}, got {session.current_manifest['seed']}"

    def test_rewind_to_first_event(self, session_manager, session_with_multiple_events):
        """Test rewinding to the very first event (index 0)."""
        session, seeds = session_with_multiple_events
        
        # Rewind to event index 0
        success, error = session_manager.rewind_session(session.session_id, 0)
        
        assert success, f"Rewind to first event should succeed: {error}"
        assert session.current_manifest["seed"] == seeds[0], \
            f"Rewound manifest seed should be {seeds[0]}"

    def test_rewind_preserves_grid_operations(self, session_manager):
        """Test that rewinding preserves earlier grid operations."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Add grid operations
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.GRID_DEFORM,
                        payload={"type": "turbulence", "params": {"octaves": 3}})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=1, event_type=EventType.GRID_DEFORM,
                        payload={"type": "ripple", "params": {"amplitude": 0.5}})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_SEED,
                        payload={"seed": 100})
        )
        
        # Rewind to index 1
        session_manager.rewind_session(session.session_id, 1)
        
        grid_ops = session.current_manifest.get("grid_operations", [])
        assert len(grid_ops) == 2, "Should have 2 grid operations after rewind to index 1"
        assert grid_ops[0]["type"] == "turbulence"
        assert grid_ops[1]["type"] == "ripple"

    def test_rewind_preserves_effects(self, session_manager):
        """Test that rewinding preserves earlier effects."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Add effects
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=0, event_type=EventType.SET_EFFECT,
                        payload={"effect": "vignette", "params": {"intensity": 0.5}})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=1, event_type=EventType.SET_EFFECT,
                        payload={"effect": "bloom", "params": {"threshold": 0.8}})
        )
        session_manager.apply_event(
            session.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_EFFECT,
                        payload={"effect": "blur", "params": {"radius": 2}})
        )
        
        # Rewind to index 1
        session_manager.rewind_session(session.session_id, 1)
        
        effects = session.current_manifest.get("effects", [])
        assert len(effects) == 2, "Should have 2 effects after rewind to index 1"
        effect_names = [e.get("name") for e in effects]
        assert "vignette" in effect_names
        assert "bloom" in effect_names


class TestRewindEventIndexValidation:
    """Test that event indexes remain valid after rewind."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def session_with_events(self, session_manager):
        """Create a session with multiple events."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        for i in range(5):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        return session

    def test_event_indexes_remain_contiguous_after_rewind(self, session_manager, session_with_events):
        """Test that event indexes stay contiguous after rewinding."""
        session = session_with_events
        
        # Rewind to index 2
        session_manager.rewind_session(session.session_id, 2)
        
        # All events should still have their original indexes
        for i, event in enumerate(session.events):
            assert event.event_index == i, \
                f"Event at position {i} should have index {i}, got {event.event_index}"

    def test_rewind_maintains_event_count(self, session_manager, session_with_events):
        """Test that rewind does not delete events from the history."""
        session = session_with_events
        original_count = len(session.events)
        
        # Rewind to index 2
        session_manager.rewind_session(session.session_id, 2)
        
        # Event count should remain the same
        assert len(session.events) == original_count, \
            "Rewind should not delete events from history"

    def test_rewind_updates_current_frame(self, session_manager, session_with_events):
        """Test that rewind updates the current_frame to match the rewound index."""
        session = session_with_events
        
        # Rewind to index 3
        session_manager.rewind_session(session.session_id, 3)
        
        assert session.current_frame == 3, \
            f"current_frame should be 3 after rewind, got {session.current_frame}"


class TestRewindHistoryPreservation:
    """Test that history is preserved correctly after rewind."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_full_history_accessible_after_rewind(self, session_manager):
        """Test that all events are still accessible after rewinding."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply 5 events
        for i in range(5):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )
        
        # Rewind to index 1
        session_manager.rewind_session(session.session_id, 1)
        
        # All 5 events should still be accessible
        assert len(session.events) == 5, "All events should still be accessible after rewind"
        
        # Verify we can reconstruct any earlier state via replay
        for idx in range(5):
            replayed = session_manager.replay_events(
                session.base_manifest,
                session.events[:idx + 1]
            )
            assert replayed["seed"] == (idx + 1) * 100

    def test_rewind_clears_frame_cache(self, session_manager):
        """Test that rewinding clears the frame cache."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Add some events and populate cache
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Manually add entries to frame cache
        session._frame_cache[0] = "test_hash_1"
        session._frame_cache[1] = "test_hash_2"
        
        # Rewind
        session_manager.rewind_session(session.session_id, 1)
        
        # Frame cache should be cleared
        assert len(session._frame_cache) == 0, \
            "Frame cache should be cleared after rewind"

    def test_multiple_rewinds_maintain_history(self, session_manager):
        """Test that multiple rewinds to different points maintain full history."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply 4 events
        for i in range(4):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Rewind to index 1
        session_manager.rewind_session(session.session_id, 1)
        assert session.current_manifest["seed"] == 20
        
        # Rewind to index 0
        session_manager.rewind_session(session.session_id, 0)
        assert session.current_manifest["seed"] == 10
        
        # Rewind to index 2
        session_manager.rewind_session(session.session_id, 2)
        assert session.current_manifest["seed"] == 30
        
        # History should still be complete
        assert len(session.events) == 4, "All events should still be preserved"


class TestInvalidRewindScenarios:
    """Test rewind behavior with invalid inputs."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def session_with_events(self, session_manager):
        """Create a session with some events."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        return session

    def test_rewind_negative_index_fails(self, session_manager, session_with_events):
        """Test that rewinding with a negative index fails."""
        session = session_with_events
        
        success, error = session_manager.rewind_session(session.session_id, -1)
        
        assert not success, "Rewind with negative index should fail"
        assert error is not None
        assert "invalid" in error.lower() or "index" in error.lower()

    def test_rewind_beyond_last_event_fails(self, session_manager, session_with_events):
        """Test that rewinding beyond the last event index fails."""
        session = session_with_events
        max_valid_index = len(session.events) - 1  # 2
        
        success, error = session_manager.rewind_session(session.session_id, max_valid_index + 1)
        
        assert not success, "Rewind beyond last event should fail"
        assert error is not None

    def test_rewind_nonexistent_session_fails(self, session_manager):
        """Test that rewinding a nonexistent session fails gracefully."""
        success, error = session_manager.rewind_session("nonexistent-session-id", 0)
        
        assert not success, "Rewind of nonexistent session should fail"
        assert "not found" in error.lower()

    def test_rewind_closed_session_fails(self, session_manager, session_with_events):
        """Test that rewinding a closed session fails."""
        session = session_with_events
        session.status = SessionStatus.CLOSED
        
        success, error = session_manager.rewind_session(session.session_id, 1)
        
        assert not success, "Rewind of closed session should fail"
        assert "closed" in error.lower()


class TestRewindAndAdvanceAgain:
    """Test rewind followed by advancing with new events."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_rewind_then_advance_creates_new_branch(self, session_manager):
        """Test that advancing after rewind creates a new timeline branch."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply 3 events: seeds 10, 20, 30
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Rewind to index 1 (seed 20)
        session_manager.rewind_session(session.session_id, 1)
        assert session.current_manifest["seed"] == 20
        
        # Advance with new events (different seeds)
        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=3,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )
        
        # Current seed should be the new one
        assert session.current_manifest["seed"] == 999
        
        # History should show the divergence
        assert len(session.events) == 4
        assert session.events[3].payload["seed"] == 999

    def test_rewind_and_render_at_earlier_point(self, session_manager):
        """Test rendering works correctly at a rewound state."""
        from canopy.manifest import ManifestBuilder
        from canopy import CanopyRenderer
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )
        
        # Rewind to index 1
        session_manager.rewind_session(session.session_id, 1)
        
        # Render should work at the rewound state
        frame, pixel_hash = session_manager.render_session_frame(
            session, session.current_frame, width=32, height=32
        )
        
        assert frame is not None
        assert pixel_hash is not None
        
        # Verify deterministic rendering
        frame2, pixel_hash2 = session_manager.render_session_frame(
            session, session.current_frame, width=32, height=32
        )
        assert pixel_hash == pixel_hash2, "Rendering should be deterministic"

    def test_can_rewind_to_same_point_multiple_times(self, session_manager):
        """Test that rewinding to the same point multiple times is idempotent."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        for i in range(4):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Rewind to index 2 multiple times
        for _ in range(3):
            session_manager.rewind_session(session.session_id, 2)
        
        assert session.current_manifest["seed"] == 30
        assert session.current_frame == 2
        assert len(session.events) == 4, "History should be preserved"

    def test_rewind_preserves_base_manifest_reference(self, session_manager):
        """Test that rewinding doesn't modify the base_manifest."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        original_base_dict = copy.deepcopy(base_manifest.to_dict())
        
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )
        
        # Rewind
        session_manager.rewind_session(session.session_id, 1)
        
        # Base manifest should be unchanged
        assert session.base_manifest == original_base_dict, \
            "Base manifest should not be modified by rewind"


class TestRewindIntegrity:
    """Test rewind-related integrity checks."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_session_integrity_after_rewind(self, session_manager):
        """Test that session passes integrity check after rewind."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Rewind
        session_manager.rewind_session(session.session_id, 1)
        
        # Integrity check should pass
        is_valid, errors = session_manager.verify_session_integrity(session.session_id)
        
        assert is_valid, f"Session should pass integrity check after rewind: {errors}"

    def test_rewind_then_fork_maintains_correct_state(self, session_manager):
        """Test that forking after rewind uses the rewound state."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events
        for i in range(4):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Rewind to index 2
        session_manager.rewind_session(session.session_id, 2)
        
        # Fork from rewound state
        fork_session, error = session_manager.fork_session(session.session_id, 2)
        
        assert fork_session is not None, f"Fork should succeed: {error}"
        assert fork_session.current_manifest["seed"] == 30, \
            "Fork should have the rewound state's seed"
        assert len(fork_session.events) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
