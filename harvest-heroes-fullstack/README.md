# 🌱 Harvest Heroes — Field Shift

An editable **VS Code** farming workspace with a preserved pixel-art challenge game. It combines the user's original pixel-art **Harvest Heroes** battle system with a Python **FastAPI** backend, an **SQLite** database, collectible crop cards, a location map, field plans, crop rotation suggestions and a planting tracker.

The referenced GitHub repository’s **`main`** branch contains documentation and a proposed architecture. Its separate **`data_science_tsuyu`** branch contains a working FastAPI agronomic rotation engine. This package builds the game around your uploaded pixel-art frontend and **adapts the Tsuyu-branch methodology and crop matrix** for location-aware rotation scoring (climate suitability, FAO-56 ET0, SoilGrids, crop-family constraints, multi-criteria scores and water/nitrogen/soil-cover implications). It is an independently integrated codebase, not a byte-for-byte copy of Tsuyu’s backend. No GitHub files were changed.

## Quick start — VS Code

1. Unzip this package and open the **`harvest-heroes-fullstack` folder** in VS Code (**File → Open Folder**).
2. Install Python 3.10+ (recommended Python 3.11+). In the VS Code terminal, run:

   **Windows (PowerShell):**

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r backend/requirements.txt
   python -m uvicorn app.main:app --reload --app-dir backend
   ```

   **macOS / Linux:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r backend/requirements.txt
   python -m uvicorn app.main:app --reload --app-dir backend
   ```

3. Open **http://127.0.0.1:8000** in your browser. All frontend files are served from the same backend; do **not** open `frontend/index.html` directly as a local file or use a standalone Live Server without a proxy.
4. Stop the server with **Ctrl+C**. Your progress persists in `data/harvest.sqlite3` (created automatically).

You can also use VS Code's **Terminal → Run Task → Run Harvest Heroes** after installing dependencies. API documentation is available at **http://127.0.0.1:8000/docs**.

## How to play

- **FARM:** Enter country, region, biome, crop, soil, season, farm size and water access. Start a Pokémon-inspired, turn-based battle against a challenge creature. Choose a helpful response (irrigation, drainage, mulch or crop rotation), earn XP and unlock a context-aware field plan.
- **LOCATION MAP:** Pan/zoom an interactive OpenStreetMap map and click to place a pin, or enter coordinates manually. With a pin selected, optionally request *historical* NASA POWER temperature and precipitation data (not forecasts). Map tiles require internet, but manual coordinate entry works offline.
- **CROP CARDS:** Browse original 32px crop pixel-art cards (including soybean) with soil, water, uses, facts and rough growth duration, including Tsuyu rotation crops.
- **TRACKER:** Select a saved farm, record a crop and planting date, see estimated germination/growth/flowering/harvest stages, and log waterings/inspections/other activities.
- **ROTATION:** Enter the crop and previous plantings to see alternate crop families. If you select a map pin and have internet, **RANK WITH HISTORICAL DATA** compares three-year sequences using the Tsuyu-inspired scoring model, NASA POWER historical weather and optional SoilGrids topsoil measurements, including relative soil/water/resilience/yield scores, nitrogen and water implications, and uncertainty notices.
- **SAVED / JOURNAL:** Revisit your saved farms and plans; view discovered monsters and biome stamps. Your browser holds a private access code identifying your records. Use **SAVED → COPY MY ACCESS CODE** to restore progress on another device. Anyone who holds the code can access those records, so do not publish it.

## Project structure

```text
harvest-heroes-fullstack/
├── frontend/
│   ├── index.html        # screens, game layout, accessible controls
│   ├── style.css         # original battle visuals + new retro UI
│   ├── script.js         # original user-provided monster sprites, world art, game logic
│   └── extra.js          # API integration, crop cards, map, tracker, saved farms
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI routes and NASA POWER history endpoint
│   │   ├── db.py         # SQLite schema and persistence
│   │   ├── schemas.py    # validated request models
│   │   ├── catalog.py    # crops, threat rules, battle moves, field advice
│   │   └── engine/ranking.py # adapted Tsuyu methodology / advanced scoring
│   ├── tests/test_app.py
│   └── requirements.txt
├── data/rotation-crops.json # adapted Tsuyu agronomic matrix
├── data/                 # runtime DB goes here, ignored by Git
├── docs/api-contract.md
└── .vscode/tasks.json
```

