# PRD: AI Email Invoice Ingestion and Matching Assistant

Sources: [project brief](source/project-brief.md), [starter README](source/starter-readme.md),
[decisions](decisions.md), [ADRs](adr/), [glossary](../GLOSSARY.md). Capitalised terms are defined in the glossary.
Each user story is tagged with its release tier: **P0** ships first, **P1** follows if time allows,
**P2** is the roadmap.

## Problem Statement

Clinical trial sites email their invoices to the sponsor's accounts-payable team. No two sites format
them alike: sponsor names drift ("Northwind Pharmaceuticals Inc." vs "Northwind Pharma"), protocol
numbers carry typos, site names don't match the master record, and line items are written in each
site's own shorthand ("UA", "Hepatic Function Panel", "Drug Shipping (cold chain)").

Today a Reviewer reads every Invoice by hand. They work out which sponsor, study and site it belongs
to, find the right Catalog, pair each Line Item with a Catalog Item, check the prices and key it into
ClinRun. This is slow, and it doesn't scale as study volume grows. Errors also repeat: when the
Context is misidentified, every line is matched against the wrong Catalog, and the rework is
discovered late.

The Reviewer's real expertise is needed only for the exceptions: a price that doesn't match, a
service that isn't in the Catalog, a header that doesn't line up. Yet the clean invoices take up most
of their day. Whoever keeps the process running (the Operator) also has no clear view of where an
Invoice is in processing, or why one got stuck.

## Solution

Invoices are processed by AI from arrival to Decision, with no human step in between. A Message lands
in the inbox, and the system then:

1. extracts the Invoice Header and Line Items;
2. resolves the Context through the reference data, with a computed Context Confidence;
3. matches every Line Item against that sponsor and study's Catalog;
4. decides to **Submit** the Invoice to ClinRun or **Hold** it, with written reasons.

Clean invoices go straight through. Anything risky is held, with each Hold Reason spelled out.

The Reviewer works in the Hub after the fact. The Hub shows what was extracted, what was matched,
how confident the system was, and why it decided as it did. From there the Reviewer corrects the
Context or a Line Match and lets the pipeline rerun, Releases a business-judgement hold with a
reason, or Escalates. The AI does the routine work, and people spend their time on the exceptions.

The Operator sees every Invoice's stage-by-stage history and the Failed queue. They can rerun a
Stage, and pause or trigger the inbox poller.

Safety comes from the decision design, not from a person approving each Invoice first: hard checks
force a Hold, and the LLM can add a Hold but never clear one ([ADR-0002](adr/0002-llm-can-add-holds-never-clear-them.md)).
When the system isn't sure of the Context, it stops before matching and holds, with a Suggested
Context ready for the Reviewer ([ADR-0001](adr/0001-no-human-gate-hold-on-uncertain-context.md)).

## User Stories

### Intake

1. **P0** As an Operator, I want emails dropped into the inbox folder to be picked up automatically, so that invoices are processed without anyone starting them.
2. **P0** As a Reviewer, I want each PDF attached to a Message processed as its own Invoice, so that an email carrying two invoices produces two independent Decisions.
3. **P0** As a Reviewer, I want each Invoice linked to the Message it came from, showing sender, subject, received time and body, so that I can see where it came from.
4. **P0** As a Reviewer, I want a Message with no PDF or image file recorded as a Rejected Message with its reason, so that nothing that arrived disappears without trace.
5. **P0** As a Reviewer, I want a Rejected Messages list in the Hub, so that I can follow up with a site that forgot its attachment.
6. **P1** As a Reviewer, I want to upload an invoice file directly in the Hub, so that I can process an invoice that reached me outside the inbox.
7. **P1** As a Reviewer, I want an uploaded file treated exactly like an emailed one, so that one process and one audit trail cover both.
8. **P1** As a Reviewer, I want image invoices (PNG, JPG) accepted, so that sites that send a photo or a screenshot are still processed.
9. **P1** As an Operator, I want to pause the inbox poller and trigger an immediate check, so that I control when processing starts, for example during a demo or an incident.
10. **P2** As a Reviewer, I want an Invoice whose file, or whose invoice number and site, matches one already received held as a Possible Duplicate, so that the sponsor is never billed twice.

