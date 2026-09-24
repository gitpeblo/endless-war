import random

from endless_war.ai.strategic import choose_strategic_actions
from endless_war.config import load_config
from endless_war.simulation.systems.movement import update_movement
from endless_war.simulation.worldgen import generate_world


def test_at_peace_armies_are_given_no_offensive_orders() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert w.provinces[army.destination_id].controller_faction_id == army.faction_id


def test_at_war_some_army_is_ordered_toward_the_enemy() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    # Faction 0 and faction 1 share no border at seed 42; use faction 3,
    # which borders faction 0 at provinces [17, 28, 39, 50].
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    # Place one of faction 0's armies on the shared border explicitly; the
    # starting layout does not guarantee an army starts adjacent to faction 3.
    border = next(
        pid for pid in sorted(w.provinces)
        if w.provinces[pid].controller_faction_id == 0
        and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[pid].neighbors)
    )
    next(a for a in w.armies.values() if a.faction_id == 0).province_id = border
    choose_strategic_actions(w, random.Random(1), cfg)
    ordered = [
        a for a in w.armies.values()
        if a.faction_id == 0
        and a.destination_id is not None
        and w.provinces[a.destination_id].controller_faction_id == 3
    ]
    assert ordered, "faction 0 should push into faction 3 territory"


def test_destinations_are_always_adjacent() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert army.destination_id in w.provinces[army.province_id].neighbors


def test_broken_army_is_ordered_to_withdraw_to_friendly_ground() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    army = next(a for a in w.armies.values() if a.faction_id == 0)
    army.organization = 0.1
    army.morale = 0.1
    choose_strategic_actions(w, random.Random(1), cfg)
    if army.destination_id is not None:
        assert w.provinces[army.destination_id].controller_faction_id == 0
    assert army.stance == "withdrawal"


def test_ai_is_deterministic_for_a_given_seed() -> None:
    cfg = load_config()
    a = generate_world(seed=42, config=cfg)
    b = generate_world(seed=42, config=cfg)
    for w in (a, b):
        w.factions[0].at_war_with = {3}
        w.factions[3].at_war_with = {0}
    choose_strategic_actions(a, random.Random(7), cfg)
    choose_strategic_actions(b, random.Random(7), cfg)
    assert [x.destination_id for x in a.armies.values()] == [
        x.destination_id for x in b.armies.values()
    ]


def test_broken_army_at_war_in_the_rear_is_not_ordered_to_withdraw() -> None:
    """The AI half of the recovery ruling, exercised through the real path.

    `test_broken_army_in_safe_territory_recovers` reaches
    `_standing_somewhere_safe` through its `if not at_war: return True`
    short-circuit, so re-introducing the unconditional withdrawal order would
    not fail it. This one is at war, so the predicate has to do its real work:
    nothing hostile adjacent, nothing hostile standing here, therefore hold.

    Fixture from worldgen at seed 42: army 0 (faction 0) is in province 13,
    every neighbour of which faction 0 also controls -- asserted, not assumed --
    and factions 0 and 3 genuinely border, so the war is not a fiction.
    """
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    assert army.faction_id == 0 and army.province_id == 13
    assert all(w.provinces[n].controller_faction_id == 0 for n in w.provinces[13].neighbors), (
        "fixture: province 13 must be interior to faction 0"
    )
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    assert w.factions[0].at_war_with, "fixture: the safety predicate must not short-circuit"
    assert not [
        a for a in w.armies.values() if a.province_id == 13 and a.faction_id in {3}
    ], "fixture: no hostile army may be standing in province 13"

    army.organization = 0.20          # broken
    army.supply = 1.0

    choose_strategic_actions(w, random.Random(1), cfg)

    assert army.stance == "withdrawal"
    assert army.destination_id is None, (
        "a broken army in its own rear must hold, not be marched around; "
        "marching is what keeps it from ever recovering"
    )

    update_movement(w, random.Random(1), cfg)
    assert army.organization > 0.20, "and holding must let it recover"


def _war_world():
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    return w, cfg


def _rear_province(w, fid, enemy):
    fronts = {p for p in w.provinces if w.provinces[p].controller_faction_id == fid
              and any(w.provinces[n].controller_faction_id == enemy for n in w.provinces[p].neighbors)}
    for pid in sorted(w.provinces):
        p = w.provinces[pid]
        if p.controller_faction_id == fid and pid not in fronts and not any(
            w.provinces[n].controller_faction_id != fid for n in p.neighbors
        ):
            return pid
    raise AssertionError("premise: faction has an interior province")


def test_an_idle_army_in_the_rear_steps_toward_the_front() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    rear = _rear_province(w, 0, 3)
    w.armies[1] = Army(id=1, faction_id=0, province_id=rear, manpower=20_000)
    choose_strategic_actions(w, random.Random(1), cfg)
    step = w.armies[1].destination_id
    assert step is not None and step in w.provinces[rear].neighbors
    assert w.provinces[step].controller_faction_id == 0


def test_idle_armies_spread_over_the_front_instead_of_stacking() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    rear = _rear_province(w, 0, 3)
    for aid in range(1, 5):
        w.armies[aid] = Army(id=aid, faction_id=0, province_id=rear, manpower=20_000)
    w.armies[9] = Army(id=9, faction_id=3, province_id=next(
        p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 3), manpower=40_000)
    # From one rear province the first step can be shared even when the
    # targets differ, so march them and note where each reaches the front
    # (its first tick with a hostile neighbour, when it stops being idle).
    arrived: dict[int, int] = {}
    for _ in range(12):
        choose_strategic_actions(w, random.Random(1), cfg)
        for aid in range(1, 5):
            if aid not in arrived and w.armies[aid].stance != "balanced":
                arrived[aid] = w.armies[aid].province_id
        update_movement(w, random.Random(1), cfg)
    assert len(arrived) == 4, "premise: all four reach the front"
    assert len(set(arrived.values())) >= 2, f"all four reached the same spot: {arrived}"


def test_a_broken_stack_does_not_deter_an_attack() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    border = next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 0
                  and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[p].neighbors))
    target = next(n for n in w.provinces[border].neighbors if w.provinces[n].controller_faction_id == 3)
    w.armies[1] = Army(id=1, faction_id=0, province_id=border, manpower=20_000)
    w.armies[2] = Army(id=2, faction_id=3, province_id=target, manpower=150_000,
                       organization=0.0, morale=0.0)
    choose_strategic_actions(w, random.Random(1), cfg)
    assert w.armies[1].destination_id == target


def test_an_empty_hostile_province_is_always_attackable() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    border = next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 0
                  and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[p].neighbors))
    w.armies[1] = Army(id=1, faction_id=0, province_id=border, manpower=500)
    choose_strategic_actions(w, random.Random(1), cfg)
    assert w.provinces[w.armies[1].destination_id].controller_faction_id == 3
