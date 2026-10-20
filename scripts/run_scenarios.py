"""Run generated test scenarios and compare each outcome with what was expected.

Prerequisites: the stack is up (ref-mcp on localhost:8200) and ANTHROPIC_API_KEY is set.
    python scripts/make_test_invoices.py            # generate (once)
    python scripts/run_scenarios.py                 # every scenario, in process (nothing is submitted)
    python scripts/run_scenarios.py price-variance unmatched
    python scripts/run_scenarios.py --via-inbox     # drop the emails into inbox/ and watch them in the Hub
A scenario passes when the Decision matches and every expected Hold Reason is present
(extra reasons are shown but allowed). Exit code 1 if any scenario fails.
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
GENERATED = ROOT / "samples" / "generated"


def scenarios(names: list[str]) -> list[dict]:
    golds = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GENERATED.glob("*/gold.json"))]
    if not golds:
        sys.exit("No scenarios found: run python scripts/make_test_invoices.py first.")
    return [g for g in golds if not names or g["sample"] in names]


def via_inbox(golds: list[dict]):
    inbox = ROOT / "inbox"
    inbox.mkdir(exist_ok=True)
    for g in golds:
        shutil.copy(ROOT / g["email"], inbox / f"{int(time.time())}-{g['sample']}.eml")
        print(f"queued {g['sample']:<20} expect {g['expected_decision']} {g['expected_hold_reasons'] or ''}")
    print("Watch them arrive in the Hub: http://localhost:8501 (queue 'All').")


def in_process(golds: list[dict]) -> int:
    from evals.run_eval import run_gold
    failures = 0
    print(f"{'scenario':<20} {'expected':<32} {'actual':<44} result")
    for g in golds:
        started = time.time()
        p = run_gold(g)
        expected = f"{g['expected_decision']} {','.join(g['expected_hold_reasons'])}".strip()
        actual = f"{p['decision']} {','.join(p['hold_reasons'])}".strip()
        ok = p["decision"] == g["expected_decision"] and set(g["expected_hold_reasons"]) <= set(p["hold_reasons"])
        failures += not ok
        print(f"{g['sample']:<20} {expected:<32} {actual:<44} {'PASS' if ok else 'FAIL'} ({time.time() - started:.0f}s)")
        if not ok:
            print(f"{'':<20} rationale: {p['rationale']}")
    print(f"\n{len(golds) - failures}/{len(golds)} scenarios passed")
    return 1 if failures else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    chosen = scenarios([a for a in args if not a.startswith("--")])
    if "--via-inbox" in args:
        via_inbox(chosen)
    else:
        sys.exit(in_process(chosen))
