# Runbook

Operating the local stack. Service names and ports are in the [README](../README.md); the deployment
layout is in [deploy.md](deploy.md).

## Start, stop, status

| Task | Command |
|---|---|
| Start (and rebuild after code changes) | `docker compose up -d --build` |
| Status | `docker compose ps` (six services; `db` shows `healthy`) |
| Follow the worker | `docker compose logs -f worker` |
| Stop, keeping data | `docker compose stop` (or `docker compose down`, which keeps volumes) |
| Restart one service | `docker compose restart ref-mcp` |
| Health checks | `curl localhost:8000/health`, `curl localhost:8100/health`; the Hub at http://localhost:8501 |

## Reset demo data

| What | Command |
|---|---|
| Everything | `docker compose down -v` then `docker compose up -d` |
| Invoices and ClinRun only | `docker compose down`; `docker volume rm lr-emailassist_app_data lr-emailassist_clinrun_data`; `docker compose up -d` |
| Inbox | delete `inbox/processed/*.eml` |

ClinRun IDs restart at `CR-000001` only when `clinrun_data` is removed. If only `app_data` is
removed, re-sending a sample returns its old ClinRun ID, because the idempotency key is the same.

## Reseed the reference API

`docker compose restart api`. The entrypoint waits for Postgres, truncates the reference tables
(restarting IDs), seeds them from `services/api/seed/data/*.json`, then starts the API. IDs stay the
same, so stored Contexts remain valid. The Hub caches the reference lists for 10 minutes; restart
the Hub (`docker compose restart hub`) to pick up changed seed data at once.

## Rerun a Failed Invoice

1. Hub → **Failed** queue → select the Invoice. The banner names the failed Stage and the error.
2. Fix the cause (see faults below).
3. Press **Rerun from &lt;stage&gt;**. This calls `ReviewActions.rerun`, which records a `rerun`
   Action and runs the Pipeline from that Stage with trigger `operator rerun by <actor>`.

Rules enforced by Review Actions: only a Failed Invoice can be rerun; only from its failed Stage or
an earlier one; and a rerun into submission is refused when the Decision is Hold and nothing was
Released. A Released Invoice whose submission failed keeps its Release on the rerun. The rerun
runs in the Hub process, so the page waits until it finishes.

## Pause the poller

Sidebar → **Pause poller**. The worker keeps ticking every `POLL_SECONDS` but does not read the
inbox. **Check inbox now** asks for one poll on the next tick, paused or not. The sidebar shows the
last tick time. The flags live in the `control` table of the app store, so they survive restarts.

## Common faults

| Symptom | Cause | Fix |
|---|---|---|
| `api` exits on first start: `ModuleNotFoundError: No module named 'psycopg'` | ISSUE-001: SQLAlchemy 2.1 maps `postgresql://` to psycopg 3; only psycopg2 is installed | Already fixed by pinning `sqlalchemy>=2.0.36,<2.1` in `services/api/requirements.txt`. If it recurs, check that pin and rebuild: `docker compose build api` |
| Context Stage fails with `TypeError: string indices must be integers` | ISSUE-002: the mcp 2.x client names the field `structured_content`; code reading the 1.x name `structuredContent` gets one text block | Fixed in `context._tool_json`. If it recurs after a dependency upgrade, check the mcp client version and run `tests/test_issue_002_mcp_result_parsing.py` |
| `api` exits at once with `/bin/bash^M: bad interpreter` or `no such file or directory` for the entrypoint | `services/api/docker-entrypoint.sh` checked out with CRLF line endings (Windows `core.autocrlf`) | `.gitattributes` forces LF for `*.sh`. For an older checkout: `git add --renormalize .` or re-checkout the file, then `docker compose build api` |
| Invoices become Failed at `context` after about 5 seconds; error mentions a refused connection | ref-mcp (or the API behind it) is down. The Stage was tried 3 times (waits of 1 s and 4 s) | `docker compose ps`; `docker compose start ref-mcp` (or `api`); then **Rerun from context** |
| Failed at `submission` | mock-clinrun is down | `docker compose start mock-clinrun`; **Rerun from submission** (Released Invoices keep their Release) |
| Every Invoice Failed at `extraction`; error says the API key is missing or invalid | `ANTHROPIC_API_KEY` not set in `.env`, or `.env` missing (Compose treats it as optional) | Set the key in `.env`, `docker compose up -d --force-recreate worker hub`, then rerun from extraction |
| Failed with `LLMRefusal` | The model and its server-side fallback both declined | Read the Stage Run error and rerun once. If it repeats, the Invoice stays Failed: Escalation needs a Held Invoice, so look at the document itself |
| No traces in LangSmith | `LANGSMITH_API_KEY` is empty, so the client is not wrapped | Expected: the Pipeline runs normally without tracing. Set the key and run `docker compose up -d --force-recreate worker hub` to trace |
| `python -m evals.run_eval` exits with code 2 | `LANGSMITH_API_KEY` is not set; evals record results as LangSmith experiments | Set the key in `.env` or the shell. Exit code 1 means the gate failed: read `evals/reports/latest.md` |
| Hub shows an error opening a Held Invoice right after start | The Hub loads the reference lists through ref-mcp for the Correction picker, outside the action error boundary | Check `ref-mcp` and `api` are up, then reload the page |
| An email sits in `inbox/` and nothing happens | Poller paused, or the worker container stopped | Sidebar **Pause poller** off, or `docker compose ps` / `docker compose logs worker`; `docker compose up -d worker` |
| Worker container exited | An unexpected error in the poll loop (for example, an `.eml` that cannot be parsed) stops the process; there is no restart policy | `docker compose logs worker` for the traceback; move the bad file out of `inbox/`; `docker compose up -d worker` |
| The same invoice appears twice in the Hub | The email was delivered twice. Possible Duplicate detection is P2 | Both rows carry the same ClinRun ID; ClinRun holds one submission |

## Where logs and traces are

| What | Where |
|---|---|
| Worker log (each Invoice and its final status, rejections) | `docker compose logs worker` |
| Hub, ref-mcp, mock-clinrun, api logs | `docker compose logs <service>` |
| Stage Runs (inputs, outputs, attempts, errors, serving model, timings) | Hub → Invoice → **History**; or the `stage_runs` table in `/data/app.db` (volume `app_data`) |
| Reviewer and Operator Actions | Hub → Invoice → History (second table); `actions` table |
| What ClinRun received | `curl localhost:8100/submissions` |
| LLM calls (prompts, tokens, latency) | LangSmith project `LANGSMITH_PROJECT` (`lr-emailassist`), when a key is set |
| Eval results | `evals/reports/latest.md` and `.json`; the LangSmith experiment named in the report |

To open the container's store: `docker compose exec worker python -c "import sqlite3; ..."` or copy
it out with `docker compose cp worker:/data/app.db ./app-copy.db`.
