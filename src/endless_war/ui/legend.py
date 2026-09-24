"""The map legend.

Swatches are painted with the map's own painters on a small top-face diamond,
so the legend cannot drift from what the map shows. The terrain section shows
the same darkened tiles the map uses. `legend_entries` and `render_legend`
need no display; `LegendView` is the GTK widget wrapped around them.
"""

from __future__ import annotations

from dataclasses import dataclass

import cairo
import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import WorldView  # noqa: E402
from endless_war.ui import iso  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.map_view import (  # noqa: E402
    BACKGROUND,
    SUPPLY_ALPHA,
    WASH_ALPHA,
    _blit,
    _face,
    _hatch,
    _outline,
    _wash,
)
from endless_war.ui.structures import load_structure, tank_for  # noqa: E402
from endless_war.ui.terrain import load_sheet, tile_for  # noqa: E402

PAD = 8
ROW = 24
TERRAIN_ROW = 30
THUMB_W = 48  # the terrain thumbnail column; symbol swatches centre in it
SWATCH_S = 0.5  # symbol swatches are a half-size tile face
TEXT_RGB = (0.85, 0.85, 0.85)
HEADING_RGB = (0.60, 0.61, 0.64)
GROUND_RGB = (0.30, 0.32, 0.28)  # about the darkened plains: symbols need a ground to show on
FONT_SIZE = 12
NEUTRAL_KEY = "grey"
TERRAIN_ORDER = ("plains", "forest", "hills", "mountain", "urban")


@dataclass(frozen=True, slots=True)
class LegendEntry:
    kind: str  # faction | bound | contested | supply | army | capital | industry | town | heading | terrain
    label: str
    color_key: str
    terrain: str = ""


def legend_entries(view: WorldView) -> list[LegendEntry]:
    """Faction colours, then what each map symbol means, then the terrains."""
    entries = [LegendEntry("faction", f.name, f.color_key) for f in view.factions]
    bound = next((f for f in view.factions if f.id == view.bound_faction_id), None)
    if bound is not None:
        entries.append(LegendEntry("bound", "Your territory", bound.color_key))
    entries += [
        LegendEntry("contested", "Occupied or under attack", NEUTRAL_KEY),
        LegendEntry("supply", "Supply problem", NEUTRAL_KEY),
        LegendEntry("army", "Army (in its faction's colour)", NEUTRAL_KEY),
        LegendEntry("capital", "Capital (supply source)", NEUTRAL_KEY),
        LegendEntry("town", "Town (urban province)", NEUTRAL_KEY),
        LegendEntry("heading", "Terrain", NEUTRAL_KEY),
    ]
    entries += [LegendEntry("terrain", t.capitalize(), NEUTRAL_KEY, t) for t in TERRAIN_ORDER]
    return entries


STRUCTURE_KINDS = ("army", "capital", "town")


def row_height(entry: LegendEntry) -> int:
    return TERRAIN_ROW if entry.kind == "terrain" or entry.kind in STRUCTURE_KINDS else ROW


def legend_height(view: WorldView) -> int:
    return 2 * PAD + sum(row_height(e) for e in legend_entries(view))


def _row_top(entries: list[LegendEntry], index: int) -> int:
    return PAD + sum(row_height(e) for e in entries[:index])


def _swatch_origin(entries: list[LegendEntry], index: int) -> tuple[float, float]:
    """Top-left of the half-size tile cell whose face is centred in the row."""
    s = SWATCH_S
    top = _row_top(entries, index)
    face_mid = (iso.FACE_TOP + iso.FACE_H / 2) * s
    return PAD + (THUMB_W - iso.TILE_W * s) / 2, top + ROW / 2 - face_mid


def swatch_centre(entries: list[LegendEntry], index: int) -> tuple[float, float]:
    x, y = _swatch_origin(entries, index)
    return x + iso.FACE_W / 2 * SWATCH_S, y + (iso.FACE_TOP + iso.FACE_H / 2) * SWATCH_S


def _symbol(cr, entry: LegendEntry, x: float, y: float) -> None:
    s = SWATCH_S
    _face(cr, x, y, s)
    cr.set_source_rgb(*GROUND_RGB)
    cr.fill()
    rgb = faction_rgb(entry.color_key)
    if entry.kind in ("faction", "bound"):
        _wash(cr, x, y, s, rgb, WASH_ALPHA)
    if entry.kind == "bound":
        _outline(cr, x, y, s, rgb)
    elif entry.kind == "contested":
        _hatch(cr, x, y, s)
    elif entry.kind == "supply":
        _wash(cr, x, y, s, (0.0, 0.0, 0.0), SUPPLY_ALPHA)



def _thumbnail(cr, sheet, terrain: str, top: float) -> None:
    # The top face and a little of the tall features above it, clipped to the row.
    cr.save()
    cr.rectangle(PAD, top, THUMB_W, TERRAIN_ROW)
    cr.clip()
    _blit(cr, sheet, tile_for(terrain, 0), PAD, top - 12, 1)
    cr.restore()


def _sprite(cr, name: str, top: float) -> None:
    # The sprite as the map draws it at scale 1, clipped to the row.
    cr.save()
    cr.rectangle(PAD, top, THUMB_W, TERRAIN_ROW)
    cr.clip()
    sprite = tank_for(NEUTRAL_KEY) if name == "tank" else load_structure(name)
    cr.set_source_surface(sprite, PAD + (THUMB_W - sprite.get_width()) / 2, top - 1)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def render_legend(cr, view: WorldView, width: float, height: float) -> None:
    """Draw the legend for `view` into a `width` x `height` area."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    cr.select_font_face("Sans")
    cr.set_font_size(FONT_SIZE)
    sheet = load_sheet()
    entries = legend_entries(view)
    text_x = PAD + THUMB_W + 8
    for index, entry in enumerate(entries):
        top = _row_top(entries, index)
        h = row_height(entry)
        if entry.kind == "terrain":
            _thumbnail(cr, sheet, entry.terrain, top)
        elif entry.kind in STRUCTURE_KINDS:
            _sprite(cr, "tank" if entry.kind == "army" else entry.kind, top)
        elif entry.kind != "heading":
            _symbol(cr, entry, *_swatch_origin(entries, index))
        cr.set_source_rgb(*(HEADING_RGB if entry.kind == "heading" else TEXT_RGB))
        cr.move_to(PAD if entry.kind == "heading" else text_x, top + h / 2 + FONT_SIZE * 0.35)
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
