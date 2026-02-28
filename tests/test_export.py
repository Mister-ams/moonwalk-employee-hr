"""Tests for /export/csv endpoint and export utilities."""

from datetime import date, timedelta
from unittest.mock import patch

from tests.conftest import AUTH


def test_export_csv_empty(client):
    with patch("routers.export.fetch_all_employees", return_value=[]):
        r = client.get("/export/csv", headers=AUTH)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]


def test_export_csv_has_header_row(client):
    with patch("routers.export.fetch_all_employees", return_value=[]):
        r = client.get("/export/csv", headers=AUTH)
    assert "employee_id" in r.text


def test_export_csv_includes_employee_data(client):
    emp = {
        "employee_id": "EID-1001",
        "full_name": "Test User",
        "contract_expiry_date": (date.today() + timedelta(days=60)).isoformat(),
    }
    with patch("routers.export.fetch_all_employees", return_value=[emp]):
        r = client.get("/export/csv", headers=AUTH)
    assert "EID-1001" in r.text


def test_enrich_calculates_days_until_expiry():
    from routers.export import _enrich

    future = (date.today() + timedelta(days=60)).isoformat()
    rows = [{"employee_id": "EID-1001", "contract_expiry_date": future}]
    result = _enrich(rows)
    assert result[0]["days_until_expiry"] == 60
    assert result[0]["expiry_flag"] is False


def test_enrich_sets_expiry_flag_when_close(client):
    from routers.export import _enrich

    close = (date.today() + timedelta(days=5)).isoformat()
    rows = [{"contract_expiry_date": close}]
    result = _enrich(rows)
    assert result[0]["expiry_flag"] is True


def test_enrich_handles_missing_expiry():
    from routers.export import _enrich

    rows = [{"contract_expiry_date": None}]
    result = _enrich(rows)
    assert result[0]["days_until_expiry"] is None
    assert result[0]["expiry_flag"] is False


def test_enrich_handles_invalid_date():
    from routers.export import _enrich

    rows = [{"contract_expiry_date": "not-a-date"}]
    result = _enrich(rows)
    assert result[0]["days_until_expiry"] is None