### Extraction

11. **P0** As a Reviewer, I want the invoice number, invoice date, site, PI, sponsor, study, protocol and total extracted from the Invoice, so that I don't have to read the PDF to know what it is.
12. **P0** As a Reviewer, I want every Line Item extracted with its description, quantity, unit price and amount as the site wrote them, so that I can compare them with the Catalog.
13. **P0** As a Reviewer, I want the extracted Invoice Header and Line Items shown next to the original document, so that I can check the extraction at a glance.
14. **P0** As a Reviewer, I want an Invoice held when the line amounts don't add up to quantity × unit price, or don't sum to the printed total, so that arithmetic errors never reach ClinRun.
15. **P1** As a Reviewer, I want an image Invoice held as "extraction unverifiable", a reason I can Release, so that numbers read from a picture get a human glance before submission.
16. **P2** As a Reviewer, I want every extracted number checked against the document's own text, and the Invoice held when one cannot be found, so that the AI cannot invent a figure.

### Context resolution

17. **P0** As a Reviewer, I want the sponsor, study and site resolved to reference records even when the printed names drift, so that minor spelling differences don't create work.
18. **P0** As a Reviewer, I want a computed Context Confidence for each of sponsor, study and site, so that I can see how sure the system is about each one.
19. **P0** As a Reviewer, I want the evidence behind each resolved field shown (the header text, the matched record, similarity, Corroboration), so that I understand why it was chosen.
20. **P0** As a Reviewer, I want Corroboration (the study belongs to the sponsor, the site is linked to the study, the PI matches the site) used to rank candidates, so that the most consistent Context comes first.
21. **P0** As a Reviewer, I want a field whose own header text matches weakly to stay uncertain however strong the Corroboration, so that an Invoice with a wrong header is never submitted without someone looking at it.
22. **P0** As a Reviewer, I want matching skipped and the Invoice held as "Context uncertain" when any field is below threshold, so that nothing is matched against the wrong Catalog.
23. **P0** As a Reviewer, I want a held Invoice's Suggested Context already filled in, so that confirming the right answer takes one click.
24. **P0** As a Reviewer, I want an Invoice held when its site is not linked to its study, so that a site cannot bill a study it doesn't take part in.
25. **P0** As a Reviewer, I want the context-resolution agent's lookups visible, so that I can see how the AI searched for the Context.
26. **P2** As a Reviewer, I want Email Hints (sender domain, subject, body) to support a candidate, and a contradiction with the Invoice Header held, so that the email's information is used without overriding the document.

### Matching

27. **P0** As a Reviewer, I want each Line Item matched to a Catalog Item from the resolved sponsor and study's Catalog only, so that items are never priced against another study's Catalog.
28. **P0** As a Reviewer, I want reworded and abbreviated descriptions matched correctly ("CBC" to "Complete Blood Count", "UA" to "Urinalysis"), so that site shorthand doesn't create holds.
29. **P0** As a Reviewer, I want every Line Match to show a confidence label, a reason and any alternatives considered, so that I can judge close calls.
30. **P0** As a Reviewer, I want a Line Item with no plausible Catalog Item marked Unmatched, so that out-of-catalog charges such as parking or patient stipends are flagged.
31. **P0** As a Reviewer, I want a Line Item with more than one plausible Catalog Item marked Ambiguous, with the alternatives listed, so that I make the call rather than the AI.
32. **P0** As a Reviewer, I want price used as evidence when choosing between candidates, while the line still shows as Ambiguous, so that the best guess is offered and the close call stays visible.
33. **P0** As a Reviewer, I want matching to work the same on a 100-item Catalog as on a 7-item one, so that large studies don't break the workflow.
34. **P0** As a Reviewer, I want the full Catalog fetched every time, whatever its size, so that no Catalog Item is silently missing from matching.

