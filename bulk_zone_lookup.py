"""
Bulk NWS Zone, County & City Lookup
-------------------------------------
Reads your existing locations.csv and queries the NWS /points/ API
for each site to populate:
  - Zone       : NWS forecast zone code (e.g. ARZ026)
  - CountyCode : NWS county UGC code (e.g. ARC055) — used for SPC watch matching
  - County     : County display name (e.g. Craighead)
  - City       : Nearest city/town per NWS (e.g. Jonesboro)

Writes results to locations_with_zones.csv.
Runtime: ~1 second per site due to API rate limiting.
"""

import requests
import csv
import time

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────
INPUT_CSV  = r"locations.csv"
OUTPUT_CSV = r"locations_with_zones.csv"

HEADERS = {
    "User-Agent": "NOC-BulkZoneLookup/1.0 (bulk.lookup@example.com)",
}

# ─────────────────────────────────────────
#  LOAD CSV
# ─────────────────────────────────────────
print("=" * 60)
print("Bulk NWS Zone, County & City Lookup")
print("=" * 60)
print(f"Reading from : {INPUT_CSV}")
print(f"Writing to   : {OUTPUT_CSV}\n")

locations = []

try:
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            locations.append(row)
    print(f"Loaded {len(locations)} locations\n")
except FileNotFoundError:
    print(f"ERROR: File not found — {INPUT_CSV}")
    exit(1)
except Exception as e:
    print(f"ERROR reading CSV: {e}")
    exit(1)

# ─────────────────────────────────────────
#  LOOKUP LOOP
# ─────────────────────────────────────────
print("Looking up zone, county, and city for each site...\n")

for i, location in enumerate(locations, 1):
    name = location.get("Name", "Unknown")
    print(f"[{i}/{len(locations)}] {name}...", end=" ", flush=True)

    try:
        lat = float(location.get("Latitude", 0))
        lon = float(location.get("Longitude", 0))
    except ValueError:
        print("✗ Invalid coordinates — skipping")
        location["Zone"]       = "ERROR"
        location["CountyCode"] = "ERROR"
        location["County"]     = "ERROR"
        location["City"]       = "ERROR"
        continue

    url = f"https://api.weather.gov/points/{lat},{lon}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        props = resp.json().get("properties", {})

        # ── Zone code ─────────────────────
        forecast_zone = props.get("forecastZone", "")
        zone_code = forecast_zone.split("/")[-1] if forecast_zone else "NOT_FOUND"

        # ── City (from relativeLocation) ──
        rel_loc = props.get("relativeLocation", {}).get("properties", {})
        city  = rel_loc.get("city",  "Unknown")
        state = rel_loc.get("state", "")
        # Only use rel_loc state as fallback if State column is empty
        if not location.get("State", "").strip() and state:
            location["State"] = state

        # ── County name & code ────────────
        # county_url looks like: https://api.weather.gov/zones/county/ARC055
        # We extract the UGC county code (e.g. ARC055) directly from the URL,
        # then fetch the display name separately.
        county_url  = props.get("county", "")
        county_name = "Unknown"
        county_code = "NOT_FOUND"

        if county_url:
            # Code is always the last segment of the URL — no extra API call needed
            county_code = county_url.split("/")[-1]
            try:
                c_resp = requests.get(county_url, headers=HEADERS, timeout=10)
                c_resp.raise_for_status()
                county_name = (
                    c_resp.json()
                    .get("properties", {})
                    .get("name", "Unknown")
                )
            except Exception:
                # Fall back to relativeLocation city as county approximation
                county_name = city

        location["Zone"]       = zone_code
        location["CountyCode"] = county_code
        location["County"]     = county_name
        location["City"]       = city

        print(f"✓  Zone: {zone_code}  |  CountyCode: {county_code}  |  County: {county_name}  |  City: {city}")

    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP error: {e}")
        location["Zone"]       = "ERROR"
        location["CountyCode"] = "ERROR"
        location["County"]     = "ERROR"
        location["City"]       = "ERROR"
    except requests.exceptions.Timeout:
        print("✗ Timeout — skipping")
        location["Zone"]       = "TIMEOUT"
        location["CountyCode"] = "TIMEOUT"
        location["County"]     = "TIMEOUT"
        location["City"]       = "TIMEOUT"
    except Exception as e:
        print(f"✗ Error: {e}")
        location["Zone"]       = "ERROR"
        location["CountyCode"] = "ERROR"
        location["County"]     = "ERROR"
        location["City"]       = "ERROR"

    time.sleep(1)  # Be polite to the NWS API

# ─────────────────────────────────────────
#  WRITE OUTPUT CSV
# ─────────────────────────────────────────
print(f"\nWriting results to: {OUTPUT_CSV}")

try:
    fieldnames = list(locations[0].keys())

    # Ensure new columns are present and in a logical order
    for col in ["Zone", "CountyCode", "County", "City"]:
        if col not in fieldnames:
            fieldnames.append(col)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(locations)

    # Summary
    errors   = sum(1 for loc in locations if loc.get("Zone") in ("ERROR", "TIMEOUT", "NOT_FOUND") or loc.get("CountyCode") in ("ERROR", "TIMEOUT", "NOT_FOUND"))
    success  = len(locations) - errors

    print(f"\n✓ Done! {success}/{len(locations)} sites resolved successfully.")
    if errors:
        print(f"  ⚠ {errors} site(s) returned errors — check coordinates for those rows.")
    print(f"\nNext steps:")
    print(f"  1. Review {OUTPUT_CSV}")
    print(f"  2. Correct any ERROR or NOT_FOUND rows manually if needed")
    print(f"  3. Rename to locations.csv when ready")

except Exception as e:
    print(f"ERROR writing output: {e}")
