from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.panels import event_lines, header_text, status_rows, tray_summary


def _view(bound=None, speed="1x", ticks=0, fault=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    if ticks:
        engine = SimulationEngine(world, cfg)
        for _ in range(ticks):
            engine.tick()
    return build_view(world, cfg, bound_faction_id=bound, speed=speed, fault_message=fault)


def test_the_header_shows_the_simulated_date_and_speed() -> None:
    view = _view()
    text = header_text(view)
    assert view.simulated_at.date().isoformat() in text
    assert "1x" in text


def test_a_faulted_header_says_so() -> None:
    text = header_text(_view(fault="RuntimeError: boom"))
    assert "fault" in text.lower()
    assert "boom" in text


def test_unbound_status_rows_cover_every_faction() -> None:
    view = _view()
    rows = status_rows(view)
    joined = " ".join(label + value for label, value in rows)
    for faction in view.factions:
        assert faction.name in joined


def test_bound_status_rows_describe_that_faction() -> None:
    view = _view(bound=2)
    rows = status_rows(view)
    joined = " ".join(label + value for label, value in rows)
    bound = next(f for f in view.factions if f.id == 2)
    assert bound.name in joined
    assert "provinces" in joined.lower()


def test_status_rows_are_label_value_pairs() -> None:
    for row in status_rows(_view(bound=0)):
        assert isinstance(row, tuple) and len(row) == 2
        assert all(isinstance(part, str) for part in row)


def test_event_lines_are_newest_last_and_dated() -> None:
    view = _view(ticks=600)
    lines = event_lines(view)
    assert lines, "premise: a 600-tick run logs at least one event"
    assert len(lines) == len(view.recent_events)
    assert view.recent_events[-1].title in lines[-1]
    assert view.recent_events[-1].simulated_at.date().isoformat() in lines[-1]


def test_event_lines_on_a_fresh_world_are_empty_not_an_error() -> None:
    assert event_lines(_view()) == []


def test_the_tray_summary_is_one_line() -> None:
    summary = tray_summary(_view(bound=2, ticks=100))
    assert "\n" not in summary
    assert "Meridian Compact" in summary


def test_the_unbound_tray_summary_describes_the_world() -> None:
    summary = tray_summary(_view(ticks=100))
    assert "\n" not in summary
    assert "factions" in summary.lower() or "wars" in summary.lower()
