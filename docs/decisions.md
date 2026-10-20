# Decisions: brief vs starter conflicts

The project has two source documents (see [source/](source/README.md)) that disagree in places:
the **brief** ([project-brief.md](source/project-brief.md), 2026-10-12) and the **starter README**
([starter-readme.md](source/starter-readme.md), from `ledgerrun/ai-takehome-test`). The brief is the
newer document and wins by default. Each call below was agreed on 2026-10-19.

| # | Topic | Decision |
|---|-------|----------|
| 1 | Human gate | **No gate** (brief). The starter's gate survives only as #4: hold when context is uncertain. |
| 2 | Intake | Local `.eml` inbox folder, polled. IMAP or Gmail is a drop-in swap later. |
| 3 | Reference API access | Our own MCP server (FastMCP) wrapping the starter's REST API. The agent only speaks MCP. |
| 4 | Uncertain context | Any context field below threshold: skip matching and **hold**. The reviewer fixes the context and reruns. |
| 5 | Submit/hold decision | Hard rules force holds; the LLM may add holds, never clear them, and writes the rationale. |
| 5a | Price tolerance | Exact match by default (cent rounding); one config value. Pass-through items skip the check. |
| 6 | ClinRun backend | Mock ClinRun service in Compose; idempotency key = invoice hash. |
| 7 | Correcting a submitted invoice | Amend, don't un-submit: a new version reruns downstream and goes as a linked amendment, after human approval. |
| 8 | Deliverables | Union of both documents, plus this file. |
| 9 | Runtime | One Docker Compose stack for the whole system; the app can also run natively against it. |

## 1. Human gate

- **Starter:** the user must confirm metadata before line-item matching (a hard gate).
- **Brief:** "humans are not a required gate before matching and decisioning"; QC happens after the decision.
- **Decision:** no gate. First agreed as a configurable gate (off by default, pausing only on
  low-confidence context), then dropped in the design review: a gate that pauses on uncertain context
  does exactly what #4's hold already does (same trigger, same stopping point, same reviewer action).
- **Why:** this follows the brief's principle. People step in only when the AI isn't sure, which is
  the useful part of the starter's gate, and there is one less mode to build, test and explain.

## 2. Intake

- **Starter:** file upload. **Brief:** "ingest invoices from email".
- **Decision:** we generate realistic `.eml` messages (varied senders, subjects, bodies, PDF attached)
  into an `inbox/` folder that a poller ingests. Headers and body are parsed for context hints
  alongside the PDF.
- **Why:** real email format, but offline and safe for a live demo. Live IMAP is a production-story item.

## 3. Reference API access

- **Starter:** REST API only. **Brief:** "via the MCP-wrapped reference API".
- **Decision:** a small Python MCP server (FastMCP) exposes the lookups (sponsors, studies, sites,
  study-sites, scoped catalog) as tools, each calling the starter's REST API. The REST API is unchanged.
- **Why:** meets the brief with one clear seam, and keeps the provided service untouched.

## 4. Uncertain context (gate off)

- **Starter:** the user selects the correct entity manually. **Brief:** silent.
- **Decision:** if any of sponsor, study or site is below the confidence threshold, matching does not
  run and the invoice is held as "context uncertain", with candidates and evidence shown in the hub.
  The reviewer corrects the context and reruns from matching.
- **Why:** a wrong context means the wrong catalog, which produces confident-looking wrong matches.
  Stopping is the safe default.
- **Effect on samples:** the mismatched-metadata invoice holds here; its site matches no seeded site.

## 5. Submit/hold decision

- **Starter:** the user submits. **Brief:** "make an AI decision to submit … or hold".
- **Decision:** a hybrid.
  1. **Hard checks** force a hold: unmatched line item, price outside tolerance, ambiguous match,
     low match or context confidence, site not linked to study, line amounts or totals inconsistent.
  2. If none fire, the **LLM reviews** the whole invoice and may still hold, giving a reason.
  3. The LLM can add holds, never clear one. It writes the rationale for every decision.
