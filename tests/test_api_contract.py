"""
Test: API Contract
Verifies FastAPI endpoints follow the deterministic contract.
"""
import pytest
import sys
import os
import hashlib
import base64
from unittest.mock import patch, MagicMock
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAPIContract:
    """Tests for API endpoint determinism guarantees."""
    
    @pytest.fixture
    def mock_app(self):
        """Create a mocked FastAPI app for testing."""
        # Import the app components
        from fastapi.testclient import TestClient
        from server import app
        return TestClient(app)
    
    def test_health_endpoint_works(self, mock_app):
        """Health endpoint must return status."""
        response = mock_app.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_seed_endpoint_is_deterministic(self, mock_app):
        """Setting the same seed should enable deterministic rendering."""
        # Set seed 42
        response1 = mock_app.post("/api/seed", json={
            "seed": 42,
            "width": 64,
            "height": 64
        })
        assert response1.status_code == 200
        
        # Get current state
        state1 = mock_app.get("/api/config/current").json()
        
        # Set same seed again
        response2 = mock_app.post("/api/seed", json={
            "seed": 42,
            "width": 64,
            "height": 64
        })
        assert response2.status_code == 200
        
        state2 = mock_app.get("/api/config/current").json()
        
        assert state1["seed"] == state2["seed"] == 42, \
            "Same seed request should produce same seed"
    
    def test_render_endpoint_returns_image(self, mock_app):
        """Render endpoint must return base64 image."""
        response = mock_app.post("/api/render", json={
            "seed": 42,
            "width": 64,
            "height": 64
        })
        assert response.status_code == 200
        data = response.json()
        assert "image" in data
        assert data["image"].startswith("data:image/png;base64,")
    
    def test_render_same_seed_same_image(self, mock_app):
        """Same seed must produce same image data."""
        # First render
        response1 = mock_app.post("/api/render", json={
            "seed": 42,
            "width": 32,
            "height": 32
        })
        data1 = response1.json()
        hash1 = hashlib.sha256(
            base64.b64decode(data1["image"].split(",")[1])
        ).hexdigest()
        
        # Second render with same seed
        response2 = mock_app.post("/api/render", json={
            "seed": 42,
            "width": 32,
            "height": 32
        })
        data2 = response2.json()
        hash2 = hashlib.sha256(
            base64.b64decode(data2["image"].split(",")[1])
        ).hexdigest()
        
        assert hash1 == hash2, "Same seed must produce same image"
    
    def test_effects_endpoint_lists_all(self, mock_app):
        """Effects endpoint must list all available effects."""
        response = mock_app.get("/api/effects")
        assert response.status_code == 200
        data = response.json()
        assert "effects" in data
        assert "presets" in data
        assert len(data["effects"]) > 0
    
    def test_invalid_preset_returns_400(self, mock_app):
        """Invalid preset should return 400 error."""
        response = mock_app.post("/api/effects/preset", json={
            "preset_name": "nonexistent_preset"
        })
        assert response.status_code == 400
    
    def test_archive_endpoints_work(self, mock_app):
        """Archive endpoints must function correctly."""
        # Get stats
        response = mock_app.get("/api/archive/stats")
        assert response.status_code == 200
        
        # Get recent
        response = mock_app.get("/api/archive/recent?limit=5")
        assert response.status_code == 200
        
        # Search
        response = mock_app.post("/api/archive/search", json={
            "limit": 10
        })
        assert response.status_code == 200
    
    def test_config_export_import_roundtrip(self, mock_app):
        """Config export/import must preserve state."""
        # Set a seed and effects
        mock_app.post("/api/seed", json={"seed": 123})
        mock_app.post("/api/effects/enable/vignette")
        
        # Export
        export_response = mock_app.get("/api/config/export")
        config = export_response.json()["config"]
        
        # Import
        import_response = mock_app.post("/api/config/import", json={
            "config_json": config
        })
        assert import_response.status_code == 200
        
        # Verify seed is preserved
        state = mock_app.get("/api/config/current").json()
        assert state["seed"] == 123


class TestAPIErrorHandling:
    """Tests for API error handling."""
    
    @pytest.fixture
    def mock_app(self):
        """Create a mocked FastAPI app for testing."""
        from fastapi.testclient import TestClient
        from server import app
        return TestClient(app)
    
    def test_invalid_effect_returns_404(self, mock_app):
        """Invalid effect should return 404."""
        response = mock_app.post("/api/effects/enable/nonexistent_effect")
        assert response.status_code == 404
    
    def test_nonexistent_archive_entry_returns_404(self, mock_app):
        """Nonexistent archive entry should return 404."""
        response = mock_app.get("/api/archive/99999")
        assert response.status_code == 404
    
    def test_invalid_dimensions_handled(self, mock_app):
        """Invalid dimensions should be handled gracefully."""
        response = mock_app.post("/api/seed", json={
            "seed": 42,
            "width": -1,
            "height": 720
        })
        # Should either succeed with clamped values or return error
        assert response.status_code in [200, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
