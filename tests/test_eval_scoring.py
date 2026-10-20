"""The eval scoring and gate (ADR-0012), as pure functions."""
from evals.scoring import GATE, gate, score

GOLD = {
    "context": {"sponsor_id": 1, "study_id": 1, "site_id": 2}, "context_should_be_confident": True,
    "lines": [{"line_no": 1, "acceptable_item_codes": ["ADMIN-SITE"]},
              {"line_no": 2, "acceptable_item_codes": ["PASS-COLD", "PASS-SHIP"]},
              {"line_no": 3, "acceptable_item_codes": [None]}],
    "expected_decision": "hold", "expected_hold_reasons": ["price_variance", "unmatched"],
}


def prediction(**overrides):
    base = {"decision": "hold", "hold_reasons": ["price_variance", "unmatched", "ambiguous"],
            "context": {"sponsor_id": 1, "study_id": 1, "site_id": 2}, "context_confident": True,
            "lines": {"1": "ADMIN-SITE", "2": "PASS-SHIP", "3": None}}
    return {**base, **overrides}


def test_correct_hold_with_extra_reason_scores_full_recall():
    s = score(prediction(), GOLD)
    assert s == {"false_submit": 0, "decision_correct": 1, "hold_reason_recall": 1.0, "context_correct": 1,
                 "line_accuracy": 1.0}


def test_submitting_an_invoice_gold_holds_is_a_false_submit():
    s = score(prediction(decision="submit", hold_reasons=[]), GOLD)
    assert s["false_submit"] == 1 and s["decision_correct"] == 0 and s["hold_reason_recall"] == 0.0


def test_wrong_site_or_wrong_confidence_fails_context():
    assert score(prediction(context={"sponsor_id": 1, "study_id": 1, "site_id": 3}), GOLD)["context_correct"] == 0
    assert score(prediction(context_confident=False), GOLD)["context_correct"] == 0


def test_line_accuracy_counts_missing_and_wrong_lines():
    assert score(prediction(lines={"1": "ADMIN-SITE", "2": "PROC-ECG"}), GOLD)["line_accuracy"] == 1 / 3


def test_gate_fails_on_any_false_submit_even_with_high_accuracy():
    good = [score(prediction(), GOLD)] * 19
    bad = score(prediction(decision="submit", hold_reasons=[]), GOLD)
    passed, summary = gate(good + [bad])
    assert not passed and summary["false_submits"] == 1 and summary["decision_accuracy"] >= GATE["decision_accuracy"]


def test_gate_passes_when_every_floor_is_met():
    passed, summary = gate([score(prediction(), GOLD)] * 4)
    assert passed and summary == {"examples": 4, "false_submits": 0, "decision_accuracy": 1.0,
                                  "hold_reason_recall": 1.0, "context_accuracy": 1.0, "line_match_accuracy": 1.0,
                                  "failures": []}
