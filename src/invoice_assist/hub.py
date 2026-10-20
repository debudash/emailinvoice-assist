"""Hub: where Reviewers check the AI's Decisions after the fact and act on Invoices.

Run: streamlit run src/invoice_assist/hub.py
Every action goes through Review Actions, which enforces the rules and keeps the audit trail;
the Hub only shows state and collects input. ActionRefused is the one error boundary.
"""
import json

import pandas as pd
import streamlit as st

from invoice_assist import metrics
from invoice_assist.config import settings
from invoice_assist.context import Reference
from invoice_assist.intake import write_upload
from invoice_assist.models import NEXT_STEP, HoldReason, InvoiceStatus
from invoice_assist.pipeline import Pipeline
from invoice_assist.review import ActionRefused, ReviewActions
from invoice_assist.store import Store

st.set_page_config(page_title="Invoice hub", page_icon=":material/receipt_long:", layout="wide")

ACTORS = ["Dana (Reviewer)", "Sam (Reviewer)", "Ops (Operator)"]
QUEUES = ["Held", "Escalated", "Failed", "Submitted", "All"]


def store() -> Store:
    """One SQLite connection per browser session; the worker writes through its own."""
    if "store" not in st.session_state:
        st.session_state["store"] = Store(settings.db_path)
    return st.session_state["store"]


@st.cache_resource(ttl=600)
def reference() -> Reference:
    return Reference.load()


def actions(with_reference: bool = True) -> ReviewActions:
    return ReviewActions(store(), Pipeline(store()), reference() if with_reference else None)


def run_action(label: str, action: str, *args):
    """The one friendly error boundary: every Review Action is built and called inside it."""
    with st.spinner(f"{label}… the pipeline reruns the affected Stages"):
        try:
            status = getattr(actions(), action)(*args)
        except ActionRefused as refused:
            st.error(str(refused), title=f"{label} refused", icon=":material/block:")
            return
        except Exception as exc:  # the one friendly boundary (CLAUDE.md): never a raw traceback
            st.error(f"{type(exc).__name__}: {exc}. Nothing was submitted; check the History and try again.",
                     title=f"{label} could not complete", icon=":material/error:")
            return
    st.session_state["flash"] = f"{label} done: invoice is now {status}"
    st.rerun()


