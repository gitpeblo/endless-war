"""Supply propagation.

Follows the model in docs/simulation-notes.md: capitals and industrial centres
generate supply, it spreads only through provinces the same faction controls,
and poor infrastructure makes each hop cost more.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems import clamp

INDUSTRIAL_SOURCE_THRESHOLD = 1.5


def update_supply(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Recompute `supply_value` for every province by BFS from supply sources."""
    decay: float = config["balance"]["base_supply_decay_per_hop"]
    floor: float = config["balance"]["min_supply"]

    for prov in world.provinces.values():
        prov.supply_value = floor

    for fid in sorted(world.factions):
        sources = [
            pid
            for pid in sorted(world.provinces)
            if world.provinces[pid].controller_faction_id == fid
            and (
                world.provinces[pid].is_capital
                or world.provinces[pid].industry >= INDUSTRIAL_SOURCE_THRESHOLD
            )
        ]
        # A faction that controls neither its capital nor any industrial centre
        # supplies nothing; every province stays at the floor.
        if not sources:
            continue

        cost: dict[int, float] = {pid: 0.0 for pid in sources}
        queue: deque[int] = deque(sources)
        while queue:
            pid = queue.popleft()
            prov = world.provinces[pid]
            for nid in prov.neighbors:
                neighbour = world.provinces[nid]
                if neighbour.controller_faction_id != fid:
                    continue
                hop = decay / max(0.3, neighbour.infrastructure)
                candidate = cost[pid] + hop
                if candidate < cost.get(nid, float("inf")):
                    cost[nid] = candidate
                    queue.append(nid)

        for pid, total in cost.items():
            world.provinces[pid].supply_value = clamp(1.0 - total, floor, 1.0)
