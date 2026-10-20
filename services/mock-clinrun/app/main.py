"""mock-clinrun: a stand-in for ClinRun, the sponsor payment backend (ADR 0011).

One idea worth showing: idempotent submission. Every POST carries an Idempotency-Key;
repeating a key returns the ORIGINAL ClinRun ID instead of an error or a second row,
so retries and reruns can never submit an invoice twice.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel


# --- Contract (docs/prd.md "Contracts" -> ClinRun submission) -----------------------------

class Invoice(BaseModel):
    number: str
    date: date
    currency: Literal["USD"]
    total: float


class Context(BaseModel):
    sponsor_id: int
    study_id: int
    site_id: int


class Line(BaseModel):
    catalog_item_id: int | None
    item_code: str | None
    description_as_billed: str
    qty: float
    unit_price: float
    amount: float
    price_variance: bool


class Decision(BaseModel):
    rationale: str
    straight_through: bool


class Release(BaseModel):
    reason: str
    reviewer: str


class Source(BaseModel):
    message_id: str
    received_at: str


class Submission(BaseModel):
    invoice: Invoice
    context: Context
    lines: list[Line]
    decision: Decision
    release: Release | None
    source: Source


# --- Storage: one SQLite file, stdlib sqlite3, no ORM -------------------------------------

@contextmanager
def db():
    """Open the DB (creating file and table on first use), commit on success, always close."""
    path = Path(os.environ.get("CLINRUN_DB", "/data/clinrun.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS submissions (
               id              INTEGER PRIMARY KEY AUTOINCREMENT,
               clinrun_id      TEXT UNIQUE,
               idempotency_key TEXT UNIQUE NOT NULL,
               received_at     TEXT NOT NULL,
               submission      TEXT NOT NULL)"""
    )
    try:
        with conn:  # transaction: commit or roll back
            yield conn
    finally:
        conn.close()


def as_record(row: sqlite3.Row) -> dict:
    return {
        "clinrun_id": row["clinrun_id"],
        "idempotency_key": row["idempotency_key"],
        "received_at": row["received_at"],
        "submission": json.loads(row["submission"]),
    }


# --- API ----------------------------------------------------------------------------------

app = FastAPI(title="mock-clinrun")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/submissions", status_code=201)
def submit(
    body: Submission,
    response: Response,
    idempotency_key: str | None = Header(default=None),
):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")

    with db() as conn:
        existing = conn.execute(
            "SELECT clinrun_id FROM submissions WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        if existing:
            # The idempotency rule: same key -> same ClinRun ID, no second row.
            response.status_code = 200
            return {"clinrun_id": existing["clinrun_id"], "status": "accepted", "duplicate": True}

        cur = conn.execute(
            "INSERT INTO submissions (idempotency_key, received_at, submission) VALUES (?, ?, ?)",
            (
                idempotency_key,
                datetime.now(timezone.utc).isoformat(),
                body.model_dump_json(),
            ),
        )
        clinrun_id = f"CR-{cur.lastrowid:06d}"
        conn.execute("UPDATE submissions SET clinrun_id = ? WHERE id = ?", (clinrun_id, cur.lastrowid))

    return {"clinrun_id": clinrun_id, "status": "accepted", "duplicate": False}


@app.get("/submissions")
def list_submissions():
    with db() as conn:
        rows = conn.execute("SELECT * FROM submissions ORDER BY id DESC").fetchall()
    return [as_record(r) for r in rows]


@app.get("/submissions/{clinrun_id}")
def get_submission(clinrun_id: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM submissions WHERE clinrun_id = ?", (clinrun_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Unknown ClinRun ID {clinrun_id}")
    return as_record(row)
