import random
from datetime import datetime, timezone

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.worldgen import generate_province_grid


def _world() -> WorldState:
    return WorldState(seed=42, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))


def test_generates_expected_province_count() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    assert len(w.provinces) == 96


def test_neighbours_are_symmetric() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    for pid, prov in w.provinces.items():
        for nid in prov.neighbors:
            assert pid in w.provinces[nid].neighbors


def test_corner_province_has_two_neighbours() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    assert len(w.provinces[0].neighbors) == 2


def test_graph_is_connected() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    seen = {0}
    stack = [0]
    while stack:
        for nid in w.provinces[stack.pop()].neighbors:
            if nid not in seen:
                seen.add(nid)
                stack.append(nid)
    assert len(seen) == len(w.provinces)


def test_terrain_is_known_and_population_positive() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    for prov in w.provinces.values():
        assert prov.terrain in load_config()["balance"]["terrain_defence"]
        assert prov.population > 0
        assert 0.0 <= prov.infrastructure <= 1.0


def test_generation_is_reproducible_for_same_seed() -> None:
    a, b = _world(), _world()
    generate_province_grid(a, random.Random(42), load_config())
    generate_province_grid(b, random.Random(42), load_config())
    assert [(p.terrain, p.population) for p in a.provinces.values()] == [
        (p.terrain, p.population) for p in b.provinces.values()
    ]
