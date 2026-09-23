"""The simulation service: one background thread driving one engine.

Consumers see three things — start/stop, the latest snapshot, and a command
queue. They never touch WorldState, and commands are applied only between
ticks, so a paused or sped-up run produces the same history as a
straight-through one.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from endless_war.app.clock import SPEEDS, ticks_due
from endless_war.app.commands import (
    BindFaction,
    Command,
    Pause,
    Resume,
    SetSpeed,
    Shutdown,
)
from endless_war.app.snapshot import build_view
from endless_war.app.view_model import WorldView
from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine

THREAD_NAME = "endless-war-sim"


class SimulationService:
    """Owns the engine and the only thread allowed to advance it."""

    def __init__(
        self,
        world: WorldState,
        config: dict[str, Any],
        *,
        bound_faction_id: int | None = None,
        speed: str = "1x",
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        poll_seconds: float = 0.02,
    ) -> None:
        if speed not in SPEEDS:
            raise ValueError(f"unknown speed: {speed!r}")
        self._world = world
        self._config = config
        self._engine = SimulationEngine(world, config)
        self._bound_faction_id = bound_faction_id
        self._speed = speed
        self._resume_speed = speed if speed != "paused" else "1x"
        self._monotonic = monotonic
        self._sleep = sleep
        self._poll_seconds = poll_seconds
        self._live_tick_seconds: float = config["simulation"]["live_tick_seconds"]
        self._max_catchup: int = config["simulation"]["max_catchup_ticks_per_wake"]
        self._commands: queue.Queue[Command] = queue.Queue()
        self._view: WorldView | None = None
        self._view_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._fault_message: str | None = None

    # -- public interface -------------------------------------------------

    def start(self) -> None:
        """Spawn the simulation thread. Idempotent."""
        if self._thread is not None:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name=THREAD_NAME, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the thread to finish and wait for it. Idempotent."""
        self._stopping.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def latest_view(self) -> WorldView | None:
        """The newest snapshot, or None before the first publish. Never blocks."""
        with self._view_lock:
            return self._view

    def submit(self, command: Command) -> None:
        """Queue a command; it is applied at the next tick boundary."""
        self._commands.put(command)

    # -- internals --------------------------------------------------------

    def _publish(self) -> None:
        view = build_view(
            self._world,
            self._config,
            bound_faction_id=self._bound_faction_id,
            speed=self._speed,
            fault_message=self._fault_message,
        )
        with self._view_lock:
            self._view = view

    def _apply(self, command: Command) -> None:
        if isinstance(command, Pause):
            if self._speed != "paused":
                self._resume_speed = self._speed
            self._speed = "paused"
        elif isinstance(command, Resume):
            self._speed = self._resume_speed
        elif isinstance(command, SetSpeed):
            if command.speed not in SPEEDS:
                raise ValueError(f"unknown speed: {command.speed!r}")
            if command.speed != "paused":
                self._resume_speed = command.speed
            self._speed = command.speed
        elif isinstance(command, BindFaction):
            self._bound_faction_id = command.faction_id
        elif isinstance(command, Shutdown):
            self._stopping.set()

    def _drain(self) -> bool:
        """Apply every queued command. True if any were applied."""
        applied = False
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return applied
            self._apply(command)
            applied = True

    def _run(self) -> None:
        last_tick_at = self._monotonic()
        self._publish()
        while not self._stopping.is_set():
            changed = self._drain()
            if self._stopping.is_set():
                break

            due = 0
            if self._fault_message is None:
                due = ticks_due(
                    self._monotonic() - last_tick_at,
                    self._speed,
                    self._live_tick_seconds,
                    self._max_catchup,
                )
            if due:
                last_tick_at = self._monotonic()
                for _ in range(due):
                    try:
                        self._engine.tick()
                    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                        self._fault_message = f"{type(exc).__name__}: {exc}"
                        break

            if due or changed:
                self._publish()
            self._sleep(self._poll_seconds)
        self._publish()
