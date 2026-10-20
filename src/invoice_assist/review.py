"""Review Actions: what a Reviewer or Operator can do after the AI has decided.

Every action is checked here (not in the Hub), recorded as an Action, and any rerun goes
through the Pipeline so it adds Stage Runs rather than overwriting them. A Correction is input,
not approval: the rerun decides on its own (decisions.md R2-2).
"""
from .models import Context, ContextField, HoldReason, InvoiceStatus, LineMatch, MatchConfidence, RELEASABLE
from .pipeline import Pipeline
from .store import Store, now


class ActionRefused(Exception):
    """The action is not allowed for this Invoice; the message says why."""


class ReviewActions:
    def __init__(self, store: Store, pipeline: Pipeline, reference):
        self.store, self.pipeline, self.reference = store, pipeline, reference

    def _require(self, text: str, what: str) -> str:
        if not text or not text.strip():
            raise ActionRefused(f"A {what} is required")
        return text.strip()

    def _open(self, invoice_id: int) -> None:
        if self.store.invoice(invoice_id)["status"] == InvoiceStatus.submitted:
            raise ActionRefused("Already submitted; corrections to a submitted Invoice are Amendments (P2)")

    def correct_context(self, invoice_id: int, actor: str, sponsor_id: int, study_id: int, site_id: int,
                        note: str) -> str:
        self._open(invoice_id)
        before = self.store.latest_output(invoice_id, "context")
        old = Context.model_validate(before)
        sponsor = next(r for r in self.reference.sponsors if r["id"] == sponsor_id)
        study = next(r for r in self.reference.studies if r["id"] == study_id)
        site = next(r for r in self.reference.sites if r["id"] == site_id)

        def chosen(name, row, old_field: ContextField) -> ContextField:
            return ContextField(record_id=row["id"], record_name=row["name"], header_text=old_field.header_text,
                                confidence=1.0, confident=True)

        corrected = Context(
            sponsor=chosen("sponsor", sponsor, old.sponsor), study=chosen("study", study, old.study),
            site=chosen("site", site, old.site),
            site_linked_to_study=site_id in self.reference.study_sites(study_id),
            study_belongs_to_sponsor=study["sponsor_id"] == sponsor_id,
            explanation=f"Corrected by {actor}: {note}", agent_lookups=old.agent_lookups, corrected_by=actor)
        trigger = f"correction by {actor}"
        inv = self.store.invoice(invoice_id)
        self.store.add_stage_run(invoice_id, inv["version"], "context", trigger, "succeeded",
                                 {"previous_context_run": self.store.latest_run(invoice_id, "context")["id"]},
                                 corrected.model_dump(), None, [], now())
        self.store.add_action(invoice_id, actor, "correct_context", self._require(note, "note"), before, corrected.model_dump())
        return self.pipeline.process(invoice_id, from_stage="matching", trigger=trigger)

    def correct_line(self, invoice_id: int, actor: str, line_no: int, catalog_item_id: int | None, note: str) -> str:
        self._open(invoice_id)
        matching = self.store.latest_output(invoice_id, "matching")
        if not matching or matching.get("skipped"):
            raise ActionRefused("Matching has not run; correct the Context first")
        catalog = {item["id"]: item for item in matching["catalog"]}
        matches = [dict(m) for m in matching["matches"]]
        index = next(i for i, m in enumerate(matches) if m["line_no"] == line_no)
        before = matches[index]
        matches[index] = LineMatch(
            line_no=line_no, catalog_item_id=catalog_item_id,
            item_code=catalog[catalog_item_id]["item_code"] if catalog_item_id else None,
            confidence=MatchConfidence.high, ambiguous=False, alternatives=[],
            reason=f"Corrected by {actor}: {note}", corrected_by=actor).model_dump()
        trigger = f"correction by {actor}"
        inv = self.store.invoice(invoice_id)
        self.store.add_stage_run(invoice_id, inv["version"], "matching", trigger, "succeeded",
                                 {"previous_matching_run": self.store.latest_run(invoice_id, "matching")["id"]},
                                 {**matching, "matches": matches}, None, [], now())
        self.store.add_action(invoice_id, actor, "correct_line", self._require(note, "note"), before, matches[index])
        return self.pipeline.process(invoice_id, from_stage="decision", trigger=trigger)

    def release(self, invoice_id: int, actor: str, reason: str) -> str:
        reason = self._require(reason, "Release reason")
        inv = self.store.invoice(invoice_id)
        if inv["status"] not in (InvoiceStatus.held, InvoiceStatus.escalated):
            raise ActionRefused(f"Only a Held or Escalated Invoice can be Released (status is {inv['status']})")
        reasons = {HoldReason(r) for r in self.store.latest_output(invoice_id, "decision")["hold_reasons"]}
        blocking = sorted(reasons - RELEASABLE)
        if blocking:
            raise ActionRefused(f"Needs a Correction, not a Release: {', '.join(blocking)}")
        self.store.add_action(invoice_id, actor, "release", reason)
        return self.pipeline.process(invoice_id, from_stage="submission", trigger=f"release by {actor}",
                                     release={"reason": reason, "reviewer": actor})

    def escalate(self, invoice_id: int, actor: str, note: str) -> str:
        note = self._require(note, "note")
        self.store.add_action(invoice_id, actor, "escalate", note)
        self.store.set_status(invoice_id, InvoiceStatus.escalated)
        return InvoiceStatus.escalated

    def rerun(self, invoice_id: int, actor: str, stage: str) -> str:
        self._open(invoice_id)
        self.store.add_action(invoice_id, actor, "rerun", f"Rerun from {stage}")
        return self.pipeline.process(invoice_id, from_stage=stage, trigger=f"operator rerun by {actor}")
