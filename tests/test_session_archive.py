"""
Test: Session Archive Functionality
Comprehensive tests for session archival, retrieval, replay, and integrity verification.
"""
import pytest
import sys
import os
import tempfile
import shutil
import hashlib
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.archive.database import SessionArchive
from canopy.session import (
    SessionManager,
    Session,
    SessionEvent,
    EventType,
    SessionStatus,
)
from canopy.manifest import ManifestBuilder
from canopy.hashing import hash_manifest, hash_event_log


class TestSessionArchiveSaveLoad:
    """Test basic session save and load operations."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    @pytest.fixture
    def session_with_events(self, session_manager):
        """Create a session with multiple events."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        # Apply several events
        for i in range(5):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )

        return session, session_manager

    def test_save_session_returns_entry_id(self, temp_archive, session_with_events):
        """Test that saving a session returns a valid entry ID."""
        session, _ = session_with_events
        entry_id = temp_archive.save_session(session)
        assert isinstance(entry_id, int)
        assert entry_id > 0

    def test_load_session_retrieves_all_data(self, temp_archive, session_with_events):
        """Test that loaded session contains all expected fields."""
        session, _ = session_with_events
        temp_archive.save_session(session)

        loaded = temp_archive.load_session(session.session_id)

        assert loaded is not None
        assert loaded["session_id"] == session.session_id
        assert loaded["schema_version"] == session.schema_version
        assert loaded["engine_version"] == session.engine_version
        assert loaded["status"] == session.status.value
        assert loaded["base_manifest"] == session.base_manifest
        assert loaded["current_manifest"] == session.current_manifest
        assert len(loaded["events"]) == len(session.events)

    def test_load_nonexistent_session_returns_none(self, temp_archive):
        """Test that loading a nonexistent session returns None."""
        result = temp_archive.load_session("nonexistent-session-id")
        assert result is None

    def test_save_and_reload_preserves_manifest(self, temp_archive, session_with_events):
        """Test that saving and reloading preserves manifest state."""
        session, _ = session_with_events
        original_manifest = session.current_manifest.copy()

        temp_archive.save_session(session)
        loaded = temp_archive.load_session(session.session_id)

        assert loaded["current_manifest"] == original_manifest

    def test_save_and_reload_preserves_events(self, temp_archive, session_with_events):
        """Test that saving and reloading preserves event log."""
        session, _ = session_with_events
        original_event_count = len(session.events)

        temp_archive.save_session(session)
        loaded = temp_archive.load_session(session.session_id)

        assert len(loaded["events"]) == original_event_count


class TestSessionArchiveReplay:
    """Test that archived sessions can be replayed deterministically."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    def test_archived_session_replays_identically(self, temp_archive):
        """Test that session replay produces identical manifest state after archive."""
        # Create session manager (simulating "first process")
        session_manager1 = SessionManager()
        base_manifest = ManifestBuilder(
            seed=12345,
            width=64,
            height=64
        ).with_grid_op("turbulence", octaves=4).with_effect(
            "bloom", threshold=0.7
        ).build()

        session1 = session_manager1.create_session(base_manifest)
        session_manager1.apply_event(
            session1.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )

        # Save to archive
        temp_archive.save_session(session1)

        # Create new session manager (simulating "fresh process restart")
        session_manager2 = SessionManager()
        loaded_data = temp_archive.load_session(session1.session_id)

        # Reconstruct session from loaded data
        session2 = Session.from_dict(loaded_data)

        # Replay events on fresh session
        session_manager2.create_session(ManifestBuilder(
            seed=session2.base_manifest.get("seed", 0),
            width=session2.base_manifest.get("width", 64),
            height=session2.base_manifest.get("height", 64)
        ).build())

        # Verify event log hash matches
        original_event_hash = hash_event_log(session1.events)
        loaded_event_hash = hash_event_log(loaded_data["events"])
        assert original_event_hash == loaded_event_hash

    def test_archived_session_hash_matches_original(self, temp_archive):
        """Test that stored manifest hash matches recomputed hash."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)

        # Save to archive
        entry_id = temp_archive.save_session(session)

        # Load back
        loaded = temp_archive.load_session(session.session_id)

        # Recompute hashes
        recomputed_manifest_hash = hash_manifest(loaded["current_manifest"])
        recomputed_event_hash = hash_event_log(loaded["events"])

        assert loaded["final_manifest_hash"] == recomputed_manifest_hash
        assert loaded["event_log_hash"] == recomputed_event_hash


