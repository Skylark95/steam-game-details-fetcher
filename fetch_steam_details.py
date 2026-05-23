"""
fetch_steam_details.py
======================
Fetches game metadata for your entire Steam library from two sources:
  1. Steam Store API  (genres, categories, description, metacritic, etc.)
  2. SteamSpy API    (user-applied tags, player counts)

Output: steam_game_details.json  — appended/updated on every run.
        fetch_progress.json      — tracks which appids are done (resumability).

Rate limits:
  Steam Store API : ~200 requests / 5 min  → we target 1 req / 1.75s (safe margin)
  SteamSpy API    : ~4 requests / sec      → we target 1 req / 0.3s

Usage:
  1. Install deps:  pip install requests
  2. Place steam_library.json in the same directory as this script.
  3. Run:  python fetch_steam_details.py           # full library
           python fetch_steam_details.py --limit 5 # test first 5 games
  4. If interrupted, just run again — it picks up where it left off.
  5. When done, upload steam_game_details.json to your Claude project.

Estimated runtime for 5,678 games: ~2.5-3 hours (dominated by Steam rate limit).
"""

import json
import os
import time
import sys
import argparse
import requests
from datetime import datetime

# -- Config -------------------------------------------------------------------

LIBRARY_FILE  = "steam_library.json"
OUTPUT_FILE   = "steam_game_details.json"
PROGRESS_FILE = "fetch_progress.json"

STEAM_DELAY   = 1.75   # seconds between Steam API calls
STEAMSPY_DELAY = 0.35  # seconds between SteamSpy calls
RETRY_DELAY   = 60     # seconds to wait after a 429 / 403
MAX_RETRIES   = 5      # max retries per appid before skipping

STEAM_URL     = "https://store.steampowered.com/api/appdetails"
STEAMSPY_URL  = "https://steamspy.com/api.php"

# Fields we keep from Steam appdetails (everything else is discarded)
STEAM_KEEP = {
    "type", "name", "steam_appid", "required_age", "is_free",
    "short_description", "developers", "publishers",
    "platforms", "controller_support",
    "metacritic", "categories", "genres",
    "recommendations", "achievements",
    "release_date", "content_descriptors",
}

