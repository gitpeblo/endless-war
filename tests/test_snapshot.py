from endless_war.app.snapshot import RECENT_EVENT_LIMIT, build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world


def _world():
    cfg = load_config()
    return generate_world(seed=42, config=cfg), cfg


def test_every_province_appears_exactly_once_in_stable_order() -> None:
    world, cfg = _world()
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    ids = [cell.id for cell in view.provinces]
    assert ids == sorted(world.provinces)
    assert len(ids) == len(set(ids))


def test_faction_rows_carry_controlled_totals() -> None:
    world, cfg = _world()
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    rows = {row.id: row for row in view.factions}
    assert set(rows) == set(world.factions)
    for fid, row in rows.items():
        controlled = [
            p for p in world.provinces.values() if p.controller_faction_id == fid
        ]
        assert row.provinces == len(controlled)
        assert row.population == sum(p.population for p in controlled)
        assert row.name == world.factions[fid].name


def test_at_war_with_is_a_sorted_tuple_not_a_set() -> None:
    world, cfg = _world()
    world.factions[0].at_war_with = {3, 2}
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    row = next(r for r in view.factions if r.id == 0)
    assert row.at_war_with == (2, 3)


def test_binding_a_faction_is_recorded_and_unbound_is_none() -> None:
    world, cfg = _world()
    assert build_view(world, cfg, bound_faction_id=2, speed="1x").bound_faction_id == 2
    assert build_view(world, cfg, bound_faction_id=None, speed="1x").bound_faction_id is None


def test_an_occupied_province_is_contested() -> None:
    world, cfg = _world()
    target = next(
        pid for pid in sorted(world.provinces)
        if world.provinces[pid].owner_faction_id == 0
    )
    assert world.provinces[target].controller_faction_id == 0, "premise: owner controls it"
    world.provinces[target].controller_faction_id = 3
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    cell = next(c for c in view.provinces if c.id == target)
    assert cell.is_contested


def test_a_province_holding_a_hostile_army_is_contested() -> None:
    world, cfg = _world()
    army = world.armies[0]
    here = world.provinces[army.province_id]
    assert here.controller_faction_id == army.faction_id, "premise: army is at home"
    enemy = next(
        fid for fid in sorted(world.factions) if fid != army.faction_id
    )
    world.factions[army.faction_id].at_war_with = {enemy}
    world.factions[enemy].at_war_with = {army.faction_id}
    world.armies[army.id] = army
    intruder = next(a for a in world.armies.values() if a.faction_id == enemy)
    intruder.province_id = here.id
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    cell = next(c for c in view.provinces if c.id == here.id)
    assert cell.is_contested
    assert cell.has_armies


def test_a_starved_province_is_flagged() -> None:
    world, cfg = _world()
    threshold = cfg["balance"]["low_supply_threshold"]
    pid = sorted(world.provinces)[0]
    assert world.provinces[pid].supply_value >= threshold, "premise: starts supplied"
    world.provinces[pid].supply_value = threshold - 0.01
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert next(c for c in view.provinces if c.id == pid).has_supply_problem


def test_the_event_window_is_bounded_and_newest_last() -> None:
    world, cfg = _world()
    engine = SimulationEngine(world, cfg)
    for _ in range(600):
        engine.tick()
    assert len(world.events) > RECENT_EVENT_LIMIT, "premise: the run logged enough events"
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert len(view.recent_events) == RECENT_EVENT_LIMIT
    newest = list(world.events)[-1]
    assert view.recent_events[-1].id == newest.id
    assert [line.id for line in view.recent_events] == sorted(
        line.id for line in view.recent_events
    )


def test_war_counts_are_reported() -> None:
    world, cfg = _world()
    engine = SimulationEngine(world, cfg)
    for _ in range(1500):
        engine.tick()
    assert world.wars, "premise: the run declared at least one war"
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert view.total_wars == len(world.wars)
    assert view.active_wars == sum(
        1 for w in world.wars.values() if w.status == "active"
    )


def test_speed_and_fault_are_carried_through() -> None:
    world, cfg = _world()
    ok = build_view(world, cfg, bound_faction_id=None, speed="16x")
    assert ok.speed == "16x" and ok.faulted is False and ok.fault_message is None
    bad = build_view(world, cfg, bound_faction_id=None, speed="paused", fault_message="boom")
    assert bad.faulted is True and bad.fault_message == "boom"
