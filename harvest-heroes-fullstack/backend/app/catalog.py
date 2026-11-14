"""Educational crop catalogue and recommendation rules (not a live agronomic diagnosis)."""
import re
from datetime import date, timedelta

THREATS = {
    "drought": {"name": "DROUGHTON", "type": "DROUGHT", "weak_to": "irrigate", "tip": "Mulch and efficient irrigation help retain soil moisture."},
    "flood": {"name": "FLOODRA", "type": "FLOOD", "weak_to": "drainage", "tip": "Keep roots aerated using suitable drainage and raised beds."},
    "frost": {"name": "FROSTHORN", "type": "FROST", "weak_to": "mulch", "tip": "Frost covers and insulation can protect vulnerable plants."},
    "heat": {"name": "PYRABLOOM", "type": "HEAT", "weak_to": "mulch", "tip": "Manage heat stress with shade, soil cover, and irrigation."},
    "pest": {"name": "ROOTROT", "type": "PEST", "weak_to": "rotation", "tip": "Monitor crops and rotate crop families to interrupt pest cycles."},
}
BIOMES = {"tropical": "Tropical Rainforest", "desert": "Desert", "tundra": "Icy Tundra", "temperate": "Temperate Countryside", "steppe": "Central Asian Steppe", "plains": "North American Plains"}
MOVES = {"irrigate": [34, 4, 8, 24, 8], "drainage": [8, 34, 16, 6, 14], "mulch": [20, 12, 30, 34, 10], "rotation": [10, 10, 12, 8, 34]}
SOIL_BONUS = {"clay": "drainage", "sandy": "mulch", "loam": "rotation", "silt": "irrigate", "peat": "drainage"}
CROPS = {
  "rice": {"name": "Rice", "family": "Poaceae", "days": 120, "stages": [12, 38, 44, 26], "stage_names": ["Germination", "Vegetative growth", "Flowering / grain fill", "Harvest"], "soil": "Clay or loam with controlled water", "water": "High; water management depends on cultivation method", "uses": "Staple food and animal feed", "fact": "Rice feeds billions of people worldwide.", "note": "Some rice systems benefit from alternate wetting and drying where locally appropriate."},
  "wheat": {"name": "Wheat", "family": "Poaceae", "days": 125, "stages": [10, 55, 35, 25], "stage_names": ["Germination", "Vegetative growth", "Flowering / grain fill", "Harvest"], "soil": "Well-drained loam", "water": "Moderate", "uses": "Flour, bread and cereals", "fact": "Wheat is one of the most widely cultivated cereals.", "note": "Cultivar and climate strongly affect growing duration."},
  "corn": {"name": "Maize", "family": "Poaceae", "days": 115, "stages": [8, 47, 35, 25], "stage_names": ["Germination", "Vegetative growth", "Flowering / grain fill", "Harvest"], "soil": "Well-drained fertile loam", "water": "High around tasselling and silking", "uses": "Food, feed and starch", "fact": "Maize is especially sensitive to water stress during flowering.", "note": "Monitor moisture closely when tassels and silks form."},
  "potatoes": {"name": "Potatoes", "family": "Solanaceae", "days": 105, "stages": [18, 37, 30, 20], "stage_names": ["Sprouting", "Leaf growth", "Tuber bulking", "Harvest"], "soil": "Loose, well-drained loam", "water": "Steady but avoid waterlogging", "uses": "Food and starch", "fact": "Potatoes form underground stem tubers.", "note": "Check for blight and use certified seed potatoes."},
  "tomatoes": {"name": "Tomatoes", "family": "Solanaceae", "days": 95, "stages": [9, 34, 27, 25], "stage_names": ["Germination", "Vegetative growth", "Flowering / fruiting", "Harvest"], "soil": "Fertile, well-drained loam", "water": "Even moisture; avoid splashing leaves", "uses": "Fresh food and sauces", "fact": "Tomatoes are botanically fruits.", "note": "Provide airflow and inspect for pests and diseases."},
  "soybean": {"name": "Soybean", "family": "Fabaceae", "days": 105, "stages": [8, 37, 35, 25], "stage_names": ["Emergence", "Leaf growth", "Flowering / pods", "Harvest"], "soil": "Well-drained loam", "water": "Moderate; important during flowering", "uses": "Tofu, oil, food and animal feed", "fact": "Soybeans are legumes that can form nitrogen-fixing associations.", "note": "Rotate with a different crop family to reduce disease pressure."},
  "barley": {"name": "Barley", "family": "Poaceae", "days": 100, "stages": [10, 40, 30, 20], "stage_names": ["Germination", "Vegetative growth", "Heading / grain fill", "Harvest"], "soil": "Well-drained loam", "water": "Moderate", "uses": "Food, animal feed and malt", "fact": "Barley is a cereal grown in a broad range of climates.", "note": "Avoid prolonged waterlogging."},
  "cotton": {"name": "Cotton", "family": "Malvaceae", "days": 155, "stages": [10, 65, 55, 25], "stage_names": ["Emergence", "Vegetative growth", "Flowering / bolls", "Harvest"], "soil": "Deep, well-drained loam", "water": "Moderate to high", "uses": "Natural fibre and cottonseed", "fact": "Cotton fibres grow around the seeds.", "note": "Check water and salinity in hot, dry climates."},
  "dates": {"name": "Date palm", "family": "Arecaceae", "days": 210, "stages": [30, 60, 80, 40], "stage_names": ["New growth", "Vegetative growth", "Flowering / fruiting", "Harvest"], "soil": "Well-drained sandy loam", "water": "Regular deep watering", "uses": "Sweet fruit", "fact": "Date palms are perennial trees, not annual crops.", "note": "Timeline represents an illustrative fruiting cycle, not time from seed to first harvest."},
  "oats": {"name":"Oats","family":"Poaceae","days":115,"stages":[9,42,39,25],"stage_names":["Germination","Leaf growth","Heading / grain fill","Harvest"],"soil":"Cool, well-drained loam","water":"Moderate","uses":"Porridge, feed and oat-based foods","fact":"Oats are cool-season cereals.","note":"Choose a local sowing window and watch for lodging."},
  "alfalfa": {"name":"Alfalfa","family":"Fabaceae","days":365,"stages":[35,115,140,75],"stage_names":["Establishment","Leaf growth","Flowering / cutting","Annual care"],"soil":"Deep, well-drained soil","water":"Moderate to high","uses":"Forage and soil cover","fact":"Alfalfa is a deep-rooted perennial legume.","note":"The stages show one illustrative management year, not establishment through removal."},
  "lentil": {"name":"Lentil","family":"Fabaceae","days":110,"stages":[10,42,36,22],"stage_names":["Emergence","Leaf growth","Flowers / pods","Harvest"],"soil":"Well-drained loam","water":"Low to moderate","uses":"High-protein food pulses","fact":"Lentils belong to the legume family.","note":"Avoid waterlogging and use appropriate disease management."},
  "chickpea": {"name":"Chickpea","family":"Fabaceae","days":120,"stages":[10,43,41,26],"stage_names":["Emergence","Leaf growth","Flowers / pods","Harvest"],"soil":"Well-drained soil","water":"Low to moderate","uses":"Food pulses, hummus and flour","fact":"Chickpeas develop a deep taproot.","note":"Select cultivars adapted to your local rain and heat pattern."},
  "sorghum": {"name":"Sorghum","family":"Poaceae","days":130,"stages":[9,53,43,25],"stage_names":["Emergence","Leaf growth","Heading / grain fill","Harvest"],"soil":"Well-drained loam","water":"Low to moderate","uses":"Grain, forage and food","fact":"Sorghum is known for its heat and drought tolerance.","note":"Check regional variety and sowing temperature guidance."},
  "cereal_rye_cover": {"name":"Cereal rye cover","family":"Poaceae","days":150,"stages":[12,58,52,28],"stage_names":["Establishment","Winter cover","Spring growth","Termination"],"soil":"Adaptable, well-drained soils","water":"Low to moderate","uses":"Soil cover and erosion control","fact":"Rye used as a cover crop may not be harvested for grain.","note":"Arrange termination timing carefully relative to the next crop."},
}
ALIASES = {"maize": "corn", "potato": "potatoes", "tomato": "tomatoes", "soybeans": "soybean", "date": "dates"}
GUIDANCE = {
 "drought": ["Use moisture checks and efficient irrigation methods where available.", "Cover soil with appropriate mulch and add organic matter to improve water retention.", "Select locally suitable drought-resilient varieties and align planting with rainfall."],
 "flood": ["Improve suitable field drainage or raised beds to protect roots from prolonged saturation.", "Avoid traffic on wet soils and inspect for root disease after flooding.", "Use buffer strips and maintain drainage routes to reduce erosion."],
 "frost": ["Check local frost forecasts and protect vulnerable seedlings with suitable covers.", "Use soil cover and choose planting windows that avoid damaging late frost.", "Consider locally adapted cold-tolerant varieties."],
 "heat": ["Reduce heat stress with suitable shade, mulch and irrigation timing.", "Track crop development because flowering can be especially sensitive to heat.", "Select locally appropriate planting dates and heat-tolerant varieties."],
 "pest": ["Scout the field regularly and identify the organism before applying treatments.", "Rotate unrelated crop families and remove diseased material safely.", "Encourage beneficial insects and use locally approved integrated pest management."],
}


