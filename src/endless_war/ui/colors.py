"""Faction colours.

The simulation hands out an abstract `color_key`; what it looks like is the
UI's business alone.
"""

from __future__ import annotations

RGB = tuple[float, float, float]

def _hex(code: str) -> RGB:
    return tuple(int(code[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


# Validated with the dataviz palette checker against the map background
# (#1c1f24): lightness band, chroma floor, adjacent-pair colour-blind
# separation, normal-vision floor and contrast all pass. No five colours can
# pass all-pairs; the legend, the bound-faction outline and the chart's direct
# labels are the secondary encoding. See docs/decisions.md, 2026-09-24.
FACTION_RGB: dict[str, RGB] = {
    "blue": _hex("#3987e5"),
    "orange": _hex("#d95926"),
    "teal": _hex("#199e70"),
    "gold": _hex("#c98500"),
    "pink": _hex("#d55181"),
    "grey": (0.45, 0.45, 0.45),
}
FALLBACK_KEY = "grey"


def faction_rgb(color_key: str) -> RGB:
    """The fill colour for a faction, or grey for anything unrecognised."""
    return FACTION_RGB.get(color_key, FACTION_RGB[FALLBACK_KEY])


def darken(rgb: RGB, factor: float = 0.55) -> RGB:
    """Toward black. Used for provinces with a supply problem."""
    return (rgb[0] * factor, rgb[1] * factor, rgb[2] * factor)


def lighten(rgb: RGB, factor: float = 0.45) -> RGB:
    """Toward white. Used for the bound faction's outline."""
    return tuple(c + (1.0 - c) * factor for c in rgb)  # type: ignore[return-value]
