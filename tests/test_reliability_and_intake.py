"""Retries (ADR-0009), image and upload intake, and metrics."""
from email.message import EmailMessage

from conftest import context, make_pipeline

from invoice_assist import metrics
from invoice_assist.intake import parse_eml
from invoice_assist.models import Extraction
from invoice_assist.worker import ingest
from conftest import extraction


def test_transient_failure_is_retried_and_the_attempts_recorded(store, simple_invoice):
    calls = []

    def flaky(header):
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("slow")
        return context()
    pipeline, _ = make_pipeline(store, resolve=flaky)

    assert pipeline.process(simple_invoice) == "Submitted"
    context_run = [r for r in store.stage_runs(simple_invoice) if r["stage"] == "context"][0]
    assert context_run["attempts"] == 3 and context_run["outcome"] == "succeeded"


def test_retries_exhausted_marks_failed_with_attempts(store, simple_invoice):
    def down(header):
        raise ConnectionError("ref-mcp down")
    pipeline, _ = make_pipeline(store, resolve=down)

    assert pipeline.process(simple_invoice) == "Failed"
    assert store.stage_runs(simple_invoice)[-1]["attempts"] == 3


def eml_with(tmp_path, filename, maintype, subtype, source=None):
    msg = EmailMessage()
    msg["From"], msg["Subject"], msg["Date"] = "site@example.org", "invoice", "Mon, 19 Oct 2026 09:00:00 +0000"
    if source:
        msg["X-Invoice-Source"] = source
    msg.set_content("attached")
    msg.add_attachment(b"\x89PNG fake", maintype=maintype, subtype=subtype, filename=filename)
    path = tmp_path / f"{filename}.eml"
    path.write_bytes(bytes(msg))
    return path


def test_image_attachment_is_an_invoice(tmp_path):
    m = parse_eml(eml_with(tmp_path, "invoice.png", "image", "png"))
    assert m.rejection_reason is None and m.invoices[0].media_type == "image/png"


def test_upload_is_recorded_as_its_source(store, tmp_path):
    ingest(store, eml_with(tmp_path, "invoice.png", "image", "png", source="upload"))
    assert store.db.execute("SELECT source FROM messages").fetchone()[0] == "upload"


def test_image_invoice_holds_as_extraction_unverifiable(store, tmp_path):
    invoice_id = ingest(store, eml_with(tmp_path, "invoice.png", "image", "png"))[0]

    def extract_image(data, media_type):
        ex = extraction()
        ex.source_media_type = media_type
        return ex
    pipeline, clinrun = make_pipeline(store, extract=extract_image)

    assert pipeline.process(invoice_id) == "Held"
    assert store.latest_output(invoice_id, "decision")["hold_reasons"] == ["extraction_unverifiable"]
    assert clinrun.calls == []


def test_metrics_report_straight_through_and_time_saved(store, simple_invoice):
    make_pipeline(store)[0].process(simple_invoice)

    summary = metrics.summary(store, minutes_per_invoice=5, minutes_per_line=1)

    assert summary["invoices"] == 1 and summary["straight_through_rate"] == 1.0
    assert summary["manual_minutes"] == 5 + 2  # two line items
    assert summary["holds_by_reason"] == {}
    assert Extraction  # model import kept for readability of the image test
