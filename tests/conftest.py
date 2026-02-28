"""Test fixtures for Employee HR Service."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Must be set before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")
os.environ.setdefault("LOOMI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

AUTH = {"X-API-Key": "test-key"}


def _make_mock_conn():
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@pytest.fixture(scope="session")
def mock_conn_cursor():
    return _make_mock_conn()


@pytest.fixture(scope="session")
def client(mock_conn_cursor):
    mock_conn, _ = mock_conn_cursor
    with patch("psycopg2.connect", return_value=mock_conn):
        from main import app

        with patch("main.init_db"):
            with TestClient(app) as c:
                yield c