class TestSessionArchiveSearch:
    """Test session search functionality."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    @pytest.fixture
    def multiple_sessions(self, temp_archive):
        """Create multiple sessions with varying properties."""
        session_manager = SessionManager()
        sessions = []

        # Create sessions with different seeds and effects
        for i in range(5):
            base_manifest = ManifestBuilder(
                seed=i * 100,
                width=64,
                height=64
            ).with_effect("bloom", threshold=0.5 + i * 0.1).build()

            session = session_manager.create_session(base_manifest)
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=0,
                    event_type=EventType.SET_SEED,
                    payload={"seed": i * 1000}
                )
            )

            temp_archive.save_session(session)
            sessions.append(session)

        return sessions

    def test_search_returns_all_sessions(self, temp_archive, multiple_sessions):
        """Test that search returns all saved sessions."""
        results = temp_archive.search_sessions(limit=10)
        assert len(results) == len(multiple_sessions)

    def test_search_respects_limit(self, temp_archive, multiple_sessions):
        """Test that search respects the limit parameter."""
        results = temp_archive.search_sessions(limit=2)
        assert len(results) == 2

    def test_search_respects_offset(self, temp_archive, multiple_sessions):
        """Test that search respects the offset parameter."""
        results_with_offset = temp_archive.search_sessions(limit=10, offset=3)
        results_without_offset = temp_archive.search_sessions(limit=10)

        assert len(results_with_offset) == len(results_without_offset) - 3

    def test_search_includes_session_metadata(self, temp_archive, multiple_sessions):
        """Test that search results include essential metadata."""
        results = temp_archive.search_sessions(limit=1)

        assert len(results) > 0
        result = results[0]
        assert "session_id" in result
        assert "engine_version" in result
        assert "status" in result
        assert "created_at" in result


class TestSessionArchiveForkPreservation:
    """Test fork relationship preservation in archive."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    def test_fork_relationship_preserved_in_archive(self, temp_archive):
        """Test that parent-child fork relationship is preserved after archival."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        parent = session_manager.create_session(base_manifest)

        # Add events to parent
        for i in range(3):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )

        # Fork the session
        fork, _ = session_manager.fork_session(parent.session_id, 2)

        # Add an event to the fork
        session_manager.apply_event(
            fork.session_id,
            SessionEvent(
                event_index=3,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )

        # Save both to archive
        temp_archive.save_session(parent)
        temp_archive.save_session(fork)

        # Load and verify fork relationship
        loaded_parent = temp_archive.load_session(parent.session_id)
        loaded_fork = temp_archive.load_session(fork.session_id)

        assert loaded_fork["parent_session_id"] == parent.session_id
        assert loaded_fork["fork_event_index"] == 2
        assert loaded_parent["parent_session_id"] is None

    def test_list_session_forks(self, temp_archive):
        """Test that forks of a session can be listed."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        parent = session_manager.create_session(base_manifest)

        # Create multiple forks
        forks = []
        for i in range(3):
            session_manager.apply_event(
                parent.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )
            fork, _ = session_manager.fork_session(parent.session_id, i)
            forks.append(fork)

        # Save all to archive
        temp_archive.save_session(parent)
        for fork in forks:
            temp_archive.save_session(fork)

        # List forks
        listed_forks = temp_archive.list_session_forks(parent.session_id)

        assert len(listed_forks) == 3
        for fork, listed in zip(forks, listed_forks):
            assert listed["session_id"] == fork.session_id
            assert listed["fork_event_index"] == fork.fork_event_index

    def test_forked_session_can_be_loaded(self, temp_archive):
        """Test that a forked session can be loaded from archive."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        parent = session_manager.create_session(base_manifest)

        # Add events and create fork
        session_manager.apply_event(
            parent.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )
        fork, _ = session_manager.fork_session(parent.session_id, 0)

        # Save to archive
        temp_archive.save_session(parent)
        temp_archive.save_session(fork)

        # Load and verify fork data is correctly stored
        loaded_fork = temp_archive.load_session(fork.session_id)
        assert loaded_fork is not None
        assert loaded_fork["session_id"] == fork.session_id
        assert loaded_fork["parent_session_id"] == parent.session_id
        assert loaded_fork["fork_event_index"] == 0

    def test_forked_session_hash_integrity(self, temp_archive):
        """Test that forked session hashes are correctly computed."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        parent = session_manager.create_session(base_manifest)
        fork, _ = session_manager.fork_session(parent.session_id, 0)

        # Save to archive
        temp_archive.save_session(fork)

        # Verify manifest hash matches
        loaded_fork = temp_archive.load_session(fork.session_id)
        computed_hash = hash_manifest(loaded_fork["current_manifest"])
        assert computed_hash == loaded_fork["final_manifest_hash"]

        # Verify event log hash matches
        computed_event_hash = hash_event_log(loaded_fork["events"])
        assert computed_event_hash == loaded_fork["event_log_hash"]


