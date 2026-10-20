# AI usage

How AI was used to design, build, verify and review this project, and where the developer made the
call. Sources: [ai_log.md](ai_log.md) (phase summaries), [ai_log/actions.jsonl](ai_log/actions.jsonl)
(one line per agent tool call), [decisions.md](decisions.md), [issue_log.md](issue_log.md) and the
git history. How the agents were organised is in [agents.md](agents.md).

The tooling was Claude Code with `claude-opus-5-5` as the main agent, plus subagents. The
developer's standing rules (`~/.claude/CLAUDE.md`) shaped the work: a default demo stack and
philosophy (tight, explainable, local-first, happy path first with one friendly error boundary), a
bug-fix convention (test first, an issue ID at the fix site and in the test, a four-part commit
message, an issue-log entry), and no AI attribution trailers on commits unless asked.

## By numbers

From `actions.jsonl` as committed at the end of S5 (219 calls, 2026-10-20 00:41 to 03:10 UTC, one
session). The hook was added during Phase 0 and does not log Read, Grep or Glob, so design-phase
interviews and all file reading are not counted.

| Tool | Main agent | Subagents | Total |
|---|---|---|---|
| Bash | 84 | 58 | 142 |
| Write | 36 | 11 | 47 |
| Edit | 19 | 1 | 20 |
| Agent (subagent launches) | 7 | 0 | 7 |
| Skill | 3 | 0 | 3 |
| **Total** | **149** | **70** | **219** |

Seven subagents made the 70 subagent calls (31, 9, 7, 7, 6, 5 and 5). The three skills invoked
during the build were `claude-api`, `developing-with-streamlit` and `code-review`. No logged call
returned an error flag.

## Design

- **Reconciling the sources.** The AI compared the brief with the starter README and listed every
  conflict (human gate, intake, reference access, uncertain Context, the submit decision, ClinRun,
  correcting a submitted Invoice, deliverables, runtime). Each was put to the developer as a
  question with a recommendation; the outcomes are the table in [decisions.md](decisions.md).
- **Grilling and domain modelling.** A grilling interview stress-tested the plan; a
  domain-modelling pass produced [GLOSSARY.md](../GLOSSARY.md) and the first ADRs.
- **PRD interview.** `/write-prd` produced [prd.md](prd.md) with P0/P1/P2 tiers and a module
  sketch, which the developer approved.
- **ADRs.** ADRs 0001–0012 record the choices a reader would otherwise question, each with the
  options rejected.

## Build

- **Slices.** P0 was built as a tracer bullet (S0: the simple sample from email to ClinRun through
  every component) and then vertical slices S1–S5, each on its own branch, merged and tagged (`s0`,
  `p0`).
- **Subagents.** Two built the separate services in parallel (mock-clinrun, ref-mcp), each with an
  exact contract, confined to its own directory, and not allowed to commit. One derived the gold
  labels. The main agent built the app package, Hub, Compose and sample emails.
- **Changing course on evidence.** In S0 the AI found that LangChain's structured output forces a
  tool call, which `claude-opus-5-5` rejects (as it does `temperature`). It moved the app to the
  Anthropic SDK and recorded the change as an amendment to ADR-0008.

## Verification

- **Tests.** 61 app tests (pytest), plus 26 in ref-mcp, 7 in mock-clinrun and 1 in the reference
  API. LLM-backed Stages are tested with fakes at the seams; see [test_plan.md](test_plan.md).
- **Live runs on the real model**, recorded in commit messages and ai_log.md:
  - S0: simple sample → Submitted as `CR-000001`. A rerun from the failed Stage kept the failed
    Stage Run. Re-sending the same email reused `CR-000001`, and ClinRun held one row.
  - S1+S2: medium → Hold `price_variance`; large → Hold `ambiguous`, `price_variance`, `unmatched`,
    with 27 of 27 lines on the gold Catalog code.
  - S3+S4: all four samples (medium Released, large Escalated, mismatched Corrected → Submitted)
    and a ref-mcp outage (3 attempts → Failed → Operator rerun → Submitted).
- **Evals.** `python -m evals.run_eval` as a LangSmith experiment. The committed report
  (`gold-3cb2e154`) passed the gate with zero False Submits and every metric at 1.00.

## Review

Every slice was reviewed by AI agents along two axes, Standards and Spec, before merging.

