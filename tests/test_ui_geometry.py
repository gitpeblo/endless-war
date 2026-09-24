import pytest

from endless_war.simulation.worldgen import FACTION_COLORS
from endless_war.ui.colors import darken, faction_rgb, lighten
from endless_war.ui.geometry import grid_shape


def test_every_colour_key_the_simulation_emits_has_a_mapping() -> None:
    for key in FACTION_COLORS:
        rgb = faction_rgb(key)
        assert rgb != faction_rgb("__nonexistent__"), f"{key} falls through to the fallback"


def test_an_unknown_colour_key_falls_back_instead_of_raising() -> None:
    assert faction_rgb("chartreuse") == faction_rgb("grey")


def test_components_stay_in_range() -> None:
    for key in ("blue", "orange", "teal", "gold", "pink", "grey"):
        for component in faction_rgb(key):
            assert 0.0 <= component <= 1.0
    for component in darken(faction_rgb("orange")) + lighten(faction_rgb("orange")):
        assert 0.0 <= component <= 1.0


def test_faction_colours_are_the_validated_palette() -> None:
    # Checked with the dataviz palette validator against the map background
    # (#1c1f24); see docs/decisions.md, 2026-09-24. Change these only by
    # re-running the validator.
    expected = {
        "blue": "#3987e5",
        "orange": "#d95926",
        "teal": "#199e70",
        "gold": "#c98500",
        "pink": "#d55181",
    }
    for key, code in expected.items():
        want = tuple(int(code[i : i + 2], 16) / 255 for i in (1, 3, 5))
        assert faction_rgb(key) == pytest.approx(want), key
    assert FACTION_COLORS == list(expected)


def test_darken_is_darker_and_lighten_is_lighter() -> None:
    base = faction_rgb("blue")
    assert sum(darken(base)) < sum(base) < sum(lighten(base))


def test_grid_shape_is_cols_by_rows() -> None:
    assert grid_shape(96, 12) == (12, 8)


def test_a_ragged_grid_is_rejected() -> None:
    with pytest.raises(ValueError):
        grid_shape(97, 12)
    with pytest.raises(ValueError):
        grid_shape(96, 0)
