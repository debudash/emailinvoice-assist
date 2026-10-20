"""ISSUE-005 regression test.

Found by: the /code-review Spec reviewer (2026-10-20). A scanned PDF (no text layer) failed every
number check and held as extraction_unverified, a Hold no Reviewer can Release or correct.
"""
import io

from PIL import Image

from conftest import CATALOG, context, extraction, matching
from invoice_assist.decision import decide
from invoice_assist.models import RELEASABLE, LLMReview
from invoice_assist.verify import unverified_values


def scanned_pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (612, 792), "white").save(buf, format="PDF")  # a page that is only a picture
    return buf.getvalue()


def test_issue_005_scanned_pdf_holds_as_unverifiable_not_unverified():
    ex = extraction()
    ex.unverified = unverified_values(scanned_pdf(), "application/pdf", ex)

    d = decide(ex, context(), matching(), CATALOG, lambda *args: LLMReview(concern=None, rationale="fine"))

    assert d.hold_reasons == ["extraction_unverifiable"]
    assert "no text layer" in d.details[0]
    assert set(d.hold_reasons) <= RELEASABLE
