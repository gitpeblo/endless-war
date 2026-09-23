import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.colors import faction_rgb
from endless_war.ui.geometry import cell_for
from endless_war.ui.map_view import render_map

WIDTH, HEIGHT, COLS = 600, 400, 12


def _surface():
    return cairo.ImageSurface(cairo.FORMAT_RGB24, WIDTH, HEIGHT)


def _pixel(surface, x: float, y: float) -> tuple[int, int, int]:
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    offset = int(y) * stride + int(x) * 4
    blue, green, red = data[offset], data[offset + 1], data[offset + 2]
    return red, green, blue


def _view(bound=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    return build_view(world, cfg, bound_faction_id=bound, speed="1x"), world


def test_a_province_is_painted_in_its_controllers_colour() -> None:
    view, world = _view()
    surface = _surface()
    render_map(cairo.Context(surface), view, WIDTH, HEIGHT, COLS)

    pid = 0
    controller = world.provinces[pid].controller_faction_id
    assert controller is not None, "premise: province 0 has a controller at seed 42"
    expected = faction_rgb(world.factions[controller].color_key)
    cell = cell_for(pid, len(view.provinces), COLS, WIDTH, HEIGHT)
    got = _pixel(surface, cell.x + cell.width / 2, cell.y + cell.height / 2)
    for channel, want in zip(got, expected):
        assert abs(channel - round(want * 255)) <= 2, f"got {got}, expected ~{expected}"


def test_two_factions_render_as_different_colours() -> None:
    view, world = _view()
    surface = _surface()
    render_map(cairo.Context(surface), view, WIDTH, HEIGHT, COLS)

    by_faction: dict[int, int] = {}
    for cell_view in view.provinces:
        if cell_view.controller_faction_id not in by_faction:
            by_faction[cell_view.controller_faction_id] = cell_view.id
    assert len(by_faction) >= 2, "premise: seed 42 has at least two controllers"

    samples = set()
    for pid in list(by_faction.values())[:2]:
        rect = cell_for(pid, len(view.provinces), COLS, WIDTH, HEIGHT)
        samples.add(_pixel(surface, rect.x + rect.width / 2, rect.y + rect.height / 2))
    assert len(samples) == 2, "two different factions painted the same colour"


def test_a_supply_starved_province_is_darker_than_a_healthy_one() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    healthy, starved = sorted(world.provinces)[0], sorted(world.provinces)[1]
    assert (
        world.provinces[healthy].controller_faction_id
        == world.provinces[starved].controller_faction_id
    ), "premise: both provinces share a controller, so only supply differs"
    world.provinces[starved].supply_value = cfg["balance"]["low_supply_threshold"] - 0.01
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")

    surface = _surface()
    render_map(cairo.Context(surface), view, WIDTH, HEIGHT, COLS)
    a = cell_for(healthy, 96, COLS, WIDTH, HEIGHT)
    b = cell_for(starved, 96, COLS, WIDTH, HEIGHT)
    bright = sum(_pixel(surface, a.x + a.width / 2, a.y + a.height / 2))
    dim = sum(_pixel(surface, b.x + b.width / 2, b.y + b.height / 2))
    assert dim < bright


def test_rendering_an_empty_view_does_not_raise() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    world.provinces.clear()
    view = build_view(world, cfg, bound_faction_id=None, speed="paused")
    render_map(cairo.Context(_surface()), view, WIDTH, HEIGHT, COLS)


def test_rendering_is_stable_for_the_same_view() -> None:
    view, _world = _view()
    first, second = _surface(), _surface()
    render_map(cairo.Context(first), view, WIDTH, HEIGHT, COLS)
    render_map(cairo.Context(second), view, WIDTH, HEIGHT, COLS)
    first.flush()
    second.flush()
    assert bytes(first.get_data()) == bytes(second.get_data())
