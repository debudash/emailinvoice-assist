import json, re, sys
from decimal import Decimal
root = sys.argv[1]
cat = json.load(open(f"{root}/services/api/seed/data/catalog_items.json"))
links = {(l["study_id"], l["site_id"]) for l in json.load(open(f"{root}/services/api/seed/data/study_sites.json"))}
src = open(f"{root}/scripts/generate_sample_invoices.py").read()
# pull line_items per invoice from generator, in order
blocks = re.findall(r'write_invoice\(\s*"([\w-]+)-invoice\.pdf".*?line_items=\[(.*?)\],', src, re.S)
items = {k: re.findall(r'\("([^"]+)",\s*(\d+),\s*"([\d.]+)"\)', v) for k, v in blocks}

S = {
 "simple": dict(email="01", ctx=(2,3,1), conf=True, labels={
   "Site Management Fee": ["ADMIN-SITE"], "Screening Visit": ["VISIT-SCR"], "Baseline Visit": ["VISIT-BL"],
   "Complete Blood Count": ["LAB-CBC"], "IV Infusion Administration": ["PROC-INFUS"]},
   dec="submit", reasons=[], notes="Contoso / CATALYST Trial (study 3) at Willow Creek (site 1, linked). Light wording variation only ('Site Management Fee' -> ADMIN-SITE 'Site Fee'); every price equals the catalog. Clean Submit."),
 "medium": dict(email="02", ctx=(1,1,2), conf=True, labels={
   "Site Administration Fee": ["ADMIN-SITE"], "Screening Visit": ["VISIT-SCR"], "Baseline Assessment": ["VISIT-BL"],
   "Week 4 Follow-up": ["VISIT-WK4"], "Week 8 Follow-up": ["VISIT-WK8"], "12-Lead ECG": ["PROC-ECG"], "CBC": ["LAB-CBC"],
   "CMP": ["LAB-CMP"], "Drug Infusion": ["PROC-INFUS"], "PK Blood Draw": ["PROC-PK"], "IRB/Ethics Fees": ["ADMIN-IRB"]},
   dec="hold", reasons=["price_variance"], notes="Northwind / LUMIN-2024 (study 1) at Harborview (site 2, linked). Fuzzy wording but each line has one clear item. 'Week N Follow-up' is the week-specific visit (VISIT-WK4/WK8 at 475, matching price), not generic VISIT-FU (400). Only anomaly: IRB/Ethics Fees $550 vs ADMIN-IRB $500."),
 "large": dict(email="03", ctx=(1,1,3), conf=True, labels={
   "Site Admin": ["ADMIN-SITE"], "Screening Visit": ["VISIT-SCR"], "Baseline Visit": ["VISIT-BL"], "Wk 4 Visit": ["VISIT-WK4"],
   "Wk 8 Visit": ["VISIT-WK8"], "Week 12 Visit": ["VISIT-WK12"], "Week 16 Visit": ["VISIT-WK16"], "Wk 24 Visit": ["VISIT-WK24"],
   "End of Study Visit": ["VISIT-EOS"], "ECG": ["PROC-ECG"], "Vitals": ["PROC-VITAL"], "Physical Exam": ["PROC-PHYS"],
   "IV Drug Administration": ["PROC-INFUS"], "Pharmacokinetic Sampling": ["PROC-PK"], "CBC w/ Differential": ["LAB-CBC"],
   "Comprehensive Metabolic Panel": ["LAB-CMP"], "UA": ["LAB-URINAL"], "Hepatic Function Panel": ["LAB-LFT"], "Lipid Panel": ["LAB-LIPID"],
   "CT Scan - Chest/Abdomen": ["IMG-CT"], "IRB Annual Maintenance": ["ADMIN-IRB"],
   "Drug Shipping (cold chain)": ["PASS-COLD", "PASS-SHIP"],
   "Lab Supplies": ["PASS-KIT"], "Sample Transport": ["PASS-SPEC"],
   "Parking Reimbursement": None, "Patient Stipend": None, "Translator Services": None},
   dec="hold", reasons=["unmatched", "ambiguous", "price_variance"], notes="Northwind / LUMIN-2024 (study 1) at Highland Ridge (site 3, linked). Three Unmatched patient-reimbursement/service lines (Parking, Stipend, Translator: nothing like them in the catalog). One Ambiguous line: 'Drug Shipping (cold chain)' fits PASS-COLD 'Cold Chain Shipping' ($125, price matches) and PASS-SHIP 'Study Drug Shipping' ($75); expected is PASS-COLD (description + price tie-break) but per decisions.md price as tie-break still leaves it Ambiguous. One Price Variance: CT Scan $475 vs IMG-CT $450. Judgement calls: 'Lab Supplies' -> PASS-KIT 'Lab Kit - Standard' and 'Sample Transport' -> PASS-SPEC 'Specimen Shipping' are fuzzy but price-exact single candidates, so labelled matched (not ambiguous, not unmatched); 'Hepatic Function Panel' -> LAB-LFT (synonym, price-exact). 'ECG' -> PROC-ECG not PROC-ECG-Read, and 'IV Drug Administration' -> PROC-INFUS not PROC-IV (IV Placement): the alternatives are different services and the price agrees, so not marked ambiguous - reviewer may wish to revisit."),
 "mismatched-metadata": dict(email="04", ctx=(1,2,6), conf=False, labels={
   "Site Admin Fee": ["ADMIN-SITE"], "Screening": ["VISIT-SCR"], "Baseline": ["VISIT-BL"], "Month 3 Follow-up": ["VISIT-MONTH3"],
   "ECG": ["PROC-ECG"], "CBC": ["LAB-CBC"], "Lipid Profile": ["LAB-LIPID"]},
   dec="hold", reasons=["context_uncertain"], notes="True context: Northwind / VERITAS (study 2) at Prairie Field Research Group (site 6, linked). Header is fuzzy: site 'Prairie Clinical Research' matches no seeded site, sponsor 'Northwind Pharmaceuticals Inc.', study 'VERITAS Phase 2 Study', protocol printed NWD-VER-2024-002 vs seeded NWD-VER-2023-002. Expected first pass: Hold for uncertain Context, matching skipped. Lines are labelled against the true VERITAS catalog for the post-Correction run: all clean, prices equal catalog, so after Correction the invoice should Submit."),
}
# Plain-language notes for the subject matter expert (Hub > Gold review): why a line, or the
# expected outcome, is a judgement call. Lines that are Unmatched, Ambiguous or a Price Variance
# are explained by the page itself.
WEEK = "The week-specific visit, not the generic Follow-up visit ($400); the billed price matches it."
REVIEW_NOTES = {
 "medium": {4: WEEK, 5: WEEK},
 "large": {
   10: "Two ECG items exist: 'ECG - 12 Lead' and 'ECG Interpretation' ($55). The billed price matches the 12-lead ECG.",
   13: "'IV Placement' ($65) is a different service; the billed price matches the infusion.",
   18: "Another name for the liver function tests; the billed price matches.",
   23: "Loose wording; 'Lab Kit - Standard' is the only close item and the billed price matches.",
   24: "Loose wording; 'Specimen Shipping' is the only close item and the billed price matches."},
}
OUTCOME_NOTES = {
 "mismatched-metadata": "The sponsor, protocol and site printed on the header don't match the reference data, so the "
                        "AI should hold for an uncertain Context. Once a Reviewer corrects the Context (Northwind / "
                        "VERITAS / Prairie Field), every line matches and it should submit.",
}
for name, s in S.items():
    sp, st, si = s["ctx"]
    assert (st, si) in links, name
    catalog = {c["item_code"]: c for c in cat if c["sponsor_id"] == sp and c["study_id"] == st}
    lines = []
    printed = items[name]
    assert [d for d, _, _ in printed] == list(s["labels"]), (name, [d for d,_,_ in printed])
    for i, (desc, qty, price) in enumerate(printed, 1):
        codes = s["labels"][desc]
        if codes:
            for c in codes: assert c in catalog, (name, c)
            exp = codes[0]
            var = Decimal(price) != Decimal(catalog[exp]["unit_price"])
        else:
            exp, var = None, False
        line = {"line_no": i, "description": desc, "qty": int(qty), "billed_unit_price": price,
                "expected_item_code": exp, "acceptable_item_codes": codes or [None],
                "ambiguous": bool(codes and len(codes) > 1), "price_variance": var}
        if i in REVIEW_NOTES.get(name, {}):
            line["review_note"] = REVIEW_NOTES[name][i]
        lines.append(line)
    out = {"sample": name, "email": f"samples/emails/{s['email']}-{name}-invoice.eml",
           "context": {"sponsor_id": sp, "study_id": st, "site_id": si},
           "context_should_be_confident": s["conf"], "lines": lines,
           "expected_decision": s["dec"], "expected_hold_reasons": s["reasons"], "notes": s["notes"]}
    if name in OUTCOME_NOTES:
        out["outcome_note"] = OUTCOME_NOTES[name]
    json.dump(out, open(f"{root}/evals/gold/{name}.json", "w", newline="\n"), indent=2)
    open(f"{root}/evals/gold/{name}.json", "a").write("\n")
    print(name, [(l["line_no"], l["expected_item_code"], "A" if l["ambiguous"] else "", "V" if l["price_variance"] else "") for l in lines])
