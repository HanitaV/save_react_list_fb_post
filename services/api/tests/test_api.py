import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_db
from app.main import app


def test_native_dashboard_and_post_flow(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Evidence System" in dashboard.text
        token = client.post(
            "/api/auth/login", json={"password": "development-only"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            "/api/posts",
            json={"urls": ["https://www.facebook.com/example/posts/1"]},
            headers=headers,
        )
        assert created.status_code == 200
        assert len(client.get("/api/posts", headers=headers).json()) == 1
        assert client.get("/api/system/status", headers=headers).json()["posts"] == 1
        exported = client.post(
            f"/api/reports/post/{created.json()[0]['id']}", headers=headers
        )
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert {
                "report.html",
                "report.json",
                "hashes.json",
                "evidence_chain.json",
            } <= set(archive.namelist())
    finally:
        app.dependency_overrides.clear()


def test_viewer_cannot_create_posts(db, monkeypatch):
    monkeypatch.setattr(settings, "viewer_password", "viewer-test-password")
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        login = client.post(
            "/api/auth/login", json={"password": "viewer-test-password"}
        )
        assert login.json()["role"] == "VIEWER"
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/posts", headers=headers).status_code == 200
        assert (
            client.post("/api/posts", json={"urls": []}, headers=headers).status_code
            == 403
        )
    finally:
        app.dependency_overrides.clear()


def test_extension_bundle_import(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        token = client.post(
            "/api/auth/login", json={"password": "development-only"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        bundle = {
            "scans": [
                {
                    "post_url": "https://www.facebook.com/groups/123/posts/456",
                    "captured_at": "2026-01-01T10:00:00Z",
                    "truncated": False,
                    "records": [
                        {
                            "profile_url": "https://www.facebook.com/groups/123/user/456/",
                            "name": "Example",
                            "reaction": "Thích",
                        }
                    ],
                }
            ]
        }
        response = client.post(
            "/api/import/extension",
            files={
                "file": ("facebook-review.json", json.dumps(bundle), "application/json")
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["inserted"] == 1
        assert response.json()["source"] == "extension_scan"
    finally:
        app.dependency_overrides.clear()
