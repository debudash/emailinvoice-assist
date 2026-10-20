"""ClinRun Client against a private mock-clinrun (integration).

Starts its own mock on a free port with a temp database, so it never writes to the demo's ClinRun.
"""
import os
import socket
import subprocess
import sys
import time
import uuid

import httpx
import pytest

from conftest import ROOT
from invoice_assist import clinrun

SUBMISSION = {
    "invoice": {"number": "INV-TEST", "date": "2024-03-15", "currency": "USD", "total": 400.0},
    "context": {"sponsor_id": 2, "study_id": 3, "site_id": 1},
    "lines": [{"catalog_item_id": 101, "item_code": "ADMIN-SITE", "description_as_billed": "Site Management Fee",
               "qty": 1, "unit_price": 400.0, "amount": 400.0, "price_variance": False}],
    "decision": {"rationale": "test", "straight_through": True},
    "release": None,
    "source": {"message_id": "test@local", "received_at": "2026-10-19T09:00:00+00:00"},
}


@pytest.fixture(scope="module")
def mock_clinrun(tmp_path_factory):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "CLINRUN_DB": str(tmp_path_factory.mktemp("clinrun") / "clinrun.db")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=ROOT / "services" / "mock-clinrun", env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def client_at(mock_clinrun, monkeypatch):
    import invoice_assist.config as config
    monkeypatch.setattr(clinrun, "settings", config.Settings(clinrun_url=mock_clinrun))
    return mock_clinrun


def test_resubmitting_the_same_key_returns_the_original_clinrun_id(client_at):
    key = clinrun.idempotency_key(uuid.uuid4().hex, 1)

    first = clinrun.submit(SUBMISSION, key)
    second = clinrun.submit(SUBMISSION, key)

    assert first.startswith("CR-") and second == first
    assert len(httpx.get(f"{client_at}/submissions").json()) == 1


def test_a_new_invoice_version_gets_a_new_key():
    assert clinrun.idempotency_key("abc", 1) != clinrun.idempotency_key("abc", 2)