### Decision

35. **P0** As a Reviewer, I want each Invoice to end in exactly one Decision, Submit or Hold, with a written rationale, so that I always know what happened and why.
36. **P0** As a Reviewer, I want any Unmatched, Ambiguous, Price Variance, uncertain Context, unlinked site or arithmetic inconsistency to force a Hold, so that known risks are never submitted.
37. **P0** As a Reviewer, I want a Price Variance raised whenever the unit price differs from the Catalog price by more than the tolerance (exact by default), so that overcharges are caught.
38. **P0** As a Reviewer, I want a billed amount against a Catalog Item priced at $0.00 treated as a Price Variance, so that open-priced items always get a human look.
39. **P0** As a Reviewer, I want the LLM to review an Invoice that passed every hard check and be able to hold it, giving its concern, so that risks the rules don't cover are still caught.
40. **P0** As a Reviewer, I want it guaranteed that the LLM can never turn a failed hard check into a Submit, so that a model mistake cannot cause a False Submit.
41. **P0** As a Reviewer, I want every Hold to list each of its Hold Reasons separately, so that I can deal with them one by one.
42. **P0** As a Reviewer, I want a clean Invoice submitted to ClinRun automatically and its ClinRun ID shown, so that routine invoices need no human time.

### Submission

43. **P0** As a Reviewer, I want each submission to carry the Context IDs, every Line Match with both the Catalog Item and the text as billed, the totals and the rationale, so that ClinRun receives everything it needs to pay.
44. **P0** As a Reviewer, I want a rerun or retry of an Invoice never to submit it twice, so that ClinRun never receives duplicates.
45. **P0** As a Reviewer, I want a Released Invoice's submission to carry my Release reason and my name, so that the override travels with the record.

### Review and QC in the Hub

46. **P0** As a Reviewer, I want queues for Held, Escalated, Submitted, Failed and Rejected, so that I can see my workload at a glance.
47. **P0** As a Reviewer, I want the Held queue to show each Invoice's Hold Reasons in the list, so that I can choose what to work on first.
48. **P0** As a Reviewer, I want one Invoice detail view showing the extraction, the Context with confidence, the Line Matches, the Decision with Hold Reasons and rationale, and the Stage history, so that I can review without hunting.
49. **P0** As a Reviewer, I want to also open a Submitted Invoice and see why it went straight through, so that I can check the AI's automatic decisions.
50. **P0** As a Reviewer, I want to correct the Context by choosing any sponsor, study or site from the full reference lists, not only from the suggestions, so that I can fix a header the AI couldn't place at all.
51. **P0** As a Reviewer, I want a Correction to rerun the affected Stages automatically, and the new Decision to be made by the AI, so that a corrected Invoice can still go straight through.
52. **P0** As a Reviewer, I want to Release a Hold with a required reason when every Hold Reason is a business judgement (Price Variance, Unmatched, Ambiguous, LLM concern, image unverifiable), so that agreed exceptions can be paid.
53. **P0** As a Reviewer, I want Release refused while a Hold Reason that needs a Correction remains (uncertain Context, unlinked site, arithmetic inconsistency), so that we never bill the wrong study.
54. **P0** As a Reviewer, I want to Escalate an Invoice with a required note, so that what I can't resolve gets a second look.
55. **P0** As a Reviewer, I want an Escalated queue that any Reviewer can work, so that escalations don't depend on one person.
56. **P0** As a Reviewer, I want to choose who I'm acting as, so that every action is attributed to someone.
57. **P0** As a Reviewer, I want every action I take recorded with who, when, what and why, so that the audit trail is complete.
58. **P1** As a Reviewer, I want to correct a single Line Match by choosing a Catalog Item or marking it Unmatched, so that I can fix one line without changing the rest.
59. **P1** As a Reviewer, I want to see the AI's original Decision next to the one after my Correction, so that the effect of my change is clear.
60. **P2** As a Reviewer, I want to correct an Invoice that was already submitted, so that a mistake found after submission can still be fixed.
61. **P2** As a Reviewer, I want a correction to a submitted Invoice to create a new Invoice Version and go to ClinRun as an Amendment linked to the original, only after I approve it, so that the original record stays intact and nothing is withdrawn.
62. **P2** As a Reviewer, I want the full Invoice Version history, so that I can see every state the Invoice has been in.

