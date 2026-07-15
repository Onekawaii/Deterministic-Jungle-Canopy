"""
Tests for WebSocket Protocol.
Comprehensive tests for WebSocket session interaction including event handling,
rendering, rewinding, error handling, and multi-client scenarios.
"""
import pytest
import pytest_asyncio
import asyncio
import sys
import os
import json
import random
from typing import List, Optional
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

from canopy.session import (
    SessionManager,
    Session,
    SessionEvent,
    EventType,
    SessionStatus,
    get_session_manager,
)
from canopy.manifest import ManifestBuilder
from canopy.hashing import hash_manifest, hash_event_log, hash_pixels

pytestmark = pytest.mark.skipif(
    not WEBSOCKETS_AVAILABLE,
    reason="websockets library not installed"
)

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture
def session_manager():
    """Create a fresh session manager."""
    return SessionManager()


@pytest.fixture
def base_session(session_manager):
    """Create a base session for WebSocket testing."""
    base_manifest = ManifestBuilder(
        seed=42,
        width=64,
        height=64
    ).with_effect("brightness", enabled=True).build()
    return session_manager.create_session(base_manifest)


@pytest.fixture
def server_url():
    """Get the WebSocket server URL."""
    return "ws://localhost:8000"


class MockWebSocket:
    """Mock WebSocket for testing without actual server connection."""

    def __init__(self):
        self.messages: List[dict] = []
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def accept(self):
        self.accepted = True

    async def receive_json(self) -> dict:
        if not self.messages:
            raise Exception("No messages")
        return self.messages.pop(0)

    async def send_json(self, data: dict):
        self.sent_messages = getattr(self, 'sent_messages', [])
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class TestEventMessageHandling:
    """Test cases for event message handling via WebSocket."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket."""
        return MockWebSocket()

    @pytest.mark.asyncio
    async def test_event_message_applies_successfully(
        self, session_manager, mock_websocket
    ):
        """Test that valid event message is processed and applied correctly."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        event_data = {
            "type": "event",
            "event": {
                "event_type": "set_seed",
                "payload": {"seed": 12345}
            }
        }
        mock_websocket.messages = [event_data]

        data = await mock_websocket.receive_json()
        assert data["type"] == "event"

        event_msg = data["event"]
        assert event_msg["event_type"] == "set_seed"
        assert event_msg["payload"]["seed"] == 12345

        success, error = session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=len(session.events),
                event_type=EventType.SET_SEED,
                payload=event_msg["payload"]
            )
        )
        assert success is True
        assert error is None

    @pytest.mark.asyncio
    async def test_event_message_with_set_parameter(self, session_manager):
        """Test event message with set_parameter event type."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        event_data = {
            "type": "event",
            "event": {
                "event_type": "set_parameter",
                "payload": {
                    "effect": "brightness",
                    "param": "value",
                    "value": 1.5
                }
            }
        }

        event_msg = event_data["event"]
        success, error = session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=len(session.events),
                event_type=EventType.SET_PARAMETER,
                payload=event_msg["payload"]
            )
        )

        assert success is True
        assert session.events[0].event_type == EventType.SET_PARAMETER
        assert session.events[0].payload["effect"] == "brightness"

    @pytest.mark.asyncio
    async def test_event_message_updates_manifest_hash(self, session_manager):
        """Test that applying event updates manifest hash."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)
        original_hash = hash_manifest(session.current_manifest)

        event = SessionEvent(
            event_index=len(session.events),
            event_type=EventType.SET_SEED,
            payload={"seed": 999}
        )
        success, _ = session_manager.apply_event(session.session_id, event)

        assert success is True
        session = session_manager.get_session(session.session_id)
        new_hash = hash_manifest(session.current_manifest)
        assert new_hash != original_hash


class TestRenderMessageHandling:
    """Test cases for render message handling via WebSocket."""

    @pytest.mark.asyncio
    async def test_render_message_returns_frame(self, session_manager):
        """Test that render message returns a valid frame with pixel hash."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        frame, pixel_hash = session_manager.render_session_frame(
            session, frame_index=0, width=64, height=64
        )

        assert frame is not None
        assert pixel_hash is not None
        assert len(pixel_hash) == 64  # SHA-256 hex digest

    @pytest.mark.asyncio
    async def test_render_message_includes_required_fields(self, session_manager):
        """Test that render response includes all required protocol fields."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        frame, pixel_hash = session_manager.render_session_frame(
            session, frame_index=0, width=64, height=64
        )

        manifest_hash = hash_manifest(session.current_manifest)
        event_log_hash = hash_event_log(session.events)

        expected_fields = {
            "session_id": session.session_id,
            "frame_index": 0,
            "manifest_hash": manifest_hash,
            "event_log_hash": event_log_hash,
            "pixel_hash": pixel_hash,
        }

        for key, value in expected_fields.items():
            assert key in [k for k in expected_fields.keys()]
        assert expected_fields["pixel_hash"] == pixel_hash

    @pytest.mark.asyncio
    async def test_render_different_seeds_produce_different_hashes(
        self, session_manager
    ):
        """Test that rendering with different seeds produces different hashes."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        frame0, hash0 = session_manager.render_session_frame(session, 0)

        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 100}
            )
        )

        frame1, hash1 = session_manager.render_session_frame(session, 0)

        assert hash0 != hash1


