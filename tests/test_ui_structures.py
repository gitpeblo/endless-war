import dataclasses

import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.structures import NAMES, load_structure, structure_for


def _cell(**changes):
    cfg = load_config()
    view = build_view(generate_world(seed=42, config=cfg), cfg, bound_faction_id=None, speed="1x")
    base = dataclasses.replace(
        view.provinces[0], is_capital=False, is_industrial=False, terrain="plains"
    )
    return dataclasses.replace(base, **changes)


def test_every_structure_sprite_ships() -> None:
    for name in NAMES:
        sprite = load_structure(name)
        assert (sprite.get_width(), sprite.get_height()) == (32, 32), name


def test_one_structure_per_province_capital_first() -> None:
    assert structure_for(_cell()) is None
    assert structure_for(_cell(terrain="urban")) == "town"
    assert structure_for(_cell(is_industrial=True, terrain="urban")) == "industry"
    assert structure_for(_cell(is_capital=True, is_industrial=True, terrain="urban")) == "capital"
