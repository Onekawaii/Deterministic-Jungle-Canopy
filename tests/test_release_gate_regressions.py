"""Regression tests for Sovereign release-gate defects."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from canopy.session import get_session_manager
from server import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_sessions():
    manager = get_session_manager()
    manager._sessions.clear()
    yield
    manager._sessions.clear()


def _create(client, seed=424242):
    response = client.post("/api/session", json={"seed": seed, "width": 64, "height": 64})
    assert response.status_code == 201
    return response.json()["session_id"]


def test_invalid_event_is_4xx_and_does_not_mutate(client):
    sid = _create(client)
    before = client.get(f"/api/session/{sid}").json()

    response = client.post(
        f"/api/session/{sid}/event",
        json={"event_type": "definitely_invalid_event", "payload": {"seed": 1}},
    )

    after = client.get(f"/api/session/{sid}").json()
    assert response.status_code == 400
    assert "unknown event type" in response.json()["detail"].lower()
    assert after["manifest_hash"] == before["manifest_hash"]
    assert after["event_count"] == before["event_count"]


def test_safe_export_import_roundtrip(client):
    sid = _create(client)
    exported = client.get(f"/api/export/session/{sid}")
    assert exported.status_code == 200

    imported = client.post("/api/import/session", json=exported.json())
    assert imported.status_code == 200
    body = imported.json()
    assert body["imported"] is True
    assert body["session_id"] != sid


def test_sequence_export_is_real_zip_with_pixel_hashes(client):
    sid = _create(client)
    response = client.get(
        f"/api/export/session/{sid}/sequence",
        params={"start_frame": 0, "end_frame": 2, "step": 1},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    with zipfile.ZipFile(io.BytesIO(response.content), "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "metadata.json" in names
        assert {"frames/0000.png", "frames/0001.png", "frames/0002.png"} <= names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["frame_count"] == 3
        assert all(len(frame["pixel_hash"]) == 64 for frame in manifest["frames"])
        for name in ("frames/0000.png", "frames/0001.png", "frames/0002.png"):
            assert zf.read(name).startswith(b"\x89PNG")


def test_single_frame_export_is_png(client):
    sid = _create(client)
    response = client.get(f"/api/export/session/{sid}/frame/0")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