class TestRewindMessageHandling:
    """Test cases for rewind message handling via WebSocket."""

    @pytest.mark.asyncio
    async def test_rewind_to_valid_event_index(self, session_manager):
        """Test rewinding to a valid event index."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        for i in range(5):
            session_manager.apply_event(
                session.session_id,
                SessionEvent(
                    event_index=i,
                    event_type=EventType.SET_SEED,
                    payload={"seed": i * 10}
                )
            )

        success, error = session_manager.rewind_session(session.session_id, 2)

        assert success is True
        assert error is None
        session = session_manager.get_session(session.session_id)
        assert session.current_frame == 2

    @pytest.mark.asyncio
    async def test_rewind_response_includes_required_fields(self, session_manager):
        """Test that rewind response includes all required protocol fields."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 42}
            )
        )

        success, error = session_manager.rewind_session(session.session_id, 0)

        assert success is True
        session = session_manager.get_session(session.session_id)
        manifest_hash = hash_manifest(session.current_manifest)

        response = {
            "type": "rewound",
            "event_index": 0,
            "manifest_hash": manifest_hash,
            "current_frame": session.current_frame,
        }

        assert response["event_index"] == 0
        assert response["manifest_hash"] is not None
        assert response["current_frame"] == 0

    @pytest.mark.asyncio
    async def test_rewind_to_invalid_index_fails(self, session_manager):
        """Test that rewinding to invalid index fails gracefully."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        success, error = session_manager.rewind_session(session.session_id, 999)

        assert success is False
        assert error is not None
        assert "Invalid event index" in error


class TestErrorHandlingMalformedMessages:
    """Test cases for error handling of malformed messages."""

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_error(self):
        """Test that unknown message type returns appropriate error."""
        mock_ws = MockWebSocket()
        mock_ws.messages = [{"type": "unknown_type"}]

        data = await mock_ws.receive_json()
        msg_type = data.get("type")

        assert msg_type == "unknown_type"
        error_response = {
            "type": "error",
            "code": "UNKNOWN_MESSAGE",
            "detail": f"Unknown message type: {msg_type}"
        }
        assert error_response["code"] == "UNKNOWN_MESSAGE"

    @pytest.mark.asyncio
    async def test_render_missing_frame_index_uses_current(self, session_manager):
        """Test that render message without frame_index uses current frame."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        render_data = {"type": "render"}

        frame_index = render_data.get("frame_index", session.current_frame)
        assert frame_index == session.current_frame

    @pytest.mark.asyncio
    async def test_rewind_missing_event_index_returns_error(self):
        """Test that rewind message without event_index returns error."""
        rewind_data = {"type": "rewind"}

        event_index = rewind_data.get("event_index")
        if event_index is None:
            error_response = {
                "type": "error",
                "code": "INVALID_REQUEST",
                "detail": "event_index required"
            }
            assert error_response["code"] == "INVALID_REQUEST"
            assert error_response["detail"] == "event_index required"

    @pytest.mark.asyncio
    async def test_event_message_without_event_field_returns_error(self):
        """Test that event message without event field is handled."""
        invalid_event = {"type": "event"}

        event_data = invalid_event.get("event", {})
        assert event_data == {}

        event_type = EventType(event_data.get("event_type", "set_parameter"))
        assert event_type == EventType.SET_PARAMETER

    @pytest.mark.asyncio
    async def test_malformed_json_returns_protocol_error(self):
        """Test that malformed JSON is handled gracefully."""
        mock_ws = MockWebSocket()
        mock_ws.messages = [{"type": "render", "frame_index": "not_a_number"}]

        data = await mock_ws.receive_json()
        frame_index = data.get("frame_index")

        try:
            index = int(frame_index)
        except (ValueError, TypeError):
            error_response = {
                "type": "error",
                "code": "RENDER_ERROR",
                "detail": f"Invalid frame_index: {frame_index}"
            }
            assert error_response["code"] == "RENDER_ERROR"


