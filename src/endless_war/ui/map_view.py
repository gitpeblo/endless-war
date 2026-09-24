"""The strategic map: an isometric board of darkened pixel-art terrain.

`render_map` draws onto any cairo context, so it can be tested against an
image surface with no display. `MapView` is the GTK widget wrapped around it.
Each province is its terrain tile, washed in its controller's colour; the
markers sit on the tile's top face.
"""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from endless_war.app.view_model import ProvinceCell, WorldView  # noqa: E402
from endless_war.ui import iso  # noqa: E402
from endless_war.ui.colors import faction_rgb, lighten  # noqa: E402
from endless_war.ui.terrain import WATER, load_sheet, tile_for  # noqa: E402

BACKGROUND = (0.11, 0.12, 0.14)
HATCH_RGBA = (0.05, 0.05, 0.05, 0.55)
CAPITAL_RGB = (1.0, 1.0, 1.0)
ARMY_RGB = (0.08, 0.08, 0.08)
TOWN_RGB = (0.10, 0.10, 0.11)
WASH_ALPHA = 0.45
SUPPLY_ALPHA = 0.35


def _blit(cr, sheet, cell: tuple[int, int], x: float, y: float, s: float) -> None:
    row, col = cell
    cr.save()
    cr.translate(x, y)
    cr.scale(s, s)
    cr.rectangle(0, 0, iso.TILE_W, iso.TILE_H)
    cr.clip()
    cr.set_source_surface(sheet, -col * iso.TILE_W, -row * iso.TILE_H)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def _face(cr, x: float, y: float, s: float, inset: float = 0.0) -> None:
    """The top-face diamond of the tile whose cell's top-left is (x, y)."""
    cx, top = x + iso.FACE_W / 2 * s, y + iso.FACE_TOP * s
    half_h = iso.FACE_H / 2 * s
    cr.move_to(cx, top + inset)
    cr.line_to(x + iso.FACE_W * s - 2 * inset, top + half_h)
    cr.line_to(cx, top + 2 * half_h - inset)
    cr.line_to(x + 2 * inset, top + half_h)
    cr.close_path()


def _wash(cr, x: float, y: float, s: float, rgb, alpha: float) -> None:
    _face(cr, x, y, s)
    cr.set_source_rgba(*rgb, alpha)
    cr.fill()


def _hatch(cr, x: float, y: float, s: float) -> None:
    cr.save()
    _face(cr, x, y, s)
    cr.clip()
    cr.set_source_rgba(*HATCH_RGBA)
    cr.set_line_width(1.5 * s)
    top, height = y + iso.FACE_TOP * s, iso.FACE_H * s
    offset = -height
    while offset < iso.FACE_W * s:
        cr.move_to(x + offset, top)
        cr.line_to(x + offset + height, top + height)
        offset += 6 * s
    cr.stroke()
    cr.restore()


def _outline(cr, x: float, y: float, s: float, rgb) -> None:
    _face(cr, x, y, s, inset=1.5 * s)
    cr.set_source_rgb(*lighten(rgb))
    cr.set_line_width(2.0 * s)
    cr.stroke()


def _centre(x: float, y: float, s: float) -> tuple[float, float]:
    return x + iso.FACE_W / 2 * s, y + (iso.FACE_TOP + iso.FACE_H / 2) * s


