"""Matching Stage: every Line Item against the whole scoped Catalog in one call (ADR-0006)."""
import json

from . import llm
from .models import LineItem, Matching

SYSTEM = """You match clinical trial invoice Line Items to a sponsor's Catalog for one study.
For each line, choose the single Catalog Item that bills the same service, allowing for
site shorthand, abbreviations and rewording (e.g. "CBC" = "Complete Blood Count").
Rules:
- Only use Catalog Items from the list given. Never invent an item.
- If no item bills the same service, set catalog_item_id and item_code to null (Unmatched).
- If more than one item is plausible, pick the best, set ambiguous=true and list the others
  in alternatives. Price may be used as evidence for the best pick, but a line that needed
  price to decide is still ambiguous.
- confidence: high = clearly the same service; medium = probable; low = a guess.
- Do not judge whether the price is correct; a separate check does that.
- reason: one short sentence."""


def match(lines: list[LineItem], catalog: list[dict]) -> Matching:
    payload = {
        "catalog": [{k: item[k] for k in ("id", "item_code", "description", "category", "unit_price")}
                    for item in catalog],
        "line_items": [line.model_dump() for line in lines],
    }
    return llm.parse(Matching, SYSTEM, [{"type": "text", "text": json.dumps(payload)}],
                     effort="high")