### Operations and reliability

63. **P0** As an Operator, I want each Invoice's status to show which Stage it is in as it runs (Received, Extracted, Context Resolved, Matched, Decided), so that progress is observable.
64. **P0** As an Operator, I want every Stage Run recorded with its inputs, output, timing and the reason it ran, so that I can debug any Decision after the fact.
65. **P0** As an Operator, I want a failing Stage retried automatically twice with backoff, so that brief outages of the LLM or the reference API don't need me.
66. **P0** As an Operator, I want an Invoice whose retries are exhausted marked Failed at that Stage, kept separate from Held, so that "the system couldn't decide" never looks like "the system decided to hold".
67. **P0** As an Operator, I want to rerun a Failed Invoice from the Stage that failed, so that recovery doesn't repeat completed work.
68. **P0** As an Operator, I want reruns to add Stage Runs rather than overwrite them, so that the history of attempts is preserved.
69. **P0** As an Operator, I want Invoices processed one at a time, oldest first, so that behaviour and timings are predictable.
70. **P0** As an Operator, I want the whole system started with one command, so that setup is reliable on any laptop.
71. **P0** As an Operator, I want the system to keep running when tracing is unavailable, so that a network problem never stops invoice processing.
72. **P0** As an Operator, I want every LLM call traced to LangSmith when a key is configured, so that I can inspect prompts, tokens and latency.
73. **P1** As an Operator, I want per-Stage timings in the Hub, so that I can spot slow Stages.

### Metrics

74. **P1** As a Reviewer, I want the Straight-Through rate shown, so that I know how much work the AI is taking off me.
75. **P1** As a Reviewer, I want the estimated time saved shown, comparing a manual baseline (minutes per Invoice and per Line Item, with the assumptions on screen) against actual processing time, so that the benefit is measurable.
76. **P1** As a Reviewer, I want counts of Holds by Hold Reason, so that recurring problems with sites or Catalogs become visible.

### Quality

77. **P0** As an Operator, I want an eval run over the labelled sample invoices that fails if any False Submit occurs, so that a prompt or model change can't quietly make the system unsafe.
78. **P0** As an Operator, I want the eval to report Decision accuracy, Hold Reason recall, Context accuracy and Line Match accuracy against their thresholds, so that quality is measured, not assumed.
79. **P2** As an Operator, I want a synthetic set of scenario-built invoices whose labels are correct by construction, so that every Hold Reason and edge case is evaluated, not just the four samples.
80. **P2** As an Operator, I want rationale faithfulness graded by an LLM judge, so that explanations stay grounded in the data.

## Implementation Decisions

### Shape

- **Fixed Stages, one agent loop.** The pipeline runs fixed Stages in a fixed order: extraction, context resolution, matching, decision, submission. Extraction, matching and the decision review are each a single structured LLM call. The only agent loop is in context resolution: a tool-calling agent over the reference-data MCP tools, because that is where the AI must choose which lookups to make. Context Confidence is still computed, not chosen by the agent. **P0.**
- **No human gate** ([ADR-0001](adr/0001-no-human-gate-hold-on-uncertain-context.md)). If any Context field is uncertain, matching is skipped and the Invoice is held.
- **Hard checks override the LLM** ([ADR-0002](adr/0002-llm-can-add-holds-never-clear-them.md)). The LLM can add Holds, never clear them.
- **Processing is sequential.** One Invoice at a time, oldest first, in a long-running worker separate from the Hub, so the Hub never waits on an LLM. A queue with scaled-out workers is the production design.
- **Model.** `claude-sonnet-5-5` for every LLM call, including the eval judge. The model name is configuration.
- **Runtime.** One Docker Compose stack: Postgres and the reference API (as provided), ref-mcp, mock-clinrun, and the app (worker and Hub). App state lives in a single SQLite file on a volume, and the inbox folder is mounted. The app can also run natively against the containers. The only required secret is the Anthropic key; LangSmith is optional at runtime and required for evals.

