from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class PlayerCreate(BaseModel):
    name: str = Field(default="Farmer", min_length=1, max_length=40)


class FarmCreate(BaseModel):
    name: str = Field(default="My farm", min_length=1, max_length=80)
    country: str = Field(min_length=2, max_length=120)
    region: str = Field(default="", max_length=120)
    crop: str = Field(min_length=2, max_length=80)
    biome: Literal["tropical", "desert", "tundra", "temperate", "steppe", "plains"]
    soil: Literal["clay", "sandy", "loam", "silt", "peat"]
    season: Literal["monsoon", "summer", "winter", "spring", "autumn"]
    size: Literal["small", "medium", "large"]
    water: Literal["limited", "rainfed", "irrigated", "waterlogged"]
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("name", "country", "crop")
    @classmethod
    def not_blank(cls, value: str):
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class BattleStart(BaseModel):
    farm_id: str | None = None
    farm: FarmCreate | None = None


class BattleMove(BaseModel):
    move: Literal["irrigate", "drainage", "mulch", "rotation"]


class PlantingCreate(BaseModel):
    farm_id: str
    crop: str = Field(min_length=2, max_length=80)
    planted_on: date
    note: str = Field(default="", max_length=500)


class PlantingEvent(BaseModel):
    kind: Literal["water", "fertilise", "inspect", "pest", "harvest", "note"]
    note: str = Field(default="", max_length=500)
    event_on: date = Field(default_factory=date.today)


class RotationRequest(BaseModel):
    crop: str = Field(min_length=2, max_length=80)
    history: list[str] = Field(default_factory=list, max_length=30)


class RotationRankRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    sequence_length: int = Field(default=3, ge=2, le=3)
    top_n: int = Field(default=5, ge=1, le=10)
    current_rotation: list[str] = Field(default_factory=list, max_length=5)
    priority_weights: dict[Literal["soil", "water", "resilience", "revenue"], float] = Field(default_factory=lambda: {"soil":0.3,"water":0.3,"resilience":0.15,"revenue":0.25})