- **5a. Price tolerance:** unit price must equal the catalog price (cent rounding allowed). The
  tolerance is one config value, default 0%. Pass-through items with no fixed price skip the check.
- **Why:** submission is outward-facing and hard to reverse, and with no gate before it, the fixed
  checks take the place of a person's approval. Guardrails are calibrated to risk.

## 6. ClinRun backend

- **Both documents:** nothing is provided.
- **Decision:** a separate mock FastAPI service in Compose, with `POST /submissions`,
  `GET /submissions` and `POST /submissions/{id}/amendments`. The idempotency key is the invoice hash, *(Amendments endpoint: P2, not built.)*
  so a rerun cannot double-submit. It returns a ClinRun ID that the hub displays.
- **Why:** a visible boundary to an external system, which the real ClinRun would replace.

## 7. Correcting a submitted invoice

- **Brief:** "corrections, rerun/escalation", with no detail.
- **Decision:** the original submission stands. A correction creates a new invoice version, reruns
  the downstream stages and, **after a reviewer approves it**, goes to ClinRun as an amendment linked
  to the original. Everything is in the audit log.
- **Why:** a clean audit trail. Amending something already sent is the high-risk tier, so it gets a
  human-in-the-loop step even with the gate off.

## 8. Deliverables

- **Brief:** source code, technical documentation, demo video, AI-usage documentation.
- **Starter:** README (how to run, env vars, full flow) plus a write-up (prompt design,
  partial-metadata-failure handling, what's next).
- **Decision:** all of them, plus this file.
  `README.md` · `docs/prd.md` · `docs/architecture.md` · `docs/decisions.md` · `docs/adr/` ·
  `docs/users.md` · `docs/test_plan.md` · `docs/agents.md` · `docs/ai_log.md` · `docs/ai_usage.md` ·
  `docs/deploy.md` · `docs/runbook.md` · `docs/issue_log.md` · demo video.

## 9. Runtime

- **Starter:** the reference API runs in Compose; your app "may run in the same Docker Compose or
  separately". **Brief:** Docker Compose is a required dev tool.
- **Decision:** one `docker-compose.yml` brings up Postgres, the reference API, ref-mcp,
  mock-clinrun and the app (pipeline worker plus Streamlit hub), with app state in SQLite on a volume
  and `inbox/` mounted. For a fast dev loop, the app can run natively against the containers.

## Design review outcomes (2026-10-19)

Terms are defined in [GLOSSARY.md](../GLOSSARY.md).

| Topic | Decision |
|-------|----------|
| Unit of work | A Message is one email; each PDF attachment is one Invoice (one invoice per PDF, assumed). |
| Rejected Messages, duplicates | A Message with no PDF is recorded as Rejected with a reason. A Possible Duplicate (same file hash, or same invoice number and site) is held. |
| Email vs PDF | The Invoice Header is authoritative. Email Hints are supporting evidence; a contradiction is a Hold Reason. |
| Context Confidence | Computed: fuzzy similarity of header text plus Corroboration. The LLM proposes and explains. |
| Corroboration limit | Corroboration ranks candidates but cannot lift a field whose own text matches weakly. The mismatched-metadata sample holds with a Suggested Context ready. |
| Name matching | The ref-mcp server provides `search_*` tools returning scored candidates (rapidfuzz), and `get_catalog` fetches every page (the default page size of 50 would cut LUMIN's 100 items). |
| Line Match confidence | The LLM gives a high/medium/low label, a reason and alternatives; Ambiguous means more than one plausible item. The price check runs independently. |
| Large catalog | The whole scoped Catalog goes in one call. An embedding pre-filter is documented for catalogs in the thousands; no Chroma. |
| Extraction | The PDF goes natively to Claude with a structured schema. Extracted numbers are cross-checked against local pdfplumber text; a number that isn't found is a Hold Reason. | *(P2: the text cross-check is not built; image invoices hold as extraction_unverifiable.)*
| $0.00 catalog prices | Taken literally: any billed amount is a Price Variance (Releasable). |
| Price as tie-break | Price is evidence for the matcher, but the line is still marked Ambiguous and the alternative is recorded. |
| Release | Allowed with a required reason for Price Variance, Unmatched, Ambiguous and LLM concern. Not allowed for uncertain Context, Possible Duplicate or unverified extraction. |
| Escalation | A status with a required note and its own queue. Reviewer identity comes from an "acting as" picker. |
| Stage failure | Two retries with backoff, then Failed at that stage (distinct from a Hold), with a "Rerun from stage" button. |
| Rerun after Correction | Decides autonomously; a clean rerun submits. |
| Lifecycle | Received → Extracted → Context Resolved → Matched → Submitted or Held. Held can be Corrected, Released or Escalated. A Submitted invoice can be Corrected into an Amendment. Any stage can end in Failed. |
| Agent placement | Fixed Python stages. The only agent loop is context resolution, a LangChain tool-calling agent over ref-mcp. Other LLM work is single structured calls. | *(Superseded in S0: the Anthropic SDK tool runner, see the ADR-0008 amendment.)*
| Learning from Corrections | None (audited only). Site alias memory is a documented next step. |
| Hub | Streamlit, built for responsiveness: cached reads, `st.fragment`, and the pipeline in a separate worker. |
| Time saved | Metrics strip: Straight-Through rate, stage timings, and estimated manual time vs actual (assumptions shown). |
| Gold set | Synthetic now: the 4 originals hand-labelled plus about 20 scenario-built invoices whose labels are true by construction, also emitted as `.eml` files. Rewordings come from a curated, frozen variant table. | *(Revised in the PRD split: P0 ships the 4 hand-labelled samples; the synthetic set is P2.)*
| Eval gate | False Submits = 0 (hard). Decision accuracy ≥ 90%, Hold Reason recall ≥ 90%, Context accuracy ≥ 95%, Line Match accuracy ≥ 90%. Straight-Through rate is reported only. |
| Eval platform | LangSmith first (datasets plus experiments). LLM-as-judge grades rationale faithfulness only, reported and not gated. |

## Expected outcome per sample (seed of the eval set)

| Sample | Expected | Driven by |
|--------|----------|-----------|
| simple | Submit | Clean matches with light wording variation |
| medium | Hold | IRB price $550 vs catalog $500 (#5a) |
| large | Hold | 3 unmatched items, CT price mismatch, ambiguous matches (#5) |
| mismatched-metadata | Hold, not matched | Context below threshold (#4) |

## ADR index

| ADR | Decision |
|-----|----------|
| [0001](adr/0001-no-human-gate-hold-on-uncertain-context.md) | No human gate; hold on uncertain Context instead |
| [0002](adr/0002-llm-can-add-holds-never-clear-them.md) | The LLM can add Holds but never clear the hard checks |
| [0003](adr/0003-mcp-server-owns-reference-search.md) | An MCP server wraps the reference API and owns name search |
| [0004](adr/0004-context-confidence-is-computed.md) | Context Confidence is computed, not rated by the LLM |
| [0005](adr/0005-corroboration-ranks-but-cannot-lift.md) | Corroboration ranks candidates but cannot lift a weak field |
| [0006](adr/0006-whole-catalog-in-one-matching-call.md) | Whole Catalog in one matching call, no retrieval |
| [0007](adr/0007-native-pdf-extraction-with-text-check.md) | Native document extraction, checked against the document's own text |
| [0008](adr/0008-fixed-stages-one-agent-loop.md) | Fixed Stages; the only agent loop is in context resolution |
| [0009](adr/0009-failed-is-not-held.md) | Failed is separate from Held; retries and rerun from a Stage |
| [0010](adr/0010-amend-never-withdraw.md) | Corrections after submission are Amendments, never withdrawals |
| [0011](adr/0011-mock-clinrun-idempotent.md) | ClinRun is a separate mock service with idempotent submission |
| [0012](adr/0012-eval-gate-zero-false-submits.md) | The eval gate requires zero False Submits |

## Build decisions (2026-10-19)

| # | Topic | Decision |
|---|-------|----------|
| D1 | Git workflow | One branch per slice. Merge to `main` after the slice's tests and `/code-review` pass, then push to the Gauntlet repo. |
| D2 | P0 slices | S0 tracer bullet (simple → Submit) · S1 hard checks (medium → Hold) · S2 large catalog (large → Hold) · S3 uncertain context and Correction (mismatched → Hold → Submit) · S4 QC and reliability · S5 eval gate |
| D3 | ADRs | 0003–0012 written as short ADRs, one paragraph each. Smaller calls stay in this file. |
| D4 | Time-saved baseline | 5 minutes per Invoice plus 1 minute per Line Item, labelled on screen as an assumption |
| D5 | Secrets | A git-ignored `.env` with a committed `.env.example`. Required: `ANTHROPIC_API_KEY`. Optional: `LANGSMITH_API_KEY`. |
| — | Model | `claude-opus-5-5` for every LLM call, set in configuration |
| — | Tooling (implementer's call) | Python 3.13 with uv (inside the project venv); ref-mcp served over streamable HTTP as its own Compose service (server on mcp 1.x FastMCP, app client on mcp 2.x); the Anthropic SDK tool runner with its MCP helper for the context agent; pytest for app tests |
| — | LLM client (changed in S0) | Anthropic SDK directly; LangChain dropped because Opus 5.5 rejects the forced tool calls and `temperature` it relies on. See the ADR-0008 amendment. Server-side refusal fallbacks (`fallbacks: "default"`) are on for every call. |

## S0 code review: deferred findings (2026-10-19)

Fixed before the S0 merge:
- glossary names in intake
- the "Matched" status shown when matching was skipped
- the total invented from the lines (a missing printed total now holds)
- the study-belongs-to-sponsor check
- Stage Run inputs and the model that served each call
- the ClinRun Client test and the computed-confidence tests
- one threshold per field
- the agent restricted to the search tools
- the unused `price_tolerance`

Deferred:

| Finding | Owner | Note |
|---------|-------|------|
| Retries with backoff (ADR-0009) | S4 | A failure is recorded as Failed on the first error until then |
| "Matching did not run" filed under `context_uncertain` | S1 | Hold Reasons are revisited when the remaining checks land |
| Stage defined in three places; status strings; Catalog as `list[dict]`; `build_submission` arguments | S1 | A refactor once S1 adds the remaining checks and the LLM review |
| Unused `actions` table | S3 | Corrections are its first writer |
| mock-clinrun race between two concurrent first submissions of the same key | Not planned | The worker is sequential; see the production story |
| A rerun from submission adds a second `submissions` row with the same ClinRun ID | S4 | Harmless; the Hub reads the latest |
| Refusal fallbacks | Kept | The model that served each call is now recorded on its Stage Run, so evals can attribute results |

## S1–S4 notes (2026-10-19)

- **$0.00 rule:** it supersedes 5a's "pass-through items with no fixed price skip the check". Every
  line is checked, and $0.00 is taken literally.
- **Low-confidence Line Matches** hold as `ambiguous`, as decision 5.1 requires.
- **Lines the matcher leaves out** count as Unmatched. The checks iterate the Line Items, not the
  matcher's answer, which closes a False Submit path found in review.
- **Release eligibility (Q8):** a Release is allowed only when every Hold Reason is in `RELEASABLE`:
  price_variance, unmatched, ambiguous, llm_concern, extraction_unverifiable. Otherwise it needs a
  Correction.
- **After a Correction,** the LLM review is told the Reviewer confirmed the Context. Without that,
  it re-raised the very question the Reviewer had answered, which caused a needless Over-Hold.
- **Refactors deferred to S1 were not done:** typed Catalog, a Stage registry, `build_submission`'s
  argument list. They are judgement-call smells with no behaviour impact, so they are moved to "not
  planned" in favour of shipping. The checks keep one shared signature on purpose, so `HARD_CHECKS`
  stays a plain list.

## S3/S4 code review notes (2026-10-19)

Fixed before merge:
- **Rerun guard:** an Operator rerun is allowed only for a Failed Invoice, from its failed Stage or
  earlier, and never into submission past a Hold. This closes a False Submit path.
- **Escalation** is allowed only for a Held Invoice.
- **Guards before writes:** every guard runs before anything is written, so a Correction without a
  note leaves nothing behind.
- **Release survives reruns:** a Release carries over to a rerun of a failed submission.
- **Straight-Through:** a Corrected Invoice is never counted as Straight-Through.
- **Missing lines:** a line the matcher left out can be corrected.
- **Hub:**
  - One Store connection per browser session.
  - The single friendly error boundary now also catches unexpected errors.
  - Upload messages are built in Intake.
  - Release eligibility comes from Review Actions.
  - The manual baseline is configuration.

Deferred:
| Finding | Decision |
|---------|----------|
| Rejected Messages shown in an expander, not a queue | Kept; they are not Invoices and need no action, only visibility |
| Metrics cover all time, with no time window | P2 |
| Roles inferred from the actor name, so any actor can rerun | Auth is out of scope; roles are a production-story item |
| Metrics make several queries per Invoice (N+1) | Fine at demo volume; P2 |

## P1 consistency pass (2026-10-19)

From the docs agent's cross-check of the code against the PRD:
- **Fixed:**
  - An unreadable `.eml` is moved to `inbox/failed/` and the worker keeps going.
  - The Compose services restart unless stopped.
  - The submission's `price_variance` flag uses the same tolerance rule as the decision
    (`decision.is_price_variance`).
  - The Hub builds and calls Review Actions inside its one error boundary.
  - The Correction picker starts empty when the agent proposed no record.
  - The eval report is written as UTF-8.
  - Superseded statements are annotated.
- **Accepted limitation:**
  - Hub actions (Correction, Release, rerun) run the Pipeline in the Hub process, so the
    Reviewer waits on the LLM (about 10–60 s, behind a spinner). Automatic processing still runs
    only in the worker.
  - Moving actions onto the worker's queue is the production design: SQS plus workers (deploy.md).
- **Not built, by tier:**
  - P1: showing the original document beside the extraction (story 13), the before/after
    Decision view (story 59), and a separate "Decided" status. Statuses go straight from Matched to
    Submitted or Held.
  - P2: the MessageSource adapter. The worker reads the folder directly; upload writes into the
    same folder.
- **Store:** Stage Runs and Actions are append-only. `invoices.status` and the `control` table are
  current-state fields, updated in place by design.

## Run-through changes (2026-10-20)

- **Release at catalog price (PRD story 52a).** The run-through showed a Reviewer wanting to "correct
  a wrong price". A Correction cannot change a billed figure: Line Items stay as the site wrote them
  (story 12). A Release now offers two choices for Price Variance lines: accept as billed, or pay the
  Catalog price. Paying the Catalog price sends the Catalog unit price and amount to ClinRun, and adds
  the billed unit price and amount to the line, so the record still shows what the site invoiced. The
  invoice total stays the printed total. It is recorded as a `release_at_catalog_price` Action, and an
  Operator rerun of a failed submission keeps the choice.
- **What clears it (ISSUE-007).** The Hub lists the next step for each Hold Reason, and a Correction
  that would change nothing is refused.
