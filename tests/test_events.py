from endless_war.config import load_config
from endless_war.simulation.systems.events import MAX_EVENTS, record_events
from endless_war.simulation.worldgen import generate_world


def test_war_declaration_is_logged_as_critical() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [], [], [{"kind": "war_declared", "attacker": 0, "defender": 1}])
    assert len(w.events) == 1
    event = w.events[-1]
    assert event.category == "diplomacy"
    assert event.severity == "critical"
    assert "Valdran Hegemony" in event.title or "Valdran Hegemony" in event.body


def test_capture_is_logged_with_both_factions() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [], [{"province_id": 5, "from_faction": 1, "to_faction": 0}], [])
    assert len(w.events) == 1
    assert w.events[-1].category == "territory"
    assert w.events[-1].related_entity_ids == [5, 1, 0]


def test_small_battles_are_not_logged() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [{"province_id": 3, "attacker_faction": 0, "defender_faction": 1,
                            "attacker_losses": 4, "defender_losses": 3,
                            "attacker_broke": False, "defender_broke": False}], [], [])
    assert len(w.events) == 0, "trivial skirmishes must not flood the log"


def test_large_battles_are_logged() -> None:
    """The fixture must be a battle the simulation can actually produce.

    `resolve_battles` bounds combined per-tick losses at `2 * base_casualty_rate`
    of the engaged manpower, so the old 17,000-casualty fixture tested a state
    that cannot occur -- and the old 5,000 threshold it cleared was itself
    unreachable, which is why ten years logged zero military events. Measured
    maximum single-tick total across three decade-long runs: 3,687.
    """
    cfg = load_config()
    threshold = cfg["balance"]["significant_battle_losses"]
    attacker_losses, defender_losses = 1_500, 1_100      # 2,600: over the bar, under the bound
    assert attacker_losses + defender_losses > threshold, "fixture: must clear the threshold"
    assert attacker_losses + defender_losses < 3_687, "fixture: must stay within the bound"

    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [{"province_id": 3, "attacker_faction": 0, "defender_faction": 1,
                            "attacker_losses": attacker_losses,
                            "defender_losses": defender_losses,
                            "attacker_broke": False, "defender_broke": False}], [], [])
    assert len(w.events) == 1
    assert w.events[-1].category == "military"


def test_event_ids_are_unique_and_increasing() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(10):
        record_events(w, cfg, [], [], [{"kind": "peace", "attacker": 0, "defender": 1}])
    ids = [e.id for e in w.events]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_log_is_capped_and_keeps_the_newest() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(MAX_EVENTS + 50):
        record_events(w, cfg, [], [], [{"kind": "peace", "attacker": 0, "defender": 1}])
    assert len(w.events) == MAX_EVENTS
    assert [e.id for e in w.events] == list(range(50, MAX_EVENTS + 50))
