"""Hub component test: renders the queue and the detail of a processed invoice."""
from streamlit.testing.v1 import AppTest

from conftest import ROOT, make_pipeline
from invoice_assist.store import Store
from invoice_assist.worker import ingest

HUB = str(ROOT / "src" / "invoice_assist" / "hub.py")


def test_hub_shows_submitted_invoice_with_clinrun_id(tmp_path, monkeypatch):
    db = tmp_path / "app.db"
    store = Store(db)
    invoice_id = ingest(store, ROOT / "samples" / "emails" / "01-simple-invoice.eml")[0]
    make_pipeline(store)[0].process(invoice_id)
    monkeypatch.setenv("APP_DB", str(db))

    at = AppTest.from_file(HUB, default_timeout=30)
    import invoice_assist.config as config
    monkeypatch.setattr(config, "settings", config.Settings(db_path=db, hub_refresh_seconds=0))
    at.session_state["selected"] = invoice_id
    at.run()

    assert not at.exception
    assert "CR-000001" in at.success[0].proto.title
    assert any("Stage runs" in h.value for h in at.subheader)
