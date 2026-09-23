"""The strategic map.

`render_map` draws onto any cairo context, so it can be tested against an
image surface with no display. `MapView` is the GTK widget wrapped around it.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import ProvinceCell, WorldView  # noqa: E402
from endless_war.ui.colors import darken, faction_rgb, lighten  # noqa: E402
from endless_war.ui.geometry import Cell, cell_for  # noqa: E402

BACKGROUND = (0.11, 0.12, 0.14)
HATCH_RGBA = (0.05, 0.05, 0.05, 0.55)
CAPITAL_RGB = (1.0, 1.0, 1.0)
ARMY_RGB = (0.08, 0.08, 0.08)


def _fill(cr, cell: Cell, province: ProvinceCell) -> None:
    rgb = faction_rgb(province.color_key)
    if province.has_supply_problem:
        rgb = darken(rgb)
    cr.set_source_rgb(*rgb)
    cr.rectangle(cell.x, cell.y, cell.width, cell.height)
    cr.fill()


def _hatch(cr, cell: Cell) -> None:
    cr.save()
    cr.rectangle(cell.x, cell.y, cell.width, cell.height)
    cr.clip()
    cr.set_source_rgba(*HATCH_RGBA)
    cr.set_line_width(1.5)
    step = 6.0
    offset = -cell.height
    while offset < cell.width:
        cr.move_to(cell.x + offset, cell.y)
        cr.line_to(cell.x + offset + cell.height, cell.y + cell.height)
        offset += step
    cr.stroke()
    cr.restore()


def _capital(cr, cell: Cell) -> None:
    size = min(cell.width, cell.height) * 0.22
    cx, cy = cell.x + cell.width / 2, cell.y + cell.height / 2
    cr.set_source_rgb(*CAPITAL_RGB)
    cr.move_to(cx, cy - size)
    cr.line_to(cx + size, cy)
    cr.line_to(cx, cy + size)
    cr.line_to(cx - size, cy)
    cr.close_path()
    cr.fill()


def _army(cr, cell: Cell) -> None:
    radius = min(cell.width, cell.height) * 0.12
    cr.set_source_rgb(*ARMY_RGB)
    cr.arc(cell.x + cell.width * 0.78, cell.y + cell.height * 0.78, radius, 0, 6.2832)
    cr.fill()


def _bound_outline(cr, cell: Cell, province: ProvinceCell) -> None:
    cr.set_source_rgb(*lighten(faction_rgb(province.color_key)))
    cr.set_line_width(2.0)
    cr.rectangle(cell.x + 1, cell.y + 1, cell.width - 2, cell.height - 2)
    cr.stroke()


def render_map(cr, view: WorldView, width: float, height: float, cols: int) -> None:
    """Draw every province of `view` into a `width` x `height` area."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    count = len(view.provinces)
    if count == 0 or width <= 0 or height <= 0:
        return

    for province in view.provinces:
        cell = cell_for(province.id, count, cols, width, height)
        _fill(cr, cell, province)
        if province.is_contested:
            _hatch(cr, cell)
        if province.is_capital:
            _capital(cr, cell)
        if province.has_armies:
            _army(cr, cell)
        if (
            view.bound_faction_id is not None
            and province.controller_faction_id == view.bound_faction_id
        ):
            _bound_outline(cr, cell, province)


class MapView(Gtk.DrawingArea):
    """A drawing area that paints the newest `WorldView` it was given."""

    def __init__(self, cols: int) -> None:
        super().__init__()
        self._cols = cols
        self._view: WorldView | None = None
        self.set_size_request(480, 320)
        self.connect("draw", self._on_draw)

    def set_view(self, view: WorldView) -> None:
        self._view = view
        self.queue_draw()

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        if self._view is None:
            cr.set_source_rgb(*BACKGROUND)
            cr.rectangle(0, 0, allocation.width, allocation.height)
            cr.fill()
            return False
        render_map(cr, self._view, allocation.width, allocation.height, self._cols)
        return False
