import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.colors import faction_rgb
from endless_war.ui.legend import (
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
            return sum((g - (WASH_ALPHA * c)) ** 2 for g, c in zip(got, rgb))

        others = [f.color_key for f in view.factions if f.color_key != entry.color_key]
        assert all(distance(entry.color_key) < distance(k) for k in others), entry.label
