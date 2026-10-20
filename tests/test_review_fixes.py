"""Behaviour required by the S0 code review (spec findings a1, a3, a4, c1-c3)."""
import asyncio

from conftest import context, extraction, make_pipeline

from invoice_assist.context import score_context
from invoice_assist.decision import decide
from invoice_assist.models import ContextProposal
from conftest import matching


def test_skipped_matching_never_reports_matched(store, simple_invoice):
    pipeline, _ = make_pipeline(store, resolve=lambda h: context(site_conf=0.6))
    statuses = []
    real = store.set_status
    store.set_status = lambda i, s, failed_stage=None: statuses.append(s) or real(i, s, failed_stage)

    pipeline.process(simple_invoice)

    assert "Matched" not in statuses and statuses[-1] == "Held"


def test_missing_printed_total_holds_instead_of_inventing_one():
    ex = extraction()
    ex.header.total = None

    d = decide(ex, context(), matching())

    assert d.outcome == "hold" and "arithmetic" in d.hold_reasons


def test_study_from_another_sponsor_holds():
    ctx = context()
    ctx.study_belongs_to_sponsor = False

    d = decide(extraction(), ctx, matching())

    assert d.outcome == "hold" and "context_uncertain" in d.hold_reasons


def test_stage_runs_record_their_inputs_and_served_model(store, simple_invoice):
    pipeline, _ = make_pipeline(store)
    pipeline.process(simple_invoice)

    runs = {r["stage"]: r for r in store.stage_runs(simple_invoice)}
    extraction_run = runs["extraction"]["id"]
    assert f'"extraction": {extraction_run}' in runs["context"]["inputs"]
    assert '"context"' in runs["matching"]["inputs"]


# --- computed Context Confidence (ADR-0004/0005), through score_context -------------

REF = {
    "search_sponsors": [{"id": 1, "name": "Northwind Pharma", "score": 1.0}],
    "search_studies": [{"id": 2, "sponsor_id": 1, "name": "VERITAS", "score": 0.938},
                       {"id": 1, "sponsor_id": 1, "name": "LUMIN-2024", "score": 0.75}],
    "search_sites": [{"id": 6, "name": "Prairie Field Research Group", "name_score": 0.78, "pi_score": 1.0, "score": 0.78},
                     {"id": 1, "name": "Willow Creek", "name_score": 0.81, "pi_score": 0.24, "score": 0.81}],
    "list_study_sites": [{"site_id": 2, "status": "active"}, {"site_id": 6, "status": "active"}],
}


async def fake_call(tool, **args):
    return REF[tool]


def mismatched_header():
    h = extraction().header
    h.sponsor_name, h.protocol_number, h.study_name = "Northwind Pharmaceuticals Inc.", "NWD-VER-2024-002", "VERITAS Phase 2 Study"
    h.site_name, h.pi_name = "Prairie Clinical Research", "Dr. Riley H. Foster"
    return h


def test_weak_site_name_stays_uncertain_despite_pi_and_link():
    proposal = ContextProposal(sponsor_id=1, study_id=2, site_id=6, explanation="PI and link agree")

    ctx = asyncio.run(score_context(fake_call, mismatched_header(), proposal))

    assert (ctx.sponsor.confident, ctx.study.confident) == (True, True)
    assert ctx.site.confidence == 0.78 and not ctx.site.confident  # corroboration did not lift it
    assert ctx.site_linked_to_study and ctx.study_belongs_to_sponsor
    assert ctx.site.record_name == "Prairie Field Research Group"  # Suggested Context is the right answer


def test_unproposed_field_scores_zero():
    proposal = ContextProposal(sponsor_id=1, study_id=None, site_id=None, explanation="no study found")

    ctx = asyncio.run(score_context(fake_call, mismatched_header(), proposal))

    assert ctx.study.confidence == 0 and not ctx.study.confident and not ctx.site_linked_to_study


def test_study_found_by_both_protocol_and_name_scores_without_error():
    # Live searches return a different row per query; equal scores must not fall through to comparing rows.
    async def call(tool, **args):
        if tool == "search_studies":
            return [{"id": 3, "sponsor_id": 2, "name": "CATALYST Trial", "score": 1.0, "matched_on": args["query"]}]
        return {"search_sponsors": [{"id": 2, "name": "Contoso Therapeutics", "score": 1.0}],
                "search_sites": [{"id": 1, "name": "Willow Creek", "name_score": 1.0, "score": 1.0}],
                "list_study_sites": [{"site_id": 1, "status": "active"}]}[tool]

    ctx = asyncio.run(score_context(call, extraction().header,
                                    ContextProposal(sponsor_id=2, study_id=3, site_id=1, explanation="exact")))

    assert ctx.confident and ctx.study.confidence == 1.0


def test_failed_stage_run_records_the_underlying_error_not_the_task_group(store, simple_invoice):
    def broken(header):
        raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionRefusedError("ref-mcp down")])
    pipeline, _ = make_pipeline(store, resolve=broken)

    pipeline.process(simple_invoice)

    assert store.stage_runs(simple_invoice)[-1]["error"] == "ConnectionRefusedError: ref-mcp down"
