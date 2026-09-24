import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs an X display")

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from endless_war.app.snapshot import build_view  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.simulation.worldgen import generate_world  # noqa: E402
from endless_war.ui.iso import board_for, board_with  # noqa: E402
from endless_war.ui.map_view import MapView  # noqa: E402


def _shown_map():
    cfg = load_config()
    view = build_view(generate_world(seed=42, config=cfg), cfg, bound_faction_id=None, speed="1x")
    window = Gtk.Window()
    window.set_default_size(600, 400)
    area = MapView(cfg["world"]["grid_cols"])
    window.add(area)
    window.show_all()
    area.set_view(view)
    for _ in range(50):
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
    return window, area


def _size(area):
    a = area.get_allocation()
    return a.width, a.height


def test_scrolling_up_zooms_in_one_step_and_down_zooms_back_to_fit() -> None:
    window, area = _shown_map()
    try:
        w, h = _size(area)
        fit = board_for(96, 12, w, h).scale
        area._on_scroll(area, SimpleNamespace(direction=Gdk.ScrollDirection.UP, x=w / 2, y=h / 2))
        assert area.camera is not None and area.camera.scale == fit + 1
        area._on_scroll(area, SimpleNamespace(direction=Gdk.ScrollDirection.DOWN, x=w / 2, y=h / 2))
        assert area.camera is None
    finally:
        window.destroy()


def test_smooth_scrolling_zooms_too() -> None:
    window, area = _shown_map()
    try:
        w, h = _size(area)
        event = SimpleNamespace(
            direction=Gdk.ScrollDirection.SMOOTH, x=w / 2, y=h / 2,
            get_scroll_deltas=lambda: (True, 0.0, -1.0),
        )
        area._on_scroll(area, event)
        assert area.camera is not None
    finally:
        window.destroy()


def test_a_middle_button_drag_pans_the_board() -> None:
    window, area = _shown_map()
    try:
        w, h = _size(area)
        before = board_with(96, 12, w, h, area.camera)
        area._on_press(area, SimpleNamespace(button=2, x=100.0, y=100.0))
        area._on_motion(area, SimpleNamespace(x=130.0, y=90.0))
        area._on_motion(area, SimpleNamespace(x=150.0, y=80.0))
        area._on_release(area, SimpleNamespace(button=2, x=150.0, y=80.0))
        after = board_with(96, 12, w, h, area.camera)
        assert (after.origin_x - before.origin_x, after.origin_y - before.origin_y) == (50, -20)
        area._on_motion(area, SimpleNamespace(x=300.0, y=300.0))
        assert board_with(96, 12, w, h, area.camera) == after, "moving after release must not pan"
    finally:
        window.destroy()


def test_other_buttons_do_not_pan() -> None:
    window, area = _shown_map()
    try:
        area._on_press(area, SimpleNamespace(button=1, x=100.0, y=100.0))
        area._on_motion(area, SimpleNamespace(x=200.0, y=200.0))
        assert area.camera is None
    finally:
        window.destroy()