def crop_key(name: str) -> str:
    key = re.sub(r"\s+", " ", name.lower().strip())
    return ALIASES.get(key, key)


def timeline(crop: str, planted_on: str, today: date | None = None) -> dict:
    key = crop_key(crop)
    item = CROPS.get(key)
    if not item:
        raise ValueError("Unknown crop; choose one from the crop catalogue")
    start = date.fromisoformat(planted_on)
    today = today or date.today()
    days = (today - start).days
    elapsed = 0
    stages = []
    for name, duration in zip(item["stage_names"], item["stages"]):
        begin = start + timedelta(days=elapsed)
        elapsed += duration
        end = start + timedelta(days=elapsed)
        stages.append({"name": name, "start": begin.isoformat(), "end": end.isoformat(), "status": "complete" if today >= end else ("active" if today >= begin else "upcoming")})
    return {"crop": key, "planted_on": planted_on, "estimated_harvest": (start + timedelta(days=item["days"])).isoformat(), "days_elapsed": max(0, days), "days_remaining": max(0, item["days"] - days), "progress_percent": max(0, min(100, round(days * 100 / item["days"]))), "stages": stages, "disclaimer": "Illustrative estimates only; local variety, weather and farm practice change development dates."}


def threat_for(farm: dict) -> tuple[str, list[str]]:
    sc = {key: 0 for key in THREATS}
    reasons = {key: [] for key in THREATS}
    def add(table: dict, val: str, label: str):
        for key, score in table.get(val, []):
            sc[key] += score
            reasons[key].append(label)
    add({"tropical": [("flood", 2), ("pest", 2)], "desert": [("drought", 3), ("heat", 2)], "tundra": [("frost", 3)], "temperate": [("flood", 1), ("pest", 1)], "steppe": [("drought", 2), ("frost", 1)], "plains": [("drought", 1), ("heat", 1), ("pest", 1)]}, farm["biome"], "biome")
    add({"monsoon": [("flood", 3)], "summer": [("heat", 2), ("drought", 1)], "winter": [("frost", 3)], "spring": [("flood", 1), ("pest", 1), ("frost", 1)], "autumn": [("pest", 1), ("frost", 1)]}, farm["season"], "season")
    add({"clay": [("flood", 2)], "sandy": [("drought", 2)], "silt": [("flood", 1)], "loam": [("pest", 1)], "peat": [("flood", 1), ("frost", 1)]}, farm["soil"], "soil")
    add({"limited": [("drought", 3)], "rainfed": [("drought", 1), ("flood", 1)], "irrigated": [("pest", 1), ("heat", 1)], "waterlogged": [("flood", 3)]}, farm["water"], "water access")
    c = crop_key(farm["crop"])
    if c in ("rice",): add({"crop": [("flood", 2)]}, "crop", "crop choice")
    elif c in ("dates", "cotton"): add({"crop": [("drought", 1), ("heat", 1)]}, "crop", "crop choice")
    elif c in ("wheat", "barley"): add({"crop": [("frost", 1)]}, "crop", "crop choice")
    elif c in ("potatoes", "tomatoes"): add({"crop": [("pest", 1), ("flood", 1)]}, "crop", "crop choice")
    elif c in ("corn",): add({"crop": [("heat", 1), ("drought", 1)]}, "crop", "crop choice")
    top = max(sc, key=sc.get)
    return top, reasons[top]


