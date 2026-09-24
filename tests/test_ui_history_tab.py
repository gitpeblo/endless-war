import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs an X display")

import dataclasses  # noqa: E402

from endless_war.app.snapshot import build_view  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.simulation.engine import SimulationEngine  # noqa: E402
from endless_war.simulation.worldgen import generate_world  # noqa: E402
from endless_war.ui.history_tab import HistoryTab  # noqa: E402
from endless_war.ui.panels import event_log_lines  # noqa: E402


def _view_with_events():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(4 * 365):
        if len(world.events) >= 4:
            break
        engine.tick()
    # The eviction test pops two events, so it needs a few to begin with.
    assert len(world.events) >= 4, "premise: at least four events"
    return engine, world, cfg, build_view(world, cfg, bound_faction_id=None, speed="1x")


def test_every_faction_gets_a_toggle_and_all_start_visible() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    assert sorted(tab.toggles) == [f.id for f in view.factions]
    assert all(button.get_active() for button in tab.toggles.values())
    assert tab.chart.visible == frozenset(f.id for f in view.factions)


def test_unticking_a_faction_hides_it_from_the_chart() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    tab.toggles[1].set_active(False)
    assert 1 not in tab.chart.visible
    tab.set_view(view)
    assert 1 not in tab.chart.visible, "a refresh must not re-tick a hidden faction"
    tab.toggles[1].set_active(True)
    assert 1 in tab.chart.visible


def test_a_faction_that_appears_later_gets_a_toggle_without_resetting_others() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(dataclasses.replace(view, factions=view.factions[:2]))
    tab.toggles[0].set_active(False)
    tab.set_view(view)
    assert sorted(tab.toggles) == [f.id for f in view.factions]
    assert not tab.toggles[0].get_active()
    assert 0 not in tab.chart.visible


def test_the_log_is_newest_first() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    lines = tab.log_lines()
    assert lines == event_log_lines(view)
    newest = view.event_log[-1]
    assert newest.title in lines[0] and newest.body in lines[0]


def _advance_until_new_event(engine, world, view) -> None:
    for _ in range(4 * 365):
        if world.events[-1].id != view.event_log[-1].id:
            return
        engine.tick()
    raise AssertionError("premise: a new event arrives within a year")


def test_new_events_are_added_on_top_without_rebuilding_the_log() -> None:
    # Re-laying out the whole log on every new event stalled the GTK main loop
    # by ~0.2-0.8 s in long games (final review, measured). Rows already shown
    # must survive an update; only new ones are added.
    engine, world, cfg, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    tab.mark_oldest_row("sentinel")
    tab.set_view(view)
    assert tab.log_lines()[-1] == "sentinel", "no new event: nothing may change"
    _advance_until_new_event(engine, world, view)
    later = build_view(world, cfg, bound_faction_id=None, speed="1x", previous=view)
    tab.set_view(later)
    lines = tab.log_lines()
    assert lines[-1] == "sentinel", "the log was rebuilt instead of updated"
    assert lines[:-1] == event_log_lines(later)[:-1]


def test_evicted_events_leave_the_bottom_of_the_log() -> None:
    engine, world, cfg, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    # Emulate the 2000-entry cap: the oldest two go, one new arrives.
    world.events.popleft()
    world.events.popleft()
    world.events.append(dataclasses.replace(world.events[-1], id=world.next_event_id))
    world.next_event_id += 1
    later = build_view(world, cfg, bound_faction_id=None, speed="1x", previous=view)
    tab.set_view(later)
    assert tab.log_lines() == event_log_lines(later)


def test_a_log_from_a_different_run_replaces_the_old_one() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    fresh = build_view(generate_world(seed=7, config=load_config()), load_config(),
                       bound_faction_id=None, speed="1x")
    tab.set_view(fresh)
    assert tab.log_lines() == event_log_lines(fresh)
