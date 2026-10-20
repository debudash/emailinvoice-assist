"""ISSUE-007 regression tests.

Found by: the developer, in the hands-on run-through (2026-10-20). Invoice 2 held for a Price
Variance; two Corrections that changed nothing (the same Catalog Item, the same Context) were
accepted and reran the AI, which held it again, and the Hub never said that Release clears it.
"""
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT, extraction, make_pipeline
from invoice_assist.review import ActionRefused
from invoice_assist.store import Store
from invoice_assist.worker import ingest
from test_issue_003_004_hub_queue import HUB
from test_review_actions import FakeReference, actions_for


def overbilled():
    ex = extraction()
    ex.line_items[0].unit_price = ex.line_items[0].amount = 450  # catalog ADMIN-SITE is 400.00
    ex.header.total = 1410.0
    return ex


def held_for_price(store, invoice_id):
    actions, pipeline, clinrun = actions_for(store, extract=lambda data, mt: overbilled())
    assert pipeline.process(invoice_id) == "Held"
    return actions


def test_issue_007_a_line_correction_that_changes_nothing_is_refused(store, simple_invoice):
    actions = held_for_price(store, simple_invoice)

    with pytest.raises(ActionRefused, match="Release"):
        actions.correct_line(simple_invoice, "Dana", line_no=1, catalog_item_id=101, note="match the catalog price")
    assert store.actions(simple_invoice) == []


def test_issue_007_a_context_correction_that_changes_nothing_is_refused(store, simple_invoice):
    actions = held_for_price(store, simple_invoice)

    with pytest.raises(ActionRefused, match="already"):
        actions.correct_context(simple_invoice, "Dana", sponsor_id=2, study_id=3, site_id=1, note="fixed the price")
    assert store.actions(simple_invoice) == []


def test_issue_007_hub_says_what_clears_a_price_variance(tmp_path, monkeypatch):
    import invoice_assist.config as config
    db = tmp_path / "app.db"
    st.cache_resource.clear()
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0, inbox_dir=tmp_path / "inbox"))
    store = Store(db)
    held_for_price(store, ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0])

    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()

    assert not at.exception
    assert any("Release to accept it as billed" in el.value for el in at.markdown)
