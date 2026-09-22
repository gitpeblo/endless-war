import random

from endless_war.config import load_config
from endless_war.simulation.systems.supply import update_supply
from endless_war.simulation.worldgen import generate_world


def test_capital_is_fully_supplied() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    for fac in w.factions.values():
        assert w.provinces[fac.capital_province_id].supply_value == 1.0


def test_supply_decays_with_distance_from_capital() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    fac = w.factions[0]
    capital = w.provinces[fac.capital_province_id]
    neighbour = w.provinces[
        next(n for n in capital.neighbors if w.provinces[n].controller_faction_id == fac.id)
    ]
    assert neighbour.supply_value < capital.supply_value


def test_supply_is_always_within_bounds() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    floor = cfg["balance"]["min_supply"]
    for prov in w.provinces.values():
        assert floor <= prov.supply_value <= 1.0


def test_province_cut_off_from_its_capital_drops_to_minimum() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    # Find one of this faction's provinces that is not the capital, then hand
    # every one of its neighbours to another faction, isolating it.
    target = next(
        p for p in w.provinces.values()
        if p.controller_faction_id == fac.id and not p.is_capital
    )
    for nid in target.neighbors:
        w.provinces[nid].controller_faction_id = 1 if fac.id != 1 else 2
    update_supply(w, random.Random(1), cfg)
    assert target.supply_value == cfg["balance"]["min_supply"]
