#!/usr/bin/env python3
"""
Fetch physicochemical water quality data from the Hub'Eau API v2 for the rivers
declared in config/rivers.json. For each river, discovers the top-3 best
documented quality stations (by SANDRE river code), then downloads O2, pH,
Nitrates, Nitrites and Ammonium measurements into data_cache/<river_id>/.

Usage:
    python3 scripts/fetch_quality_data.py                # all rivers, top-3 stations
    python3 scripts/fetch_quality_data.py --river odon   # one river
    python3 scripts/fetch_quality_data.py --discover     # list stations and exit
    python3 scripts/fetch_quality_data.py --since 2020-01-01  # incremental
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

BASE_URL = "https://hubeau.eaufrance.fr/api/v2/qualite_rivieres"

PARAMETERS = {
    "1311": {"name": "Oxygène dissous", "unit": "mg/L"},
    "1302": {"name": "pH", "unit": ""},
    "1340": {"name": "Nitrates", "unit": "mg/L NO₃"},
    "1339": {"name": "Nitrites", "unit": "mg/L NO₂"},
    "1335": {"name": "Ammonium", "unit": "mg/L NH₄"},
}
PARAM_CODES = list(PARAMETERS.keys())

TOP_N_STATIONS = 3
RATE_LIMIT_DELAY = 0.15
PAGE_SIZE = 5000


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


def discover_stations(quality_code):
    """Return all quality stations on a river, ranked by record count (5 target params)."""
    print(f"Discovering quality stations on river code {quality_code}...")
    params = urllib.parse.urlencode({"code_cours_eau": quality_code, "size": 200})
    url = f"{BASE_URL}/station_pc?{params}"
    result = fetch_json(url)
    stations = result.get("data", [])
    print(f"  Found {len(stations)} stations")

    ranked = []
    for i, st in enumerate(stations):
        code = st["code_station"]
        name = st.get("libelle_station", code)
        lon = st.get("longitude_station")
        lat = st.get("latitude_station")

        count_params = [
            ("code_station", code),
            ("code_parametre", "1311"),
            ("code_parametre", "1302"),
            ("code_parametre", "1340"),
            ("code_parametre", "1339"),
            ("code_parametre", "1335"),
            ("size", "1"),
        ]
        count_url = f"{BASE_URL}/analyse_pc?{urllib.parse.urlencode(count_params)}"
        print(f"  [{i+1}/{len(stations)}] {name[:40]:<40}", end="\r")
        try:
            res = fetch_json(count_url)
            count = res.get("count", 0)
        except Exception:
            count = 0
        time.sleep(RATE_LIMIT_DELAY)

        ranked.append({
            "code": code,
            "name": name,
            "longitude": lon,
            "latitude": lat,
            "total_records": count,
        })

    ranked.sort(key=lambda s: s["total_records"], reverse=True)
    print(f"\n  Ranking complete ({len(ranked)} stations evaluated)")
    return ranked


def fetch_parameter_records(station_code, param_code, date_start=None):
    """Fetch all records for one station/parameter, handling pagination."""
    params_list = [
        ("code_station", station_code),
        ("code_parametre", param_code),
        ("size", str(PAGE_SIZE)),
        ("sort", "asc"),
    ]
    if date_start:
        params_list.append(("date_debut_prelevement", date_start))

    url = f"{BASE_URL}/analyse_pc?{urllib.parse.urlencode(params_list)}"
    all_records = []
    page = 0

    while url:
        page += 1
        print(f"      Page {page} ({len(all_records)} records)...", end="\r")
        result = fetch_json(url)
        all_records.extend(result.get("data", []))
        url = result.get("next")
        if url:
            time.sleep(RATE_LIMIT_DELAY)

    print(f"      {len(all_records)} records fetched" + " " * 20)
    return all_records


def simplify_record(raw):
    """Keep only date and numeric value from a raw API record."""
    date_raw = raw.get("date_prelevement", "")
    return {
        "date": date_raw[:10] if date_raw else "",
        "value": raw.get("resultat"),
    }


def load_existing_cache(filepath):
    """Return {param_code: [records]} from an existing cache file, or {} if absent."""
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {code: pdata.get("records", []) for code, pdata in data.get("parameters", {}).items()}


def save_station_cache(filepath, station_info, parameters_data):
    """Write quality data for one station to JSON."""
    params_out = {}
    for code, records in parameters_data.items():
        meta = PARAMETERS[code]
        dates = [r["date"] for r in records if r.get("date")]
        params_out[code] = {
            "name": meta["name"],
            "unit": meta["unit"],
            "record_count": len(records),
            "date_min": min(dates) if dates else None,
            "date_max": max(dates) if dates else None,
            "records": records,
        }
    output = {
        "station_code": station_info["code"],
        "station_name": station_info["name"],
        "longitude": station_info.get("longitude"),
        "latitude": station_info.get("latitude"),
        "fetched_at": datetime.now().isoformat(),
        "parameters": params_out,
    }
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(filepath) / 1024
    print(f"    → {os.path.basename(filepath)} ({size_kb:.1f} KB)")


def fetch_station_quality(station_info, cache_dir, force_since=None):
    """Fetch and cache all 5 quality parameters for one station."""
    filepath = os.path.join(cache_dir, f"{station_info['code']}_quality.json")
    existing = load_existing_cache(filepath)

    parameters_data = {}
    for code in PARAM_CODES:
        meta = PARAMETERS[code]
        print(f"  Fetching {meta['name']} ({code})...")

        existing_records = existing.get(code, [])
        date_start = force_since
        if not date_start and existing_records:
            last_date = max((r["date"] for r in existing_records if r.get("date")), default=None)
            if last_date:
                date_start = last_date
                print(f"    Incremental update from {last_date}")

        raw = fetch_parameter_records(station_info["code"], code, date_start)
        new_records = [simplify_record(r) for r in raw]

        if existing_records and date_start:
            existing_dates = {r["date"] for r in existing_records}
            merged = existing_records + [r for r in new_records if r["date"] not in existing_dates]
            merged.sort(key=lambda r: r["date"] or "")
        else:
            merged = new_records

        parameters_data[code] = merged

    save_station_cache(filepath, station_info, parameters_data)


def build_quality_stations_index(stations, cache_dir):
    """Write quality_stations.json index for the dashboard."""
    index = {
        "stations": [
            {
                "code": s["code"],
                "name": s["name"],
                "longitude": s.get("longitude"),
                "latitude": s.get("latitude"),
                "total_records": s.get("total_records", 0),
            }
            for s in stations
        ],
        "updated_at": datetime.now().isoformat(),
    }
    filepath = os.path.join(cache_dir, "quality_stations.json")
    os.makedirs(cache_dir, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"Saved quality stations index: {filepath}")


def fetch_river_quality(river, discover_only=False, force_since=None):
    """Discover and fetch the top-N quality stations for one river."""
    print(f"\n{'#'*72}")
    print(f"# River: {river['name']} (quality code {river['quality_code']})")
    print(f"{'#'*72}")
    ranked = discover_stations(river["quality_code"])

    if discover_only:
        print(f"\n{'='*72}")
        print(f"{'#':<4} {'Records':>8}  {'Code':<22} Name")
        print(f"{'='*72}")
        for i, s in enumerate(ranked, 1):
            marker = f"  ← top {TOP_N_STATIONS}" if i <= TOP_N_STATIONS else ""
            print(f"  {i:<3} {s['total_records']:>8}  {s['code']:<22} {s['name']}{marker}")
        return

    top_stations = [s for s in ranked[:TOP_N_STATIONS] if s["total_records"] > 0]
    if not top_stations:
        print(f"No quality data found for any station on {river['name']}. Skipping.")
        return

    cache_dir = os.path.join(DATA_DIR, river["id"])
    os.makedirs(cache_dir, exist_ok=True)

    print(f"\nSelected top {len(top_stations)} stations:")
    for s in top_stations:
        print(f"  {s['code']} — {s['name']} ({s['total_records']} records across target params)")

    for station in top_stations:
        print(f"\n{'='*60}")
        print(f"Station: {station['name']} ({station['code']})")
        print(f"{'='*60}")
        fetch_station_quality(station, cache_dir, force_since=force_since)

    build_quality_stations_index(top_stations, cache_dir)


def main():
    parser = argparse.ArgumentParser(description="Fetch river water quality data (Hub'Eau)")
    parser.add_argument("--river", help="Fetch only this river id (e.g. orne, odon)")
    parser.add_argument(
        "--discover", action="store_true",
        help="List available quality stations ranked by record count, then exit",
    )
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD",
        help="Override incremental logic: fetch data starting from this date",
    )
    args = parser.parse_args()

    rivers = load_rivers()
    if args.river:
        rivers = [r for r in rivers if r["id"] == args.river]
        if not rivers:
            print(f"Unknown river id: {args.river}")
            print("Available rivers: " + ", ".join(r["id"] for r in load_rivers()))
            sys.exit(1)

    start_time = time.time()
    for river in rivers:
        fetch_river_quality(river, discover_only=args.discover, force_since=args.since)

    if not args.discover:
        elapsed = time.time() - start_time
        print(f"\nDone in {elapsed:.1f}s — data directory: {DATA_DIR}")


if __name__ == "__main__":
    main()
