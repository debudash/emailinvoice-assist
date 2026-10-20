"""mock-clinrun contract tests (docs/prd.md "Contracts", ADR 0011)."""
import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app

SUBMISSION = {
    "invoice": {"number": "INV-1001", "date": "2026-10-01", "currency": "USD", "total": 1250.0},
    "context": {"sponsor_id": 1, "study_id": 12, "site_id": 7},
    "lines": [
        {
            "catalog_item_id": 3,
            "item_code": "SCR-01",
            "description_as_billed": "Screening visit",
            "qty": 1,
            "unit_price": 1250.0,
            "amount": 1250.0,
            "price_variance": False,
        }
    ],
    "decision": {"rationale": "All checks passed", "straight_through": True},
    "release": None,
    "source": {"message_id": "<abc@example.com>", "received_at": "2026-10-01T09:00:00Z"},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINRUN_DB", str(tmp_path / "sub" / "clinrun.db"))
    return TestClient(app)


def post(client, key="key-1", body=SUBMISSION):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/submissions", json=body, headers=headers)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_new_submission_returns_201_and_clinrun_id(client):
    r = post(client)
    assert r.status_code == 201
    assert r.json() == {"clinrun_id": "CR-000001", "status": "accepted", "duplicate": False}
    assert post(client, key="key-2").json()["clinrun_id"] == "CR-000002"


def test_repeated_key_returns_original_id_and_stores_once(client):
    first = post(client).json()
    r = post(client)
    assert r.status_code == 200
    assert r.json() == {"clinrun_id": first["clinrun_id"], "status": "accepted", "duplicate": True}
    listing = client.get("/submissions").json()
    assert len(listing) == 1
    assert listing[0]["idempotency_key"] == "key-1"
    assert listing[0]["submission"]["invoice"]["number"] == "INV-1001"


def test_list_is_newest_first_and_get_by_id(client):
    post(client, key="a")
    post(client, key="b")
    assert [s["clinrun_id"] for s in client.get("/submissions").json()] == ["CR-000002", "CR-000001"]
    one = client.get("/submissions/CR-000001")
    assert one.status_code == 200
    assert one.json()["idempotency_key"] == "a"


def test_missing_idempotency_key_returns_400(client):
    assert post(client, key=None).status_code == 400


def test_bad_body_returns_422(client):
    bad = copy.deepcopy(SUBMISSION)
    bad["invoice"]["currency"] = "EUR"
    assert post(client, body=bad).status_code == 422
    assert post(client, body={"invoice": {}}).status_code == 422


def test_get_unknown_returns_404(client):
    assert client.get("/submissions/CR-999999").status_code == 404
