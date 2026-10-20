"""ISSUE-009 regression test (recorded after the fact; the first fix was in 98425f5).

Found by: the P1 docs cross-check (2026-10-19): one unreadable .eml in the inbox crashed the worker
loop. The /code-review Spec reviewer (2026-10-20) then found that the set-aside file never became
a Rejected Message, so it vanished from the Reviewer's view (PRD story 4).
"""
from conftest import SIMPLE_EML, make_pipeline
from invoice_assist.worker import poll_once


def test_issue_009_unreadable_email_is_set_aside_recorded_and_the_worker_keeps_going(store, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "01-broken.eml").write_bytes(b"From: x\nDate: not a date at all\n\nbody")
    (inbox / "02-good.eml").write_bytes(SIMPLE_EML.read_bytes())
    pipeline, clinrun = make_pipeline(store)

    assert poll_once(store, pipeline, inbox) == 1
    assert (inbox / "failed" / "01-broken.eml").exists() and len(clinrun.calls) == 1
    rejected = store.rejected_messages()
    assert len(rejected) == 1 and rejected[0]["subject"] == "01-broken.eml"
    assert rejected[0]["rejection_reason"].startswith("Unreadable email")
    assert "inbox/failed/01-broken.eml" in rejected[0]["rejection_reason"]
