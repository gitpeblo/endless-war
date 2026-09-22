"""Deterministic world generation.

A rectangular grid graph is the simplest province topology that still produces
real fronts and salients. docs/data-model.md treats provinces as a graph, so
nothing downstream may assume the grid: always walk `Province.neighbors`.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Province, WorldState

# Defensive multiplier applied to the defender's power in battle.
TERRAIN_DEFENCE: dict[str, float] = {
    "plains": 1.00,
    "forest": 1.20,
    "hills": 1.35,
    "mountain": 1.60,
    "urban": 1.45,
}

_TERRAIN_WEIGHTS: list[tuple[str, int]] = [
    ("plains", 40), ("forest", 22), ("hills", 18), ("mountain", 10), ("urban", 10),
]


def _pick_terrain(rng: random.Random) -> str:
    total = sum(weight for _, weight in _TERRAIN_WEIGHTS)
    roll = rng.randrange(total)
    upto = 0
    for name, weight in _TERRAIN_WEIGHTS:
        upto += weight
        if roll < upto:
            return name
    return _TERRAIN_WEIGHTS[-1][0]


def generate_province_grid(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Populate `world.provinces` with a connected 4-neighbour grid graph."""
    count: int = config["world"]["default_provinces"]
    cols: int = config["world"]["grid_cols"]
    if count % cols:
        raise ValueError(f"default_provinces ({count}) must be divisible by grid_cols ({cols})")
    rows = count // cols

    for row in range(rows):
        for col in range(cols):
            pid = row * cols + col
            terrain = _pick_terrain(rng)
            world.provinces[pid] = Province(
                id=pid,
                name=f"P{pid:03d}",
                population=rng.randint(180_000, 900_000),
                industry=round(rng.uniform(0.4, 2.0), 3),
                infrastructure=round(rng.uniform(0.55, 1.0), 3),
                terrain=terrain,
            )

    for row in range(rows):
        for col in range(cols):
            pid = row * cols + col
            neighbours: list[int] = []
            if col > 0:
                neighbours.append(pid - 1)
            if col < cols - 1:
                neighbours.append(pid + 1)
            if row > 0:
                neighbours.append(pid - cols)
            if row < rows - 1:
                neighbours.append(pid + cols)
            world.provinces[pid].neighbors = sorted(neighbours)
