#!/usr/bin/env python3
"""Search a NYC supplemental tax roll database by owner name and/or address.

Name search uses the FTS5 index for tokenized, prefix matching (case-insensitive).
Each token is matched as a prefix, so "PEARL" finds "66 PEARL, LLC" and
"san yu" finds "SO SAN YUEN, AS TRUSTEE".

Address search normalizes both the query and the index the same way ("E 7th St"
and "EAST 7 STREET" collapse to the same tokens) and matches a leading house
number against the roll's HOUSENUM_LO..HOUSENUM_HI range.

Usage:
    python search.py tc1 "PEARL LLC"
    python search.py tc2 "san yuen" --limit 50
    python search.py tc2 --address "220 central park south"
    python search.py tc1 "smith" --address "e 7th st"    # both must match
    python search.py tc2.db "smith" --exact              # substring LIKE match
    python search.py tc2 "llc" --sort fmv                # priciest matches first
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import address


def resolve_db(name: str) -> Path:
    """Accept 'tc1', 'tc2', or a path to a .db file."""
    p = Path(name)
    if p.suffix == ".db" and p.exists():
        return p
    candidate = Path(f"{name}.db")
    if candidate.exists():
        return candidate
    sys.exit(f"error: no database found for '{name}' (looked for {candidate})")


def fts_query(terms: str, prefix_numbers: bool = True) -> str:
    """Turn free text into an FTS5 prefix query: each token -> "tok"* joined by AND.

    With prefix_numbers=False, purely numeric tokens are matched exactly. That
    matters for addresses: "EAST 7 STREET" as a prefix query would also match
    EAST 70 through EAST 79 STREET.
    """
    tokens = [t for t in terms.replace('"', " ").split() if t]
    if not tokens:
        sys.exit("error: empty search")
    parts = []
    for t in tokens:
        if not prefix_numbers and t.isdigit():
            parts.append(f'"{t}"')
        else:
            parts.append(f'"{t}"*')
    return " ".join(parts)


def has_table(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ?", (name,)
    ).fetchone() is not None


def housenum_sql(hnum: str, t: str = "p"):
    """(sql, params) matching a typed house number against HOUSENUM_LO/HI.

    The roll stores plain numbers ("26"), true ranges ("1".."5"), Queens-style
    hyphenates ("34-12"), and suffixed numbers ("41-35C"), so match on any of:
    an exact hit on either endpoint, a numeric LO..HI range, or the part before
    the hyphen ("22" finds "22-24 DOWNING STREET").
    """
    lo, hi = f"{t}.HOUSENUM_LO", f"{t}.HOUSENUM_HI"
    clauses = [f"UPPER(TRIM({lo})) = ?", f"UPPER(TRIM({hi})) = ?"]
    params = [hnum, hnum]

    if hnum.isdigit():
        # CAST('41-35C') is 41, so only range-compare when both ends are all digits
        digits = "TRIM({0}) <> '' AND NOT TRIM({0}) GLOB '*[^0-9]*'"
        clauses.append(
            f"({digits.format(lo)} AND {digits.format(hi)} AND "
            f"CAST({lo} AS INTEGER) <= ? AND ? <= CAST({hi} AS INTEGER))"
        )
        params += [int(hnum), int(hnum)]
        clauses.append(f"{lo} LIKE ?")
        params.append(f"{hnum}-%")

    return "(" + " OR ".join(clauses) + ")", params


def address_filter(con: sqlite3.Connection, query: str, exact: bool):
    """(sql, params) restricting `properties p` to rows matching an address query."""
    raw_addr = ("TRIM(COALESCE(p.HOUSENUM_LO,'')) || ' ' || "
                "TRIM(COALESCE(p.STREET_NAME,'')) || ' ' || "
                "TRIM(COALESCE(p.APTNO,''))")
    if exact:
        return f"{raw_addr} LIKE ?", [f"%{query}%"]

    apt, rest = address.split_apt(query)
    hnum, rest = address.split_house_number(rest)
    clauses, params = [], []

    if hnum:
        sql, p = housenum_sql(hnum)
        clauses.append(sql)
        params += p

    if apt:
        clauses.append("UPPER(TRIM(p.APTNO)) = ?")
        params.append(apt)

    rest = address.normalize(rest)
    if rest:
        if has_table(con, "address_fts"):
            clauses.append(
                "p.rowid IN (SELECT rowid FROM address_fts WHERE address_fts MATCH ?)"
            )
            params.append(fts_query(rest, prefix_numbers=False))
        else:
            # DB predates the address index: normalize on the fly instead. Correct
            # but scans every row, so hint that a rebuild makes this fast.
            print("note: no address index in this database; falling back to a full "
                  "scan (rebuild with build_db.py to speed this up)", file=sys.stderr)
            con.create_function("_norm_addr", 1, address.normalize, deterministic=True)
            present = {r[1] for r in con.execute("PRAGMA table_info(properties)")}
            cols = " || ' ' || ".join(
                f"COALESCE(p.{c},'')" for c in address.INDEX_COLUMNS if c in present)
            for tok in rest.split():
                clauses.append(f"(' ' || _norm_addr({cols}) || ' ') LIKE ?")
                # numeric tokens match whole-word only, matching fts_query above
                params.append(f"% {tok} %" if tok.isdigit() else f"% {tok}%")
    elif not hnum and not apt:
        sys.exit("error: empty address search")

    return " AND ".join(clauses), params


class OwnerLookup:
    """Resolve a row with a blank OWNER to the name recorded on its tax lot.

    Co-op unit rows carry no OWNER: the whole building is a single tax lot, and
    a shareholder holds stock plus a proprietary lease rather than a deed, so
    there is no unit-level owner for DOF to record. Every unit therefore shares
    the building's PARID, and the corporation's name sits on the row for that
    same parcel.

    Keyed on PARID rather than COOP_NUM. COOP_NUM identifies the co-op
    *corporation*, which can span several parcels -- 429 and 431 WEST BROADWAY
    share COOP_NUM 100320 under two spellings of one corp -- so it resolves
    ambiguously for 717 unit rows. PARID is the parcel, and reaches exactly one
    owner name for every blank-owner row in the roll.
    """

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        self.cache = {}
        cols = {r[1] for r in con.execute("PRAGMA table_info(properties)")}
        self.is_coop_col = "COOP_BLDG_NUM" if "COOP_BLDG_NUM" in cols else None

    def lot_owner(self, parid: str):
        """The owner name recorded against this PARID, or None."""
        if not parid:
            return None
        if parid not in self.cache:
            hit = self.con.execute(
                "SELECT OWNER FROM properties WHERE PARID = ? AND TRIM(OWNER) <> '' "
                "LIMIT 1", (parid,),
            ).fetchone()
            self.cache[parid] = hit[0].strip() if hit else None
        return self.cache[parid]

    def label(self, row: dict, parid: str) -> str:
        """Stand-in owner text for a row whose OWNER field is empty."""
        name = self.lot_owner(parid)
        if not name:
            return "[no owner listed]"
        if self.is_coop_col and (row.get(self.is_coop_col) or "").strip():
            return f"[CO-OP UNIT — no individual owner; building: {name}]"
        return f"[no owner listed; tax lot: {name}]"


def format_row(row: sqlite3.Row, owners: OwnerLookup = None) -> str:
    d = dict(row)
    owner = d.pop("OWNER", "").strip()
    parid = d.pop("PARID", "")
    if not owner:
        owner = owners.label(d, parid) if owners else "[no owner listed]"
    # build a compact address from whatever address fields exist
    lo = d.get("HOUSENUM_LO", "").strip()
    hi = d.get("HOUSENUM_HI", "").strip()
    num = lo if lo == hi or not hi else f"{lo}-{hi}"
    street = d.get("STREET_NAME", "").strip()
    apt = d.get("APTNO", "").strip()
    addr = " ".join(x for x in [num, street] if x)
    if apt:
        addr += f" #{apt}"
    fmv = d.get("FMV", "")
    line = f"{owner}  |  {addr}  |  PARID {parid}"
    if fmv:
        try:
            line += f"  |  FMV ${int(fmv):,}"
        except ValueError:
            pass
    return line


ADDRESS_ORDER = "p.STREET_NAME, CAST(p.HOUSENUM_LO AS INTEGER), p.HOUSENUM_LO, p.APTNO"


def order_by(con: sqlite3.Connection, args) -> str:
    """ORDER BY clause for the requested --sort, or the default for this search.

    Sorting happens in SQL, before LIMIT, so `--sort fmv --limit 25` is the 25
    most valuable matches rather than an alphabetical 25 re-sorted afterwards.
    """
    choice = args.sort
    if not choice:
        # Address-only searches read best grouped by street; otherwise by owner
        choice = "address" if (args.addr and not args.name) else "owner"

    if choice == "fmv":
        cols = {r[1] for r in con.execute("PRAGMA table_info(properties)")}
        if "FMV" not in cols:
            sys.exit("error: this database has no FMV column; rebuild it with "
                      "build_db.py (tc1 needs the property-master join argument "
                      "-- see README) or use --sort owner / --sort address")
        # FMV is TEXT, so compare numerically; highest first is the useful default
        direction = "ASC" if args.reverse else "DESC"
        return f"CAST(p.FMV AS INTEGER) {direction}, {ADDRESS_ORDER}"

    order = ADDRESS_ORDER if choice == "address" else "p.OWNER"
    if args.reverse:
        return ", ".join(f"{c.strip()} DESC" for c in order.split(","))
    return order


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Search tax roll by owner name and/or address")
    ap.add_argument("db", help="tc1, tc2, or path to a .db file")
    ap.add_argument("name", nargs="?",
                    help="owner name (or fragment) to search for")
    ap.add_argument("-a", "--address", dest="addr",
                    help="address to search for, e.g. '220 central park south'")
    ap.add_argument("--limit", default="25",
                    help="max rows (default 25; 'none'/'all'/0 = no limit)")
    ap.add_argument("--exact", action="store_true",
                    help="substring LIKE match instead of FTS token/prefix match")
    ap.add_argument("--sort", choices=("owner", "address", "fmv"),
                    help="sort order (default: address for address-only "
                         "searches, owner otherwise; fmv sorts highest first)")
    ap.add_argument("-r", "--reverse", action="store_true",
                    help="reverse the sort order")
    args = ap.parse_args()

    if not args.name and not args.addr:
        ap.error("give an owner name, --address, or both")

    # -1 means "no limit" in SQLite; treat none/all/0 as unlimited
    if str(args.limit).lower() in ("none", "all", "0"):
        limit = -1
    else:
        try:
            limit = int(args.limit)
        except ValueError:
            sys.exit(f"error: --limit must be an integer or none/all (got {args.limit!r})")

    con = sqlite3.connect(resolve_db(args.db))
    con.row_factory = sqlite3.Row

    where, params = [], []

    if args.name:
        if args.exact:
            where.append("p.OWNER LIKE ?")
            params.append(f"%{args.name}%")
        else:
            where.append(
                "p.rowid IN (SELECT rowid FROM properties_fts "
                "WHERE properties_fts MATCH ?)"
            )
            params.append(fts_query(args.name))

    if args.addr:
        sql, p = address_filter(con, args.addr, args.exact)
        where.append(sql)
        params += p

    order = order_by(con, args)

    rows = con.execute(
        f"SELECT p.* FROM properties p WHERE {' AND '.join(where)} "
        f"ORDER BY {order} LIMIT ?",
        params + [limit],
    ).fetchall()

    if not rows:
        print("No matches.")
        return

    owners = OwnerLookup(con)
    for r in rows:
        print(format_row(r, owners))

    print(f"\n{len(rows)} row(s).")


if __name__ == "__main__":
    main()
