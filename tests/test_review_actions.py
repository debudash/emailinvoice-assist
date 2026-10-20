"""Review Actions through their interface: Correction, Release, Escalation, rerun, with an audit trail."""
import pytest

from conftest import context, make_pipeline, matching

from invoice_assist.review import ActionRefused, ReviewActions


class FakeReference:
    sponsors = [{"id": 2, "name": "Contoso Therapeutics"}]
    studies = [{"id": 3, "sponsor_id": 2, "name": "CATALYST Trial"}]
    sites = [{"id": 1, "name": "Willow Creek Clinical Research Center"}, {"id": 6, "name": "Prairie Field"}]
    links = {3: [1]}

    def study_sites(self, study_id):
        return self.links.get(study_id, [])


def actions_for(store, **overrides):
    pipeline, clinrun = make_pipeline(store, **overrides)
    return ReviewActions(store, pipeline, FakeReference()), pipeline, clinrun


def held_for_context(store, invoice_id):
    actions, pipeline, clinrun = actions_for(store, resolve=lambda h: context(site_conf=0.6))
    assert pipeline.process(invoice_id) == "Held"
    return actions, clinrun


def test_correcting_context_reruns_matching_and_the_ai_decides(store, simple_invoice):
    actions, clinrun = held_for_context(store, simple_invoice)

    status = actions.correct_context(simple_invoice, "Dana (reviewer)", sponsor_id=2, study_id=3, site_id=1,
                                     note="Site is Willow Creek; header used an old name")

    assert status == "Submitted" and len(clinrun.calls) == 1
    ctx = store.latest_output(simple_invoice, "context")
    assert ctx["site"]["record_id"] == 1 and ctx["site"]["confident"] and ctx["corrected_by"] == "Dana (reviewer)"
    runs = [(r["stage"], r["trigger"]) for r in store.stage_runs(simple_invoice)]
    assert ("context", "correction by Dana (reviewer)") in runs and ("matching", "correction by Dana (reviewer)") in runs
    assert store.actions(simple_invoice)[0]["kind"] == "correct_context"


def test_correction_to_an_unlinked_site_still_holds(store, simple_invoice):
    actions, clinrun = held_for_context(store, simple_invoice)

    status = actions.correct_context(simple_invoice, "Dana", sponsor_id=2, study_id=3, site_id=6, note="try Prairie")

    assert status == "Held" and "site_not_linked" in store.latest_output(simple_invoice, "decision")["hold_reasons"]
    assert clinrun.calls == []


def test_release_submits_a_price_variance_with_reason_and_reviewer(store, simple_invoice):
    actions, pipeline, clinrun = actions_for(store, match=lambda l, c: matching(unmatched_line=1))
    pipeline.process(simple_invoice)

    assert actions.release(simple_invoice, "Dana", "Site fee agreed by sponsor email 2024-03-01") == "Submitted"

    submission, _ = clinrun.calls[0]
    assert submission["release"] == {"reason": "Site fee agreed by sponsor email 2024-03-01", "reviewer": "Dana"}
    assert submission["decision"]["straight_through"] is False


def test_release_needs_a_reason(store, simple_invoice):
    actions, pipeline, _ = actions_for(store, match=lambda l, c: matching(unmatched_line=1))
    pipeline.process(simple_invoice)
    with pytest.raises(ActionRefused, match="reason"):
        actions.release(simple_invoice, "Dana", "  ")


def test_release_is_refused_for_uncertain_context(store, simple_invoice):
    actions, clinrun = held_for_context(store, simple_invoice)
    with pytest.raises(ActionRefused, match="context_uncertain"):
        actions.release(simple_invoice, "Dana", "looks fine to me")
    assert clinrun.calls == []


def test_escalation_needs_a_note_and_moves_to_escalated(store, simple_invoice):
    actions, clinrun = held_for_context(store, simple_invoice)
    with pytest.raises(ActionRefused):
        actions.escalate(simple_invoice, "Dana", "")

    assert actions.escalate(simple_invoice, "Dana", "Unknown site name; ask the study lead") == "Escalated"
    assert store.invoice(simple_invoice)["status"] == "Escalated"


def test_correcting_a_line_match_reruns_the_decision(store, simple_invoice):
    actions, pipeline, clinrun = actions_for(store, match=lambda l, c: matching(unmatched_line=1))
    pipeline.process(simple_invoice)

    status = actions.correct_line(simple_invoice, "Dana", line_no=1, catalog_item_id=101, note="Site Management Fee is the Site Fee")

    assert status == "Submitted"
    line1 = store.latest_output(simple_invoice, "matching")["matches"][0]
    assert line1["item_code"] == "ADMIN-SITE" and line1["corrected_by"] == "Dana"


def test_submitted_invoice_cannot_be_corrected_yet(store, simple_invoice):
    actions, pipeline, _ = actions_for(store)
    pipeline.process(simple_invoice)
    with pytest.raises(ActionRefused, match="Amendment"):
        actions.correct_context(simple_invoice, "Dana", 2, 3, 1, "x")


def test_operator_rerun_from_failed_stage(store, simple_invoice):
    calls = []

    def flaky(header):
        calls.append(1)
        if len(calls) <= 3:  # fails every retry of the first run
            raise ConnectionError("ref-mcp down")
        return context()
    actions, pipeline, _ = actions_for(store, resolve=flaky)
    assert pipeline.process(simple_invoice) == "Failed"

    assert actions.rerun(simple_invoice, "Ops", "context") == "Submitted"
    assert store.actions(simple_invoice)[-1]["kind"] == "rerun"
