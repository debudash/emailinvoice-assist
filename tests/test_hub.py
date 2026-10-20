"""Hub component tests: a submitted invoice, and a held one with its actions."""
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT, context, make_pipeline
from invoice_assist.store import Store
from invoice_assist.worker import ingest

HUB = str(ROOT / "src" / "invoice_assist" / "hub.py")


@pytest.fixture
def hub(tmp_path, monkeypatch):
    import invoice_assist.config as config
    import invoice_assist.context as ctx_module
    db = tmp_path / "app.db"
    st.cache_resource.clear()  # the Hub caches its Store; each test has its own database
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0, inbox_dir=tmp_path / "inbox"))
    monkeypatch.setattr(ctx_module.Reference, "load", classmethod(lambda cls: cls(
        [{"id": 2, "name": "Contoso Therapeutics"}],
        [{"id": 3, "sponsor_id": 2, "name": "CATALYST Trial", "protocol_number": "CON-CAT-2024-101"}],
        [{"id": 1, "name": "Willow Creek Clinical Research Center", "pi_name": "Dr. Alex Morgan"}])))
    store = Store(db)
    invoice_id = ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0]

    def open_hub(queue="Held", **pipeline_overrides):
        make_pipeline(store, **pipeline_overrides)[0].process(invoice_id)
        at = AppTest.from_file(HUB, default_timeout=30)
        at.session_state["queue_name"] = queue
        at.session_state["selected"] = invoice_id
        at.run()
        return at
    return open_hub


def test_submitted_invoice_shows_clinrun_id_and_history(hub):
    at = hub(queue="Submitted")
    assert not at.exception
    assert "CR-000001" in at.success[0].proto.title
    assert any("History" in h.value for h in at.subheader)


def test_held_invoice_offers_actions_and_locks_release_for_context(hub):
    at = hub(resolve=lambda h: context(site_conf=0.6))
    assert not at.exception
    assert "context_uncertain" in at.warning[0].proto.title
    assert any("Act on this invoice" in h.value for h in at.subheader)
    assert any("needs a Correction" in i.value for i in at.info)