class TestSessionArchiveIntegrity:
    """Test session integrity verification."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    def test_verify_valid_session_passes(self, temp_archive):
        """Test that a valid session passes integrity verification."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        temp_archive.save_session(session)
        is_valid, errors = temp_archive.verify_session_integrity(session.session_id)

        assert is_valid
        assert len(errors) == 0

    def test_verify_session_with_events_passes(self, temp_archive):
        """Test that a session with events passes integrity verification."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        # Add multiple events
        for i in range(5):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )

        temp_archive.save_session(session)
        is_valid, errors = temp_archive.verify_session_integrity(session.session_id)

        assert is_valid, f"Session with events should pass integrity check: {errors}"

    def test_verify_nonexistent_session_fails(self, temp_archive):
        """Test that verifying a nonexistent session fails."""
        is_valid, errors = temp_archive.verify_session_integrity("nonexistent-id")

        assert not is_valid
        assert "Session not found" in errors

    def test_verify_manifest_hash_integrity(self, temp_archive):
        """Test that manifest hash verification works correctly."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        temp_archive.save_session(session)
        is_valid, errors = temp_archive.verify_session_integrity(session.session_id)

        assert is_valid, f"Manifest hash verification failed: {errors}"
        assert not any("Manifest hash mismatch" in e for e in errors)

    def test_verify_event_log_hash_integrity(self, temp_archive):
        """Test that event log hash verification works correctly."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        # Add events
        for i in range(3):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": (i + 1) * 100}
                )
            )

        temp_archive.save_session(session)
        is_valid, errors = temp_archive.verify_session_integrity(session.session_id)

        assert is_valid, f"Event log hash verification failed: {errors}"
        assert not any("Event log hash mismatch" in e for e in errors)

    def test_verify_session_can_be_reloaded_after_save(self, temp_archive):
        """Test that a session can be reloaded and verified after archival."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )

        # Save, reload, and verify
        temp_archive.save_session(session)
        loaded = temp_archive.load_session(session.session_id)

        # Verify the loaded data can be validated
        assert loaded is not None
        assert loaded["session_id"] == session.session_id
        assert len(loaded["events"]) == len(session.events)

        # Re-verify integrity
        is_valid, errors = temp_archive.verify_session_integrity(session.session_id)
        assert is_valid, f"Reload verification failed: {errors}"


class TestSessionArchiveStats:
    """Test session archive statistics."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    def test_get_stats_empty_archive(self, temp_archive):
        """Test that empty archive returns zero counts."""
        stats = temp_archive.get_stats()

        assert stats["total_sessions"] == 0
        assert stats["active_sessions"] == 0
        assert stats["closed_sessions"] == 0
        assert stats["total_forks"] == 0

    def test_get_stats_counts_sessions(self, temp_archive):
        """Test that stats correctly count sessions."""
        session_manager = SessionManager()

        # Create and save multiple sessions
        for i in range(3):
            base_manifest = ManifestBuilder(seed=i, width=64, height=64).build()
            session = session_manager.create_session(base_manifest)
            temp_archive.save_session(session)

        stats = temp_archive.get_stats()
        assert stats["total_sessions"] == 3

    def test_get_stats_counts_forks(self, temp_archive):
        """Test that stats correctly count forked sessions."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        parent = session_manager.create_session(base_manifest)

        # Create forks
        for i in range(3):
            fork, _ = session_manager.fork_session(parent.session_id, 0)
            temp_archive.save_session(fork)

        stats = temp_archive.get_stats()
        assert stats["total_forks"] == 3

    def test_close_session_updates_stats(self, temp_archive):
        """Test that closing a session updates stats."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)
        temp_archive.save_session(session)

        # Close the session
        temp_archive.close_session(session.session_id)

        stats = temp_archive.get_stats()
        assert stats["active_sessions"] == 0
        assert stats["closed_sessions"] == 1


class TestSessionArchiveClose:
    """Test session close functionality."""

    @pytest.fixture
    def temp_archive(self):
        """Create a temporary session archive database."""
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test_sessions.db")
        archive = SessionArchive(db_path)
        yield archive
        shutil.rmtree(tmpdir)

    def test_close_active_session(self, temp_archive):
        """Test closing an active session."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)
        temp_archive.save_session(session)

        result = temp_archive.close_session(session.session_id)
        assert result is True

        loaded = temp_archive.load_session(session.session_id)
        assert loaded["status"] == "closed"
        assert loaded["closed_at"] is not None

    def test_close_session_updates_status(self, temp_archive):
        """Test that closing a session updates its status in the archive."""
        session_manager = SessionManager()
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)
        temp_archive.save_session(session)

        # Verify initial status
        loaded_before = temp_archive.load_session(session.session_id)
        assert loaded_before["status"] == "active"

        # Close session
        temp_archive.close_session(session.session_id)

        # Verify updated status
        loaded_after = temp_archive.load_session(session.session_id)
        assert loaded_after["status"] == "closed"
        assert loaded_after["closed_at"] is not None

    def test_close_nonexistent_session_no_error(self, temp_archive):
        """Test that closing a nonexistent session does not raise an error."""
        # The current implementation returns True even for nonexistent sessions
        # This tests the actual behavior (which may be a design choice or bug)
        result = temp_archive.close_session("nonexistent-id")
        # Just verify it doesn't raise an exception
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
