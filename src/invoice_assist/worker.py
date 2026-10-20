"""Worker: polls the inbox folder and processes Invoices one at a time, oldest first."""
import logging
import time
from pathlib import Path

from .config import settings
from .intake import Message, parse_eml
from .pipeline import Pipeline
from .store import Store, now

log = logging.getLogger("worker")


def ingest(store: Store, path: Path) -> list[int]:
    """Record the Message and its Invoices; returns the new invoice ids."""
    incoming = parse_eml(path)
    message_row = store.add_message(incoming)
    if incoming.rejection_reason:
        log.info("Rejected %s: %s", path.name, incoming.rejection_reason)
    return [store.add_invoice(message_row, a) for a in incoming.invoices]


def poll_once(store: Store, pipeline: Pipeline, inbox: Path) -> int:
    processed_dir, failed_dir = inbox / "processed", inbox / "failed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(inbox.glob("*.eml"), key=lambda p: (p.stat().st_mtime, p.name)):
        # ISSUE-009: one unreadable .eml crashed the worker loop, and later, once set aside, it
        # vanished from the Hub. Root cause: parsing errors were not caught per file, and the set-aside
        # file was only logged. Fix: this per-file catch (the worker's error boundary, as the Pipeline
        # is the Stages') moves the file to inbox/failed/ and records it as a Rejected Message, so the
        # worker keeps going and the Reviewer sees it in the Rejected list (PRD story 4).
        try:
            invoice_ids = ingest(store, path)
        except Exception as exc:
            log.exception("Could not read %s; moved to %s", path.name, failed_dir)
            path.rename(failed_dir / path.name)
            store.add_message(Message(message_id="", sender="(unreadable)", subject=path.name, body="",
                                      received_at=now(), rejection_reason=f"Unreadable email ({type(exc).__name__});"
                                      f" the file is in inbox/failed/{path.name}"))
            continue
        path.rename(processed_dir / path.name)
        for invoice_id in invoice_ids:
            log.info("Invoice %s from %s -> %s", invoice_id, path.name, pipeline.process(invoice_id))
            count += 1
    return count


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    store = Store(settings.db_path)
    pipeline = Pipeline(store)
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    log.info("Watching %s every %ss", settings.inbox_dir.resolve(), settings.poll_seconds)
    while True:
        # Operator controls, set from the Hub: pause the poller, or ask for one check now.
        check_now = store.control("check_now") == "1"
        if store.control("paused") != "1" or check_now:
            store.set_control("check_now", "0")
            poll_once(store, pipeline, settings.inbox_dir)
        store.set_control("last_poll", time.strftime("%H:%M:%S"))
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
