import threading
import time

from endless_war.app.commands import BindFaction, Pause, Resume, SetSpeed, Shutdown
from endless_war.app.service import SimulationService
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self) -> None:
        self.now = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += seconds


def _service(**kwargs):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    clock = FakeClock()
    service = SimulationService(
        world, cfg, monotonic=clock, sleep=lambda _s: None, **kwargs
    )
    return service, clock, world


def _run_until(service, predicate, clock, step=1.0, limit=3000):
    """Drive the service thread by advancing the fake clock until predicate holds.

    The 1 ms sleep is a yield to the simulation thread, not a wait on simulated
    time: without it this loop spins so fast the other thread may never be
    scheduled, which is how thread tests turn flaky on a loaded machine.
    """
    for _ in range(limit):
        if predicate():
            return True
        clock.advance(step)
        time.sleep(0.001)
    return predicate()


def test_a_fresh_service_publishes_a_view_before_any_tick() -> None:
    service, _clock, _world = _service()
    service.start()
    try:
        assert _run_until(service, lambda: service.latest_view() is not None, _clock, 0.0)
        view = service.latest_view()
        assert view.tick_count == 0
        assert view.speed == "1x"
        assert view.faulted is False
    finally:
        service.stop()


def test_the_clock_advances_the_world() -> None:
    service, clock, world = _service()
    service.start()
    try:
        assert _run_until(service, lambda: service.latest_view().tick_count >= 5, clock)
        assert world.tick_count >= 5
    finally:
        service.stop()


def test_pausing_stops_the_world_and_resume_restores_the_speed() -> None:
    service, clock, _world = _service(speed="4x")
    service.start()
    try:
        _run_until(service, lambda: service.latest_view().tick_count >= 4, clock)
        service.submit(Pause())
        _run_until(service, lambda: service.latest_view().speed == "paused", clock, 0.0)
        frozen = service.latest_view().tick_count
        for _ in range(50):
            clock.advance(10.0)
        assert service.latest_view().tick_count == frozen
        service.submit(Resume())
        _run_until(service, lambda: service.latest_view().speed == "4x", clock, 0.0)
        assert _run_until(
            service, lambda: service.latest_view().tick_count > frozen, clock
        )
    finally:
        service.stop()


def test_setting_a_speed_is_reflected_in_the_view() -> None:
    service, clock, _world = _service()
    service.start()
    try:
        service.submit(SetSpeed("16x"))
        assert _run_until(
            service, lambda: service.latest_view().speed == "16x", clock, 0.0
        )
    finally:
        service.stop()


def test_binding_a_faction_changes_later_views_only() -> None:
    service, clock, _world = _service()
    service.start()
    try:
        _run_until(service, lambda: service.latest_view() is not None, clock, 0.0)
        assert service.latest_view().bound_faction_id is None
        service.submit(BindFaction(2))
        assert _run_until(
            service, lambda: service.latest_view().bound_faction_id == 2, clock
        )
    finally:
        service.stop()


def test_the_slot_keeps_only_the_newest_view() -> None:
    service, clock, _world = _service(speed="16x")
    service.start()
    try:
        _run_until(service, lambda: service.latest_view().tick_count >= 20, clock)
        first = service.latest_view()
        second = service.latest_view()
        assert first is second, "reading must not consume the slot"
        _run_until(
            service, lambda: service.latest_view().tick_count > first.tick_count, clock
        )
        assert service.latest_view().tick_count > first.tick_count
    finally:
        service.stop()


def test_shutdown_stops_the_thread() -> None:
    service, clock, _world = _service()
    service.start()
    _run_until(service, lambda: service.latest_view().tick_count >= 2, clock)
    service.submit(Shutdown())
    service.stop()
    assert not service.is_running()


def test_stop_is_idempotent_and_leaves_no_thread() -> None:
    service, clock, _world = _service()
    service.start()
    _run_until(service, lambda: service.latest_view() is not None, clock, 0.0)
    service.stop()
    service.stop()
    assert not service.is_running()
    assert not any(t.name == "endless-war-sim" for t in threading.enumerate())


def test_a_failing_tick_surfaces_as_a_faulted_view_instead_of_a_silent_stall() -> None:
    service, clock, _world = _service()

    def explode(*_args, **_kwargs):
        raise RuntimeError("tick exploded")

    service._engine.tick = explode  # noqa: SLF001 - injecting a fault is the point
    service.start()

    def has_faulted() -> bool:
        view = service.latest_view()
        return view is not None and view.faulted

    try:
        assert _run_until(service, has_faulted, clock)
        view = service.latest_view()
        assert view.faulted is True
        assert "tick exploded" in view.fault_message
        frozen = view.tick_count
        for _ in range(20):
            clock.advance(10.0)
        assert service.latest_view().tick_count == frozen, "a faulted service stops ticking"
    finally:
        service.stop()


def test_a_failing_command_surfaces_as_a_faulted_view_instead_of_killing_the_thread() -> None:
    service, clock, _world = _service()
    service.start()
    try:
        assert _run_until(service, lambda: service.latest_view() is not None, clock, 0.0)
        service.submit(SetSpeed("ludicrous"))

        def has_faulted() -> bool:
            view = service.latest_view()
            return view is not None and view.faulted

        assert _run_until(service, has_faulted, clock, 0.0)

        # The signature of the old bug was is_running() going False while
        # latest_view() kept returning a stale, unfaulted view. Assert the
        # thread survived the bad command, not just that some view exists.
        assert service.is_running() is True

        view = service.latest_view()
        assert view.faulted is True
        assert "ludicrous" in view.fault_message

        frozen = view.tick_count
        for _ in range(20):
            clock.advance(10.0)
        assert (
            service.latest_view().tick_count == frozen
        ), "a faulted service stops ticking, whether the fault came from a tick or a command"
    finally:
        service.stop()
