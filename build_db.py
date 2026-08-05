#!/usr/bin/env python3
"""Load a NYC supplemental tax roll CSV into a SQLite database.

Each CSV becomes its own database with a `properties` table (one column per CSV
field, all TEXT), an FTS5 index on OWNER for name search, and an FTS5 index of
normalized address text for address search.

Usage:
    python build_db.py data/tc1/supplemental_roll_TC1_2027.csv tc1.db
    python build_db.py data/tc2/supplemental_roll_TC2_2027.csv tc2.db
"""
import csv
import sqlite3
import sys
from pathlib import Path

import address


def build(csv_path: str, db_path: str) -> None:
    csv_path = Path(csv_path)
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()

    with csv_path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        cols = [c.strip() for c in header]
        if "OWNER" not in cols:
            sys.exit(f"error: {csv_path} has no OWNER column (found: {cols})")

        con = sqlite3.connect(db_path)
        cur = con.cursor()
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f"CREATE TABLE properties ({col_defs})")

        placeholders = ", ".join("?" for _ in cols)
        insert = f"INSERT INTO properties VALUES ({placeholders})"

        n = 0
        batch = []
        for row in reader:
            # tolerate ragged rows: pad/trim to column count
            if len(row) < len(cols):
                row = row + [""] * (len(cols) - len(row))
            elif len(row) > len(cols):
                row = row[: len(cols)]
            batch.append(row)
            if len(batch) >= 10000:
                cur.executemany(insert, batch)
                n += len(batch)
                batch = []
        if batch:
            cur.executemany(insert, batch)
            n += len(batch)

    # FTS5 index over OWNER (tokenized name search) + plain index for exact lookups
    cur.execute(
        "CREATE VIRTUAL TABLE properties_fts USING fts5("
        "owner, content='properties', content_rowid='rowid')"
    )
    cur.execute(
        "INSERT INTO properties_fts(rowid, owner) SELECT rowid, OWNER FROM properties"
    )
    cur.execute("CREATE INDEX idx_owner ON properties(OWNER)")

    build_address_index(con, cols)

    con.commit()
    con.close()
    print(f"{csv_path.name}: {n:,} rows -> {db_path} ({len(cols)} cols)")


def build_address_index(con: sqlite3.Connection, cols: list) -> None:
    """FTS5 index of normalized address text, one row per property rowid.

    Normalization happens in Python (see address.normalize), so this cannot be an
    external-content table -- the indexed text does not appear verbatim in
    `properties`.
    """
    addr_cols = [c for c in ("STREET_NAME", "APTNO", "CITYNAME", "ZIP_CODE")
                 if c in cols]
    if not addr_cols:
        print("  (no address columns found; skipping address index)")
        return

    cur = con.cursor()
    cur.execute("CREATE VIRTUAL TABLE address_fts USING fts5(address)")
    quoted = ", ".join('"%s"' % c for c in addr_cols)
    select = f"SELECT rowid, {quoted} FROM properties"

    batch = []
    for row in con.execute(select):
        text = address.index_text(dict(zip(addr_cols, row[1:])))
        batch.append((row[0], text))
        if len(batch) >= 10000:
            cur.executemany("INSERT INTO address_fts(rowid, address) VALUES (?, ?)", batch)
            batch = []
    if batch:
        cur.executemany("INSERT INTO address_fts(rowid, address) VALUES (?, ?)", batch)

    # House-number range filtering scans LO/HI; index the street for scoped queries
    if "STREET_NAME" in cols:
        cur.execute("CREATE INDEX idx_street ON properties(STREET_NAME)")
    # Co-op unit rows have a blank OWNER; search.py resolves the name recorded
    # against their tax lot, which is the same PARID as the building's row
    cur.execute("CREATE INDEX idx_parid ON properties(PARID)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
