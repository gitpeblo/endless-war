"""Event log.

docs/superpowers/specs/02-ui-and-tray.md: only surface events that matter. The
thresholds here are the first line of defence against a log nobody can read.
"""

from __future__ import annotations

from typing import Any

from endless_war.domain.models import Event, WorldState

MAX_EVENTS = 2000


def _add(world: WorldState, category: str, severity: str, title: str,
         body: str, related: list[int]) -> None:
    world.events.append(Event(
        id=world.next_event_id,
        simulated_at=world.current_time,
        category=category,
        severity=severity,
        title=title,
        body=body,
        related_entity_ids=related,
    ))
    world.next_event_id += 1
    while len(world.events) > MAX_EVENTS:
        world.events.popleft()


def record_events(
    world: WorldState,
    config: dict[str, Any],
    battle_records: list[dict[str, Any]],
    capture_records: list[dict[str, Any]],
    diplomacy_events: list[dict[str, Any]],
    surrender_records: list[dict[str, Any]] = (),
) -> None:
    """Turn this tick's system records into history."""
    significant: int = config["balance"]["significant_battle_losses"]
    name = lambda fid: world.factions[fid].name if fid in world.factions else "unknown"  # noqa: E731

    for event in diplomacy_events:
        attacker, defender = event["attacker"], event["defender"]
        if event["kind"] == "war_declared":
            _add(world, "diplomacy", "critical", "War declared",
                 f"{name(attacker)} has declared war on {name(defender)}.",
                 [attacker, defender])
        elif event["kind"] == "peace":
            _add(world, "diplomacy", "critical", "Peace signed",
                 f"{name(attacker)} and {name(defender)} have signed a ceasefire.",
                 [attacker, defender])

    for capture in capture_records:
        _add(world, "territory", "major", "Province captured",
             f"{name(capture['to_faction'])} has taken "
             f"{world.provinces[capture['province_id']].name} from "
             f"{name(capture['from_faction'])}.",
             [capture["province_id"], capture["from_faction"], capture["to_faction"]])

    for surrender in surrender_records:
        _add(world, "military", "major", "Army surrendered",
             f"{name(surrender['faction'])}'s army of {surrender['men']:,} surrendered in "
             f"{world.provinces[surrender['province_id']].name}.",
             [surrender["province_id"], surrender["faction"]])

    for battle in battle_records:
        total = battle["attacker_losses"] + battle["defender_losses"]
        if total < significant:
            continue
        _add(world, "military", "major", "Major engagement",
             f"{total:,} casualties in {world.provinces[battle['province_id']].name} "
             f"between {name(battle['attacker_faction'])} and "
             f"{name(battle['defender_faction'])}.",
             [battle["province_id"]])
