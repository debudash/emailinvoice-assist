"""Intake: turn one inbox .eml file into a Message with its Invoice files (GLOSSARY.md)."""
import email
import hashlib
from dataclasses import dataclass, field
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

INVOICE_TYPES = {"application/pdf", "image/png", "image/jpeg"}


@dataclass
class InvoiceFile:
    filename: str
    media_type: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass
class Message:
    message_id: str
    sender: str
    subject: str
    body: str
    received_at: str
    invoices: list[InvoiceFile] = field(default_factory=list)
    rejection_reason: str | None = None
    source: str = "inbox"  # or "upload": a file a Reviewer added in the Hub


def parse_eml(path: Path) -> Message:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    body_part = msg.get_body(preferencelist=("plain",))
    received = msg["Date"]
    incoming = Message(
        message_id=(msg["Message-ID"] or path.name).strip("<>"),
        sender=str(msg["From"] or ""),
        subject=str(msg["Subject"] or ""),
        body=body_part.get_content() if body_part else "",
        received_at=parsedate_to_datetime(received).isoformat() if received else "",
        source=str(msg["X-Invoice-Source"] or "inbox"),
    )
    for part in msg.iter_attachments():
        if part.get_content_type() in INVOICE_TYPES:
            incoming.invoices.append(InvoiceFile(part.get_filename() or "invoice",
                                                part.get_content_type(), part.get_content()))
    if not incoming.invoices:
        incoming.rejection_reason = "No PDF or image attachment"
    return incoming


def write_upload(inbox: Path, filename: str, media_type: str, data: bytes, uploaded_by: str) -> Path:
    """A file a Reviewer added in the Hub becomes a Message in the inbox, marked source=upload."""
    from datetime import datetime, timezone
    from email.message import EmailMessage
    from email.utils import format_datetime, make_msgid
    msg = EmailMessage()
    msg["From"], msg["Subject"] = uploaded_by, f"Uploaded in the Hub: {filename}"
    msg["Date"], msg["Message-ID"] = format_datetime(datetime.now(timezone.utc)), make_msgid(domain="hub.local")
    msg["X-Invoice-Source"] = "upload"
    msg.set_content(f"Uploaded by {uploaded_by}.")
    maintype, subtype = media_type.split("/")
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"upload-{datetime.now():%Y%m%d%H%M%S}-{filename}.eml"
    path.write_bytes(bytes(msg))
    return path
