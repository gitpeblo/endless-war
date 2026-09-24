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


def test_status_rows_with_unknown_bound_faction_shows_unknown_and_world() -> None:
    view = _view(bound=999)
    rows = status_rows(view)
    joined = " ".join(label + value for label, value in rows)
    assert "999" in joined, "unknown faction id must be visible"
    assert "unknown" in joined.lower(), "must be marked as unknown"
    for faction in view.factions:
        assert faction.name in joined, "world factions still shown"


def test_tray_summary_with_unknown_bound_faction_shows_unknown_and_world() -> None:
    view = _view(bound=999, ticks=100)
    summary = tray_summary(view)
    assert "\n" not in summary, "must remain single line"
    assert "999" in summary, "unknown faction id must be visible"
    assert "unknown" in summary.lower(), "must be marked as unknown"
    assert "factions" in summary.lower() or "wars" in summary.lower(), "world info present"


from endless_war.app.snapshot import build_view as _build_view
from endless_war.config import load_config as _load_config
from endless_war.simulation.engine import SimulationEngine as _Engine
from endless_war.simulation.worldgen import generate_world as _generate_world
from endless_war.ui.panels import event_log_lines


def test_event_log_lines_are_every_event_newest_first() -> None:
    cfg = _load_config()
    world = _generate_world(seed=42, config=cfg)
    engine = _Engine(world, cfg)
    for _ in range(4 * 365):
        if len(world.events) > 20:
            break
        engine.tick()
    view = _build_view(world, cfg, bound_faction_id=None, speed="1x")
    lines = event_log_lines(view)
    assert len(lines) == len(view.event_log) > 20
    newest = view.event_log[-1]
    assert lines[0] == f"{newest.simulated_at.date().isoformat()}  {newest.title}: {newest.body}"
