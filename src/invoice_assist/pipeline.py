"""Pipeline: fixed Stages in a fixed order (ADR-0008), every run recorded as a Stage Run.

Stages: extraction -> context -> matching -> decision -> submission.
Matching is skipped when Context is uncertain (ADR-0001). Each Stage reads its inputs from
the latest successful Stage Runs, so a rerun can start from any Stage.
"""
from collections.abc import Callable
from dataclasses import dataclass

from . import clinrun, context, decision, extraction, matching
from .models import Context, Decision, Extraction, Matching, Outcome
from .store import Store, now

STAGES = ["extraction", "context", "matching", "decision", "submission"]
STATUS_AFTER = {"extraction": "Extracted", "context": "Context Resolved", "matching": "Matched"}


@dataclass
class Stages:
    """The Stage functions, injectable so tests can swap in fakes at the LLM/MCP seams."""
    extract: Callable = extraction.extract
    resolve: Callable = context.resolve
    catalog: Callable = context.catalog
    match: Callable = matching.match
    decide: Callable = decision.decide
    submit: Callable = clinrun.submit


def build_submission(store: Store, invoice_id: int, ex: Extraction, ctx: Context, m: Matching,
                     d: Decision, catalog_by_id: dict) -> dict:
    msg = store.message_for(invoice_id)
    by_no = {mm.line_no: mm for mm in m.matches}
    lines = []
    for line in ex.line_items:
        mm = by_no.get(line.line_no)
        item = catalog_by_id.get(mm.catalog_item_id) if mm else None
        lines.append({
            "catalog_item_id": item["id"] if item else None,
            "item_code": item["item_code"] if item else None,
            "description_as_billed": line.description,
            "qty": line.quantity, "unit_price": line.unit_price, "amount": line.amount,
            "price_variance": bool(item) and round(line.unit_price, 2) != round(float(item["unit_price"]), 2),
        })
    return {
        "invoice": {"number": ex.header.invoice_number, "date": ex.header.invoice_date, "currency": "USD",
                    "total": ex.header.total if ex.header.total is not None else sum(l.amount for l in ex.line_items)},
        "context": {"sponsor_id": ctx.sponsor.record_id, "study_id": ctx.study.record_id, "site_id": ctx.site.record_id},
        "lines": lines,
        "decision": {"rationale": d.rationale, "straight_through": d.straight_through},
        "release": None,
        "source": {"message_id": msg["message_id"], "received_at": msg["received_at"]},
    }


class Pipeline:
    def __init__(self, store: Store, stages: Stages | None = None):
        self.store = store
        self.stages = stages or Stages()

    def process(self, invoice_id: int, from_stage: str = "extraction", trigger: str = "automatic") -> str:
        inv = self.store.invoice(invoice_id)
        for stage in STAGES[STAGES.index(from_stage):]:
            started = now()
            try:
                output = self._run(stage, invoice_id, inv)
            except Exception as exc:  # recorded as a failed Stage Run; retries arrive in S4
                self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "failed", None,
                                         f"{type(exc).__name__}: {exc}", started)
                self.store.set_status(invoice_id, "Failed", failed_stage=stage)
                return "Failed"
            self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "succeeded", output, None, started)
            if stage in STATUS_AFTER:
                self.store.set_status(invoice_id, STATUS_AFTER[stage])
            if stage == "decision" and output["outcome"] == Outcome.hold:
                self.store.set_status(invoice_id, "Held")
                return "Held"
        self.store.set_status(invoice_id, "Submitted")
        return "Submitted"

    def _run(self, stage: str, invoice_id: int, inv) -> dict:
        s, latest = self.stages, lambda name: self.store.latest_output(invoice_id, name)
        if stage == "extraction":
            return s.extract(inv["data"], inv["media_type"]).model_dump()
        ex = Extraction.model_validate(latest("extraction"))
        if stage == "context":
            return s.resolve(ex.header).model_dump()
        ctx = Context.model_validate(latest("context"))
        if stage == "matching":
            if not ctx.confident:
                return {"skipped": True, "reason": "Context uncertain"}
            catalog = s.catalog(ctx.sponsor.record_id, ctx.study.record_id)
            return {"skipped": False, "catalog": catalog, **s.match(ex.line_items, catalog).model_dump()}
        mout = latest("matching")
        m = Matching.model_validate(mout) if mout and not mout.get("skipped") else None
        if stage == "decision":
            return s.decide(ex, ctx, m).model_dump()
        if stage == "submission":
            d = Decision.model_validate(latest("decision"))
            catalog_by_id = {item["id"]: item for item in mout["catalog"]}
            key = clinrun.idempotency_key(inv["sha256"], inv["version"])
            clinrun_id = s.submit(build_submission(self.store, invoice_id, ex, ctx, m, d, catalog_by_id), key)
            self.store.add_submission(invoice_id, inv["version"], clinrun_id, key)
            return {"clinrun_id": clinrun_id, "idempotency_key": key}
        raise ValueError(stage)
