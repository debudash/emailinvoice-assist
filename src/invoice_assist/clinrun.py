"""ClinRun Client: submit to the (mock) ClinRun backend with an idempotency key (ADR-0011)."""
import hashlib

import httpx

from .config import settings


def idempotency_key(sha256: str, version: int) -> str:
    return hashlib.sha256(f"{sha256}:v{version}".encode()).hexdigest()


def submit(submission: dict, key: str) -> str:
    """Returns the ClinRun ID. A repeated key returns the original ID, so retries are safe."""
    response = httpx.post(f"{settings.clinrun_url}/submissions", json=submission,
                          headers={"Idempotency-Key": key}, timeout=30)
    response.raise_for_status()
    return response.json()["clinrun_id"]
