"""Review Actions: what a Reviewer or Operator can do after the AI has decided.

Every rule is checked here, before anything is written (not in the Hub). Each action is recorded
as an Action, and any rerun goes through the Pipeline so it adds Stage Runs rather than
overwriting them. A Correction is input, not approval: the rerun decides on its own.
"""
from .models import Context, ContextField, HoldReason, InvoiceStatus, LineMatch, MatchConfidence, RELEASABLE
from .pipeline import STAGES, Pipeline
from .store import Store, now


class ActionRefused(Exception):
    """The action is not allowed for this Invoice; the message says why."""


def _required(text: str, what: str) -> str:
    if not text or not text.strip():
        raise ActionRefused(f"A {what} is required")
    return text.strip()


class ReviewActions:
    def __init__(self, store: Store, pipeline: Pipeline, reference):
        self.store, self.pipeline, self.reference = store, pipeline, reference

    # --- guards -----------------------------------------------------------------------------
    def _status(self, invoice_id: int) -> str:
        return self.store.invoice(invoice_id)["status"]

    def _held(self, invoice_id: int, action: str) -> None:
        status = self._status(invoice_id)
        if status == InvoiceStatus.submitted:
            raise ActionRefused("Already submitted; corrections to a submitted Invoice are Amendments (P2)")
        if status not in (InvoiceStatus.held, InvoiceStatus.escalated):
            raise ActionRefused(f"{action} needs a Held or Escalated Invoice (status is {status})")

    def release_blockers(self, invoice_id: int) -> list[str]:
        """Hold Reasons that need a Correction rather than a Release (empty means Release is allowed)."""
        decision = self.store.latest_output(invoice_id, "decision") or {"hold_reasons": []}
        return sorted({HoldReason(r) for r in decision["hold_reasons"]} - RELEASABLE)

    # --- corrections --------------------------------------------------------------------------
    def _rerun_after_correction(self, invoice_id: int, actor: str, stage: str, corrected: dict, kind: str,
                                note: str, before, after, from_stage: str) -> str:
        trigger = f"correction by {actor}"
        self.store.add_stage_run(invoice_id, self.store.invoice(invoice_id)["version"], stage, trigger, "succeeded",
                                 {f"previous_{stage}_run": self.store.latest_run(invoice_id, stage)["id"]},
                                 corrected, None, [], now())
        self.store.add_action(invoice_id, actor, kind, note, before, after)
        return self.pipeline.process(invoice_id, from_stage=from_stage, trigger=trigger)

    def correct_context(self, invoice_id: int, actor: str, sponsor_id: int, study_id: int, site_id: int,
                        note: str) -> str:
        note = _required(note, "note")
        self._held(invoice_id, "Correction")
        before = self.store.latest_output(invoice_id, "context")
        old = Context.model_validate(before)
        # ISSUE-007: a Correction that changed nothing was accepted, reran the AI and held again, so a
        # Reviewer "fixing" a Price Variance this way saw no effect. Root cause: no check that the
        # Correction differs from what is there. Fix: refuse it and say which action clears the Hold.
        if old.confident and (old.sponsor.record_id, old.study.record_id, old.site.record_id) == (
                sponsor_id, study_id, site_id):
            raise ActionRefused("The Context is already these records, all confident; a Correction would change "
                                "nothing. Check what clears each Hold Reason on the hold.")
        sponsor = next(r for r in self.reference.sponsors if r["id"] == sponsor_id)
        study = next(r for r in self.reference.studies if r["id"] == study_id)
        site = next(r for r in self.reference.sites if r["id"] == site_id)

        def chosen(row: dict, old_field: ContextField) -> ContextField:
            return ContextField(record_id=row["id"], record_name=row["name"], header_text=old_field.header_text,
                                confidence=1.0, confident=True)

        corrected = Context(
            sponsor=chosen(sponsor, old.sponsor), study=chosen(study, old.study), site=chosen(site, old.site),
            site_linked_to_study=site_id in self.reference.study_sites(study_id),
            study_belongs_to_sponsor=study["sponsor_id"] == sponsor_id,
            explanation=f"Corrected by {actor}: {note}", agent_lookups=old.agent_lookups, corrected_by=actor).model_dump()
        return self._rerun_after_correction(invoice_id, actor, "context", corrected, "correct_context", note,
                                            before, corrected, from_stage="matching")

    def correct_line(self, invoice_id: int, actor: str, line_no: int, catalog_item_id: int | None, note: str) -> str:
        note = _required(note, "note")
        self._held(invoice_id, "Correction")
        matching = self.store.latest_output(invoice_id, "matching")
        if not matching or matching.get("skipped"):
            raise ActionRefused("Matching has not run; correct the Context first")
        catalog = {item["id"]: item for item in matching["catalog"]}
        before = next((m for m in matching["matches"] if m["line_no"] == line_no), None)
        if (before and before["catalog_item_id"] == catalog_item_id and before["confidence"] == MatchConfidence.high
                and not before["ambiguous"]):  # ISSUE-007: see correct_context
            raise ActionRefused(f"Line {line_no} is already matched to {before['item_code'] or 'Unmatched'}; a "
                                "Correction would change nothing. A Price Variance is cleared by a Release.")
        corrected_line = LineMatch(
            line_no=line_no, catalog_item_id=catalog_item_id,
            item_code=catalog[catalog_item_id]["item_code"] if catalog_item_id else None,
            confidence=MatchConfidence.high, ambiguous=False, alternatives=[],
            reason=f"Corrected by {actor}: {note}", corrected_by=actor).model_dump()
        matches = sorted([m for m in matching["matches"] if m["line_no"] != line_no] + [corrected_line],
                         key=lambda m: m["line_no"])  # also covers a line the matcher left out
        return self._rerun_after_correction(invoice_id, actor, "matching", {**matching, "matches": matches},
                                            "correct_line", note, before, corrected_line, from_stage="decision")

    # --- release, escalation, rerun -------------------------------------------------------------
    def release(self, invoice_id: int, actor: str, reason: str, at_catalog_price: bool = False) -> str:
        """Submit a held Invoice as billed, or with Price Variance lines paid at the Catalog price."""
        reason = _required(reason, "Release reason")
        self._held(invoice_id, "Release")
        blocking = self.release_blockers(invoice_id)
        if blocking:
            raise ActionRefused(f"Needs a Correction, not a Release: {', '.join(blocking)}")
        if at_catalog_price and HoldReason.price_variance not in self.store.latest_output(invoice_id, "decision")["hold_reasons"]:
            raise ActionRefused("There is no Price Variance to pay at the catalog price")
        self.store.add_action(invoice_id, actor, "release_at_catalog_price" if at_catalog_price else "release", reason)
        return self.pipeline.process(invoice_id, from_stage="submission", trigger=f"release by {actor}",
                                     release={"reason": reason, "reviewer": actor, "at_catalog_price": at_catalog_price})

    def escalate(self, invoice_id: int, actor: str, note: str) -> str:
        note = _required(note, "note")
        if self._status(invoice_id) != InvoiceStatus.held:
            raise ActionRefused(f"Only a Held Invoice can be Escalated (status is {self._status(invoice_id)})")
        self.store.add_action(invoice_id, actor, "escalate", note)
        self.store.set_status(invoice_id, InvoiceStatus.escalated)
        return InvoiceStatus.escalated

    def rerun(self, invoice_id: int, actor: str, stage: str) -> str:
        """Operator recovery: a Failed Invoice, from its failed Stage or earlier (never past a Hold)."""
        inv = self.store.invoice(invoice_id)
        if inv["status"] != InvoiceStatus.failed:
            raise ActionRefused(f"Only a Failed Invoice can be rerun (status is {inv['status']})")
        if stage not in STAGES or STAGES.index(stage) > STAGES.index(inv["failed_stage"]):
            raise ActionRefused(f"Rerun from {inv['failed_stage']} or an earlier Stage")
        release = None
        if stage == "submission":  # a Released Invoice whose submission failed keeps its Release
            last = [a for a in self.store.actions(invoice_id) if a["kind"] in ("release", "release_at_catalog_price")]
            release = {"reason": last[-1]["note"], "reviewer": last[-1]["actor"],
                       "at_catalog_price": last[-1]["kind"] == "release_at_catalog_price"} if last else None
            if release is None and (self.store.latest_output(invoice_id, "decision") or {}).get("outcome") != "submit":
                raise ActionRefused("The Decision is Hold and nothing was Released; there is nothing to submit")
        self.store.add_action(invoice_id, actor, "rerun", f"Rerun from {stage}")
        return self.pipeline.process(invoice_id, from_stage=stage, trigger=f"operator rerun by {actor}", release=release)
