"""Faction colours.

The simulation hands out an abstract `color_key`; what it looks like is the
UI's business alone.
"""

from __future__ import annotations

RGB = tuple[float, float, float]

FACTION_RGB: dict[str, RGB] = {
    "red": (0.78, 0.24, 0.24),
    "blue": (0.24, 0.45, 0.78),
    "green": (0.27, 0.62, 0.36),
    "amber": (0.85, 0.62, 0.20),
    "violet": (0.55, 0.36, 0.72),
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
