#!/usr/bin/env python3
"""Load a NYC supplemental tax roll CSV into a SQLite database.

Each CSV becomes its own database with a `properties` table (one column per CSV
field, all TEXT), an FTS5 index on OWNER for name search, and an FTS5 index of
normalized address text for address search.

Usage:
    python build_db.py data/tc1/supplemental_roll_TC1_2027.csv tc1.db
    python build_db.py data/tc2/supplemental_roll_TC2_2027.csv tc2.db

    # TC1's supplemental roll has no market-value column. Pass the FY2027
    # final assessment "property master" file (fetch.sh downloads it to
    # data/tc1_master/) as a third argument to join one in as FMV:
    python build_db.py data/tc1/supplemental_roll_TC1_2027.csv tc1.db \\
        data/tc1_master/PROPMAST_TC1_2027_FIN.txt
"""
import csv
import sqlite3
import sys
from pathlib import Path

import address


def build(csv_path: str, db_path: str, master_path: str = None) -> None:
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

    if master_path:
        add_fmv_column(con, master_path, cols)

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


def load_market_values(master_path: Path) -> dict:
    """PARID -> market value (plain digit string) from a PTS property-master file.

    The property master is tab-delimited, one row per parcel, with no PARID
    column of its own to key on reliably (its PARID field is fixed-width and
    space-padded) -- BORO/BLOCK/LOT concatenate into the same PARID format the
    supplemental rolls use, so rebuild it from those instead. FINMKTTOT ("Final
    Market Assessed Total Value") is the DOF market value figure -- the same
    concept as the supplemental roll's own FMV column, just from a different
    file, since TC1's supplemental roll doesn't carry one.
    """
    values = {}
    with master_path.open(encoding="utf-8", errors="replace") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {c: i for i, c in enumerate(header)}
        required = ("BORO", "BLOCK", "LOT", "FINMKTTOT")
        missing = [c for c in required if c not in idx]
        if missing:
            sys.exit(f"error: {master_path} is missing columns {missing}")

        for line in fh:
            parts = line.rstrip("\n").split("\t")
            parid = (
                parts[idx["BORO"]].strip()
                + parts[idx["BLOCK"]].strip().zfill(5)
                + parts[idx["LOT"]].strip().zfill(4)
            )
            try:
                values[parid] = str(int(parts[idx["FINMKTTOT"]]))
            except ValueError:
                pass
    return values


def add_fmv_column(con: sqlite3.Connection, master_path: str, cols: list) -> None:
    """Join market values from a property-master file onto `properties` as FMV."""
    if "FMV" in cols:
        print("  (properties already has FMV; skipping market-value join)")
        return
    if "PARID" not in cols:
        sys.exit("error: --master join needs a PARID column to key on")

    values = load_market_values(Path(master_path))

    cur = con.cursor()
    cur.execute("CREATE TEMP TABLE market_values (parid TEXT PRIMARY KEY, fmv TEXT)")
    cur.executemany(
        "INSERT INTO market_values VALUES (?, ?)", values.items()
    )
    cur.execute('ALTER TABLE properties ADD COLUMN "FMV" TEXT')
    cur.execute(
        "UPDATE properties SET FMV = ("
        "  SELECT fmv FROM market_values WHERE market_values.parid = properties.PARID"
        ")"
    )
    cur.execute("DROP TABLE market_values")

    matched = cur.execute(
        "SELECT COUNT(*) FROM properties WHERE FMV IS NOT NULL"
    ).fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    print(f"  joined FMV from {Path(master_path).name}: "
          f"{matched:,}/{total:,} rows matched")


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
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
