# Test plan

## What makes a good test here

- **It checks behaviour through a module's interface**: inputs in, outputs and recorded state out
  (status, Stage Runs, Actions, what ClinRun received). It does not assert on prompts, private
  helpers or call order.
- **LLM-backed modules are tested deterministically** by swapping in fakes at the seams:
  `Pipeline` takes a `Stages` object, and `decide()` takes a `review` function. The fakes in
  [`tests/conftest.py`](../tests/conftest.py) use the simple sample's real values. How good the
  prompts are is measured by evals, not by unit tests.
- **Every core path and every exception path has a test.** There is no coverage percentage target.
- **Every False Submit path found in review gets a test** that fails without the fix (for example,
  a line the matcher leaves out, or a rerun pushing a Held Invoice into submission).
- **Bug fixes go test first**, with the issue ID in the test's docstring and a "found by" line
  (ISSUE-001, ISSUE-002).

## Levels

### Interface and integration (app, `tests/`, 61 tests)

Run with `python -m pytest` from the repository root (the `.venv` from `uv sync`). No stack and no
API key are needed: the Store is in-memory SQLite or a temp file, and the ClinRun Client test starts
its own mock-clinrun.

| File | Tests | Covers |
|---|---|---|
| `test_decision.py` | 14 | Every hard check through `decide()`: clean submit with the LLM rationale; Price Variance above and below the Catalog price; $0.00 Catalog price billed, and $0.00 billed at $0.00; Ambiguous even when price picked the match; low confidence holds; line arithmetic; lines vs printed total; half-up rounding; tolerance; `llm_concern` added to a clean Invoice; **the LLM cannot clear a hard-check Hold**; a line the matcher left out is Unmatched |
| `test_pipeline.py` | 6 | Pipeline with the real Store and fake Stages: all five Stages then Submitted, with the submission's Context, codes and as-billed text; uncertain Context skips matching and holds; Unmatched never submits; a Stage failure marks Failed at that Stage; a rerun adds Stage Runs without overwriting; a Message with no PDF is Rejected |
| `test_review_actions.py` | 15 | Review Actions: Correct Context reruns matching and the AI decides; a Correction to an unlinked site still holds; Release submits with reason and Reviewer; Release needs a reason; Release refused for `context_uncertain`; Escalation needs a note; Correct a Line Match; a Submitted Invoice cannot be corrected; Operator rerun from the failed Stage; rerun cannot push a Held Invoice into submission; only Held can be Escalated; a Correction without a note writes nothing; a Corrected Invoice is not Straight-Through; a Release survives a failed-submission rerun; a line the matcher left out can be corrected |
| `test_review_fixes.py` | 8 | S0 review findings: skipped matching never reports Matched; a missing printed total holds; a study from another sponsor holds; Stage Runs record their inputs; computed Context Confidence through `score_context` (a weak site name stays uncertain despite PI and link; an unproposed field scores 0; a study found by both protocol and name scores without error); a Failed Stage Run records the underlying error, not the ExceptionGroup |
| `test_reliability_and_intake.py` | 6 | Retries with attempts recorded; retries exhausted is Failed with 3 attempts; an image attachment is an Invoice; an upload is recorded as `upload`; an image Invoice holds as `extraction_unverifiable`; metrics (Straight-Through rate, manual minutes) |
| `test_eval_scoring.py` | 6 | The eval scoring and gate as pure functions: extra Hold Reasons keep full recall; a False Submit; Context correctness; line accuracy; the gate fails on one False Submit despite high accuracy; the gate passes when every floor is met |
| `test_hub.py` | 2 | **Component** level, through Streamlit's `AppTest`: a Submitted Invoice shows its ClinRun ID and History; a Held Invoice shows the actions and the Release lock for `context_uncertain` |
| `test_clinrun_client.py` | 2 | **Integration**: the ClinRun Client against a private mock-clinrun on a free port with a temp database; the same key returns the original ClinRun ID and stores one row; a new Invoice Version gets a new key |
| `test_issue_002_mcp_result_parsing.py` | 2 | ISSUE-002 regression: an mcp 2.x list result returns every row; a dict result is returned whole |

### Service suites

| Suite | Tests | Covers | How to run |
|---|---|---|---|
| `services/ref-mcp/tests/test_scoring.py` | 13 | Name, person and protocol normalisation and scores; the wrong-year protocol scores high but not 1.0; the wrong site name stays weak; PI reorders but does not change the name score | In `services/ref-mcp`, a venv with `requirements.txt` plus `pytest` and `pytest-asyncio`, then `python -m pytest` |
| `services/ref-mcp/tests/test_tools_live.py` | 11 | **Integration** against the reference API in Compose: sponsor, study and site search on the sample headers; study-site links; the LUMIN Catalog is complete (100 items); paging follows every page; list tools return everything | Same; marked `live`, skipped when the API at `REFERENCE_API_URL` (default `http://localhost:8000`) is down |
| `services/ref-mcp/tests/test_mcp_e2e.py` | 2 | Starts the server and calls it with the mcp client over streamable HTTP: tool list and full Catalog; list results are structured | Same; `live` |
| `services/mock-clinrun/tests/test_submissions.py` | 7 | The contract: health, 201 with a ClinRun ID, repeated key returns the original ID and stores once, list and get, missing key 400, bad body 422, unknown ID 404 | In `services/mock-clinrun`, a venv with `requirements-test.txt`, then `python -m pytest` |
| `services/api/tests/test_issue_001_postgres_driver.py` | 1 | ISSUE-001 regression (standard-library `unittest`) | `docker compose run --rm --no-deps --entrypoint python api -m unittest discover -s tests` |

### AI eval (gold set and gate)

