# Invoice Ingestion

How clinical trial site invoices that arrive by email are read, put in context, matched to a sponsor's catalog, and either submitted to ClinRun or held for review.

## Language

### Intake

**Message**:
One arrival of invoice files: an email received in the inbox, with its sender, subject, body and attachments, or a file a Reviewer uploaded in the Hub.
_Avoid_: Email (as a domain term), mail item

**Invoice**:
One PDF or image file of a Message, requesting payment from a sponsor for work a site did on a study. Each file is assumed to hold exactly one invoice.
_Avoid_: Document, bill, attachment (when meaning the invoice)

**Rejected Message**:
A Message that yields no Invoice because it has no PDF or image file. It is kept, with the reason, rather than discarded.
_Avoid_: Spam, junk, dropped email

**Possible Duplicate**:
An Invoice whose file, or whose invoice number and site, matches an Invoice already received.
_Avoid_: Resend, copy

### Context

**Context**:
The sponsor, study and site an Invoice belongs to, identified as records in the reference data. The sponsor and study together select the Catalog.
_Avoid_: Metadata (for the resolved records), header

**Invoice Header**:
The sponsor, study, protocol, site and PI text exactly as printed on the Invoice, before it is resolved to a Context. It is the authoritative source for the Context.
_Avoid_: Metadata, extracted context

**Email Hint**:
Context evidence from the Message rather than the Invoice: sender domain, subject or body. It can support a candidate, and if it contradicts the Invoice Header, the Invoice is held.
_Avoid_: Email metadata

**Context Confidence**:
A computed score for each Context field, based on how closely the Invoice Header text matches a record. Corroboration can rank candidates but cannot raise a weak field above the threshold.
_Avoid_: AI confidence, certainty

**Corroboration**:
Evidence that ties Context fields to one another rather than to header text: the study belongs to the sponsor, the site is linked to the study, the PI matches the site.
_Avoid_: Cross-validation

**Suggested Context**:
The highest-ranked candidate Context offered to a reviewer when an Invoice is held for uncertain context.
_Avoid_: Default, guess

### Matching

**Catalog**:
The billable items a sponsor has agreed to pay for on one study, each with a code, description, category and fixed unit price. A Catalog belongs to exactly one sponsor and study.
_Avoid_: Price list, fee schedule, budget

**Catalog Item**:
One billable entry in a Catalog. Its code is unique only within its Catalog.
_Avoid_: SKU, product, service

**Line Item**:
One billed row on an Invoice: description, quantity, unit price and amount, as the site wrote them.
_Avoid_: Charge, entry, row

**Line Match**:
The pairing of a Line Item to one Catalog Item, or to none, with a confidence label (high, medium or low), a reason and any alternatives considered.
_Avoid_: Mapping, link

**Unmatched**:
A Line Item with no Catalog Item in its Catalog.
_Avoid_: Unknown, missing

**Ambiguous**:
A Line Item with more than one plausible Catalog Item.
_Avoid_: Uncertain (reserved for Context)

**Price Variance**:
A Line Match where the Line Item's unit price differs from the Catalog Item's price by more than the tolerance.
_Avoid_: Price mismatch, overcharge

### Processing

**Stage**:
One step of processing an Invoice: extraction, context resolution, matching, decision, submission.
_Avoid_: Step, phase, node

**Stage Run**:
One execution of a Stage for an Invoice Version, with its inputs, output, timing and the reason it ran. Stage Runs are never overwritten; a rerun adds a new one.
_Avoid_: Attempt (reserved for retries within a run), job

**Invoice Version**:
One state of an Invoice's processed content. The first comes from intake, and an Amendment creates the next. Earlier versions are kept.
_Avoid_: Revision, copy

### Decision and review

**Reviewer**:
The person who checks the AI's Decisions after the fact and acts on Invoices: Correction, Release, Escalation, Amendment approval.
_Avoid_: Approver, AP clerk, user

**Operator**:
The person responsible for the pipeline running: Failed Invoices, reruns, stage timings and traces.
_Avoid_: Admin, support, DevOps

**Hub**:
The reviewer's workspace, showing what was extracted, what was matched, confidence and Hold Reasons, and each Decision, and where reviewers act on Invoices after the AI has decided.
_Avoid_: Dashboard, portal, console

**Decision**:
The AI's outcome for an Invoice: Submit or Hold, with a written rationale.
_Avoid_: Verdict, result, approval

**Hold**:
A Decision not to send an Invoice to ClinRun until a reviewer acts. A Hold always carries at least one Hold Reason.
_Avoid_: Exception (as a status), reject, block

**Hold Reason**:
One specific cause of a Hold, such as Price Variance, Unmatched, Ambiguous, uncertain Context or Possible Duplicate. Some Hold Reasons can be Released; others need a Correction.
_Avoid_: Error, flag, issue

**Release**:
A reviewer's choice to submit a held Invoice, with a required reason: as billed, or with Price Variance lines paid at the Catalog price (the billed price is kept on the record). It is allowed only for Hold Reasons that are business judgements.
_Avoid_: Override, approve, force-submit

**Correction**:
A reviewer's change to the Context or to a Line Match, after which the affected stages run again.
_Avoid_: Edit, fix, adjustment

**Failed**:
An Invoice whose processing stopped because a stage could not complete, so no Decision was made. Distinct from a Hold, which is a Decision.
_Avoid_: Error state, held (for failures)

**Amendment**:
A Correction to an Invoice already submitted, sent to ClinRun linked to the original submission once a reviewer approves it. The original submission is never withdrawn.
_Avoid_: Resubmission, recall, revision

**Escalation**:
A reviewer's handoff of an Invoice they cannot resolve, with a required note explaining why.
_Avoid_: Referral, ticket

**Straight-Through**:
An Invoice that reached Submit with no human action.
_Avoid_: Auto-approved, touchless

**False Submit**:
An Invoice the AI submitted when it should have been held. It is the costliest error the system can make.
_Avoid_: False positive (ambiguous direction)

**Over-Hold**:
An Invoice the AI held when it could have been submitted. It costs reviewer time but no money.
_Avoid_: False negative
