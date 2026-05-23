# Steam Game Details Fetcher

Fetches metadata for every game in your Steam library from the Steam Store API and SteamSpy, then saves it as `steam_game_details.json` for use with Claude project knowledge.

**Runtime:** ~2.5–3 hours for a 5,000+ game library (Steam rate limit is the bottleneck).  
**Cost:** Free — runs on GitHub Actions (2,000 free minutes/month on Linux runners).

---

## One-time setup

### 1. Enable workflow write permissions

In your repo on GitHub:

> **Settings → Actions → General → Workflow permissions**  
> Select **"Read and write permissions"** → Save

This lets the workflow commit `steam_game_details.json` back to your repo when done.

### 2. Upload your Steam library file

Add `steam_library.json` to the root of this repo (same level as `fetch_steam_details.py`) and push it.

Your library file should be exported from the Steam `GetOwnedGames` API and have the shape:
```json
{"response": {"game_count": N, "games": [...]}}
```

---

## Running the fetch

1. Go to the **Actions** tab in your repo
2. Click **"Fetch Steam Game Details"** in the left sidebar
3. Click **"Run workflow"** → **"Run workflow"**

The job will run for ~3 hours. You can watch live logs in the Actions tab.

When complete, `steam_game_details.json` will be:
- **Committed to your repo** (check the commit history)
- **Available as a downloadable artifact** on the Actions run page for 90 days

---

## Resumability

If the job is interrupted (timeout, network error, etc.), just run it again. It reads `fetch_progress.json` to skip games already processed and picks up where it left off.

---

## Output format

`steam_game_details.json` is keyed by appid (string):

```json
{
  "2868840": {
    "appid": 2868840,
    "name": "Slay the Spire 2",
    "type": "game",
    "genres": ["Strategy"],
    "categories": ["Single-player", "Full controller support"],
    "tags": ["Roguelike", "Deck Building", "Card Game", "Turn-Based"],
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
}
```

### Key fields for recommendations

| Field | Source | Notes |
|-------|--------|-------|
| `tags` | SteamSpy | User-applied tags sorted by votes — best signal for genre matching |
| `genres` | Steam | Official Steam genres (broader than tags) |
| `categories` | Steam | Features: "Single-player", "Full controller support", "Co-op", etc. |
| `metacritic_score` | Steam | 0–100, null if not rated |
| `recommendation_count` | Steam | Total Steam reviews (proxy for popularity) |
| `platforms.linux` | Steam | `true` is a strong Steam Deck compatibility signal |
| `controller_support` | Steam | `"full"` = Deck-friendly |

---

## Updating after buying new games

1. Re-export `steam_library.json` from the Steam API
2. Push the updated file to the repo
3. Run the workflow again — it only fetches games not already in `fetch_progress.json`

---

## Project knowledge instructions (add to Claude)

Once you've uploaded `steam_game_details.json` to your Claude project, add this note:

> **steam_game_details.json** — keyed by appid (string). Each entry contains: `type` (game/dlc/demo), `genres` (Steam official genres), `categories` (Steam feature flags e.g. "Full controller support"), `tags` (SteamSpy user tags sorted by vote count — most useful for recommendations), `metacritic_score` (int or null), `recommendation_count` (total Steam reviews), `positive_reviews`, `negative_reviews`, `release_date` (string), `platforms` (windows/mac/linux booleans — linux=true correlates with Steam Deck support), `controller_support` ("full"/"partial"/absent), `developers`, `publishers`, `is_free`, `avg_playtime_all` and `med_playtime_all` (minutes, across all owners), `owners_estimate` (range string), `achievement_count`.
