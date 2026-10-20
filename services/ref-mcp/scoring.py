"""Pure similarity scoring for ref-mcp search tools (ADR-0003, ADR-0004).

No I/O here: every function takes strings and returns a float in 0..1, rounded to 3 dp,
so the numbers the Hub shows can be unit-tested and tuned against the gold set.
"""

import re

from rapidfuzz import fuzz

# Corporate suffix tokens carry no identity ("Northwind Pharma Inc." is Northwind Pharma).
CORPORATE_SUFFIXES = {"inc", "incorporated", "llc", "ltd", "corp", "corporation", "co", "plc"}

# Spelling variants folded to one token before comparing.
TOKEN_SYNONYMS = {"pharmaceuticals": "pharma", "pharmaceutical": "pharma"}

_PUNCT = re.compile(r"[^\w\s]|_")


def _tokens(text: str) -> list[str]:
    """Lowercase, replace punctuation with spaces, split on whitespace."""
    return _PUNCT.sub(" ", (text or "").lower()).split()


def normalise_name(text: str) -> str:
    """Normalise an organisation, study or site name.

    Site words such as "clinical" or "research" are deliberately kept: the mismatched sample
    relies on a wrong site name staying a weak match.
    """
    tokens = [TOKEN_SYNONYMS.get(t, t) for t in _tokens(text)]
    return " ".join(t for t in tokens if t not in CORPORATE_SUFFIXES)


def normalise_person(text: str) -> str:
    """Normalise a PI name: as a name, minus a leading "dr" title."""
    tokens = _tokens(text)
    if tokens and tokens[0] == "dr":
        tokens = tokens[1:]
    return " ".join(tokens)


def normalise_protocol(text: str) -> str:
    """Normalise a protocol number: case-folded, separators collapsed to single spaces."""
    return " ".join(_tokens(text))


def _score(scorer, a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(scorer(a, b) / 100.0, 3)


def name_score(query: str, candidate: str) -> float:
    """Token-set similarity of two names (word order and extra words tolerated)."""
    return _score(fuzz.token_set_ratio, normalise_name(query), normalise_name(candidate))


def person_score(query: str, candidate: str) -> float:
    """Token-set similarity of two person names (a middle initial is tolerated)."""
    return _score(fuzz.token_set_ratio, normalise_person(query), normalise_person(candidate))


def protocol_score(query: str, candidate: str) -> float:
    """Character-level similarity of two protocol numbers.

    fuzz.ratio, not token_set: a wrong year ("2024" for "2023") must score high but below 1.0.
    """
    return _score(fuzz.ratio, normalise_protocol(query), normalise_protocol(candidate))


def site_rank_score(site_name_score: float, pi_score: float | None) -> float:
    """Ordering key for site candidates; never reported as the site's confidence.

    ADR-0005: Corroboration ranks but cannot lift. A matching PI may reorder candidates (on the
    mismatched sample, "Prairie Clinical Research" scores Willow Creek 0.81 vs Prairie Field 0.78
    on name alone; Dr. Riley Foster puts Prairie Field first), but the site's `score` stays its
    name score, so a weak name can never clear a threshold on PI evidence.
    """
    if pi_score is None:
        return site_name_score
    return round((site_name_score + pi_score) / 2, 3)
