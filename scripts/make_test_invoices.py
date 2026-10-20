"""Generate test invoices (PDF, optional PNG) wrapped in .eml Messages, with labels.

Each scenario is built from the seed reference data, so its expected outcome is true by
construction. Output per scenario in samples/generated/<name>/: invoice.pdf (and invoice.png for
image scenarios), message.eml, and gold.json in the same shape as evals/gold/.

    python scripts/make_test_invoices.py                 # every scenario
    python scripts/make_test_invoices.py price-variance  # one or more by name
    python scripts/make_test_invoices.py --list
Then run them with scripts/run_scenarios.py, or copy the .eml files into inbox/ and watch the Hub.
"""
import json
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "services" / "api" / "seed" / "data"
OUT = ROOT / "samples" / "generated"


def load(name):
    return json.loads((SEED / f"{name}.json").read_text(encoding="utf-8"))


SPONSORS = {r["id"]: r for r in load("sponsors")}
STUDIES = {r["id"]: r for r in load("studies")}
SITES = {r["id"]: r for r in load("sites")}
CATALOG = load("catalog_items")


def item(study_id: int, code: str) -> dict:
    return next(c for c in CATALOG if c["study_id"] == study_id and c["item_code"] == code)


def line(study_id, code, qty, description=None, price=None, amount=None):
    """A billed line from a Catalog Item; override description/price/amount to plant an anomaly."""
    it = item(study_id, code)
    unit = float(price if price is not None else it["unit_price"])
    return {"description": description or it["description"], "qty": qty, "unit_price": unit,
            "amount": amount if amount is not None else round(qty * unit, 2), "code": code,
            "variance": price is not None and float(price) != float(it["unit_price"])}


def extra(description, qty, price):
    """A billed line with no Catalog Item (Unmatched)."""
    return {"description": description, "qty": qty, "unit_price": price, "amount": round(qty * price, 2),
            "code": None, "variance": False}


# name: (what it tests, study_id, site_id, header overrides, lines, total override, attachment, decision, reasons)
SCENARIOS = {
    "clean-catalyst": ("Clean invoice, exact catalog wording and prices", 3, 1, {},
                       [line(3, "ADMIN-SITE", 1), line(3, "VISIT-SCR", 2), line(3, "LAB-CBC", 2)],
                       None, "pdf", "submit", []),
    "clean-summit": ("Clean invoice for another sponsor and study", 5, 6, {},
                     [line(5, "VISIT-SCR", 3), line(5, "VISIT-BL", 2), line(5, "LAB-HBA1C", 4)],
                     None, "pdf", "submit", []),
    "reworded": ("Site shorthand for every line; prices exact", 3, 3, {},
                 [line(3, "ADMIN-SITE", 1, "Site Mgmt Fee"), line(3, "VISIT-SCR", 2, "Scr Visit"),
                  line(3, "LAB-CBC", 3, "Complete Blood Count"), line(3, "PROC-INFUS", 2, "IV infusion admin")],
                 None, "pdf", "submit", []),
    "price-variance": ("One line billed above the catalog price", 3, 1, {},
                       [line(3, "ADMIN-SITE", 1), line(3, "VISIT-BL", 1, price=600)],
                       None, "pdf", "hold", ["price_variance"]),
    "zero-priced-billed": ("A $0.00 catalog item billed at a price ($0.00 taken literally)", 1, 2, {},
                           [line(1, "VISIT-SCR", 1), line(1, "PASS-DEVICE", 1, "Study device (pass-through)", price=300)],
                           None, "pdf", "hold", ["price_variance"]),
    "unmatched": ("A charge with no Catalog Item", 3, 1, {},
                  [line(3, "VISIT-SCR", 1), extra("Taxi voucher for subject", 2, 40)],
                  None, "pdf", "hold", ["unmatched"]),
    "wrong-total": ("Printed total does not equal the sum of the lines", 3, 1, {},
                    [line(3, "VISIT-SCR", 1), line(3, "LAB-CBC", 1)], 999.0, "pdf", "hold", ["arithmetic"]),
    "bad-line-math": ("A line amount that is not quantity x unit price", 3, 1, {},
                      [line(3, "VISIT-SCR", 2, amount=900.0), line(3, "LAB-CBC", 1)], None, "pdf", "hold", ["arithmetic"]),
    "site-not-linked": ("A real site that is not on this study", 3, 8, {},
                        [line(3, "VISIT-SCR", 1)], None, "pdf", "hold", ["site_not_linked"]),
    "unknown-site": ("A site name that matches no record", 3, 1, {"site": "Lakeshore Trials Clinic", "pi": "Dr. Pat Lee"},
                     [line(3, "VISIT-SCR", 1)], None, "pdf", "hold", ["context_uncertain"]),
    "image-invoice": ("A clean invoice sent as a PNG image", 3, 1, {},
                      [line(3, "ADMIN-SITE", 1), line(3, "VISIT-SCR", 1)], None, "png", "hold", ["extraction_unverifiable"]),
    "no-attachment": ("An email with no invoice file", 3, 1, {}, [], None, "none", "rejected", []),
}


