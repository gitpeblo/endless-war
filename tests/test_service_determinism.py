import threading
import time

from endless_war.app.commands import Pause, Resume, SetSpeed
from endless_war.app.service import SimulationService
from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world

TICKS = 400


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self.now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += seconds


def _fingerprint(world: WorldState) -> tuple:
    """Everything a tick can change, in a stable order.

    Audited against every `simulation/systems/*.py` module (see
    task-5-report.md, "Fingerprint audit"). Beyond the brief's original
    fields, a tick also mutates: Army.equipment, Army.morale, Army.supply,
    Army.destination_id and Army.stance (movement.py, battle.py,
    strategic.py); Faction.treasury, Faction.manpower, Faction.stability,
    Faction.war_support and Faction.exhaustion_casualty_mark (economy.py,
    diplomacy.py); and the entire `wars` dict, including war status and
    last_capture_tick (diplomacy.py), plus the id counters `next_war_id` and
    `next_event_id`. All of those are included below so a bug in any system
    cannot hide from this comparison.
    """
    return (
        world.tick_count,
        world.current_time,
        world.next_war_id,
        world.next_event_id,
        tuple(
            (
                pid,
                world.provinces[pid].controller_faction_id,
                round(world.provinces[pid].supply_value, 9),
                world.provinces[pid].population,
            )
            for pid in sorted(world.provinces)
        ),
        tuple(
            (
                aid,
                world.armies[aid].province_id,
                world.armies[aid].manpower,
                round(world.armies[aid].organization, 9),
                round(world.armies[aid].equipment, 9),
                round(world.armies[aid].morale, 9),
                round(world.armies[aid].supply, 9),
                world.armies[aid].destination_id,
                world.armies[aid].stance,
            )
            for aid in sorted(world.armies)
        ),
        tuple(
            (
                fid,
                world.factions[fid].casualties,
                round(world.factions[fid].exhaustion, 9),
                round(world.factions[fid].treasury, 9),
                world.factions[fid].manpower,
                round(world.factions[fid].stability, 9),
                round(world.factions[fid].war_support, 9),
                world.factions[fid].exhaustion_casualty_mark,
                tuple(sorted(world.factions[fid].at_war_with)),
            )
            for fid in sorted(world.factions)
        ),
        tuple(
            (
                wid,
                world.wars[wid].status,
                world.wars[wid].last_capture_tick,
                tuple(sorted(world.wars[wid].attackers)),
                tuple(sorted(world.wars[wid].defenders)),
            )
            for wid in sorted(world.wars)
        ),
        tuple(event.id for event in world.events),
    )


def _straight_through(cfg, ticks: int) -> WorldState:
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(ticks):
        engine.tick()
    return world


def _via_service(cfg, commands_at: dict[int, list]) -> WorldState:
    """Run at least TICKS ticks through the service, submitting commands en route.

    The service ticks in batches (catch-up is capped per wake), so it may stop a
    few ticks PAST the target. That is fine and must not be papered over: the
    caller compares against a plain engine run of whatever length this actually
    reached, so the comparison is always like-for-like.
    """
    world = generate_world(seed=42, config=cfg)
    clock = FakeClock()
    pending = dict(commands_at)
    service = SimulationService(
        world, cfg, speed="1x", monotonic=clock, sleep=lambda _s: None
    )
    service.start()
    try:
        for _ in range(20_000):
            view = service.latest_view()
            reached = view.tick_count if view is not None else 0
            if reached >= TICKS:
                break
            for at in sorted(k for k in pending if k <= reached):
                for command in pending.pop(at):
                    service.submit(command)
            clock.advance(1.0)
            time.sleep(0.001)
    finally:
        service.stop()
    assert world.tick_count >= TICKS, "the service never reached the target tick count"
    assert not pending, f"commands were never submitted: {sorted(pending)}"
    return world


def _assert_history_matches(cfg, commands_at: dict[int, list]) -> None:
    actual = _via_service(cfg, commands_at)
    expected = _straight_through(cfg, actual.tick_count)
    assert _fingerprint(actual) == _fingerprint(expected)


def _drive_until(service, clock, predicate, *, max_iterations=20_000, step=1.0):
    """Advance the fake clock and yield to the service thread until `predicate` holds.

    Never waits on real time beyond the 1ms yield needed to let the service
    thread actually run; the deadline is an iteration count, not a clock.
    """
    for _ in range(max_iterations):
        view = service.latest_view()
        if view is not None and predicate(view):
            return view
        clock.advance(step)
        time.sleep(0.001)
    raise AssertionError("condition was never met within max_iterations")


def test_pausing_and_resuming_changes_nothing_about_the_history() -> None:
    """An explicit phase script, not a tick-keyed command dict.

    Keying `Resume()` to a tick count that pausing makes unreachable is what
    made the earlier version of this test an unsatisfiable, racy driver (see
    task-5-report.md, "Fix Round 1"). This version submits each command only
    once the previous phase is observably complete, and separately proves the
    property that mattered most and was never actually checked before: that a
    long pause holds the tick count exactly still.
    """
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    clock = FakeClock()
    service = SimulationService(
        world, cfg, speed="1x", monotonic=clock, sleep=lambda _s: None
    )
    service.start()
    try:
        _drive_until(service, clock, lambda v: v.tick_count >= 50)

        service.submit(Pause())
        _drive_until(service, clock, lambda v: v.speed == "paused")

        held_tick_count = service.latest_view().tick_count
        # Advance the fake clock hard while paused -- many iterations, large
        # steps -- and confirm nothing ticks. This is the property the old
        # dict-driven schedule assumed but never actually verified.
        for _ in range(200):
            clock.advance(1000.0)
            time.sleep(0.001)
        assert service.latest_view().tick_count == held_tick_count, (
            "the tick count advanced while paused"
        )

        service.submit(Resume())
        _drive_until(service, clock, lambda v: v.tick_count >= TICKS)
    finally:
        service.stop()

    assert world.tick_count >= TICKS, "the service never reached the target tick count"
    expected = _straight_through(cfg, world.tick_count)
    assert _fingerprint(world) == _fingerprint(expected)


def test_changing_speed_changes_nothing_about_the_history() -> None:
    _assert_history_matches(
        load_config(),
        {10: [SetSpeed("16x")], 120: [SetSpeed("4x")], 300: [SetSpeed("1x")]},
    )


def test_the_service_matches_a_plain_engine_run_with_no_commands_at_all() -> None:
    _assert_history_matches(load_config(), {})


def test_the_service_advances_against_the_real_clock() -> None:
    """The one test here that waits on real time; it stays well under a second."""
    cfg = load_config()
    cfg["simulation"]["live_tick_seconds"] = 0.001
    world = generate_world(seed=42, config=cfg)
    service = SimulationService(world, cfg, speed="16x")
    service.start()
    try:
        deadline = 3.0
        waited = 0.0
        while waited < deadline:
            view = service.latest_view()
            if view is not None and view.tick_count >= 5:
                break
            import time as _time

            _time.sleep(0.02)
            waited += 0.02
        view = service.latest_view()
        assert view is not None and view.tick_count >= 5, "service did not advance in real time"
    finally:
        service.stop()
    assert not service.is_running()
