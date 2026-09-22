"""Core domain models.

Keep these objects independent from GTK and persistence implementation details.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Province:
    id: int
    name: str
    owner_faction_id: int | None = None
    controller_faction_id: int | None = None
    neighbors: list[int] = field(default_factory=list)
    population: int = 0
    industry: float = 0.0
    infrastructure: float = 1.0


@dataclass(slots=True)
class Faction:
    id: int
    name: str
    capital_province_id: int
    treasury: float = 0.0
    manpower: int = 0
    stability: float = 1.0
    war_support: float = 0.5
    exhaustion: float = 0.0


@dataclass(slots=True)
class Army:
    id: int
    faction_id: int
    province_id: int
    manpower: int
    equipment: float = 1.0
    morale: float = 1.0
    organization: float = 1.0
    training: float = 1.0
    supply: float = 1.0


@dataclass(slots=True)
class WorldState:
    seed: int
    current_time: datetime
    tick_count: int = 0
    provinces: dict[int, Province] = field(default_factory=dict)
    factions: dict[int, Faction] = field(default_factory=dict)
    armies: dict[int, Army] = field(default_factory=dict)
