"""ISSUE-010 regression test (recorded after the fact; fixed in 98425f5).

Found by: the P1 docs cross-check (2026-10-19). With a price tolerance set, an Invoice the Decision
submitted (price within tolerance) still went to ClinRun with price_variance true on that line.
"""
from conftest import extraction, make_pipeline


def test_issue_010_submission_flags_variance_using_the_same_tolerance_as_the_decision(store, simple_invoice, monkeypatch):
    import invoice_assist.decision as decision
    from invoice_assist.config import Settings
    monkeypatch.setattr(decision, "settings", Settings(price_tolerance=0.02))

    def slightly_high():  # 404.00 against a 400.00 Catalog price: 1%, inside the 2% tolerance
        ex = extraction()
        ex.line_items[0].unit_price, ex.line_items[0].amount, ex.header.total = 404, 404, 1364
        return ex
    pipeline, clinrun = make_pipeline(store, extract=lambda d, mt: slightly_high())

    assert pipeline.process(simple_invoice) == "Submitted"
    assert clinrun.calls[0][0]["lines"][0]["price_variance"] is False
