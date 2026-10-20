"""Thin read-only client for the starter's reference REST API.

Every list call pages to the end: the API defaults to 50 rows a page, which silently halves the
100-item LUMIN Catalog (ADR-0003).
"""

import os

import httpx

API_PREFIX = "/api/v1"
MAX_PAGE_SIZE = {"catalog-items": 200}  # every other list endpoint caps at 100
DEFAULT_MAX_PAGE_SIZE = 100


def base_url() -> str:
    """REFERENCE_API_URL with or without the /api/v1 prefix; returns the prefixed base."""
    url = os.environ.get("REFERENCE_API_URL", "http://api:8000").rstrip("/")
    return url if url.endswith(API_PREFIX) else url + API_PREFIX


async def fetch_all(resource: str, **filters) -> list[dict]:
    """Return every row of a paginated list endpoint, following pages until the last."""
    params = {k: v for k, v in filters.items() if v is not None}
    params["page_size"] = MAX_PAGE_SIZE.get(resource, DEFAULT_MAX_PAGE_SIZE)
    rows: list[dict] = []
    async with httpx.AsyncClient(base_url=base_url(), timeout=10.0) as client:
        page = 1
        while True:
            response = await client.get(f"/{resource}", params={**params, "page": page})
            response.raise_for_status()
            body = response.json()
            rows.extend(body["items"])
            if page >= body["pages"]:
                break
            page += 1
    if len(rows) != body["total"]:
        raise RuntimeError(f"{resource}: fetched {len(rows)} rows but the API reports {body['total']}")
    return rows
