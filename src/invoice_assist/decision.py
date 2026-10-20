"""Decision Stage: hard checks force a Hold; the LLM can add Holds, never clear them (ADR-0002).

Every check is a pure function returning findings, with one shared signature. The LLM review
always runs to write the rationale (see the ADR-0002 note in decisions.md); it is told the
computed outcome and may raise a concern, which adds a Hold. The outcome is computed here, in
code: any finding means Hold, whatever the review says.
"""
import json
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal

from . import llm
from .config import settings
from .models import Context, Decision, Extraction, HoldReason, LLMReview, MatchConfidence, Matching, Outcome

Finding = tuple[HoldReason, str]
CENT = Decimal("0.01")


def money(value) -> Decimal:
    """Exact money: from the printed decimal string, rounded half up like an invoice."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def is_price_variance(billed, catalog_price) -> bool:
    """Billed unit price outside the tolerance of the catalog price ($0.00 taken literally)."""
    billed, catalog_price = money(billed), money(catalog_price)
    return abs(billed - catalog_price) > catalog_price * Decimal(str(settings.price_tolerance))


def check_source(extraction: Extraction, context: Context, matching: Matching | None, catalog: dict) -> list[Finding]:
    # An image has no text layer to check extracted numbers against (ADR-0007): a human glances first.
    if extraction.source_media_type.startswith("image/"):
        return [(HoldReason.extraction_unverifiable,
                 f"Read from an image ({extraction.source_media_type}); numbers not verifiable")]
    # Values the model extracted that are not printed on the document (ADR-0007): never Releasable.
    return [(HoldReason.extraction_unverified, f"Extracted {value} does not appear on the document")
            for value in extraction.unverified]


def check_context(extraction: Extraction, context: Context, matching: Matching | None, catalog: dict) -> list[Finding]:
    findings = []
    for name in ("sponsor", "study", "site"):
        field = getattr(context, name)
        if not field.confident:
            findings.append((HoldReason.context_uncertain,
                             f"{name.title()} '{field.header_text}' resolved to '{field.record_name}' "
                             f"with confidence {field.confidence:.2f}, below threshold"))
    if not context.study_belongs_to_sponsor:
        findings.append((HoldReason.context_uncertain, "Study does not belong to the resolved sponsor"))
    if not context.site_linked_to_study:
        findings.append((HoldReason.site_not_linked, "Site is not linked to the study"))
    if matching is None and not findings:
        findings.append((HoldReason.context_uncertain, "Matching did not run"))
    return findings


def check_arithmetic(extraction: Extraction, context: Context, matching: Matching | None, catalog: dict) -> list[Finding]:
    findings = []
    for line in extraction.line_items:
        expected = money(Decimal(str(line.quantity)) * Decimal(str(line.unit_price)))
        if expected != money(line.amount):
            findings.append((HoldReason.arithmetic, f"Line {line.line_no}: {line.quantity} x {line.unit_price} "
                                                    f"= {expected}, billed {money(line.amount)}"))
    lines_total = sum(money(line.amount) for line in extraction.line_items)
    if extraction.header.total is None:
        findings.append((HoldReason.arithmetic, "No printed invoice total"))
    elif lines_total != money(extraction.header.total):
        findings.append((HoldReason.arithmetic, f"Lines sum to {lines_total}, printed total is "
                                                f"{money(extraction.header.total)}"))
    return findings


def check_matches(extraction: Extraction, context: Context, matching: Matching | None, catalog: dict) -> list[Finding]:
    if matching is None:
        return []
    findings, by_line = [], {m.line_no: m for m in matching.matches}
    for line in extraction.line_items:  # every Line Item, so one the matcher left out cannot slip through
        match = by_line.get(line.line_no)
        if match is None or match.catalog_item_id is None:
            findings.append((HoldReason.unmatched, f"Line {line.line_no} '{line.description}' has no Catalog Item"))
            continue
        if match.ambiguous or match.confidence == MatchConfidence.low:
            also = f"; also plausible: {', '.join(match.alternatives)}" if match.alternatives else ""
            findings.append((HoldReason.ambiguous, f"Line {line.line_no} '{line.description}' matched "
                                                   f"{match.item_code} ({match.confidence} confidence){also}"))
        item = catalog[match.catalog_item_id]
        # $0.00 is taken literally: any billed amount is a variance (decisions.md); this supersedes
        # the earlier "pass-through items skip the check".
        if is_price_variance(line.unit_price, item["unit_price"]):
            findings.append((HoldReason.price_variance, f"Line {line.line_no} '{line.description}' billed at "
                                                        f"{money(line.unit_price)}, catalog {item['item_code']} is "
                                                        f"{money(item['unit_price'])}"))
    return findings


HARD_CHECKS = [check_source, check_context, check_arithmetic, check_matches]

REVIEW_SYSTEM = """You review a clinical trial site invoice for a sponsor's accounts-payable team,
after automated checks. You are given the invoice, its resolved Context, the line matches with
catalog prices, the hard-check findings, and the outcome those findings already determine.
Use only the data given; do not assume facts that are not in it. If the Context was corrected by a
Reviewer, the Reviewer has already confirmed those records against the header: do not question them.
1. concern: raise one only for a specific, material risk the hard checks did not cover, such as an
   implausible quantity for a visit schedule or a service billed twice. Otherwise null. You cannot
   clear a finding.
2. rationale: two or three sentences a Reviewer reads in ten seconds, stating the outcome given
   (held or submitted, adjusted for your concern) and the reasons for it."""


def llm_review(extraction: Extraction, context: Context, matching: Matching | None, catalog: dict,
               findings: list[Finding]) -> LLMReview:
    payload = {
        "outcome_from_hard_checks": "held" if findings else "submitted unless you raise a concern",
        "hard_check_findings": [text for _, text in findings],
        "invoice": extraction.model_dump(exclude={"source_media_type", "unverified"}),
        "context": {f: getattr(context, f).record_name for f in ("sponsor", "study", "site")},
        "context_corrected_by_reviewer": {"reviewer": context.corrected_by, "note": context.explanation}
        if context.corrected_by else None,
        "matches": [{**m.model_dump(exclude={"corrected_by"}),
                     "catalog_price": catalog[m.catalog_item_id]["unit_price"] if m.catalog_item_id else None}
                    for m in (matching.matches if matching else [])],
    }
    return llm.parse(LLMReview, REVIEW_SYSTEM, [{"type": "text", "text": json.dumps(payload)}], effort="high")


def decide(extraction: Extraction, context: Context, matching: Matching | None, catalog: list[dict],
           review: Callable[..., LLMReview] = llm_review) -> Decision:
    by_id = {item["id"]: item for item in catalog}
    findings = [f for check in HARD_CHECKS for f in check(extraction, context, matching, by_id)]
    review_result = review(extraction, context, matching, by_id, list(findings))
    if review_result.concern:
        findings.append((HoldReason.llm_concern, review_result.concern))
    if findings:
        return Decision(outcome=Outcome.hold, hold_reasons=list(dict.fromkeys(r for r, _ in findings)),
                        details=[text for _, text in findings], rationale=review_result.rationale,
                        straight_through=False)
    return Decision(outcome=Outcome.submit, hold_reasons=[], details=[], rationale=review_result.rationale,
                    straight_through=True)
