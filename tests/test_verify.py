"""Extracted numbers checked against the document's own text (ADR-0007)."""
from conftest import ROOT, CATALOG, context, extraction, matching

from invoice_assist.decision import decide
from invoice_assist.models import RELEASABLE, HoldReason, LLMReview
from invoice_assist.verify import unverified_values

SIMPLE_PDF = (ROOT / "sample-invoices" / "simple-invoice.pdf").read_bytes()


def ok_review(*args):
    return LLMReview(concern=None, rationale="fine")


def simple_extraction():
    ex = extraction()  # lines 1-2 of the simple invoice; add the rest so the total matches the PDF
    ex.header.total = 2230.0
    return ex


def test_values_printed_on_the_pdf_verify():
    assert unverified_values(SIMPLE_PDF, "application/pdf", simple_extraction()) == []


def test_a_number_not_on_the_pdf_is_reported():
    ex = simple_extraction()
    ex.line_items[1].amount = 690.0  # the PDF says $960.00

    assert unverified_values(SIMPLE_PDF, "application/pdf", ex) == ["line 2 amount 690.00"]


def test_an_invoice_number_not_on_the_pdf_is_reported():
    ex = simple_extraction()
    ex.header.invoice_number = "INV-2024-999"
    assert unverified_values(SIMPLE_PDF, "application/pdf", ex) == ["invoice number INV-2024-999"]


def test_unverified_extraction_holds_and_cannot_be_released():
    ex = extraction()
    ex.unverified = ["line 2 amount 690.00"]

    d = decide(ex, context(), matching(), CATALOG, ok_review)

    assert d.hold_reasons == ["extraction_unverified"] and "690.00" in d.details[0]
    assert HoldReason.extraction_unverified not in RELEASABLE
