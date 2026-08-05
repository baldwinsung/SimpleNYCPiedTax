#!/usr/bin/env python3
"""Address normalization shared by build_db.py (indexing) and search.py (querying).

The roll's address fields are inconsistent: "EAST 7 STREET" and "EAST 7TH STREET"
both appear, street types are sometimes doubled-spaced, and people type "E 72 ST"
when the data says "EAST 72 STREET". Both the index and the query run through
`normalize()`, so the two sides always agree -- even where the normalization is
arguably "wrong" (e.g. ST NICHOLAS AVENUE -> STREET NICHOLAS AVENUE), it is wrong
identically on both sides and still matches.
"""
import re

# Abbreviation -> canonical form. Only entries where FTS prefix matching would
# not already do the job need to be here (e.g. "ST"* already matches STREET),
# but listing them explicitly keeps both sides symmetric.
STREET_TYPES = {
    "ST": "STREET", "STR": "STREET", "STRT": "STREET",
    "AVE": "AVENUE", "AV": "AVENUE", "AVEN": "AVENUE",
    "BLVD": "BOULEVARD", "BLV": "BOULEVARD", "BVD": "BOULEVARD",
    "RD": "ROAD", "DR": "DRIVE", "PL": "PLACE", "LN": "LANE",
    "CT": "COURT", "CIR": "CIRCLE", "SQ": "SQUARE", "PLZ": "PLAZA",
    "TER": "TERRACE", "TERR": "TERRACE", "WY": "WAY",
    "PKWY": "PARKWAY", "PKY": "PARKWAY", "PWY": "PARKWAY",
    "TPKE": "TURNPIKE", "TPK": "TURNPIKE", "HWY": "HIGHWAY",
    "EXPY": "EXPRESSWAY", "EXPWY": "EXPRESSWAY", "BRDG": "BRIDGE",
}

DIRECTIONS = {
    "E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH",
    "NE": "NORTHEAST", "NW": "NORTHWEST", "SE": "SOUTHEAST", "SW": "SOUTHWEST",
}

_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)$")
_NONWORD = re.compile(r"[^A-Z0-9]+")


def normalize(text: str) -> str:
    """Uppercase, strip punctuation, drop ordinal suffixes, expand abbreviations.

    >>> normalize("E. 7th St")
    'EAST 7 STREET'
    >>> normalize("CENTRAL  PARK SOUTH")
    'CENTRAL PARK SOUTH'
    """
    if not text:
        return ""
    out = []
    for tok in _NONWORD.sub(" ", text.upper()).split():
        # 7TH -> 7 must happen before ST -> STREET, or "1ST" becomes "1 STREET"
        m = _ORDINAL.match(tok)
        if m:
            out.append(m.group(1))
            continue
        out.append(DIRECTIONS.get(tok) or STREET_TYPES.get(tok) or tok)
    return " ".join(out)


INDEX_COLUMNS = ("STREET_NAME", "CITYNAME", "ZIP_CODE")


def index_text(row: dict) -> str:
    """Normalized searchable address text for a roll row.

    House numbers and apartment numbers are deliberately excluded. Both are
    small integers that collide badly with street numbers if thrown into the
    same token soup -- searching "E 7th St" would match "789 EAST 160 STREET #7"
    on the apartment. They are matched as separate fields instead (see
    search.housenum_sql and the apt handling in search.address_filter).
    """
    parts = [row.get(c, "") for c in INDEX_COLUMNS]
    return normalize(" ".join(p for p in parts if p))


_HOUSE_NUM = re.compile(r"\d+(-\d+)?[A-Z]?")
_APT = re.compile(r"(?:#\s*|\b(?:APT|APARTMENT|UNIT)\.?\s+)([A-Z0-9-]+)", re.I)


def split_apt(query: str):
    """Split a typed address into (apartment, rest).

    Apartments must be marked explicitly -- "#57B", "APT 57B", or "UNIT 57B" --
    mirroring how results are displayed. An unmarked trailing token is treated
    as part of the street, not a unit.
    """
    m = _APT.search(query)
    if not m:
        return None, query
    rest = (query[:m.start()] + " " + query[m.end():]).strip()
    return m.group(1).upper(), rest


def split_house_number(query: str):
    """Split a typed address into (house_number, rest).

    Returns (None, query) when the query does not start with something that
    looks like a house number. Handles Queens-style hyphenates ("34-12") and
    suffixed numbers ("41-35C", "514F").
    """
    parts = query.strip().split(None, 1)
    if not parts:
        return None, ""
    head = parts[0].strip().upper()
    rest = parts[1] if len(parts) > 1 else ""
    if _HOUSE_NUM.fullmatch(head):
        return head, rest
    return None, query
