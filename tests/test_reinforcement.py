from endless_war.config import load_config
from endless_war.simulation.systems.economy import reinforce_armies
from endless_war.simulation.worldgen import generate_world


def _world():
    cfg = load_config()
    return generate_world(seed=42, config=cfg), cfg


def test_a_faction_with_no_armies_raises_one_from_its_reserves() -> None:
    # Destroyed armies were never replaced (the ledgered "reinforcement gap"):
    # at seed 99 faction 3 held 29 provinces and 1,021,298 reserves, no army.
    w, cfg = _world()
    for aid in [a for a in sorted(w.armies) if w.armies[a].faction_id == 3]:
        del w.armies[aid]
    w.factions[3].manpower = 500_000
    reinforce_armies(w, cfg)
    raised = [a for a in w.armies.values() if a.faction_id == 3]
    assert raised, "no army raised"
    assert w.factions[3].manpower < 500_000
    assert all(w.provinces[a.province_id].controller_faction_id == 3 for a in raised)


def test_reserves_flow_into_armies_on_supplied_land_only() -> None:
    w, cfg = _world()
    w.factions[0].manpower = 400_000
    mine = [a for a in w.armies.values() if a.faction_id == 0]
    starved, fed = mine[0], mine[1]
    w.provinces[starved.province_id].supply_value = cfg["balance"]["min_supply"]
    w.provinces[fed.province_id].supply_value = 1.0
    if starved.province_id == fed.province_id:
        fed.province_id = next(
            p for p in sorted(w.provinces)
            if w.provinces[p].controller_faction_id == 0 and p != starved.province_id
        )
        w.provinces[fed.province_id].supply_value = 1.0
    before = (starved.manpower, fed.manpower)
    reinforce_armies(w, cfg)
    assert starved.manpower == before[0], "no reinforcement without supply"
    assert fed.manpower > before[1]


def test_reinforcement_is_deterministic() -> None:
    a, cfg = _world()
    b, _ = _world()
    for w in (a, b):
        w.factions[0].manpower = 300_000
        reinforce_armies(w, cfg)
    assert [(x.id, x.manpower, x.province_id) for x in a.armies.values()] == [
        (x.id, x.manpower, x.province_id) for x in b.armies.values()
    ]


def test_men_in_the_field_count_against_the_mobilization_ceiling() -> None:
    # Recruitment refilled the pool while reinforcement drained it into armies,
    # so fielded men never counted: by year 30 at seed 42, 48M of 48.6M people
    # were under arms (final review).
    from endless_war.simulation.systems.economy import update_recruitment
    import random

    w, cfg = _world()
    population = sum(p.population for p in w.provinces.values() if p.controller_faction_id == 0)
    cap = population * cfg["balance"]["mobilization_ceiling"]
    for a in w.armies.values():
        if a.faction_id == 0:
            a.manpower = int(cap)  # already more than the whole ceiling in the field
    w.factions[0].manpower = 0
    for _ in range(100):
        update_recruitment(w, random.Random(1), cfg)
    assert w.factions[0].manpower == 0, "no recruits while the field already exceeds the ceiling"
