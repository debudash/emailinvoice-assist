"""Gold label review: check each labelled line against the catalog and record your feedback.

Run: streamlit run evals/gold_review.py   (no stack needed; reads the seed reference data)
Feedback is saved to evals/gold/review/<sample>.json. "Apply to gold file" also updates the
labels you changed in evals/gold/<sample>.json and records who reviewed it.
"""
import json
from datetime import datetime, timezone
from email import message_from_bytes, policy
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
GOLD_DIR, REVIEW_DIR, SEED = ROOT / "evals" / "gold", ROOT / "evals" / "gold" / "review", ROOT / "services" / "api" / "seed" / "data"
UNMATCHED = "(Unmatched)"
VERDICTS = ["agree", "change", "unsure"]

st.set_page_config(page_title="Gold label review", page_icon=":material/fact_check:", layout="wide")


@st.cache_data
def seed(name: str) -> dict:
    return {row["id"]: row for row in json.loads((SEED / f"{name}.json").read_text(encoding="utf-8"))}


def gold_files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(GOLD_DIR.glob("*.json"))}


def invoice_pdf(gold: dict) -> bytes | None:
    msg = message_from_bytes((ROOT / gold["email"]).read_bytes(), policy=policy.default)
    return next((part.get_content() for part in msg.iter_attachments()), None)


st.title("Gold label review")
st.caption("The eval scores the pipeline against these labels. Check each line against the catalog, "
           "mark it, and save. Your feedback is kept in the repo next to the labels.")

reviewer = st.text_input("Your name", value=st.session_state.get("reviewer", ""), key="reviewer")
files = gold_files()
sample = st.segmented_control("Sample", list(files), default=list(files)[0], key="sample")
if not sample:
    st.stop()
gold = json.loads(files[sample].read_text(encoding="utf-8"))
review_path = REVIEW_DIR / f"{sample}.json"
previous = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else None

sponsors, studies, sites, catalog = seed("sponsors"), seed("studies"), seed("sites"), seed("catalog_items")
ctx = gold["context"]
study_catalog = {c["item_code"]: c for c in catalog.values() if c["study_id"] == ctx["study_id"]}

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("Expected outcome")
        st.markdown(f"**{gold['expected_decision'].title()}** · hold reasons: "
                    f"{', '.join(gold['expected_hold_reasons']) or 'none'}")
        st.markdown(f"Context: **{sponsors[ctx['sponsor_id']]['name']}** / **{studies[ctx['study_id']]['name']}** "
                    f"({studies[ctx['study_id']]['protocol_number']}) / **{sites[ctx['site_id']]['name']}** · "
                    f"confident: {gold['context_should_be_confident']}")
        st.caption(gold.get("notes", ""))
        if previous:
            st.info(f"Last reviewed by {previous['reviewer']} at {previous['at']}"
                    + (" · applied to the gold file" if previous.get("applied") else ""), icon=":material/history:")
with right:
    pdf = invoice_pdf(gold)
    with st.expander("Invoice as received", expanded=False, icon=":material/description:"):
        if pdf:
            st.pdf(pdf, height=500, alt=f"{sample} invoice")

prior = {str(l["line_no"]): l for l in (previous or {}).get("lines", [])}
rows = []
for line in gold["lines"]:
    code = line["expected_item_code"]
    item = study_catalog.get(code) if code else None
    p = prior.get(str(line["line_no"]), {})
    rows.append({
        "line": line["line_no"], "as printed": line["description"],
        "gold code": code or UNMATCHED,
        "catalog description": item["description"] if item else "",
        "catalog price": item["unit_price"] if item else "",
        "also accepted": ", ".join(c or UNMATCHED for c in line["acceptable_item_codes"] if c != code),
        "ambiguous": line["ambiguous"], "price variance": line["price_variance"],
        "verdict": p.get("verdict", "agree"), "corrected code": p.get("corrected_code"), "comment": p.get("comment", ""),
    })

st.subheader("Lines")
edited = st.data_editor(
    pd.DataFrame(rows), hide_index=True, key=f"editor_{sample}",
    disabled=["line", "as printed", "gold code", "catalog description", "catalog price", "also accepted",
              "ambiguous", "price variance"],
    column_config={
        "verdict": st.column_config.SelectboxColumn("verdict", options=VERDICTS, required=True),
        "corrected code": st.column_config.SelectboxColumn(
            "corrected code", options=[UNMATCHED] + sorted(study_catalog), help="Only when the verdict is 'change'"),
        "comment": st.column_config.TextColumn("comment", width="large"),
    },
    alt="Gold labels with your review",
)
with st.expander(f"Catalog for {studies[ctx['study_id']]['name']} ({len(study_catalog)} items)"):
    st.dataframe(pd.DataFrame([{k: c[k] for k in ("item_code", "description", "category", "unit_price")}
                               for c in study_catalog.values()]), hide_index=True, alt="Study catalog")

outcome_ok = st.radio("Do you agree with the expected outcome and hold reasons?", VERDICTS, horizontal=True,
                      index=VERDICTS.index((previous or {}).get("outcome_verdict", "agree")))
outcome_comment = st.text_area("Comment on the outcome", value=(previous or {}).get("outcome_comment", ""))


def feedback(applied: bool) -> dict:
    return {"sample": sample, "reviewer": reviewer.strip(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "outcome_verdict": outcome_ok, "outcome_comment": outcome_comment, "applied": applied,
            "lines": [{"line_no": int(r["line"]), "verdict": r["verdict"], "corrected_code": r["corrected code"],
                       "comment": r["comment"]} for r in edited.to_dict("records")]}


changes = [r for r in edited.to_dict("records") if r["verdict"] == "change"]
bad = [r["line"] for r in changes if not r["corrected code"]]
save, apply = st.columns(2)
with save:
    if st.button("Save feedback", type="primary", icon=":material/save:", width="stretch", disabled=not reviewer.strip()):
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(feedback(applied=False), indent=2), encoding="utf-8")
        st.success(f"Saved to {review_path.relative_to(ROOT)}", icon=":material/check:")
with apply:
    if st.button(f"Apply {len(changes)} change(s) to the gold file", icon=":material/edit_note:", width="stretch",
                 disabled=not reviewer.strip() or not changes or bool(bad)):
        by_line = {int(r["line"]): r for r in changes}
        for line in gold["lines"]:
            if line["line_no"] in by_line:
                code = by_line[line["line_no"]]["corrected code"]
                line["expected_item_code"] = None if code == UNMATCHED else code
                line["acceptable_item_codes"] = [line["expected_item_code"]]
        gold["reviewed_by"] = {"reviewer": reviewer.strip(), "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        files[sample].write_text(json.dumps(gold, indent=2), encoding="utf-8")
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        review_path.write_text(json.dumps(feedback(applied=True), indent=2), encoding="utf-8")
        st.success(f"Updated {files[sample].relative_to(ROOT)}; rerun the eval to see the effect.", icon=":material/check:")
if bad:
    st.warning(f"Pick a corrected code for line(s) {', '.join(map(str, bad))} before applying.", icon=":material/rule:")
if not reviewer.strip():
    st.caption("Enter your name to save.")
