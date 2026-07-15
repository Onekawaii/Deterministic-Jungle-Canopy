"""
Test: Canonical Hashing Functionality
Comprehensive tests for deterministic hashing primitives.
"""
import pytest
import sys
import os
import math
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from canopy.hashing import (
    canonical_json,
    hash_manifest,
    hash_event,
    hash_pixels,
    hash_event_log,
    hash_session_export,
    verify_no_nan_inf,
    verify_canonical,
    HashVerificationError,
)


class TestCanonicalJsonRejectsNaNInfinity:
    """Test that canonical_json properly rejects NaN and Infinity values."""

    def test_rejects_float_nan(self):
        """Test that NaN floats are rejected."""
        with pytest.raises(ValueError, match="NaN not allowed"):
            canonical_json({"value": float('nan')})

    def test_rejects_float_positive_infinity(self):
        """Test that positive Infinity floats are rejected."""
        with pytest.raises(ValueError, match="Infinity not allowed"):
            canonical_json({"value": float('inf')})

    def test_rejects_float_negative_infinity(self):
        """Test that negative Infinity floats are rejected."""
        with pytest.raises(ValueError, match="Infinity not allowed"):
            canonical_json({"value": float('-inf')})

    def test_rejects_numpy_nan(self):
        """Test that NumPy NaN values are rejected."""
        with pytest.raises(ValueError, match="NaN"):
            canonical_json({"value": np.nan})

    def test_rejects_numpy_positive_infinity(self):
        """Test that NumPy positive infinity is rejected."""
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json({"value": np.inf})

    def test_rejects_numpy_negative_infinity(self):
        """Test that NumPy negative infinity is rejected."""
        with pytest.raises(ValueError, match="Infinity"):
            canonical_json({"value": -np.inf})

    def test_rejects_nan_in_nested_dict(self):
        """Test that NaN in nested dictionaries is rejected."""
        with pytest.raises(ValueError, match="NaN not allowed"):
            canonical_json({
                "outer": {
                    "inner": {
                        "value": float('nan')
                    }
                }
            })

    def test_rejects_nan_in_list(self):
        """Test that NaN in lists is rejected."""
        with pytest.raises(ValueError, match="NaN not allowed"):
            canonical_json([1, 2, float('nan'), 3])

    def test_rejects_nan_in_array(self):
        """Test that NumPy arrays containing NaN are rejected."""
        with pytest.raises(ValueError, match="ndarray not allowed"):
            canonical_json({"array": np.array([1.0, np.nan, 3.0])})


