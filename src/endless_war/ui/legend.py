"""The map legend.

Every swatch is drawn with the map's own cell painters, so the legend cannot
drift from what the map actually shows. `legend_entries` and `render_legend`
need no display; `LegendView` is the GTK widget wrapped around them.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import ProvinceCell, WorldView  # noqa: E402
from endless_war.ui.geometry import Cell  # noqa: E402
from endless_war.ui.map_view import (  # noqa: E402
    BACKGROUND,
    _army,
    _bound_outline,
    _capital,
    _fill,
    _hatch,
)

PAD = 8
ROW = 24
SWATCH = 18
TEXT_RGB = (0.85, 0.85, 0.85)
FONT_SIZE = 12
NEUTRAL_KEY = "grey"
# Capitals and armies are sized relative to their cell; on an 18px swatch
# they would be specks. Paint them on a larger cell, the largest whose
# capital diamond (0.22 of the cell, each way) still fits inside a swatch.
SYMBOL_CELL = 36.0


@dataclass(frozen=True, slots=True)
class LegendEntry:
    kind: str  # faction | bound | contested | supply | capital | army
    label: str
    color_key: str


def legend_entries(view: WorldView) -> list[LegendEntry]:
    """Faction colours first, then what each map symbol means."""
    entries = [LegendEntry("faction", f.name, f.color_key) for f in view.factions]
    bound = next((f for f in view.factions if f.id == view.bound_faction_id), None)
    if bound is not None:
        entries.append(LegendEntry("bound", "Your territory", bound.color_key))
    entries += [
        LegendEntry("contested", "Occupied or under attack", NEUTRAL_KEY),
        LegendEntry("supply", "Supply problem", NEUTRAL_KEY),
        LegendEntry("capital", "Capital", NEUTRAL_KEY),
        LegendEntry("army", "Army present", NEUTRAL_KEY),
    ]
    return entries


def legend_height(view: WorldView) -> int:
    return 2 * PAD + len(legend_entries(view)) * ROW


def _province(entry: LegendEntry) -> ProvinceCell:
    return ProvinceCell(
        id=0,
        name="",
        owner_faction_id=None,
        controller_faction_id=None,
        color_key=entry.color_key,
        is_capital=False,
        is_contested=False,
        has_armies=False,
        has_supply_problem=entry.kind == "supply",
        terrain="plains",
    )


def _symbol_cell(swatch: Cell, anchor: float) -> Cell:
    """A map-sized cell placed so its `anchor` point is the swatch centre."""
    cx = swatch.x + swatch.width / 2
    cy = swatch.y + swatch.height / 2
    return Cell(cx - anchor * SYMBOL_CELL, cy - anchor * SYMBOL_CELL, SYMBOL_CELL, SYMBOL_CELL)


def _swatch(cr, swatch: Cell, entry: LegendEntry) -> None:
    province = _province(entry)
    cr.save()
    cr.rectangle(swatch.x, swatch.y, swatch.width, swatch.height)
    cr.clip()
    _fill(cr, swatch, province)
    if entry.kind == "contested":
        _hatch(cr, swatch)
    elif entry.kind == "capital":
        _capital(cr, _symbol_cell(swatch, 0.5))
    elif entry.kind == "army":
        _army(cr, _symbol_cell(swatch, 0.78))
    elif entry.kind == "bound":
        _bound_outline(cr, swatch, province)
    cr.restore()


def render_legend(cr, view: WorldView, width: float, height: float) -> None:
    """Draw the legend for `view` into a `width` x `height` area."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    cr.select_font_face("Sans")
    cr.set_font_size(FONT_SIZE)
    for row, entry in enumerate(legend_entries(view)):
        top = PAD + row * ROW
        _swatch(cr, Cell(PAD, top, SWATCH, SWATCH), entry)
        cr.set_source_rgb(*TEXT_RGB)
        cr.move_to(PAD + SWATCH + 8, top + SWATCH / 2 + FONT_SIZE * 0.35)
        cr.show_text(entry.label)


class LegendView(Gtk.DrawingArea):
    """A drawing area that paints the legend for the newest view."""

    def __init__(self) -> None:
        super().__init__()
        self._view: WorldView | None = None
        self.connect("draw", self._on_draw)

    def set_view(self, view: WorldView) -> None:
        self._view = view
        height = legend_height(view)
        if self.get_size_request()[1] != height:
            self.set_size_request(-1, height)
        self.queue_draw()

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        if self._view is None:
            return False
        render_legend(cr, self._view, allocation.width, allocation.height)
        return False
