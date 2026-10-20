"""ref-mcp: an MCP server that wraps the read-only reference API and owns name search (ADR-0003).

Search tools return ranked candidates with computed similarity scores (ADR-0004) plus the
reference fields that support Corroboration. The Catalog tool always returns the whole Catalog.
Served over streamable HTTP at http://<host>:8200/mcp.
"""

import os

from mcp.server.fastmcp import FastMCP

import refapi
import scoring

mcp = FastMCP(
    "ref-mcp",
    host=os.environ.get("MCP_HOST", "0.0.0.0"),
    port=int(os.environ.get("MCP_PORT", "8200")),
    streamable_http_path="/mcp",
    stateless_http=True,  # every call stands alone: no session state to lose between Stage Runs
    json_response=True,  # plain JSON responses; easy to inspect with curl
)


def _top(candidates: list[dict], limit: int, key: str = "score") -> list[dict]:
    return sorted(candidates, key=lambda c: c[key], reverse=True)[:limit]


@mcp.tool()
async def search_sponsors(query: str, limit: int = 5) -> list[dict]:
    """Rank sponsors by name similarity to `query` (e.g. the sponsor printed on an invoice)."""
    sponsors = await refapi.fetch_all("sponsors")
    candidates = [
        {"id": s["id"], "name": s["name"], "code": s["code"], "score": scoring.name_score(query, s["name"])}
        for s in sponsors
    ]
    return _top(candidates, limit)


@mcp.tool()
async def search_studies(query: str, sponsor_id: int | None = None, limit: int = 5) -> list[dict]:
    """Rank studies by similarity of `query` to the study name and to its protocol number.

    score = max(name_score, protocol_score). Pass sponsor_id to search one sponsor's studies only.
    """
    studies = await refapi.fetch_all("studies", sponsor_id=sponsor_id)
    candidates = []
    for s in studies:
        n = scoring.name_score(query, s["name"])
        p = scoring.protocol_score(query, s["protocol_number"])
        candidates.append(
            {
                "id": s["id"],
                "sponsor_id": s["sponsor_id"],
                "name": s["name"],
                "protocol_number": s["protocol_number"],
                "phase": s["phase"],
                "name_score": n,
                "protocol_score": p,
                "score": max(n, p),
            }
        )
    return _top(candidates, limit)


@mcp.tool()
async def search_sites(name: str, pi_name: str | None = None, limit: int = 5) -> list[dict]:
    """Rank sites by name similarity; an optional PI name corroborates but never lifts the score.

    score = name_score. pi_score is reported separately (null without pi_name). Candidates are
    ordered by rank_score, which blends in the PI match (ADR-0005: Corroboration ranks but
    cannot lift); without pi_name, rank_score equals score.
    """
    sites = await refapi.fetch_all("sites")
    candidates = []
    for s in sites:
        n = scoring.name_score(name, s["name"])
        p = scoring.person_score(pi_name, s["pi_name"]) if pi_name else None
        candidates.append(
            {
                "id": s["id"],
                "name": s["name"],
                "city": s["city"],
                "state": s["state"],
                "pi_name": s["pi_name"],
                "name_score": n,
                "pi_score": p,
                "score": n,
                "rank_score": scoring.site_rank_score(n, p),
            }
        )
    return _top(candidates, limit, key="rank_score")


@mcp.tool()
async def list_study_sites(study_id: int) -> list[dict]:
    """The sites linked to a study, for the 'site is linked to the study' Corroboration check."""
    links = await refapi.fetch_all("study-sites", study_id=study_id)
    return [{"site_id": link["site_id"], "status": link["status"]} for link in links]


@mcp.tool()
async def get_catalog(sponsor_id: int, study_id: int) -> dict:
    """The complete Catalog for one sponsor and study, every page fetched.

    unit_price is the API's exact decimal string (e.g. "450.00"), never a float.
    """
    items = await refapi.fetch_all("catalog-items", sponsor_id=sponsor_id, study_id=study_id)
    return {
        "sponsor_id": sponsor_id,
        "study_id": study_id,
        "total": len(items),
        "items": [
            {
                "id": i["id"],
                "item_code": i["item_code"],
                "description": i["description"],
                "category": i["category"],
                "unit_price": i["unit_price"],
            }
            for i in items
        ],
    }


@mcp.tool()
async def list_sponsors() -> list[dict]:
    """Every sponsor (for the Hub's manual correction picker)."""
    return await refapi.fetch_all("sponsors")


@mcp.tool()
async def list_studies(sponsor_id: int | None = None) -> list[dict]:
    """Every study, optionally for one sponsor (for the Hub's manual correction picker)."""
    return await refapi.fetch_all("studies", sponsor_id=sponsor_id)


@mcp.tool()
async def list_sites() -> list[dict]:
    """Every site (for the Hub's manual correction picker)."""
    return await refapi.fetch_all("sites")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
