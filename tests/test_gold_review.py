"""Gold review page: renders every sample and saves feedback without touching the gold file."""
import json
import shutil

from streamlit.testing.v1 import AppTest

from conftest import ROOT

PAGE = ROOT / "evals" / "gold_review.py"


def test_review_page_saves_feedback_to_the_review_folder(tmp_path, monkeypatch):
    # Work on a copy so the test never writes into the real gold folder.
    shutil.copytree(ROOT / "evals", tmp_path / "evals")
    shutil.copytree(ROOT / "services" / "api" / "seed", tmp_path / "services" / "api" / "seed")
    shutil.copytree(ROOT / "samples", tmp_path / "samples")
    page = tmp_path / "evals" / "gold_review.py"

    at = AppTest.from_file(str(page), default_timeout=30)
    at.run()
    assert not at.exception
    at.text_input(key="reviewer").input("Debu").run()
    at.button[0].click().run()  # Save feedback

    saved = json.loads((tmp_path / "evals" / "gold" / "review" / "large.json").read_text(encoding="utf-8"))
    assert saved["reviewer"] == "Debu" and saved["applied"] is False and len(saved["lines"]) == 27
    assert json.loads((tmp_path / "evals" / "gold" / "large.json").read_text()) == \
        json.loads((ROOT / "evals" / "gold" / "large.json").read_text())
