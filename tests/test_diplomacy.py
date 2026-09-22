import random

from endless_war.config import load_config
from endless_war.simulation.systems.diplomacy import update_diplomacy, update_exhaustion
from endless_war.simulation.worldgen import generate_world


def test_exhaustion_rises_with_casualties_and_stays_bounded() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {1}
    w.factions[1].at_war_with = {0}
    fac.casualties = fac.manpower * 2
    for _ in range(200):
        update_exhaustion(w, random.Random(1), cfg)
    assert 0.0 <= fac.exhaustion <= 1.0
    assert fac.exhaustion > 0.0


def test_exhaustion_decays_in_peacetime() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = set()
    fac.exhaustion = 0.5
    for _ in range(50):
        update_exhaustion(w, random.Random(1), cfg)
    assert fac.exhaustion < 0.5


def test_war_support_falls_as_exhaustion_rises() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {1}
    fac.exhaustion = 0.9
    fac.war_support = 0.8
    update_exhaustion(w, random.Random(1), cfg)
    assert fac.war_support < 0.8


def test_a_war_eventually_gets_declared() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    # Guarantee faction 0 clears the strength ratio, so this tests the code path
    # rather than the luck of the seed. At seed 42, faction 0 borders factions
    # 2, 3, and 4 (it does not border faction 1).
    w.factions[0].manpower *= 10
    rng = random.Random(1)
    for _ in range(5000):
        update_diplomacy(w, rng, cfg)
        if w.wars:
            break
    assert w.wars, "no war was ever declared"


def test_declaration_is_mutual_and_recorded() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].manpower *= 10
    rng = random.Random(1)
    for _ in range(5000):
        events = update_diplomacy(w, rng, cfg)
        declared = [e for e in events if e["kind"] == "war_declared"]
        if declared:
            a, d = declared[0]["attacker"], declared[0]["defender"]
            assert d in w.factions[a].at_war_with
            assert a in w.factions[d].at_war_with
            return
    raise AssertionError("no war was declared")


def test_exhausted_factions_make_peace() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    from endless_war.domain.models import War
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    w.wars[0] = War(id=0, attackers={0}, defenders={1},
                    started_at=w.current_time, status="active")
    w.next_war_id = 1
    w.factions[0].exhaustion = 0.9
    w.factions[1].exhaustion = 0.9
    events = update_diplomacy(w, random.Random(1), cfg)
    assert any(e["kind"] == "peace" for e in events)
    assert w.factions[0].at_war_with == set()
    assert w.wars[0].status == "ended"


def test_a_faction_is_never_at_war_with_itself() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    rng = random.Random(1)
    for _ in range(3000):
        update_diplomacy(w, rng, cfg)
    for fid, fac in w.factions.items():
        assert fid not in fac.at_war_with
