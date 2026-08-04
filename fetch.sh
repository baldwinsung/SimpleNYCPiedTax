#!/usr/bin/env bash
# Download the NYC DOF supplemental tax roll CSVs (TC1 + TC2) and unzip them.
# NYC's Akamai edge blocks non-browser user agents, so we send a browser UA.
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p data

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
REFERER="https://www.nyc.gov/site/finance/property/property-tax-rates.page"
BASE="https://www.nyc.gov/assets/finance/downloads/tar"

for tc in tc1 tc2; do
  echo "Downloading ${tc}..."
  curl -fsSL -A "$UA" -H "Referer: $REFERER" \
    -o "data/${tc}.zip" "${BASE}/supplemental_roll_${tc}_2027.zip"
  unzip -o "data/${tc}.zip" -d "data/${tc}" >/dev/null
done

echo "Done. CSVs are under data/tc1/ and data/tc2/."
