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
    try:
        _run_until(service, lambda: service.latest_view().tick_count >= 2, clock)
        thread = service._thread  # noqa: SLF001 - observe the real thread, not stop()'s bookkeeping
        service.submit(Shutdown())

        # Poll the thread itself to death, without calling stop(), so this
        # test can only pass because Shutdown actually made the thread exit
        # (deleting _apply's Shutdown branch would hang here instead).
        for _ in range(2000):
            if not thread.is_alive():
                break
            time.sleep(0.001)
        else:
            raise AssertionError("thread did not stop after Shutdown was submitted")

        assert not service.is_running()
    finally:
        service.stop()


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
    calls = {"count": 0}

    def explode(*_args, **_kwargs):
        calls["count"] += 1
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
        frozen_tick_count = view.tick_count
        frozen_calls = calls["count"]
        for _ in range(20):
            clock.advance(10.0)
            time.sleep(0.001)  # yield so a regression actually gets to call tick() again
        assert service.latest_view().tick_count == frozen_tick_count, "a faulted service stops ticking"
        assert calls["count"] == frozen_calls, "a faulted service must stop calling tick() at all"
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


def test_resuming_after_a_long_pause_does_not_burst_catch_up_ticks() -> None:
    service, clock, _world = _service()
    service.start()
    try:
        _run_until(service, lambda: service.latest_view().tick_count >= 1, clock)
        service.submit(Pause())
        _run_until(service, lambda: service.latest_view().speed == "paused", clock, 0.0)
        frozen = service.latest_view().tick_count

        # A pause must not bank backlog: advance the clock by far more than
        # max_catchup ticks' worth of simulated time while still paused, and
        # give the paused thread a real yield so it observes (and discards)
        # the gap before Resume is ever queued.
        clock.advance(1000.0)
        time.sleep(0.01)

        service.submit(Resume())
        _run_until(service, lambda: service.latest_view().speed == "1x", clock, 0.0)
        assert _run_until(
            service, lambda: service.latest_view().tick_count > frozen, clock
        )
        assert service.latest_view().tick_count == frozen + 1, (
            "resuming after a long pause must advance one tick's worth of "
            "progress, not a max_catchup burst"
        )
    finally:
        service.stop()


def test_a_timed_out_stop_is_observable_and_blocks_a_second_thread() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    clock = FakeClock()
    # A sleep callable that blocks far longer than the join timeout below,
    # so the simulation thread cannot notice `_stopping` promptly and the
    # join is guaranteed to time out.
    service = SimulationService(
        world, cfg, monotonic=clock, sleep=lambda _s: time.sleep(0.2)
    )
    service.start()
    try:
        time.sleep(0.05)  # let the thread get into its slow sleep at least once

        stopped_cleanly = service.stop(timeout=0.02)
        assert stopped_cleanly is False, (
            "a timed-out stop must be observable, not silently reported as success"
        )
        assert service.is_running() is True, "the thread is still alive after a timed-out stop"

        # start()'s guard must refuse to spawn a second thread on top of the
        # first one, which never actually died -- two threads calling
        # engine.tick() on one WorldState is the exact bug being prevented.
        service.start()
        sim_threads = [t for t in threading.enumerate() if t.name == "endless-war-sim"]
        assert len(sim_threads) == 1, "a timed-out stop must not let start() spawn a second thread"

        # The slow thread does eventually notice `_stopping` and exit; a
        # generously-timed stop() must then succeed and report True.
        assert service.stop(timeout=2.0) is True
        assert service.is_running() is False
    finally:
        service.stop()


def test_start_recovers_after_a_stale_thread_dies_on_its_own() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    clock = FakeClock()
    # Same slow-sleep trick as the timed-out-stop test: force a stop() to
    # time out and leave a stale-but-alive thread reference behind.
    service = SimulationService(
        world, cfg, monotonic=clock, sleep=lambda _s: time.sleep(0.2)
    )
    service.start()
    try:
        time.sleep(0.05)  # let the thread get into its slow sleep at least once

        assert service.stop(timeout=0.02) is False
        assert service.is_running() is True

        # While the old thread is genuinely alive, start() must still
        # refuse -- the same property test_a_timed_out_stop_is_observable_
        # and_blocks_a_second_thread protects.
        service.start()
        assert (
            len([t for t in threading.enumerate() if t.name == "endless-war-sim"]) == 1
        ), "start() must refuse while the old thread is still alive"

        # _stopping is already set from the stop() call above, so the old
        # thread exits on its own the next time it wakes from its slow
        # sleep -- neither stop() nor start() is called again to make that
        # happen. Poll the real thread to death, bounded so a regression
        # fails fast instead of hanging.
        old_thread = service._thread  # noqa: SLF001 - poll the real thread directly
        for _ in range(2000):
            if not old_thread.is_alive():
                break
            time.sleep(0.001)
        else:
            raise AssertionError("old thread did not die on its own")

        assert service.is_running() is False, "is_running() already agrees the thread is gone"

        # start() must not refuse forever just because self._thread is a
        # stale reference to a thread that has since died on its own --
        # that would make the service unusable through its own interface.
        service.start()
        assert service.is_running() is True
        sim_threads = [t for t in threading.enumerate() if t.name == "endless-war-sim"]
        assert len(sim_threads) == 1, "start() after a stale dead thread must run exactly one thread"
    finally:
        service.stop()


def test_a_failing_publish_surfaces_as_a_faulted_view_instead_of_a_silent_stall(
    monkeypatch,
) -> None:
    from endless_war.app import service as service_module

    real_build_view = service_module.build_view

    def flaky_build_view(*args, **kwargs):
        # Fails on every "normal" publish, but succeeds once the caller is
        # already reporting a fault -- this is what lets _safe_publish's
        # retry actually get a faulted view out, rather than modelling a
        # bug that can never be surfaced at all.
        if kwargs.get("fault_message") is None:
            raise RuntimeError("publish exploded")
        return real_build_view(*args, **kwargs)

    monkeypatch.setattr(service_module, "build_view", flaky_build_view)

    service, clock, _world = _service()
    service.start()

    def has_faulted() -> bool:
        view = service.latest_view()
        return view is not None and view.faulted

    try:
        assert _run_until(service, has_faulted, clock)
        view = service.latest_view()
        assert view.faulted is True
        assert "publish exploded" in view.fault_message
        assert service.is_running() is True, "a failing publish must not kill the thread"
    finally:
        service.stop()


def test_the_service_accepts_64x() -> None:
    service, clock, _world = _service(speed="64x")
    service.start()
    try:
        assert _run_until(
            service, lambda: service.latest_view().speed == "64x", clock, 0.0
        )
    finally:
        service.stop()
