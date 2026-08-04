# nyc_piedtax

NYC pied-à-terre tax — figuring out who'd owe it.

Builds a searchable SQLite database from the NYC Department of Finance
**supplemental tax rolls** (Tax Class 1 and Tax Class 2, tax year 2027), so you
can look up property owners by name.

## What's here

| File | Purpose |
| --- | --- |
| `fetch.sh` | Download + unzip the TC1 and TC2 roll CSVs from nyc.gov |
| `build_db.py` | Load a roll CSV into its own SQLite DB (`tc1.db` / `tc2.db`) with an FTS5 name index |
| `search.py` | Search a database by owner name |

Two separate databases, one per roll — they have **different schemas**:

- **`tc1.db`** — Tax Class 1 (~685k rows): `PARID, OWNER, HOUSENUM_LO, HOUSENUM_HI, STREET_NAME, APTNO`
- **`tc2.db`** — Tax Class 2 (~275k rows): the above plus `BORO, BLOCK, LOT, TAXYR, RECTYPE, TAX_CLASS, BLDG_CLASS, ZIP_CODE, CITYNAME, COOP_*, CONDO_NUMBER, FMV`

## Setup

```bash
./fetch.sh                                             # download + unzip CSVs into data/
python3 build_db.py data/tc1/supplemental_roll_TC1_2027.csv tc1.db
python3 build_db.py data/tc2/supplemental_roll_TC2_2027.csv tc2.db
```

Only the Python standard library is required (`sqlite3`, built with FTS5).
The `data/` downloads and `*.db` files are gitignored — regenerate them with the
commands above.

## Searching by name

```bash
python3 search.py tc2 "PEARL LLC"          # tokenized prefix match (default)
python3 search.py tc1 "san yuen"           # matches "SO SAN YUEN, AS TRUSTEE"
python3 search.py tc2 "trump" --limit 50
python3 search.py tc2 "smith" --exact      # substring LIKE match instead
python3 search.py tc2 "central park" --limit none | grep -i llc   # no cap, pipe to grep
```

- First argument is `tc1`, `tc2`, or a path to a `.db` file.
- Default search uses the FTS5 index: each word is matched as a **prefix**,
  case-insensitive, all words required (AND). Order doesn't matter.
- `--exact` switches to a plain `%LIKE%` substring match on the raw owner string.
- `--limit none` (or `all` / `0`) removes the row cap — handy for piping the full
  result set to `grep`, e.g. `... --limit none | grep -i fund`.
- Output shows owner, address, PARID, and (for TC2) the fair market value.

Example:

```
$ python3 search.py tc2 "PEARL LLC" --limit 3
220 PEARL, LLC  |  220 CENTRAL PARK SOUTH #57B  |  PARID 1010301088  |  FMV $2,146,099
66 PEARL, LLC   |  1-5 COENTIES SLIP #RES       |  PARID 1000071002  |  FMV $9,372,000
87-89 PEARL LLC |  54 STONE STREET #2A          |  PARID 1000291303  |  FMV $1,741,153
```

## Important: the roll is not a list of who owes

The roll has ~960k rows, but only **~17,000 owners** are actually potentially
subject to the surcharge — and they were notified privately by letter. Being in
`tc1.db` / `tc2.db` means almost nothing, and you **cannot** reproduce the 17k
list from this data. See **[docs/about-the-roll.md](docs/about-the-roll.md)** for
the full explanation (including the co-op rule that inflates the counts).

## Data source

NYC Department of Finance, Supplemental Tax Rolls (TC1 / TC2), tax year 2027:
`https://www.nyc.gov/assets/finance/downloads/tar/supplemental_roll_tc{1,2}_2027.zip`

Published July 24, 2026. Context:
[NYC DOF – Property Assessments](https://www.nyc.gov/site/finance/property/property-assessments.page)
("Supplemental market value roll – July 2026").

---

> Built with Claude Code (Opus).
