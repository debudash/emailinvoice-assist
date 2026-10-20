"""Extraction Stage: the invoice document goes to Claude natively (ADR-0007)."""
import base64

from . import llm
from .models import Extraction

SYSTEM = """You read clinical trial site invoices and transcribe them exactly.
Copy every header field and every line item as printed: do not correct spelling,
normalise names, or fix arithmetic. Use null for a field that is not on the invoice.
Dates as YYYY-MM-DD. Numbers as plain numbers without currency symbols.
Number line items from 1 in the order they appear."""


def extract(data: bytes, media_type: str) -> Extraction:
    document = {
        "type": "document",
        "source": {"type": "base64", "media_type": media_type,
                   "data": base64.standard_b64encode(data).decode()},
    }
    return llm.parse(Extraction, SYSTEM,
                     [document, {"type": "text", "text": "Transcribe this invoice."}],
                     effort="medium")
