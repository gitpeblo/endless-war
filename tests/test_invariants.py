from endless_war.config import load_config
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world


def test_fresh_world_has_no_violations() -> None:
    assert check_invariants(generate_world(seed=42, config=load_config())) == []


def test_detects_out_of_range_morale() -> None:
    w = generate_world(seed=42, config=load_config())
    w.armies[0].morale = 1.4
    assert any("morale" in v for v in check_invariants(w))


def test_detects_negative_manpower() -> None:
    w = generate_world(seed=42, config=load_config())
    w.factions[0].manpower = -5
    assert any("manpower" in v for v in check_invariants(w))


def test_detects_lost_province() -> None:
    w = generate_world(seed=42, config=load_config())
    del w.provinces[0]
    assert any("province count" in v for v in check_invariants(w))


def test_detects_nan() -> None:
    w = generate_world(seed=42, config=load_config())
    w.factions[0].treasury = float("nan")
    assert any("finite" in v for v in check_invariants(w))
