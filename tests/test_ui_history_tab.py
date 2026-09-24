import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs an X display")

import dataclasses  # noqa: E402

from endless_war.app.snapshot import build_view  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.simulation.engine import SimulationEngine  # noqa: E402
from endless_war.simulation.worldgen import generate_world  # noqa: E402
from endless_war.ui.history_tab import HistoryTab  # noqa: E402


def _view_with_events():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(4 * 365):
        if len(world.events) >= 2:
            break
        engine.tick()
    assert len(world.events) >= 2, "premise: at least two events"
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
    newest = view.event_log[-1]
    first = tab.log.get_text().splitlines()[0]
    assert newest.title in first and newest.body in first


def test_the_log_is_not_reset_when_no_new_event_arrived() -> None:
    # Re-setting a Label's text every 250 ms would throw away the reader's
    # scroll position, so the log only changes when the newest event does.
    engine, world, cfg, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    tab.log.set_text("sentinel")
    tab.set_view(view)
    assert tab.log.get_text() == "sentinel"
    for _ in range(4 * 365):
        if world.events[-1].id != view.event_log[-1].id:
            break
        engine.tick()
    tab.set_view(build_view(world, cfg, bound_faction_id=None, speed="1x"))
    assert tab.log.get_text() != "sentinel"
