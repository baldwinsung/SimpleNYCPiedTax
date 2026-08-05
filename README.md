# SimpleNYCPiedTax

> ⚠️ **Unofficial. Use at your own risk. No warranties — the data may be wrong,
> incomplete, or out of date.** Not affiliated with the City of New York or the
> NYC Department of Finance. Not legal, tax, or financial advice. **Being in this
> data does NOT mean anyone owes the surcharge.** See
> **[DISCLAIMER.md](DISCLAIMER.md)** and [LICENSE](LICENSE) before relying on
> anything here.

A convenience index over NYC's public **supplemental market value roll**.

The NYC Department of Finance publishes these tax rolls (Tax Class 1 and Tax
Class 2, tax year 2027) as bulk CSVs. This tool just loads that already-public
data into a local SQLite database so it's searchable by owner name instead of
grepping a 36 MB file. It adds no new information and makes no judgment about any
property or owner — in particular, **it cannot and does not identify who is
subject to the non-primary-residence surcharge** (see below).

## What's here

| File | Purpose |
| --- | --- |
| `fetch.sh` | Download + unzip the TC1 and TC2 roll CSVs from nyc.gov |
| `build_db.py` | Load a roll CSV into its own SQLite DB (`tc1.db` / `tc2.db`) with FTS5 name + address indexes |
| `search.py` | Search a database by owner name and/or address |
| `address.py` | Address normalization shared by the builder and the searcher |

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
python3 search.py tc2 "realty holdings" --limit 50
python3 search.py tc2 "trust" --exact      # substring LIKE match instead
python3 search.py tc2 "central park" --limit none | grep -i llc   # no cap, pipe to grep
```

- First argument is `tc1`, `tc2`, or a path to a `.db` file.
- Default search uses the FTS5 index: each word is matched as a **prefix**,
  case-insensitive, all words required (AND). Order doesn't matter.
- `--exact` switches to a plain `%LIKE%` substring match on the raw owner string.
- `--limit none` (or `all` / `0`) removes the row cap — handy for piping the full
  result set to `grep`, e.g. `... --limit none | grep -i fund`.
- Output shows owner, address, PARID, and (for TC2) the fair market value.

## Sorting

```bash
python3 search.py tc2 "llc" --sort fmv                      # priciest first
python3 search.py tc2 -a "central park south" --sort fmv    # priciest on the block
python3 search.py tc2 "smith" --sort address                # group by street
python3 search.py tc2 "smith" --sort owner --reverse        # Z to A
```

- `--sort` takes `owner`, `address`, or `fmv`. The default is unchanged:
  `address` for address-only searches, `owner` otherwise.
- **`fmv` sorts highest-first**, since that's almost always the question being
  asked; `-r` / `--reverse` flips any sort.
- Sorting runs in SQL **before** `--limit`, so `--sort fmv --limit 25` is the 25
  most valuable matches — not an alphabetical 25 reordered after the fact. This
  is the part you can't get by piping to `sort`.
- `--sort fmv` needs the `FMV` column, which only TC2 has; on `tc1` it exits
  with an error rather than sorting silently wrong.

Piping still works for anything else — the output is `|`-delimited, so
`sort -t'|' -k1` sorts by owner (note `-t`, which BSD/macOS `sort` requires as a
separate flag from the delimiter).

Example:

```
$ python3 search.py tc2 "PEARL LLC" --limit 3
220 PEARL, LLC  |  220 CENTRAL PARK SOUTH #57B  |  PARID 1010301088  |  FMV $2,146,099
66 PEARL, LLC   |  1-5 COENTIES SLIP #RES       |  PARID 1000071002  |  FMV $9,372,000
87-89 PEARL LLC |  54 STONE STREET #2A          |  PARID 1000291303  |  FMV $1,741,153
```

## Searching by address

```bash
python3 search.py tc2 -a "220 central park south"      # whole building
python3 search.py tc2 -a "220 central park south #57B" # one unit
python3 search.py tc1 -a "e 7th st"                    # abbreviations expand
python3 search.py tc1 -a "41-35C de reimer ave"        # Queens-style numbers
python3 search.py tc2 "LLC" -a "central park south"    # name AND address
```

Query and index are normalized the same way, so you don't have to match the
roll's spelling:

- **Abbreviations expand** — `st`→`STREET`, `ave`→`AVENUE`, `blvd`→`BOULEVARD`,
  `e`/`w`/`n`/`s`→`EAST`/`WEST`/`NORTH`/`SOUTH`, and so on.
- **Ordinals are dropped** — `7th`→`7`. The roll contains *both*
  `EAST 7 STREET` and `EAST 7TH STREET`; either spelling finds both.
- **Punctuation and extra spaces don't matter** — `E. 7th St` works.
- **House numbers match the recorded range.** Rows store a `HOUSENUM_LO`..`HI`
  span, so `3 coenties slip` finds the row filed as `1-5 COENTIES SLIP`, and
  `22 downing st` finds `22-24 DOWNING STREET`.
- **Apartments must be marked** with `#57B`, `APT 57B`, or `UNIT 57B`. An
  unmarked trailing number is read as part of the street name — otherwise
  `e 7th st` would also match `789 EAST 160 STREET #7`.
