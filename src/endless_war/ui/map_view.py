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
from endless_war.ui.structures import (  # noqa: E402
    ANCHOR,
    TANK_ANCHOR,
    load_structure,
    structure_for,
    tank_for,
)
from endless_war.ui.terrain import WATER, load_sheet, tile_for  # noqa: E402

BACKGROUND = (0.11, 0.12, 0.14)
HATCH_RGBA = (0.05, 0.05, 0.05, 0.55)
WASH_ALPHA = 0.10  # a hint only (was 0.45, 0.35, 0.25): the faction contour carries ownership
SUPPLY_ALPHA = 0.35


def _blit(cr, sheet, cell: tuple[int, int], x: float, y: float, s: float) -> None:
    row, col = cell
    cr.save()
    # At a fractional fitted scale, whole-pixel tile corners and an aliased
    # clip keep neighbouring tiles from leaving hairline seams between them.
    cr.translate(round(x), round(y))
    cr.scale(s, s)
    cr.set_antialias(cairo.ANTIALIAS_NONE)
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


def _structure(cr, name: str, x: float, y: float, s: float) -> None:
    """Stand the structure sprite on the tile's top-face centre."""
    cx, cy = _centre(x, y, s)
    cr.save()
    cr.translate(round(cx - ANCHOR[0] * s), round(cy - ANCHOR[1] * s))
    cr.scale(s, s)
    cr.set_source_surface(load_structure(name), 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def _army(cr, x: float, y: float, s: float, color_keys: tuple[str, ...] = ("grey",)) -> None:
    """A tank per faction present, in its colour, centred on the tile's top face.

    Two factions (a battle) stand side by side; more than two show the first two.
    """
    keys = color_keys[:2] or ("grey",)
    offsets = (0.0,) if len(keys) == 1 else (-7.0, 7.0)
    for key, dx in zip(keys, offsets):
        _tank(cr, key, x + dx * s, y, s)


def _tank(cr, color_key: str, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    cr.save()
    cr.translate(round(cx - TANK_ANCHOR[0] * s), round(cy - TANK_ANCHOR[1] * s))
    cr.scale(s, s)
    cr.set_source_surface(tank_for(color_key), 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def _province(cr, sheet, province: ProvinceCell, x: float, y: float, s: float, bound: int | None) -> None:
    _blit(cr, sheet, tile_for(province.terrain, province.id), x, y, s)
    rgb = faction_rgb(province.color_key)
    _wash(cr, x, y, s, rgb, WASH_ALPHA)
    if province.has_supply_problem:
        _wash(cr, x, y, s, (0.0, 0.0, 0.0), SUPPLY_ALPHA)
    if province.is_contested:
        _hatch(cr, x, y, s)
    structure = structure_for(province)
    if structure is not None:
        _structure(cr, structure, x, y, s)


# Each neighbour, and the edge of this cell's top face it shares: T, R, B, L
# are the diamond's top, right, bottom and left vertices.
_EDGES = (((0, -1), "T", "R"), ((1, 0), "R", "B"), ((0, 1), "B", "L"), ((-1, 0), "L", "T"))


def _vertices(x: float, y: float, s: float, inset: float) -> dict[str, tuple[float, float]]:
    cx, top = x + iso.FACE_W / 2 * s, y + iso.FACE_TOP * s
    half_h = iso.FACE_H / 2 * s
    return {
        "T": (cx, top + inset),
        "R": (x + iso.FACE_W * s - 2 * inset, top + half_h),
        "B": (cx, top + 2 * half_h - inset),
        "L": (x + 2 * inset, top + half_h),
    }


def _contours(cr, board, by_cell, bound: int | None) -> None:
    """A thin line in each faction's colour along its land's outer edge.

    Drawn just inside each province's top face wherever the neighbour has a
    different controller (or is sea), so two factions' lines run side by side
    along a front. The bound faction's line is thicker and lighter.
    """
    s = board.scale
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for (col, row), province in sorted(by_cell.items(), key=lambda kv: (kv[0][0] + kv[0][1], kv[0][0])):
        mine = province.controller_faction_id
        yours = bound is not None and mine == bound
        x, y = iso.tile_origin(board, col, row)
        points = _vertices(x, y, s, inset=1.2 * s)
        rgb = faction_rgb(province.color_key)
        cr.set_source_rgb(*(lighten(rgb) if yours else rgb))
        cr.set_line_width((2.2 if yours else 1.2) * s)
        for (dc, dr), a, b in _EDGES:
            other = by_cell.get((col + dc, row + dr))
            if other is not None and other.controller_faction_id == mine:
                continue
            cr.move_to(*points[a])
            cr.line_to(*points[b])
        cr.stroke()
    cr.restore()


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
    _contours(cr, board, by_cell, view.bound_faction_id)
    # Armies go on top of the finished board, back to front, so no nearer
    # tile or tall terrain can cut a tank off.
    for col, row in iso.draw_order(board.cols, board.rows):
        province = by_cell.get((col, row))
        if province is not None and province.has_armies:
            _army(cr, *iso.tile_origin(board, col, row), s, province.army_color_keys)


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
        self._scroll_acc = 0.0  # smooth-scroll deltas not yet worth a step
        # The widget size the camera was made for; a draw at any other size
        # re-fits or re-clamps it.
        self._size: tuple[int, int] | None = None
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
            # Touchpads and high-resolution wheels send many small deltas;
            # a step is one whole unit of accumulated scroll, not one event.
            _ok, _dx, dy = event.get_scroll_deltas()
            if dy == 0:
                self._scroll_acc = 0.0  # end of a touchpad gesture
            self._scroll_acc += dy
            steps = 0
            while self._scroll_acc <= -1 + 1e-9:
                steps += 1
                self._scroll_acc += 1
            while self._scroll_acc >= 1 - 1e-9:
                steps -= 1
                self._scroll_acc -= 1
        else:
            steps = 0
        count = self._province_count()
        if steps and count:
            a = self.get_allocation()
            self.camera = iso.zoom_at(
                count, self._cols, a.width, a.height, self.camera, event.x, event.y, steps
            )
            self._size = (a.width, a.height)
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
        self._size = (a.width, a.height)
        self._drag_from = (event.x, event.y)
        self.queue_draw()
        return True

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        size = (allocation.width, allocation.height)
        if self.camera is not None and size != self._size and self._province_count():
            # A camera from the old size may now be below the fit or off-screen.
            self.camera = iso.refit(
                self._province_count(), self._cols, size[0], size[1], self.camera
            )
            self._size = size
        if self._view is None:
            cr.set_source_rgb(*BACKGROUND)
            cr.rectangle(0, 0, allocation.width, allocation.height)
            cr.fill()
            return False
        render_map(
            cr, self._view, allocation.width, allocation.height, self._cols, self.camera
        )
        return False