The gold set is the four sample invoices, hand-labelled in [`evals/gold/`](../evals/gold/README.md):
the true Context, whether the Context should be confident, the acceptable Catalog Item codes per
line (`null` for Unmatched), and the expected Decision and Hold Reasons. The labels were derived by
an AI agent from the invoice generator script and the seed data (`evals/make_gold.py`); a human reviewer,
standing in for the subject matter expert, agreed them on 2026-10-20 (`evals/gold/review/`).

`python -m evals.run_eval` runs each sample through the real Pipeline (real Claude, real ref-mcp)
on a temporary Store with a fake ClinRun, so nothing is submitted. The mismatched-metadata sample is
then corrected to its gold Context, as a Reviewer would, so its Line Matches are scored too. Results
go to a LangSmith experiment and to `evals/reports/latest.{md,json}`.

**Gate** ([ADR-0012](adr/0012-eval-gate-zero-false-submits.md), `evals/scoring.py`):

| Metric | Gate | Latest committed report (experiment `gold-3cb2e154`, 2026-10-20) |
|---|---|---|
| False Submits | = 0 | 0 |
| Decision accuracy | ≥ 0.90 | 1.00 |
| Hold Reason recall | ≥ 0.90 | 1.00 |
| Context accuracy (IDs and confident flag) | ≥ 0.95 | 1.00 |
| Line Match accuracy | ≥ 0.90 | 1.00 |

| Sample | Decision | Hold Reasons |
|---|---|---|
| simple | submit | none |
| medium | hold | ambiguous, price_variance |
| large | hold | ambiguous, price_variance, unmatched |
| mismatched-metadata | hold, then submit after Correction | context_uncertain |

Hold Reason recall counts only the expected reasons, so extra reasons do not lower it. The medium
sample's gold reasons are `price_variance` only; the extra `ambiguous` (Week 4 / Week 8 Follow-up
vs generic VISIT-FU) appears in some runs and not others, which is run-to-run variation the
four-sample set cannot measure well. Exit codes: 0 pass, 1 gate failed, 2 `LANGSMITH_API_KEY` not
set.

### Smoke (whole stack, by hand)

With the stack up, copy `samples/emails/*.eml` into `inbox/` and check the outcomes in the Hub:

| Sample | Expected |
|---|---|
| simple | Submitted |
| medium | Held for `price_variance`; Release with a reason → Submitted |
| large | Held for `unmatched`, `ambiguous`, `price_variance`; Release or Escalate |
| mismatched-metadata | Held for `context_uncertain`, matching skipped; Correct Context → Submitted |

Outage check: `docker compose stop ref-mcp`, drop an email, expect Failed at context after 3
attempts; `docker compose start ref-mcp`, **Rerun from context** → Submitted. The S3+S4 commit
records this check, and all four sample outcomes, as verified live. The smoke run is not automated.

## Scenario tests (generated invoices)

`scripts/make_test_invoices.py` builds 12 scenarios from the seed reference data (PDF, a PNG for the
image case, `.eml`, and a `gold.json` label in the eval's format). `scripts/run_scenarios.py` runs
them through the real pipeline in process (fake ClinRun) and prints PASS/FAIL: the Decision must
match and every expected Hold Reason must be present. Together they cover the Hold Reasons the four
samples miss: `arithmetic` (wrong total, bad line amount), `site_not_linked`, `extraction_unverifiable`
(image), plus a $0.00 item billed, reworded lines, a second sponsor and a Rejected Message. First run:
12/12 passed. `--via-inbox` sends them through the running worker instead, for watching in the Hub.

## Extraction verification and the rationale judge

- **Extracted numbers are checked against the PDF's text layer** (`verify.py`, ADR-0007): every unit
  price, line amount, the total and the invoice number must be printed on the document, or the
  Invoice holds as `extraction_unverified` (not Releasable). Tested in `tests/test_verify.py` against
  the real sample PDFs.
- **Rationale faithfulness** is graded by an LLM judge (`evals/judge.py`): states the outcome, cites
  every Hold Reason, no claim the evidence does not support. The judge sees the same evidence the
  rationale was written from. Reported per sample and on average; not part of the gate.

## Known gaps

- **Generated scenarios are not in the gated eval yet (P2).** They run through `run_scenarios.py`
  with PASS/FAIL, but not as a LangSmith experiment, and no scenario measures run-to-run variation.
- **No gold example for `llm_concern`.** The review's concerns are judgement calls; a scenario that
  reliably provokes one has not been designed.
- **No automated smoke test** of the Compose stack, and no CI.
- **The Hub's component tests cover two views.** The Correction, Release and Escalation forms are
  covered at the Review Actions level, not by clicking through the Hub.
- **The worker loop** (`poll_once`, the pause and check-now flags) has no direct test.
- **Gold labels** are AI-derived and human-reviewed once (2026-10-20); the subject matter expert re-reviews them in the Hub (**Gold review**), and the eval is rerun by hand afterwards (not in CI yet).

## Judge calibration (2026-10-20)

- **Why the judge needed fixing:** its first run scored every sample 0.67. It had been given the
  Decision's findings but not the evidence, so it flagged true arithmetic as unsupported. Its
  evidence for the mismatched sample was also captured after the Correction, not when the
  rationale was written.
- **What changed:** the judge now receives the same evidence the rationale was written from, and
  treats the plausibility assessments the review was asked to make as judgement, not fact.
- **Result:** every sample scored 1.00 (`gold-c6290478`).
- **Check that it isn't lenient:** a planted bad rationale for the large invoice scored 0.33. It
  contained a wrong total ($31,500 vs $29,191), an invented "verified by phone" check, and was
  missing the unmatched and ambiguous reasons. The judge caught all three.
