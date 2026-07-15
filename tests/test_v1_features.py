"""
Tests for v1.0.0 Features
"""
import pytest
import json
from canopy.schema import (
    validate_manifest, validate_event, validate_session, validate_timeline,
    migrate_from_v1_to_v2, SchemaError
)
from canopy.timeline import Timeline, Track, Interpolation, Keyframe
from canopy.comparison import compare_sessions, compare_events, compare_manifests
from canopy.storage.models import StoredSession, StoredEvent, SessionStatus
from canopy.errors import (
    ErrorCode, ErrorDetail, InvalidRequestError, SessionNotFoundError,
    SessionConflictError
)
from canopy.security import validate_import_payload, sanitize_zip_path, ExportBundle


class TestSchemaV2:
    """Test schema v2.0 validation."""
    
    def test_valid_manifest_v2(self):
        manifest = {
            "schema_version": "2.0",
            "seed": 42,
            "width": 256,
            "height": 256,
        }
        validate_manifest(manifest)  # Should not raise
    
    def test_manifest_rejects_nan(self):
        manifest = {
            "schema_version": "2.0",
            "seed": 42,
            "effects": {"bloom": {"threshold": float('nan')}}
        }
        with pytest.raises(SchemaError):
            validate_manifest(manifest)
    
    def test_manifest_rejects_infinity(self):
        manifest = {
            "schema_version": "2.0", 
            "seed": 42,
            "effects": {"bloom": {"threshold": float('inf')}}
        }
        with pytest.raises(SchemaError):
            validate_manifest(manifest)
    
    def test_event_requires_index(self):
        event = {"event_type": "set_effect", "payload": {}}
        with pytest.raises(SchemaError):
            validate_event(event)
    
    def test_event_requires_type(self):
        event = {"event_index": 0, "payload": {}}
        with pytest.raises(SchemaError):
            validate_event(event)
    
    def test_valid_event_v2(self):
        event = {
            "event_index": 0,
            "event_type": "set_effect",
            "payload": {"effect": "bloom"}
        }
        validate_event(event)  # Should not raise


class TestTimeline:
    """Test timeline system."""
    
    def test_create_timeline(self):
        timeline = Timeline(duration_frames=240, fps=30)
        assert timeline.duration_frames == 240
        assert timeline.fps == 30
        assert len(timeline.tracks) == 0
    
    def test_add_track(self):
        timeline = Timeline()
        track = Track(track_id="test", target="effects.glitch.intensity")
        timeline.add_track(track)
        assert len(timeline.tracks) == 1
    
    def test_evaluate_linear_interpolation(self):
        timeline = Timeline()
        track = Track(
            track_id="test",
            target="effects.glitch.intensity",
            interpolation=Interpolation.LINEAR
        )
        track.add_keyframe(0, 0.0)
        track.add_keyframe(10, 1.0)
        timeline.add_track(track)
        
        # Test interpolation at frame 5
        result = timeline.evaluate_frame(5)
        assert "effects.glitch.intensity" in result
        assert abs(result["effects.glitch.intensity"] - 0.5) < 0.01
    
    def test_evaluate_step_interpolation(self):
        timeline = Timeline()
        track = Track(
            track_id="test",
            target="test.value",
            interpolation=Interpolation.STEP
        )
        track.add_keyframe(0, 0.0)
        track.add_keyframe(10, 1.0)
        timeline.add_track(track)
        
        result = timeline.evaluate_frame(5)
        assert result["test.value"] == 0.0  # Step stays at first value
    
    def test_keyframe_hash_deterministic(self):
        track1 = Track(track_id="test", target="value")
        track1.add_keyframe(0, 0.0)
        track1.add_keyframe(10, 1.0)
        
        track2 = Track(track_id="test", target="value")
        track2.add_keyframe(0, 0.0)
        track2.add_keyframe(10, 1.0)
        
        assert track1.get_hash() == track2.get_hash()


