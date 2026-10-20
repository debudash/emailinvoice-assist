"""Pipeline: fixed Stages in a fixed order (ADR-0008), every run recorded as a Stage Run.

Stages: extraction -> context -> matching -> decision -> submission.
Matching is skipped when Context is uncertain (ADR-0001). Each Stage reads its inputs from
the latest successful Stage Runs and records which ones it read, so a rerun can start from
any Stage and any Decision can be rebuilt from its rows.
"""
from collections.abc import Callable
from dataclasses import dataclass

from . import clinrun, context, decision, extraction, llm, matching
from .models import Context, Decision, Extraction, InvoiceStatus, Matching, Outcome
from .store import Store, now

STAGES = ["extraction", "context", "matching", "decision", "submission"]
STATUS_AFTER = {"extraction": InvoiceStatus.extracted, "context": InvoiceStatus.context_resolved,
                "matching": InvoiceStatus.matched}


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
        # The printed total only; a missing one is held by the decision (check_printed_total).
        "invoice": {"number": ex.header.invoice_number, "date": ex.header.invoice_date, "currency": "USD",
                    "total": ex.header.total},
        "context": {"sponsor_id": ctx.sponsor.record_id, "study_id": ctx.study.record_id, "site_id": ctx.site.record_id},
        "lines": lines,
        "decision": {"rationale": d.rationale, "straight_through": d.straight_through},
        "release": None,
        "source": {"message_id": msg["message_id"], "received_at": msg["received_at"]},
    }


def _describe(exc: BaseException) -> str:
    """The error an Operator needs: async MCP calls wrap the real cause in ExceptionGroups."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


class Pipeline:
    def __init__(self, store: Store, stages: Stages | None = None):
        self.store = store
        self.stages = stages or Stages()

    def process(self, invoice_id: int, from_stage: str = "extraction", trigger: str = "automatic") -> str:
        inv = self.store.invoice(invoice_id)
        for stage in STAGES[STAGES.index(from_stage):]:
            started, inputs, served = now(), {}, []
            token = llm.served_by.set(served)
            try:
                output = self._run(stage, invoice_id, inv, inputs)
            except Exception as exc:  # recorded as a failed Stage Run (ADR-0009); retries arrive in S4
                self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "failed", inputs, None,
                                         _describe(exc), served, started)
                self.store.set_status(invoice_id, InvoiceStatus.failed, failed_stage=stage)
                return InvoiceStatus.failed
            finally:
                llm.served_by.reset(token)
            self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "succeeded", inputs, output,
                                     None, served, started)
            if stage in STATUS_AFTER and not output.get("skipped"):
                self.store.set_status(invoice_id, STATUS_AFTER[stage])
            if stage == "decision" and output["outcome"] == Outcome.hold:
                self.store.set_status(invoice_id, InvoiceStatus.held)
                return InvoiceStatus.held
        self.store.set_status(invoice_id, InvoiceStatus.submitted)
        return InvoiceStatus.submitted

    def _read(self, invoice_id: int, stage: str, inputs: dict) -> dict:
        run = self.store.latest_run(invoice_id, stage)
        inputs[stage] = run["id"]
        return self.store.latest_output(invoice_id, stage)

    def _run(self, stage: str, invoice_id: int, inv, inputs: dict) -> dict:
        s = self.stages
        if stage == "extraction":
            return s.extract(inv["data"], inv["media_type"]).model_dump()
        ex = Extraction.model_validate(self._read(invoice_id, "extraction", inputs))
        if stage == "context":
            return s.resolve(ex.header).model_dump()
        ctx = Context.model_validate(self._read(invoice_id, "context", inputs))
        if stage == "matching":
            if not ctx.confident:
                return {"skipped": True, "reason": "Context uncertain"}
            catalog = s.catalog(ctx.sponsor.record_id, ctx.study.record_id)
            return {"skipped": False, "catalog": catalog, **s.match(ex.line_items, catalog).model_dump()}
        matching_output = self._read(invoice_id, "matching", inputs)
        m = None if matching_output.get("skipped") else Matching.model_validate(matching_output)
        if stage == "decision":
            return s.decide(ex, ctx, m, matching_output.get("catalog", [])).model_dump()
        if stage == "submission":
            d = Decision.model_validate(self._read(invoice_id, "decision", inputs))
            catalog_by_id = {item["id"]: item for item in matching_output["catalog"]}
            key = clinrun.idempotency_key(inv["sha256"], inv["version"])
            clinrun_id = s.submit(build_submission(self.store, invoice_id, ex, ctx, m, d, catalog_by_id), key)
            self.store.add_submission(invoice_id, inv["version"], clinrun_id, key)
            return {"clinrun_id": clinrun_id, "idempotency_key": key}
        raise ValueError(stage)
