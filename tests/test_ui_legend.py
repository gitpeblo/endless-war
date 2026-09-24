import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.colors import faction_rgb
from endless_war.ui.legend import legend_entries, legend_height, render_legend


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
    assert len(bound) == 1
    assert bound[0].color_key == _view(bound=0).factions[0].color_key


def test_the_legend_paints_each_factions_swatch() -> None:
    view = _view()
    height = legend_height(view)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 220, height)
    render_legend(cairo.Context(surface), view, 220, height)
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    # The first row is the first faction; its swatch starts at the left edge.
    x, y = 8, 8 + 4
    offset = y * stride + x * 4
    red, green, blue = data[offset + 2], data[offset + 1], data[offset]
    expected = tuple(round(c * 255) for c in faction_rgb(view.factions[0].color_key))
    assert all(abs(a - b) <= 2 for a, b in zip((red, green, blue), expected))
