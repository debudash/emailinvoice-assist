"""Gold set: the answer key the eval scores against, and the subject matter expert's review of it.

The review page is Hub > Gold review. A changed answer goes straight into the gold file; every
review, changed or not, is saved to evals/gold/review/<sample>.json. Rerunning the eval after a
change is an engineering step (python -m evals.run_eval); it is not wired into CI yet.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "evals" / "gold"
REVIEW_DIR = GOLD_DIR / "review"
SEED = ROOT / "services" / "api" / "seed" / "data"

TITLES = {"simple": "Simple invoice", "medium": "Medium invoice", "large": "Large invoice",
          "mismatched-metadata": "Invoice with wrong header details"}
REASON_WORDS = {"price_variance": "a price that differs from the catalog",
                "unmatched": "lines with no catalog item", "ambiguous": "a line that could be more than one item",
                "context_uncertain": "header details that don't match the reference data",
                "site_not_linked": "a site not linked to the study", "arithmetic": "amounts that don't add up"}


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def samples() -> dict[str, dict]:
    """Every gold sample, simplest first (the order of TITLES; any other sample after them)."""
    order = list(TITLES)
    paths = sorted(GOLD_DIR.glob("*.json"), key=lambda p: (order.index(p.stem) if p.stem in order else len(order), p.stem))
    return {path.stem: _read(path) for path in paths}


def last_review(sample: str) -> dict | None:
    path = REVIEW_DIR / f"{sample}.json"
    return _read(path) if path.exists() else None


def catalog_for(gold: dict) -> dict[str, dict]:
    """The Catalog of the sample's true study, by item code."""
    study = gold["context"]["study_id"]
    return {c["item_code"]: c for c in _read(SEED / "catalog_items.json") if c["study_id"] == study}


def seed(name: str) -> dict[int, dict]:
    return {row["id"]: row for row in _read(SEED / f"{name}.json")}


def why_review(line: dict, catalog: dict[str, dict]) -> str | None:
    """Why a person should look at this line, in plain words; None when it is straightforward."""
    code = line["expected_item_code"]
    if code is None:
        return "Nothing in the catalog fits, so the answer is 'not in the catalog' and the invoice should hold."
    if line["ambiguous"]:
        others = [catalog[c] for c in line["acceptable_item_codes"] if c and c != code]
        names = " or ".join(f"'{c['description']}' (${c['unit_price']})" for c in others)
        return (f"Could also be {names}. The answer picks '{catalog[code]['description']}', and the AI should "
                "still flag the line for a person.")
    if line["price_variance"]:
        return (f"Billed ${line['billed_unit_price']}, catalog price ${catalog[code]['unit_price']}. "
                "The answer expects a hold for the price difference.")
    return line.get("review_note")


def save_review(sample: str, reviewer: str, answers: dict[int, dict], outcome_verdict: str,
                outcome_comment: str) -> list[int]:
    """Record the review; write changed answers into the gold file. Returns the changed line numbers.

    answers: line_no -> {"verdict": "agree" | "change" | "unsure", "item_code": code or None, "comment"}.
    """
    path, at = GOLD_DIR / f"{sample}.json", datetime.now(timezone.utc).isoformat(timespec="seconds")
    gold = _read(path)
    catalog = catalog_for(gold)
    changed = []
    for line in gold["lines"]:
        answer = answers[line["line_no"]]
        if answer["verdict"] != "change" or answer["item_code"] == line["expected_item_code"]:
            continue
        code = answer["item_code"]  # None means "not in the catalog" (Unmatched)
        line.update(expected_item_code=code, acceptable_item_codes=[code], ambiguous=False,
                    price_variance=bool(code) and Decimal(line["billed_unit_price"]) != Decimal(catalog[code]["unit_price"]))
        changed.append(line["line_no"])
    if changed:
        gold["reviewed_by"] = {"reviewer": reviewer, "at": at}
        path.write_text(json.dumps(gold, indent=2) + "\n", encoding="utf-8")
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (REVIEW_DIR / f"{sample}.json").write_text(json.dumps({
        "sample": sample, "reviewer": reviewer, "at": at, "outcome_verdict": outcome_verdict,
        "outcome_comment": outcome_comment, "applied": bool(changed),
        "lines": [{"line_no": n, "verdict": a["verdict"],
                   "corrected_code": a["item_code"] if a["verdict"] == "change" else None, "comment": a["comment"]}
                  for n, a in sorted(answers.items())]}, indent=2) + "\n", encoding="utf-8")
    return changed
