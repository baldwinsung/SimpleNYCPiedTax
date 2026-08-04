#!/usr/bin/env python3
"""Load a NYC supplemental tax roll CSV into a SQLite database.

Each CSV becomes its own database with a `properties` table (one column per CSV
field, all TEXT) plus an FTS5 index on OWNER for fast name search.

Usage:
    python build_db.py data/tc1/supplemental_roll_TC1_2027.csv tc1.db
    python build_db.py data/tc2/supplemental_roll_TC2_2027.csv tc2.db
"""
import csv
import sqlite3
import sys
from pathlib import Path


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
    con.commit()
    con.close()
    print(f"{csv_path.name}: {n:,} rows -> {db_path} ({len(cols)} cols)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
