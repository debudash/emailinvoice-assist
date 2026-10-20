"""ISSUE-003 and ISSUE-004 regression tests.

Found by: the developer, using the Hub (2026-10-20). ISSUE-003: with the Held queue selected and a
Held row ticked, the detail still showed Submitted "Invoice 1". ISSUE-004: the status column showed
":material/pause_circle:" as literal text.
"""
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT, context, make_pipeline
from invoice_assist.store import Store
from invoice_assist.worker import ingest

HUB = str(ROOT / "src" / "invoice_assist" / "hub.py")


def hub_with_submitted_and_held(tmp_path, monkeypatch):
    import invoice_assist.config as config
    db = tmp_path / "app.db"
    st.cache_resource.clear()
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0, inbox_dir=tmp_path / "inbox"))
    store = Store(db)
    eml = ROOT / "samples" / "emails" / "01-simple-invoice.eml"
    submitted = ingest(store, eml)[0]
    make_pipeline(store)[0].process(submitted)
    held = ingest(store, eml)[0]
    make_pipeline(store, resolve=lambda h: context(site_conf=0.6))[0].process(held)
    return submitted, held


def test_issue_003_detail_shows_an_invoice_from_the_selected_queue(tmp_path, monkeypatch):
    submitted, held = hub_with_submitted_and_held(tmp_path, monkeypatch)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.session_state["selected"] = submitted  # left over from browsing another queue
    at.run()  # the default queue is Held

    assert not at.exception
    assert at.header[0].value.startswith(f"Invoice {held}:")


def test_issue_004_status_column_has_no_icon_markup(tmp_path, monkeypatch):
    hub_with_submitted_and_held(tmp_path, monkeypatch)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()

    statuses = list(at.dataframe[0].value["status"])
    assert statuses and not any(":material/" in s for s in statuses)
