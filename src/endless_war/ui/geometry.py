"""The province grid's shape.

Provinces are generated as `pid = row * cols + col`; the isometric board built
on it is `ui/iso.py`. Pure: no GTK, no cairo.
"""

from __future__ import annotations


def grid_shape(province_count: int, cols: int) -> tuple[int, int]:
    """(cols, rows) for a rectangular map."""
    if cols <= 0:
        raise ValueError(f"cols must be positive, got {cols}")
    if province_count % cols:
        raise ValueError(f"{province_count} provinces do not divide into {cols} columns")
    return cols, province_count // cols
