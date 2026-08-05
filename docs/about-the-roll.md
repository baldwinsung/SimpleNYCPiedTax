# Why does the roll have ~960,000 names when only ~17,000 owe?

Short version: **this roll is a valuation document, not a list of who owes the
surcharge.** The two get conflated because DOF published them at the same time,
but they are not the same thing.

## What DOF actually said

From the NYC Department of Finance
[Property Assessments page](https://www.nyc.gov/site/finance/property/property-assessments.page),
"Supplemental market value roll – July 2026" section:

> The Department of Finance published a supplemental market value roll on
> July 24, 2026, related to the annual non-primary residence property surcharge.
> This roll includes, but is not limited to, all 1-, 2-, and 3-family homes and
> all co-op and condominium properties, **as well as each individual co-op unit
> in a building in which at least one unit may be subject to the surcharge.**
>
> The vast majority of properties and units listed in the roll will **NOT** be
> subject to the surcharge. Only the roughly **17,000 property owners to whom DOF
> sent a letter** are potentially subject to the surcharge. Property owners who
> received a letter that they may be subject to the surcharge should review DOF's
> FAQ, and if needed, can submit a surcharge exemption application.

## The logic (such as it is)

### 1. The roll's job is to publish market values, not to name who owes.

A "supplemental market value roll" exists to *establish and disclose an assessed
market value* for a whole category of property. For the non-primary-residence
surcharge to be legally defensible, DOF needs a published market value on record
for every property that *could conceivably* fall under it — so that an owner who
does get charged can see the number their surcharge is based on and challenge it.

So DOF valued the entire eligible universe:

- all 1-, 2-, and 3-family homes → **TC1**, ~685k rows
- all co-op / condo units → **TC2**, ~275k rows

That's ~960k rows — roughly the **entire residential base of NYC**. That is the
point. The roll is supposed to be nearly everybody.

### 2. The co-op rule is the big multiplier.

> …as well as each individual co-op unit in a building in which **at least one
> unit** may be subject to the surcharge.

Co-ops are valued at the **building** level, then allocated across units. So if
even **one** apartment in a 300-unit co-op building might owe the surcharge, DOF
lists **all 300 units** — it can't publish the one without publishing the whole
building's allocation. One potentially-subject penthouse drags 299 unaffected
neighbors onto the list. That's why TC2 is padded with co-op units.

The same rule, seen from the other side: those unit rows are **anonymous**. All
36,677 co-op unit rows in TC2 have an empty `OWNER` field — 100% of them.

The parcel IDs show why. A condo files each unit as its own tax lot, so every
unit has a distinct `PARID` and a deeded owner. A co-op is **one tax lot for the
whole building** — all its units share the building's `PARID` — and a
shareholder holds stock plus a proprietary lease, not a deed. There is simply no
unit-level owner to record; the only name on the lot is the co-op corporation
(`WINDSOR OWNERS CORP`, etc.).

So the co-op rule inflates the row count *without* naming anybody. Condos, which
are individually deeded, do carry real owner names. If you look up a co-op unit
and find no name, that is the data working as designed — the resident's name is
not in this dataset in any form.

### 3. The ~17,000 who actually owe were notified privately, by letter.

The targeting logic — who's a non-primary resident, whose mailing address is out
of state, who lost a homestead/exemption flag — is **not** in these CSVs. The
roll has no "you owe" column. The only authoritative signal is **"did DOF mail
you a letter."**

## What this means for this project

- **Being in `tc1.db` / `tc2.db` means almost nothing.** Nearly every home and
  condo/co-op unit in the city is here.
- **You cannot reproduce the ~17,000 list from this data alone.** The letter
  recipients were selected using information DOF did not publish. That's by
  design.
- The search tool answers "does DOF have a market value on record for this
  owner/unit, and what is it?" — **not** "is this owner surcharged?"
- If anything, *absence* from the roll would be the more informative signal than
  presence.

## Data recap

| DB | Roll | Rows | What it covers |
| --- | --- | ---: | --- |
| `tc1.db` | Tax Class 1 | ~685k | all 1-, 2-, 3-family homes |
| `tc2.db` | Tax Class 2 | ~275k | all co-op / condo units (incl. every unit in any building with ≥1 possibly-subject unit) |
| — | letter recipients | ~17k | **not in this data** — mailed privately by DOF |

---

> Built with Claude Code (Opus).