def make_plan(farm: dict, threat: str) -> dict:
    item = CROPS.get(crop_key(farm["crop"]))
    risk = THREATS[threat]
    return {"title": f"Field plan: {farm['crop']} in {farm['region'] or farm['country']}", "threat": threat, "monster": risk["name"], "location": ", ".join(s for s in [farm["region"], farm["country"]] if s), "crop": farm["crop"], "soil": farm["soil"], "actions": GUIDANCE[threat], "soil_guidance": {"clay": "Clay can compact and waterlog; avoid working it when very wet.", "sandy": "Sandy soils lose water and nutrients quickly; add organic matter.", "loam": "Keep loam protected with living cover and organic matter.", "silt": "Keep silt covered to reduce crusting and erosion.", "peat": "Balance peat moisture and protect its carbon-rich structure."}[farm["soil"]], "crop_guidance": item["note"] if item else "Choose locally adapted cultivars and consult regional agricultural guidance.", "rotation": rotation_advice(farm["crop"], []), "disclaimer": "Educational simulation based on user selections. These are not measurements, diagnoses, local crop calendars or live forecasts. Seek regional agricultural advice before important decisions."}


def rotation_advice(crop: str, history: list[str]) -> dict:
    key = crop_key(crop)
    current = CROPS.get(key)
    family = current["family"] if current else "unknown"
    same = [name for name in history if CROPS.get(crop_key(name), {}).get("family") == family and family != "unknown"]
    choices = [dict(key=k, name=v["name"], family=v["family"]) for k, v in CROPS.items() if v["family"] != family]
    return {"current_crop": crop, "family": family, "previous_same_family": same, "alternatives": choices[:5], "advice": "Repeated planting within one family can increase pest or disease pressure. Rotate with a different family where suitable for the site, local season and market."}
