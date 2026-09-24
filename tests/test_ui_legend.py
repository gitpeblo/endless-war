import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.colors import faction_rgb
from endless_war.ui.legend import (
    GROUND_RGB,
    PAD,
    TERRAIN_ORDER,
    legend_entries,
    legend_height,
    render_legend,
    row_height,
    swatch_centre,
)
from endless_war.ui.map_view import WASH_ALPHA


def _view(bound=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    return build_view(world, cfg, bound_faction_id=bound, speed="1x")


def test_every_faction_is_named_with_its_colour() -> None:
    view = _view()
    factions = [e for e in legend_entries(view) if e.kind == "faction"]
    assert [(e.label, e.color_key) for e in factions] == [
        (f.name, f.color_key) for f in view.factions
    ]


def test_every_map_symbol_is_explained() -> None:
    kinds = [e.kind for e in legend_entries(_view())]
    for kind in ("contested", "supply", "capital", "army"):
        assert kind in kinds


def test_the_outline_is_explained_only_when_a_faction_is_bound() -> None:
    assert "bound" not in [e.kind for e in legend_entries(_view())]
    bound = [e for e in legend_entries(_view(bound=0)) if e.kind == "bound"]
    assert len(bound) == 1 and bound[0].color_key == _view(bound=0).factions[0].color_key


def test_a_terrain_section_lists_every_simulation_terrain_in_order() -> None:
    entries = legend_entries(_view())
    kinds = [e.kind for e in entries]
    start = kinds.index("heading")
    assert entries[start].label == "Terrain"
    terrains = [e.terrain for e in entries[start + 1 :]]
    assert terrains == list(TERRAIN_ORDER)
    assert set(TERRAIN_ORDER) == set(load_config()["balance"]["terrain_defence"])


def test_the_height_covers_every_row() -> None:
    view = _view()
    assert legend_height(view) == 2 * PAD + sum(row_height(e) for e in legend_entries(view))


def test_each_faction_swatch_shows_its_wash() -> None:
    # The swatch is the map's wash over dark ground: the pixel at the swatch
    # centre must be nearer its own faction's washed colour than any other's.
    view = _view()
    height = legend_height(view)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 240, height)
    render_legend(cairo.Context(surface), view, 240, height)
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    entries = legend_entries(view)
    for index, entry in enumerate(entries):
        if entry.kind != "faction":
            continue
        x, y = swatch_centre(entries, index)
        o = int(y) * stride + int(x) * 4
        got = (data[o + 2], data[o + 1], data[o])

        def distance(key: str) -> float:
            rgb = [c * 255 for c in faction_rgb(key)]
            ground = [c * 255 for c in GROUND_RGB]
            want = [gr + WASH_ALPHA * (c - gr) for gr, c in zip(ground, rgb)]
            return sum((g - w) ** 2 for g, w in zip(got, want))

        others = [f.color_key for f in view.factions if f.color_key != entry.color_key]
        assert all(distance(entry.color_key) < distance(k) for k in others), entry.label


def _render(view):
    height = legend_height(view)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 240, height)
    render_legend(cairo.Context(surface), view, 240, height)
    surface.flush()
    return surface


def _px(surface, x, y):
    data, stride = surface.get_data(), surface.get_stride()
    o = int(y) * stride + int(x) * 4
    return data[o + 2], data[o + 1], data[o]


def test_the_supply_and_occupied_swatches_are_visible_on_their_ground() -> None:
    # Drawn on black, a darkening wash and dark hatching were invisible.
    view = _view()
    surface = _render(view)
    entries = legend_entries(view)
    ground = sum(round(c * 255) for c in GROUND_RGB)
    for index, entry in enumerate(entries):
        x, y = swatch_centre(entries, index)
        if entry.kind == "supply":
            assert sum(_px(surface, x, y)) < ground - 10, "supply swatch not darker than ground"
        if entry.kind == "contested":
            dark = sum(
                1 for dx in range(-8, 9) for dy in range(-2, 3)
                if sum(_px(surface, x + dx, y + dy)) < ground - 10
            )
            assert dark > 5, "no hatching visible on the occupied swatch"
        if entry.kind == "army":
            assert sum(_px(surface, x + 4.5, y + 2)) < ground - 10, "army dot not visible"
