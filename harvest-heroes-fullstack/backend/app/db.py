"""Local SQLite persistence. Records are partitioned by bearer-token player identity."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("HARVEST_DB", Path(__file__).resolve().parents[2] / "data" / "harvest.sqlite3"))


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 10000")
    return con


@contextmanager
def session():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with session() as con:
        con.executescript("""
          CREATE TABLE IF NOT EXISTS players (
            id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS farms (
            id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
            name TEXT NOT NULL, country TEXT NOT NULL, region TEXT NOT NULL,
            crop TEXT NOT NULL, biome TEXT NOT NULL, soil TEXT NOT NULL,
            season TEXT NOT NULL, size TEXT NOT NULL, water TEXT NOT NULL,
            lat REAL, lon REAL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS battles (
            id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
            farm_id TEXT NOT NULL REFERENCES farms(id), threat TEXT NOT NULL,
            why_json TEXT NOT NULL, eh INTEGER NOT NULL DEFAULT 100,
            ph INTEGER NOT NULL DEFAULT 90, pp_json TEXT NOT NULL,
            turn INTEGER NOT NULL DEFAULT 0, good INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
            farm_id TEXT NOT NULL REFERENCES farms(id), battle_id TEXT NOT NULL UNIQUE REFERENCES battles(id),
            content_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS plantings (
            id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
            farm_id TEXT NOT NULL REFERENCES farms(id), crop TEXT NOT NULL,
            planted_on TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS planting_events (
            id TEXT PRIMARY KEY, planting_id TEXT NOT NULL REFERENCES plantings(id),
            player_id TEXT NOT NULL REFERENCES players(id), kind TEXT NOT NULL,
            note TEXT NOT NULL, event_on TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE TABLE IF NOT EXISTS environment_cache (
            cache_key TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
          );
          CREATE INDEX IF NOT EXISTS idx_farms_owner ON farms(player_id);
          CREATE INDEX IF NOT EXISTS idx_plans_owner ON plans(player_id);
          CREATE INDEX IF NOT EXISTS idx_plantings_owner ON plantings(player_id);
        """)


def row_obj(row):
    return dict(row) if row is not None else None


def row_with_json(row, *fields):
    item = row_obj(row)
    if item is not None:
        for field in fields:
            item[field.removesuffix("_json")] = json.loads(item.pop(field))
    return item
