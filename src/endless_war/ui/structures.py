"""Structure sprites: capital, industry and town, drawn on a province's tile.

Isometric 32 x 32 pixel art made for this game (`assets/structures/` holds
the generator); each sprite's footprint centre is at (16, 22), which is
placed on the tile's top-face centre.
"""

from __future__ import annotations

from pathlib import Path

import cairo

from endless_war.app.view_model import ProvinceCell

STRUCTURES_DIR = Path(__file__).parent / "assets" / "structures"
NAMES = ("capital", "industry", "town")
SPRITE_SIZE = 32
ANCHOR = (16, 22)  # footprint centre within the sprite

_sprites: dict[str, cairo.ImageSurface] = {}


def load_structure(name: str) -> cairo.ImageSurface:
    if name not in _sprites:
        path = STRUCTURES_DIR / f"{name}.png"
        if not path.exists():
            raise FileNotFoundError(f"structure sprite missing: {path}")
        _sprites[name] = cairo.ImageSurface.create_from_png(str(path))
    return _sprites[name]


def structure_for(province: ProvinceCell) -> str | None:
    """The one structure a province shows: capital, then industry, then town."""
    if province.is_capital:
        return "capital"
    if province.is_industrial:
        return "industry"
    if province.terrain == "urban":
        return "town"
    return None
