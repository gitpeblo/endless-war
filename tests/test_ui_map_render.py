import dataclasses

import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world
from endless_war.ui import map_view
from endless_war.ui.colors import faction_rgb
from endless_war.ui.iso import board_for, face_centre, tile_origin
from endless_war.ui.map_view import BACKGROUND, render_map

WIDTH, HEIGHT, COLS = 600, 400, 12


def _view(ticks: int = 0, bound=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    SimulationEngine(world, cfg).run(ticks)
    return build_view(world, cfg, bound_faction_id=bound, speed="1x")


def _render(view, width=WIDTH, height=HEIGHT):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    render_map(cairo.Context(surface), view, width, height, COLS)
    surface.flush()
    return surface


def _pixel(surface, x: float, y: float) -> tuple[int, int, int]:
    data, stride = surface.get_data(), surface.get_stride()
    o = int(y) * stride + int(x) * 4
    return data[o + 2], data[o + 1], data[o]


def _probe(pid: int, width=WIDTH, height=HEIGHT) -> tuple[float, float]:
    # Left part of the top face: clear of the capital, army and town markers.
    board = board_for(96, COLS, width, height)
    x, y = face_centre(board, pid % COLS, pid // COLS)
    return x - 10 * board.scale, y


def _with(view, pid: int, **changes):
    cells = tuple(
        dataclasses.replace(c, **changes) if c.id == pid else c for c in view.provinces
    )
    return dataclasses.replace(view, provinces=cells)


def _plain(view, pid: int):
    # A bare tile: no markers and no structure sprite over the probe points.
    return _with(
        view, pid, is_contested=False, has_supply_problem=False, has_armies=False,
        is_capital=False, is_industrial=False, terrain="plains",
    )


def test_the_wash_is_the_provinces_faction_colour(monkeypatch) -> None:
    # Alpha blending is exact: washed = base + alpha * (colour - base). Render
    # once without the wash to get base, then solve for the colour.
    view = _view()
    pid = next(c.id for c in view.provinces if not c.is_capital)
    view = _plain(view, pid)
    washed = _pixel(_render(view), *_probe(pid))
    alpha = map_view.WASH_ALPHA
    monkeypatch.setattr(map_view, "WASH_ALPHA", 0.0)
    base = _pixel(_render(view), *_probe(pid))
    cell = next(c for c in view.provinces if c.id == pid)
    want = [round(v * 255) for v in faction_rgb(cell.color_key)]
    got = [b + (w - b) / alpha for w, b in zip(washed, base)]
    assert all(abs(g - v) <= 6 for g, v in zip(got, want)), (got, want)


def test_a_contested_province_is_hatched() -> None:
    view = _plain(_view(), 5)
    calm = _render(view)
    fought = _render(_with(view, 5, is_contested=True))
    board = board_for(96, COLS, WIDTH, HEIGHT)
    cx, cy = face_centre(board, 5, 0)
    changed = sum(
        1
        for dx in range(-14, 15)
        for dy in range(-5, 6)
        if sum(_pixel(fought, cx + dx, cy + dy)) < sum(_pixel(calm, cx + dx, cy + dy)) - 10
    )
    assert changed > 15


def test_a_supply_problem_darkens_the_province() -> None:
    view = _plain(_view(), 7)
    fine = sum(_pixel(_render(view), *_probe(7)))
    starved = sum(_pixel(_render(_with(view, 7, has_supply_problem=True)), *_probe(7)))
    assert starved < fine - 10


def test_the_sea_surrounds_the_board() -> None:
    surface = _render(_view())
    board = board_for(96, COLS, WIDTH, HEIGHT)
    x, y = face_centre(board, -1, 3)
    assert _pixel(surface, x, y + 4) != tuple(round(c * 255) for c in BACKGROUND)


def test_a_nearer_tall_tile_covers_the_province_behind_it() -> None:
    # Back-to-front order: the mountain at (1, 1) rises into the top face of
    # the province at (0, 0), so the farther province's wash must not show
    # through the nearer peak.
    view = _view()
    board = board_for(96, COLS, WIDTH, HEIGHT)
    behind, front = 0, 13  # cells (0, 0) and (1, 1)
    base = _with(_plain(_plain(view, behind), front), front, terrain="mountain")
    fx, fy = tile_origin(board, 1, 1)
    x, y = fx + 24 * board.scale, fy + 14 * board.scale  # on the peak (its apex is at y=12), inside (0, 0)'s face
    orange = _pixel(_render(_with(base, behind, color_key="orange")), x, y)
    blue = _pixel(_render(_with(base, behind, color_key="blue")), x, y)
    assert orange == blue, "the farther province's wash showed through the nearer peak"
    flat = _with(_with(base, front, terrain="plains"), behind, color_key="orange")
    assert _pixel(_render(flat), x, y) != orange, "premise: the peak covers this point"


def test_an_empty_view_and_a_tiny_surface_render() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    world.provinces.clear()
    empty = build_view(world, cfg, bound_faction_id=None, speed="paused")
    _render(empty)
    _render(_view(), width=20, height=20)


def test_an_unknown_terrain_renders_as_plains() -> None:
    view = _with(_view(), 3, terrain="swamp")
    _render(view)


def test_rendering_is_stable_for_the_same_view() -> None:
    view = _view(4 * 30)
    first, second = _render(view), _render(view)
    assert bytes(first.get_data()) == bytes(second.get_data())


def test_the_wash_lets_the_terrain_show_through() -> None:
    # The user asked for more transparency than the first 45 %.
    assert map_view.WASH_ALPHA == 0.10


def test_a_capital_is_drawn_with_its_sprite() -> None:
    view = _plain(_view(), 5)
    view = _with(view, 5, terrain="plains", is_industrial=False)
    board = board_for(96, COLS, WIDTH, HEIGHT)
    cx, cy = face_centre(board, 5, 0)
    plain = _render(view)
    capital = _render(_with(view, 5, is_capital=True))
    changed = sum(
        1
        for dx in range(-12, 13)
        for dy in range(-18, 4)
        if _pixel(plain, cx + dx, cy + dy) != _pixel(capital, cx + dx, cy + dy)
    )
    assert changed > 60, "no capital building drawn on the province"


def test_a_tank_is_never_covered_by_a_nearer_tile() -> None:
    # Armies are drawn after the whole board, so a tall tile in front of a
    # province cannot cut its tank off (the user asked for this).
    view = _plain(_plain(_view(), 0), 13)
    with_tank = _with(view, 0, has_armies=True)
    flat_empty = _render(_with(view, 13, terrain="plains"))
    flat = _render(_with(with_tank, 13, terrain="plains"))
    peak = _render(_with(with_tank, 13, terrain="mountain"))
    tank = [
        (x, y) for x in range(WIDTH) for y in range(HEIGHT)
        if _pixel(flat, x, y) != _pixel(flat_empty, x, y)
    ]
    assert len(tank) > 30, "premise: a tank is drawn"
    assert all(_pixel(flat, x, y) == _pixel(peak, x, y) for x, y in tank)


def test_a_contour_runs_where_controllers_differ_and_not_inside() -> None:
    view = _view()
    board = board_for(96, COLS, WIDTH, HEIGHT)
    s = board.scale

    def edge_pixel(surface, a, b):
        # The midpoint of the edge between cells a and b, nudged into a.
        ax, ay = face_centre(board, a % COLS, a // COLS)
        bx, by = face_centre(board, b % COLS, b // COLS)
        mx, my = (ax + bx) / 2, (ay + by) / 2
        return _pixel(surface, mx + (ax - mx) * 0.08, my + (ay - my) * 0.08)

    same = _with(_with(_plain(_plain(view, 5), 6), 5, color_key="blue", controller_faction_id=0), 6, color_key="blue", controller_faction_id=0)
    split = _with(same, 6, color_key="orange", controller_faction_id=1)
    inside = edge_pixel(_render(same), 5, 6)
    border = edge_pixel(_render(split), 5, 6)
    blue = [round(c * 255) for c in faction_rgb("blue")]
    assert sum(abs(p - q) for p, q in zip(border, blue)) < sum(abs(p - q) for p, q in zip(inside, blue)) - 60
