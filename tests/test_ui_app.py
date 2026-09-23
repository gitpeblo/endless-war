import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"), reason="needs an X display"
)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from endless_war.app.commands import Pause  # noqa: E402
from endless_war.app.service import SimulationService  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.simulation.worldgen import generate_world  # noqa: E402
from endless_war.ui.app import WarRoom  # noqa: E402


def _service():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    return SimulationService(world, cfg, speed="16x"), cfg


def _pump(iterations: int = 40) -> None:
    # `Gtk.events_pending()` only reports queued GDK events; with none
    # pending (as is typical in a quiet, headless-ish X session with no
    # continuous event traffic), this loop can finish in well under a
    # millisecond. That is far less than the simulation thread's poll
    # interval (`SimulationService`'s default `poll_seconds=0.02`), so a
    # caller retrying on a condition (e.g. waiting for a submitted command
    # to be applied) needs this loop to actually span real wall-clock time.
    # A tiny sleep does that without changing what is being tested: it is
    # standard practice when interleaving a GTK main-loop pump with a
    # background thread's own polling cadence.
    for _ in range(iterations):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.001)


def test_the_window_builds_and_shows_a_view() -> None:
    service, cfg = _service()
    room = WarRoom(service, cols=cfg["world"]["grid_cols"])
    service.start()
    try:
        room.window.show_all()
        _pump()
        room.refresh()
        assert room.header.get_text() != ""
    finally:
        room.shutdown()
        service.stop()
    assert not service.is_running()


def test_the_pause_button_reaches_the_service() -> None:
    service, cfg = _service()
    room = WarRoom(service, cols=cfg["world"]["grid_cols"])
    service.start()
    try:
        room.window.show_all()
        _pump()
        service.submit(Pause())
        for _ in range(200):
            _pump(2)
            view = service.latest_view()
            if view is not None and view.speed == "paused":
                break
        assert service.latest_view().speed == "paused"
        room.refresh()
        assert "paused" in room.header.get_text()
    finally:
        room.shutdown()
        service.stop()


def test_closing_the_window_hides_it_instead_of_quitting() -> None:
    service, cfg = _service()
    room = WarRoom(service, cols=cfg["world"]["grid_cols"])
    service.start()
    try:
        room.window.show_all()
        _pump()
        handled = room.window.emit("delete-event", None)
        _pump()
        assert handled is True, "delete-event must be handled, not propagated"
        assert not room.window.get_visible()
        assert service.is_running(), "the simulation keeps running in the tray"
    finally:
        room.shutdown()
        service.stop()
