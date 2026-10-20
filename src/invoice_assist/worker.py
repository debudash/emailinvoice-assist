"""Worker: polls the inbox folder and processes Invoices one at a time, oldest first."""
import logging
import time
from pathlib import Path

from .config import settings
from .intake import parse_eml
from .pipeline import Pipeline
from .store import Store

log = logging.getLogger("worker")


def ingest(store: Store, path: Path) -> list[int]:
    """Record the Message and its Invoices; returns the new invoice ids."""
    incoming = parse_eml(path)
    message_row = store.add_message(incoming)
    if incoming.rejection_reason:
        log.info("Rejected %s: %s", path.name, incoming.rejection_reason)
    return [store.add_invoice(message_row, a) for a in incoming.invoices]


def poll_once(store: Store, pipeline: Pipeline, inbox: Path) -> int:
    processed_dir = inbox / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(inbox.glob("*.eml"), key=lambda p: p.stat().st_mtime):
        invoice_ids = ingest(store, path)
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
