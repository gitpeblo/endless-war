"""The CONTINUE_OFFLINE.md checkpoint, as an automated test.

SLOW relative to the unit tests: the ten-year fixture runs 14 600 ticks.
Measured at about 6 seconds, so it is worth running -- skip it during tight
loops with `-m "not slow"`, but do not avoid it before committing.
"""

import pytest

pytestmark = pytest.mark.slow

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_YEAR = 4 * 365

# Captures must land in at least this many distinct simulated years of the ten.
# Observed behaviour at seed 42 is EIGHT of the ten simulated years, so this
# leaves real headroom. (Do not confuse it with the six years that contain a
# battle: captures include bloodless walk-ins into undefended provinces.)
# Raise it only with a measurement showing the extra years are reliably there.
MIN_YEARS_WITH_CAPTURES = 3


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
    """Territory must keep changing hands, not change once and then freeze.

    Asserting only that *some* capture exists passed happily while the map was
    frozen for eight of ten years -- the exact failure this task was spent
    diagnosing. The year comes from the event's own `simulated_at` rather than
    from a tick count, so it stays correct if the calendar mapping changes.
    """
    captures = [e for e in ten_year_world.events if e.category == "territory"]
    assert captures, "no province ever changed hands"
    years = sorted({e.simulated_at.year for e in captures})
    assert len(years) >= MIN_YEARS_WITH_CAPTURES, (
        f"territory changed hands in only {len(years)} distinct simulated year(s) "
        f"({years}); a front that moves once and then freezes is not a moving front"
    )


def test_history_accumulated(ten_year_world) -> None:
    assert len(ten_year_world.events) > 10


def test_no_faction_was_silently_annihilated_by_a_bug(ten_year_world) -> None:
    """No province may leak out of the world by losing its controller.

    The ownership half below can only fail on data corruption, because nothing
    in the simulation ever mutates `owner_faction_id`. The assertion that bites
    is the total: every province must be controlled by exactly one live faction,
    so a province dropping to `None` or to an id that is not in `factions` --
    annihilation by bug, as opposed to by conquest -- fails here.
    """
    controlled_total = 0
    for fid in ten_year_world.factions:
        controlled = [
            p for p in ten_year_world.provinces.values() if p.controller_faction_id == fid
        ]
        owned = [p for p in ten_year_world.provinces.values() if p.owner_faction_id == fid]
        assert owned, f"faction {fid} lost its ownership records entirely"
        controlled_total += len(controlled)  # zero controlled is legitimate: conquest

    assert controlled_total == ten_year_world.expected_province_count, (
        f"{controlled_total} provinces are controlled by a live faction but the world "
        f"should have {ten_year_world.expected_province_count}; "
        f"{ten_year_world.expected_province_count - controlled_total} leaked to no "
        f"controller or to a faction that does not exist"
    )


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
