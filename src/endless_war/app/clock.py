"""Tick scheduling: how wall-clock time becomes simulated ticks.

Pure arithmetic, deliberately free of threads and of the system clock, so the
schedule can be tested exhaustively without waiting for real time to pass.
Nothing here touches world state — speed changes when ticks happen, never what
a tick does.
"""

from __future__ import annotations

SPEEDS: dict[str, float] = {
    "paused": 0.0,
    "1x": 1.0,
    "4x": 4.0,
    "16x": 16.0,
}


def seconds_per_tick(speed: str, live_tick_seconds: float) -> float | None:
    """Real seconds between ticks at `speed`, or None when paused."""
    if speed not in SPEEDS:
        raise ValueError(f"unknown speed: {speed!r}")
    multiplier = SPEEDS[speed]
    if multiplier == 0.0:
        return None
    return live_tick_seconds / multiplier


def ticks_due(
    elapsed_seconds: float,
    speed: str,
    live_tick_seconds: float,
    max_catchup: int,
) -> int:
    """How many ticks `elapsed_seconds` has earned, capped at `max_catchup`."""
    interval = seconds_per_tick(speed, live_tick_seconds)
    if interval is None or elapsed_seconds < interval:
        return 0
    return min(int(elapsed_seconds / interval), max_catchup)
