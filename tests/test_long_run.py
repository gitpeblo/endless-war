"""The CONTINUE_OFFLINE.md checkpoint, as an automated test.

SLOW: the ten-year fixture runs 14 600 ticks and takes minutes, not seconds.
Skip it during tight loops with `-m "not slow"`.
"""

import pytest

pytestmark = pytest.mark.slow

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_YEAR = 4 * 365


@pytest.fixture(scope="module")
def ten_year_world():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(10 * TICKS_PER_YEAR):
        engine.tick()
    return world


def test_invariants_hold_after_ten_years(ten_year_world) -> None:
    assert check_invariants(ten_year_world) == []


def test_wars_started_and_ended(ten_year_world) -> None:
    assert ten_year_world.wars, "no war ever started"
    assert any(w.status == "ended" for w in ten_year_world.wars.values()), "no war ever ended"


def test_fronts_moved(ten_year_world) -> None:
    captures = [e for e in ten_year_world.events if e.category == "territory"]
    assert captures, "no province ever changed hands"


def test_history_accumulated(ten_year_world) -> None:
    assert len(ten_year_world.events) > 10


def test_no_faction_was_silently_annihilated_by_a_bug(ten_year_world) -> None:
    for fid in ten_year_world.factions:
        controlled = [
            p for p in ten_year_world.provinces.values() if p.controller_faction_id == fid
        ]
        owned = [p for p in ten_year_world.provinces.values() if p.owner_faction_id == fid]
        assert owned, f"faction {fid} lost its ownership records entirely"
        _ = controlled  # conquest to zero controlled provinces is legitimate


def test_run_is_reproducible() -> None:
    cfg = load_config()
    results = []
    for _ in range(2):
        world = generate_world(seed=99, config=cfg)
        engine = SimulationEngine(world, cfg)
        for _ in range(TICKS_PER_YEAR):
            engine.tick()
        results.append([
            (p.controller_faction_id, p.supply_value) for p in world.provinces.values()
        ])
    assert results[0] == results[1]
