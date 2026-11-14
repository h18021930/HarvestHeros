# API contract and architecture

API base: `/api`. Run the app, then open `/docs` for generated OpenAPI descriptions and example request bodies.

| Method | Path | Token? | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | No | Service health |
| GET | `/config` | No | Crops, biomes, moves, monsters |
| POST | `/players` | No | Create a player, returns one-time private access token |
| GET | `/me` | Yes | Player level, wins and XP |
| POST / GET | `/farms` | Yes | Save or list farms |
| GET | `/crops`, `/crops/{key}` | No | Crop education catalogue |
| POST | `/battles/start` | Yes | Create a battle for a saved farm or new farm |
| POST | `/battles/{id}/moves` | Yes | Validate and execute a battle move |
| GET | `/plans`, `/plans/{id}` | Yes | Persisted unlocked field plans |
| POST | `/rotation` | No | Crop-family rotation advice |
| POST | `/rotations/rank` | Yes | Tsuyu-inspired, historical weather/soil rotation ranking |
| POST / GET | `/plantings` | Yes | Create planting or list stage estimates |
| POST | `/plantings/{id}/events` | Yes | Log field-care activity |
| GET | `/environment?lat=...&lon=...` | Yes | Cached historical NASA POWER daily-data summary |

## Engine design

- **Threat scoring:** biome, season, soil, water availability, crop type drive deterministic points for drought, flood, frost, heat, and pest. The highest risk becomes the creature (not a scientific field-risk estimate).
- **Turn resolution:** server stores HP, PP, turn, win state and XP. Battle completion is a one-way transition with plan creation in the same SQLite transaction, preventing double-awards.
- **Planning:** curated threat action templates are combined with soil- and crop-specific guidance and a crop-family rotation suggestion.
- **Plant tracker:** server computes dated stage boundaries from a catalogue of general approximate crop durations, not from remote weather observations.
- **Historical data:** NASA POWER endpoint is optional and separate from battle simulation. Missing remote observations return 503, not invented numbers.

## Demo identity/security

A random bearer token is issued once at player creation, stored in the user's browser and hashed in the database. Requests are owner-scoped; sharing the token shares account access. This is a prototype identity system, not a substitute for real user accounts, encryption at rest, rate limiting, operational secrets management, or production deployment hardening.

## Tsuyu branch reference

The repository has a `data_science_tsuyu` branch with `backend/app/engine/{candidates,climate_suitability,evapotranspiration,rotation_scoring}.py`, NASA POWER and SoilGrids clients and `data/crops.json`. This local package adapts those methods in `backend/app/engine/ranking.py` and `data/rotation-crops.json` to fit the battle-first application and keeps the more basic `/api/rotation` endpoint as an offline option.

`/api/rotations/rank` uses a 365-day window ending 14 days ago, tests candidate temperature suitability in rolling crop-length growing windows, estimates daily reference ET0 with an assumed 300m elevation and FAO-56 Penman-Monteith variables, then computes ETc using crop Kc stages. Ranking combines soil, water, resilience and a *yield-only* revenue proxy with user-adjustable weights. It compares selected rotations against a continuous-maize baseline, including nitrogen balance (kg/ha), water demand difference (mm) and uncovered-ground days. **These indicators are not actual fertiliser reductions, real profit, soil loss or field-level predictions**; see returned risks and gaps. SoilGrids topsoil measurements may be missing or spatially coarse; the absence is labelled rather than presented as a measurement.
