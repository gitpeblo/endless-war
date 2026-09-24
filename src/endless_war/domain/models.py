"""Core domain models.

Keep these objects independent from GTK and persistence implementation details.
"""

from collections import deque
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
    terrain: str = "plains"
    supply_value: float = 1.0
    is_capital: bool = False
    # (occupying faction, ticks held) while a walk-in capture is under way.
    occupation: tuple[int, int] | None = None


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
    at_war_with: set[int] = field(default_factory=set)
    casualties: int = 0
    exhaustion_casualty_mark: int = 0
    color_key: str = "grey"


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
    destination_id: int | None = None
    stance: str = "balanced"


@dataclass(slots=True)
class War:
    id: int
    attackers: set[int]
    defenders: set[int]
    started_at: datetime
    status: str = "active"
    last_capture_tick: int = 0


@dataclass(slots=True)
class Event:
    id: int
    simulated_at: datetime
    category: str
    severity: str
    title: str
    body: str
    related_entity_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CasualtyReading:
    """Every faction's cumulative casualties at one simulated instant.

    Frozen and built from tuples, so a view can share a reading instead of
    copying it.
    """

    simulated_at: datetime
    casualties: tuple[tuple[int, int], ...]  # (faction_id, cumulative), sorted by id


@dataclass(slots=True)
class WorldState:
    seed: int
    current_time: datetime
    tick_count: int = 0
    expected_province_count: int = 0
    provinces: dict[int, Province] = field(default_factory=dict)
    factions: dict[int, Faction] = field(default_factory=dict)
    armies: dict[int, Army] = field(default_factory=dict)
    wars: dict[int, War] = field(default_factory=dict)
    next_war_id: int = 0
    events: deque[Event] = field(default_factory=deque)
    next_event_id: int = 0
    casualty_history: list[CasualtyReading] = field(default_factory=list)
