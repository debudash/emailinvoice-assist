"""Release at catalog price: a Price Variance paid at the Catalog price, the billed price kept."""
import pytest

from conftest import matching
from invoice_assist.review import ActionRefused
from test_issue_007_hold_guidance import held_for_price
from test_review_actions import actions_for


def test_release_at_catalog_price_submits_catalog_prices_and_keeps_what_was_billed(store, simple_invoice):
    actions = held_for_price(store, simple_invoice)  # line 1 billed 450.00, catalog 400.00

    assert actions.release(simple_invoice, "Dana", "Pay the agreed site fee", at_catalog_price=True) == "Submitted"

    submission, _ = actions.pipeline.stages.submit.calls[0]
    line1, line2 = submission["lines"]
    assert (line1["unit_price"], line1["amount"]) == (400.0, 400.0)
    assert (line1["billed_unit_price"], line1["billed_amount"]) == (450.0, 450.0) and line1["price_variance"]
    assert line2["unit_price"] == 480.0 and line2["billed_unit_price"] is None
    assert submission["release"] == {"reason": "Pay the agreed site fee", "reviewer": "Dana", "at_catalog_price": True}
    assert store.actions(simple_invoice)[-1]["kind"] == "release_at_catalog_price"


def test_release_as_billed_still_submits_the_billed_price(store, simple_invoice):
    actions = held_for_price(store, simple_invoice)

    actions.release(simple_invoice, "Dana", "Fee increase agreed")

    submission, _ = actions.pipeline.stages.submit.calls[0]
    assert submission["lines"][0]["unit_price"] == 450.0
    assert submission["release"] == {"reason": "Fee increase agreed", "reviewer": "Dana", "at_catalog_price": False}


def test_release_at_catalog_price_needs_a_price_variance(store, simple_invoice):
    actions, pipeline, _ = actions_for(store, match=lambda l, c: matching(unmatched_line=1))
    pipeline.process(simple_invoice)

    with pytest.raises(ActionRefused, match="Price Variance"):
        actions.release(simple_invoice, "Dana", "pay catalog", at_catalog_price=True)


def test_operator_rerun_of_a_failed_submission_keeps_the_catalog_price(store, simple_invoice):
    actions = held_for_price(store, simple_invoice)
    calls = []

    def down(submission, key):
        calls.append(submission)
        raise ConnectionError("ClinRun down")
    actions.pipeline.stages.submit = down
    assert actions.release(simple_invoice, "Dana", "Pay catalog", at_catalog_price=True) == "Failed"

    actions.pipeline.stages.submit = lambda submission, key: calls.append(submission) or "CR-000002"
    assert actions.rerun(simple_invoice, "Ops", "submission") == "Submitted"
    assert calls[-1]["lines"][0]["unit_price"] == 400.0 and calls[-1]["release"]["at_catalog_price"]
