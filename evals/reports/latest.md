# Eval report (2026-10-20T14:13:59+00:00)

**Gate: PASSED** · LangSmith experiment `gold-c6290478`

| Metric | Value | Gate |
|---|---|---|
| false_submits | 0.00 | = 0 |
| decision_accuracy | 1.00 | >= 0.9 |
| hold_reason_recall | 1.00 | >= 0.9 |
| context_accuracy | 1.00 | >= 0.95 |
| line_match_accuracy | 1.00 | >= 0.9 |
| rationale_faithfulness (LLM judge) | 1.00 | reported only |

| Sample | Decision | Hold reasons | False submit | Context | Lines | Rationale |
|---|---|---|---|---|---|---|
| simple | submit |  | 0 | 1 | 1.00 | 1.0 |
| mismatched-metadata | hold -> submit after correction | context_uncertain | 0 | 1 | 1.00 | 1.0 |
| large | hold | ambiguous, price_variance, unmatched | 0 | 1 | 1.00 | 1.0 |
| medium | hold | price_variance | 0 | 1 | 1.00 | 1.0 |
