"""Tests for ingest helper functions."""

import io

from tests.conftest import AUTH
from routers.ingest import _build_needs_review


def test_build_needs_review_empty_when_all_high():
    scores = {"full_name": 1.0, "passport_number": 1.0}
    fields = {"full_name": "Ahmed", "passport_number": "A123"}
    result = _build_needs_review(scores, fields)
    assert result == []


def test_build_needs_review_flags_low_scores():
    scores = {"full_name": 0.85, "passport_number": 1.0}
    fields = {"full_name": "Ahmed", "passport_number": "A123"}
    result = _build_needs_review(scores, fields)
    assert len(result) == 1
    assert result[0]["field"] == "full_name"
    assert result[0]["score"] == 0.85
    assert result[0]["current_value"] == "Ahmed"


def test_build_needs_review_skips_insurance_status():
    scores = {"insurance_status": 0.0, "full_name": 1.0}
    fields = {}
    result = _build_needs_review(scores, fields)
    assert result == []


def test_build_needs_review_action_enter_manually():
    scores = {"full_name": 0.0}
    result = _build_needs_review(scores, {})
    assert result[0]["action"] == "enter_manually"


def test_build_needs_review_action_spot_check():
    scores = {"full_name": 0.85}
    result = _build_needs_review(scores, {})
    assert result[0]["action"] == "spot_check"


def test_ingest_rejects_non_pdf(client):
    data = {"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")}
    r = client.post("/ingest", headers=AUTH, files=data)
    assert r.status_code == 400


def test_ingest_base64_rejects_non_pdf(client):
    r = client.post("/ingest/base64", headers=AUTH, json={"filename": "x.txt", "data": "dGVzdA=="})
    assert r.status_code == 400


def test_ingest_base64_rejects_invalid_base64(client):
    r = client.post("/ingest/base64", headers=AUTH, json={"filename": "x.pdf", "data": "!!!invalid!!!"})
    assert r.status_code == 400
