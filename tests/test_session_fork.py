"""
Test: Session Fork Functionality
Comprehensive tests for session fork behavior, parent-child relationships,
divergence tracking, and independent timeline evolution.
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


class TestForkBasicBehavior:
    """Test fundamental fork creation and properties."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def parent_session(self, session_manager):
        """Create a parent session with multiple events."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        
        # Apply events with different seed values
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

    def test_fork_creates_new_session(self, session_manager, parent_session):
        """Test that fork creates a new, independent session."""
        parent, _ = parent_session
        
        fork_session, error = session_manager.fork_session(parent.session_id, 2)
        
        assert fork_session is not None, f"Fork should succeed: {error}"
        assert fork_session.session_id != parent.session_id, \
            "Fork should have a different session ID"
        assert session_manager.get_session(fork_session.session_id) is not None, \
            "Fork should be registered in session manager"

    def test_fork_has_correct_parent_reference(self, session_manager, parent_session):
        """Test that fork correctly references its parent session."""
        parent, _ = parent_session
        
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        
        assert fork_session.parent_session_id == parent.session_id, \
            "Fork should reference its parent session ID"
        assert fork_session.fork_event_index == 2, \
            "Fork should record the event index it was created from"


class TestForkMatchesParentBeforeDivergence:
    """Test that fork state matches parent before divergence point."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def parent_session(self, session_manager):
        """Create a parent session with multiple events."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=100, width=64, height=64).build()
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
        
        return session

    def test_fork_matches_parent_seed_at_fork_point(self, session_manager, parent_session):
        """Test that fork has the same seed as parent had at fork point in history."""
        parent = parent_session
        
        # Fork at event index 3 (parent has 5 events, fork should have seed 400 from event 3)
        fork_session, _ = session_manager.fork_session(parent.session_id, 3)
        
        # The fork should have seed 400 (from event at index 3)
        # Parent continues to have seed 500 (from last event)
        assert fork_session.current_manifest["seed"] == 400, \
            f"Fork seed should be 400 (state at event index 3), got {fork_session.current_manifest['seed']}"
        assert parent.current_manifest["seed"] == 500, \
            "Parent should still have its current state (seed 500)"

    def test_fork_matches_parent_manifest_at_fork_point(self, session_manager, parent_session):
        """Test that fork manifest matches what parent had at the fork event in history."""
        parent = parent_session
        
        # Parent continues to evolve (seed 500), but fork is created at event index 2 (seed 300)
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        
        # Fork should have seed 300 (state at event index 2)
        assert fork_session.current_manifest["seed"] == 300, \
            f"Fork should have seed 300 (at event index 2), got {fork_session.current_manifest['seed']}"
        # Parent should have seed 500 (current state)
        assert parent.current_manifest["seed"] == 500, \
            "Parent should have current seed 500"

    def test_fork_has_same_events_as_parent_up_to_fork_point(self, session_manager, parent_session):
        """Test that fork inherits all events up to the fork point."""
        parent = parent_session
        fork_index = 3
        
        fork_session, _ = session_manager.fork_session(parent.session_id, fork_index)
        
        # Fork should have events 0, 1, 2, 3
        assert len(fork_session.events) == fork_index + 1, \
            f"Fork should have {fork_index + 1} events"
        
        for i, event in enumerate(fork_session.events):
            assert event.event_index == i, \
                f"Fork event {i} should have correct index"
            assert event.event_type == parent.events[i].event_type, \
                f"Event {i} type should match parent"
            assert event.payload == parent.events[i].payload, \
                f"Event {i} payload should match parent"

    def test_fork_from_first_event(self, session_manager, parent_session):
        """Test forking from the very first event (index 0)."""
        parent = parent_session
        
        fork_session, _ = session_manager.fork_session(parent.session_id, 0)
        
        # Fork at index 0 should have 1 event (the event at index 0)
        assert len(fork_session.events) == 1, "Fork from index 0 should have 1 event"
        # The seed at event 0 is (0+1) * 100 = 100
        assert fork_session.current_manifest["seed"] == 100, \
            "Fork from index 0 should have seed 100"


class TestForkDivergenceBehavior:
    """Test that fork diverges correctly after fork point."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def forked_pair(self, session_manager):
        """Create a parent session and a fork at event index 2."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Apply 5 events with seed changes
        seeds = [10, 20, 30, 40, 50]
        for i, seed_value in enumerate(seeds):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": seed_value}
                )
            )
        
        # Fork at index 2 (seed will be 30)
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        
        return parent, fork_session, seeds

    def test_fork_divergence_with_new_event(self, session_manager, forked_pair):
        """Test that fork diverges when new event is applied."""
        parent, fork_session, _ = forked_pair
        parent_original_seed = parent.current_manifest["seed"]
        
        # Apply a new event to the fork only
        session_manager.apply_event(
            fork_session.session_id,
            SessionEvent(
                event_index=3,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )
        
        # Fork should have the new seed
        assert fork_session.current_manifest["seed"] == 999, \
            "Fork should have the new seed after divergence"
        
        # Parent should be unchanged
        assert parent.current_manifest["seed"] == parent_original_seed, \
            "Parent seed should remain unchanged after fork mutation"

    def test_fork_divergence_affects_only_fork(self, session_manager, forked_pair):
        """Test that changes to fork do not affect parent."""
        parent, fork_session, _ = forked_pair
        
        # Add multiple events to fork
        for i in range(3):
            session_manager.apply_event(
                fork_session.session_id,
                SessionEvent(
                    event_index=3 + i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": 100 + i}
                )
            )
        
        # Parent should be completely unchanged
        assert len(parent.events) == 5, \
            "Parent should still have original 5 events"
        assert parent.current_manifest["seed"] == 50, \
            "Parent seed should be unchanged"

    def test_multiple_divergence_events_on_fork(self, session_manager, forked_pair):
        """Test multiple sequential divergence events on fork."""
        parent, fork_session, _ = forked_pair
        
        # Apply multiple events to fork
        new_seeds = [111, 222, 333, 444]
        for i, seed_value in enumerate(new_seeds):
            session_manager.apply_event(
                fork_session.session_id,
                SessionEvent(
                    event_index=3 + i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": seed_value}
                )
            )
        
        # Fork should have all new events
        assert len(fork_session.events) == 7, \
            f"Fork should have 7 events (original 3 + 4 new), got {len(fork_session.events)}"
        assert fork_session.events[-1].payload["seed"] == 444, \
            "Fork should have last new seed"

    def test_parent_continues_independently(self, session_manager, forked_pair):
        """Test that parent session continues independently after fork."""
        parent, fork_session, _ = forked_pair
        
        # Apply event to parent
        session_manager.apply_event(
            parent.session_id,
            SessionEvent(
                event_index=5,
                event_type=EventType.SET_SEED,
                payload={"seed": 888}
            )
        )
        
        # Parent should have advanced
        assert len(parent.events) == 6, "Parent should have 6 events"
        assert parent.current_manifest["seed"] == 888
        
        # Fork should be unaffected
        assert len(fork_session.events) == 3, "Fork should still have 3 events"
        assert fork_session.current_manifest["seed"] == 30, "Fork seed should be unchanged"


class TestForkParentUnchanged:
    """Test that parent remains unchanged after fork operations."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def parent_with_state(self, session_manager):
        """Create a parent session with complex state."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(
            seed=999, width=128, height=128
        ).with_grid_op("turbulence", octaves=5).with_effect("bloom", intensity=0.8).build()
        
        session = session_manager.create_session(base_manifest)
        
        # Apply several events
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )
        
        return session

    def test_parent_state_unchanged_after_fork(self, session_manager, parent_with_state):
        """Test that parent manifest is unchanged after forking."""
        parent = parent_with_state
        original_seed = parent.current_manifest["seed"]
        original_events_count = len(parent.events)
        
        # Create fork
        fork_session, _ = session_manager.fork_session(parent.session_id, 1)
        
        # Parent should be unchanged
        assert parent.current_manifest["seed"] == original_seed, \
            "Parent seed should be unchanged after fork"
        assert len(parent.events) == original_events_count, \
            "Parent event count should be unchanged"
        assert parent.session_id == parent_with_state.session_id, \
            "Parent session ID should be unchanged"

    def test_parent_unchanged_after_fork_mutation(self, session_manager, parent_with_state):
        """Test that parent is unchanged even after fork is mutated."""
        parent = parent_with_state
        original_manifest = copy.deepcopy(parent.current_manifest)
        
        # Create fork and mutate it
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        for i in range(5):
            session_manager.apply_event(
                fork_session.session_id,
                SessionEvent(
                    event_index=3 + i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": 1000 + i}
                )
            )
        
        # Parent should be completely unchanged
        assert parent.current_manifest == original_manifest, \
            "Parent manifest should be identical after fork mutation"
        assert len(parent.events) == 3, \
            "Parent should still have only original events"

    def test_multiple_forks_do_not_affect_parent(self, session_manager, parent_with_state):
        """Test that creating multiple forks doesn't affect parent."""
        parent = parent_with_state
        original_state = copy.deepcopy(parent.current_manifest)
        
        # Create multiple forks
        fork1, _ = session_manager.fork_session(parent.session_id, 0)
        fork2, _ = session_manager.fork_session(parent.session_id, 1)
        fork3, _ = session_manager.fork_session(parent.session_id, 2)
        
        # Mutate all forks
        for fork in [fork1, fork2, fork3]:
            session_manager.apply_event(
                fork.session_id,
                SessionEvent(
                    event_index=len(fork.events),
                    event_type=EventType.SET_SEED,
                    payload={"seed": 5555}
                )
            )
        
        # Parent should still be unchanged
        assert parent.current_manifest == original_state, \
            "Parent should be unchanged after multiple fork mutations"


