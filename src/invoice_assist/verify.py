"""Check extracted numbers against the document's own text layer (ADR-0007).

Guards against a misread or invented figure: every unit price, line amount and the total, and the
invoice number, must appear in the PDF's text. Images have no text layer and are handled by the
extraction_unverifiable Hold instead.
"""
import io
import re
from decimal import Decimal

import pdfplumber

from .models import Extraction

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def document_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def unverified_values(data: bytes, media_type: str, extraction: Extraction) -> list[str]:
    """Extracted values that do not appear in the document text; empty means verified."""
    if media_type != "application/pdf":
        return []
    text = document_text(data)
    printed = {_money(n.replace(",", "")) for n in NUMBER.findall(text)}
    missing = []
    if extraction.header.invoice_number.lower() not in text.lower():
        missing.append(f"invoice number {extraction.header.invoice_number}")
    for line in extraction.line_items:
        for label, value in (("unit price", line.unit_price), ("amount", line.amount)):
            if _money(value) not in printed:
                missing.append(f"line {line.line_no} {label} {_money(value)}")
    if extraction.header.total is not None and _money(extraction.header.total) not in printed:
        missing.append(f"total {_money(extraction.header.total)}")
    return missing
