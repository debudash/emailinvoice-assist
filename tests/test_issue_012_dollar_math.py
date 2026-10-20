"""ISSUE-012 regression test.

Found by: recording the demo video (2026-10-20). The simple invoice's rationale said "$2,230.00
total ... at the same $400 price", and the Hub drew the text between the two dollar signs as a
LaTeX formula, in a monospace math font.
"""
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT, make_pipeline
from invoice_assist.decision import decide
from invoice_assist.models import LLMReview
from invoice_assist.store import Store
from invoice_assist.worker import ingest
from test_issue_003_004_hub_queue import HUB

RATIONALE = "Submitted: the lines sum to the $2,230.00 total, and the Site Fee is at the same $400 price."


def test_issue_012_dollar_amounts_in_ai_text_are_not_drawn_as_math(tmp_path, monkeypatch):
    import invoice_assist.config as config
    db = tmp_path / "app.db"
    st.cache_resource.clear()
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0, inbox_dir=tmp_path / "inbox"))
    store = Store(db)
    invoice_id = ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0]
    review = lambda *args: LLMReview(concern=None, rationale=RATIONALE)
    pipeline, _ = make_pipeline(store, decide=lambda ex, ctx, m, cat: decide(ex, ctx, m, cat, review))
    assert pipeline.process(invoice_id) == "Submitted"

    at = AppTest.from_file(HUB, default_timeout=30)
    at.session_state["queue_name"] = "Submitted"
    at.run()

    assert not at.exception
    banner = at.success[0].value
    assert r"\$2,230.00" in banner and r"\$400" in banner
