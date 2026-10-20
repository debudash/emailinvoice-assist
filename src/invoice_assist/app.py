"""Hub entry point: the Invoices page (hub.py) and the Gold review page (gold_review.py).

Run: streamlit run src/invoice_assist/app.py
"""
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent
st.set_page_config(page_title="Invoice hub", page_icon=":material/receipt_long:", layout="wide")

st.navigation([
    st.Page(HERE / "hub.py", title="Invoices", icon=":material/receipt_long:", default=True),
    st.Page(HERE / "gold_review.py", title="Gold review", icon=":material/fact_check:"),
]).run()
