"""War exhaustion, declarations, and peace.

specs/01-game-design.md requires that individual wars end while the world does
not. Peace triggers on mutual exhaustion or on a stalemate with no captures.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import War, WorldState
from endless_war.simulation.systems import clamp


def update_exhaustion(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Grow exhaustion from accumulated casualties; decay it in peacetime."""
    factor: float = config["balance"]["exhaustion_per_casualty_fraction"]
    decay: float = config["balance"]["exhaustion_decay_per_tick"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        new_casualties = fac.casualties - fac.exhaustion_casualty_mark
        fac.exhaustion_casualty_mark = fac.casualties
        if fac.at_war_with:
            army_strength = sum(
                a.manpower for a in world.armies.values() if a.faction_id == fid
            )
            base = max(1, fac.manpower + army_strength)
            fac.exhaustion = clamp(fac.exhaustion + (new_casualties / base) * factor)
        else:
            fac.exhaustion = clamp(fac.exhaustion - decay)
        fac.war_support = clamp(0.9 - fac.exhaustion * 0.8)
        fac.stability = clamp(fac.stability + (0.002 if not fac.at_war_with else -0.0005))


def note_captures(world: WorldState, capture_records: list[dict[str, Any]]) -> None:
    """Reset the stalemate timer of each active war in which a capture happened."""
    for capture in capture_records:
        taker, loser = capture["to_faction"], capture["from_faction"]
        for war_id in sorted(world.wars):
            war = world.wars[war_id]
            if war.status != "active":
                continue
            if (taker in war.attackers and loser in war.defenders) or (
                taker in war.defenders and loser in war.attackers
            ):
                war.last_capture_tick = world.tick_count


def _strength(world: WorldState, faction_id: int) -> float:
    army = sum(a.manpower for a in world.armies.values() if a.faction_id == faction_id)
    return army + world.factions[faction_id].manpower * 0.5


def _neighbouring_factions(world: WorldState, faction_id: int) -> list[int]:
    found: set[int] = set()
    for pid in sorted(world.provinces):
        prov = world.provinces[pid]
        if prov.controller_faction_id != faction_id:
            continue
        for nid in prov.neighbors:
            other = world.provinces[nid].controller_faction_id
            if other is not None and other != faction_id:
                found.add(other)
    return sorted(found)


def update_diplomacy(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Declare new wars and end exhausted or stalemated ones."""
    ratio_needed: float = config["balance"]["war_declaration_strength_ratio"]
    max_exhaustion: float = config["balance"]["war_declaration_max_exhaustion"]
    peace_exhaustion: float = config["balance"]["peace_exhaustion_threshold"]
    stalemate: int = config["balance"]["peace_stalemate_ticks"]
    events: list[dict[str, Any]] = []

    for war_id in sorted(world.wars):
        war = world.wars[war_id]
        if war.status != "active":
            continue
        involved = sorted(war.attackers | war.defenders)
        worn_out = all(world.factions[f].exhaustion >= peace_exhaustion for f in involved)
        stalled = world.tick_count - war.last_capture_tick > stalemate
        if not (worn_out or stalled):
            continue
        war.status = "ended"
        for a in sorted(war.attackers):
            for d in sorted(war.defenders):
                world.factions[a].at_war_with.discard(d)
                world.factions[d].at_war_with.discard(a)
        events.append({
            "kind": "peace",
            "attacker": sorted(war.attackers)[0],
            "defender": sorted(war.defenders)[0],
        })

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.at_war_with or fac.exhaustion > max_exhaustion:
            continue
        if rng.random() > 0.004:
            continue
        candidates = [
            other for other in _neighbouring_factions(world, fid)
            if not world.factions[other].at_war_with
            and _strength(world, fid) > _strength(world, other) * ratio_needed
        ]
        if not candidates:
            continue
        target = rng.choice(candidates)
        fac.at_war_with.add(target)
        world.factions[target].at_war_with.add(fid)
        world.wars[world.next_war_id] = War(
            id=world.next_war_id,
            attackers={fid},
            defenders={target},
            started_at=world.current_time,
            last_capture_tick=world.tick_count,
        )
        world.next_war_id += 1
        events.append({"kind": "war_declared", "attacker": fid, "defender": target})

    return events
