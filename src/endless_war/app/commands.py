"""Commands a consumer may submit to the simulation service.

None of these touch world state: they change when ticks happen, which faction a
view describes, or whether the service is running. That is what keeps a paused,
sped-up or rebound run byte-identical to a straight-through one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pause:
    """Stop advancing the clock; the world keeps its state."""


@dataclass(frozen=True, slots=True)
class Resume:
    """Return to the speed in use before the last pause."""


@dataclass(frozen=True, slots=True)
class SetSpeed:
    """Switch to one of the speeds in clock.SPEEDS."""

    speed: str


@dataclass(frozen=True, slots=True)
class BindFaction:
    """Describe this faction in future views, or the world when None."""

    faction_id: int | None


@dataclass(frozen=True, slots=True)
class Shutdown:
    """Stop the service thread after the current tick."""


Command = Pause | Resume | SetSpeed | BindFaction | Shutdown
