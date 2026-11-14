import os
import tempfile
from pathlib import Path

os.environ["HARVEST_DB"] = str(Path(tempfile.mkdtemp()) / "test.sqlite")
from fastapi.testclient import TestClient
from app.main import app

FARM = {"name": "Demo field", "country": "Wales", "region": "Cardiff", "crop": "soybean", "biome": "temperate", "soil": "loam", "season": "summer", "size": "small", "water": "rainfed"}


def test_complete_game_and_persistence():
    with TestClient(app) as client:
        p = client.post("/api/players", json={"name": "Tester"})
        assert p.status_code == 201
        headers = {"Authorization": "Bearer " + p.json()["token"]}
        r = client.post("/api/battles/start", json={"farm": FARM}, headers=headers)
        assert r.status_code == 201, r.text
        battle = r.json()
        assert battle["threat"] in ["drought", "flood", "frost", "heat", "pest"]
        best = battle["monster"]["weak_to"]
        outcome = None
        for _ in range(5):
            r = client.post(f"/api/battles/{battle['id']}/moves", json={"move": best}, headers=headers)
            assert r.status_code == 200, r.text
            outcome = r.json()
            if outcome["status"] != "active":
                break
        assert outcome["status"] == "won"
        assert outcome["plan"]
        assert client.get("/api/me", headers=headers).json()["xp"] == 50
        assert len(client.get("/api/plans", headers=headers).json()) == 1
        assert client.post(f"/api/battles/{battle['id']}/moves", json={"move": best}, headers=headers).status_code == 409
        farm_id = battle["farm"]["id"]
        planted = client.post("/api/plantings", json={"farm_id": farm_id, "crop": "soybean", "planted_on": "2026-09-01"}, headers=headers)
        assert planted.status_code == 201, planted.text
        pid = planted.json()["id"]
        event = client.post(f"/api/plantings/{pid}/events", json={"kind": "water", "note": "Irrigated"}, headers=headers)
        assert event.status_code == 201
        assert len(client.get("/api/plantings", headers=headers).json()[0]["events"]) == 1
        assert client.get("/api/farms").status_code == 401
        other = client.post("/api/players", json={"name": "Another"}).json()["token"]
        outsider = {"Authorization": "Bearer " + other}
        assert client.get("/api/plans", headers=outsider).json() == []
        assert client.post("/api/plantings", json={"farm_id": farm_id, "crop": "soybean", "planted_on": "2026-09-01"}, headers=outsider).status_code == 404


def test_catalogue_and_rotation():
    with TestClient(app) as client:
        assert "soybean" in client.get("/api/crops").json()["crops"]
        result = client.post("/api/rotation", json={"crop": "potatoes", "history": ["tomatoes"]}).json()
        assert result["previous_same_family"] == ["tomatoes"]
        assert all(item["family"] != "Solanaceae" for item in result["alternatives"])