### Modules

| Module | Interface | Hides |
|---|---|---|
| **Intake** | Turns a source item (an inbox file, or an upload in P1) into a Message with its Invoices, or a Rejected Message | Parsing email, sorting attachments, rejection reasons, file hashing. Behind it is a MessageSource adapter, so IMAP is a later swap. |
| **Extraction** | Turns an invoice file into an Invoice Header, Line Items and a verification result | The prompt and schema, reading PDFs and images natively, the image "unverifiable" result (P1), and checking numbers against the document's text (P2) |
| **ref-mcp** (service) | MCP tools: search sponsors by text; search studies by text, optionally within a sponsor; search sites by name, optionally with a PI; list a study's sites; get a Catalog for a sponsor and study | REST calls, paging (the reference API pages at 50 by default, which would cut a 100-item Catalog in half), fuzzy scoring and name normalisation |
| **Context Resolution** | Turns an Invoice Header (plus Email Hints in P2) into a Context: for each of sponsor, study and site, its candidates, Context Confidence, evidence and the Suggested Context | The agent loop over ref-mcp, combining scores, Corroboration that ranks but cannot lift a weak field, thresholds |
| **Matching** | Turns Line Items plus a Catalog into Line Matches | The prompt, the whole Catalog in one call, price as evidence, Ambiguous and Unmatched labels with their alternatives |
| **Decision** | Turns an Invoice Version's state into a Decision: Submit or Hold, Hold Reasons, rationale | Each hard check as a pure rule, the price tolerance, the $0.00 rule, the LLM review, and the guarantee that the LLM cannot clear a hold |
| **Pipeline** | Processes an Invoice Version from a given Stage, for a given reason | Stage order, skipping matching when Context is uncertain, retries (two, with backoff), the Failed status, writing Stage Runs, status changes |
| **Review Actions** | Correct Context, correct a Line Match (P1), Release, Escalate, rerun from a Stage, approve an Amendment (P2) | Which Hold Reasons can be Released, required reasons and notes, audit records, starting the Pipeline |
| **Store** | Repositories for Messages, Invoices, Invoice Versions, Stage Runs, Decisions and Actions, plus the queue queries | The SQLite schema; writes only ever append |
| **ClinRun Client** | Submit, and amend (P2) | HTTP, the idempotency key, treating a duplicate as success |
| **mock-clinrun** (service) | Accept a submission; accept an Amendment (P2); list submissions | Its own store, idempotency. Shallow, deliberately. |
| **Worker** | Poll, process, pause, check now (P1) | The loop and its control flags. Shallow, deliberately. |
| **Hub** | Queues, Invoice detail, QC actions, Operator controls, upload (P1), metrics (P1) | Layout, caching, fragments. Shallow, deliberately: it only calls Review Actions and Store queries. |
| **Metrics** (P1) | A summary over a time window: Straight-Through rate, Stage timings, Holds by reason, time saved | Queries and the manual-baseline assumptions. Shallow, deliberately. |
| **Eval Runner** (tooling) | Runs a labelled dataset, returns metrics and whether the gate passed | Uploading the dataset to LangSmith, running experiments, comparing results with the labels |
| **Gold Set Generator** (tooling, P2) | Generates scenario invoices, as PDFs plus `.eml` files, with their labels | The starter's invoice layout, a curated table of wording variants, a fixed random seed |
| **Reference API** | Unchanged | Kept as provided, apart from the ISSUE-001 dependency pin |

