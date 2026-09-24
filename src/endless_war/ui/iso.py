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
