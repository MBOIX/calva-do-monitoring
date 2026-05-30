#!/usr/bin/env python3
"""
Fetch historical hydrological data from the Hub'Eau API v2 for the rivers
declared in config/rivers.json. Downloads daily max water height (HIXnJ) and
daily mean flow rate (QmnJ) per station, then saves JSON cache files under
data_cache/<river_id>/.

Usage:
    python3 scripts/fetch_hydro_data.py                       # all rivers
    python3 scripts/fetch_hydro_data.py --river odon          # one river
    python3 scripts/fetch_hydro_data.py --station I362101001  # one station
    python3 scripts/fetch_hydro_data.py --since 2024-01-01    # incremental
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "rivers.json")
DATA_DIR = os.path.join(REPO_ROOT, "data_cache")

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/hydrometrie"

RATE_LIMIT_DELAY = 0.15  # seconds between requests (stay under 10 req/s)
PAGE_SIZE = 2000


def load_rivers():
    """Load the river manifest from config/rivers.json."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["rivers"]


def fetch_json(url):
    """Fetch JSON from a URL with retry logic."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < 2:
                print(f"  Retry {attempt + 1}/3 after error: {e}")
                time.sleep(2)
            else:
                raise


def fetch_obs_elab(station_code, grandeur, date_start=None):
    """Fetch all elaborated observations for a station/grandeur, handling pagination."""
    params = {
        "code_entite": station_code,
        "grandeur_hydro_elab": grandeur,
        "size": PAGE_SIZE,
        "sort": "asc",
    }
    if date_start:
        params["date_debut_obs_elab"] = date_start

    url = f"{BASE_URL}/obs_elab?{urllib.parse.urlencode(params)}"
    all_data = []
    page = 0

    while url:
        page += 1
        print(f"    Page {page} ({len(all_data)} records so far)...", end="\r")
        result = fetch_json(url)
        records = result.get("data", [])
        all_data.extend(records)
        url = result.get("next")
        if url:
            time.sleep(RATE_LIMIT_DELAY)

    print(f"    Fetched {len(all_data)} records" + " " * 30)
    return all_data


def simplify_record(record):
    """Extract only the fields we need to minimize cache size."""
    return {
        "date": record["date_obs_elab"],
        "value": record["resultat_obs_elab"],
        "quality": record.get("libelle_qualification"),
    }


def load_existing_cache(filepath):
    """Load existing cached data to determine last date."""
    if not os.path.exists(filepath):
        return [], None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records", [])
    if records:
        last_date = max(r["date"] for r in records if r.get("date"))
        return records, last_date
    return records, None


def save_cache(filepath, station, grandeur, records, unit):
    """Save data to a JSON cache file."""
    metadata = {
        "station_code": station["code"],
        "station_name": station["name"],
        "grandeur": grandeur,
        "unit": unit,
        "fetched_at": datetime.now().isoformat(),
        "record_count": len(records),
        "date_min": min((r["date"] for r in records if r.get("date")), default=None),
        "date_max": max((r["date"] for r in records if r.get("date")), default=None),
        "records": records,
    }
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    size_kb = os.path.getsize(filepath) / 1024
    print(f"    Saved {filepath} ({size_kb:.1f} KB)")


def fetch_station_data(station, grandeur, unit, cache_dir, force_since=None):
    """Fetch and cache data for one station/grandeur combination."""
    filename = f"{station['code']}_{grandeur}.json"
    filepath = os.path.join(cache_dir, filename)

    existing_records, last_date = load_existing_cache(filepath)

    date_start = force_since
    if not date_start and last_date:
        date_start = last_date
        print(f"  Incremental update from {last_date}")

    raw_data = fetch_obs_elab(station["code"], grandeur, date_start)

    new_records = [simplify_record(r) for r in raw_data]

    if existing_records and date_start:
        existing_dates = {r["date"] for r in existing_records}
        merged = existing_records + [r for r in new_records if r["date"] not in existing_dates]
        merged.sort(key=lambda r: r["date"] or "")
    else:
        merged = new_records

    save_cache(filepath, station, grandeur, merged, unit)
    return len(merged)


def build_stations_index(stations, cache_dir):
    """Build a stations.json index file for the dashboard."""
    index = {
        "stations": stations,
        "updated_at": datetime.now().isoformat(),
    }
    filepath = os.path.join(cache_dir, "stations.json")
    os.makedirs(cache_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Saved stations index: {filepath}")


def fetch_river(river, station_code=None, since=None):
    """Fetch hydrometric data for every station of one river."""
    cache_dir = os.path.join(DATA_DIR, river["id"])
    os.makedirs(cache_dir, exist_ok=True)

    stations = river["stations"]
    if station_code:
        stations = [s for s in stations if s["code"] == station_code]
        if not stations:
            return 0  # this river does not own the requested station

    total_records = 0
    for station in stations:
        print(f"\n{'='*60}")
        print(f"[{river['name']}] Station: {station['name']} ({station['code']})")
        print(f"{'='*60}")

        print("  Fetching HIXnJ (daily max water height)...")
        total_records += fetch_station_data(station, "HIXnJ", "mm", cache_dir, force_since=since)

        if station["has_Q"]:
            print("  Fetching QmnJ (daily mean flow rate)...")
            total_records += fetch_station_data(station, "QmnJ", "L/s", cache_dir, force_since=since)
        else:
            print("  Skipping QmnJ (no flow rate data for this station)")

    build_stations_index(river["stations"], cache_dir)
    return total_records


def main():
    parser = argparse.ArgumentParser(description="Fetch river hydrological data (Hub'Eau)")
    parser.add_argument("--river", help="Fetch only this river id (e.g. orne, odon)")
    parser.add_argument("--station", help="Fetch only this station code")
    parser.add_argument("--since", help="Fetch data starting from this date (YYYY-MM-DD)")
    args = parser.parse_args()

    rivers = load_rivers()
    if args.river:
        rivers = [r for r in rivers if r["id"] == args.river]
        if not rivers:
            print(f"Unknown river id: {args.river}")
            print("Available rivers: " + ", ".join(r["id"] for r in load_rivers()))
            sys.exit(1)

    total_records = 0
    start_time = time.time()
    for river in rivers:
        total_records += fetch_river(river, station_code=args.station, since=args.since)

    elapsed = time.time() - start_time
    print(f"\nDone! {total_records:,} total records cached in {elapsed:.1f}s")
    print(f"Data directory: {DATA_DIR}")


if __name__ == "__main__":
    main()
