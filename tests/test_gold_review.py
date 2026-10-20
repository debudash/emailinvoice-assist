"""Gold review (Hub > Gold review): the SME checks the answer key, and a change goes straight into it."""
import json
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from invoice_assist import gold

PAGE = str(ROOT / "src" / "invoice_assist" / "gold_review.py")


@pytest.fixture
def gold_copy(tmp_path, monkeypatch):
    """A copy of the gold folder, so no test writes into the real answer key."""
    shutil.copytree(ROOT / "evals" / "gold", tmp_path / "gold", ignore=shutil.ignore_patterns("review"))
    monkeypatch.setattr(gold, "GOLD_DIR", tmp_path / "gold")
    monkeypatch.setattr(gold, "REVIEW_DIR", tmp_path / "gold" / "review")
    return tmp_path / "gold"


def test_judgement_lines_come_with_a_plain_reason():
    large = gold.samples()["large"]
    catalog = gold.catalog_for(large)
    reasons = {line["line_no"]: gold.why_review(line, catalog) for line in large["lines"]}

    assert sorted(n for n, why in reasons.items() if why) == [10, 13, 18, 20, 22, 23, 24, 25, 26, 27]
    assert "Study Drug Shipping" in reasons[22]  # the other plausible item, by name
    assert "$475.00" in reasons[20] and "$450.00" in reasons[20]  # billed vs catalog price
    assert "not in the catalog" in reasons[25]


def test_saving_a_changed_answer_updates_the_answer_key_and_records_the_review(gold_copy):
    large = gold.samples()["large"]
    answers = {line["line_no"]: {"verdict": "agree", "item_code": None, "comment": ""} for line in large["lines"]}
    answers[22] = {"verdict": "change", "item_code": "PASS-SHIP", "comment": "Our drug ships ambient"}

    changed = gold.save_review("large", "Pat (SME)", answers, outcome_verdict="agree", outcome_comment="")

    assert changed == [22]
    line = json.loads((gold_copy / "large.json").read_text(encoding="utf-8"))["lines"][21]
    assert line["expected_item_code"] == "PASS-SHIP" and line["acceptable_item_codes"] == ["PASS-SHIP"]
    assert line["ambiguous"] is False and line["price_variance"] is True  # billed $125.00, PASS-SHIP is $75.00
    review = gold.last_review("large")
    assert review["reviewer"] == "Pat (SME)" and review["applied"] is True
    assert review["lines"][21] == {"line_no": 22, "verdict": "change", "corrected_code": "PASS-SHIP",
                                   "comment": "Our drug ships ambient"}


def test_agreeing_leaves_the_answer_key_unchanged(gold_copy):
    before = (gold_copy / "simple.json").read_text(encoding="utf-8")
    answers = {n: {"verdict": "agree", "item_code": None, "comment": ""} for n in range(1, 6)}

    assert gold.save_review("simple", "Pat (SME)", answers, outcome_verdict="agree", outcome_comment="") == []
    assert (gold_copy / "simple.json").read_text(encoding="utf-8") == before
    assert gold.last_review("simple")["applied"] is False


def test_page_shows_judgement_lines_first_and_saves_under_the_sme(gold_copy):
    at = AppTest.from_file(PAGE, default_timeout=30)
    at.run()
    at.radio(key="sample").set_value("large").run()

    assert not at.exception
    assert at.selectbox(key="reviewer").value == "Pat (SME)"
    first_cards = [m.value for m in at.markdown if m.value.startswith("**Line ")][:3]
    assert [c.split(":")[0] for c in first_cards] == ["**Line 10", "**Line 13", "**Line 18"]

    at.button(key="save").click().run()
    assert gold.last_review("large")["reviewer"] == "Pat (SME)"
