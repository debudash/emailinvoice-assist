# Users

Two actors use the system, both through the Hub. Identity comes from the **Acting as** picker in the
sidebar (Dana and Sam as Reviewers, Ops as Operator); authentication is assumed to be solved
upstream, and every action is recorded with the name picked. Terms are defined in
[GLOSSARY.md](../GLOSSARY.md).

## Reviewer

Checks the AI's Decisions after the fact and acts on the exceptions.

**Goals**
- Spend time only on Invoices that need judgement; clean ones go straight to ClinRun.
- Understand any Decision without opening the PDF: what was extracted, how the Context was
  resolved and how sure the system was, what each Line Item matched, and why it held or submitted.
- Clear each Hold the right way: correct what is wrong, Release what is an agreed exception,
  Escalate what they cannot resolve.

**Main scenarios**

1. **Check a Straight-Through submission**
   1. Select the **Submitted** queue and click the Invoice row.
   2. The banner shows the ClinRun ID and the LLM's rationale.
   3. Read **Extracted** (header and Line Items), **Context** (header text, resolved record,
      confidence, linked and ownership checks, agent lookups), **Matched** (Catalog Item, price,
      confidence, alternatives, reason) and **History** (Stage Runs).
2. **Correct an uncertain Context** (the mismatched-metadata sample)
   1. In **Held**, the Reasons column shows `context_uncertain`; the Matched panel says matching
      was skipped.
   2. Open **Act on this invoice → Correct context**. The Suggested Context is preselected; any
      sponsor, study or site can be chosen from the full lists.
   3. Enter a note and press **Apply correction and rerun**. Matching and the Decision rerun; the
      flash message shows the new status (Submitted, or Held with new reasons).
3. **Release a business-judgement Hold** (the medium sample's Price Variance)
   1. Open the Invoice; the warning lists each Hold Reason with a detail line, for example the
      billed and Catalog prices.
   2. **Release** tab: enter a reason, press **Release to ClinRun**.
   3. The submission carries the reason and the Reviewer's name; the Invoice is not
      Straight-Through.
4. **Correct one Line Match**
   1. **Correct a line** tab (available once matching has run).
   2. Choose the line, then a Catalog Item from that Catalog or "Unmatched", and enter a note.
   3. The Decision reruns on the corrected matches.
5. **Escalate**
   1. **Escalate** tab on a Held Invoice; a note is required.
   2. The Invoice moves to the **Escalated** queue, where any Reviewer can open it and Correct or
      Release it.
6. **Follow up a Rejected Message**: open the **Rejected messages** expander under the queue to see
   the sender, subject, time and reason (for example "No PDF or image attachment").
7. **Upload an invoice that came by another route**: sidebar **Upload an invoice**, then **Add to
   inbox**. It becomes a Message with source `upload` and follows the same process.

**A Reviewer must never be able to**
- Release a Hold that has a Reason needing a Correction: `context_uncertain`, `site_not_linked`,
  `arithmetic`. The Hub hides the Release form, and Review Actions refuses it if called anyway.
- Release, Correct or Escalate without a reason or note.
- Push a Held Invoice into submission any way other than Release (an Operator rerun is refused for
  anything that is not Failed).
- Correct a Submitted Invoice. That would be an Amendment, which is P2 and not built.
- Make the AI's Decision for it after a Correction: the rerun decides on its own.

## Operator

Keeps the pipeline running.

**Goals**
- Know where every Invoice is and why it stopped.
- Recover from outages without repeating finished work and without double-submitting.
- Control when processing starts.

**Main scenarios**

1. **Watch progress**: the **All** queue shows each Invoice's status (Received, Extracted, Context
   Resolved, Matched, then Submitted, Held, Escalated or Failed), refreshed every
   `HUB_REFRESH_SECONDS`. The metrics strip shows invoice count, Straight-Through rate, the manual
   estimate against AI processing time, Holds by reason and average seconds per Stage.
2. **Recover a Failed Invoice**
   1. **Failed** queue; the red banner names the failed Stage and the underlying error.
   2. Fix the cause (for example start ref-mcp again).
   3. Press **Rerun from &lt;stage&gt;**. New Stage Runs are added; earlier ones, including the
      failed one, stay in History.
3. **Pause the poller**: sidebar **Pause poller** toggle. **Check inbox now** asks the worker for
   one poll on its next tick, even while paused. The caption shows the last poll time.
4. **Debug a Decision**: the History table shows every Stage Run with trigger, outcome, attempts,
   the model that served it, timings and error. Stage Run inputs (the IDs of the runs it read) and
   outputs are in the SQLite store; LLM calls are in LangSmith when a key is set.

**An Operator must never be able to**
- Rerun an Invoice that is not Failed, or rerun from a Stage later than the one that failed.
- Rerun into submission an Invoice whose Decision is Hold and that nothing Released.
- Submit the same Invoice Version twice: the idempotency key returns the original ClinRun ID.

## Limits of the role model

Roles are not enforced. Any name in the picker can do any action; the guards above apply to every
actor equally. Role-based permissions are a production-story item ([decisions.md](decisions.md),
S3/S4 deferred findings).
