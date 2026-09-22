"""Deterministic world generation.

A rectangular grid graph is the simplest province topology that still produces
real fronts and salients. docs/data-model.md treats provinces as a graph, so
nothing downstream may assume the grid: always walk `Province.neighbors`.
"""

from __future__ import annotations

import random
from collections import deque
from datetime import datetime, timezone
from typing import Any

from endless_war.domain.models import Faction, Province, WorldState

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


FACTION_NAMES: list[str] = [
    "Valdran Hegemony",
    "Korsk Federation",
    "Meridian Compact",
    "Astaran Dominion",
    "Free Cities League",
]
FACTION_COLORS: list[str] = ["red", "blue", "green", "amber", "violet"]


def _pick_capitals(world: WorldState, rng: random.Random, count: int, cols: int) -> list[int]:
    """Choose `count` well-separated provinces as capitals (greedy farthest-point)."""
    ids = sorted(world.provinces)
    chosen = [rng.choice(ids)]
    while len(chosen) < count:
        best_id, best_dist = ids[0], -1.0
        for pid in ids:
            if pid in chosen:
                continue
            row, col = divmod(pid, cols)
            nearest = min(
                abs(row - divmod(c, cols)[0]) + abs(col - divmod(c, cols)[1]) for c in chosen
            )
            if nearest > best_dist:
                best_dist, best_id = float(nearest), pid
        chosen.append(best_id)
    return chosen


def generate_factions(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Create factions and assign contiguous starting territory."""
    count: int = config["world"]["default_factions"]
    cols: int = config["world"]["grid_cols"]
    ceiling: float = config["balance"]["mobilization_ceiling"]
    if count > len(FACTION_NAMES):
        raise ValueError(f"only {len(FACTION_NAMES)} faction names are defined")

    capitals = _pick_capitals(world, rng, count, cols)
    for fid, capital in enumerate(capitals):
        world.factions[fid] = Faction(
            id=fid,
            name=FACTION_NAMES[fid],
            capital_province_id=capital,
            color_key=FACTION_COLORS[fid],
            treasury=round(rng.uniform(400_000, 900_000), 2),
            stability=round(rng.uniform(0.55, 0.9), 3),
            war_support=round(rng.uniform(0.35, 0.6), 3),
        )
        world.provinces[capital].is_capital = True

    # Multi-source BFS: every province goes to the nearest capital, so each
    # faction's territory is contiguous by construction.
    queue: deque[int] = deque()
    for fid, capital in enumerate(capitals):
        world.provinces[capital].owner_faction_id = fid
        world.provinces[capital].controller_faction_id = fid
        queue.append(capital)
    while queue:
        pid = queue.popleft()
        owner = world.provinces[pid].owner_faction_id
        for nid in world.provinces[pid].neighbors:
            neighbour = world.provinces[nid]
            if neighbour.owner_faction_id is None:
                neighbour.owner_faction_id = owner
                neighbour.controller_faction_id = owner
                queue.append(nid)

    for fid, fac in sorted(world.factions.items()):
        population = sum(
            p.population for p in world.provinces.values() if p.owner_faction_id == fid
        )
        fac.manpower = int(population * ceiling * rng.uniform(0.35, 0.6))


def generate_world(seed: int, config: dict[str, Any]) -> WorldState:
    """Build a complete starting world. This is the only entry point callers need."""
    world = WorldState(seed=seed, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))
    world.expected_province_count = config["world"]["default_provinces"]
    rng = random.Random(seed)
    generate_province_grid(world, rng, config)
    generate_factions(world, rng, config)
    generate_armies(world, rng, config)
    return world


ARMIES_PER_FACTION = 3


def generate_armies(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Place each faction's starting armies on its capital and border provinces."""
    from endless_war.domain.models import Army

    next_id = 0
    for fid in sorted(world.factions):
        fac = world.factions[fid]
        owned = [
            pid for pid in sorted(world.provinces)
            if world.provinces[pid].owner_faction_id == fid
        ]
        border = [
            pid for pid in owned
            if any(
                world.provinces[n].owner_faction_id != fid
                for n in world.provinces[pid].neighbors
            )
        ]
        placements = [fac.capital_province_id]
        placements += rng.sample(border, k=min(ARMIES_PER_FACTION - 1, len(border)))
        while len(placements) < ARMIES_PER_FACTION:
            placements.append(rng.choice(owned))

        for province_id in placements:
            strength = int(fac.manpower * rng.uniform(0.08, 0.16))
            fac.manpower = max(0, fac.manpower - strength)
            world.armies[next_id] = Army(
                id=next_id,
                faction_id=fid,
                province_id=province_id,
                manpower=strength,
                equipment=round(rng.uniform(0.6, 0.95), 3),
                morale=round(rng.uniform(0.6, 0.9), 3),
                organization=round(rng.uniform(0.7, 1.0), 3),
                training=round(rng.uniform(0.5, 0.85), 3),
            )
            next_id += 1
