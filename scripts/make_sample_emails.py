"""Wrap the four sample invoice PDFs in realistic .eml Messages.

Usage: python scripts/make_sample_emails.py [out_dir]   (default: samples/emails)
Copy the generated files into the inbox folder to have the worker pick them up.
"""
import sys
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDFS = ROOT / "sample-invoices"

SAMPLES = [
    ("simple-invoice.pdf", "billing@willowcreekcr.org", "Invoice INV-2024-001 - CATALYST Trial",
     "Hello,\n\nPlease find attached our invoice for the CATALYST Trial (March).\n\nThanks,\nWillow Creek Accounts"),
    ("medium-invoice.pdf", "ap@harborviewmed.org", "LUMIN-2024 invoice attached",
     "Hi team,\n\nAttached is invoice INV-2024-042 for LUMIN-2024 visits in June.\n\nRegards,\nHarborview Research Billing"),
    ("large-invoice.pdf", "research.finance@highlandridge.org", "Q3 invoice - Highland Ridge / LUMIN",
     "Good afternoon,\n\nOur Q3 invoice is attached, including patient reimbursements.\n\nHighland Ridge Research Unit"),
    ("mismatched-metadata-invoice.pdf", "office@prairieclinical.com", "Invoice for VERITAS study",
     "Hello,\n\nAttached is our invoice for the VERITAS Phase 2 study.\n\nPrairie Clinical Research"),
]


def build(pdf: str, sender: str, subject: str, body: str, sent: datetime) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, "invoices@sponsor-ap.example", subject
    msg["Date"], msg["Message-ID"] = format_datetime(sent), make_msgid(domain="sample.local")
    msg.set_content(body)
    msg.add_attachment((PDFS / pdf).read_bytes(), maintype="application", subtype="pdf", filename=pdf)
    return msg


def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (pdf, sender, subject, body) in enumerate(SAMPLES):
        sent = datetime(2026, 10, 19, 9, i * 5, tzinfo=timezone.utc)
        path = out_dir / f"{i + 1:02d}-{pdf.removesuffix('.pdf')}.eml"
        path.write_bytes(bytes(build(pdf, sender, subject, body, sent)))
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "samples" / "emails")