## API and farming data

- Open `/docs` for interactive FastAPI endpoint documentation.
- For example, `POST /api/players` creates a private player token. Subsequent user endpoints require `Authorization: Bearer <token>`.
- `POST /api/battles/start` saves a farm and creates a server-side battle; `POST /api/battles/{id}/moves` applies server-calculated damage, PP, XP and plan unlocks. Replaying a completed battle cannot award XP twice.
- `POST /api/plantings` and `POST /api/plantings/{id}/events` save growing and care records; the timeline is an educational duration estimate.
- `GET /api/environment?lat=...&lon=...` requests recent **historical** NASA POWER gridded temperature/precipitation. `POST /api/rotations/rank` requests one full year of NASA POWER data, optionally obtains ISRIC SoilGrids 0–5cm soil estimates, calculates FAO-56-style ET0 and ranks climate-suitable three-year rotations. NASA POWER is required for advanced ranking; failed remote requests return an error rather than fabricated data. If SoilGrids is unavailable, an explicitly flagged neutral carbon estimate is used. This does not integrate NASA SMAP.

## Tests

```bash
python -m pytest backend/tests -q
```

On some Python environments, set `PYTHONPATH=backend` first if `app` cannot be imported. From the `backend/` folder you can also run `python -m pytest tests -q`.

## Important limitations

- The game deliberately models **possible farming challenges**, *not* a prediction based on live local weather or measured soil. The risk score is deterministic and based on user choices. All field advice should be verified against regional agriculture guidance.
- Growth timelines are general illustrative averages, not crop-calibrated forecasts or reminders. For perennial dates, the duration is a sample fruiting cycle, not seed-to-first-harvest.
- Authentication is a **bearer-code demo system**; use proper login/roles, HTTPS, backups, access controls, and privacy/legal review before hosting real users or sensitive farm data. The SQLite implementation is designed for local/demo use.
- Leaflet/OSM map tiles are fetched via a public CDN and internet connection. For a wholly offline map, bundle local map tiles and Leaflet libraries under the relevant licences.
- No application deployment or GitHub push is included. Open this folder in VS Code, test locally, and commit it to a repository when ready.

## Credits

The pixel battle, canvas-based sprites, biome scenes, and original core visuals come from the user's uploaded Harvest Heroes files. The new crops, UI and server implementation were created for this project. The `data_science_tsuyu` branch of `ada-th25/nasa-field-shift-crop-rotation` contributed the agronomic approach and crop parameter values used for the adapted rotation-analysis engine. NASA POWER and ISRIC SoilGrids are optional public remote data sources; OpenStreetMap contributors provide map tiles.


## Farmer dashboard, NASA data, instructions, and reset

Open **DASHBOARD** for saved field counts, recent planting activity, and a real NASA POWER historical weather summary for a saved geolocated field. Choose a location in **LOCATION MAP** or select a field that was saved with coordinates. The NASA POWER API is called by the FastAPI backend through `GET /api/environment`, returning recent historical estimates for 2m air temperature and cumulative precipitation. It requires internet access; missing data produces an error rather than fabricated values. These are **not forecasts**, crop-health satellite imagery, or in-field sensor measurements. The climate-based rotation tool already also uses NASA POWER with optional ISRIC SoilGrids estimates.

Use **INSTRUCTIONS** for an in-app walkthrough of mapping, NASA data, field activity logging, rotation advice, gaming, profile recovery and resetting.

Under **SAVED**, choose **RESET GAME PROGRESS** to clear only this profile's battles, unlocked plans, XP and victories. Field definitions, plantings, and field activity logs remain intact. **RESET EVERYTHING** also removes this profile's fields, plantings and events. Both options require two browser confirmations and cannot be undone; they do not delete other players' data. API: authenticated `POST /api/progress/reset?scope=game` or `?scope=all`. Back up important records before resetting.
