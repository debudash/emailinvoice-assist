"""ISSUE-006 regression test.

Found by: the /code-review Spec reviewer (2026-10-20). The queue table remembers a row position, so
when a new Invoice arrived (newest first) the detail jumped to a different Invoice on its own.
"""
from streamlit.testing.v1 import AppTest

from conftest import ROOT, context, make_pipeline
from invoice_assist.store import Store
from invoice_assist.worker import ingest
from test_issue_003_004_hub_queue import HUB, hub_with_submitted_and_held


def add_held(store: Store) -> int:
    invoice_id = ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0]
    make_pipeline(store, resolve=lambda h: context(site_conf=0.6))[0].process(invoice_id)
    return invoice_id


def test_issue_006_detail_stays_on_the_chosen_invoice_when_a_new_one_arrives(tmp_path, monkeypatch):
    _, older = hub_with_submitted_and_held(tmp_path, monkeypatch)
    store = Store(tmp_path / "app.db")
    add_held(store)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()
    table = at.dataframe[0]
    row = list(table.value["id"]).index(older)
    at.session_state[table.key] = {"selection": {"rows": [row], "columns": [], "cells": []}}  # the Reviewer ticks it
    at.run()
    assert at.header[0].value.startswith(f"Invoice {older}:")

    add_held(store)  # arrives while the Reviewer is reading; the queue refreshes
    at.run()

    assert not at.exception
    assert at.header[0].value.startswith(f"Invoice {older}:")
