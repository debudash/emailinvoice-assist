"""Shared fakes for the LLM and MCP seams, built from the simple sample's real values."""
from pathlib import Path

import pytest

from invoice_assist.models import (Context, ContextField, Extraction, InvoiceHeader, LineItem, LineMatch,
                                   Matching, MatchConfidence)
from invoice_assist.pipeline import Pipeline, Stages
from invoice_assist.store import Store
from invoice_assist.worker import ingest

ROOT = Path(__file__).resolve().parent.parent
SIMPLE_EML = ROOT / "samples" / "emails" / "01-simple-invoice.eml"

CATALOG = [
    {"id": 101, "item_code": "ADMIN-SITE", "description": "Site Fee", "category": "administrative", "unit_price": "400.00"},
    {"id": 102, "item_code": "VISIT-SCR", "description": "Screening Visit", "category": "patient_visits", "unit_price": "480.00"},
]


def extraction() -> Extraction:
    return Extraction(
        header=InvoiceHeader(invoice_number="INV-2024-001", invoice_date="2024-03-15",
                             site_name="Willow Creek Clinical Research Center", pi_name="Dr. Alex Morgan",
                             sponsor_name="Contoso Therapeutics", study_name="CATALYST Trial",
                             protocol_number="CON-CAT-2024-101", total=1360.0),
        line_items=[LineItem(line_no=1, description="Site Management Fee", quantity=1, unit_price=400, amount=400),
                    LineItem(line_no=2, description="Screening Visit", quantity=2, unit_price=480, amount=960)])


def field(record_id, name, conf=1.0) -> ContextField:
    return ContextField(record_id=record_id, record_name=name, header_text=name, confidence=conf,
                        confident=conf >= 0.85)


def context(site_conf=1.0, linked=True) -> Context:
    return Context(sponsor=field(2, "Contoso Therapeutics"), study=field(3, "CATALYST Trial"),
                   site=field(1, "Willow Creek Clinical Research Center", site_conf),
                   site_linked_to_study=linked, study_belongs_to_sponsor=True, explanation="fake")


def matching(unmatched_line: int | None = None) -> Matching:
    return Matching(matches=[
        LineMatch(line_no=1, catalog_item_id=None if unmatched_line == 1 else 101,
                  item_code=None if unmatched_line == 1 else "ADMIN-SITE",
                  confidence=MatchConfidence.high, ambiguous=False, reason="fake"),
        LineMatch(line_no=2, catalog_item_id=102, item_code="VISIT-SCR",
                  confidence=MatchConfidence.high, ambiguous=False, reason="fake")])


class FakeClinRun:
    def __init__(self):
        self.calls = []

    def __call__(self, submission, key):
        self.calls.append((submission, key))
        return "CR-000001"


@pytest.fixture
def store():
    return Store(":memory:")


@pytest.fixture
def simple_invoice(store):
    return ingest(store, SIMPLE_EML)[0]


def make_pipeline(store, **overrides) -> tuple[Pipeline, FakeClinRun]:
    clinrun = overrides.pop("submit", FakeClinRun())
    stages = Stages(extract=lambda data, mt: extraction(), resolve=lambda header: context(),
                    catalog=lambda s, st: CATALOG, match=lambda lines, cat: matching(), submit=clinrun)
    for name, fn in overrides.items():
        setattr(stages, name, fn)
    return Pipeline(store, stages), clinrun
