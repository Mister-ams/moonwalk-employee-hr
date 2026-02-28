"""Tests for /exceptions endpoint and db.fetch_exceptions."""

from unittest.mock import patch

from tests.conftest import AUTH


def test_exceptions_empty(client):
    with patch("routers.exceptions.fetch_exceptions", return_value=[]):
        r = client.get("/exceptions", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


def test_exceptions_returns_low_score_employees(client):
    emp = {"employee_id": "EID-1001", "field_scores": {"full_name": 0.85}}
    with patch("routers.exceptions.fetch_exceptions", return_value=[emp]):
        r = client.get("/exceptions", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_db_fetch_exceptions_filters_low_scores():
    """db.fetch_exceptions filters rows where any field score < 0.95."""
    from unittest.mock import patch as p

    rows = [
        {"employee_id": "EID-1001", "field_scores": {"full_name": 0.85}},
        {"employee_id": "EID-1002", "field_scores": {"full_name": 1.0}},
        {"employee_id": "EID-1003", "field_scores": None},
    ]
    with p("db.fetch_all_employees", return_value=rows):
        from db import fetch_exceptions

        result = fetch_exceptions()

    assert len(result) == 1
    assert result[0]["employee_id"] == "EID-1001"


def test_db_fetch_exceptions_excludes_insurance_status():
    """Insurance status below 0.95 does NOT trigger exception flag."""
    from unittest.mock import patch as p

    rows = [{"employee_id": "EID-1001", "field_scores": {"insurance_status": 0.0}}]
    with p("db.fetch_all_employees", return_value=rows):
        from db import fetch_exceptions

        result = fetch_exceptions()

    assert result == []
