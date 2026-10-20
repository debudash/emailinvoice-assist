"""Eval scoring against the gold labels, and the quality gate (ADR-0012). Pure functions."""

GATE = {"false_submits": 0, "decision_accuracy": 0.90, "hold_reason_recall": 0.90,
        "context_accuracy": 0.95, "line_match_accuracy": 0.90}


def score(prediction: dict, gold: dict) -> dict:
    """Per-invoice scores. `lines` maps line_no (as str) to the predicted item_code or None."""
    expected_hold = gold["expected_decision"] == "hold"
    held = prediction["decision"] == "hold"
    expected_reasons = set(gold["expected_hold_reasons"])
    recall = (len(expected_reasons & set(prediction["hold_reasons"])) / len(expected_reasons)
              if expected_reasons else 1.0)
    correct_lines = sum(1 for line in gold["lines"]
                        if str(line["line_no"]) in prediction["lines"]
                        and prediction["lines"][str(line["line_no"])] in line["acceptable_item_codes"])
    return {
        "false_submit": int(expected_hold and not held),
        "decision_correct": int(held == expected_hold),
        "hold_reason_recall": recall,
        "context_correct": int(prediction["context"] == gold["context"]
                               and prediction["context_confident"] == gold["context_should_be_confident"]),
        "line_accuracy": correct_lines / len(gold["lines"]) if gold["lines"] else 1.0,
    }


def gate(scores: list[dict]) -> tuple[bool, dict]:
    n = len(scores)
    summary = {
        "examples": n,
        "false_submits": sum(s["false_submit"] for s in scores),
        "decision_accuracy": sum(s["decision_correct"] for s in scores) / n,
        "hold_reason_recall": sum(s["hold_reason_recall"] for s in scores) / n,
        "context_accuracy": sum(s["context_correct"] for s in scores) / n,
        "line_match_accuracy": sum(s["line_accuracy"] for s in scores) / n,
    }
    failures = [] if summary["false_submits"] <= GATE["false_submits"] else ["false_submits"]
    failures += [k for k in ("decision_accuracy", "hold_reason_recall", "context_accuracy", "line_match_accuracy")
                 if summary[k] < GATE[k]]
    summary["failures"] = failures
    return not failures, summary
