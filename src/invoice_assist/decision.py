"""Decision Stage: hard checks force a Hold; the LLM can add Holds, never clear them (ADR-0002).

Every check is a pure function returning findings. The LLM review always runs and writes the
rationale; it may raise a concern, which adds a Hold. The outcome is computed here, in code:
any finding means Hold, whatever the review says.
"""
import json
from collections.abc import Callable
from decimal import Decimal

from . import llm
from .config import settings
from .models import Context, Decision, Extraction, HoldReason, Matching, Outcome, Review

Finding = tuple[HoldReason, str]
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT)


def check_context(ex: Extraction, ctx: Context, m: Matching | None, catalog: dict) -> list[Finding]:
    findings = []
    for name in ("sponsor", "study", "site"):
        field = getattr(ctx, name)
        if not field.confident:
            findings.append((HoldReason.context_uncertain,
                             f"{name.title()} '{field.header_text}' resolved to '{field.record_name}' "
                             f"with confidence {field.confidence:.2f}, below threshold"))
    if not ctx.study_belongs_to_sponsor:
        findings.append((HoldReason.context_uncertain, "Study does not belong to the resolved sponsor"))
    if not ctx.site_linked_to_study:
        findings.append((HoldReason.site_not_linked, "Site is not linked to the study"))
    if m is None and not findings:
        findings.append((HoldReason.context_uncertain, "Matching did not run"))
    return findings


def check_arithmetic(ex: Extraction, ctx: Context, m: Matching | None, catalog: dict) -> list[Finding]:
    findings = []
    for line in ex.line_items:
        if money(line.quantity * line.unit_price) != money(line.amount):
            findings.append((HoldReason.arithmetic, f"Line {line.line_no}: {line.quantity} x {line.unit_price} "
                                                    f"is not the billed {line.amount}"))
    if ex.header.total is None:
        findings.append((HoldReason.arithmetic, "No printed invoice total"))
    elif sum(money(line.amount) for line in ex.line_items) != money(ex.header.total):
        findings.append((HoldReason.arithmetic, f"Lines sum to {sum(money(l.amount) for l in ex.line_items)}, "
                                                f"printed total is {money(ex.header.total)}"))
    return findings


def check_matches(ex: Extraction, ctx: Context, m: Matching | None, catalog: dict) -> list[Finding]:
    if m is None:
        return []
    findings, by_no = [], {line.line_no: line for line in ex.line_items}
    for match in m.matches:
        line = by_no[match.line_no]
        if match.catalog_item_id is None:
            findings.append((HoldReason.unmatched, f"Line {line.line_no} '{line.description}' has no Catalog Item"))
            continue
        if match.ambiguous:
            findings.append((HoldReason.ambiguous, f"Line {line.line_no} '{line.description}' matched "
                                                   f"{match.item_code}; also plausible: {', '.join(match.alternatives)}"))
        item = catalog[match.catalog_item_id]
        catalog_price, billed = money(item["unit_price"]), money(line.unit_price)
        # $0.00 is taken literally: any billed amount is a variance (decisions.md).
        if abs(billed - catalog_price) > catalog_price * Decimal(str(settings.price_tolerance)):
            findings.append((HoldReason.price_variance, f"Line {line.line_no} '{line.description}' billed at {billed}, "
                                                        f"catalog {item['item_code']} is {catalog_price}"))
    return findings


HARD_CHECKS = [check_context, check_arithmetic, check_matches]

REVIEW_SYSTEM = """You review a clinical trial site invoice after automated checks, for a sponsor's
accounts-payable team. You see the invoice, its resolved Context, the line matches with catalog
prices, and the findings of the hard checks. Hard-check findings already hold the invoice; you cannot
override them. Raise a concern only for a specific, material risk the checks did not cover (e.g. an
implausible quantity for the visit schedule, a duplicated service, a charge that does not fit the
study). Do not raise concerns about formatting or wording. Then write a short rationale a Reviewer can
read in ten seconds: what was checked and why the invoice is submitted or held."""


def llm_review(ex: Extraction, ctx: Context, m: Matching | None, catalog: dict, findings: list[Finding]) -> Review:
    payload = {
        "invoice": ex.model_dump(),
        "context": {f: getattr(ctx, f).record_name for f in ("sponsor", "study", "site")},
        "matches": [{**match.model_dump(), "catalog_price": catalog[match.catalog_item_id]["unit_price"]
                     if match.catalog_item_id else None} for match in (m.matches if m else [])],
        "hard_check_findings": [text for _, text in findings],
    }
    return llm.parse(Review, REVIEW_SYSTEM, [{"type": "text", "text": json.dumps(payload)}], effort="high")


def decide(ex: Extraction, ctx: Context, m: Matching | None, catalog: list[dict],
           review: Callable[..., Review] = llm_review) -> Decision:
    by_id = {item["id"]: item for item in catalog}
    findings = [f for check in HARD_CHECKS for f in check(ex, ctx, m, by_id)]
    verdict = review(ex, ctx, m, by_id, findings)
    if verdict.concern:
        findings.append((HoldReason.llm_concern, verdict.concern))
    if findings:
        return Decision(outcome=Outcome.hold, hold_reasons=list(dict.fromkeys(r for r, _ in findings)),
                        details=[text for _, text in findings], rationale=verdict.rationale, straight_through=False)
    return Decision(outcome=Outcome.submit, hold_reasons=[], details=[], rationale=verdict.rationale,
                    straight_through=True)
