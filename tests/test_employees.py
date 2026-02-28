"""Tests for /employees endpoints."""

from unittest.mock import patch

from tests.conftest import AUTH

_EMPLOYEE = {
    "employee_id": "EID-1001",
    "full_name": "Ahmed Al-Rashid",
    "nationality": "UAE",
    "date_of_birth": "1990-01-01",
    "passport_number": "A12345678",
    "job_title": "Engineer",
    "base_salary": 10000,
    "total_salary": 12000,
    "contract_start_date": "2024-01-01",
    "contract_expiry_date": "2025-01-01",
    "insurance_status": None,
    "mohre_transaction_no": "MOH123",
    "source_file": "contract.pdf",
    "confidence_score": 1.0,
    "field_scores": {},
    "source_doc_type": "employment_contract",
    "ingested_at": "2024-01-01T00:00:00",
}


def test_list_employees_empty(client):
    with patch("routers.employees.fetch_all_employees", return_value=[]):
        r = client.get("/employees", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == []


def test_list_employees_returns_data(client):
    with patch("routers.employees.fetch_all_employees", return_value=[_EMPLOYEE]):
        r = client.get("/employees", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["employee_id"] == "EID-1001"


def test_get_employee_found(client):
    with patch("routers.employees.fetch_employee", return_value=_EMPLOYEE):
        r = client.get("/employees/EID-1001", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["employee_id"] == "EID-1001"


def test_get_employee_not_found(client):
    with patch("routers.employees.fetch_employee", return_value=None):
        r = client.get("/employees/EID-9999", headers=AUTH)
    assert r.status_code == 404


def test_list_employees_requires_auth(client):
    with patch("routers.employees.fetch_all_employees", return_value=[]):
        r = client.get("/employees")
    assert r.status_code == 401