class TestForkRelationshipTracking:
    """Test fork relationship tracking mechanisms."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_fork_records_correct_parent_id(self, session_manager):
        """Test that fork correctly records its parent session ID."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        fork_session, _ = session_manager.fork_session(parent.session_id, 0)
        
        assert fork_session.parent_session_id is not None, \
            "Fork should have a parent session ID"
        assert fork_session.parent_session_id == parent.session_id, \
            "Fork parent ID should match original session"

    def test_fork_records_correct_event_index(self, session_manager):
        """Test that fork correctly records the event index it was created from."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Add events
        for i in range(5):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        fork_index = 3
        fork_session, _ = session_manager.fork_session(parent.session_id, fork_index)
        
        assert fork_session.fork_event_index == fork_index, \
            f"Fork should record event index {fork_index}, got {fork_session.fork_event_index}"

    def test_fork_chain_tracking(self, session_manager):
        """Test tracking when a fork is forked again."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        grandparent = session_manager.create_session(base_manifest)
        
        # Add events to grandparent
        for i in range(4):
            session_manager.apply_event(
                grandparent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Create parent fork
        parent_fork, _ = session_manager.fork_session(grandparent.session_id, 2)
        
        # Add more events to parent fork
        session_manager.apply_event(
            parent_fork.session_id,
            SessionEvent(
                event_index=3,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )
        
        # Create child fork from parent fork
        child_fork, _ = session_manager.fork_session(parent_fork.session_id, 3)
        
        # Verify chain
        assert child_fork.parent_session_id == parent_fork.session_id, \
            "Child fork should reference parent fork as parent"
        assert child_fork.fork_event_index == 3, \
            "Child fork should record correct fork event index"
        assert child_fork.events[3].payload["seed"] == 100, \
            "Child fork should include parent's events"


class TestMultipleForksFromSameParent:
    """Test behavior when multiple forks are created from the same parent."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    @pytest.fixture
    def parent_for_forks(self, session_manager):
        """Create a parent session with multiple events for forking."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Apply 5 events
        seeds = [10, 20, 30, 40, 50]
        for i, seed_value in enumerate(seeds):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": seed_value}
                )
            )
        
        return parent, seeds

    def test_multiple_forks_at_different_points(self, session_manager, parent_for_forks):
        """Test creating multiple forks at different event points."""
        parent, seeds = parent_for_forks
        
        # Create forks at different points
        fork0, _ = session_manager.fork_session(parent.session_id, 0)
        fork2, _ = session_manager.fork_session(parent.session_id, 2)
        fork4, _ = session_manager.fork_session(parent.session_id, 4)
        
        # Verify each fork has correct state
        assert fork0.current_manifest["seed"] == seeds[0], "Fork at 0 should have seed 10"
        assert fork2.current_manifest["seed"] == seeds[2], "Fork at 2 should have seed 30"
        assert fork4.current_manifest["seed"] == seeds[4], "Fork at 4 should have seed 50"

    def test_forks_are_independent(self, session_manager, parent_for_forks):
        """Test that multiple forks from same parent are independent."""
        parent, _ = parent_for_forks
        
        # Create forks
        fork1, _ = session_manager.fork_session(parent.session_id, 1)
        fork2, _ = session_manager.fork_session(parent.session_id, 1)
        
        # Mutate each fork differently
        session_manager.apply_event(
            fork1.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_SEED, payload={"seed": 111})
        )
        session_manager.apply_event(
            fork2.session_id,
            SessionEvent(event_index=2, event_type=EventType.SET_SEED, payload={"seed": 222})
        )
        
        # Forks should have different seeds
        assert fork1.current_manifest["seed"] == 111, "Fork1 should have seed 111"
        assert fork2.current_manifest["seed"] == 222, "Fork2 should have seed 222"

    def test_all_forks_reference_same_parent(self, session_manager, parent_for_forks):
        """Test that all forks correctly reference their common parent."""
        parent, _ = parent_for_forks
        
        # Create multiple forks
        forks = []
        for i in range(3):
            fork, _ = session_manager.fork_session(parent.session_id, i)
            forks.append(fork)
        
        # All forks should reference the same parent
        for fork in forks:
            assert fork.parent_session_id == parent.session_id, \
                "All forks should reference the same parent"

    def test_fork_at_same_point_produces_same_initial_state(self, session_manager, parent_for_forks):
        """Test that forks at the same point have identical initial state."""
        parent, _ = parent_for_forks
        
        # Create forks at the same point
        fork1, _ = session_manager.fork_session(parent.session_id, 3)
        fork2, _ = session_manager.fork_session(parent.session_id, 3)
        
        # Initial states should be identical
        assert fork1.current_manifest == fork2.current_manifest, \
            "Forks at same point should have identical initial state"
        assert fork1.base_manifest == fork2.base_manifest, \
            "Forks should share the same base manifest"
        assert len(fork1.events) == len(fork2.events), \
            "Forks should have same number of events"