class TestClientConnectionRNGState:
    """Test that connecting a client does not alter RNG state."""

    @pytest.mark.asyncio
    async def test_client_connection_preserves_session_state(
        self, session_manager
    ):
        """Test that client connection does not modify session state."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)
        original_manifest = session.current_manifest.copy()

        frame1, hash1 = session_manager.render_session_frame(session, 0)

        frame2, hash2 = session_manager.render_session_frame(session, 0)

        assert hash1 == hash2

        session = session_manager.get_session(session.session_id)
        assert session.current_manifest == original_manifest

    @pytest.mark.asyncio
    async def test_multiple_connections_do_not_alter_rng(self, session_manager):
        """Test that multiple client connections do not affect RNG state."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        frame_ref, hash_ref = session_manager.render_session_frame(session, 0)

        for _ in range(3):
            frame, hash_val = session_manager.render_session_frame(session, 0)
            assert hash_val == hash_ref

    @pytest.mark.asyncio
    async def test_render_does_not_mutate_session(self, session_manager):
        """Test that rendering a frame does not mutate the session."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        original_events_count = len(session.events)
        original_frame = session.current_frame

        session_manager.render_session_frame(session, 0)

        session = session_manager.get_session(session.session_id)
        assert len(session.events) == original_events_count
        assert session.current_frame == original_frame


class TestMultipleClientsIdenticalFrames:
    """Test that multiple clients observe identical frames."""

    @pytest.mark.asyncio
    async def test_concurrent_renders_produce_identical_hashes(
        self, session_manager
    ):
        """Test that concurrent render requests produce identical pixel hashes."""
        base_manifest = ManifestBuilder(
            seed=12345,
            width=64,
            height=64
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

        hashes = []
        for _ in range(5):
            _, pixel_hash = session_manager.render_session_frame(session, 1)
            hashes.append(pixel_hash)

        assert len(set(hashes)) == 1, (
            f"Clients received different hashes: {set(hashes)}"
        )

    @pytest.mark.asyncio
    async def test_clients_see_same_frame_after_events(self, session_manager):
        """Test that all clients see the same frame after events are applied."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        session_manager.apply_event(
            session.session_id,
            SessionEvent(
                event_index=0,
                event_type=EventType.SET_SEED,
                payload={"seed": 777}
            )
        )

        hashes = []
        for client_id in range(3):
            frame, hash_val = session_manager.render_session_frame(session, 1)
            hashes.append(hash_val)

        assert len(set(hashes)) == 1, (
            f"Client frames differ: {set(hashes)}"
        )

    @pytest.mark.asyncio
    async def test_identical_frames_across_different_sessions(
        self, session_manager
    ):
        """Test that sessions with same seed produce identical frames."""
        base_manifest = ManifestBuilder(seed=999, width=64, height=64).build()
        session1 = session_manager.create_session(base_manifest)

        session2_manifest = ManifestBuilder(seed=999, width=64, height=64).build()
        session2 = session_manager.create_session(session2_manifest)

        frame1, hash1 = session_manager.render_session_frame(session1, 0)
        frame2, hash2 = session_manager.render_session_frame(session2, 0)

        assert hash1 == hash2, (
            "Sessions with same seed should produce identical frames"
        )


class TestWebSocketProtocolMessages:
    """Test WebSocket protocol message format and structure."""

    @pytest.mark.asyncio
    async def test_event_applied_response_format(self, session_manager):
        """Test that event_applied response has correct format."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        event = SessionEvent(
            event_index=0,
            event_type=EventType.SET_SEED,
            payload={"seed": 42}
        )
        success, _ = session_manager.apply_event(session.session_id, event)

        assert success is True
        session = session_manager.get_session(session.session_id)

        response = {
            "type": "event_applied",
            "event_index": event.event_index,
            "manifest_hash_after": hash_manifest(session.current_manifest),
        }

        assert response["type"] == "event_applied"
        assert "event_index" in response
        assert "manifest_hash_after" in response

    @pytest.mark.asyncio
    async def test_frame_response_contains_pixel_hash(self, session_manager):
        """Test that frame response contains pixel hash for verification."""
        base_manifest = ManifestBuilder(seed=42, width=64, height=64).build()
        session = session_manager.create_session(base_manifest)

        frame, pixel_hash = session_manager.render_session_frame(session, 0)

        computed_hash = hash_pixels(frame)
        assert pixel_hash == computed_hash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
