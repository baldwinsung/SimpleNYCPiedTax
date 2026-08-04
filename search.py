#!/usr/bin/env python3
"""Search a NYC supplemental tax roll database by owner name.

Uses the FTS5 index for tokenized, prefix name matching (case-insensitive).
Each token is matched as a prefix, so "PEARL" finds "66 PEARL, LLC" and
"san yu" finds "SO SAN YUEN, AS TRUSTEE".

Usage:
    python search.py tc1 "PEARL LLC"
    python search.py tc2 "san yuen" --limit 50
    python search.py tc2.db "smith" --exact     # substring LIKE match instead
"""
import argparse
import sqlite3
import sys
from pathlib import Path


def resolve_db(name: str) -> Path:
    """Accept 'tc1', 'tc2', or a path to a .db file."""
    p = Path(name)
    if p.suffix == ".db" and p.exists():
        return p
    candidate = Path(f"{name}.db")
    if candidate.exists():
        return candidate
    sys.exit(f"error: no database found for '{name}' (looked for {candidate})")


def fts_query(terms: str) -> str:
    """Turn free text into an FTS5 prefix query: each token -> "tok"* joined by AND."""
    tokens = [t for t in terms.replace('"', " ").split() if t]
    if not tokens:
        sys.exit("error: empty search")
    return " ".join(f'"{t}"*' for t in tokens)


def main() -> None:
    ap = argparse.ArgumentParser(description="Search tax roll by owner name")
    ap.add_argument("db", help="tc1, tc2, or path to a .db file")
    ap.add_argument("name", help="owner name (or fragment) to search for")
    ap.add_argument("--limit", default="25",
                    help="max rows (default 25; 'none'/'all'/0 = no limit)")
    ap.add_argument("--exact", action="store_true",
                    help="substring LIKE match instead of FTS token/prefix match")
    args = ap.parse_args()

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
    cur = con.cursor()

    if args.exact:
        rows = cur.execute(
            "SELECT * FROM properties WHERE OWNER LIKE ? ORDER BY OWNER LIMIT ?",
            (f"%{args.name}%", limit),
        ).fetchall()
    else:
        rows = cur.execute(
            "SELECT p.* FROM properties_fts f "
            "JOIN properties p ON p.rowid = f.rowid "
            "WHERE properties_fts MATCH ? ORDER BY p.OWNER LIMIT ?",
            (fts_query(args.name), limit),
        ).fetchall()

    if not rows:
        print("No matches.")
        return

    for r in rows:
        d = dict(r)
        owner = d.pop("OWNER", "")
        parid = d.pop("PARID", "")
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
        print(line)

    print(f"\n{len(rows)} row(s).")


if __name__ == "__main__":
    main()
