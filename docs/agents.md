# Agents used to build this

This document is about the AI agents that **built** the project, not the product's own agent (the
context-resolution agent is described in [architecture.md](architecture.md)). The tool-call counts
below come from [`ai_log/actions.jsonl`](ai_log/actions.jsonl) as committed at the end of S5; the
phase summaries are in [ai_log.md](ai_log.md).

## Roles

| Agent | Kind | Job | Calls logged |
|---|---|---|---|
| Main agent | Claude Code, `claude-opus-5-5` | Design interviews and documents; the core package, Hub, Compose and sample emails; integrating each subagent's output; live runs; fixes; commits, merges and tags | 149 |
| Starter reader | Explore-style subagent, read-only | Read the starter repo's data model, seed data and invoice generator in Phase 0 | not logged (before the hook existed) |
| mock-clinrun builder | general-purpose subagent | Built `services/mock-clinrun` from the PRD's ClinRun contract: 7 tests, image builds, no deviations | 31 and 9 for the two builders, which ran in parallel |
| ref-mcp builder | general-purpose subagent | Built `services/ref-mcp`: 26 tests, image builds, four deviations (all accepted, see below) | (above) |
| S0 reviewers | two general-purpose subagents, run by the `/code-review` skill | One reviewed against the repo's standards, one against the spec, in parallel | 6 and 5 |
| Gold-label writer | general-purpose subagent | Derived `evals/gold/*.json` from the invoice generator and seed data (`evals/make_gold.py`) | 7 |
| S1+S2 reviewer | general-purpose subagent | Reviewed both axes (standards and spec) in one agent | 7 |
| S3+S4 reviewer | general-purpose subagent | Reviewed both axes in one agent | 5 |
| Docs writer | general-purpose subagent | Wrote this documentation set from the repo | after S5, not in the counts |

The ref-mcp builder's four deviations from its contract, each accepted by the main agent:
- PI Corroboration ranks sites without raising their score (this became the shape of ADR-0005 in
  code).
- `mcp` is pinned below 2 on the server, because FastMCP was removed in mcp 2.x.
- Catalog prices stay decimal strings.
- The `/api/v1` prefix is handled whether or not `REFERENCE_API_URL` includes it.

## Hand-off pattern

Each building subagent got:

- **An exact contract**, taken from the PRD's Contracts and Modules sections: for mock-clinrun, the
  ClinRun submission shape and the idempotency rule; for ref-mcp, the search and Catalog tools, what
  they return (ranked candidates with scores and Corroboration fields; the complete Catalog) and
  the paging requirement.
- **Its own directory.** It worked only inside `services/mock-clinrun/` or `services/ref-mcp/`, with
  its own test venv (`.venv-test`, git-ignored), so the two could run in parallel without touching
  each other or the app.
- **No commits.** The subagent reported back (tests, build result, any deviations); the main agent
  reviewed the work, decided on the deviations and committed it.

Reviewer subagents looked at the changes since the slice's starting point along the two axes of
the `/code-review` skill: Standards (does the code follow the documented coding standards?) and
Spec (does it do what the PRD and ADRs ask?). They reported findings only; the main agent fixed
them or recorded them as deferred in [decisions.md](decisions.md).

## Per-slice loop

The P0 build was cut into slices (decision D2): S0 tracer bullet, S1 hard checks, S2 large catalog,
S3 uncertain Context and Correction, S4 QC and reliability, S5 eval gate. S1+S2 and S3+S4 were built
and reviewed together. Each followed the same loop:

1. **Branch** from `main` (`slice/s0-tracer`, `slice/s1-s2-checks`, `slice/s3-s4-qc`,
   `slice/s5-evals`).
2. **Tests first** through the module interface, with fakes at the LLM and MCP seams.
3. **Build** until the tests pass.
4. **Live run** on the real model and the Compose stack with the slice's sample (for S0, the simple
   sample to `CR-000001`; for S3+S4, all four samples plus a ref-mcp outage).
5. **Review** along two axes, Standards and Spec (`/code-review` for S0; one reviewer agent per
   later slice pair).
6. **Fix** the correctness and spec findings, each with a test; record the rest as deferred with an
   owner.
7. **Merge** to `main`, then **tag** (`s0` after S0; `p0` after S1–S5).

Bug fixes inside a slice followed the developer's issue convention: a failing test carrying the
issue ID, the fix with a comment block at the fix site, a four-part commit message (Issue, Root
cause, Fix, Test), and an entry in [issue_log.md](issue_log.md). ISSUE-002 was fixed this way during
S0, in its own commit.

## The AI-log hook

[`.claude/hooks/ai_log.py`](../.claude/hooks/ai_log.py) is a Claude Code `PostToolUse` hook,
registered in [`.claude/settings.json`](../.claude/settings.json) for the `Bash`, `PowerShell`,
`Edit`, `Write`, `Agent`, `Skill` and `Artifact` tools. For each call it appends one JSON line with:
the time, the session (first 8 characters), the agent (`main` or the subagent's ID), the tool, a
short input summary, and whether the call succeeded.

The summary keeps only `file_path`, `description`, `pattern`, `skill`, `url` and `subagent_type`,
each cut to 200 characters. It never records file contents, full commands or tool output, so
secrets do not land in the log. Read, Grep and Glob calls are not matched, so reading is not
counted. The hook writes LF line endings on Windows (commit `2e8838b`) and is wrapped in
`|| true` so a logging failure never blocks the agent.
