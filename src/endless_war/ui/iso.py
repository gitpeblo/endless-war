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


@dataclass(frozen=True, slots=True)
class Board:
    cols: int
    rows: int
    scale: int
    origin_x: float  # screen x of cell (0, 0)'s top-left corner
    origin_y: float


def _extent(cols: int, rows: int) -> tuple[int, int, int, int]:
    """Unscaled (width, height, left, top) of the board and its ring, relative to cell (0, 0)."""
    c0, r0 = -BORDER, -BORDER
    c1, r1 = cols - 1 + BORDER, rows - 1 + BORDER
    left = (c0 - r1) * STEP_X
    right = (c1 - r0) * STEP_X + TILE_W
    top = (c0 + r0) * STEP_Y
    bottom = (c1 + r1) * STEP_Y + TILE_H + WATER_DROP
    return right - left, bottom - top, left, top


def board_for(province_count: int, cols: int, width: float, height: float) -> Board:
    """The largest integer scale that fits, centred in `width` x `height`."""
    columns, rows = grid_shape(province_count, cols)
    w, h, left, top = _extent(columns, rows)
    scale = max(1, int(min(width / w, height / h)))
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
KEEP_VISIBLE = 48  # px of the board that must stay on screen while panning


@dataclass(frozen=True, slots=True)
class Camera:
    """A zoom level (integer, so pixel art stays sharp) and a pan offset in px.

    No camera means "fit": the largest integer scale that fits, centred.
    """

    scale: int
    pan_x: float = 0.0
    pan_y: float = 0.0


def _centred(width: float, height: float, w: int, h: int, left: int, top: int, scale: int) -> tuple[float, float]:
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


def _clamp(province_count: int, cols: int, width: float, height: float, camera: Camera) -> Camera:
    """Keep at least KEEP_VISIBLE px of the board inside the widget on each axis."""
    columns, rows = grid_shape(province_count, cols)
    w, h, _left, _top = _extent(columns, rows)
    s = camera.scale
    # With no pan the board's bounding box starts at (width - w*s) / 2.
    box_x, box_y = (width - w * s) / 2, (height - h * s) / 2
    pan_x = min(max(camera.pan_x, KEEP_VISIBLE - w * s - box_x), width - KEEP_VISIBLE - box_x)
    pan_y = min(max(camera.pan_y, KEEP_VISIBLE - h * s - box_y), height - KEEP_VISIBLE - box_y)
    return Camera(s, pan_x, pan_y)


def zoom_at(
    province_count: int, cols: int, width: float, height: float,
    camera: Camera | None, x: float, y: float, steps: int,
) -> Camera | None:
    """Zoom by `steps` whole scale steps, keeping the point (x, y) where it is.

    Zooming back down to the fitted scale returns None: the map recentres and
    the pan is forgotten, so the whole board is always one scroll away.
    """
    fit = board_for(province_count, cols, width, height).scale
    current = camera.scale if camera is not None else fit
    new = min(MAX_SCALE, max(1, current + steps))
    if new <= fit:
        return None
    if new == current:
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
