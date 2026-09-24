import cairo
import pytest

from endless_war.config import load_config
from endless_war.ui import terrain
from endless_war.ui.terrain import FALLBACK, TILES, WATER, grim, load_sheet, tile_for


def _lum(r: float, g: float, b: float) -> float:
    return 0.30 * r + 0.59 * g + 0.11 * b


def test_the_sheet_ships_with_the_package() -> None:
    assert terrain.SHEET_PATH.exists(), terrain.SHEET_PATH
    sheet = cairo.ImageSurface.create_from_png(str(terrain.SHEET_PATH))
    assert (sheet.get_width(), sheet.get_height()) == (432, 384)


def test_every_simulation_terrain_has_a_tile() -> None:
    for name in load_config()["balance"]["terrain_defence"]:
        assert name in TILES, name


def test_every_tile_is_inside_the_sheet() -> None:
    for variants in list(TILES.values()) + [(WATER,)]:
        for row, col in variants:
            assert 0 <= row < 8 and 0 <= col < 9, (row, col)


def test_a_province_always_gets_the_same_variant() -> None:
    assert tile_for("forest", 17) == tile_for("forest", 17)
    assert {tile_for("forest", pid) for pid in range(8)} == set(TILES["forest"])


def test_an_unknown_terrain_falls_back_to_plains() -> None:
    assert tile_for("swamp", 3) == tile_for(FALLBACK, 3)


def _sample(surface, x, y):
    surface.flush()
    d, s = surface.get_data(), surface.get_stride()
    o = y * s + x * 4
    return d[o + 2], d[o + 1], d[o], d[o + 3]  # r, g, b, a


def test_grim_darkens_desaturates_and_leaves_the_input_alone() -> None:
    src = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 1)
    cr = cairo.Context(src)
    for x, rgb in enumerate(((0.9, 0.2, 0.1), (0.1, 0.8, 0.3), (0.2, 0.3, 0.9), (0.5, 0.5, 0.5))):
        cr.set_source_rgb(*rgb)
        cr.rectangle(x, 0, 1, 1)
        cr.fill()
    before = [_sample(src, x, 0) for x in range(4)]
    out = grim(src)
    assert [_sample(src, x, 0) for x in range(4)] == before, "input mutated"
    for x in range(4):
        r0, g0, b0, a0 = before[x]
        r1, g1, b1, a1 = _sample(out, x, 0)
        assert a1 == a0
        assert _lum(r1, g1, b1) <= _lum(r0, g0, b0)
        assert max(r1, g1, b1) - min(r1, g1, b1) <= max(r0, g0, b0) - min(r0, g0, b0)


def test_grim_keeps_transparent_pixels_transparent() -> None:
    src = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 2)
    out = grim(src)
    assert all(v == 0 for v in bytes(out.get_data()))


def test_load_sheet_is_cached() -> None:
    assert load_sheet() is load_sheet()
