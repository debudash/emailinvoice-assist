"""ref-mcp tools against the reference API running in Compose (http://localhost:8000)."""

import pytest

import refapi
import server

pytestmark = pytest.mark.live


async def test_mismatched_sponsor_ranks_northwind_first():
    results = await server.search_sponsors("Northwind Pharmaceuticals Inc.")
    assert results[0]["name"] == "Northwind Pharma"
    assert results[0]["score"] >= 0.9


async def test_exact_sponsor_scores_one():
    results = await server.search_sponsors("Contoso Therapeutics")
    assert results[0]["name"] == "Contoso Therapeutics"
    assert results[0]["score"] == 1.0


async def test_results_sorted_and_limited():
    results = await server.search_sponsors("Pharma", limit=2)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]


async def test_wrong_year_protocol_finds_veritas():
    results = await server.search_studies("NWD-VER-2024-002")
    top = results[0]
    assert top["id"] == 2 and top["name"] == "VERITAS"
    assert 0.85 <= top["protocol_score"] < 1.0
    assert top["score"] == max(top["name_score"], top["protocol_score"])


async def test_studies_filtered_by_sponsor():
    results = await server.search_studies("CATALYST", sponsor_id=2)
    assert {r["sponsor_id"] for r in results} == {2}
    assert results[0]["id"] == 3


async def test_mismatched_site_ranked_by_pi_but_name_score_stays_weak():
    results = await server.search_sites("Prairie Clinical Research", pi_name="Dr. Riley H. Foster")
    top = results[0]
    assert top["id"] == 6
    assert top["score"] == top["name_score"] < 0.9
    assert top["pi_score"] >= 0.9


async def test_exact_site_scores_one_and_pi_null():
    results = await server.search_sites("Willow Creek Clinical Research Center")
    assert results[0]["id"] == 1 and results[0]["score"] == 1.0
    assert results[0]["pi_score"] is None


async def test_list_study_sites():
    assert await server.list_study_sites(2) == [
        {"site_id": 2, "status": "active"},
        {"site_id": 6, "status": "active"},
    ]


async def test_lumin_catalog_is_complete():
    catalog = await server.get_catalog(1, 1)
    assert catalog["total"] == 100
    assert len(catalog["items"]) == 100
    assert len({i["id"] for i in catalog["items"]}) == 100
    assert set(catalog["items"][0]) == {"id", "item_code", "description", "category", "unit_price"}


async def test_paging_follows_every_page(monkeypatch):
    # Tiny pages make the 8 sites and the 100-item Catalog span several pages.
    monkeypatch.setattr(refapi, "DEFAULT_MAX_PAGE_SIZE", 3)
    monkeypatch.setattr(refapi, "MAX_PAGE_SIZE", {"catalog-items": 30})
    assert len(await server.list_sites()) == 8
    assert len((await server.get_catalog(1, 1))["items"]) == 100


async def test_list_tools_return_everything():
    assert len(await server.list_sponsors()) == 4
    assert len(await server.list_studies()) == 6
    assert {s["sponsor_id"] for s in await server.list_studies(sponsor_id=1)} == {1}
    assert len(await server.list_sites()) == 8