The deep modules are **Decision**, **Context Resolution** and **Pipeline**. Most of the behaviour and
most of the deterministic tests sit behind their interfaces.

### Data model (app store)

- **Message**: its source (inbox or upload), sender, subject, body, received time, and a rejection reason if rejected.
- **Invoice**: belongs to one Message, with the file, its hash, the file type and the current status.
- **Invoice Version**: belongs to one Invoice and is numbered. P0 creates only the first version; an Amendment creates the next (P2).
- **Stage Run**: belongs to an Invoice Version. Records the Stage, run number, trigger (automatic, Correction, Operator rerun), inputs, output, attempts, start and end times, and outcome (succeeded or failed). Stage Runs are never overwritten; the Invoice Version points to its latest run for each Stage.
- **Decision**: belongs to a Stage Run. Records Submit or Hold, the Hold Reasons, the rationale, and whether the Invoice went straight through.
- **Action**: belongs to an Invoice. Records who acted, when, the kind of action (Correction, Release, Escalation, rerun, Amendment approval), the reason or note, and the before and after values.
- **Submission**: belongs to an Invoice Version. Records the ClinRun ID, the idempotency key and the time it was sent.

**Status lifecycle:** Received → Extracted → Context Resolved → Matched, then Submitted or Held.
- **From Held:** Correction (rerun from the affected Stage), Release (to Submitted) or Escalation (to Escalated).
- **From any Stage:** retries exhausted leads to Failed, and a rerun from that Stage resumes.
- **From Submitted (P2):** a Correction leads to Amendment Pending, then Amended.
- **Rejected Messages** never become Invoices.

### Contracts

**ClinRun submission:**
- **Idempotency key:** a hash of the file plus the Invoice Version.
- **Invoice:** number, date, currency (USD only) and total.
- **Context:** sponsor, study and site IDs.
- **Lines:** for each, the Catalog Item's ID and code, the description as billed, quantity, unit price, amount, and a Price Variance flag.
- **Decision:** the rationale, and whether it went straight through.
- **Release, if any:** the reason and the Reviewer.
- **Source:** the Message ID and the time it was received.

The response is a ClinRun ID with status *accepted*. A repeated idempotency key returns the original
ClinRun ID rather than an error. An Amendment (P2) has the same shape, plus a reference to the
original ClinRun ID and a summary of the Correction.

**ref-mcp search tools** return a ranked list of candidates. Each candidate carries the record's ID,
its name or protocol, a similarity score and the reference fields that support Corroboration
(sponsor of a study, PI of a site). The Catalog tool always returns the complete Catalog.

### Thresholds and rules (configuration)

- **Context Confidence threshold:** one per field. The starting values are tuned on the labelled samples.
- **Price tolerance:** 0% by default (amounts compared to the cent).
- **$0.00 Catalog price:** taken literally, so any billed amount is a Price Variance.
- **Release:** allowed for Price Variance, Unmatched, Ambiguous, LLM concern and image unverifiable. Not allowed for uncertain Context, unlinked site, arithmetic inconsistency, unverified extraction (P2) or Possible Duplicate (P2).
- **Time-saved baseline (P1):** configurable minutes per Invoice and per Line Item.

## Testing Decisions

