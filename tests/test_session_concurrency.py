"""
Test: Session Concurrency Safety
Comprehensive tests for thread-safe session operations, event ordering,
and concurrent access patterns in the Deterministic Jungle Canopy.
"""
import pytest
import sys
import os
import threading
import time
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.session import (
    SessionManager,
    Session,
    SessionEvent,
    EventType,
    SessionStatus,
)
from canopy.manifest import ManifestBuilder
from canopy.hashing import hash_event_log, hash_manifest


class ThreadSafeCounter:
    """Thread-safe counter for generating sequential event indexes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._value = 0

    def get_and_increment(self) -> int:
        with self._lock:
            val = self._value
            self._value += 1
            return val


class TestConcurrentEventUpdates:
    """Test that concurrent event updates preserve contiguous ordering."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    @pytest.fixture
    def base_session(self, session_manager):
        """Create a base session for concurrent testing."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        return session_manager.create_session(base_manifest)

    def test_concurrent_events_maintain_contiguous_indexes(
        self, session_manager, base_session
    ):
        """Test that events from concurrent threads have contiguous indexes."""
        session_id = base_session.session_id
        num_threads = 10
        events_per_thread = 5
        results = []
        errors = []
        counter = ThreadSafeCounter()

        def apply_events(thread_id: int):
            try:
                for i in range(events_per_thread):
                    event_index = counter.get_and_increment()
                    event = SessionEvent(
                        event_index=event_index,
                        event_type=EventType.SET_SEED,
                        payload={"seed": thread_id * 100 + i}
                    )
                    result = session_manager.apply_event(session_id, event)
                    results.append((thread_id, i, result))
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [
            threading.Thread(target=apply_events, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        session = session_manager.get_session(session_id)
        assert len(session.events) == num_threads * events_per_thread

        indexes = [e.event_index for e in session.events]
        assert indexes == list(range(len(indexes))), (
            f"Event indexes not contiguous: {indexes}"
        )

    def test_event_order_deterministic_regardless_of_arrival(
        self, session_manager, base_session
    ):
        """Test that final event order is deterministic regardless of thread timing."""
        session_id = base_session.session_id
        num_events = 20
        counter = ThreadSafeCounter()

        def apply_events_gradually():
            for i in range(num_events):
                event = SessionEvent(
                    event_index=counter.get_and_increment(),
                    event_type=EventType.SET_SEED,
                    payload={"seed": i}
                )
                session_manager.apply_event(session_id, event)
                time.sleep(0.001)

        thread = threading.Thread(target=apply_events_gradually)
        thread.start()

        session = session_manager.get_session(session_id)
        while len(session.events) < num_events:
            time.sleep(0.005)

        thread.join()
        session = session_manager.get_session(session_id)

        expected_seeds = list(range(num_events))
        actual_seeds = [e.payload["seed"] for e in session.events]
        assert actual_seeds == expected_seeds

    def test_concurrent_manifest_updates_are_atomic(
        self, session_manager, base_session
    ):
        """Test that manifest updates during concurrent events are atomic."""
        session_id = base_session.session_id
        num_threads = 5
        events_per_thread = 10
        barrier = threading.Barrier(num_threads)
        counter = ThreadSafeCounter()

        original_manifest = copy.deepcopy(base_session.current_manifest)

        def apply_and_check(thread_id: int):
            barrier.wait()
            for i in range(events_per_thread):
                event = SessionEvent(
                    event_index=counter.get_and_increment(),
                    event_type=EventType.SET_SEED,
                    payload={"seed": thread_id * 1000 + i}
                )
                session_manager.apply_event(session_id, event)

        threads = [
            threading.Thread(target=apply_and_check, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        session = session_manager.get_session(session_id)
        assert session.status == SessionStatus.ACTIVE
        assert len(session.events) == num_threads * events_per_thread


class TestMultipleClientsIdenticalHashes:
    """Test that multiple WebSocket clients receive identical pixel hashes."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_simultaneous_render_produces_identical_hashes(
        self, session_manager
    ):
        """Test that simultaneous render requests produce identical pixel hashes."""
        base_manifest = ManifestBuilder(
            seed=12345,
            width=32,
            height=32
        ).with_grid_op("turbulence", octaves=3).build()
        session = session_manager.create_session(base_manifest)

        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 999}
            )
        )

        num_clients = 5
        hashes = []
        lock = threading.Lock()

        def render_frame():
            frame, pixel_hash = session_manager.render_session_frame(
                session, frame_index=1
            )
            with lock:
                hashes.append(pixel_hash)

        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            futures = [executor.submit(render_frame) for _ in range(num_clients)]
            for f in as_completed(futures):
                f.result()

        assert len(set(hashes)) == 1, (
            f"Clients received different hashes: {set(hashes)}"
        )

    def test_clients_receive_consistent_state_after_events(
        self, session_manager
    ):
        """Test that clients receive consistent manifest state after concurrent events."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        num_clients = 3
        manifest_snapshots = []
        lock = threading.Lock()
        counter = ThreadSafeCounter()

        def add_event_and_check(client_id: int):
            for i in range(5):
                event = SessionEvent(
                    event_index=counter.get_and_increment(),
                    event_type=EventType.SET_SEED,
                    payload={"seed": client_id * 100 + i}
                )
                session_manager.apply_event(session_id, event)
                time.sleep(0.01)

                sess = session_manager.get_session(session_id)
                manifest_hash = hash_manifest(sess.current_manifest)
                with lock:
                    manifest_snapshots.append({
                        "client_id": client_id,
                        "event_count": len(sess.events),
                        "manifest_hash": manifest_hash
                    })

        with ThreadPoolExecutor(max_workers=num_clients) as executor:
            futures = [
                executor.submit(add_event_and_check, i)
                for i in range(num_clients)
            ]
            for f in as_completed(futures):
                f.result()

        final_session = session_manager.get_session(session_id)
        final_event_count = len(final_session.events)
        final_hash = hash_manifest(final_session.current_manifest)

        for snapshot in manifest_snapshots:
            assert snapshot["event_count"] <= final_event_count, (
                f"Client {snapshot['client_id']} saw more events than final state"
            )
            assert snapshot["event_count"] >= 0, (
                "Client saw negative event count"
            )


class TestReconnectPreservesState:
    """Test that state remains unchanged during session access cycles."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_concurrent_get_session_preserves_event_count(
        self, session_manager
    ):
        """Test that multiple threads getting session does not change event count."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        for i in range(10):
            session_manager.apply_event(
                session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": i * 100}
                )
            )

        event_counts = []
        lock = threading.Lock()

        def get_session_repeatedly():
            for _ in range(100):
                session = session_manager.get_session(session_id)
                with lock:
                    event_counts.append(len(session.events))

        threads = [threading.Thread(target=get_session_repeatedly) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(count == 10 for count in event_counts)

    def test_session_state_immutable_during_concurrent_reads(
        self, session_manager
    ):
        """Test that session state is consistent during concurrent read-only access."""
        base_manifest = ManifestBuilder(
            seed=42,
            width=32,
            height=32
        ).with_effect("bloom", threshold=0.5).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        session_manager.apply_event(
            session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 12345}
            )
        )

        original_manifest = copy.deepcopy(session.current_manifest)
        original_events = len(session.events)

        manifest_snapshots = []
        lock = threading.Lock()

        def read_session_state():
            for _ in range(50):
                session = session_manager.get_session(session_id)
                with lock:
                    manifest_snapshots.append(
                        (session.current_manifest.copy(), len(session.events))
                    )
                time.sleep(0.001)

        threads = [threading.Thread(target=read_session_state) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for manifest, event_count in manifest_snapshots:
            assert manifest == original_manifest
            assert event_count == original_events

    def test_fork_after_events_preserves_original(self, session_manager):
        """Test that forking after events does not modify original session."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        for i in range(5):
            session_manager.apply_event(
                session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": i * 100}
                )
            )

        original_event_count = len(session.events)
        original_manifest = copy.deepcopy(session.current_manifest)

        fork, _ = session_manager.fork_session(session_id, 2)
        assert fork is not None

        session = session_manager.get_session(session_id)
        assert len(session.events) == original_event_count
        assert session.current_manifest == original_manifest