| Slice | Findings | Fixed before merge (examples) |
|---|---|---|
| S0 (`/code-review`, two parallel agents) | Standards: 5 documented violations and about 12 smells. Spec: 13 findings | A missing printed total was being invented from the lines; it now holds (`arithmetic`). The "Matched" status was shown when matching was skipped. A study-belongs-to-sponsor check was added. Stage Runs now record their inputs and the serving model. One threshold per field. The agent was restricted to the search tools. Glossary names in Intake. |
| S1+S2 | Spec and standards | **False Submit path:** the checks iterated the matcher's answer, so a line the matcher left out was never checked. They now iterate the Line Items, and a missing line is Unmatched. Low-confidence matches hold. Money moved to `Decimal` with half-up rounding. The review prompt now states the outcome, uses only the data given, and treats a Reviewer's Context Correction as confirmed (it had caused a needless Over-Hold). |
| S3+S4 | Spec and standards | **False Submit path:** an Operator rerun could push a Held Invoice into submission. It is now allowed only for a Failed Invoice, from its failed Stage or earlier, and never past a Hold. Escalation only from Held. Guards run before any write. A Release survives a failed-submission rerun. Corrected Invoices are not Straight-Through. |

Two problems found while building, each fixed under the issue convention:
- **ISSUE-001:** the reference API crashed on first start because SQLAlchemy 2.1 maps
  `postgresql://` to psycopg 3. The fix pinned `sqlalchemy<2.1`.
- **ISSUE-002:** the context Stage crashed because the mcp 2.x client renamed `structuredContent`
  to `structured_content`. The fix reads the new field.

Two more came from live runs and test runs:
- **A regression during the S0 fixes:** a tie in study scoring. It was caught by the live run, and
  a test was written first.
- **Test isolation:** the ClinRun Client test wrote into the demo's ClinRun data. It now starts a
  private mock.

Findings not fixed were recorded with an owner or as "not planned" in decisions.md.

## Where the developer decided

The AI recommended; the developer decided. These are the places where the developer overrode the
recommendation or made a call the AI left open:

| Decision | Outcome |
|---|---|
| Human gate | First a configurable gate, then dropped in the design review: it would pause on the same trigger as the uncertain-Context Hold ([ADR-0001](adr/0001-no-human-gate-hold-on-uncertain-context.md)) |
| Uncertain Context | Always stop before matching and hold |
| Eval platform | LangSmith first |
| Gold set | Build the synthetic set now; later moved to P2 |
| $0.00 Catalog prices | Taken literally: any billed amount is a Price Variance |
| Actors | Two: Reviewer and Operator |
| Agent loop | Kept in P0 (context resolution) |
| Model | `claude-opus-5-5` for every LLM call, not the default stack's Sonnet |
| Secrets and tooling | Keys in a git-ignored `.env`; uv inside the project venv |
| Refusal fallbacks | Kept on, with the serving model recorded on each Stage Run |
| Git workflow, slices, ADR format, time-saved baseline | D1–D5 in decisions.md |

The developer also reviewed each design document as it was written, and approved the module sketch
and the P0/P1/P2 split.

## Limitations and what to double-check

- **Gold labels are AI-derived.** A human reviewer (standing in for the subject matter expert) agreed every label on 2026-10-20
  (`evals/gold/review/`); the `notes` field records the judgement calls (for example "Lab Supplies" → PASS-KIT).
  A wrong label would make the gate pass for the wrong reason.
- **Four samples are a thin gate.** The medium sample adds an `ambiguous` reason on some runs and
  not others. Rerun the eval just before presenting and check `evals/reports/latest.md`.
- **Thresholds were set on the same four samples.** The mismatched site scores 0.78 against a 0.85
  floor; a new site name could fall either side.
- **The AI log is partial.** Phase 0 interviews predate the hook, file reads are not logged, and
  [ai_log.md](ai_log.md) has summaries only for Phase 0 and S0. The S1–S5 account here comes from
  commit messages and decisions.md.
- **Docs written by an agent.** This documentation set was drafted by a subagent from the code.
  Check the sample outcomes, the quoted prompts and the counts against a fresh run.
- **Stale statements in older documents**, listed so they are not repeated in a presentation: the
  design-review table in decisions.md still says the context agent is a LangChain agent (superseded
  by the ADR-0008 amendment) and that numbers are cross-checked with pdfplumber (P2, not built);
  the comment in `services/ref-mcp/requirements.txt` still cites `langchain-mcp-adapters`.
