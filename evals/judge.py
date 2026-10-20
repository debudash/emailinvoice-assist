"""LLM-as-judge for rationale faithfulness (decisions R3-2: reported, not gated).

Grades a Decision's rationale against the Decision itself: does it state the outcome, cite every
Hold Reason, and make no claim the findings and invoice data do not support?
"""
import json

from pydantic import BaseModel, Field

from invoice_assist import llm

SYSTEM = """You grade the rationale an automated accounts-payable system wrote for one invoice Decision.
You are given the Decision (outcome, hold reasons, the findings behind them), the evidence the
rationale was written from (the extracted invoice and its line matches with catalog prices), and the
rationale text. Judge only against that data. Arithmetic and counts derived from the evidence are
supported. The system was asked to assess plausibility (quantities against a visit schedule, duplicated
services); such assessments are its judgement, not factual claims: flag them only if the evidence
contradicts them.
- states_outcome: the rationale says the invoice was submitted or held, matching the outcome.
- cites_every_reason: every hold reason is reflected in the rationale (true when there are none).
- unsupported_claims: each specific factual claim in the rationale that the findings and data do not
  support (wrong numbers, invented checks, facts not given). Empty list when there are none."""


class Grade(BaseModel):
    states_outcome: bool
    cites_every_reason: bool
    unsupported_claims: list[str] = Field(default_factory=list)


def faithfulness(grade: Grade) -> float:
    """1.0 only when the outcome is stated, every reason cited, and nothing is unsupported."""
    return (grade.states_outcome + grade.cites_every_reason + (not grade.unsupported_claims)) / 3


def judge(prediction: dict) -> Grade:
    payload = {"outcome": prediction["decision"], "hold_reasons": prediction["hold_reasons"],
               "findings": prediction.get("details", []), "evidence": prediction.get("evidence", {}),
               "rationale": prediction["rationale"]}
    return llm.parse(Grade, SYSTEM, [{"type": "text", "text": json.dumps(payload)}], effort="medium")
