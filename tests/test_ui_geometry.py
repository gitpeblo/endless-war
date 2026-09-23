import pytest

from endless_war.simulation.worldgen import FACTION_COLORS
from endless_war.ui.colors import darken, faction_rgb, lighten
from endless_war.ui.geometry import Cell, cell_for, grid_shape, province_at


def test_every_colour_key_the_simulation_emits_has_a_mapping() -> None:
    for key in FACTION_COLORS:
        rgb = faction_rgb(key)
        assert rgb != faction_rgb("__nonexistent__"), f"{key} falls through to the fallback"


def test_an_unknown_colour_key_falls_back_instead_of_raising() -> None:
    assert faction_rgb("chartreuse") == faction_rgb("grey")


def test_components_stay_in_range() -> None:
    for key in ("red", "blue", "green", "amber", "violet", "grey"):
        for component in faction_rgb(key):
            assert 0.0 <= component <= 1.0
    for component in darken(faction_rgb("red")) + lighten(faction_rgb("red")):
        assert 0.0 <= component <= 1.0


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


def test_cells_tile_the_widget_without_overlapping() -> None:
    width, height = 600.0, 400.0
    cells = [cell_for(pid, 96, 12, width, height) for pid in range(96)]
    assert all(0.0 <= c.x and 0.0 <= c.y for c in cells)
    assert all(c.x + c.width <= width + 1e-9 for c in cells)
    assert all(c.y + c.height <= height + 1e-9 for c in cells)
    first_row = [c for c in cells[:12]]
    assert all(abs(c.y - first_row[0].y) < 1e-9 for c in first_row), "row 0 shares a y"
    assert first_row[1].x > first_row[0].x, "columns advance left to right"
    assert cells[12].y > cells[0].y, "rows advance top to bottom"


def test_a_province_id_round_trips_through_its_own_centre() -> None:
    for width, height in ((600.0, 400.0), (313.0, 197.0), (1920.0, 1080.0)):
        for pid in range(96):
            cell = cell_for(pid, 96, 12, width, height)
            hit = province_at(
                cell.x + cell.width / 2, cell.y + cell.height / 2, 96, 12, width, height
            )
            assert hit == pid, f"{pid} at {width}x{height} resolved to {hit}"


def test_a_point_outside_the_widget_hits_nothing() -> None:
    assert province_at(-1.0, 10.0, 96, 12, 600.0, 400.0) is None
    assert province_at(10.0, -1.0, 96, 12, 600.0, 400.0) is None
    assert province_at(601.0, 10.0, 96, 12, 600.0, 400.0) is None
    assert province_at(10.0, 401.0, 96, 12, 600.0, 400.0) is None


def test_round_trip_at_small_and_irregular_widget_sizes() -> None:
    """Padding must scale adaptively so round-trip holds even at degenerate sizes."""
    # Test sizes where fixed padding would break the invariant
    for province_count, cols in [(96, 12), (72, 8)]:
        for width, height in (
            (10.0, 8.0),      # Very small
            (24.0, 16.0),     # Small
            (1.0, 1.0),       # Degenerate
            (313.0, 197.0),   # Uneven division (from existing test)
        ):
            for pid in range(province_count):
                cell = cell_for(pid, province_count, cols, width, height)
                hit = province_at(
                    cell.x + cell.width / 2, cell.y + cell.height / 2,
                    province_count, cols, width, height
                )
                assert hit == pid, (
                    f"pid {pid} at {width}x{height} ({province_count} provinces, {cols} cols): "
                    f"cell {cell}, centre ({cell.x + cell.width / 2}, "
                    f"{cell.y + cell.height / 2}) resolved to {hit}"
                )


def test_tiling_holds_at_small_sizes() -> None:
    """Cells must stay inside widget and not overlap, even when padded at small sizes."""
    for width, height in ((10.0, 8.0), (24.0, 16.0), (1.0, 1.0)):
        cells = [cell_for(pid, 96, 12, width, height) for pid in range(96)]
        # All cells inside widget
        assert all(0.0 <= c.x and 0.0 <= c.y for c in cells), f"Cell outside at {width}x{height}"
        assert all(c.x + c.width <= width + 1e-9 for c in cells), f"Cell exceeds width at {width}x{height}"
        assert all(c.y + c.height <= height + 1e-9 for c in cells), f"Cell exceeds height at {width}x{height}"
        # Cells don't have negative extent
        assert all(c.width >= 0.0 and c.height >= 0.0 for c in cells), f"Negative extent at {width}x{height}"
