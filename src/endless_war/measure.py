"""Ten-year measurement of the war model against the gate in docs/decisions.md.

    PYTHONPATH=src python3 -m endless_war.measure --seeds 42 7 99
"""

from __future__ import annotations

import argparse
import time

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_DAY = 4
GATE = {
    "longest_island_days": 180,
    "captures_per_battle": 3.0,
    "map_changes": 6,
    "events": 2000,
    "largest_share": 0.70,
    "seconds": 6.0,
}


def _islands(world) -> set[int]:
    found = set()
    for pid, province in world.provinces.items():
        mine = province.controller_faction_id
        if province.neighbors and all(
            world.provinces[n].controller_faction_id != mine for n in province.neighbors
        ):
            found.add(pid)
    return found


def measure(seed: int, years: int = 10) -> dict:
    cfg = load_config()
    world = generate_world(seed=seed, config=cfg)
    engine = SimulationEngine(world, cfg)
    battles = captures = violations = 0
    battle_years: set[int] = set()
    island_since: dict[int, int] = {}
    longest = 0
    yearly: list[tuple] = []
    largest = 0.0
    eliminated: dict[int, int] = {}
    total = len(world.provinces)
    start = time.perf_counter()
    for tick in range(years * 365 * TICKS_PER_DAY):
        counts = engine.tick()
        year = tick // (365 * TICKS_PER_DAY)
        battles += counts["battles"]
        captures += counts["captures"]
        if counts["battles"]:
            battle_years.add(year)
        if tick % TICKS_PER_DAY:
            continue
        day = tick // TICKS_PER_DAY
        islands = _islands(world)
        for pid in list(island_since):
            if pid not in islands:
                longest = max(longest, day - island_since.pop(pid))
        for pid in islands:
            island_since.setdefault(pid, day)
        held: dict[int, int] = {}
        for province in world.provinces.values():
            held[province.controller_faction_id] = held.get(province.controller_faction_id, 0) + 1
        largest = max(largest, max(held.values()) / total)
        for fid in world.factions:
            if fid not in held and fid not in eliminated:
                eliminated[fid] = year + 1
        if (tick + TICKS_PER_DAY) % (365 * TICKS_PER_DAY) == 0:
            yearly.append(tuple(world.provinces[p].controller_faction_id for p in sorted(world.provinces)))
            violations += len(check_invariants(world))
    last_day = years * 365
    for since in island_since.values():
        longest = max(longest, last_day - since)
    return {
        "seed": seed,
        "battles": battles,
        "battle_years": len(battle_years),
        "captures": captures,
        "captures_per_battle": captures / battles if battles else float(captures),
        "map_changes": sum(1 for a, b in zip(yearly, yearly[1:]) if a != b),
        "largest_share": largest,
        "longest_island_days": longest,
        "events": world.next_event_id,
        "eliminated": eliminated,
        "wars_started": len(world.wars),
        "wars_ended": sum(1 for w in world.wars.values() if w.status == "ended"),
        "violations": violations,
        "seconds": time.perf_counter() - start,
    }


def _passes(row: dict) -> dict[str, bool]:
    return {
        "longest_island_days": row["longest_island_days"] <= GATE["longest_island_days"],
        "captures_per_battle": row["captures_per_battle"] <= GATE["captures_per_battle"],
        "map_changes": row["map_changes"] >= GATE["map_changes"],
        "events": row["events"] < GATE["events"],
        "largest_share": row["largest_share"] <= GATE["largest_share"],
        "violations": row["violations"] == 0,
        "seconds": row["seconds"] < GATE["seconds"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="endless-war-measure")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 99])
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args(argv)
    cols = ("seed", "battles", "battle_years", "captures", "captures_per_battle", "map_changes",
            "largest_share", "longest_island_days", "events", "wars_started", "wars_ended",
            "eliminated", "violations", "seconds")
    print(" | ".join(cols))
    for seed in args.seeds:
        row = measure(seed, args.years)
        cells = []
        for c in cols:
            v = row[c]
            cells.append(f"{v:.2f}" if isinstance(v, float) else str(v))
        verdict = _passes(row)
        print(" | ".join(cells), "|", "PASS" if all(verdict.values()) else
              "FAIL: " + ", ".join(k for k, ok in verdict.items() if not ok))


if __name__ == "__main__":
    main()
