import random

from endless_war.config import load_config
from endless_war.simulation.systems.diplomacy import (
    note_captures,
    update_diplomacy,
    update_exhaustion,
)
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


def test_exhaustion_does_not_grow_without_new_casualties() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {2}
    w.factions[2].at_war_with = {0}
    fac.casualties = 10_000
    update_exhaustion(w, random.Random(1), cfg)  # absorbs the 10,000
    after_first = fac.exhaustion
    for _ in range(100):
        update_exhaustion(w, random.Random(1), cfg)
    assert fac.exhaustion == after_first, "standing casualties must not keep raising exhaustion"


def test_casualties_from_a_previous_war_do_not_carry_into_the_next() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {2}
    fac.casualties = 50_000
    update_exhaustion(w, random.Random(1), cfg)
    fac.at_war_with = set()
    for _ in range(3000):
        update_exhaustion(w, random.Random(1), cfg)
    assert fac.exhaustion == 0.0
    fac.at_war_with = {2}
    update_exhaustion(w, random.Random(1), cfg)
    assert fac.exhaustion == 0.0, "a new war must start with no inherited exhaustion"


def test_a_capture_only_resets_the_stalemate_timer_of_its_own_war() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    from endless_war.domain.models import War
    w.wars[0] = War(id=0, attackers={0}, defenders={2},
                    started_at=w.current_time, last_capture_tick=0)
    w.wars[1] = War(id=1, attackers={1}, defenders={3},
                    started_at=w.current_time, last_capture_tick=0)
    w.tick_count = 300
    note_captures(w, [{"province_id": 5, "from_faction": 2, "to_faction": 0}])
    assert w.wars[0].last_capture_tick == 300
    assert w.wars[1].last_capture_tick == 0, "an unrelated war's timer must not reset"


def test_a_faction_is_never_at_war_with_itself() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    rng = random.Random(1)
    for _ in range(3000):
        update_diplomacy(w, rng, cfg)
    for fid, fac in w.factions.items():
        assert fid not in fac.at_war_with


def _losing_everything(fid: int = 4, winner: int = 3):
    import random as _random
    from endless_war.config import load_config as _load
    from endless_war.domain.models import War
    from endless_war.simulation.worldgen import generate_world as _gen

    cfg = _load()
    w = _gen(seed=42, config=cfg)
    w.factions[fid].at_war_with = {winner}
    w.factions[winner].at_war_with = {fid}
    w.wars[w.next_war_id] = War(id=w.next_war_id, attackers={winner}, defenders={fid},
                                started_at=w.current_time, last_capture_tick=w.tick_count)
    w.next_war_id += 1
    for p in w.provinces.values():
        if p.controller_faction_id == fid:
            p.controller_faction_id = winner
    return w, cfg, _random.Random(1)


def test_a_faction_with_no_land_is_eliminated() -> None:
    from endless_war.simulation.systems.diplomacy import update_diplomacy
    w, cfg, rng = _losing_everything()
    assert any(a.faction_id == 4 for a in w.armies.values()), "premise: it has armies"
    events = update_diplomacy(w, rng, cfg)
    assert w.factions[4].eliminated
    assert not any(a.faction_id == 4 for a in w.armies.values())
    assert w.factions[4].at_war_with == set() and 4 not in w.factions[3].at_war_with
    assert all(war.status == "ended" for war in w.wars.values() if 4 in war.defenders)
    assert {"kind": "eliminated", "faction": 4} in events


def test_an_eliminated_faction_never_declares_war() -> None:
    from endless_war.simulation.engine import SimulationEngine
    w, cfg, _rng = _losing_everything()
    engine = SimulationEngine(w, cfg)
    engine.run(400)
    assert w.factions[4].eliminated
    assert not any(4 in war.attackers | war.defenders for war in w.wars.values() if war.status == "active")


def _ending_war():
    """A 3-vs-4 war that ends on stalemate at the next update."""
    import random as _random
    from endless_war.config import load_config as _load
    from endless_war.domain.models import War
    from endless_war.simulation.worldgen import generate_world as _gen

    cfg = _load()
    w = _gen(seed=42, config=cfg)
    w.factions[3].at_war_with = {4}
    w.factions[4].at_war_with = {3}
    w.tick_count = cfg["balance"]["peace_stalemate_ticks"] + 10
    w.wars[w.next_war_id] = War(id=w.next_war_id, attackers={3}, defenders={4},
                                started_at=w.current_time, last_capture_tick=0)
    w.next_war_id += 1
    return w, cfg, _random.Random(1)


def test_peace_hands_occupied_land_to_the_occupier() -> None:
    w, cfg, rng = _ending_war()
    pid = next(p for p in sorted(w.provinces) if w.provinces[p].owner_faction_id == 4)
    w.provinces[pid].controller_faction_id = 3
    events = update_diplomacy(w, rng, cfg)
    assert w.provinces[pid].owner_faction_id == 3
    peace = next(e for e in events if e["kind"] == "peace")
    assert (pid, 4, 3) in peace["annexed"]


def test_peace_settles_a_third_partys_land_the_winner_holds() -> None:
    w, cfg, rng = _ending_war()
    pid = next(p for p in sorted(w.provinces) if w.provinces[p].owner_faction_id == 1)
    w.provinces[pid].controller_faction_id = 3  # taken from faction 1 in an earlier war
    update_diplomacy(w, rng, cfg)
    assert w.provinces[pid].owner_faction_id == 3


def test_land_still_disputed_with_its_owner_is_not_settled() -> None:
    w, cfg, rng = _ending_war()
    w.factions[3].at_war_with.add(1)
    w.factions[1].at_war_with = {3}
    pid = next(p for p in sorted(w.provinces) if w.provinces[p].owner_faction_id == 1)
    w.provinces[pid].controller_faction_id = 3
    update_diplomacy(w, rng, cfg)
    assert w.provinces[pid].owner_faction_id == 1, "3 and 1 are still at war over it"
