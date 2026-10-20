"""Hub: the Reviewer's view of what the AI did. S0 is read-only; QC actions arrive in S3-S4.

Run: streamlit run src/invoice_assist/hub.py
"""
import json

import pandas as pd
import streamlit as st

from invoice_assist.config import settings
from invoice_assist.store import Store

st.set_page_config(page_title="Invoice hub", page_icon=":material/receipt_long:", layout="wide")


@st.cache_resource
def store() -> Store:
    return Store(settings.db_path)


STATUS_ICON = {"Submitted": ":material/check_circle:", "Held": ":material/pause_circle:",
               "Failed": ":material/error:", "Escalated": ":material/flag:"}

st.title("Invoice hub")
st.caption("AI decides first; reviewers check after. Every Stage Run is recorded.")


@st.fragment(run_every=settings.hub_refresh_seconds or None)
def queue():
    rows = store().invoices()
    if not rows:
        st.info("No invoices yet. Drop .eml files into the inbox folder.", icon=":material/inbox:")
        return
    df = pd.DataFrame([dict(r) for r in rows])
    df["status"] = [f"{STATUS_ICON.get(s, ':material/autorenew:')} {s}" for s in df["status"]]
    event = st.dataframe(
        df[["id", "status", "filename", "sender", "subject", "updated_at"]],
        hide_index=True, on_select="rerun", selection_mode="single-row", key="queue",
        alt="Invoices and their current status",
    )
    if event.selection.rows:
        st.session_state["selected"] = int(df.iloc[event.selection.rows[0]]["id"])


queue()

invoice_id = st.session_state.get("selected")
if invoice_id is None:
    st.stop()

s = store()
inv = s.invoice(invoice_id)
msg = s.message_for(invoice_id)
st.header(f"Invoice {invoice_id}: {inv['filename']}")
st.markdown(f"**Status:** {inv['status']}" + (f" at `{inv['failed_stage']}`" if inv["failed_stage"] else ""))
st.caption(f"From {msg['sender']} · {msg['subject']} · received {msg['received_at']}")

decision = s.latest_output(invoice_id, "decision")
submission = s.submission(invoice_id)
if decision:
    if decision["outcome"] == "submit":
        st.success(decision["rationale"], title=f"Submitted to ClinRun: {submission['clinrun_id'] if submission else '…'}",
                   icon=":material/check_circle:")
    else:
        st.warning("\n".join(f"- {d}" for d in decision["details"]), title="Held: " + ", ".join(decision["hold_reasons"]),
                   icon=":material/pause_circle:")

left, right = st.columns(2)
with left:
    with st.container(border=True):
        st.subheader("Extracted")
        ex = s.latest_output(invoice_id, "extraction")
        if ex:
            st.table(pd.Series(ex["header"], name="value"))
            st.dataframe(pd.DataFrame(ex["line_items"]), hide_index=True, alt="Extracted line items")
with right:
    with st.container(border=True):
        st.subheader("Context")
        ctx = s.latest_output(invoice_id, "context")
        if ctx:
            st.dataframe(pd.DataFrame([
                {"field": name, "header text": ctx[name]["header_text"], "resolved to": ctx[name]["record_name"],
                 "confidence": ctx[name]["confidence"], "confident": ctx[name]["confident"]}
                for name in ("sponsor", "study", "site")]), hide_index=True, alt="Resolved context with confidence")
            st.caption(f"Site linked to study: {ctx['site_linked_to_study']} · {ctx['explanation']}")
            with st.expander("Agent lookups"):
                st.code("\n".join(ctx["agent_lookups"]) or "none", language="text")

with st.container(border=True):
    st.subheader("Matched")
    m = s.latest_output(invoice_id, "matching")
    if m and m.get("skipped"):
        st.info(m["reason"] + ": matching was skipped.", icon=":material/block:")
    elif m and ex:
        by_no = {line["line_no"]: line for line in ex["line_items"]}
        catalog = {item["id"]: item for item in m["catalog"]}
        st.dataframe(pd.DataFrame([{
            "line": mm["line_no"], "as billed": by_no[mm["line_no"]]["description"],
            "unit price": by_no[mm["line_no"]]["unit_price"],
            "catalog item": f"{mm['item_code']}: {catalog[mm['catalog_item_id']]['description']}" if mm["catalog_item_id"] else "UNMATCHED",
            "catalog price": catalog[mm["catalog_item_id"]]["unit_price"] if mm["catalog_item_id"] else None,
            "confidence": mm["confidence"], "ambiguous": mm["ambiguous"], "reason": mm["reason"]}
            for mm in m["matches"]]), hide_index=True, alt="Line matches against the catalog")

with st.container(border=True):
    st.subheader("Stage runs")
    st.dataframe(pd.DataFrame([{k: r[k] for k in ("stage", "run_no", "trigger", "outcome", "started_at", "ended_at", "error")}
                               for r in s.stage_runs(invoice_id)]), hide_index=True, alt="Stage run history")