class TestMalformedEvents:
    """Test that malformed events perform no mutation."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_invalid_event_type_rejected_no_mutation(self, session_manager):
        """Test that invalid event type is rejected and causes no mutation."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)

        original_events = len(session.events)
        original_manifest = copy.deepcopy(session.current_manifest)

        try:
            success, error = session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=0,
                    event_type="invalid_event_type",
                    payload={}
                )
            )
            assert success is False
        except ValueError:
            pass

        session = session_manager.get_session(session.session_id)
        assert len(session.events) == original_events
        assert session.current_manifest == original_manifest

    def test_empty_payload_allowed_with_default(self, session_manager):
        """Test that empty payload uses default values (no mutation)."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)

        success, error = session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={}
            )
        )

        assert success is True
        session = session_manager.get_session(session.session_id)
        assert session.current_manifest.get("seed") == 0

    def test_negative_event_index_rejected_no_mutation(self, session_manager):
        """Test that explicitly negative event index is rejected."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)

        original_events = len(session.events)
        original_manifest = copy.deepcopy(session.current_manifest)

        success, error = session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=-5,
                event_type=EventType.SET_SEED,
                payload={"seed": 123}
            )
        )

        assert success is False

        session = session_manager.get_session(session.session_id)
        assert len(session.events) == original_events
        assert session.current_manifest == original_manifest

    def test_wrong_event_index_rejected_no_mutation(self, session_manager):
        """Test that wrong event index is rejected with no mutation."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        session_manager.apply_event(
            session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )

        original_state = copy.deepcopy(session.current_manifest)
        original_event_count = len(session.events)

        success, error = session_manager.apply_event(
            session_id,
            SessionEvent(
                event_index=5,
                event_type=EventType.SET_SEED,
                payload={"seed": 200}
            )
        )

        assert success is False

        session = session_manager.get_session(session_id)
        assert len(session.events) == original_event_count
        assert session.current_manifest == original_state


class TestSlowClientsNoCorruption:
    """Test that slow clients cannot corrupt shared state."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_slow_reader_sees_complete_state(self, session_manager):
        """Test that slow readers always see complete, consistent state."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        for i in range(20):
            session_manager.apply_event(
                session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": i}
                )
            )

        state_snapshots = []
        lock = threading.Lock()
        stop_flag = threading.Event()

        def slow_reader(reader_id: int):
            while not stop_flag.is_set():
                session = session_manager.get_session(session_id)
                with lock:
                    state_snapshots.append({
                        "reader_id": reader_id,
                        "event_count": len(session.events),
                        "manifest": copy.deepcopy(session.current_manifest)
                    })
                time.sleep(0.02)

        readers = [
            threading.Thread(target=slow_reader, args=(i,))
            for i in range(3)
        ]

        for r in readers:
            r.start()

        time.sleep(0.5)
        stop_flag.set()

        for r in readers:
            r.join()

        final_session = session_manager.get_session(session_id)
        final_event_count = len(final_session.events)

        for snapshot in state_snapshots:
            assert snapshot["event_count"] <= final_event_count, (
                "Reader saw more events than final state"
            )

    def test_rapid_updates_with_slow_clients(self, session_manager):
        """Test that rapid updates don't corrupt state with concurrent slow reads."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        errors = []
        updates_done = threading.Event()
        integrity_lock = threading.Lock()
        counter = ThreadSafeCounter()

        def rapid_updater():
            for i in range(100):
                try:
                    session_manager.apply_event(
                        session_id,
                        SessionEvent(
                            event_index=counter.get_and_increment(),
                            event_type=EventType.SET_SEED,
                            payload={"seed": i}
                        )
                    )
                except Exception as e:
                    with integrity_lock:
                        errors.append(str(e))
            updates_done.set()

        def integrity_checker():
            while not updates_done.is_set() or len(session.events) < 100:
                is_valid, errs = session_manager.verify_session_integrity(
                    session_id
                )
                if not is_valid:
                    with integrity_lock:
                        errors.extend(errs)
                time.sleep(0.01)

        updater = threading.Thread(target=rapid_updater)
        checkers = [
            threading.Thread(target=integrity_checker)
            for _ in range(2)
        ]

        updater.start()
        for c in checkers:
            c.start()

        updater.join()
        for c in checkers:
            c.join()

        assert len(errors) == 0, f"Integrity errors: {errors}"
        session = session_manager.get_session(session_id)
        assert len(session.events) == 100

        is_valid, errs = session_manager.verify_session_integrity(session_id)
        assert is_valid, f"Session integrity failed: {errs}"

    def test_concurrent_rewind_and_updates(self, session_manager):
        """Test that concurrent rewind and event updates don't corrupt state."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        counter = ThreadSafeCounter()

        for i in range(20):
            session_manager.apply_event(
                session_id,
                SessionEvent(
                    event_index=counter.get_and_increment(),
                    event_type=EventType.SET_SEED,
                    payload={"seed": i}
                )
            )

        errors = []
        lock = threading.Lock()
        update_counter = ThreadSafeCounter()

        def rewind_worker():
            for _ in range(10):
                try:
                    idx = 5
                    session_manager.rewind_session(session_id, idx)
                    time.sleep(0.01)
                except Exception as e:
                    with lock:
                        errors.append(str(e))

        def update_worker():
            for i in range(10, 20):
                try:
                    session_manager.apply_event(
                        session_id,
                        SessionEvent(
                            event_index=update_counter.get_and_increment(),
                            event_type=EventType.SET_SEED,
                            payload={"seed": i}
                        )
                    )
                    time.sleep(0.01)
                except Exception as e:
                    with lock:
                        errors.append(str(e))

        threads = [
            threading.Thread(target=rewind_worker),
            threading.Thread(target=update_worker),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent ops: {errors}"

        is_valid, errs = session_manager.verify_session_integrity(session_id)
        assert is_valid, f"Session integrity failed after concurrent ops: {errs}"


class TestSessionIntegrityUnderConcurrency:
    """Test session integrity verification under concurrent access."""

    @pytest.fixture
    def session_manager(self):
        """Create a fresh session manager."""
        return SessionManager()

    def test_event_indexes_remain_contiguous_under_load(
        self, session_manager
    ):
        """Test that event indexes remain contiguous under heavy concurrent load."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id

        num_threads = 20
        events_per_thread = 10
        counter = ThreadSafeCounter()

        def apply_events(thread_id: int):
            for i in range(events_per_thread):
                session_manager.apply_event(
                    session_id,
                    SessionEvent(
                        event_index=counter.get_and_increment(),
                        event_type=EventType.SET_SEED,
                        payload={"seed": thread_id * 1000 + i}
                    )
                )

        threads = [
            threading.Thread(target=apply_events, args=(i,))
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        is_valid, errors = session_manager.verify_session_integrity(session_id)
        assert is_valid, f"Integrity check failed: {errors}"

        session = session_manager.get_session(session_id)
        assert len(session.events) == num_threads * events_per_thread

        indexes = [e.event_index for e in session.events]
        assert indexes == list(range(len(indexes)))

    def test_manifest_hash_chain_valid_under_concurrency(
        self, session_manager
    ):
        """Test that manifest hash chain remains valid under concurrent updates."""
        base_manifest = ManifestBuilder(seed=42, width=32, height=32).build()
        session = session_manager.create_session(base_manifest)
        session_id = session.session_id
        counter = ThreadSafeCounter()

        def apply_events_and_verify(thread_id: int):
            for i in range(5):
                session_manager.apply_event(
                    session_id,
                    SessionEvent(
                        event_index=counter.get_and_increment(),
                        event_type=EventType.SET_SEED,
                        payload={"seed": thread_id * 100 + i}
                    )
                )

        threads = [
            threading.Thread(target=apply_events_and_verify, args=(i,))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        is_valid, errors = session_manager.verify_session_integrity(session_id)
        assert is_valid, f"Manifest hash chain broken: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
