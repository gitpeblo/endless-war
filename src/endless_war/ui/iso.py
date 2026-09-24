"""Isometric board geometry. Pure: no GTK, no cairo.

Province `id` sits at column `id % cols`, row `id // cols`. Cell (c, r)'s
48 x 48 tile has its top-left corner at `origin + ((c - r) * 24, (c + r) * 12)`,
times the integer scale; its top face is the diamond whose top vertex is 16 px
down the cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from endless_war.ui.geometry import grid_shape

TILE_W = TILE_H = 48
STEP_X, STEP_Y = 24, 12
FACE_TOP = 16
FACE_W, FACE_H = 48, 24
BORDER = 1  # ring of water tiles around the board
WATER_DROP = 4  # water sits this far below the land
MIN_SCALE = 0.25


@dataclass(frozen=True, slots=True)
class Board:
    cols: int
    rows: int
    scale: float
    origin_x: float  # screen x of cell (0, 0)'s top-left corner
    origin_y: float


def _extent(cols: int, rows: int) -> tuple[int, int, int, int]:
    """Unscaled (width, height, left, top) of the land, relative to cell (0, 0).

    The sea ring is left out on purpose: fitting and centring on the land lets
    the map open closer (the user found a fit that included the sea too far
    out), and the ring simply runs off the widget's edges.
    """
    c1, r1 = cols - 1, rows - 1
    left = -r1 * STEP_X
    right = c1 * STEP_X + TILE_W
    top = 0
    bottom = (c1 + r1) * STEP_Y + TILE_H
    return right - left, bottom - top, left, top


def board_for(province_count: int, cols: int, width: float, height: float) -> Board:
    """The scale that exactly fills `width` x `height`, centred.

    The user asked for the map to open filling its space rather than at the
    largest whole scale that fits, which left it small. A fractional scale
    with nearest-neighbour sampling keeps hard pixel edges; zoom steps above
    it are whole numbers (see `zoom_at`).
    """
    columns, rows = grid_shape(province_count, cols)
    w, h, left, top = _extent(columns, rows)
    scale = max(MIN_SCALE, min(width / w, height / h))
    origin_x = (width - w * scale) / 2 - left * scale
    origin_y = (height - h * scale) / 2 - top * scale
    return Board(columns, rows, scale, math.floor(origin_x), math.floor(origin_y))


def tile_origin(board: Board, col: int, row: int) -> tuple[float, float]:
    return (
        board.origin_x + (col - row) * STEP_X * board.scale,
        board.origin_y + (col + row) * STEP_Y * board.scale,
    )


def face_centre(board: Board, col: int, row: int) -> tuple[float, float]:
    x, y = tile_origin(board, col, row)
    return x + FACE_W / 2 * board.scale, y + (FACE_TOP + FACE_H / 2) * board.scale


def draw_order(cols: int, rows: int, border: int = BORDER) -> list[tuple[int, int]]:
    """Every cell including the ring, back to front."""
    cells = [
        (c, r)
        for c in range(-border, cols + border)
        for r in range(-border, rows + border)
    ]
    return sorted(cells, key=lambda cell: (cell[0] + cell[1], cell[0]))


def province_at(board: Board, x: float, y: float, province_count: int) -> int | None:
    """The province whose top face contains (x, y), or None."""
    u = (x - board.origin_x) / board.scale - FACE_W / 2
    v = (y - board.origin_y) / board.scale - (FACE_TOP + FACE_H / 2)
    col = math.floor((u / STEP_X + v / STEP_Y) / 2 + 0.5)
    row = math.floor((v / STEP_Y - u / STEP_X) / 2 + 0.5)
    if not (0 <= col < board.cols and 0 <= row < board.rows):
        return None
    pid = row * board.cols + col
    return pid if pid < province_count else None


# -- zoom and pan -------------------------------------------------------------

MAX_SCALE = 8
KEEP_VISIBLE = 48  # px: some of the board stays at least this far inside the widget
_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class Camera:
    """A zoom level and a pan offset in px. No camera means "fit and centre"."""

    scale: float
    pan_x: float = 0.0
    pan_y: float = 0.0


def _centred(width: float, height: float, w: int, h: int, left: int, top: int, scale: float) -> tuple[float, float]:
    return (width - w * scale) / 2 - left * scale, (height - h * scale) / 2 - top * scale


def board_with(
    province_count: int, cols: int, width: float, height: float, camera: Camera | None
) -> Board:
    """The board as `camera` shows it; the fitted board when there is no camera."""
    if camera is None:
        return board_for(province_count, cols, width, height)
    columns, rows = grid_shape(province_count, cols)
    w, h, left, top = _extent(columns, rows)
    cx, cy = _centred(width, height, w, h, left, top, camera.scale)
    return Board(
        columns, rows, camera.scale,
        math.floor(cx + camera.pan_x), math.floor(cy + camera.pan_y),
    )


def _closest_on_segment(a, b, p) -> tuple[float, float]:
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length))
    return ax + t * dx, ay + t * dy


def _closest_in_polygon(corners, p) -> tuple[float, float]:
    """`p` itself if it is inside the convex polygon, else its nearest boundary point."""
    sides = list(zip(corners, corners[1:] + corners[:1]))
    crosses = [
        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) for a, b in sides
    ]
    if all(c >= 0 for c in crosses) or all(c <= 0 for c in crosses):
        return p
    candidates = [_closest_on_segment(a, b, p) for a, b in sides]
    return min(candidates, key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2)


def _clamp(province_count: int, cols: int, width: float, height: float, camera: Camera) -> Camera:
    """Keep part of the board itself, not just its bounding box, on screen.

    The board is a diamond, so its bounding box has empty corners. Take the
    diamond through the four corner provinces' face centres, find its point
    nearest the widget centre, and pan just enough to bring that point at
    least KEEP_VISIBLE px inside the widget.
    """
    board = board_with(province_count, cols, width, height, camera)
    last_c, last_r = board.cols - 1, board.rows - 1
    corners = [
        face_centre(board, c, r) for c, r in ((0, 0), (last_c, 0), (last_c, last_r), (0, last_r))
    ]
    px, py = _closest_in_polygon(corners, (width / 2, height / 2))
    inset_x, inset_y = min(KEEP_VISIBLE, width / 2), min(KEEP_VISIBLE, height / 2)
    tx = min(max(px, inset_x), width - inset_x)
    ty = min(max(py, inset_y), height - inset_y)
    return Camera(camera.scale, camera.pan_x + (tx - px), camera.pan_y + (ty - py))


def refit(
    province_count: int, cols: int, width: float, height: float, camera: Camera | None
) -> Camera | None:
    """`camera` for a widget of a new size: dropped at or below the new fit, else re-clamped."""
    if camera is None:
        return None
    if camera.scale <= board_for(province_count, cols, width, height).scale + _EPS:
        return None
    return _clamp(province_count, cols, width, height, camera)


def zoom_at(
    province_count: int, cols: int, width: float, height: float,
    camera: Camera | None, x: float, y: float, steps: int,
) -> Camera | None:
    """Zoom by `steps` whole scale steps, keeping the point (x, y) where it is.

    Steps land on whole numbers above the fitted scale (a fit of 1.3 zooms to
    2, then 3...). Zooming back to or below the fit returns None: the map
    recentres and the pan is forgotten, so the whole board is one scroll away.
    """
    fit = board_for(province_count, cols, width, height).scale
    current = camera.scale if camera is not None else fit
    new = current
    for _ in range(abs(steps)):
        if steps > 0:
            new = math.floor(new + _EPS) + 1
        else:
            new = math.ceil(new - _EPS) - 1
    new = min(MAX_SCALE, new)
    if new <= fit + _EPS:
        return None
    if camera is not None and abs(new - current) < _EPS:
        return camera
    before = board_with(province_count, cols, width, height, camera)
    ux = (x - before.origin_x) / before.scale
    uy = (y - before.origin_y) / before.scale
    columns, rows = grid_shape(province_count, cols)
    w, h, left, top = _extent(columns, rows)
    cx, cy = _centred(width, height, w, h, left, top, new)
    return _clamp(
        province_count, cols, width, height,
        Camera(new, x - ux * new - cx, y - uy * new - cy),
    )


def pan_by(
    province_count: int, cols: int, width: float, height: float,
    camera: Camera | None, dx: float, dy: float,
) -> Camera:
    """Move the board by (dx, dy) px, clamped so it cannot leave the widget."""
    if camera is None:
        camera = Camera(board_for(province_count, cols, width, height).scale)
    return _clamp(
        province_count, cols, width, height,
        Camera(camera.scale, camera.pan_x + dx, camera.pan_y + dy),
    )
