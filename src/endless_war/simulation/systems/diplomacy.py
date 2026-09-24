"""War exhaustion, declarations, and peace.

docs/superpowers/specs/01-game-design.md requires that individual wars end
while the world does not. Peace triggers on mutual exhaustion or on a
stalemate with no captures.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import War, WorldState
from endless_war.simulation.systems import clamp
from endless_war.simulation.systems.battle import effective_power


def update_exhaustion(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Grow exhaustion from accumulated casualties; decay it in peacetime."""
    factor: float = config["balance"]["exhaustion_per_casualty_fraction"]
    decay: float = config["balance"]["exhaustion_decay_per_tick"]
    weariness: float = config["balance"]["war_weariness_per_tick"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        new_casualties = fac.casualties - fac.exhaustion_casualty_mark
        fac.exhaustion_casualty_mark = fac.casualties
        if fac.at_war_with:
            army_strength = sum(
                a.manpower for a in world.armies.values() if a.faction_id == fid
            )
            base = max(1, fac.manpower + army_strength)
            # War weariness: exhaustion also grows with time at war, which makes
            # the exhaustion peace reachable (the casualty term alone barely
            # moved, docs/decisions.md 2026-09-23).
            fac.exhaustion = clamp(fac.exhaustion + (new_casualties / base) * factor + weariness)
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


def eliminate_landless(world: WorldState) -> list[dict[str, Any]]:
    """Eliminate every faction that controls no province.

    Its armies disband (their men count as its casualties) and it leaves every
    war. It stays in `world.factions` so its history survives.
    """
    controlled = {p.controller_faction_id for p in world.provinces.values()}
    events: list[dict[str, Any]] = []
    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.eliminated or fid in controlled:
            continue
        fac.eliminated = True
        for aid in [aid for aid in sorted(world.armies) if world.armies[aid].faction_id == fid]:
            fac.casualties += world.armies[aid].manpower
            del world.armies[aid]
        for other in sorted(fac.at_war_with):
            world.factions[other].at_war_with.discard(fid)
        fac.at_war_with.clear()
        events.append({"kind": "eliminated", "faction": fid})
    return events


def _settle(world: WorldState, war: War) -> list[tuple[int, int | None, int]]:
    """Occupied land becomes the occupier's when a war ends.

    For every province held by one of this war's belligerents but owned by
    someone else, the owner becomes the holder, unless the two are still at war
    (in another war) over it. Runs after the war's flags are cleared.
    """
    involved = war.attackers | war.defenders
    annexed: list[tuple[int, int | None, int]] = []
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        holder, owner = province.controller_faction_id, province.owner_faction_id
        if holder is None or holder not in involved or owner == holder:
            continue
        if owner in world.factions and holder in world.factions[owner].at_war_with:
            continue
        province.owner_faction_id = holder
        annexed.append((pid, owner, holder))
    return annexed


def _capitulated(world: WorldState, war: War, side: set[int], fraction: float) -> bool:
    """Every faction on `side` has lost its capital and most of its pre-war land."""
    if not war.start_land:
        return False
    for fid in sorted(side):
        fac = world.factions[fid]
        if fac.eliminated:
            continue
        held = sum(1 for p in world.provinces.values() if p.controller_faction_id == fid)
        capital = world.provinces.get(fac.capital_province_id)
        capital_lost = capital is not None and capital.controller_faction_id != fid
        if not (capital_lost and held < fraction * war.start_land.get(fid, held + 1)):
            return False
    return True


def _strength(world: WorldState, faction_id: int, config: dict[str, Any]) -> float:
    """Combat strength for war decisions: armies by effective power, plus reserves.

    Headcount made a faction with 88,000 broken men look too strong to attack,
    so the healthy neighbours of a collapsed faction never declared on it.
    """
    terrain = config["balance"]["terrain_defence"]
    army = sum(
        effective_power(world.armies[aid], world, False, terrain)
        for aid in sorted(world.armies)
        if world.armies[aid].faction_id == faction_id
    )
    # Reserves count only in proportion to supplied land: a rump state with no
    # supply source cannot field its pool, and counting it anyway kept healthy
    # neighbours from ever declaring on it (seed 99, 2026-09-24).
    low = config["balance"]["low_supply_threshold"]
    held = [p for p in world.provinces.values() if p.controller_faction_id == faction_id]
    usable = sum(1 for p in held if p.supply_value >= low) / len(held) if held else 0.0
    return army + world.factions[faction_id].manpower * 0.25 * usable


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
    give_up: float = config["balance"]["capitulation_land_fraction"]
    max_wars: int = config["balance"]["max_concurrent_wars"]
    events: list[dict[str, Any]] = eliminate_landless(world)

    for war_id in sorted(world.wars):
        war = world.wars[war_id]
        if war.status != "active":
            continue
        involved = sorted(war.attackers | war.defenders)
        worn_out = all(world.factions[f].exhaustion >= peace_exhaustion for f in involved)
        stalled = world.tick_count - war.last_capture_tick > stalemate
        destroyed = not any(not world.factions[f].eliminated for f in war.attackers) or not any(
            not world.factions[f].eliminated for f in war.defenders
        )
        capitulated = _capitulated(world, war, war.attackers, give_up) or _capitulated(
            world, war, war.defenders, give_up
        )
        if not (worn_out or stalled or destroyed or capitulated):
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
            "reason": "elimination" if destroyed else "capitulation" if capitulated else "ceasefire",
            "annexed": _settle(world, war),
        })

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        # Up to `max_concurrent_wars` at once: with one war per faction only
        # about two of five factions ever acted (the user's observation).
        if fac.eliminated or len(fac.at_war_with) >= max_wars or fac.exhaustion > max_exhaustion:
            continue
        if rng.random() > 0.004:
            continue
        candidates = [
            other for other in _neighbouring_factions(world, fid)
            if other not in fac.at_war_with
            and not world.factions[other].eliminated
            and _strength(world, fid, config) > _strength(world, other, config) * ratio_needed
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
            start_land={
                f: sum(1 for p in world.provinces.values() if p.controller_faction_id == f)
                for f in (fid, target)
            },
        )
        world.next_war_id += 1
        events.append({"kind": "war_declared", "attacker": fid, "defender": target})

    return events
