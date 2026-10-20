# AI log

Two layers:
- [`ai_log/actions.jsonl`](ai_log/actions.jsonl): one line per AI agent tool call, appended automatically by a Claude Code
  hook (`.claude/hooks/ai_log.py`). Each line records the time, session, agent, tool, a short input summary
  (file path or command description, never file contents or full commands) and whether the call succeeded.
- This file: a human-readable summary at the end of each phase or slice. It is written by the agent and
  reviewed by the developer.

`ai_usage.md` is distilled from both at the end.

## Summaries

### Phase 0: discovery and design (2026-10-19)
- **Agents:** Claude Code (Opus 5.5) as the main agent, plus one Explore-style subagent that read the
  starter repo's data model, seed data and invoice generator, read-only.
- **What AI did:**
  - Reconciled the brief with the starter README, and ran grilling, domain-modeling and `/write-prd`
    interviews.
  - Drafted the glossary, `decisions.md`, ADRs 0001–0012 and `prd.md`.
  - Imported the starter.
  - Found ISSUE-001 (SQLAlchemy 2.1 breaking the reference API) and fixed it test-first.
- **What the developer decided:** every design decision was put to the developer as a question with a
  recommendation. The developer overrode the recommendation on these:
  - a configurable gate, later dropped
  - always stopping on uncertain Context
  - LangSmith first
  - building the synthetic gold set now, later moved to P2
  - taking $0.00 catalog prices literally
  - two actors
  - keeping the agent loop in P0
  - Opus for every LLM call
- **Human checks:** the developer reviewed each document as it was written, and approved the module
  sketch and the P0/P1/P2 split.

### S0: tracer bullet (2026-10-19)
- **Agents:**
  - The main agent built the core package, the Hub, Compose and the sample emails.
  - Two general-purpose subagents ran in parallel. Each had an exact contract, was limited to its own
    service directory, and was told not to commit.
  - One built `services/mock-clinrun`: 7 tests, image builds, no contract deviations.
  - One built `services/ref-mcp`: 26 tests, image builds. It made four deviations, all accepted:
    - PI corroboration ranks sites without raising their score (ADR-0005).
    - mcp is pinned below 2 on the server, because FastMCP was removed in mcp 2.x.
    - Catalog prices stay decimal strings.
    - The `/api/v1` prefix is handled whether or not the URL includes it.
- **AI found and fixed:**
  - LangChain's structured output forces a tool call, which Opus 5.5 rejects, so the app moved to
    the Anthropic SDK (ADR-0008 amendment).
  - ISSUE-002, test-first, in its own commit.
  - The Hub test timed out because of the auto-refreshing fragment; the refresh interval is now
    configurable.
- **Verified live, on the real model:**
  - The simple sample reached Submitted as `CR-000001`.
  - A rerun from the failed Stage kept the failed Stage Run.
  - Re-sending the same email reused `CR-000001`, and ClinRun held 1 row.
- **Developer decisions this slice:** keys provided in `.env`, and uv installed inside the project venv.
- **`/code-review` (two parallel reviewer agents):**
  - **Findings:** Standards found 5 documented violations and about 12 smells. Spec found 13 findings.
  - **Fixed:** the correctness and spec items, before merging.
  - **Deferred:** the rest, each with its owning slice, in decisions.md.
  - **Regression during the fixes:** one, a tie in study scoring, caught by the live run.
    I added a test first and fixed it before committing.
  - **Test isolation:** the first ClinRun Client test wrote into the demo's ClinRun data. It now
    starts its own private mock.
- **Developer decision:** keep refusal fallbacks on and record the serving model on each Stage Run.
