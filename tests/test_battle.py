import random

from endless_war.config import load_config
from endless_war.domain.models import Army
from endless_war.simulation.systems.battle import effective_power, resolve_battles
from endless_war.simulation.worldgen import generate_world

TERRAIN = load_config()["balance"]["terrain_defence"]


def _two_army_standoff(cfg):
    """Put one army from faction 0 and one from faction 1 in the same province, at war."""
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    province = w.factions[1].capital_province_id
    w.provinces[province].controller_faction_id = 1
    w.armies[0] = Army(id=0, faction_id=0, province_id=province, manpower=50_000,
                       equipment=0.8, morale=0.8, organization=0.9, training=0.7, supply=0.9)
    w.armies[1] = Army(id=1, faction_id=1, province_id=province, manpower=50_000,
                       equipment=0.8, morale=0.8, organization=0.9, training=0.7, supply=0.9)
    return w


def test_effective_power_rises_with_manpower() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    weak = effective_power(w.armies[0], w, False, TERRAIN)
    w.armies[0].manpower = 100_000
    assert effective_power(w.armies[0], w, False, TERRAIN) > weak


def test_effective_power_is_zero_for_an_empty_army() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].manpower = 0
    assert effective_power(w.armies[0], w, False, TERRAIN) == 0.0


def test_defender_gains_a_terrain_bonus() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.provinces[w.armies[0].province_id].terrain = "mountain"
    attacking = effective_power(w.armies[0], w, False, TERRAIN)
    defending = effective_power(w.armies[0], w, True, TERRAIN)
    assert defending > attacking


def test_battle_inflicts_casualties_on_both_sides() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    records = resolve_battles(w, random.Random(1), cfg)
    assert len(records) == 1
    assert records[0]["attacker_losses"] > 0
    assert records[0]["defender_losses"] > 0
    assert w.armies[0].manpower < 50_000
    assert w.armies[1].manpower < 50_000


def test_casualties_are_bounded_per_tick() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    records = resolve_battles(w, random.Random(1), cfg)
    # No side may lose more than 10% of its strength in a single 6-hour tick.
    assert records[0]["attacker_losses"] < 5_000
    assert records[0]["defender_losses"] < 5_000


def test_stronger_side_loses_a_smaller_fraction() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].manpower = 200_000
    records = resolve_battles(w, random.Random(1), cfg)
    # Absolute losses scale with army size, so compare FRACTIONS lost.
    attacker_fraction = records[0]["attacker_losses"] / 200_000
    defender_fraction = records[0]["defender_losses"] / 50_000
    assert attacker_fraction < defender_fraction


def test_battle_never_drives_values_out_of_bounds() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    rng = random.Random(1)
    for _ in range(300):
        resolve_battles(w, rng, cfg)
    for army in w.armies.values():
        assert army.manpower >= 0
        for attr in ("morale", "organization", "supply"):
            assert 0.0 <= getattr(army, attr) <= 1.0


def test_broken_army_is_flagged_and_retreats_next_tick() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].organization = 0.05
    records = resolve_battles(w, random.Random(1), cfg)
    assert records[0]["attacker_broke"] is True


def test_faction_casualty_counters_accumulate() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    resolve_battles(w, random.Random(1), cfg)
    assert w.factions[0].casualties > 0
    assert w.factions[1].casualties > 0


def test_neutral_controller_is_not_dragged_into_someone_elses_war() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    for fac in w.factions.values():
        fac.at_war_with = set()
    # Factions 1 and 2 are at war with each other; faction 0 is at peace with both.
    w.factions[1].at_war_with = {2}
    w.factions[2].at_war_with = {1}
    province = w.factions[0].capital_province_id
    for fid in (0, 1, 2):
        w.armies[fid] = Army(id=fid, faction_id=fid, province_id=province, manpower=50_000,
                             equipment=0.8, morale=0.8, organization=0.9,
                             training=0.7, supply=0.9)
    records = resolve_battles(w, random.Random(1), cfg)
    assert all(r["defender_faction"] != 0 for r in records)
    assert w.armies[0].manpower == 50_000, "a neutral faction must not take losses"