- Numeric tokens match whole words (so `east 7 street` doesn't drag in
  `EAST 70`–`EAST 79 STREET`); word tokens still match as prefixes.
- For TC2, city and ZIP are searchable too: `-a "coenties slip 10004"`.
- `--exact` here means a plain substring match against the raw
  `HOUSENUM_LO STREET_NAME APTNO` text, with no normalization at all.

Databases built before address search still work — `search.py` falls back to
normalizing on the fly and warns you. Rebuilding with `build_db.py` takes a few
seconds and makes address queries ~10x faster.

## Co-op units have no owner name

If you find a unit by address but no name comes back, it is almost certainly a
co-op. **Every one of the 36,677 co-op unit rows in `tc2.db` has an empty
`OWNER` field** — 100%, by design, not a data gap:

| Row type in `tc2.db` | Rows | Blank owner |
| --- | ---: | ---: |
| Co-op **unit** rows | 36,677 | **36,677 (100%)** |
| Co-op **building** rows | 7,374 | 0 |
| Condo rows | 230,921 | 10 (~0%) |
| TC1 (houses) | 684,619 | 25 (~0%) |

The PARID (a boro-block-lot parcel ID) shows exactly why. A **condo** files each
unit as its own tax lot, so every unit has its own PARID, its own deed, and its
own owner name. A **co-op** is a single tax lot for the entire building — every
unit shares one PARID — and a shareholder holds stock plus a proprietary lease
rather than a deed, so there is no unit-level owner for DOF to record:

```
CONDO — 220 Central Park South     CO-OP — 5 Tudor City Place
  #18A  PARID 1010301001  lot 1001   #0A01  PARID 1013330023  lot 23   (no owner)
  #18B  PARID 1010301002  lot 1002   #0A02  PARID 1013330023  lot 23   (no owner)
  #18C  PARID 1010301003  lot 1003   #0A03  PARID 1013330023  lot 23   (no owner)
```

So the PARID is the *reason* there is no name, not a way around it — looking a
co-op unit up by PARID returns the building's corporation, which is the only
owner the lot has. `search.py` does that lookup and labels the unit rather than
printing a blank:

```
$ python3 search.py tc2 -a "5 tudor city place" --limit 3
WINDSOR OWNERS CORP CO TUDOR REALTYSVCS  CORP  |  1-19 TUDOR CITY PLACE  |  PARID 1013330023  |  FMV $104,539,000
[CO-OP UNIT — no individual owner; building: WINDSOR OWNERS CORP …]  |  5 TUDOR CITY PLACE #0A01  |  PARID 1013330023  |  FMV $186,276
[CO-OP UNIT — no individual owner; building: WINDSOR OWNERS CORP …]  |  5 TUDOR CITY PLACE #0A02  |  PARID 1013330023  |  FMV $119,908
```

Condos are individually deeded and *do* carry real owner names. **A co-op
resident's name is not in this dataset in any form** — no search can surface it.
Rows blank for other reasons show `[no owner listed]`.

The lookup keys on PARID, not `COOP_NUM`. `COOP_NUM` identifies the co-op
*corporation*, which can span several parcels — 429 and 431 WEST BROADWAY share
`COOP_NUM 100320` under two spellings of one corp — so it is ambiguous for 717
unit rows. PARID is the parcel and reaches exactly one name for all 36,677.

## Important: the roll is not a list of who owes the surcharge

The roll has ~960k rows — roughly every home and condo/co-op unit in the city —
but only **~17,000 owners** are actually potentially subject to the surcharge,
and they were notified privately by DOF letter. Being in `tc1.db` / `tc2.db`
means almost nothing, and you **cannot** reproduce the ~17k list from this data.
This tool does not attempt to. Don't use it to conclude — or imply — that anyone
owes anything. See **[docs/about-the-roll.md](docs/about-the-roll.md)** for
the full explanation (including the co-op rule that inflates the counts).

## Data source

NYC Department of Finance, Supplemental Tax Rolls (TC1 / TC2), tax year 2027:
`https://www.nyc.gov/assets/finance/downloads/tar/supplemental_roll_tc{1,2}_2027.zip`

Published July 24, 2026. Context:
[NYC DOF – Property Assessments](https://www.nyc.gov/site/finance/property/property-assessments.page)
("Supplemental market value roll – July 2026").

## License & disclaimer

MIT licensed — see [LICENSE](LICENSE). The software is provided **"AS IS"**,
without warranty of any kind, and the author is **not liable** for anything
arising from its use. Read the full [DISCLAIMER.md](DISCLAIMER.md).

---

> Built with Claude Code (Opus).
