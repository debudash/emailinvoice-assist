"""Decision Stage: hard checks force a Hold; the LLM can add Holds, never clear them (ADR-0002).

S0 (tracer bullet) ships the check framework with the Context and Unmatched checks.
S1 adds Ambiguous, Price Variance, arithmetic and the LLM review.
"""
from collections.abc import Callable

from .models import Context, Decision, Extraction, HoldReason, Matching, Outcome

Finding = tuple[HoldReason, str]
Check = Callable[[Extraction, Context, Matching | None], list[Finding]]


def check_context(extraction: Extraction, context: Context, matching: Matching | None) -> list[Finding]:
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
    return findings


def check_printed_total(extraction: Extraction, context: Context, matching: Matching | None) -> list[Finding]:
    # The submission carries the printed total; never invent one from the lines. S1 adds the sum check.
    if extraction.header.total is None:
        return [(HoldReason.arithmetic, "No printed invoice total")]
    return []


def check_unmatched(extraction: Extraction, context: Context, matching: Matching | None) -> list[Finding]:
    if matching is None:
        return []
    by_no = {line.line_no: line for line in extraction.line_items}
    return [(HoldReason.unmatched, f"Line {m.line_no} '{by_no[m.line_no].description}' has no Catalog Item")
            for m in matching.matches if m.catalog_item_id is None]


HARD_CHECKS: list[Check] = [check_context, check_printed_total, check_unmatched]


def decide(extraction: Extraction, context: Context, matching: Matching | None) -> Decision:
    findings = [f for check in HARD_CHECKS for f in check(extraction, context, matching)]
    if matching is None and not findings:
        # Matching is skipped only for uncertain Context; never submit unmatched work.
        findings.append((HoldReason.context_uncertain, "Matching did not run"))
    if findings:
        reasons = list(dict.fromkeys(reason for reason, _ in findings))
        return Decision(outcome=Outcome.hold, hold_reasons=reasons,
                        details=[text for _, text in findings],
                        rationale=f"Held: {len(findings)} finding(s) from the hard checks.",
                        straight_through=False)
    return Decision(outcome=Outcome.submit, hold_reasons=[], details=[],
                    rationale="Every hard check passed: Context confident and every line matched.",
                    straight_through=True)
