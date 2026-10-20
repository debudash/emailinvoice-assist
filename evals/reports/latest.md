# Eval report (2026-10-20T03:06:40+00:00)

**Gate: PASSED** · LangSmith experiment `gold-3cb2e154`

| Metric | Value | Gate |
|---|---|---|
| false_submits | 0.00 | = 0 |
| decision_accuracy | 1.00 | >= 0.9 |
| hold_reason_recall | 1.00 | >= 0.9 |
| context_accuracy | 1.00 | >= 0.95 |
| line_match_accuracy | 1.00 | >= 0.9 |

| Sample | Decision | Hold reasons | False submit | Context | Lines |
|---|---|---|---|---|---|
| simple | submit |  | 0 | 1 | 1.00 |
| mismatched-metadata | hold -> submit after correction | context_uncertain | 0 | 1 | 1.00 |
| large | hold | ambiguous, price_variance, unmatched | 0 | 1 | 1.00 |
| medium | hold | ambiguous, price_variance | 0 | 1 | 1.00 |
