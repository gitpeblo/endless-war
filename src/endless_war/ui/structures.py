"""Structure sprites: capital, industry and town, drawn on a province's tile.

Isometric 32 x 32 pixel art made for this game (`assets/structures/` holds
the generator); each sprite's footprint centre is at (16, 22), which is
placed on the tile's top-face centre.
"""

from __future__ import annotations

from pathlib import Path

import cairo

from endless_war.app.view_model import ProvinceCell
from endless_war.ui.colors import faction_rgb

STRUCTURES_DIR = Path(__file__).parent / "assets" / "structures"
NAMES = ("capital", "town")
SPRITE_SIZE = 32
ANCHOR = (16, 22)  # footprint centre within the sprite

_sprites: dict[str, cairo.ImageSurface] = {}


UNITS_DIR = Path(__file__).parent / "assets" / "units"
TANK_ANCHOR = (14, 18)  # the tank's footprint centre in its 28 x 28 sprite


def load_structure(name: str) -> cairo.ImageSurface:
    if name not in _sprites:
        folder = UNITS_DIR if name == "tank" else STRUCTURES_DIR
        path = folder / f"{name}.png"
        if not path.exists():
            raise FileNotFoundError(f"structure sprite missing: {path}")
        _sprites[name] = cairo.ImageSurface.create_from_png(str(path))
    return _sprites[name]


TINT_FLOOR = 0x40  # grey pixels above this are the body; darker ones are tracks and outline
_tanks: dict[str, cairo.ImageSurface] = {}


def tank_for(color_key: str) -> cairo.ImageSurface:
    """The tank tinted in a faction's colour: body greys become shades of it."""
    if color_key not in _tanks:
        base = load_structure("tank")
        out = cairo.ImageSurface(cairo.FORMAT_ARGB32, base.get_width(), base.get_height())
        cr = cairo.Context(out)
        cr.set_source_surface(base, 0, 0)
        cr.paint()
        out.flush()
        data = out.get_data()
        tint = faction_rgb(color_key)
        for i in range(0, len(data), 4):
            b, g, r, a = data[i], data[i + 1], data[i + 2], data[i + 3]
            if a == 0 or not (r == g == b) or r <= TINT_FLOOR:
                continue
            level = min(1.0, r / 255 * 1.25)
            data[i] = min(a, int(tint[2] * level * 255))
            data[i + 1] = min(a, int(tint[1] * level * 255))
            data[i + 2] = min(a, int(tint[0] * level * 255))
        out.mark_dirty()
        _tanks[color_key] = out
    return _tanks[color_key]


def structure_for(province: ProvinceCell) -> str | None:
    """The one structure a province shows: capital, then town.

    Industry is not drawn: 35 of 96 provinces are industrial at seed 42, and
    a plant on each crowded the map (the user chose to remove it).
    """
    if province.is_capital:
        return "capital"
    if province.terrain == "urban":
        return "town"
    return None
