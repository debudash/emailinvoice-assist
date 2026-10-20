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
