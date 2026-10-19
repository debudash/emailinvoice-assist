# Source documents

Inputs to the project, kept verbatim. Do not edit these; record interpretations and decisions elsewhere in `docs/`.

| File | What it is | Origin |
|------|------------|--------|
| `project-brief.md` | Ledger Run challenge brief / PRD (v1, last updated 2026-10-12) | Provided by the user, 2026-10-19 |
| `starter-readme.md` | Starter repo README: reference API, endpoints, seed data, sample-invoice gradient | `github.com/ledgerrun/ai-takehome-test` @ `7d54910` |
| `sample-invoices/*.pdf` | Simple, medium, large and mismatched-metadata sample invoices | Same starter repo, `sample-invoices/` |

Note: the brief and the starter README disagree on the human gate. The starter README makes user
confirmation of metadata a hard gate before line-item matching; the brief says humans are *not* a
required gate and QC happens after the AI decision. The brief is the newer document.
