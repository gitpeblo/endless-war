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
from endless_war.simulation.systems.supply import INDUSTRIAL_SOURCE_THRESHOLD

RECENT_EVENT_LIMIT = 12


def _province_cells(
    world: WorldState, low_supply_threshold: float
) -> tuple[ProvinceCell, ...]:
    armies_here: dict[int, bool] = {}
    army_factions: dict[int, set[int]] = {}
    for aid in sorted(world.armies):
        army = world.armies[aid]
        armies_here[army.province_id] = True
        army_factions.setdefault(army.province_id, set()).add(army.faction_id)

    cells = []
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        controller = province.controller_faction_id
        contested = controller != province.owner_faction_id
        if not contested and controller is not None:
            contested = bool(hostile_armies_in(world, pid, controller))
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
                terrain=province.terrain,
                is_industrial=province.industry >= INDUSTRIAL_SOURCE_THRESHOLD,
                army_color_keys=tuple(
                    world.factions[fid].color_key
                    for fid in sorted(army_factions.get(pid, ()))
                    if fid in world.factions
                ),
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
                eliminated=faction.eliminated,
            )
        )
    return tuple(rows)


def _event_line(event) -> EventLine:
    return EventLine(
        id=event.id,
        simulated_at=event.simulated_at,
        category=event.category,
        severity=event.severity,
        title=event.title,
        body=event.body,
    )


def _event_log(world: WorldState, previous: WorldView | None) -> tuple[EventLine, ...]:
    """Every event, oldest first, reusing `previous`'s lines where it can.

    Converting 2000 events costs ~1.5 ms, too much to do every tick. Event ids
    are consecutive and `record_events` evicts only from the left, so the lines
    still present are a slice of the previous log and only events after its
    last id are new.
    """
    events = world.events
    if not events:
        return ()
    old = previous.event_log if previous is not None else ()
    first_id, last_id = events[0].id, events[-1].id
    if not old or old[0].id > first_id or old[-1].id > last_id:
        return tuple(_event_line(e) for e in events)
    new_count = last_id - old[-1].id
    if new_count >= len(events):
        return tuple(_event_line(e) for e in events)
    kept = old[first_id - old[0].id :]
    fresh = tuple(_event_line(events[i]) for i in range(len(events) - new_count, len(events)))
    return kept + fresh


def build_view(
    world: WorldState,
    config: dict[str, Any],
    *,
    bound_faction_id: int | None,
    speed: str,
    fault_message: str | None = None,
    previous: WorldView | None = None,
) -> WorldView:
    """Snapshot `world`. The result shares no mutable object with it.

    `previous`, if given, must be an earlier view of the same world; its event
    lines are reused rather than rebuilt.
    """
    event_log = _event_log(world, previous)
    return WorldView(
        simulated_at=world.current_time,
        tick_count=world.tick_count,
        speed=speed,
        faulted=fault_message is not None,
        fault_message=fault_message,
        bound_faction_id=bound_faction_id,
        provinces=_province_cells(world, config["balance"]["low_supply_threshold"]),
        factions=_faction_rows(world),
        recent_events=event_log[-RECENT_EVENT_LIMIT:],
        active_wars=sum(1 for w in world.wars.values() if w.status == "active"),
        total_wars=len(world.wars),
        casualty_history=tuple(world.casualty_history),
        event_log=event_log,
    )