- **A good test checks behaviour through a module's interface.** It gives inputs and asserts on outputs and recorded state, never on prompts, internal helpers or call order. LLM-backed modules are tested deterministically with a fake LLM at the LLM seam. Their real quality is measured by evals, not unit tests.
- **Bar:** every core path and every exception path has a test. There is no percentage target.
- **Levels:**
  - **Through the interface:**
    - Decision: every hard check, the tolerance, the $0.00 rule, Release eligibility, and the guarantee that the LLM cannot clear a hold.
    - Context Resolution scoring: the similarity floors, Corroboration ranking without lifting a weak field, the unlinked site.
    - Review Actions, Intake, Metrics.
  - **Integration:**
    - The Pipeline with the real Store (in-memory SQLite) and faked Stages, including injected failures for retries, Failed and rerun from a Stage.
    - ref-mcp against the reference API running in Compose, including full Catalog paging on the 100-item Catalog.
    - The ClinRun Client against mock-clinrun, including idempotency.
  - **AI eval:**
    - The four sample invoices, hand-labelled with the expected Context, the expected Catalog Item (or Unmatched or Ambiguous) for each line, the expected Decision and the expected Hold Reasons.
    - Run as a LangSmith experiment, with the gate: zero False Submits; Decision accuracy, Hold Reason recall and Line Match accuracy at least 90%; Context accuracy at least 95%. The synthetic set and the rationale judge are P2.
  - **Smoke:** the whole Compose stack runs the four sample emails to their expected outcomes:
    - simple: Submit
    - medium: Hold for Price Variance
    - large: Hold for Unmatched, Ambiguous and Price Variance
    - mismatched-metadata: Hold for uncertain Context, then Correction, then Submit
  - **Component:** the Hub through Streamlit's app-testing harness. Each queue renders, and each QC action calls the matching Review Action.
- **Prior art:** the reference API's regression test for ISSUE-001 (standard-library unittest, run inside its container). App tests use pytest. Bug fixes follow the issue-log convention: a failing test with the issue ID first, then the fix.

## Out of Scope

Neither source document requires any of these; they are optional, or not mentioned:

- Live mailbox connectors (IMAP, Gmail, Graph). The inbox is a local folder.
- PDFs containing more than one invoice, and file types other than PDF and image.
- Currencies other than USD, and tax or VAT lines.
- Authentication and roles. Identity comes from an "acting as" picker, and auth is assumed solved upstream.
- Requiring a second person to approve Amendments, and notifications for Escalations.
- Learning from Corrections (site alias memory).
- Narrowing the Catalog with embeddings or retrieval before matching.
- Parallel processing.
- A real ClinRun integration, and withdrawing a submission.
- Changes to the reference API beyond the ISSUE-001 dependency pin.
- Cloud deployment. The AWS production design is described, not built.
- A production front end. The Hub is built to be swappable.

## Further Notes

- **Release plan.**
  - **P0** (days 1–2) meets every brief requirement in its simplest form. It is built as vertical slices behind a tracer bullet, a thin first path through every component: the simple sample runs from email to Submit through every component.
  - **P1** (day 3) adds Line Match Correction, the metrics strip, upload, image invoices, the short documentation set and the demo video.
  - **P2** is the roadmap: Amendments, the synthetic gold set and rationale judge, number checking against the document text, Email Hints, Possible Duplicate, and the full documentation set.
- **Expected outcomes for the samples:**

  | Sample | Expected Decision | Why |
  |---|---|---|
  | simple | Submit | Clean matches |
  | medium | Hold | Price Variance: IRB fee $550 vs the Catalog's $500 |
  | large | Hold | Three Unmatched items, an Ambiguous cold-chain shipping line, and a Price Variance on the CT scan |
  | mismatched-metadata | Hold, unmatched | Uncertain Context: the site matches no record. The Suggested Context is VERITAS at Prairie Field Research Group, the correct answer. |

- **Deliberate deviation from the starter.** The starter makes metadata confirmation a hard gate; this
  product does not ([ADR-0001](adr/0001-no-human-gate-hold-on-uncertain-context.md)). The starter's
  write-up questions (prompt design, handling partial metadata failure, what's next) are answered in
  the README.
- **Assumptions:** one invoice per file; USD; the reference data is current; whoever is acting in the
  Hub has already been authenticated upstream.
- **Production story** (slides, not built): a queue with scaled-out workers on ECS/Fargate, RDS for
  the app store, a real mailbox connector, the real ClinRun API, managed secrets, LangSmith plus
  CloudWatch, and a CI pipeline whose eval gate blocks deploys on any False Submit.
