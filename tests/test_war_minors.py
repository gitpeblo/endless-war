"""Regression tests for the war-model final-review minors (2026-09-24)."""

import random

from endless_war.config import load_config
from endless_war.domain.models import Army, War
from endless_war.simulation.worldgen import generate_world


def _war(a=0, b=3):
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[a].at_war_with = {b}
    w.factions[b].at_war_with = {a}
    return w, cfg


def _hostile_province(w, holder=3, enemy=0):
    return next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == holder
                and any(w.provinces[n].controller_faction_id == enemy for n in w.provinces[p].neighbors))


def test_garrison_losses_are_not_counted_as_dead_soldiers() -> None:
    # Garrison strength is effective power, not men: it inflated the death toll.
    from endless_war.simulation.systems.battle import resolve_battles
    w, cfg = _war()
    target = _hostile_province(w)
    w.armies[1] = Army(id=1, faction_id=0, province_id=target, manpower=50_000)
    before = w.factions[3].casualties
    records = resolve_battles(w, random.Random(1), cfg)
    assert records and w.provinces[target].garrison < 1e9
    assert w.factions[3].casualties == before, "no defending army, so no dead defenders"
    assert records[0]["defender_losses"] == 0 and records[0]["garrison_losses"] > 0


def test_surrender_is_decided_before_any_army_is_removed() -> None:
    from endless_war.simulation.systems.control import surrender_trapped_armies
    w, cfg = _war()
    target = _hostile_province(w)
    for n in w.provinces[target].neighbors:
        w.provinces[n].controller_faction_id = 1  # neither side has a way out
    w.factions[0].at_war_with, w.factions[3].at_war_with = {3}, {0}
    w.armies[1] = Army(id=1, faction_id=0, province_id=target, manpower=10_000, organization=0.1)
    w.armies[2] = Army(id=2, faction_id=3, province_id=target, manpower=10_000, organization=0.1)
    assert surrender_trapped_armies(w, cfg) == [], "both broken: nobody to surrender to"


def test_a_trapped_army_surrenders_to_an_unbroken_enemy() -> None:
    from endless_war.simulation.systems.control import surrender_trapped_armies
    w, cfg = _war()
    target = _hostile_province(w)
    for n in w.provinces[target].neighbors:
        w.provinces[n].controller_faction_id = 0
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=10_000, organization=0.1)
    w.armies[2] = Army(id=2, faction_id=0, province_id=target, manpower=10_000)
    assert len(surrender_trapped_armies(w, cfg)) == 1 and 1 not in w.armies


def test_a_stranded_broken_army_demobilises_into_reserves() -> None:
    # A broken army in an unsupplied pocket with no route to supply sat forever.
    from endless_war.simulation.systems.control import disband_stranded_armies
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    pocket = 0
    for n in w.provinces[pocket].neighbors:
        w.provinces[n].controller_faction_id = 1
    w.provinces[pocket].controller_faction_id = 0
    w.provinces[pocket].supply_value = cfg["balance"]["min_supply"]
    w.armies[1] = Army(id=1, faction_id=0, province_id=pocket, manpower=40_000, organization=0.0, morale=0.0)
    pool = w.factions[0].manpower
    disband_stranded_armies(w, cfg)
    assert 1 not in w.armies and w.factions[0].manpower == pool + 40_000


def test_a_capital_moves_when_it_is_annexed() -> None:
    from endless_war.simulation.systems.diplomacy import update_diplomacy
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[3].at_war_with, w.factions[4].at_war_with = {4}, {3}
    w.tick_count = cfg["balance"]["peace_stalemate_ticks"] + 10
    w.wars[0] = War(id=0, attackers={3}, defenders={4}, started_at=w.current_time, last_capture_tick=0)
    w.next_war_id = 1
    old = w.factions[4].capital_province_id
    w.provinces[old].controller_faction_id = 3
    update_diplomacy(w, random.Random(1), cfg)
    new = w.factions[4].capital_province_id
    assert new != old and w.provinces[new].controller_faction_id == 4
    assert w.provinces[new].is_capital and not w.provinces[old].is_capital


def test_only_a_broken_army_may_fall_back_while_disorganized() -> None:
    from endless_war.simulation.systems.movement import update_movement
    w, cfg = _war()
    here = next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 0)
    dest = next(n for n in w.provinces[here].neighbors if w.provinces[n].controller_faction_id == 0)
    for p in (here, dest):
        w.provinces[p].supply_value = cfg["balance"]["min_supply"]
    # disorganized below min_advance but morale fine: not broken by morale; org 0.1 < broken 0.3 -> broken
    w.armies[1] = Army(id=1, faction_id=0, province_id=here, manpower=10_000, organization=0.1,
                       morale=1.0, supply=cfg["balance"]["min_supply"], destination_id=dest)
    w.armies[2] = Army(id=2, faction_id=0, province_id=here, manpower=10_000, organization=0.1,
                       morale=1.0, supply=cfg["balance"]["min_supply"], destination_id=dest)
    w.armies[2].organization = 0.12
    broken_org = cfg["balance"]["broken_organization"]
    cfg["balance"]["broken_organization"] = 0.11  # army 2 (0.12) is not broken, army 1 (0.10) is
    update_movement(w, random.Random(1), cfg)
    cfg["balance"]["broken_organization"] = broken_org
    assert w.armies[1].province_id == dest, "broken: may fall back"
    assert w.armies[2].province_id == here, "not broken: min_advance_organization still applies"


def test_settlement_runs_once_when_a_war_ends_by_elimination() -> None:
    from endless_war.simulation.systems.diplomacy import update_diplomacy
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[3].at_war_with, w.factions[4].at_war_with = {4}, {3}
    w.wars[0] = War(id=0, attackers={3}, defenders={4}, started_at=w.current_time, last_capture_tick=w.tick_count)
    w.next_war_id = 1
    for p in w.provinces.values():
        if p.controller_faction_id == 4:
            p.controller_faction_id = 3
    events = update_diplomacy(w, random.Random(1), cfg)
    peace = [e for e in events if e["kind"] == "peace"]
    assert len(peace) == 1 and peace[0]["reason"] == "elimination"
    assert all(w.provinces[pid].owner_faction_id == 3 for pid, _o, _h in peace[0]["annexed"])
    assert [e for e in update_diplomacy(w, random.Random(1), cfg) if e["kind"] == "peace"] == []


def test_a_side_that_lost_its_capital_and_most_land_capitulates() -> None:
    from endless_war.simulation.systems.diplomacy import update_diplomacy
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[3].at_war_with, w.factions[4].at_war_with = {4}, {3}
    held = [p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 4]
    w.wars[0] = War(id=0, attackers={3}, defenders={4}, started_at=w.current_time,
                    last_capture_tick=w.tick_count, start_land={3: 20, 4: len(held)})
    w.next_war_id = 1
    capital = w.factions[4].capital_province_id
    for pid in held[: len(held) - 2]:
        w.provinces[pid].controller_faction_id = 3
    w.provinces[capital].controller_faction_id = 3
    events = update_diplomacy(w, random.Random(1), cfg)
    assert any(e["kind"] == "peace" and e["reason"] == "capitulation" for e in events)