def _capital(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    half_w, half_h = 5.5 * s, 3.5 * s
    cr.set_source_rgb(*CAPITAL_RGB)
    cr.move_to(cx, cy - half_h)
    cr.line_to(cx + half_w, cy)
    cr.line_to(cx, cy + half_h)
    cr.line_to(cx - half_w, cy)
    cr.close_path()
    cr.fill()


def _army(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    cr.set_source_rgb(*ARMY_RGB)
    cr.arc(cx + 9 * s, cy + 4 * s, 3.0 * s, 0, 6.2832)
    cr.fill()


def _town(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    cr.set_source_rgb(*TOWN_RGB)
    for dx, h in ((-5, 4), (-1, 6), (3, 3)):
        cr.rectangle(cx + dx * s, cy + (1 - h) * s, 3 * s, h * s)
    cr.fill()


def _province(cr, sheet, province: ProvinceCell, x: float, y: float, s: float, bound: int | None) -> None:
    _blit(cr, sheet, tile_for(province.terrain, province.id), x, y, s)
    rgb = faction_rgb(province.color_key)
    _wash(cr, x, y, s, rgb, WASH_ALPHA)
    if province.has_supply_problem:
        _wash(cr, x, y, s, (0.0, 0.0, 0.0), SUPPLY_ALPHA)
    if province.is_contested:
        _hatch(cr, x, y, s)
    if bound is not None and province.controller_faction_id == bound:
        _outline(cr, x, y, s, rgb)
    if province.terrain == "urban":
        _town(cr, x, y, s)
    if province.is_capital:
        _capital(cr, x, y, s)
    if province.has_armies:
        _army(cr, x, y, s)


def render_map(
    cr, view: WorldView, width: float, height: float, cols: int,
    camera: iso.Camera | None = None,
) -> None:
    """Draw every province of `view` as an isometric board in `width` x `height`.

    `camera` is the widget's zoom and pan; without one the board fits and centres.
    """
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    count = len(view.provinces)
    if count == 0 or width <= 0 or height <= 0:
        return

    board = iso.board_with(count, cols, width, height, camera)
    sheet = load_sheet()
    by_cell = {(p.id % cols, p.id // cols): p for p in view.provinces}
    s = board.scale
    for col, row in iso.draw_order(board.cols, board.rows):
        x, y = iso.tile_origin(board, col, row)
        province = by_cell.get((col, row))
        if province is None:
            _blit(cr, sheet, WATER, x, y + iso.WATER_DROP * s, s)
        else:
            _province(cr, sheet, province, x, y, s, view.bound_faction_id)


class MapView(Gtk.DrawingArea):
    """Paints the newest `WorldView`; the scroll wheel zooms, a middle drag pans.

    Zoom and pan are this widget's own state: they change what is shown, never
    the world.
    """

    def __init__(self, cols: int) -> None:
        super().__init__()
        self._cols = cols
        self._view: WorldView | None = None
        self.camera: iso.Camera | None = None
        self._drag_from: tuple[float, float] | None = None
        self.set_size_request(480, 320)
        self.add_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.BUTTON2_MOTION_MASK
        )
        self.connect("draw", self._on_draw)
        self.connect("scroll-event", self._on_scroll)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event", self._on_motion)

    def set_view(self, view: WorldView) -> None:
        self._view = view
        self.queue_draw()

    def _province_count(self) -> int:
        return len(self._view.provinces) if self._view is not None else 0

    def _on_scroll(self, _widget, event) -> bool:
        if event.direction == Gdk.ScrollDirection.UP:
            steps = 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            steps = -1
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            _ok, _dx, dy = event.get_scroll_deltas()
            steps = 1 if dy < 0 else -1 if dy > 0 else 0
        else:
            steps = 0
        count = self._province_count()
        if steps and count:
            a = self.get_allocation()
            self.camera = iso.zoom_at(
                count, self._cols, a.width, a.height, self.camera, event.x, event.y, steps
            )
            self.queue_draw()
        return True

    def _on_press(self, _widget, event) -> bool:
        if event.button == 2:
            self._drag_from = (event.x, event.y)
            return True
        return False

    def _on_release(self, _widget, event) -> bool:
        if event.button == 2:
            self._drag_from = None
            return True
        return False

    def _on_motion(self, _widget, event) -> bool:
        count = self._province_count()
        if self._drag_from is None or not count:
            return False
        a = self.get_allocation()
        x0, y0 = self._drag_from
        self.camera = iso.pan_by(
            count, self._cols, a.width, a.height, self.camera, event.x - x0, event.y - y0
        )
        self._drag_from = (event.x, event.y)
        self.queue_draw()
        return True

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        if self._view is None:
            cr.set_source_rgb(*BACKGROUND)
            cr.rectangle(0, 0, allocation.width, allocation.height)
            cr.fill()
            return False
        render_map(
            cr, self._view, allocation.width, allocation.height, self._cols, self.camera
        )
        return False
