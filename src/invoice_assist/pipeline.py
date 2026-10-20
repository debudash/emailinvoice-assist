"""Pipeline: fixed Stages in a fixed order (ADR-0008), every run recorded as a Stage Run.

Stages: extraction -> context -> matching -> decision -> submission.
Matching is skipped when Context is uncertain (ADR-0001). Each Stage reads its inputs from
the latest successful Stage Runs and records which ones it read, so a rerun can start from
any Stage and any Decision can be rebuilt from its rows.
"""
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from . import clinrun, context, decision, extraction, llm, matching
from .models import Context, Decision, Extraction, InvoiceStatus, Matching, Outcome
from .store import Store, now

STAGES = ["extraction", "context", "matching", "decision", "submission"]
STATUS_AFTER = {"extraction": InvoiceStatus.extracted, "context": InvoiceStatus.context_resolved,
                "matching": InvoiceStatus.matched, "decision": InvoiceStatus.decided}


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
                     d: Decision, catalog_by_id: dict, release: dict | None = None) -> dict:
    msg = store.message_for(invoice_id)
    by_no = {mm.line_no: mm for mm in m.matches}
    at_catalog_price = bool(release and release.get("at_catalog_price"))
    lines = []
    for line in ex.line_items:
        mm = by_no.get(line.line_no)
        item = catalog_by_id.get(mm.catalog_item_id) if mm else None
        # ISSUE-010: with a price tolerance set, a line the Decision accepted went to ClinRun flagged as
        # a Price Variance. Root cause: this flag compared prices exactly, while the Decision applied
        # PRICE_TOLERANCE. Fix: both use decision.is_price_variance, so they cannot disagree.
        variance = bool(item) and decision.is_price_variance(line.unit_price, item["unit_price"])
        adjusted = variance and at_catalog_price  # paid at the Catalog price; the billed figures travel with it
        unit_price, amount = line.unit_price, line.amount
        if adjusted:
            price = decision.money(item["unit_price"])
            unit_price, amount = float(price), float(decision.money(price * Decimal(str(line.quantity))))
        lines.append({
            "catalog_item_id": item["id"] if item else None,
            "item_code": item["item_code"] if item else None,
            "description_as_billed": line.description,
            "qty": line.quantity, "unit_price": unit_price, "amount": amount,
            "price_variance": variance,
            "billed_unit_price": line.unit_price if adjusted else None,
            "billed_amount": line.amount if adjusted else None,
        })
    return {
        # The printed total only; a missing one is held by the decision (check_printed_total).
        "invoice": {"number": ex.header.invoice_number, "date": ex.header.invoice_date, "currency": "USD",
                    "total": ex.header.total},
        "context": {"sponsor_id": ctx.sponsor.record_id, "study_id": ctx.study.record_id, "site_id": ctx.site.record_id},
        "lines": lines,
        "decision": {"rationale": d.rationale, "straight_through": d.straight_through},
        "release": release,
        "source": {"message_id": msg["message_id"], "received_at": msg["received_at"]},
    }


class _Exhausted(Exception):
    def __init__(self, error: Exception, attempts: int):
        self.error, self.attempts = error, attempts


def _describe(exc: BaseException) -> str:
    """The error an Operator needs: async MCP calls wrap the real cause in ExceptionGroups."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"


class Pipeline:
    def __init__(self, store: Store, stages: Stages | None = None, backoff: tuple[float, ...] = (1, 4)):
        self.store = store
        self.stages = stages or Stages()
        self.backoff = backoff  # seconds before each retry; two retries by default (ADR-0009)

    def process(self, invoice_id: int, from_stage: str = "extraction", trigger: str = "automatic",
                release: dict | None = None) -> str:
        inv = self.store.invoice(invoice_id)
        for stage in STAGES[STAGES.index(from_stage):]:
            started, inputs, served = now(), {}, []
            token = llm.served_by.set(served)
            try:
                output, attempts = self._attempt(stage, invoice_id, inv, inputs, release)
            except _Exhausted as failure:
                self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "failed", inputs, None,
                                         _describe(failure.error), served, started, failure.attempts)
                self.store.set_status(invoice_id, InvoiceStatus.failed, failed_stage=stage)
                return InvoiceStatus.failed
            finally:
                llm.served_by.reset(token)
            self.store.add_stage_run(invoice_id, inv["version"], stage, trigger, "succeeded", inputs, output,
                                     None, served, started, attempts)
            if stage in STATUS_AFTER and not output.get("skipped"):
                self.store.set_status(invoice_id, STATUS_AFTER[stage])
            if stage == "decision" and output["outcome"] == Outcome.hold:
                self.store.set_status(invoice_id, InvoiceStatus.held)
                return InvoiceStatus.held
        self.store.set_status(invoice_id, InvoiceStatus.submitted)
        return InvoiceStatus.submitted

    def _attempt(self, stage: str, invoice_id: int, inv, inputs: dict, release: dict | None) -> tuple[dict, int]:
        for attempt, delay in enumerate((*self.backoff, None), start=1):
            try:
                return self._run(stage, invoice_id, inv, inputs, release), attempt
            except Exception as exc:  # the one place errors are caught: a Stage that cannot complete
                if delay is None:
                    raise _Exhausted(exc, attempt)
                time.sleep(delay)

    def _read(self, invoice_id: int, stage: str, inputs: dict) -> dict:
        run = self.store.latest_run(invoice_id, stage)
        inputs[stage] = run["id"]
        return self.store.latest_output(invoice_id, stage)

    def _run(self, stage: str, invoice_id: int, inv, inputs: dict, release: dict | None) -> dict:
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
            d = s.decide(ex, ctx, m, matching_output.get("catalog", []))
            # Straight-Through means no human action (GLOSSARY): a Corrected Invoice never counts.
            if any(a["kind"].startswith("correct_") for a in self.store.actions(invoice_id)):
                d.straight_through = False
            return d.model_dump()
        if stage == "submission":
            d = Decision.model_validate(self._read(invoice_id, "decision", inputs))
            catalog_by_id = {item["id"]: item for item in matching_output["catalog"]}
            key = clinrun.idempotency_key(inv["sha256"], inv["version"])
            submission = build_submission(self.store, invoice_id, ex, ctx, m, d, catalog_by_id, release)
            clinrun_id = s.submit(submission, key)
            self.store.add_submission(invoice_id, inv["version"], clinrun_id, key)
            return {"clinrun_id": clinrun_id, "idempotency_key": key}
        raise ValueError(stage)