def render_pdf(path: Path, number: str, date: str, header: dict, lines: list, total: float):
    styles = getSampleStyleSheet()
    rows = [["Description", "Qty", "Unit Price", "Amount"]] + [
        [l["description"], f"{l['qty']:g}", f"${l['unit_price']:,.2f}", f"${l['amount']:,.2f}"] for l in lines]
    table = Table(rows, colWidths=[260, 50, 90, 90])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
    story = [Paragraph("Clinical Trial Site Invoice", styles["Title"]),
             Paragraph(f"Invoice #: {number}<br/>Date: {date}", styles["Normal"]), Spacer(1, 8),
             Paragraph(f"From: {header['site']}<br/>Principal Investigator: {header['pi']}", styles["Normal"]),
             Spacer(1, 8),
             Paragraph(f"Study: {header['study']}<br/>Protocol: {header['protocol']}<br/>Sponsor: {header['sponsor']}",
                       styles["Normal"]),
             Spacer(1, 12), table, Spacer(1, 12), Paragraph(f"<b>Total: ${total:,.2f}</b>", styles["Normal"])]
    SimpleDocTemplate(str(path), pagesize=letter).build(story)


def build(name: str, index: int) -> Path:
    what, study_id, site_id, overrides, lines, total_override, attach, decision, reasons = SCENARIOS[name]
    study, site = STUDIES[study_id], SITES[site_id]
    header = {"sponsor": SPONSORS[study["sponsor_id"]]["name"], "study": study["name"],
              "protocol": study["protocol_number"], "site": site["name"], "pi": site.get("pi_name") or "",
              **overrides}
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    number, date = f"TST-{2026_000 + index}", "2026-10-01"
    total = total_override if total_override is not None else round(sum(l["amount"] for l in lines), 2)

    msg = EmailMessage()
    msg["From"], msg["To"] = f"billing@{site['name'].split()[0].lower()}.example", "invoices@sponsor-ap.example"
    msg["Subject"] = f"Invoice {number} - {study['name']}" if attach != "none" else "Invoice attached (see below)"
    msg["Date"] = format_datetime(datetime(2026, 10, 20, 9, index, tzinfo=timezone.utc))
    msg["Message-ID"] = make_msgid(domain="generated.local")
    msg.set_content(f"Hello,\n\nPlease find our invoice {number} attached.\n\n{header['site']}\n")
    if attach != "none":
        pdf = folder / "invoice.pdf"
        render_pdf(pdf, number, date, header, lines, total)
        if attach == "png":
            import pdfplumber
            with pdfplumber.open(pdf) as doc:
                doc.pages[0].to_image(resolution=110).save(folder / "invoice.png")
            msg.add_attachment((folder / "invoice.png").read_bytes(), maintype="image", subtype="png", filename=f"{number}.png")
        else:
            msg.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=f"{number}.pdf")
    eml = folder / "message.eml"
    eml.write_bytes(bytes(msg))

    gold = {
        "sample": name, "what": what, "email": str(eml.relative_to(ROOT)).replace("\\", "/"),
        "context": {"sponsor_id": study["sponsor_id"], "study_id": study_id, "site_id": site_id},
        "context_should_be_confident": "context_uncertain" not in reasons,
        "lines": [{"line_no": i, "description": l["description"], "expected_item_code": l["code"],
                   "acceptable_item_codes": [l["code"]], "ambiguous": False, "price_variance": l["variance"]}
                  for i, l in enumerate(lines, start=1)],
        "expected_decision": decision, "expected_hold_reasons": reasons,
        "notes": f"Generated by scripts/make_test_invoices.py: {what}",
    }
    (folder / "gold.json").write_text(json.dumps(gold, indent=2), encoding="utf-8")
    return folder


def main(args: list[str]):
    if "--list" in args:
        for name, spec in SCENARIOS.items():
            print(f"{name:<20} {spec[7]:<8} {', '.join(spec[8]) or '-':<26} {spec[0]}")
        return
    names = args or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        sys.exit(f"Unknown scenario(s): {', '.join(unknown)}. Use --list.")
    for name in names:
        print("wrote", build(name, list(SCENARIOS).index(name)).relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1:])
