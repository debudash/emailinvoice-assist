"""Domain models. Names follow GLOSSARY.md."""
from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema


# --- Extraction ---------------------------------------------------------------

class InvoiceHeader(BaseModel):
    """The header text exactly as printed on the Invoice, before resolution."""
    invoice_number: str
    invoice_date: str = Field(description="ISO date YYYY-MM-DD")
    site_name: str
    pi_name: str | None = None
    sponsor_name: str
    study_name: str | None = None
    protocol_number: str | None = None
    total: float | None = Field(None, description="Invoice total as printed")


class LineItem(BaseModel):
    """One billed row as the site wrote it."""
    line_no: int
    description: str
    quantity: float
    unit_price: float
    amount: float


class Extraction(BaseModel):
    header: InvoiceHeader
    line_items: list[LineItem]
    # Set by the Stage, never by the LLM (kept out of the output schema).
    source_media_type: SkipJsonSchema[str] = "application/pdf"


# --- Context ------------------------------------------------------------------

class ContextProposal(BaseModel):
    """What the context agent proposes after searching reference data."""
    sponsor_id: int | None
    study_id: int | None
    site_id: int | None
    explanation: str = Field(description="How the candidates were chosen, citing the header text")


class ContextField(BaseModel):
    """One resolved field with its computed Context Confidence (ADR-0004)."""
    record_id: int | None
    record_name: str | None
    header_text: str | None
    confidence: float
    confident: bool


class Context(BaseModel):
    sponsor: ContextField
    study: ContextField
    site: ContextField
    site_linked_to_study: bool
    study_belongs_to_sponsor: bool
    explanation: str
    agent_lookups: list[str] = []
    corrected_by: str | None = None

    @property
    def confident(self) -> bool:
        return self.sponsor.confident and self.study.confident and self.site.confident


# --- Matching -----------------------------------------------------------------

class MatchConfidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class LineMatch(BaseModel):
    line_no: int
    catalog_item_id: int | None = Field(description="null when Unmatched")
    item_code: str | None
    confidence: MatchConfidence
    ambiguous: bool = Field(description="true when more than one Catalog Item is plausible")
    alternatives: list[str] = Field(default_factory=list, description="item_codes of other plausible items")
    reason: str
    corrected_by: SkipJsonSchema[str | None] = None


class Matching(BaseModel):
    matches: list[LineMatch]


# --- Decision -----------------------------------------------------------------

class HoldReason(StrEnum):
    context_uncertain = "context_uncertain"
    site_not_linked = "site_not_linked"
    unmatched = "unmatched"
    ambiguous = "ambiguous"
    price_variance = "price_variance"
    arithmetic = "arithmetic"
    extraction_unverifiable = "extraction_unverifiable"
    llm_concern = "llm_concern"


# Hold Reasons a Reviewer may Release with a reason; the rest need a Correction (PRD: Thresholds and rules).
RELEASABLE = {HoldReason.price_variance, HoldReason.unmatched, HoldReason.ambiguous, HoldReason.llm_concern,
              HoldReason.extraction_unverifiable}


class Outcome(StrEnum):
    submit = "submit"
    hold = "hold"


class InvoiceStatus(StrEnum):
    received = "Received"
    extracted = "Extracted"
    context_resolved = "Context Resolved"
    matched = "Matched"
    submitted = "Submitted"
    held = "Held"
    failed = "Failed"
    escalated = "Escalated"


class LLMReview(BaseModel):
    """The LLM's review of an Invoice after the hard checks (ADR-0002)."""
    concern: str | None = Field(description="A specific risk the hard checks did not cover, or null")
    rationale: str = Field(description="Two or three sentences explaining the outcome to a Reviewer")


class Decision(BaseModel):
    outcome: Outcome
    hold_reasons: list[HoldReason]
    details: list[str] = Field(default_factory=list, description="One human-readable line per finding")
    rationale: str
    straight_through: bool
