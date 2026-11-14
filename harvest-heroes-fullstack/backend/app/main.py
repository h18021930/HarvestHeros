"""Harvest Heroes API: saved farms, authoritative battles, field plans and plant tracking."""
import hashlib
import json
import os
import random
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalog import BIOMES, CROPS, GUIDANCE, MOVES, SOIL_BONUS, THREATS, crop_key, make_plan, rotation_advice, threat_for, timeline
from .db import init_db, row_obj, session
from .schemas import BattleMove, BattleStart, FarmCreate, PlantingCreate, PlantingEvent, PlayerCreate, RotationRequest, RotationRankRequest
from .engine.ranking import rank_rotations as rank_climate_rotations

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Harvest Heroes", version="1.0.0", lifespan=lifespan,
              description="Field management, NASA POWER historical observations, and optional pixel farming challenges")
origins = [s.strip() for s in os.environ.get("HARVEST_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])


def new_id() -> str:
    return str(uuid.uuid4())


def player(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "A player token is required; create a player first")
    token = authorization.removeprefix("Bearer ").strip()
    if len(token) < 30:
        raise HTTPException(401, "Invalid player token")
    with session() as con:
        row = con.execute("SELECT id,name,xp,wins,created_at FROM players WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row is None:
        raise HTTPException(401, "Invalid player token")
    return dict(row)


def get_farm(con, farm_id: str, user_id: str):
    row = con.execute("SELECT * FROM farms WHERE id=? AND player_id=?", (farm_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Farm not found")
    return dict(row)


def create_farm(con, user_id: str, farm: FarmCreate):
    farm_id = new_id()
    data = farm.model_dump()
    con.execute("INSERT INTO farms(id, player_id, name, country, region, crop, biome, soil, season, size, water, lat, lon) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (farm_id, user_id, *(data[x] for x in ("name", "country", "region", "crop", "biome", "soil", "season", "size", "water", "lat", "lon"))))
    return get_farm(con, farm_id, user_id)


@app.get("/api/health")
def health():
    return {"ok": True, "api": "Harvest Heroes 1.0", "storage": "sqlite"}


@app.get("/api/config")
def config():
    return {"biomes": BIOMES, "threats": THREATS, "moves": list(MOVES), "crops": CROPS}


@app.post("/api/players", status_code=201)
def create_player(data: PlayerCreate):
    user_id, token = new_id(), secrets.token_urlsafe(40)
    with session() as con:
        con.execute("INSERT INTO players(id,token_hash,name) VALUES(?,?,?)", (user_id, hashlib.sha256(token.encode()).hexdigest(), data.name.strip()))
    return {"token": token, "player": {"id": user_id, "name": data.name.strip(), "xp": 0, "wins": 0, "level": 1}}


@app.get("/api/me")
def me(user=Depends(player)):
    return {**user, "level": 1 + user["xp"] // 100}


@app.post("/api/progress/reset")
def reset_progress(scope: str = Query(pattern="^(game|all)$"), user=Depends(player)):
    """Reset only the authenticated profile; game-only retains agronomic records."""
    with session() as con:
        uid = user["id"]
        con.execute("DELETE FROM plans WHERE player_id=?", (uid,))
        con.execute("DELETE FROM battles WHERE player_id=?", (uid,))
        con.execute("UPDATE players SET xp=0, wins=0 WHERE id=?", (uid,))
        if scope == "all":
            con.execute("DELETE FROM planting_events WHERE player_id=?", (uid,))
            con.execute("DELETE FROM plantings WHERE player_id=?", (uid,))
            con.execute("DELETE FROM farms WHERE player_id=?", (uid,))
    return {
        "reset": scope, "xp": 0, "wins": 0,
        "farming_records_preserved": scope == "game",
        "message": "Game progress reset. Field and crop records retained." if scope == "game" else "All records for this profile were reset."
    }


@app.post("/api/farms", status_code=201)
def save_farm(data: FarmCreate, user=Depends(player)):
    with session() as con:
        return create_farm(con, user["id"], data)


@app.get("/api/farms")
def farms(user=Depends(player)):
    with session() as con:
        return [dict(row) for row in con.execute("SELECT * FROM farms WHERE player_id=? ORDER BY created_at DESC", (user["id"],))]


@app.get("/api/crops")
def crops():
    return {"crops": CROPS, "disclaimer": "Growth stages are illustrative estimates and not local forecasts."}


@app.get("/api/crops/{key}")
def crop_info(key: str):
    info = CROPS.get(crop_key(key))
    if not info:
        raise HTTPException(404, "Crop not found")
    return info


@app.post("/api/battles/start", status_code=201)
def start_battle(body: BattleStart, user=Depends(player)):
    if not body.farm and not body.farm_id:
        raise HTTPException(422, "Provide a farm or farm_id")
    with session() as con:
        farm = create_farm(con, user["id"], body.farm) if body.farm else get_farm(con, body.farm_id, user["id"])
        threat, reasons = threat_for(farm)
        battle_id = new_id()
        pp = {name: 5 for name in MOVES}
        con.execute("INSERT INTO battles(id,player_id,farm_id,threat,why_json,pp_json) VALUES(?,?,?,?,?,?)", (battle_id, user["id"], farm["id"], threat, json.dumps(reasons), json.dumps(pp)))
    return {"id": battle_id, "farm": farm, "threat": threat, "monster": THREATS[threat], "why": reasons, "eh": 100, "ph": 90, "pp": pp, "status": "active"}


@app.post("/api/battles/{battle_id}/moves")
def battle_move(battle_id: str, body: BattleMove, user=Depends(player)):
    with session() as con:
        b = con.execute("SELECT * FROM battles WHERE id=? AND player_id=?", (battle_id, user["id"])).fetchone()
        if b is None:
            raise HTTPException(404, "Battle not found")
        if b["status"] != "active":
            raise HTTPException(409, "This battle has already finished")
        farm = get_farm(con, b["farm_id"], user["id"])
        pp = json.loads(b["pp_json"])
        if pp[body.move] <= 0:
            raise HTTPException(409, "That move has no PP remaining")
        pp[body.move] -= 1
        kind = b["threat"]
        dmg = max(1, MOVES[body.move][list(THREATS).index(kind)] + (5 if SOIL_BONUS[farm["soil"]] == body.move else 0) + random.randint(-3, 3))
        eh = max(0, b["eh"] - dmg)
        good = b["good"] + int(dmg >= 30)
        ph, turn, enemy_damage = b["ph"], b["turn"], 0
        status, plan = "active", None
        if eh == 0:
            status = "won"
            plan = make_plan(farm, kind)
            plan["why"] = json.loads(b["why_json"])
            plan["super_effective_moves"] = good
            con.execute("UPDATE players SET xp=xp+50, wins=wins+1 WHERE id=?", (user["id"],))
            con.execute("INSERT INTO plans(id,player_id,farm_id,battle_id,content_json) VALUES(?,?,?,?,?)", (new_id(), user["id"], b["farm_id"], battle_id, json.dumps(plan)))
        else:
            enemy_damage = random.randint(18, 24) if turn % 3 == 2 else random.randint(10, 16)
            ph = max(0, ph - enemy_damage)
            turn += 1
            if ph == 0 or not any(pp.values()):
                status = "lost"
        con.execute("UPDATE battles SET eh=?,ph=?,pp_json=?,turn=?,good=?,status=? WHERE id=?", (eh, ph, json.dumps(pp), turn, good, status, battle_id))
        p = con.execute("SELECT name,xp,wins FROM players WHERE id=?", (user["id"],)).fetchone()
    return {"id": battle_id, "threat": kind, "damage": dmg, "enemy_damage": enemy_damage, "enemy_attack": ["Sandstorm", "Water Drain", "Heat Wave"] if kind == "drought" else {"flood": ["Flash Flood", "Rising Tide", "Mudslide"], "frost": ["Blizzard", "Ice Spike", "Frozen Ground"], "heat": ["Scorching Sun", "Fire Burst", "Burning Soil"], "pest": ["Crop Infestation", "Root Damage", "Disease Spread"]}[kind], "eh": eh, "ph": ph, "pp": pp, "turn": turn, "good": good, "status": status, "plan": plan, "player": {"xp": p["xp"], "wins": p["wins"], "level": 1+p["xp"]//100}}


@app.get("/api/plans")
def list_plans(user=Depends(player)):
    with session() as con:
        rows = con.execute("SELECT id, farm_id, battle_id, content_json, created_at FROM plans WHERE player_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        return [{**dict(r), "content": json.loads(r["content_json"])} for r in rows]


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str, user=Depends(player)):
    with session() as con:
        row = con.execute("SELECT content_json FROM plans WHERE id=? AND player_id=?", (plan_id, user["id"])).fetchone()
    if row is None:
        raise HTTPException(404, "Plan not found")
    return json.loads(row["content_json"])


@app.post("/api/rotation")
def rotation(body: RotationRequest):
    return rotation_advice(body.crop, body.history)


@app.post("/api/plantings", status_code=201)
def plant(data: PlantingCreate, user=Depends(player)):
    if crop_key(data.crop) not in CROPS:
        raise HTTPException(422, "Choose a crop listed in the catalogue")
    try:
        progress = timeline(data.crop, data.planted_on.isoformat())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with session() as con:
        get_farm(con, data.farm_id, user["id"])
        planting_id = new_id()
        con.execute("INSERT INTO plantings(id, player_id, farm_id, crop, planted_on, note) VALUES(?,?,?,?,?,?)", (planting_id, user["id"], data.farm_id, crop_key(data.crop), data.planted_on.isoformat(), data.note))
    return {"id": planting_id, "farm_id": data.farm_id, "note": data.note, "timeline": progress}


@app.get("/api/plantings")
def plantings(user=Depends(player)):
    with session() as con:
        rows = [dict(row) for row in con.execute("SELECT * FROM plantings WHERE player_id=? ORDER BY created_at DESC", (user["id"],))]
        for row in rows:
            row["timeline"] = timeline(row["crop"], row["planted_on"])
            row["events"] = [dict(e) for e in con.execute("SELECT id,kind,note,event_on FROM planting_events WHERE planting_id=? AND player_id=? ORDER BY event_on DESC", (row["id"], user["id"]))]
    return rows


@app.post("/api/plantings/{planting_id}/events", status_code=201)
def add_event(planting_id: str, data: PlantingEvent, user=Depends(player)):
    with session() as con:
        row = con.execute("SELECT id FROM plantings WHERE id=? AND player_id=?", (planting_id, user["id"])).fetchone()
        if row is None:
            raise HTTPException(404, "Planting not found")
        eid = new_id()
        con.execute("INSERT INTO planting_events(id,planting_id,player_id,kind,note,event_on) VALUES(?,?,?,?,?,?)", (eid, planting_id, user["id"], data.kind, data.note, data.event_on.isoformat()))
    return {"id": eid, "planting_id": planting_id, "kind": data.kind, "note": data.note, "event_on": data.event_on.isoformat()}


@app.get("/api/environment")
async def environment(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), user=Depends(player)):
    """NASA POWER recent historical observations; never portrayed as real-time forecasts."""
    ending = date.today() - timedelta(days=14)
    beginning = ending - timedelta(days=30)
    key = f"{lat:.2f}:{lon:.2f}:{ending.isoformat()}"
    with session() as con:
        row = con.execute("SELECT payload_json FROM environment_cache WHERE cache_key=?", (key,)).fetchone()
    if row:
        return json.loads(row["payload_json"])
    params = {"parameters": "T2M,PRECTOTCORR", "community": "AG", "longitude": lon, "latitude": lat, "start": beginning.strftime("%Y%m%d"), "end": ending.strftime("%Y%m%d"), "format": "JSON"}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            result = await client.get("https://power.larc.nasa.gov/api/temporal/daily/point", params=params)
            result.raise_for_status()
            values = result.json()["properties"]["parameter"]
        temperatures = [float(v) for v in values["T2M"].values() if isinstance(v, (int, float)) and v > -900]
        rainfall = [float(v) for v in values["PRECTOTCORR"].values() if isinstance(v, (int, float)) and v >= 0]
        if not temperatures or not rainfall:
            raise ValueError("No valid environmental observations")
        payload = {"source": "NASA POWER", "start": beginning.isoformat(), "end": ending.isoformat(), "average_temperature_c": round(sum(temperatures)/len(temperatures), 1), "total_precipitation_mm": round(sum(rainfall), 1), "sample_count": len(temperatures), "note": "Historical gridded estimates; not live weather, soil moisture, a forecast or a field-level diagnosis."}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "NASA POWER historical data unavailable. Retry later; no observations have been invented.")
    with session() as con:
        con.execute("INSERT OR REPLACE INTO environment_cache(cache_key,payload_json) VALUES(?,?)", (key, json.dumps(payload)))
    return payload


@app.post("/api/rotations/rank")
async def climate_rank_rotations(body: RotationRankRequest, user=Depends(player)):
    """Tsuyu-inspired, location-aware rotation scoring from real historical remote data.

    This uses historical 365-day NASA POWER weather and SoilGrids topsoil values.
    It deliberately returns 503 if POWER observations cannot be obtained, rather
    than silently claiming that made-up weather or soil is measured data.
    """
    ending = date.today() - timedelta(days=14)
    beginning = ending - timedelta(days=365)
    key = f"advanced_power:{body.lat:.2f}:{body.lon:.2f}:{ending.isoformat()}"
    with session() as con:
        cached = con.execute("SELECT payload_json FROM environment_cache WHERE cache_key=?", (key,)).fetchone()
    raw = json.loads(cached["payload_json"]) if cached else None
    if raw is None:
        params = {"parameters": "T2M_MAX,T2M_MIN,T2M,RH2M,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR,GWETROOT,GWETTOP", "community": "AG", "longitude": body.lon, "latitude": body.lat, "start": beginning.strftime("%Y%m%d"), "end": ending.strftime("%Y%m%d"), "format": "JSON"}
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                response = await client.get("https://power.larc.nasa.gov/api/temporal/daily/point", params=params)
                response.raise_for_status()
                raw = response.json()["properties"]["parameter"]
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise HTTPException(503, "NASA POWER year-long historical weather data unavailable; advanced rotation ranking needs observations. The basic rotation planner still works.") from exc
        with session() as con:
            con.execute("INSERT OR REPLACE INTO environment_cache(cache_key,payload_json) VALUES(?,?)", (key,json.dumps(raw)))
    soil_key = f"soilgrids:{body.lat:.2f}:{body.lon:.2f}"
    with session() as con:
        cached_soil=con.execute("SELECT payload_json FROM environment_cache WHERE cache_key=?", (soil_key,)).fetchone()
    soil=json.loads(cached_soil["payload_json"]) if cached_soil else None
    if soil is None:
        soil={"clay_pct":None,"sand_pct":None,"ph":None,"soc_g_kg":None,"source":"SoilGrids unavailable"}
        try:
            query=[("lon", str(body.lon)), ("lat",str(body.lat)), ("depth","0-5cm"),("value","mean")]
            query.extend(("property", x) for x in ["clay", "sand", "phh2o", "soc"])
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response=await client.get("https://rest.isric.org/soilgrids/v2.0/properties/query", params=query)
                response.raise_for_status()
                layers=response.json()["properties"]["layers"]
            vals={}
            for layer in layers:
                depth=next((x for x in layer.get("depths",[]) if x.get("label")=="0-5cm"),None)
                raw_value=depth.get("values",{}).get("mean") if depth else None
                vals[layer["name"]]=None if raw_value is None else round(float(raw_value)*0.1,3)
            soil={"clay_pct":vals.get("clay"),"sand_pct":vals.get("sand"),"ph":vals.get("phh2o"),"soc_g_kg":vals.get("soc"),"source":"ISRIC SoilGrids surface topsoil (0-5 cm)"}
        except (httpx.HTTPError, KeyError, ValueError, TypeError, StopIteration):
            pass
        with session() as con:
            con.execute("INSERT OR REPLACE INTO environment_cache(cache_key,payload_json) VALUES(?,?)", (soil_key,json.dumps(soil)))
    try:
        weights={k:float(body.priority_weights.get(k,0)) for k in ("soil","water","resilience","revenue")}
        result=rank_climate_rotations(raw,soil,body.lat,sequence_length=body.sequence_length,top_n=body.top_n,weights=weights,current_rotation=body.current_rotation)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422,str(exc)) from exc
    return {**result,"weather_source":"NASA POWER historical daily values", "weather_period":{"start":beginning.isoformat(),"end":ending.isoformat()},"soil_source":soil.get("source")}


app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")