# --- Sidebar: identity, Operator controls, upload ----------------------------------------
with st.sidebar:
    actor = st.selectbox("Acting as", ACTORS, help="Authentication is assumed upstream; this records who acted.")
    st.subheader("Inbox poller")
    s = store()
    st.toggle("Pause poller", value=s.control("paused") == "1", key="paused",
              on_change=lambda: store().set_control("paused", "1" if st.session_state["paused"] else "0"))
    if st.button("Check inbox now", icon=":material/refresh:", width="stretch"):
        s.set_control("check_now", "1")
        st.toast("The worker will check the inbox on its next tick")
    st.caption(f"Last poll: {s.control('last_poll', 'not yet')}")
    st.subheader("Upload an invoice")
    upload = st.file_uploader("PDF or image", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed")
    if upload and st.button("Add to inbox", icon=":material/upload:", width="stretch"):
        write_upload(settings.inbox_dir, upload.name, upload.type or "application/pdf", upload.getvalue(), actor)
        st.toast("Added to the inbox; the worker picks it up on its next poll")

# --- Header and metrics -------------------------------------------------------------------
st.title("Invoice hub")
st.caption("The AI decides first; Reviewers check after. Every Stage Run and action is recorded.")
if flash := st.session_state.pop("flash", None):
    st.success(flash, icon=":material/task_alt:")


@st.fragment(run_every=settings.hub_refresh_seconds or None)
def metrics_strip():
    m = metrics.summary(store(), settings.minutes_per_invoice, settings.minutes_per_line)
    with st.container(horizontal=True):
        st.metric("Invoices", m["invoices"], border=True)
        st.metric("Straight-through", f"{m['straight_through_rate']:.0%}", border=True)
        st.metric("Manual estimate", f"{m['manual_minutes']:.0f} min", border=True)
        st.metric("AI processing", f"{m['actual_minutes']:.1f} min", border=True)
    holds = ", ".join(f"{k} ({v})" for k, v in m["holds_by_reason"].items()) or "none"
    st.caption(f"Holds by reason: {holds} · Avg Stage seconds: {m['stage_seconds']} · "
               f"Manual baseline assumption: {settings.minutes_per_invoice:g} min per invoice + "
               f"{settings.minutes_per_line:g} min per line item")


metrics_strip()

# --- Queues -------------------------------------------------------------------------------
queue_name = st.segmented_control("Queue", QUEUES, default="Held", key="queue_name")


def queue_rows(name: str | None) -> list[dict]:
    rows = [dict(r) for r in store().invoices()]
    return [r for r in rows if r["status"] == name] if name and name != "All" else rows


# ISSUE-003: choosing a queue or ticking a row did not change the invoice shown below.
# Root cause: the table lives in an auto-refreshing fragment, so a row click reran only the fragment
# and the detail (outside it) never redrew; one table key was shared by every queue, so a stored row
# position pointed at another queue's invoice; and the detail never checked the selection was in the
# chosen queue. Fix: a changed selection reruns the whole app, each queue keeps its own table state,
# and the detail always shows an invoice from the chosen queue (its first when nothing is selected).
@st.fragment(run_every=settings.hub_refresh_seconds or None)
def queue():
    rows = queue_rows(queue_name)
    if not rows:
        st.info(f"Nothing in {queue_name or 'this queue'}.", icon=":material/inbox:")
        return
    df = pd.DataFrame(rows)
    df["reasons"] = [", ".join((store().latest_output(i, "decision") or {}).get("hold_reasons", [])) for i in df["id"]]
    # ISSUE-004: the status column showed ":material/pause_circle: Held" as literal text. Root cause:
    # dataframe cells render plain text, not Markdown, so the icon shortcode was never drawn. Fix: plain
    # status words in the table; icons stay on the alerts, which do render them.
    # ISSUE-006: when a new Invoice arrived, the detail jumped to a different Invoice on its own.
    # Root cause: the table remembers a selected row position, not an Invoice; newest-first rows shift
    # on refresh, so the same position named another Invoice. Fix: the key includes the row ids, so a
    # changed row set starts with no selection and the detail keeps the Invoice in "selected".
    table_key = f"queue_table_{queue_name}_{'-'.join(map(str, df['id']))}"
    event = st.dataframe(df[["id", "status", "reasons", "filename", "sender", "updated_at"]], hide_index=True,
                         on_select="rerun", selection_mode="single-row", key=table_key,
                         alt="Invoices in the selected queue")
    if event.selection.rows:
        chosen = int(df.iloc[event.selection.rows[0]]["id"])
        if chosen != st.session_state.get("selected"):
            st.session_state["selected"] = chosen
            st.rerun()  # the whole app, so the detail below shows the chosen invoice


queue()
with st.expander("Rejected messages"):
    rejected = store().rejected_messages()
    if rejected:
        st.dataframe(pd.DataFrame([{k: r[k] for k in ("sender", "subject", "received_at", "rejection_reason")}
                                   for r in rejected]), hide_index=True, alt="Messages with no invoice file")
    else:
        st.caption("None")

in_queue = [r["id"] for r in queue_rows(queue_name)]
invoice_id = st.session_state.get("selected")
if invoice_id not in in_queue:
    invoice_id = in_queue[0] if in_queue else None
    st.session_state["selected"] = invoice_id
if invoice_id is None:
    st.stop()

# --- Invoice detail -----------------------------------------------------------------------
s = store()
inv, msg = s.invoice(invoice_id), s.message_for(invoice_id)
ex, ctx = s.latest_output(invoice_id, "extraction"), s.latest_output(invoice_id, "context")
m, decision, submission = s.latest_output(invoice_id, "matching"), s.latest_output(invoice_id, "decision"), s.submission(invoice_id)
st.header(f"Invoice {invoice_id}: {inv['filename']}")
st.caption(f"{msg['source']} · from {msg['sender']} · {msg['subject']} · received {msg['received_at']}")

if inv["status"] == InvoiceStatus.failed:
    st.error(f"Failed at the {inv['failed_stage']} Stage: {s.stage_runs(invoice_id)[-1]['error']}",
             title="No Decision was made", icon=":material/error:")
elif decision and submission and inv["status"] == InvoiceStatus.submitted:
    st.success(decision["rationale"], title=f"Submitted to ClinRun: {submission['clinrun_id']}", icon=":material/check_circle:")
elif decision:
    st.warning(decision["rationale"] + "\n\n" + "\n".join(f"- {d}" for d in decision["details"]),
               title=f"{inv['status']}: " + ", ".join(decision["hold_reasons"]), icon=":material/pause_circle:")
    # ISSUE-007: the Hub never said which action clears a Hold, so a Price Variance got Corrections
    # that could not clear it. Fix: name the next step for each Hold Reason on the hold.
    st.markdown("**What clears it**\n\n" + "\n".join(f"- **{r}**: {NEXT_STEP[HoldReason(r)]}"
                                                     for r in dict.fromkeys(decision["hold_reasons"])))

# --- Actions --------------------------------------------------------------------------------
if inv["status"] in (InvoiceStatus.held, InvoiceStatus.escalated) and decision:
    needs_correction = actions(with_reference=False).release_blockers(invoice_id)
    try:
        ref = reference()
    except Exception as exc:  # ref-mcp down: show it, keep the rest of the page usable
        ref = None
        st.warning(f"Reference data is unavailable ({type(exc).__name__}); Context corrections are disabled "
                   "until ref-mcp is back.", icon=":material/cloud_off:")
    with st.container(border=True):
        st.subheader("Act on this invoice")
        tabs = st.tabs(["Correct context", "Correct a line", "Release", "Escalate"])
        with tabs[0]:
            if ref is None:
                st.caption("Unavailable while reference data cannot be loaded.")
            else:
                with st.form("correct_context"):
                    st.caption("Choose any record; the Suggested Context is preselected where there is one. "
                               "Matching and the Decision rerun.")

                    def pick(label, rows, field, fmt):
                        suggested = ctx[field]["record_id"]
                        index = next((i for i, r in enumerate(rows) if r["id"] == suggested), None)
                        return st.selectbox(label, rows, format_func=fmt, index=index, placeholder="Choose a record")
                    sponsor = pick("Sponsor", ref.sponsors, "sponsor", lambda r: r["name"])
                    study = pick("Study", ref.studies, "study", lambda r: f"{r['name']} ({r['protocol_number']})")
                    site = pick("Site", ref.sites, "site", lambda r: f"{r['name']} · {r.get('pi_name') or ''}")
                    note = st.text_input("Why (required)")
                    if st.form_submit_button("Apply correction and rerun", type="primary"):
                        if None in (sponsor, study, site):
                            st.error("Choose a sponsor, a study and a site.", icon=":material/rule:")
                        else:
                            run_action("Correction", "correct_context", invoice_id, actor, sponsor["id"], study["id"],
                                       site["id"], note)
        with tabs[1]:
            if m and not m.get("skipped") and ex:
                with st.form("correct_line"):
                    lines = {line["line_no"]: line for line in ex["line_items"]}
                    line_no = st.selectbox("Line", list(lines), format_func=lambda n: f"{n}: {lines[n]['description']}")
                    options = [None] + m["catalog"]
                    item = st.selectbox("Catalog Item", options, format_func=lambda r: "Unmatched" if r is None
                                        else f"{r['item_code']}: {r['description']} ({r['unit_price']})")
                    note = st.text_input("Why (required)", key="line_note")
                    if st.form_submit_button("Apply and rerun the Decision", type="primary"):
                        run_action("Line correction", "correct_line", invoice_id, actor, line_no,
                                   item["id"] if item else None, note)
            else:
                st.caption("Matching has not run; correct the Context first.")
        with tabs[2]:
            if needs_correction:
                st.info(f"Release is not available: {', '.join(needs_correction)} needs a Correction.", icon=":material/lock:")
            else:
                with st.form("release"):
                    st.caption("Submits as-is. Your reason travels with the submission to ClinRun.")
                    reason = st.text_input("Release reason (required)")
                    if st.form_submit_button("Release to ClinRun", type="primary"):
                        run_action("Release", "release", invoice_id, actor, reason)
        with tabs[3], st.form("escalate"):
            note = st.text_area("What needs a second look (required)")
            if st.form_submit_button("Escalate"):
                run_action("Escalation", "escalate", invoice_id, actor, note)
elif inv["status"] == InvoiceStatus.failed:
    if st.button(f"Rerun from {inv['failed_stage']}", type="primary", icon=":material/replay:"):
        run_action("Rerun", "rerun", invoice_id, actor, inv["failed_stage"])
elif inv["status"] == InvoiceStatus.submitted:
    st.caption("Corrections to a submitted invoice become Amendments (planned, P2).")

# --- What the AI saw and did ------------------------------------------------------------------
left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader("Extracted")
    with st.expander("Original document", icon=":material/description:"):
        if inv["media_type"] == "application/pdf":
            st.pdf(bytes(inv["data"]), height=600, alt=f"Invoice {inv['filename']} as received")
        else:
            st.image(bytes(inv["data"]), alt=f"Invoice {inv['filename']} as received")
    if ex:
        st.table(pd.Series({k: "" if v is None else str(v) for k, v in ex["header"].items()}, name="value"))
        st.dataframe(pd.DataFrame(ex["line_items"]), hide_index=True, alt="Extracted line items")
with right, st.container(border=True):
    st.subheader("Context")
    if ctx:
        st.dataframe(pd.DataFrame([
            {"field": f, "header text": ctx[f]["header_text"], "resolved to": ctx[f]["record_name"],
             "confidence": ctx[f]["confidence"], "confident": ctx[f]["confident"]} for f in ("sponsor", "study", "site")]),
            hide_index=True, alt="Resolved context with computed confidence")
        st.caption(f"Site linked to study: {ctx['site_linked_to_study']} · Study belongs to sponsor: "
                   f"{ctx['study_belongs_to_sponsor']} · {ctx['explanation']}")
        with st.expander("Agent lookups"):
            st.code("\n".join(ctx["agent_lookups"]) or "none", language="text")

with st.container(border=True):
    st.subheader("Matched")
    if m and m.get("skipped"):
        st.info(m["reason"] + ": matching was skipped so nothing is priced against the wrong Catalog.", icon=":material/block:")
    elif m and ex:
        lines, catalog = {l["line_no"]: l for l in ex["line_items"]}, {i["id"]: i for i in m["catalog"]}
        st.dataframe(pd.DataFrame([{
            "line": mm["line_no"], "as billed": lines[mm["line_no"]]["description"], "unit price": lines[mm["line_no"]]["unit_price"],
            "catalog item": f"{mm['item_code']}: {catalog[mm['catalog_item_id']]['description']}" if mm["catalog_item_id"] else "UNMATCHED",
            "catalog price": catalog[mm["catalog_item_id"]]["unit_price"] if mm["catalog_item_id"] else None,
            "confidence": mm["confidence"], "ambiguous": mm["ambiguous"], "alternatives": ", ".join(mm["alternatives"]),
            "reason": mm["reason"]} for mm in m["matches"]]), hide_index=True, alt="Line matches against the catalog")

with st.container(border=True):
    st.subheader("History")
    st.dataframe(pd.DataFrame([{k: r[k] for k in ("stage", "run_no", "trigger", "outcome", "attempts", "served_by",
                                                   "started_at", "ended_at", "error")} for r in s.stage_runs(invoice_id)]),
                 hide_index=True, alt="Stage run history")
    decisions = [r for r in s.stage_runs(invoice_id) if r["stage"] == "decision" and r["outcome"] == "succeeded"]
    if len(decisions) > 1:  # the AI's original Decision next to the one after a Correction (story 59)
        st.markdown("**Decisions over time**")
        st.dataframe(pd.DataFrame([{"run": r["run_no"], "trigger": r["trigger"], "outcome": out["outcome"],
                                    "hold reasons": ", ".join(out["hold_reasons"]), "rationale": out["rationale"]}
                                   for r in decisions for out in [json.loads(r["output"])]]),
                     hide_index=True, alt="Each Decision the AI made for this invoice")
    audit = s.actions(invoice_id)
    if audit:
        st.dataframe(pd.DataFrame([{k: r[k] for k in ("at", "actor", "kind", "note")} for r in audit]),
                     hide_index=True, alt="Reviewer and Operator actions")
