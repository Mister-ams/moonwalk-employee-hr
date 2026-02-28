"""Tests for /health endpoint."""


def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)


def test_health_deep_no_database_url(client):
    """When DATABASE_URL points to non-Postgres host, deep health reports degraded."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"DATABASE_URL": ""}):
        r = client.get("/health/deep")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
