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
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [{"province_id": 3, "attacker_faction": 0, "defender_faction": 1,
                            "attacker_losses": 9_000, "defender_losses": 8_000,
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
