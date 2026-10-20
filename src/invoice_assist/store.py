"""Store: the app's SQLite file. Stage Runs and Actions are append-only."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, message_id TEXT, source TEXT, sender TEXT, subject TEXT,
    body TEXT, received_at TEXT, rejection_reason TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY, message_id INTEGER REFERENCES messages(id), filename TEXT,
    media_type TEXT, sha256 TEXT, data BLOB, version INTEGER DEFAULT 1, status TEXT,
    failed_stage TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS stage_runs (
    id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), version INTEGER,
    stage TEXT, run_no INTEGER, trigger TEXT, outcome TEXT, inputs TEXT, output TEXT, error TEXT,
    served_by TEXT, attempts INTEGER, started_at TEXT, ended_at TEXT);
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), version INTEGER,
    clinrun_id TEXT, idempotency_key TEXT, sent_at TEXT);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id), actor TEXT, kind TEXT,
    note TEXT, before TEXT, after TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS control (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")  # the Hub reads while the worker writes
        self.db.executescript(SCHEMA)

    # --- writes ---------------------------------------------------------------
    def add_message(self, m) -> int:
        cur = self.db.execute(
            "INSERT INTO messages (message_id, source, sender, subject, body, received_at, rejection_reason, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (m.message_id, m.source, m.sender, m.subject, m.body, m.received_at, m.rejection_reason, now()))
        self.db.commit()
        return cur.lastrowid

    def add_invoice(self, message_row_id: int, a) -> int:
        cur = self.db.execute(
            "INSERT INTO invoices (message_id, filename, media_type, sha256, data, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (message_row_id, a.filename, a.media_type, a.sha256, a.data, "Received", now(), now()))
        self.db.commit()
        return cur.lastrowid

    def set_status(self, invoice_id: int, status: str, failed_stage: str | None = None):
        self.db.execute("UPDATE invoices SET status=?, failed_stage=?, updated_at=? WHERE id=?",
                        (status, failed_stage, now(), invoice_id))
        self.db.commit()

    def add_stage_run(self, invoice_id: int, version: int, stage: str, trigger: str, outcome: str,
                      inputs: dict, output: dict | None, error: str | None, served_by: list[str],
                      started_at: str, attempts: int = 1) -> int:
        """inputs: the Stage Run ids this run read from, so any Decision can be rebuilt from its rows."""
        run_no = self.db.execute("SELECT COUNT(*) FROM stage_runs WHERE invoice_id=? AND version=? AND stage=?",
                                 (invoice_id, version, stage)).fetchone()[0] + 1
        cur = self.db.execute(
            "INSERT INTO stage_runs (invoice_id, version, stage, run_no, trigger, outcome, inputs, output, error,"
            " served_by, attempts, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (invoice_id, version, stage, run_no, trigger, outcome, json.dumps(inputs),
             json.dumps(output) if output is not None else None, error, ",".join(served_by), attempts,
             started_at, now()))
        self.db.commit()
        return cur.lastrowid

    def add_submission(self, invoice_id: int, version: int, clinrun_id: str, key: str):
        self.db.execute("INSERT INTO submissions (invoice_id, version, clinrun_id, idempotency_key, sent_at)"
                        " VALUES (?,?,?,?,?)", (invoice_id, version, clinrun_id, key, now()))
        self.db.commit()

    def add_action(self, invoice_id: int, actor: str, kind: str, note: str, before=None, after=None):
        self.db.execute("INSERT INTO actions (invoice_id, actor, kind, note, before, after, at) VALUES (?,?,?,?,?,?,?)",
                        (invoice_id, actor, kind, note, json.dumps(before), json.dumps(after), now()))
        self.db.commit()

    def set_control(self, key: str, value: str):
        self.db.execute("INSERT INTO control (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value))
        self.db.commit()

    def control(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # --- reads ----------------------------------------------------------------
    def actions(self, invoice_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM actions WHERE invoice_id=? ORDER BY id", (invoice_id,)).fetchall()

    def invoice(self, invoice_id: int) -> sqlite3.Row:
        return self.db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()

    def message_for(self, invoice_id: int) -> sqlite3.Row:
        return self.db.execute("SELECT m.* FROM messages m JOIN invoices i ON i.message_id=m.id WHERE i.id=?",
                               (invoice_id,)).fetchone()

    def latest_run(self, invoice_id: int, stage: str) -> sqlite3.Row | None:
        """The latest successful Stage Run of the Invoice's current version."""
        return self.db.execute(
            "SELECT s.* FROM stage_runs s JOIN invoices i ON i.id=s.invoice_id"
            " WHERE s.invoice_id=? AND s.version=i.version AND s.stage=? AND s.outcome='succeeded'"
            " ORDER BY s.id DESC LIMIT 1", (invoice_id, stage)).fetchone()

    def latest_output(self, invoice_id: int, stage: str) -> dict | None:
        row = self.latest_run(invoice_id, stage)
        return json.loads(row["output"]) if row and row["output"] else None

    def stage_runs(self, invoice_id: int) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM stage_runs WHERE invoice_id=? ORDER BY id", (invoice_id,)).fetchall()

    def submission(self, invoice_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM submissions WHERE invoice_id=? ORDER BY id DESC LIMIT 1",
                               (invoice_id,)).fetchone()

    def invoices(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT i.id, i.filename, i.status, i.failed_stage, i.updated_at, m.sender, m.subject"
            " FROM invoices i JOIN messages m ON m.id=i.message_id ORDER BY i.id DESC").fetchall()

    def rejected_messages(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM messages WHERE rejection_reason IS NOT NULL ORDER BY id DESC").fetchall()
