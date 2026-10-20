"""ISSUE-008 regression tests.

Found by: the developer, in the hands-on run-through (2026-10-20). "Correct a line" listed every
line in invoice order, the Matched table did not say which lines were the problem, and "Correct
context" looked necessary even when the Context was confident.
"""
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT, extraction, make_pipeline, matching
from invoice_assist.review import ReviewActions
from invoice_assist.store import Store
from invoice_assist.worker import ingest
from test_issue_003_004_hub_queue import HUB
from test_review_actions import FakeReference


def line_2_overbilled():
    ex = extraction()
    ex.line_items[1].unit_price, ex.line_items[1].amount = 500, 1000  # catalog VISIT-SCR is 480.00
    ex.header.total = 1400.0
    return ex


def hub_with_two_flagged_lines(tmp_path, monkeypatch):
    """Line 1 Unmatched, line 2 a Price Variance."""
    import invoice_assist.config as config
    db = tmp_path / "app.db"
    st.cache_resource.clear()
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0, inbox_dir=tmp_path / "inbox"))
    store = Store(db)
    invoice_id = ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0]
    pipeline, _ = make_pipeline(store, extract=lambda data, mt: line_2_overbilled(),
                                match=lambda lines, cat: matching(unmatched_line=1))
    assert pipeline.process(invoice_id) == "Held"
    return store, pipeline, invoice_id


def line_choices(at):
    return next(s for s in at.selectbox if s.label == "Line").options


def test_issue_008_matched_table_flags_the_problem_lines_first(tmp_path, monkeypatch):
    hub_with_two_flagged_lines(tmp_path, monkeypatch)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()

    table = next(d.value for d in at.dataframe if "issue" in d.value.columns)
    assert list(table["issue"]) == ["unmatched", "price_variance"]


def test_issue_008_correct_a_line_lists_only_flagged_lines_and_drops_a_fixed_one(tmp_path, monkeypatch):
    store, pipeline, invoice_id = hub_with_two_flagged_lines(tmp_path, monkeypatch)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()
    assert [c.split(":")[0] for c in line_choices(at)] == ["1", "2"]
    assert "unmatched" in line_choices(at)[0] and "price_variance" in line_choices(at)[1]

    ReviewActions(store, pipeline, FakeReference()).correct_line(invoice_id, "Dana", 1, 101, "Site fee item")
    at.run()

    assert not at.exception
    assert [c.split(":")[0] for c in line_choices(at)] == ["2"]


def test_issue_008_correct_context_says_when_the_context_is_already_confident(tmp_path, monkeypatch):
    hub_with_two_flagged_lines(tmp_path, monkeypatch)
    at = AppTest.from_file(HUB, default_timeout=30)
    at.run()

    assert any("Context is confident" in c.value for c in at.caption)
