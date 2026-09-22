"""Simulation systems: stateless functions that mutate WorldState in place.

Every system has the signature (world, rng, config) -> None and is called by
SimulationEngine.tick() in the fixed order from docs/architecture.md.
"""

from __future__ import annotations


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp to [low, high]. Every bounded field is written through this."""
    return max(low, min(high, value))