class TestComparison:
    """Test comparison engine."""
    
    def test_identical_sessions(self):
        left = {
            "session_id": "s1",
            "current_manifest": {"seed": 42},
            "events": []
        }
        right = {
            "session_id": "s2", 
            "current_manifest": {"seed": 42},
            "events": []
        }
        
        result = compare_sessions(left, right)
        assert result.identical_pixels == True
        assert result.difference_score == 0.0
    
    def test_different_sessions(self):
        left = {
            "session_id": "s1",
            "current_manifest": {"seed": 42},
            "events": []
        }
        right = {
            "session_id": "s2",
            "current_manifest": {"seed": 123},
            "events": []
        }
        
        result = compare_sessions(left, right)
        assert result.identical_pixels == False
        assert result.difference_score > 0
    
    def test_manifest_diff_details(self):
        left = {"seed": 42, "width": 256}
        right = {"seed": 123, "width": 256}
        
        diffs = compare_manifests(left, right)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "seed"


class TestSecurity:
    """Test import/export security."""
    
    def test_sanitize_zip_path_valid(self):
        assert sanitize_zip_path("session.json") == "session.json"
        assert sanitize_zip_path("subdir/file.json") == "subdir/file.json"
    
    def test_sanitize_zip_path_blocks_traversal(self):
        # Path traversal attempts should return None
        assert sanitize_zip_path("../etc/passwd") is None
        assert sanitize_zip_path("../../../etc") is None
        # Leading slash is stripped but doesn't return None
        result = sanitize_zip_path("/absolute/path")
        assert result == "absolute/path" or result is None  # Normalized
    
    def test_validate_import_size(self):
        large_data = {"key": "x" * 20_000_000}
        with pytest.raises(Exception):  # Raises ImportTooLargeError
            validate_import_payload(large_data)
    
    def test_validate_import_rejects_nan(self):
        data = {"value": float('nan')}
        result = validate_import_payload(data)
        assert result.valid == False


class TestErrorContract:
    """Test error contract."""
    
    def test_error_detail_format(self):
        error = ErrorDetail(
            code=ErrorCode.SESSION_NOT_FOUND.value,
            message="Session not found",
            details={"session_id": "abc"}
        )
        
        response = error.to_api_response()
        assert "error" in response
        assert response["error"]["code"] == "SESSION_NOT_FOUND"
        assert response["error"]["details"]["session_id"] == "abc"
    
    def test_canopy_error_subclasses(self):
        err = SessionNotFoundError("abc123")
        assert err.error_detail.code == "SESSION_NOT_FOUND"
        assert err.error_detail.details["session_id"] == "abc123"
        assert err.status_code == 404


class TestStorageModels:
    """Test storage models."""
    
    def test_stored_session_creation(self):
        session = StoredSession(
            session_id="test-123",
            base_manifest={"seed": 42}
        )
        assert session.session_id == "test-123"
        assert session.status == SessionStatus.ACTIVE.value
        assert session.event_cursor == 0
    
    def test_session_get_active_events(self):
        session = StoredSession(session_id="test")
        session.events = [
            StoredEvent(0, "set_effect", {}),
            StoredEvent(1, "set_effect", {}),
            StoredEvent(2, "set_effect", {}),
        ]
        session.event_cursor = 2
        
        active = session.get_active_events()
        assert len(active) == 2
    
    def test_session_has_abandoned_future(self):
        session = StoredSession(session_id="test")
        session.abandoned_future = [StoredEvent(1, "x")]
        assert session.has_abandoned_future() == True
        
        session.abandoned_future = []
        assert session.has_abandoned_future() == False


class TestMigration:
    """Test schema migration."""
    
    def test_migrate_v1_to_v2(self):
        v1_manifest = {"seed": 42, "width": 256}
        v2_manifest = migrate_from_v1_to_v2(v1_manifest)
        
        assert v2_manifest["schema_version"] == "2.0"
        assert v2_manifest["seed"] == 42
    
    def test_already_v2(self):
        v2 = {"schema_version": "2.0", "seed": 42}
        result = migrate_from_v1_to_v2(v2)
        assert result["schema_version"] == "2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
