"""Garrisons: every province defends itself.

Without them any province with no army in it fell to whoever stood in it, so
armies raided empty land in circles instead of fighting (docs/decisions.md,
2026-09-24). A garrison is strength in `battle.effective_power` units; it
fights in battles as a defender, must be broken before a province can be
occupied, and regrows while no enemy stands in the province.
"""

from __future__ import annotations

from typing import Any

from endless_war.domain.models import Province, WorldState


def garrison_cap(province: Province, config: dict[str, Any]) -> float:
    """Full strength: population x per-capita x terrain, reduced while occupied."""
    balance = config["balance"]
    cap = (
        province.population
        * balance["garrison_per_capita"]
        * balance["terrain_defence"].get(province.terrain, 1.0)
    )
    if province.controller_faction_id != province.owner_faction_id:
        cap *= balance["occupied_garrison_factor"]
    return cap


def garrison_strength(province: Province, config: dict[str, Any]) -> float:
    """Current strength; a province never touched yet stands at its cap."""
    return garrison_cap(province, config) if province.garrison < 0 else province.garrison


# A garrison below this share of its cap no longer holds. At 1 % a siege took
# ~150 ticks, while an attacker breaks in ~15 (measured 2026-09-24).
BROKEN_SHARE = 0.10


def garrison_broken(province: Province, config: dict[str, Any]) -> bool:
    """Below BROKEN_SHARE of its cap: the province can be occupied."""
    return garrison_strength(province, config) < BROKEN_SHARE * garrison_cap(province, config)


def update_garrisons(world: WorldState, config: dict[str, Any]) -> None:
    """Initialise, clamp to the current cap, and regrow while unthreatened."""
    regen: float = config["balance"]["garrison_regen_per_tick"]
    # Index armies by province once: scanning every army for every province
    # was the simulation's hottest loop (4.3M checks per two simulated years).
    present: dict[int, set[int]] = {}
    for army in world.armies.values():
        if army.manpower > 0:
            present.setdefault(army.province_id, set()).add(army.faction_id)
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        cap = garrison_cap(province, config)
        if province.garrison < 0 or province.garrison > cap:
            province.garrison = cap
            continue
        controller = province.controller_faction_id
        if controller is not None and controller in world.factions:
            if present.get(pid, set()) & world.factions[controller].at_war_with:
                continue
        province.garrison = min(cap, province.garrison + regen * cap)
