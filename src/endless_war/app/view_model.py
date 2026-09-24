"""Immutable view of the world, safe to read from another thread.

A view holds plain values only — never a reference to a live simulation object.
That is what lets the GTK thread read one while the simulation keeps mutating
its own state, with no lock and no possibility of a UI handler writing back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Re-exported so ui/ can import it from app/. It is frozen and built from
# tuples, so sharing it with the live world breaks nothing above.
from endless_war.domain.models import CasualtyReading  # noqa: F401


@dataclass(frozen=True, slots=True)
class ProvinceCell:
    """One province as the map needs it (docs/superpowers/specs/02-ui-and-tray.md)."""

    id: int
    name: str
    owner_faction_id: int | None
    controller_faction_id: int | None
    color_key: str
    is_capital: bool
    is_contested: bool
    has_armies: bool
    has_supply_problem: bool
    terrain: str
    is_industrial: bool  # a supply source, like a capital


@dataclass(frozen=True, slots=True)
class FactionRow:
    """One faction as the status panel and tray summary need it."""

    id: int
    name: str
    color_key: str
    provinces: int
    population: int
    manpower: int
    treasury: float
    casualties: int
    exhaustion: float
    war_support: float
    stability: float
    at_war_with: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EventLine:
    """One logged event, without its related-entity ids."""

    id: int
    simulated_at: datetime
    category: str
    severity: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class WorldView:
    """Everything a consumer may see about the world at one instant."""

    simulated_at: datetime
    tick_count: int
    speed: str
    faulted: bool
    fault_message: str | None
    bound_faction_id: int | None
    provinces: tuple[ProvinceCell, ...]
    factions: tuple[FactionRow, ...]
    recent_events: tuple[EventLine, ...]
    active_wars: int
    total_wars: int
    casualty_history: tuple[CasualtyReading, ...]
    event_log: tuple[EventLine, ...]
