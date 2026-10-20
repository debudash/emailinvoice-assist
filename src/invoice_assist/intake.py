"""Intake: turn one inbox .eml file into a Message with its invoice files."""
import email
import hashlib
from dataclasses import dataclass, field
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

INVOICE_TYPES = {"application/pdf"}  # images arrive in P1


@dataclass
class Attachment:
    filename: str
    media_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass
class IncomingMessage:
    message_id: str
    sender: str
    subject: str
    body: str
    received_at: str
    invoices: list[Attachment] = field(default_factory=list)
    rejection_reason: str | None = None


def parse_eml(path: Path) -> IncomingMessage:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    body_part = msg.get_body(preferencelist=("plain",))
    received = msg["Date"]
    incoming = IncomingMessage(
        message_id=(msg["Message-ID"] or path.name).strip("<>"),
        sender=str(msg["From"] or ""),
        subject=str(msg["Subject"] or ""),
        body=body_part.get_content() if body_part else "",
        received_at=parsedate_to_datetime(received).isoformat() if received else "",
    )
    for part in msg.iter_attachments():
        if part.get_content_type() in INVOICE_TYPES:
            incoming.invoices.append(Attachment(part.get_filename() or "invoice.pdf",
                                                part.get_content_type(), part.get_content()))
    if not incoming.invoices:
        incoming.rejection_reason = "No PDF attachment"
    return incoming
