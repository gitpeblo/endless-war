"""Turn live world state into an immutable view.

This is the only place where simulation objects become view data. A view that
needs a field it does not carry extends the view model here, rather than a
consumer reaching into WorldState.
"""

from __future__ import annotations

from typing import Any

from endless_war.app.view_model import EventLine, FactionRow, ProvinceCell, WorldView
from endless_war.domain.models import WorldState
from endless_war.simulation.systems.movement import hostile_armies_in

RECENT_EVENT_LIMIT = 12


def _province_cells(
    world: WorldState, low_supply_threshold: float
) -> tuple[ProvinceCell, ...]:
    occupied: dict[int, bool] = {}
    armies_here: dict[int, bool] = {}
    for aid in sorted(world.armies):
        armies_here[world.armies[aid].province_id] = True

    cells = []
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        controller = province.controller_faction_id
        contested = controller != province.owner_faction_id
        if not contested and controller is not None:
            contested = bool(hostile_armies_in(world, pid, controller))
        occupied[pid] = contested
        color = (
            world.factions[controller].color_key
            if controller in world.factions
            else "grey"
        )
        cells.append(
            ProvinceCell(
                id=pid,
                name=province.name,
                owner_faction_id=province.owner_faction_id,
                controller_faction_id=controller,
                color_key=color,
                is_capital=province.is_capital,
                is_contested=contested,
                has_armies=armies_here.get(pid, False),
                has_supply_problem=province.supply_value < low_supply_threshold,
            )
        )
    return tuple(cells)


def _faction_rows(world: WorldState) -> tuple[FactionRow, ...]:
    controlled: dict[int, list[int]] = {fid: [] for fid in sorted(world.factions)}
    for pid in sorted(world.provinces):
        controller = world.provinces[pid].controller_faction_id
        if controller in controlled:
            controlled[controller].append(pid)

    rows = []
    for fid in sorted(world.factions):
        faction = world.factions[fid]
        mine = controlled[fid]
        rows.append(
            FactionRow(
                id=fid,
                name=faction.name,
                color_key=faction.color_key,
                provinces=len(mine),
                population=sum(world.provinces[pid].population for pid in mine),
                manpower=faction.manpower,
                treasury=faction.treasury,
                casualties=faction.casualties,
                exhaustion=faction.exhaustion,
                war_support=faction.war_support,
                stability=faction.stability,
                at_war_with=tuple(sorted(faction.at_war_with)),
            )
        )
    return tuple(rows)


def _recent_events(world: WorldState) -> tuple[EventLine, ...]:
    window = list(world.events)[-RECENT_EVENT_LIMIT:]
    return tuple(
        EventLine(
            id=event.id,
            simulated_at=event.simulated_at,
            category=event.category,
            severity=event.severity,
            title=event.title,
            body=event.body,
        )
        for event in window
    )


def build_view(
    world: WorldState,
    config: dict[str, Any],
    *,
    bound_faction_id: int | None,
    speed: str,
    fault_message: str | None = None,
) -> WorldView:
    """Snapshot `world`. The result shares no mutable object with it."""
    return WorldView(
        simulated_at=world.current_time,
        tick_count=world.tick_count,
        speed=speed,
        faulted=fault_message is not None,
        fault_message=fault_message,
        bound_faction_id=bound_faction_id,
        provinces=_province_cells(world, config["balance"]["low_supply_threshold"]),
        factions=_faction_rows(world),
        recent_events=_recent_events(world),
        active_wars=sum(1 for w in world.wars.values() if w.status == "active"),
        total_wars=len(world.wars),
    )
