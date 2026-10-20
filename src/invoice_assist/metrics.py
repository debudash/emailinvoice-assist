"""Metrics: Straight-Through rate, Holds by reason, Stage timings and estimated time saved.

Time saved compares a manual baseline (minutes per Invoice plus minutes per Line Item, shown on
screen as an assumption) with the pipeline's actual processing time.
"""
from collections import Counter
from datetime import datetime


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def summary(store, minutes_per_invoice: float = 5, minutes_per_line: float = 1) -> dict:
    invoices = store.db.execute("SELECT id, status FROM invoices").fetchall()
    decided = [i for i in invoices if store.latest_output(i["id"], "decision")]
    straight = [i for i in decided if store.latest_output(i["id"], "decision")["straight_through"]]
    holds = Counter(r for i in decided for r in store.latest_output(i["id"], "decision")["hold_reasons"])
    lines = sum(len((store.latest_output(i["id"], "extraction") or {}).get("line_items", [])) for i in invoices)
    runs = store.db.execute("SELECT stage, started_at, ended_at FROM stage_runs WHERE outcome='succeeded'").fetchall()
    by_stage: dict[str, list[float]] = {}
    for r in runs:
        by_stage.setdefault(r["stage"], []).append(_seconds(r["started_at"], r["ended_at"]))
    actual_minutes = sum(sum(v) for v in by_stage.values()) / 60
    manual_minutes = len(invoices) * minutes_per_invoice + lines * minutes_per_line
    return {
        "invoices": len(invoices),
        "straight_through_rate": len(straight) / len(decided) if decided else 0.0,
        "holds_by_reason": dict(holds),
        "stage_seconds": {stage: round(sum(v) / len(v), 1) for stage, v in by_stage.items()},
        "manual_minutes": manual_minutes,
        "actual_minutes": round(actual_minutes, 1),
    }
