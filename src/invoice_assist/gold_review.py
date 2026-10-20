"""Hub > Gold review: a subject matter expert checks the answer key the AI is scored against.

Lines that need judgement come first, each with the reason in plain words; the straightforward
ones sit in an expander. "Save review" records the review and writes any changed answer straight
into the gold file (invoice_assist.gold).
"""
from email import message_from_bytes, policy

import streamlit as st

from invoice_assist import gold
from invoice_assist.config import ACTORS, SME

UNMATCHED = "(not in the catalog)"
VERDICTS = {"agree": "Yes, that's right", "change": "No, it's a different item", "unsure": "Not sure"}

st.title("Gold review")
st.markdown("The AI is scored against an **answer key**: for each sample invoice, the right catalog item for "
            "every line and whether the invoice should be submitted or held. You're checking that the answer "
            "key is right. Lines that need your judgement come first.")
reviewer = st.selectbox("Reviewing as", ACTORS, index=ACTORS.index(SME), key="reviewer")

all_gold = gold.samples()


def status(sample: str) -> str:
    g, review = all_gold[sample], gold.last_review(sample)
    done = f"reviewed by {review['reviewer']} on {review['at'][:10]}" if review else "not reviewed yet"
    return f"Expected: {g['expected_decision'].title()} · {done}"


sample = st.radio("Which invoice?", list(all_gold), format_func=lambda s: gold.TITLES.get(s, s),
                  captions=[status(s) for s in all_gold], key="sample")
g, previous = all_gold[sample], gold.last_review(sample) or {}
catalog = gold.catalog_for(g)
sponsors, studies, sites = gold.seed("sponsors"), gold.seed("studies"), gold.seed("sites")
ctx = g["context"]

# --- The expected result -----------------------------------------------------------------
with st.container(border=True):
    st.subheader("Expected result")
    st.markdown(f"Sponsor **{sponsors[ctx['sponsor_id']]['name']}**, study **{studies[ctx['study_id']]['name']}**, "
                f"site **{sites[ctx['site_id']]['name']}**.")
    if g["expected_decision"] == "submit":
        st.markdown("**Submit**: every line matches a catalog item at the catalog price.")
    else:
        st.markdown("**Hold**, because of " + ", ".join(gold.REASON_WORDS.get(r, r) for r in g["expected_hold_reasons"]) + ".")
    if g.get("outcome_note"):
        st.caption(g["outcome_note"])
    outcome_verdict = st.radio("Is this the right result?", list(VERDICTS), format_func=VERDICTS.get, horizontal=True,
                               index=list(VERDICTS).index(previous.get("outcome_verdict", "agree")), key=f"{sample}_outcome")
    outcome_comment = st.text_input("Comment on the result (optional)", value=previous.get("outcome_comment", ""),
                                    key=f"{sample}_outcome_comment")
    with st.expander("The invoice as the site sent it", icon=":material/description:"):
        msg = message_from_bytes((gold.ROOT / g["email"]).read_bytes(), policy=policy.default)
        pdf = next((part.get_content() for part in msg.iter_attachments()), None)
        if pdf:
            st.pdf(pdf, height=600, alt=f"{gold.TITLES.get(sample, sample)} as received")

# --- The lines ---------------------------------------------------------------------------
prior = {l["line_no"]: l for l in previous.get("lines", [])}
answers = {}


def describe(code: str | None) -> str:
    return UNMATCHED if code is None else f"{catalog[code]['description']} ({code}, ${catalog[code]['unit_price']})"


def line_card(line: dict, why: str | None) -> None:
    n, p = line["line_no"], prior.get(line["line_no"], {})
    with st.container(border=True):
        st.markdown(f"**Line {n}: {line['description']}** · {line['qty']} × ${line['billed_unit_price']}")
        st.markdown(f"Answer: **{describe(line['expected_item_code'])}**")
        if why:
            st.caption(why)
        verdict = st.radio("Is this answer right?", list(VERDICTS), format_func=VERDICTS.get, horizontal=True,
                           index=list(VERDICTS).index(p.get("verdict", "agree")), key=f"{sample}_{n}_verdict")
        code = None
        if verdict == "change":
            options = [None] + sorted(catalog, key=lambda c: catalog[c]["description"])
            code = st.selectbox("The right item", options, format_func=describe, key=f"{sample}_{n}_code",
                                index=options.index(p["corrected_code"]) if p.get("corrected_code") in options else 0)
        comment = st.text_input("Comment (optional)", value=p.get("comment", ""), key=f"{sample}_{n}_comment")
        answers[n] = {"verdict": verdict, "item_code": code, "comment": comment}


reasons = {line["line_no"]: gold.why_review(line, catalog) for line in g["lines"]}
judgement = [line for line in g["lines"] if reasons[line["line_no"]]]
plain = [line for line in g["lines"] if not reasons[line["line_no"]]]

st.subheader(f"Lines that need your judgement ({len(judgement)})")
if not judgement:
    st.caption("None on this invoice: every line has a clear match at the catalog price.")
for line in judgement:
    line_card(line, reasons[line["line_no"]])
with st.expander(f"The other {len(plain)} lines are straightforward: the names match closely and the price is the "
                 "catalog price. Open to check them."):
    for line in plain:
        line_card(line, None)

# --- Save --------------------------------------------------------------------------------
if st.button("Save review", type="primary", icon=":material/save:", key="save"):
    changed = gold.save_review(sample, reviewer, answers, outcome_verdict, outcome_comment)
    if changed:
        st.success(f"Saved. The answer key now has your answer for line(s) {', '.join(map(str, changed))}.",
                   icon=":material/check:")
    else:
        st.success("Saved. The answer key is unchanged.", icon=":material/check:")
    st.caption("An engineer reruns the eval to score the AI against the answer key (python -m evals.run_eval). "
               "It is not automatic yet; in production it runs in CI on every change to the answer key.")
