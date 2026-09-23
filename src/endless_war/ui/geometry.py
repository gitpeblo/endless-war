"""Where a province sits on screen.

Provinces are generated as `pid = row * cols + col`, so the map is a plain
grid and the arithmetic here is its inverse. Pure: no GTK, no cairo.
"""

from __future__ import annotations

from dataclasses import dataclass

CELL_PADDING = 1.0


@dataclass(frozen=True, slots=True)
class Cell:
    x: float
    y: float
    width: float
    height: float


def grid_shape(province_count: int, cols: int) -> tuple[int, int]:
    """(cols, rows) for a rectangular map."""
    if cols <= 0:
        raise ValueError(f"cols must be positive, got {cols}")
    if province_count % cols:
        raise ValueError(f"{province_count} provinces do not divide into {cols} columns")
    return cols, province_count // cols


def cell_for(
    province_id: int,
    province_count: int,
    cols: int,
    width: float,
    height: float,
    padding: float = CELL_PADDING,
) -> Cell:
    """The rectangle `province_id` occupies in a widget of `width` x `height`."""
    columns, rows = grid_shape(province_count, cols)
    row, col = divmod(province_id, columns)
    cell_w = width / columns
    cell_h = height / rows
    # Scale padding down if the cell cannot carry it, keeping the cell centred so
    # that its centre point still resolves back to this province_id via province_at.
    effective_padding = min(padding, cell_w / 4, cell_h / 4)
    return Cell(
        x=col * cell_w + effective_padding,
        y=row * cell_h + effective_padding,
        width=max(0.0, cell_w - 2 * effective_padding),
        height=max(0.0, cell_h - 2 * effective_padding),
    )


def province_at(
    x: float, y: float, province_count: int, cols: int, width: float, height: float
) -> int | None:
    """The province under a point, or None if the point is off the map."""
    if not (0.0 <= x < width and 0.0 <= y < height):
        return None
    columns, rows = grid_shape(province_count, cols)
    col = min(columns - 1, int(x / (width / columns)))
    row = min(rows - 1, int(y / (height / rows)))
    return row * columns + col
