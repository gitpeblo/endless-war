"""Headless observatory.

Runs the simulation for N simulated years and prints a yearly report. This is
the CONTINUE_OFFLINE.md checkpoint: if the output here is not interesting,
do not start building the GTK interface.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_YEAR = 4 * 365


def _summarize(world: WorldState) -> list[tuple[int, str, int, int, int]]:
    rows = []
    for fid in sorted(world.factions):
        fac = world.factions[fid]
        controlled = sum(
            1 for p in world.provinces.values() if p.controller_faction_id == fid
        )
        population = sum(
            p.population for p in world.provinces.values() if p.controller_faction_id == fid
        )
        rows.append((fid, fac.name, controlled, population, fac.casualties))
    return rows


def run_observation(
    seed: int,
    years: int,
    config: dict[str, Any],
    emit: Callable[[str], None] = print,
) -> WorldState:
    """Run `years` simulated years, reporting once per year."""
    world = generate_world(seed=seed, config=config)
    engine = SimulationEngine(world, config)

    emit(f"Endless War — headless observation, seed {seed}, {years} simulated years")
    for year in range(1, years + 1):
        for _ in range(TICKS_PER_YEAR):
            engine.tick()

        emit("")
        emit(f"=== Year {year} — {world.current_time.date().isoformat()} ===")
        emit(f"{'Faction':<22}{'Prov':>6}{'Population':>14}{'Casualties':>13}{'Exh':>7}")
        for fid, name, provinces, population, casualties in _summarize(world):
            emit(
                f"{name:<22}{provinces:>6}{population:>14,}{casualties:>13,}"
                f"{world.factions[fid].exhaustion:>7.2f}"
            )

        active = [w for w in world.wars.values() if w.status == "active"]
        emit(f"wars: {len(active)} active, {len(world.wars)} total")
        for event in list(world.events)[-4:]:
            emit(f"  · {event.simulated_at.date().isoformat()}  {event.title}: {event.body}")

        violations = check_invariants(world)
        if violations:
            emit("!! INVARIANT VIOLATIONS !!")
            for violation in violations[:10]:
                emit(f"   {violation}")
            raise SystemExit(1)

    emit("")
    emit(f"Completed {years} simulated years with no invariant violations.")
    return world


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="endless-war-observe")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args(argv)
    run_observation(seed=args.seed, years=args.years, config=load_config())


if __name__ == "__main__":
    main()
