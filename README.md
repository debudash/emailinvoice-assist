# AI Email Invoice Ingestion and Matching Assistant

A take-home for Ledger Run. Clinical trial sites email their invoices; this system reads each
Invoice, resolves its Context (sponsor, study, site) through an MCP server over the provided
reference API, matches every Line Item against that sponsor and study's Catalog, and decides to
**Submit** the Invoice to ClinRun (a mock service here) or **Hold** it with written Hold Reasons.
No person approves an Invoice before the Decision. Safety comes from the decision design instead:
deterministic hard checks force a Hold, the LLM can add a Hold but never clear one, and an Invoice
whose Context is uncertain is held before matching runs.

Reviewers work after the fact in the Hub (Streamlit). They see what was extracted, what was matched,
the computed Context Confidence, the Hold Reasons and the rationale. From there they correct the
Context or a Line Match (the affected Stages rerun and the AI decides again), Release a
business-judgement Hold with a reason, or Escalate. Operators see each Invoice's Stage Run history,
the Failed queue, and can rerun a Failed Invoice or pause the inbox poller. Capitalised terms are
defined in [GLOSSARY.md](GLOSSARY.md).

## Quick start

Prerequisites: Docker with Compose, an `ANTHROPIC_API_KEY`, and optionally a `LANGSMITH_API_KEY`
(tracing at runtime; required for evals). Python 3.13 is needed only to regenerate sample emails or
to run tests and evals on the host.

```bash
cp .env.example .env            # then set ANTHROPIC_API_KEY (and LANGSMITH_API_KEY if you have one)
docker compose up -d --build    # db, api, ref-mcp, mock-clinrun, worker, hub
# open http://localhost:8501

python scripts/make_sample_emails.py   # optional: rewrites samples/emails/*.eml (already committed)
cp samples/emails/*.eml inbox/          # the worker picks them up within POLL_SECONDS
```

The worker moves each `.eml` it has read to `inbox/processed/`.

### Choosing the model

Every LLM call (extraction, the context agent, matching and the decision review) uses one model,
set by `LLM_MODEL` in `.env`. The default is `claude-opus-5-5`. If your key cannot use Opus, or you
want faster and cheaper runs, pick another model:

```bash
# .env
LLM_MODEL=claude-sonnet-5-5     # or claude-haiku-5-5
```

```bash
docker compose up -d            # recreates worker and hub with the new setting
```

Sonnet 5.5 and Haiku 5.5 both accept the same call settings as Opus. The eval results in
[`evals/reports/latest.md`](evals/reports/latest.md) were measured on Opus 5.5; Haiku 5.5 also passed the gate on 2026-10-20
([`evals/reports/2026-10-20-haiku-5-5.md`](evals/reports/2026-10-20-haiku-5-5.md)). Rerun
`python -m evals.run_eval` after switching to see how another model scores. Each Stage Run records
the model that served it, shown in the Hub's History tab.

### Services and ports

| Service | Port | What it is |
|---|---|---|
| `db` | 5433 → 5432 | Postgres 17 for the reference data (user, password and database `ctref`) |
| `api` | 8000 | The starter's read-only reference API, unchanged apart from the ISSUE-001 pin. Docs at `/docs` |
| `ref-mcp` | 8200, path `/mcp` | MCP server (FastMCP, streamable HTTP) wrapping the reference API: scored search tools and the full Catalog ([ADR-0003](docs/adr/0003-mcp-server-owns-reference-search.md)) |
| `mock-clinrun` | 8100 | Stand-in for ClinRun: `POST /submissions` (idempotent), `GET /submissions`, `GET /submissions/{id}` ([ADR-0011](docs/adr/0011-mock-clinrun-idempotent.md)) |
| `hub` | 8501 | The Reviewer's Hub (Streamlit) |
| `worker` | none | Polls `inbox/` and runs the Pipeline, one Invoice at a time, oldest first |

`worker` and `hub` are built from the same image and share the `app_data` volume (`/data/app.db`)
and the `./inbox` bind mount.

### Environment variables

App settings are read in [`src/invoice_assist/config.py`](src/invoice_assist/config.py); secrets come
from `.env` ([`.env.example`](.env.example)).

