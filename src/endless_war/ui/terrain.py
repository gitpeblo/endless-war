"""Terrain tiles from the CC0 isometric sheet (see assets/README.md).

The sheet is darkened and desaturated once, on first use: the map is meant to
read grim, with the faction colour carrying the only saturated colour on it.
"""

from __future__ import annotations

from pathlib import Path

import cairo

SHEET_PATH = Path(__file__).parent / "assets" / "terrain.png"
DESATURATE = 0.40  # keep 40 % of each pixel's saturation
DARKEN = 0.60  # then scale its brightness to 60 %

# (sheet row, sheet col). Several variants give a varied map; a province's
# variant is fixed by its id, so it never flickers between frames.
TILES: dict[str, tuple[tuple[int, int], ...]] = {
    "plains": ((0, 6), (6, 7), (1, 6), (2, 6), (3, 6)),
    "forest": ((0, 0), (1, 0), (2, 0), (3, 0)),
    "hills": ((5, 8),),
    "mountain": ((6, 6),),
    "urban": ((6, 8),),
}
WATER = (4, 7)
FALLBACK = "plains"

_sheet: cairo.ImageSurface | None = None


def tile_for(terrain: str, province_id: int) -> tuple[int, int]:
    """The sheet cell for `terrain`, stable per province; plains if unknown."""
    variants = TILES.get(terrain, TILES[FALLBACK])
    return variants[province_id % len(variants)]


def grim(surface: cairo.ImageSurface) -> cairo.ImageSurface:
    """A darkened, desaturated copy of `surface`; the input is not touched.

    Works on premultiplied ARGB: moving each channel toward the luminance and
    scaling it down can never exceed alpha, so the result stays valid.
    """
    width, height = surface.get_width(), surface.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(surface, 0, 0)
    cr.paint()
    out.flush()
    data = out.get_data()
    for i in range(0, len(data), 4):
        alpha = data[i + 3]
        if alpha == 0:
            continue
        b, g, r = data[i], data[i + 1], data[i + 2]
        lum = 0.30 * r + 0.59 * g + 0.11 * b
        data[i] = min(alpha, int((lum + (b - lum) * DESATURATE) * DARKEN))
        data[i + 1] = min(alpha, int((lum + (g - lum) * DESATURATE) * DARKEN))
        data[i + 2] = min(alpha, int((lum + (r - lum) * DESATURATE) * DARKEN))
    out.mark_dirty()
    return out


def load_sheet() -> cairo.ImageSurface:
    """The darkened sheet, loaded and processed once."""
    global _sheet
    if _sheet is None:
        if not SHEET_PATH.exists():
            raise FileNotFoundError(f"terrain sheet missing: {SHEET_PATH}")
        _sheet = grim(cairo.ImageSurface.create_from_png(str(SHEET_PATH)))
    return _sheet