class TestCanonicalJsonStableOutput:
    """Test that canonical_json produces stable, deterministic output."""

    def test_same_input_produces_same_output(self):
        """Test that the same input always produces the same output."""
        data = {"b": 2, "a": 1, "c": 3}
        result1 = canonical_json(data)
        result2 = canonical_json(data)
        assert result1 == result2

    def test_key_order_does_not_affect_output(self):
        """Test that dictionary key order doesn't affect canonical output."""
        data1 = {"x": 1, "y": 2, "z": 3}
        data2 = {"z": 3, "x": 1, "y": 2}
        assert canonical_json(data1) == canonical_json(data2)

    def test_nested_dict_order_does_not_affect_output(self):
        """Test that nested dictionary key order is normalized."""
        data1 = {"outer": {"z": 1, "a": 2}}
        data2 = {"outer": {"a": 2, "z": 1}}
        assert canonical_json(data1) == canonical_json(data2)

    def test_list_order_preserved(self):
        """Test that list order is preserved in output."""
        data = {"items": [3, 1, 4, 1, 5]}
        result = canonical_json(data)
        assert "[3,1,4,1,5]" in result

    def test_compact_format_no_spaces(self):
        """Test that output uses compact format without spaces."""
        data = {"key": "value", "number": 42}
        result = canonical_json(data)
        assert " " not in result
        assert '","' in result or ',"' in result or '"}' in result

    def test_sorted_keys_in_output(self):
        """Test that keys are sorted in the output."""
        data = {"z": 1, "a": 2, "m": 3}
        result = canonical_json(data)
        assert result.index('"a"') < result.index('"m"') < result.index('"z"')

    def test_datetime_converted_to_iso_format(self):
        """Test that datetime objects are converted to ISO format strings."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = canonical_json({"timestamp": dt})
        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_float_values_preserved(self):
        """Test that regular float values are preserved."""
        data = {"pi": 3.14159, "e": 2.71828}
        result = canonical_json(data)
        assert "3.14159" in result
        assert "2.71828" in result


class TestHashManifest:
    """Test hash_manifest function."""

    def test_hash_manifest_returns_hex_string(self):
        """Test that hash_manifest returns a 64-character hex string."""
        manifest = {
            "schema_version": "1.0",
            "engine_version": "1.0.0",
            "seed": 42,
            "width": 64,
            "height": 64,
            "noise_type": "perlin",
            "noise_params": {},
            "grid_operations": [],
            "effects": [],
        }
        result = hash_manifest(manifest)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in '0123456789abcdef' for c in result)

    def test_same_manifest_produces_same_hash(self):
        """Test that the same manifest always produces the same hash."""
        manifest = {
            "schema_version": "1.0",
            "seed": 12345,
            "width": 128,
            "height": 128,
        }
        hash1 = hash_manifest(manifest)
        hash2 = hash_manifest(manifest)
        assert hash1 == hash2

    def test_different_seeds_produce_different_hashes(self):
        """Test that different seeds produce different hashes."""
        manifest1 = {"schema_version": "1.0", "seed": 111, "width": 64, "height": 64}
        manifest2 = {"schema_version": "1.0", "seed": 222, "width": 64, "height": 64}
        assert hash_manifest(manifest1) != hash_manifest(manifest2)

    def test_manifest_with_to_dict_method(self):
        """Test that manifest objects with to_dict method work."""
        class MockManifest:
            def to_dict(self):
                return {
                    "schema_version": "1.0",
                    "seed": 42,
                    "width": 64,
                    "height": 64,
                }
        result = hash_manifest(MockManifest())
        assert isinstance(result, str)
        assert len(result) == 64


class TestHashEvent:
    """Test hash_event function."""

    def test_hash_event_returns_hex_string(self):
        """Test that hash_event returns a 64-character hex string."""
        event = {
            "event_index": 0,
            "event_type": "set_seed",
            "payload": {"seed": 100},
        }
        result = hash_event(event)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_event_produces_same_hash(self):
        """Test that the same event always produces the same hash."""
        event = {
            "event_index": 5,
            "event_type": "add_effect",
            "payload": {"effect": "bloom"},
        }
        hash1 = hash_event(event)
        hash2 = hash_event(event)
        assert hash1 == hash2

    def test_different_event_index_produces_different_hash(self):
        """Test that different event indices produce different hashes."""
        event1 = {"event_index": 0, "event_type": "set_seed", "payload": {}}
        event2 = {"event_index": 1, "event_type": "set_seed", "payload": {}}
        assert hash_event(event1) != hash_event(event2)


class TestHashPixels:
    """Test hash_pixels function."""

    def test_hash_pixels_returns_hex_string(self):
        """Test that hash_pixels returns a 64-character hex string."""
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        result = hash_pixels(frame)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_pixels_produces_same_hash(self):
        """Test that the same pixel data produces the same hash."""
        frame = np.array([[1, 2], [3, 4]], dtype=np.uint8)
        hash1 = hash_pixels(frame)
        hash2 = hash_pixels(frame)
        assert hash1 == hash2

    def test_different_pixels_produce_different_hash(self):
        """Test that different pixel data produces different hashes."""
        frame1 = np.zeros((5, 5), dtype=np.uint8)
        frame2 = np.ones((5, 5), dtype=np.uint8)
        assert hash_pixels(frame1) != hash_pixels(frame2)

    def test_string_input_works(self):
        """Test that string input is accepted for hashing."""
        result = hash_pixels("test string data")
        assert isinstance(result, str)
        assert len(result) == 64


class TestHashEventLog:
    """Test hash_event_log function."""

    def test_hash_event_log_returns_hex_string(self):
        """Test that hash_event_log returns a 64-character hex string."""
        events = [
            {"event_index": 0, "event_type": "set_seed", "payload": {"seed": 1}},
            {"event_index": 1, "event_type": "set_seed", "payload": {"seed": 2}},
        ]
        result = hash_event_log(events)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_events_produce_same_hash(self):
        """Test that the same event list produces the same hash."""
        events = [
            {"event_index": 0, "event_type": "set_seed", "payload": {"seed": 42}},
        ]
        hash1 = hash_event_log(events)
        hash2 = hash_event_log(events)
        assert hash1 == hash2

    def test_different_event_order_produces_different_hash(self):
        """Test that different event order produces different hashes."""
        events1 = [
            {"event_index": 0, "event_type": "a", "payload": {}},
            {"event_index": 1, "event_type": "b", "payload": {}},
        ]
        events2 = [
            {"event_index": 0, "event_type": "b", "payload": {}},
            {"event_index": 1, "event_type": "a", "payload": {}},
        ]
        assert hash_event_log(events1) != hash_event_log(events2)

    def test_empty_event_list(self):
        """Test that empty event list produces a valid hash."""
        result = hash_event_log([])
        assert isinstance(result, str)
        assert len(result) == 64


class TestHashSessionExport:
    """Test hash_session_export function."""

    def test_hash_session_export_returns_hex_string(self):
        """Test that hash_session_export returns a 64-character hex string."""
        export = {
            "session": {
                "session_id": "test-session-123",
                "engine_version": "1.0.0",
                "schema_version": "1.0",
                "base_manifest": {
                    "schema_version": "1.0",
                    "seed": 42,
                    "width": 64,
                    "height": 64,
                },
                "events": [],
            }
        }
        result = hash_session_export(export)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_export_produces_same_hash(self):
        """Test that the same export data produces the same hash."""
        export = {
            "session": {
                "session_id": "test-123",
                "engine_version": "1.0.0",
                "schema_version": "1.0",
                "base_manifest": {
                    "schema_version": "1.0",
                    "seed": 999,
                    "width": 128,
                    "height": 128,
                },
                "events": [
                    {"event_index": 0, "event_type": "set_seed", "payload": {"seed": 100}},
                ],
            }
        }
        hash1 = hash_session_export(export)
        hash2 = hash_session_export(export)
        assert hash1 == hash2


class TestVerifyNoNaNInf:
    """Test verify_no_nan_inf function."""

    def test_returns_true_for_clean_float(self):
        """Test that clean float values return True."""
        assert verify_no_nan_inf(3.14159) is True

    def test_returns_true_for_clean_dict(self):
        """Test that dict without NaN/Inf returns True."""
        assert verify_no_nan_inf({"a": 1, "b": 2.5}) is True

    def test_returns_true_for_clean_list(self):
        """Test that list without NaN/Inf returns True."""
        assert verify_no_nan_inf([1, 2.0, 3.5]) is True

    def test_returns_false_for_nan(self):
        """Test that NaN values return False."""
        assert verify_no_nan_inf(float('nan')) is False

    def test_returns_false_for_positive_infinity(self):
        """Test that positive infinity returns False."""
        assert verify_no_nan_inf(float('inf')) is False

    def test_returns_false_for_negative_infinity(self):
        """Test that negative infinity returns False."""
        assert verify_no_nan_inf(float('-inf')) is False

    def test_returns_false_for_dict_with_nan(self):
        """Test that dict containing NaN returns False."""
        assert verify_no_nan_inf({"a": 1, "b": float('nan')}) is False

    def test_returns_false_for_list_with_nan(self):
        """Test that list containing NaN returns False."""
        assert verify_no_nan_inf([1, 2, float('nan')]) is False

    def test_returns_false_for_numpy_array_with_nan(self):
        """Test that NumPy array with NaN returns False."""
        arr = np.array([1.0, np.nan, 3.0])
        assert verify_no_nan_inf(arr) is False

    def test_returns_false_for_numpy_array_with_inf(self):
        """Test that NumPy array with Infinity returns False."""
        arr = np.array([1.0, np.inf, 3.0])
        assert verify_no_nan_inf(arr) is False

    def test_returns_true_for_numpy_array_without_nan_inf(self):
        """Test that clean NumPy array returns True."""
        arr = np.array([1.0, 2.0, 3.0])
        assert verify_no_nan_inf(arr) is True

    def test_returns_true_for_nested_clean_structure(self):
        """Test that nested clean structure returns True."""
        data = {
            "outer": {
                "inner": [1, 2, 3],
            },
            "list": [{"a": 1}, {"b": 2}],
        }
        assert verify_no_nan_inf(data) is True

    def test_returns_false_for_nested_nan(self):
        """Test that nested NaN is detected."""
        data = {"outer": {"inner": float('nan')}}
        assert verify_no_nan_inf(data) is False


class TestVerifyCanonical:
    """Test verify_canonical function."""

    def test_verify_canonical_accepts_clean_data(self):
        """Test that clean data passes verification."""
        data = {"value": 42, "text": "hello", "nested": {"a": 1.5}}
        verify_canonical(data)  # Should not raise

    def test_verify_canonical_rejects_nan(self):
        """Test that NaN values raise HashVerificationError."""
        with pytest.raises(HashVerificationError, match="NaN or Infinity"):
            verify_canonical(float('nan'))

    def test_verify_canonical_rejects_infinity(self):
        """Test that Infinity values raise HashVerificationError."""
        with pytest.raises(HashVerificationError, match="NaN or Infinity"):
            verify_canonical(float('inf'))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
