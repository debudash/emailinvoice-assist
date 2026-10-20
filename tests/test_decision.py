"""Decision behaviour (ADR-0002): hard checks force a Hold; the LLM review can add a Hold, never clear one."""
from conftest import CATALOG, context, extraction, matching

from invoice_assist.decision import decide
from invoice_assist.models import LineMatch, MatchConfidence, Review


def ok_review(*args) -> Review:
    return Review(concern=None, rationale="All lines match the catalog at catalog prices.")


def worried_review(*args) -> Review:
    return Review(concern="Screening visits billed twice for one patient look unusual.", rationale="Concern noted.")


def run(ex=None, ctx=None, m=None, review=ok_review):
    return decide(ex or extraction(), ctx or context(), m if m is not None else matching(), CATALOG, review)


def test_clean_invoice_submits_with_llm_rationale():
    d = run()
    assert (d.outcome, d.hold_reasons, d.straight_through) == ("submit", [], True)
    assert d.rationale == "All lines match the catalog at catalog prices."


def test_price_above_catalog_is_a_price_variance():
    ex = extraction()
    ex.line_items[0].unit_price, ex.line_items[0].amount, ex.header.total = 450, 450, 1410

    d = run(ex=ex)

    assert d.outcome == "hold" and d.hold_reasons == ["price_variance"]
    assert "450" in d.details[0] and "400" in d.details[0]


def test_zero_priced_catalog_item_billed_is_a_price_variance():
    catalog = [dict(CATALOG[0], unit_price="0.00"), CATALOG[1]]
    d = decide(extraction(), context(), matching(), catalog, ok_review)
    assert "price_variance" in d.hold_reasons


def test_ambiguous_line_holds_even_when_price_picked_a_match():
    m = matching()
    m.matches[1] = LineMatch(line_no=2, catalog_item_id=102, item_code="VISIT-SCR", confidence=MatchConfidence.medium,
                             ambiguous=True, alternatives=["VISIT-SCR-2"], reason="two screening items")
    d = run(m=m)
    assert d.hold_reasons == ["ambiguous"] and "VISIT-SCR-2" in d.details[0]


def test_line_amount_not_qty_times_price_is_arithmetic():
    ex = extraction()
    ex.line_items[1].amount = 900  # 2 x 480 = 960
    ex.header.total = 1300
    assert run(ex=ex).hold_reasons == ["arithmetic"]


def test_lines_not_summing_to_printed_total_is_arithmetic():
    ex = extraction()
    ex.header.total = 1500  # lines sum to 1360
    assert run(ex=ex).hold_reasons == ["arithmetic"]


def test_llm_concern_adds_a_hold_to_a_clean_invoice():
    d = run(review=worried_review)
    assert d.outcome == "hold" and d.hold_reasons == ["llm_concern"]
    assert "Screening visits" in d.details[0]


def test_llm_cannot_clear_a_hard_check_hold():
    # The review says everything is fine; the unmatched line still holds (ADR-0002).
    d = run(m=matching(unmatched_line=1), review=ok_review)
    assert d.outcome == "hold" and "unmatched" in d.hold_reasons and not d.straight_through


def test_review_sees_the_hard_check_findings():
    seen = {}

    def spy(ex, ctx, m, catalog, findings):
        seen["findings"] = findings
        return ok_review()

    run(m=matching(unmatched_line=1), review=spy)
    assert [reason for reason, _ in seen["findings"]] == ["unmatched"]
