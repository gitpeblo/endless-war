"""Numeric invariants.

"No obvious numerical system explodes" from CONTINUE_OFFLINE.md, made checkable.
Returns a list of human-readable violations; empty means healthy.
"""

from __future__ import annotations

import math

from endless_war.domain.models import WorldState

UNIT_FIELDS_ARMY = ("morale", "organization", "supply", "training", "equipment")
UNIT_FIELDS_FACTION = ("stability", "war_support", "exhaustion")


def check_invariants(world: WorldState) -> list[str]:
    """Return every violated invariant, or an empty list."""
    violations: list[str] = []

    expected = world.expected_province_count
    if expected and len(world.provinces) != expected:
        violations.append(
            f"province count is {len(world.provinces)}, expected {expected}"
        )

    for pid in sorted(world.provinces):
        prov = world.provinces[pid]
        if prov.controller_faction_id not in world.factions:
            violations.append(f"province {pid} controlled by unknown faction")
        elif world.factions[prov.controller_faction_id].eliminated:
            violations.append(f"province {pid} controlled by eliminated faction")
        if not math.isfinite(prov.supply_value):
            violations.append(f"province {pid} supply_value is not finite")
        elif not 0.0 <= prov.supply_value <= 1.0:
            violations.append(f"province {pid} supply_value out of range")
        if prov.population < 0:
            violations.append(f"province {pid} has negative population")

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.manpower < 0:
            violations.append(f"faction {fid} has negative manpower")
        if not math.isfinite(fac.treasury):
            violations.append(f"faction {fid} treasury is not finite")
        elif fac.treasury < 0:
            violations.append(f"faction {fid} has negative treasury")
        if fid in fac.at_war_with:
            violations.append(f"faction {fid} is at war with itself")
        for name in UNIT_FIELDS_FACTION:
            value = getattr(fac, name)
            if not math.isfinite(value):
                violations.append(f"faction {fid} {name} is not finite")
            elif not 0.0 <= value <= 1.0:
                violations.append(f"faction {fid} {name} out of range ({value})")

    for aid in sorted(world.armies):
        army = world.armies[aid]
        if army.manpower < 0:
            violations.append(f"army {aid} has negative manpower")
        if army.province_id not in world.provinces:
            violations.append(f"army {aid} stands in a province that does not exist")
        for name in UNIT_FIELDS_ARMY:
            value = getattr(army, name)
            if not math.isfinite(value):
                violations.append(f"army {aid} {name} is not finite")
            elif not 0.0 <= value <= 1.0:
                violations.append(f"army {aid} {name} out of range ({value})")

    return violations
