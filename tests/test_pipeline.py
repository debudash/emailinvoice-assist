"""Pipeline behaviour through its interface, with fakes at the LLM/MCP/ClinRun seams."""
from conftest import context, make_pipeline, matching

from invoice_assist.intake import parse_eml
from invoice_assist.worker import ingest


def test_clean_invoice_runs_every_stage_and_submits(store, simple_invoice):
    pipeline, clinrun = make_pipeline(store)

    assert pipeline.process(simple_invoice) == "Submitted"

    assert store.invoice(simple_invoice)["status"] == "Submitted"
    assert [r["stage"] for r in store.stage_runs(simple_invoice)] == \
        ["extraction", "context", "matching", "decision", "submission"]
    assert store.submission(simple_invoice)["clinrun_id"] == "CR-000001"
    submission, key = clinrun.calls[0]
    assert submission["context"] == {"sponsor_id": 2, "study_id": 3, "site_id": 1}
    assert [l["item_code"] for l in submission["lines"]] == ["ADMIN-SITE", "VISIT-SCR"]
    assert submission["lines"][0]["description_as_billed"] == "Site Management Fee"
    assert submission["decision"]["straight_through"] is True


def test_uncertain_context_skips_matching_and_holds(store, simple_invoice):
    calls = []
    pipeline, clinrun = make_pipeline(store, resolve=lambda h: context(site_conf=0.6),
                                      match=lambda lines, cat: calls.append(1) or matching())

    assert pipeline.process(simple_invoice) == "Held"

    assert calls == []  # matching never ran against a Catalog chosen from an uncertain Context
    assert store.latest_output(simple_invoice, "matching")["skipped"] is True
    assert "context_uncertain" in store.latest_output(simple_invoice, "decision")["hold_reasons"]
    assert clinrun.calls == []


def test_unmatched_line_holds_and_never_submits(store, simple_invoice):
    pipeline, clinrun = make_pipeline(store, match=lambda lines, cat: matching(unmatched_line=1))

    assert pipeline.process(simple_invoice) == "Held"
    assert store.latest_output(simple_invoice, "decision")["hold_reasons"] == ["unmatched"]
    assert clinrun.calls == []


def test_stage_failure_marks_failed_at_that_stage(store, simple_invoice):
    def broken(header):
        raise ConnectionError("ref-mcp unreachable")
    pipeline, _ = make_pipeline(store, resolve=broken)

    assert pipeline.process(simple_invoice) == "Failed"

    inv = store.invoice(simple_invoice)
    assert (inv["status"], inv["failed_stage"]) == ("Failed", "context")
    assert store.stage_runs(simple_invoice)[-1]["error"].startswith("ConnectionError")


def test_rerun_from_a_stage_adds_stage_runs_without_overwriting(store, simple_invoice):
    pipeline, _ = make_pipeline(store, resolve=lambda h: (_ for _ in ()).throw(TimeoutError()))
    pipeline.process(simple_invoice)
    fixed, _ = make_pipeline(store)

    assert fixed.process(simple_invoice, from_stage="context", trigger="operator rerun") == "Submitted"

    context_runs = [r for r in store.stage_runs(simple_invoice) if r["stage"] == "context"]
    assert [(r["run_no"], r["outcome"]) for r in context_runs] == [(1, "failed"), (2, "succeeded")]
    assert [r["stage"] for r in store.stage_runs(simple_invoice)].count("extraction") == 1


def test_message_without_pdf_is_rejected_not_dropped(store, tmp_path):
    eml = tmp_path / "no-attachment.eml"
    eml.write_text("From: site@example.org\nSubject: see attached\nDate: Mon, 19 Oct 2026 09:00:00 +0000\n\nForgot it.\n")

    assert ingest(store, eml) == []
    assert parse_eml(eml).rejection_reason == "No PDF attachment"
    assert store.rejected_messages()[0]["subject"] == "see attached"
