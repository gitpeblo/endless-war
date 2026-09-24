import random

from endless_war.config import load_config
from endless_war.domain.models import Army
from endless_war.simulation.systems.control import apply_control_changes
from endless_war.simulation.worldgen import generate_world


def _border_province(w, faction_id, enemy_id):
    """A province controlled by `faction_id` that touches `enemy_id` territory."""
    for pid in sorted(w.provinces):
        prov = w.provinces[pid]
        if prov.controller_faction_id != faction_id or prov.is_capital:
            continue
        if any(w.provinces[n].controller_faction_id == enemy_id for n in prov.neighbors):
            return pid
    raise AssertionError(f"no border province between {faction_id} and {enemy_id}")


def test_lone_army_captures_an_undefended_hostile_province() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    target = _border_province(w, 3, 0)
    w.provinces[target].garrison = 0.0  # undefended now means: its garrison is broken
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    # Capture now takes occupation_ticks of uninterrupted holding.
    for _ in range(cfg["balance"]["occupation_ticks"] - 1):
        assert apply_control_changes(w, random.Random(1), cfg, []) == []
    captures = apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].controller_faction_id == 0
    assert captures == [{"province_id": target, "from_faction": 3, "to_faction": 0}]


def test_owner_is_unchanged_by_occupation() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    target = _border_province(w, 3, 0)
    w.provinces[target].garrison = 0.0  # undefended now means: its garrison is broken
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    for _ in range(cfg["balance"]["occupation_ticks"]):
        apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].controller_faction_id == 0, "premise: it was captured"
    assert w.provinces[target].owner_faction_id == 3, "occupation must not transfer ownership"


def test_defended_province_does_not_change_hands() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    target = _border_province(w, 3, 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=30_000)
    apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].controller_faction_id == 3


def test_broken_attacker_retreats_to_a_friendly_neighbour() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    target = _border_province(w, 3, 0)
    friendly = next(
        n for n in w.provinces[target].neighbors if w.provinces[n].controller_faction_id == 0
    )
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000, organization=0.05)
    apply_control_changes(w, random.Random(1), cfg, [
        {"province_id": target, "attacker_faction": 0, "defender_faction": 3,
         "attacker_losses": 10, "defender_losses": 10,
         "attacker_broke": True, "defender_broke": False},
    ])
    assert w.armies[0].province_id == friendly


def test_annihilated_army_is_removed() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.armies[0] = Army(id=0, faction_id=0, province_id=0, manpower=0)
    apply_control_changes(w, random.Random(1), cfg, [])
    assert 0 not in w.armies


def test_province_count_is_conserved() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    for _ in range(100):
        apply_control_changes(w, random.Random(1), cfg, [])
    controlled = [p.controller_faction_id for p in w.provinces.values()]
    assert len(controlled) == 96
    assert all(c in w.factions for c in controlled)


def _war(cfg):
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    return w


def _record(pid, defender_broke=False, attacker_broke=False):
    return {"province_id": pid, "attacker_faction": 0, "defender_faction": 3,
            "attacker_losses": 0, "defender_losses": 0,
            "attacker_broke": attacker_broke, "defender_broke": defender_broke}


def test_a_broken_defender_falls_back_to_friendly_ground() -> None:
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    assert any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[target].neighbors), "premise"
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=10_000, organization=0.1)
    w.armies[2] = Army(id=2, faction_id=0, province_id=target, manpower=30_000)
    apply_control_changes(w, random.Random(1), cfg, [_record(target, defender_broke=True)])
    moved = w.armies[1].province_id
    assert moved != target and w.provinces[moved].controller_faction_id == 3


def test_a_trapped_broken_army_surrenders() -> None:
    from endless_war.simulation.systems.control import surrender_trapped_armies
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    for n in w.provinces[target].neighbors:
        w.provinces[n].controller_faction_id = 0  # encircled
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=12_345, organization=0.1)
    w.armies[2] = Army(id=2, faction_id=0, province_id=target, manpower=30_000)
    before = w.factions[3].casualties
    records = surrender_trapped_armies(w, cfg)
    assert 1 not in w.armies and 2 in w.armies
    assert w.factions[3].casualties == before + 12_345
    assert records == [{"kind": "surrender", "province_id": target, "faction": 3, "men": 12_345}]


def test_a_broken_army_with_a_way_out_does_not_surrender() -> None:
    from endless_war.simulation.systems.control import surrender_trapped_armies
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=10_000, organization=0.1)
    w.armies[2] = Army(id=2, faction_id=0, province_id=target, manpower=30_000)
    assert surrender_trapped_armies(w, cfg) == [] and 1 in w.armies


def test_an_encircled_army_in_good_order_does_not_surrender() -> None:
    from endless_war.simulation.systems.control import surrender_trapped_armies
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    for n in w.provinces[target].neighbors:
        w.provinces[n].controller_faction_id = 0
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=10_000)
    w.armies[2] = Army(id=2, faction_id=0, province_id=target, manpower=30_000)
    assert surrender_trapped_armies(w, cfg) == [] and 1 in w.armies


def test_walking_in_and_out_captures_nothing() -> None:
    # Capture churn: armies trading an empty province every other tick made
    # 620 captures from 60 battles at seed 42. A hold must last a full day.
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    home = next(n for n in w.provinces[target].neighbors if w.provinces[n].controller_faction_id == 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    for _ in range(3 * cfg["balance"]["occupation_ticks"]):
        assert apply_control_changes(w, random.Random(1), cfg, []) == []
        w.armies[0].province_id = home if w.armies[0].province_id == target else target
    assert w.provinces[target].controller_faction_id == 3


def test_a_contested_province_never_advances_occupation() -> None:
    cfg = load_config()
    w = _war(cfg)
    target = _border_province(w, 3, 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    w.armies[1] = Army(id=1, faction_id=3, province_id=target, manpower=5_000)
    for _ in range(3 * cfg["balance"]["occupation_ticks"]):
        assert apply_control_changes(w, random.Random(1), cfg, []) == []
    assert w.provinces[target].occupation is None
