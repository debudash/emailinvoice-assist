"""Shared test setup: import the service modules, and skip live tests when the API is down."""

import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LIVE_API_URL = os.environ.get("REFERENCE_API_URL", "http://localhost:8000")
os.environ["REFERENCE_API_URL"] = LIVE_API_URL


def _api_up() -> bool:
    root = LIVE_API_URL.rstrip("/").removesuffix("/api/v1")
    try:
        return httpx.get(f"{root}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


API_UP = _api_up()


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason=f"reference API not reachable at {LIVE_API_URL}")
    for item in items:
        if "live" in item.keywords and not API_UP:
            item.add_marker(skip)