class TestForkEdgeCases:
    """Test edge cases in fork functionality."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_fork_from_session_with_events(self, session_manager):
        """Test forking from a session that has events."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Add an event to parent
        session_manager.apply_event(
            parent.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )
        
        fork_session, error = session_manager.fork_session(parent.session_id, 0)
        
        assert fork_session is not None, "Fork from session with events should succeed"
        # Fork at index 0 should have the event at index 0
        assert len(fork_session.events) == 1, "Fork should have 1 event"
        # Seed at event 0 is 100
        assert fork_session.current_manifest["seed"] == 100, \
            "Fork should have the seed from the event"

    def test_fork_nonexistent_session_fails(self, session_manager):
        """Test that forking a nonexistent session fails gracefully."""
        fork_session, error = session_manager.fork_session("nonexistent-id", 0)
        
        assert fork_session is None, "Fork of nonexistent session should fail"
        assert error is not None, "Error message should be provided"

    def test_fork_with_invalid_event_index_negative(self, session_manager):
        """Test that forking with negative event index fails."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        fork_session, error = session_manager.fork_session(parent.session_id, -1)
        
        assert fork_session is None, "Fork with negative index should fail"
        assert "invalid" in error.lower(), "Error should mention invalid index"

    def test_fork_with_invalid_event_index_beyond_length(self, session_manager):
        """Test that forking with index beyond event length fails."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Add some events
        for i in range(3):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        fork_session, error = session_manager.fork_session(parent.session_id, 10)
        
        assert fork_session is None, "Fork with out-of-bounds index should fail"
        assert error is not None, "Error should be provided"

    def test_fork_with_grid_operations_and_effects(self, session_manager):
        """Test forking a session with complex grid operations and effects."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(
            seed=123,
            width=64,
            height=64
        ).with_grid_op("turbulence", octaves=4).with_grid_op("ripple", amplitude=0.5).with_effect(
            "bloom", threshold=0.7
        ).with_effect("vignette", intensity=0.3).build()
        
        parent = session_manager.create_session(base_manifest)
        
        # Add an event
        session_manager.apply_event(
            parent.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 456}
            )
        )
        
        # Fork
        fork_session, _ = session_manager.fork_session(parent.session_id, 0)
        
        # Verify fork has the grid operations and effects
        assert len(fork_session.current_manifest["grid_operations"]) == 2, \
            "Fork should have 2 grid operations"
        assert len(fork_session.current_manifest["effects"]) == 2, \
            "Fork should have 2 effects"
        assert fork_session.current_manifest["seed"] == 456, \
            "Fork should have the updated seed"


class TestForkIntegrity:
    """Test integrity verification for forked sessions."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager for each test."""
        return SessionManager()

    def test_forked_session_passes_integrity_check(self, session_manager):
        """Test that a freshly forked session passes integrity verification."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Add events
        for i in range(3):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Fork
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        
        # Integrity check should pass
        is_valid, errors = session_manager.verify_session_integrity(fork_session.session_id)
        
        assert is_valid, f"Fork should pass integrity check: {errors}"

    def test_forked_session_with_mutation_passes_integrity(self, session_manager):
        """Test that a mutated forked session still passes integrity check."""
        from canopy.manifest import ManifestBuilder
        
        base_manifest = ManifestBuilder(seed=1, width=32, height=32).build()
        parent = session_manager.create_session(base_manifest)
        
        # Add events to parent
        for i in range(3):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 10}
                )
            )
        
        # Fork and mutate
        fork_session, _ = session_manager.fork_session(parent.session_id, 2)
        session_manager.apply_event(
            fork_session.session_id,
            SessionEvent(
                event_index=3,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )
        
        # Integrity check should pass
        is_valid, errors = session_manager.verify_session_integrity(fork_session.session_id)
        
        assert is_valid, f"Mutated fork should pass integrity check: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