# -- Helpers ------------------------------------------------------------------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"  [warn] Could not parse {path}, starting fresh.")
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_with_retry(url, params, delay_after, label=""):
    """GET a URL, retrying on 429/403/5xx, honouring rate limits."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                time.sleep(delay_after)
                return resp
            elif resp.status_code in (429, 403):
                wait = RETRY_DELAY * attempt
                print(f"  [rate-limit {resp.status_code}] {label} -- waiting {wait}s ...")
                time.sleep(wait)
            elif resp.status_code >= 500:
                wait = 10 * attempt
                print(f"  [server error {resp.status_code}] {label} -- waiting {wait}s ...")
                time.sleep(wait)
            else:
                print(f"  [http {resp.status_code}] {label} -- skipping.")
                time.sleep(delay_after)
                return None
        except requests.exceptions.RequestException as e:
            wait = 10 * attempt
            print(f"  [network error] {label}: {e} -- waiting {wait}s ...")
            time.sleep(wait)
    print(f"  [give-up] {label} after {MAX_RETRIES} attempts.")
    return None


def fetch_steam(appid):
    """Fetch and trim Steam appdetails for one appid."""
    resp = fetch_with_retry(
        STEAM_URL,
        params={"appids": appid, "cc": "us", "l": "english"},
        delay_after=STEAM_DELAY,
        label=f"Steam/{appid}",
    )
    if resp is None:
        return None

    try:
        payload = resp.json()
    except ValueError:
        return None

    entry = payload.get(str(appid), {})
    if not entry.get("success"):
        return None

    raw = entry.get("data", {})
    trimmed = {k: v for k, v in raw.items() if k in STEAM_KEEP}

    trimmed["categories"] = [
        c["description"] for c in trimmed.get("categories", [])
    ]
    trimmed["genres"] = [
        g["description"] for g in trimmed.get("genres", [])
    ]

    if "metacritic" in trimmed:
        trimmed["metacritic_score"] = trimmed["metacritic"].get("score")
        del trimmed["metacritic"]

    if "recommendations" in trimmed:
        trimmed["recommendation_count"] = trimmed["recommendations"].get("total")
        del trimmed["recommendations"]

    if "achievements" in trimmed:
        trimmed["achievement_count"] = trimmed["achievements"].get("total")
        del trimmed["achievements"]

    if "release_date" in trimmed:
        rd = trimmed["release_date"]
        trimmed["release_date"] = rd.get("date", "")
        trimmed["coming_soon"] = rd.get("coming_soon", False)

    if "content_descriptors" in trimmed:
        trimmed["content_descriptor_ids"] = trimmed["content_descriptors"].get("ids", [])
        del trimmed["content_descriptors"]

    return trimmed


def fetch_steamspy(appid):
    """Fetch SteamSpy data (primarily tags) for one appid."""
    resp = fetch_with_retry(
        STEAMSPY_URL,
        params={"request": "appdetails", "appid": appid},
        delay_after=STEAMSPY_DELAY,
        label=f"SteamSpy/{appid}",
    )
    if resp is None:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    if not data or "appid" not in data:
        return None

    raw_tags = data.get("tags") or {}
    if isinstance(raw_tags, dict):
        tags = sorted(raw_tags, key=lambda t: raw_tags[t], reverse=True)
    else:
        tags = []

    return {
        "tags":             tags,
        "positive_reviews": data.get("positive"),
        "negative_reviews": data.get("negative"),
        "average_forever":  data.get("average_forever"),
        "median_forever":   data.get("median_forever"),
        "owners":           data.get("owners"),
    }


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch Steam game metadata.")
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only fetch this many games (useful for testing). "
             "Does not count already-fetched games."
    )
    args = parser.parse_args()

    if not os.path.exists(LIBRARY_FILE):
        print(f"ERROR: {LIBRARY_FILE} not found. Place it in the same directory.")
        sys.exit(1)

    print(f"Loading {LIBRARY_FILE} ...")
    library = load_json(LIBRARY_FILE, {})
    games   = library.get("response", {}).get("games", [])
    appids  = [g["appid"] for g in games]
    print(f"  {len(appids)} games in library.")

    output   = load_json(OUTPUT_FILE, {})
    progress = load_json(PROGRESS_FILE, {"done": [], "skipped": []})

    done_set    = set(progress["done"])
    skipped_set = set(progress["skipped"])
    remaining   = [a for a in appids if a not in done_set and a not in skipped_set]

    if args.limit:
        remaining = remaining[:args.limit]
        print(f"  [--limit {args.limit}] Test mode: fetching {len(remaining)} games only.")

    print(f"  {len(done_set)} already fetched, {len(skipped_set)} skipped, "
          f"{len(remaining)} to go.\n")

    total    = len(remaining)
    start_ts = time.time()

    for idx, appid in enumerate(remaining, 1):
        name = next((g["name"] for g in games if g["appid"] == appid), str(appid))
        print(f"[{idx}/{total}] {name} ({appid})")

        steam_data = fetch_steam(appid)
        spy_data   = fetch_steamspy(appid)

        if steam_data is None and spy_data is None:
            print(f"  -> no data from either source, skipping.")
            progress["skipped"].append(appid)
        else:
            record = {"appid": appid, "name": name}
            if steam_data:
                record.update(steam_data)
            if spy_data:
                record["tags"]             = spy_data.get("tags", [])
                record["positive_reviews"] = spy_data.get("positive_reviews")
                record["negative_reviews"] = spy_data.get("negative_reviews")
                record["avg_playtime_all"] = spy_data.get("average_forever")
                record["med_playtime_all"] = spy_data.get("median_forever")
                record["owners_estimate"]  = spy_data.get("owners")

            output[str(appid)] = record
            progress["done"].append(appid)

        save_json(OUTPUT_FILE, output)
        save_json(PROGRESS_FILE, progress)

        elapsed        = time.time() - start_ts
        per_game       = elapsed / idx
        remaining_secs = per_game * (total - idx)
        eta_h = int(remaining_secs // 3600)
        eta_m = int((remaining_secs % 3600) // 60)
        print(f"  ok  ETA: {eta_h}h {eta_m}m remaining")

    print(f"\nDone! {len(progress['done'])} fetched, {len(progress['skipped'])} skipped.")
    print(f"Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
