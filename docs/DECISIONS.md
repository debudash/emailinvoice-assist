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
  `GET /submissions` and `POST /submissions/{id}/amendments`. The idempotency key is the invoice hash,
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
  `README.md` · `docs/ARCHITECTURE.md` · `docs/DECISIONS.md` · `docs/AI_USAGE.md` ·
  `docs/ISSUE_LOG.md` · demo video.

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
| Extraction | The PDF goes natively to Claude with a structured schema. Extracted numbers are cross-checked against local pdfplumber text; a number that isn't found is a Hold Reason. |
| $0.00 catalog prices | Taken literally: any billed amount is a Price Variance (Releasable). |
| Price as tie-break | Price is evidence for the matcher, but the line is still marked Ambiguous and the alternative is recorded. |
| Release | Allowed with a required reason for Price Variance, Unmatched, Ambiguous and LLM concern. Not allowed for uncertain Context, Possible Duplicate or unverified extraction. |
| Escalation | A status with a required note and its own queue. Reviewer identity comes from an "acting as" picker. |
| Stage failure | Two retries with backoff, then Failed at that stage (distinct from a Hold), with a "Rerun from stage" button. |
| Rerun after Correction | Decides autonomously; a clean rerun submits. |
| Lifecycle | Received → Extracted → Context Resolved → Matched → Submitted or Held. Held can be Corrected, Released or Escalated. A Submitted invoice can be Corrected into an Amendment. Any stage can end in Failed. |
| Agent placement | Fixed Python stages. The only agent loop is context resolution, a LangChain tool-calling agent over ref-mcp. Other LLM work is single structured calls. |
| Learning from Corrections | None (audited only). Site alias memory is a documented next step. |
| Hub | Streamlit, built for responsiveness: cached reads, `st.fragment`, and the pipeline in a separate worker. |
| Time saved | Metrics strip: Straight-Through rate, stage timings, and estimated manual time vs actual (assumptions shown). |
| Gold set | Synthetic now: the 4 originals hand-labelled plus about 20 scenario-built invoices whose labels are true by construction, also emitted as `.eml` files. Rewordings come from a curated, frozen variant table. |
| Eval gate | False Submits = 0 (hard). Decision accuracy ≥ 90%, Hold Reason recall ≥ 90%, Context accuracy ≥ 95%, Line Match accuracy ≥ 90%. Straight-Through rate is reported only. |
| Eval platform | LangSmith first (datasets plus experiments). LLM-as-judge grades rationale faithfulness only, reported and not gated. |

## Expected outcome per sample (seed of the eval set)

| Sample | Expected | Driven by |
|--------|----------|-----------|
| simple | Submit | Clean matches with light wording variation |
| medium | Hold | IRB price $550 vs catalog $500 (#5a) |
| large | Hold | 3 unmatched items, CT price mismatch, ambiguous matches (#5) |
| mismatched-metadata | Hold, not matched | Context below threshold (#4) |
