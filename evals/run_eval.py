"""Run the gold set through the real pipeline and apply the quality gate (ADR-0012).

Usage (stack running, ANTHROPIC_API_KEY and LANGSMITH_API_KEY set):
    python -m evals.run_eval            # LangSmith experiment + local report; exit 1 if the gate fails
Each sample runs on a temporary Store with a fake ClinRun, so evals never submit anything.
An invoice whose gold Context is uncertain is then corrected to the gold Context (as a Reviewer
would), so its Line Matches are scored against the true Catalog too.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from invoice_assist.context import Reference
from invoice_assist.pipeline import Pipeline, Stages
from invoice_assist.review import ReviewActions
from invoice_assist.store import Store
from invoice_assist.worker import ingest

from .scoring import GATE, gate, score

ROOT = Path(__file__).resolve().parent.parent
GOLD = {path.stem: json.loads(path.read_text()) for path in sorted((ROOT / "evals" / "gold").glob("*.json"))}
DATASET = "lr-emailassist-gold"


def run_sample(sample: str) -> dict:
    gold = GOLD[sample]
    store = Store(Path(tempfile.mkdtemp()) / "eval.db")
    pipeline = Pipeline(store, Stages(submit=lambda submission, key: "CR-EVAL"))
    invoice_id = ingest(store, ROOT / gold["email"])[0]
    pipeline.process(invoice_id, trigger="eval")
    decision = store.latest_output(invoice_id, "decision") or {"outcome": "failed", "hold_reasons": []}
    ctx = store.latest_output(invoice_id, "context") or {}
    prediction = {
        "decision": decision["outcome"], "hold_reasons": decision["hold_reasons"],
        "context": {f"{f}_id": (ctx.get(f) or {}).get("record_id") for f in ("sponsor", "study", "site")},
        "context_confident": bool(ctx) and all(ctx[f]["confident"] for f in ("sponsor", "study", "site")),
        "rationale": decision.get("rationale", ""),
    }
    if not gold["context_should_be_confident"]:
        g = gold["context"]
        ReviewActions(store, pipeline, Reference.load()).correct_context(
            invoice_id, "eval", g["sponsor_id"], g["study_id"], g["site_id"], "gold Context")
        prediction["after_correction"] = store.latest_output(invoice_id, "decision")["outcome"]
    matching = store.latest_output(invoice_id, "matching") or {}
    prediction["lines"] = {str(m["line_no"]): m["item_code"] for m in matching.get("matches", [])}
    return prediction


def _evaluator(key: str):
    def evaluate(outputs: dict, reference_outputs: dict) -> dict:
        return {"key": key, "score": score(outputs, reference_outputs)[key]}
    evaluate.__name__ = key
    return evaluate


def main() -> int:
    if not os.getenv("LANGSMITH_API_KEY"):
        print("LANGSMITH_API_KEY is not set: evals record their results as LangSmith experiments "
              "(decisions.md, Design review outcomes: Eval platform).")
        return 2
    from langsmith import Client, evaluate
    client = Client()
    if not client.has_dataset(dataset_name=DATASET):
        client.create_dataset(DATASET, description="Labelled sample invoices (evals/gold)")
        client.create_examples(dataset_name=DATASET, examples=[
            {"inputs": {"sample": name}, "outputs": gold} for name, gold in GOLD.items()])
    results = evaluate(lambda inputs: run_sample(inputs["sample"]), data=DATASET,
                       evaluators=[_evaluator(k) for k in ("false_submit", "decision_correct", "hold_reason_recall",
                                                           "context_correct", "line_accuracy")],
                       experiment_prefix="gold", max_concurrency=1)
    rows = []
    for row in results:
        sample = row["example"].inputs["sample"]
        rows.append({"sample": sample, "prediction": row["run"].outputs, **score(row["run"].outputs, GOLD[sample])})
    passed, summary = gate(rows)
    report = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "passed": passed, "gate": GATE,
              "summary": summary, "experiment": results.experiment_name, "rows": rows}
    out = ROOT / "evals" / "reports"
    out.mkdir(exist_ok=True)
    (out / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [f"# Eval report ({report['at']})", "", f"**Gate: {'PASSED' if passed else 'FAILED ' + str(summary['failures'])}**"
             f" · LangSmith experiment `{results.experiment_name}`", "", "| Metric | Value | Gate |", "|---|---|---|"]
    lines += [f"| {k} | {summary[k]:.2f} | {'= 0' if k == 'false_submits' else '>= ' + str(GATE[k])} |" for k in GATE]
    lines += ["", "| Sample | Decision | Hold reasons | False submit | Context | Lines |", "|---|---|---|---|---|---|"]
    lines += [f"| {r['sample']} | {r['prediction']['decision']}"
              f"{' -> ' + r['prediction']['after_correction'] + ' after correction' if 'after_correction' in r['prediction'] else ''}"
              f" | {', '.join(r['prediction']['hold_reasons'])} | {r['false_submit']} | {r['context_correct']} | {r['line_accuracy']:.2f} |"
              for r in rows]
    (out / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