| Variable | Default | Used for |
|---|---|---|
| `ANTHROPIC_API_KEY` | none (required) | Every LLM call |
| `LANGSMITH_API_KEY` | none | When set, every LLM call is traced to LangSmith. Required by `evals.run_eval` |
| `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` | `true`, `lr-emailassist` in `.env.example` | Read by the LangSmith SDK |
| `LLM_MODEL` | `claude-opus-5-5` | Model for every call (extraction, context agent, matching, decision review) |
| `REF_MCP_URL` | `http://localhost:8200/mcp` (Compose: `http://ref-mcp:8200/mcp`) | ref-mcp endpoint |
| `CLINRUN_URL` | `http://localhost:8100` (Compose: `http://mock-clinrun:8100`) | ClinRun endpoint |
| `APP_DB` | `data/app.db` (Compose: `/data/app.db`) | The app's SQLite file |
| `INBOX_DIR` | `inbox` (Compose: `/inbox`) | Folder the worker polls |
| `POLL_SECONDS` | `3` | Worker poll interval |
| `HUB_REFRESH_SECONDS` | `3` | Hub auto-refresh of the queue and metrics; `0` turns it off |
| `THRESHOLD_SPONSOR`, `THRESHOLD_STUDY`, `THRESHOLD_SITE` | `0.85` each | Context Confidence floor per field |
| `PRICE_TOLERANCE` | `0` | Allowed price difference as a fraction of the Catalog price; `0` means exact to the cent |
| `MANUAL_MINUTES_PER_INVOICE`, `MANUAL_MINUTES_PER_LINE` | `5`, `1` | Manual baseline for the time-saved estimate (shown on screen as an assumption) |

Service-only variables: `REFERENCE_API_URL`, `MCP_HOST`, `MCP_PORT` (ref-mcp); `CLINRUN_DB`
(mock-clinrun); `DATABASE_URL` (api). Compose sets them.

## Exercising the full flow

Copy the four sample emails into `inbox/` and watch the **All** queue in the Hub. Expected outcomes
(from the PRD and the gold labels in [evals/gold/](evals/gold/)):

| Sample | First Decision | What to do in the Hub | Final status |
|---|---|---|---|
| `01-simple-invoice` (Contoso / CATALYST, Willow Creek) | Submit, Straight-Through | Open it: the ClinRun ID (`CR-…`) and the rationale are shown | Submitted |
| `02-medium-invoice` (Northwind / LUMIN-2024, Harborview) | Hold: `price_variance` (IRB/Ethics Fees $550 vs ADMIN-IRB $500). Some runs also add `ambiguous` for the Week 4 / Week 8 Follow-up lines | **Release** tab, enter a reason | Submitted, with the Release reason and Reviewer in the submission |
| `03-large-invoice` (Northwind / LUMIN-2024, Highland Ridge) | Hold: `unmatched` (Parking Reimbursement, Patient Stipend, Translator Services), `ambiguous` (Drug Shipping (cold chain) and others), `price_variance` (CT scan $475 vs $450) | Release with a reason, or **Escalate** with a note | Submitted or Escalated |
| `04-mismatched-metadata-invoice` (header says "Northwind Pharmaceuticals Inc.", protocol NWD-VER-2024-002, site "Prairie Clinical Research") | Hold: `context_uncertain`. Matching is skipped. The site scores 0.78 against Prairie Field Research Group, below 0.85 | **Correct context** tab: the Suggested Context (Northwind Pharma / VERITAS / Prairie Field Research Group) is preselected; add a note and apply | Matching and the Decision rerun; Submitted |

Release is refused for `context_uncertain`, `site_not_linked` and `arithmetic`: those need a
Correction. To see a Stage failure, stop ref-mcp (`docker compose stop ref-mcp`), drop an email in,
and watch it become Failed at the context Stage after three attempts; start ref-mcp again and press
**Rerun from context**. See [docs/runbook.md](docs/runbook.md).

