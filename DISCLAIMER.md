# Disclaimer

**Use at your own risk. No warranties. Not legal, tax, or financial advice.**

This project is an independent, unofficial tool. It is **not** affiliated with,
endorsed by, or connected to the City of New York, the New York City Department
of Finance (DOF), or any government agency.

## No guarantee of accuracy

The data loaded by this tool comes from NYC Department of Finance public tax-roll
files and may be incomplete, out of date, mis-parsed, or simply wrong. The author
makes **no representation or warranty** of any kind — express or implied — about
the accuracy, completeness, reliability, or fitness for any purpose of this
software or any output it produces. You are responsible for independently
verifying anything you rely on against the official source.

## The roll is not a list of who owes the surcharge

Presence in these files does **not** mean a person or property is subject to the
non-primary-residence surcharge. The vast majority of listed properties are not
subject to it, and the ~17,000 potentially-subject owners were notified privately
by DOF letter — information that is **not** contained in this data and **cannot**
be derived from it. See [docs/about-the-roll.md](docs/about-the-roll.md). Do not
use this tool to conclude that anyone does or does not owe any tax.

## Informational content only

Files under `docs/` (e.g. [docs/status-2026-08.md](docs/status-2026-08.md),
[docs/about-the-roll.md](docs/about-the-roll.md)) that summarize the law,
timeline, rates, exemption process, litigation, or news coverage are provided
**for informational purposes only**. They are the author's summary of
third-party news, law-firm client alerts, and government press releases as of
the date noted in each file, may contain errors, and may be **out of date by
the time you read them** — this tax's rules, deadlines, and legal status have
already changed multiple times since enactment and may change again. These
summaries are **not** a substitute for the official DOF guidance or legal
counsel, and are **not** legal, tax, or financial advice (see "Not advice"
below). Always verify current status against the primary sources linked in
each doc's "Sources" section and against
[NYC DOF's official pages](https://www.nyc.gov/site/finance/property/property-assessments.page)
before relying on anything.

## Not advice

Nothing here is legal, tax, financial, or professional advice. For any decision
with real consequences, consult the official NYC Department of Finance records
and a qualified professional.

## Limitation of liability

To the maximum extent permitted by law, the author shall **not be liable** for
any claim, damages, loss, or other liability — whether in contract, tort, or
otherwise — arising from, out of, or in connection with this software, its use,
or its output. By using this software you accept all risk.

## Data and privacy

The underlying records are public NYC property tax-roll data. This repository
does **not** contain that data (it is downloaded locally and gitignored). Use of
any downloaded data is subject to NYC's terms and applicable law. Do not use it
to harass, dox, or harm anyone.

## Official source

NYC Department of Finance — Property Assessments:
https://www.nyc.gov/site/finance/property/property-assessments.page
