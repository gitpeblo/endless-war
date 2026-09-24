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

from endless_war.app.clock import SPEEDS, seconds_per_tick, ticks_due
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
        """Spawn the simulation thread. Idempotent while a thread is alive.

        Guards on liveness, not merely on `self._thread` being set, so this
        agrees with `is_running()`. A thread that survived a timed-out
        `stop()` and has since died on its own leaves a stale-but-not-None
        reference behind; refusing to start over that reference forever
        would make the service permanently unusable through its own public
        interface. Refuse only while the existing thread is genuinely
        alive; otherwise clear the stale reference and spawn a fresh one.
        """
        if self._thread is not None:
            if self._thread.is_alive():
                return
            self._thread = None
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name=THREAD_NAME, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> bool:
        """Ask the thread to finish and wait for it. Idempotent.

        Returns True once the thread has actually stopped, False if `timeout`
        elapsed while it was still alive. On a timeout, `self._thread` is left
        in place rather than cleared: `is_running()` must keep reporting that
        the thread is alive, and `start()`'s "already running" guard must keep
        refusing to spawn a second thread on top of a first one that never
        actually died -- two threads calling `engine.tick()` on one WorldState
        is exactly what this service exists to prevent.
        """
        self._stopping.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        if thread.is_alive():
            return False
        self._thread = None
        return True

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
            # Only this thread assigns `_view`, so reading it without the lock is safe.
            previous=self._view,
        )
        with self._view_lock:
            self._view = view

    def _safe_publish(self) -> None:
        """Publish a view; if publishing itself fails, fault instead of dying.

        `_drain()` and `engine.tick()` each have an exception boundary that
        turns a failure into a fault; `_publish()` did not, so a bug in
        `build_view` would unwind `_run` and kill the thread with no faulted
        view ever surfacing -- indistinguishable from a healthy-but-slow
        simulation. If the first attempt raises, record the fault (unless one
        is already recorded, so a publish failure never overwrites a more
        informative tick/command fault) and try once more to publish that
        faulted view. If even that second attempt raises -- publishing the
        fault about publishing can fail too -- give up silently for this
        cycle rather than let the exception escape: the thread must survive
        and `is_running()` must stay truthful no matter what `build_view`
        does.
        """
        try:
            self._publish()
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            if self._fault_message is None:
                self._fault_message = f"{type(exc).__name__}: {exc}"
            try:
                self._publish()
            except Exception:  # noqa: BLE001 - already faulted; must not crash the thread
                pass

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
        self._safe_publish()
        while not self._stopping.is_set():
            try:
                changed = self._drain()
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                self._fault_message = f"{type(exc).__name__}: {exc}"
                changed = True
            if self._stopping.is_set():
                break

            now = self._monotonic()
            due = 0
            if self._fault_message is None:
                interval = seconds_per_tick(self._speed, self._live_tick_seconds)
                if interval is None:
                    # Paused: nothing is owed, and nothing may accrue while
                    # paused either -- refresh the reference point every
                    # iteration so a long pause never banks a catch-up burst.
                    last_tick_at = now
                else:
                    due = ticks_due(
                        now - last_tick_at, self._speed, self._live_tick_seconds, self._max_catchup
                    )
                    if due >= self._max_catchup:
                        # The cap was hit: this is what it is for. Discard the
                        # backlog rather than let the world drift further and
                        # further behind wall clock.
                        last_tick_at = now
                    elif due:
                        # Advance by exactly what was consumed, preserving the
                        # sub-interval remainder instead of re-reading the
                        # clock (which would silently drop it every tick).
                        last_tick_at += due * interval
            if due:
                for _ in range(due):
                    try:
                        self._engine.tick()
                    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                        self._fault_message = f"{type(exc).__name__}: {exc}"
                        break

            if due or changed:
                self._safe_publish()
            self._sleep(self._poll_seconds)
        self._safe_publish()