## Tests and evals

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install uv && uv sync                            # app plus the dev group into .venv
python -m pytest                                     # app tests; no stack or API key needed
python -m evals.run_eval                             # needs the stack, ANTHROPIC_API_KEY, LANGSMITH_API_KEY
docker compose run --rm eval                         # the same eval in a container: no host Python needed
```

`evals.run_eval` runs the four gold samples through the real pipeline (with a fake ClinRun), writes
`evals/reports/latest.{md,json}` and exits 0 when the gate passes, 1 when it fails, 2 when
`LANGSMITH_API_KEY` is missing. It also reports rationale faithfulness from an LLM judge
(`evals/judge.py`); that metric is reported, not gated. The service test suites (ref-mcp,
mock-clinrun, reference API) are described in [docs/test_plan.md](docs/test_plan.md).

### Try it with your own invoices

```bash
python scripts/make_test_invoices.py --list          # 12 scenarios and what each should produce
python scripts/make_test_invoices.py                 # PDFs (+ a PNG) and .eml files in samples/generated/
python scripts/run_scenarios.py                      # run them all in process; PASS/FAIL per scenario
python scripts/run_scenarios.py price-variance       # or just some
python scripts/run_scenarios.py --via-inbox          # or drop them in inbox/ and watch them in the Hub
```

Scenarios are built from the seed reference data, so each expected outcome is true by construction:
clean invoices for two sponsors, reworded lines, price variance, a $0.00 item billed, an unmatched
charge, a wrong printed total, a bad line amount, a site not on the study, an unknown site, an image
invoice and an email with no attachment. Add a scenario by adding one entry to `SCENARIOS` in
`scripts/make_test_invoices.py`. You can also upload any PDF or image from the Hub's sidebar.

### Review the gold labels (the subject matter expert)

The gold labels are the answer key the eval scores the AI against. They belong to a subject matter
expert (accounts payable or clinical finance), not the developer, so the review is a page in the Hub:
open http://localhost:8501 and choose **Gold review** in the sidebar, acting as **Pat (SME)**.

- Pick an invoice; each shows its expected result and whether it has been reviewed.
- **Lines that need your judgement** come first, each with the reason in plain words (more than one
  plausible item, a price difference, nothing in the catalog, loose wording). The straightforward
  lines are in an expander.
- For each line: *Yes, that's right*, *No, it's a different item* (then pick the right one) or
  *Not sure*, with an optional comment. Check the expected result the same way.
- **Save review** records the review in `evals/gold/review/<sample>.json` and writes any changed
  answer straight into `evals/gold/<sample>.json`.

After a change, an engineer reruns the eval (`docker compose run --rm eval`) to score the AI against
the new answer key. **That step is manual today; it is not wired into CI.** In production, a change
to the answer key would be a pull request, and CI would run the eval gate on it before it merges
([docs/deploy.md](docs/deploy.md), CI/CD).

## Repository layout

```
.
├── docker-compose.yml          the whole system: db, api, ref-mcp, mock-clinrun, worker, hub
├── Dockerfile                  app image (worker and Hub), Python 3.13 + uv
├── pyproject.toml, uv.lock     app dependencies (Anthropic SDK, LangSmith, Streamlit, pydantic, httpx)
├── .env.example                secrets template
├── GLOSSARY.md                 domain terms used everywhere
├── src/invoice_assist/
│   ├── config.py               settings from the environment
│   ├── models.py               pydantic domain models, Hold Reasons, statuses, RELEASABLE
│   ├── intake.py               .eml → Message with Invoice files, or a Rejected Message; Hub uploads
│   ├── extraction.py           extraction Stage: the document goes to Claude natively
│   ├── context.py              context Stage: agent over ref-mcp, then computed Context Confidence; Catalog lookup
│   ├── matching.py             matching Stage: all Line Items against the whole Catalog in one call
│   ├── decision.py             decision Stage: hard checks plus the LLM review
│   ├── clinrun.py              ClinRun Client with the idempotency key
│   ├── pipeline.py             fixed Stages, retries, Failed, Stage Runs, status changes
│   ├── review.py               Review Actions: Correction, Release, Escalation, Operator rerun
│   ├── store.py                SQLite store (append-only Stage Runs and Actions)
│   ├── llm.py                  the LLM seam: structured calls, tool runner client, LangSmith wrap
│   ├── metrics.py              Straight-Through rate, Holds by reason, Stage timings, time saved
│   ├── worker.py               inbox poller
│   ├── app.py                  the Hub entry point: the Invoices and Gold review pages
│   ├── hub.py                  the Invoices page (Streamlit)
│   ├── gold_review.py          the Gold review page, for the subject matter expert
│   └── gold.py                 the answer key and its review: what needs judgement, saving changes
├── services/
│   ├── api/                    starter reference API and seed data (plus the ISSUE-001 test)
│   ├── ref-mcp/                MCP server: server.py (tools), scoring.py (rapidfuzz), refapi.py (paging)
│   └── mock-clinrun/           mock ClinRun (FastAPI + SQLite)
├── tests/                      app tests (pytest)
├── evals/                      gold labels, scoring and gate, eval runner, latest report
├── samples/emails/             the four sample invoices wrapped as .eml Messages
├── sample-invoices/            the starter's sample PDFs
├── scripts/                    make_sample_emails.py; the starter's generate_sample_invoices.py
├── inbox/                      (git-ignored) the polled folder; processed/ holds read files
├── .claude/                    the AI-log hook used while building (see docs/agents.md)
└── docs/                       PRD, decisions, ADRs, and the documents listed below
```

## Documentation

| Document | Contents |
|---|---|
| [docs/prd.md](docs/prd.md) | Product requirements with P0/P1/P2 tiers |
| [docs/decisions.md](docs/decisions.md), [docs/adr/](docs/adr/) | Brief vs starter conflicts, design and build decisions, ADRs 0001–0012 |
| [docs/users.md](docs/users.md) | Reviewer and Operator: goals, scenarios, limits |
| [docs/architecture.md](docs/architecture.md) | Services, modules, data model, lifecycle, sequence diagrams, decision logic |
| [docs/deploy.md](docs/deploy.md) | Local deployment and the AWS production design (not built) |
| [docs/test_plan.md](docs/test_plan.md) | Test levels, files, the gold set and the eval gate |
| [docs/runbook.md](docs/runbook.md) | Operating the stack and fixing common faults |
| [docs/agents.md](docs/agents.md) | How AI agents were used to build this |
| [docs/ai_usage.md](docs/ai_usage.md) | AI usage end to end, and where the developer decided |
| [docs/ai_log.md](docs/ai_log.md), [docs/issue_log.md](docs/issue_log.md) | Phase summaries; bug log |

## Write-up

The starter asks three questions. The answers below describe the code as it is.

### (a) How the extraction and matching prompts were designed

All four LLM calls use the Anthropic SDK with native structured outputs: a pydantic model is the
output schema, so the reply is validated before any Stage uses it. `claude-opus-5-5` rejects
`temperature` and forced tool calls, so neither is sent; depth is set with `effort`
([`llm.py`](src/invoice_assist/llm.py)). Server-side refusal fallbacks are on, and the model that
served each call is recorded on its Stage Run. Each prompt does one job, and anything that must be
exact is kept out of the LLM's hands and done in code.

**Extraction** ([`extraction.py`](src/invoice_assist/extraction.py), effort medium). The PDF or image
is sent as a native document or image block, not as locally extracted text, because local text
extraction loses table layout ([ADR-0007](docs/adr/0007-native-pdf-extraction-with-text-check.md)).
Key rules:

> Copy every header field and every line item as printed: do not correct spelling, normalise names,
> or fix arithmetic. Use null for a field that is not on the invoice.

Why: the later Stages need the raw text. Context Confidence measures how well the printed header
matches a record, so a model that "fixes" "Northwind Pharmaceuticals Inc." would hide the very
signal that decides whether to hold. The arithmetic check can only catch a site's mistake if the
model does not silently correct it. The media type is set by the Stage, not the model (it is
excluded from the schema).

**Context resolution** ([`context.py`](src/invoice_assist/context.py), effort medium, at most 12
iterations). This is the one agent loop. The agent gets only the four search tools
(`search_sponsors`, `search_studies`, `search_sites`, `list_study_sites`), so it has to search rather
than list everything. Key rules:

> Header text may be misspelled or slightly wrong (company suffixes, a wrong year in a protocol
> number, a site name that is close but not exact). Search for each of sponsor, study (by protocol
> number and by name) and site (by name and PI), check that the site is linked to the study, then
> propose the most consistent records. Use null for a field when no candidate is plausible. … Do not
> state how confident you are; that is computed separately.

Why: the agent proposes record IDs and explains; code computes the confidence that decides whether
matching runs ([ADR-0004](docs/adr/0004-context-confidence-is-computed.md)). Self-rated LLM
confidence cannot be unit-tested or tuned; the computed score can.

**Matching** ([`matching.py`](src/invoice_assist/matching.py), effort high). Every Line Item and the
whole scoped Catalog go in one call ([ADR-0006](docs/adr/0006-whole-catalog-in-one-matching-call.md)).
Key rules:

> Only use Catalog Items from the list given. Never invent an item.
> If no item bills the same service, set catalog_item_id and item_code to null (Unmatched).
> If more than one item is plausible, pick the best, set ambiguous=true and list the others in
> alternatives. Price may be used as evidence for the best pick, but a line that needed price to
> decide is still ambiguous.
> confidence: high = clearly the same service; medium = probable; low = a guess.
> Do not judge whether the price is correct; a separate check does that.

Why: the matcher's job is the service, not the money. The price check is deterministic in the
decision Stage, so a persuasive model cannot talk a Price Variance away. Price may break a tie (it
is real evidence for "Drug Shipping (cold chain)" vs two shipping items), but the line still shows
as Ambiguous so the close call stays visible. A `low` label is treated as Ambiguous by the checks.

**Decision review** ([`decision.py`](src/invoice_assist/decision.py), effort high). It runs on every
Invoice because it writes every rationale. It is told the outcome the hard checks already determine.
Key rules:

> Use only the data given; do not assume facts that are not in it. If the Context was corrected by a
> Reviewer, the Reviewer has already confirmed those records against the header: do not question
> them.
> concern: raise one only for a specific, material risk the hard checks did not cover … You cannot
> clear a finding.

Why: the review adds judgement the rules lack (an implausible quantity, a service billed twice), but
the outcome is computed in code: any finding means Hold, whatever the review says
([ADR-0002](docs/adr/0002-llm-can-add-holds-never-clear-them.md)). The "corrected by a Reviewer" rule
was added after testing showed the review re-raising a question the Reviewer had just answered,
which caused a needless Over-Hold.

### (b) How partial metadata failure is handled

The starter's example is "sponsor not found but study matched". Here every Context field is scored
separately, and any weak field stops the Invoice before matching.

1. **Computed per-field Context Confidence.** After the agent proposes a sponsor, study and site,
   `score_context` re-runs the ref-mcp searches with the printed header text and takes the proposed
   record's own similarity score: the sponsor name score; the better of the protocol-number and
   study-name scores (searched within the proposed sponsor); and the site's *name* score. A field
   is confident only when a record was proposed and its score is at least the field's threshold
   (0.85 by default). A field the agent left null, or a record that does not appear in the search
   results, scores 0.
2. **Corroboration ranks but cannot lift** ([ADR-0005](docs/adr/0005-corroboration-ranks-but-cannot-lift.md)).
   A matching PI reorders site candidates (ref-mcp's `rank_score`), and the study-site link and
   study-belongs-to-sponsor checks are reported, but none of them raises a field's confidence. On
   the mismatched sample the PI puts Prairie Field Research Group first, yet its name score stays
   0.78, so the site stays uncertain.
3. **Uncertain Context: skip matching and Hold.** If any field is uncertain, the matching Stage
   records `skipped` and the Decision holds with `context_uncertain`, one detail line per weak field
   (for example "Study 'NWD-…' resolved to 'None' with confidence 0.00, below threshold"). Nothing is
   priced against a Catalog that might be the wrong one. A study that belongs to a different sponsor
   is also `context_uncertain`; a site not linked to the study is `site_not_linked`.
4. **Suggested Context.** Whatever the agent proposed is kept and preselected in the Hub's
   Correction picker, with each field's header text, resolved record, confidence and the agent's
   lookups shown.
5. **Reviewer Correction over all records.** The picker lists every sponsor, study and site from the
   reference data (ref-mcp `list_*` tools), not only the suggestions, so a header the AI could not
   place at all can still be fixed. A note is required. The corrected Context recomputes the
   study-site link and sponsor ownership from the reference data, so a wrong Correction still holds.
6. **Rerun.** Matching and the Decision rerun as new Stage Runs, and the AI decides again; the
   review is told the Reviewer confirmed the Context. A clean rerun submits; a Corrected Invoice is
   never counted as Straight-Through.

**Sponsor found but study not** (or the reverse): the found field is confident, the other is not,
so the Invoice holds as `context_uncertain` with the found record already preselected. Matching
cannot run anyway, because the Catalog is selected by sponsor *and* study. When the sponsor is
missing, the study search is not scoped to a sponsor, and if the proposed study belongs to a
different sponsor than the one proposed, that is a further `context_uncertain` finding. Release is
refused for all of these: the only way forward is a Correction (or an Escalation).

One caveat: when the agent proposed no record for a field, the picker falls back to the first
record in the list rather than an empty choice, so the Reviewer must pick that field deliberately.

### (c) What to improve next

The one thing first: **a synthetic gold set** of scenario-built invoices whose labels are correct by
construction (PRD story 79, P2). The eval gate is the main safety net for prompt and model changes,
and four samples are too few to cover every Hold Reason and edge case; the medium sample already
shows run-to-run variation (an extra `ambiguous` reason on some runs).

The rest of the roadmap, from the PRD's P2 tier and the deferred tables in
[decisions.md](docs/decisions.md):

- Amendments for corrections to a submitted Invoice, with Reviewer approval ([ADR-0010](docs/adr/0010-amend-never-withdraw.md)); today a submitted Invoice cannot be corrected.
- Possible Duplicate holds (same file hash, or same invoice number and site). Today a re-sent email creates a second Invoice; the idempotency key stops a second ClinRun submission, but the Hub shows two rows.
- Checking every extracted number against the PDF's own text layer ([ADR-0007](docs/adr/0007-native-pdf-extraction-with-text-check.md)).
- Email Hints (sender domain, subject, body) as Context evidence, with a contradiction as a Hold Reason.
- An LLM judge for rationale faithfulness (reported, not gated).
- The AI's original Decision shown next to the post-Correction one (P1, not built).
- Metrics over a time window, without the per-Invoice queries.
- Roles enforced from identity rather than an "acting as" picker; site alias memory learned from Corrections; an embedding pre-filter once Catalogs reach the thousands; a real mailbox connector and a queue with scaled workers (see [docs/deploy.md](docs/deploy.md)).

## Deviations from the starter

| Starter says | This project | Why |
|---|---|---|
| The user confirms metadata before line-item matching (a hard gate) | No gate. An uncertain Context holds the Invoice before matching instead | The brief says humans are not a required gate; the gate's useful part (stop when unsure) is kept as a Hold ([ADR-0001](docs/adr/0001-no-human-gate-hold-on-uncertain-context.md)) |
| Call the reference REST API | The app talks only to ref-mcp, an MCP server in front of the unchanged REST API, which adds fuzzy search and full-Catalog paging | The brief requires the MCP-wrapped API; the REST API has no search, and its default page size of 50 cuts the 100-item LUMIN Catalog ([ADR-0003](docs/adr/0003-mcp-server-owns-reference-search.md)) |
| Upload a file | Invoices arrive as `.eml` files in a polled inbox folder; Hub upload writes the same kind of Message | The brief says "ingest invoices from email" |
| The user finalizes and submits | The AI submits clean Invoices to a mock ClinRun; Reviewers Release held ones | The brief asks for an AI submit/hold decision |
| The developer's default stack uses LangChain | The Anthropic SDK directly (structured outputs, tool runner with the MCP helper), traced with LangSmith's `wrap_anthropic` | `claude-opus-5-5` rejects the forced tool calls and `temperature` LangChain relies on ([ADR-0008](docs/adr/0008-fixed-stages-one-agent-loop.md) amendment) |
