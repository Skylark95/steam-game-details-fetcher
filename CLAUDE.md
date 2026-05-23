# Steam Game Details Fetcher — Claude Code Context

## What this project does
Fetches metadata for every game in a Steam library (`steam_library.json`) from two APIs:
- **Steam Store API** (`/api/appdetails`) — genres, categories, description, metacritic, platforms
- **SteamSpy API** — user-applied tags (best signal for recommendations), owner counts, review counts

Output is saved to `steam_game_details.json` (keyed by appid string) for upload to a Claude project to improve game recommendations.

## Key files
| File | Purpose |
|------|---------|
| `steam_library.json` | Source — full Steam library from GetOwnedGames API |
| `fetch_steam_details.py` | Main fetch script |
| `steam_game_details.json` | Output — created/updated by the script |
| `fetch_progress.json` | Resumability tracker — lists done/skipped appids |
| `.github/workflows/fetch_steam.yml` | GitHub Actions workflow (manual trigger) |

## Running the script

```bash
pip install requests

# Test with 5 games first
python fetch_steam_details.py --limit 5

# Full run (~2.5-3 hours)
python fetch_steam_details.py
```

The script is fully resumable — if interrupted, re-run and it skips already-processed appids.

## Rate limits
- Steam Store API: ~200 req / 5 min → script uses 1 req / 1.75s
- SteamSpy: ~4 req / sec → script uses 1 req / 0.35s
- On 429/403: backs off with exponential wait, up to 5 retries per game

## Output schema (per game)
```json
{
  "appid": 2868840,
  "name": "Slay the Spire 2",
  "type": "game",
  "genres": ["Strategy"],
  "categories": ["Single-player", "Full controller support"],
  "tags": ["Roguelike", "Deck Building", "Card Game"],
  "metacritic_score": null,
  "recommendation_count": 4821,
  "positive_reviews": 4600,
  "negative_reviews": 221,
  "release_date": "2025-05-01",
  "coming_soon": false,
  "platforms": {"windows": true, "mac": false, "linux": true},
  "controller_support": "full",
  "developers": ["Mega Crit"],
  "publishers": ["Mega Crit"],
  "is_free": false,
  "avg_playtime_all": 1820,
  "med_playtime_all": 940,
  "owners_estimate": "200,000 .. 500,000",
  "achievement_count": 40
}
```

## steam_library.json structure
Single-line JSON: `{"response": {"game_count": N, "games": [...]}}`.
Each game: `appid`, `name`, `playtime_forever` (mins), `playtime_2weeks` (mins, optional),
`rtime_last_played` (Unix timestamp, 0 if never), `playtime_windows/mac/linux/deck_forever`,
`img_icon_url`. Non-zero `playtime_deck_forever` = Steam Deck play.

## Common tasks for Claude Code
- **Check progress**: read `fetch_progress.json` — `done` and `skipped` arrays of appids
- **Inspect output**: `steam_game_details.json` keyed by appid string
- **Modify rate limits**: `STEAM_DELAY` and `STEAMSPY_DELAY` constants at top of script
- **Add new fields**: extend `STEAM_KEEP` set and/or the `fetch_steamspy()` return dict
- **Reset progress**: delete `fetch_progress.json` to start from scratch
