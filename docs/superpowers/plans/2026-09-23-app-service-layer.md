# Application Service Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the simulation a live wall-clock heartbeat in a background thread, and publish immutable snapshots of world state that a GUI on another thread can read safely.

**Architecture:** A new `src/endless_war/app/` package sits between `simulation/` and the future `ui/`. A `SimulationService` owns the engine and one background thread; after each tick it builds a frozen `WorldView` and publishes it to a latest-wins slot. Consumers read snapshots and submit commands (pause, speed, faction binding, shutdown) that are applied only at tick boundaries. No GTK code appears anywhere in this plan.

**Tech Stack:** Python 3.12 standard library only — `threading`, `queue`, `time`, `dataclasses`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-23-app-service-layer-design.md`

## Global Constraints

- **Determinism is absolute.** Same initial state + seed + commands reproduce the same history. No command in this plan may touch world state. Wall-clock time decides *when* a tick happens, never *what* it does. Never call the `random` module; the engine owns the only RNG.
- **Never iterate a set**, and iterate dicts via `sorted(...)` wherever order can affect a result. Snapshot contents must be a pure function of world state, in a stable order.
- **Layer direction is one-way:** `app/` may import `domain` and `simulation`. Nothing in `domain/`, `simulation/` or `ai/` may import `app/`. No module in this plan may import GTK, tray, persistence, or `tools/`.
- **Tunable numbers live in `config/default.toml`**, never in code. This plan adds one key: `max_catchup_ticks_per_wake` under `[simulation]`.
- **TDD is required** for every task: write the test, run it and capture the failure, implement, capture the pass.
- **Fixture discipline:** any test that selects a faction or province must assert the premise it relies on rather than assuming properties of the seed-42 map. Five tasks on the previous branch shipped fixtures that assumed false things about it; the worst passed by luck.
- **Time and threads must be injectable.** Every unit that reads the clock or sleeps takes those as parameters so tests run in microseconds and never flake. Exactly one test in this plan uses real wall-clock time.
- Existing suite is 87 tests, green. It must stay green.

---

### Task 1: The view model

**Files:**
- Create: `src/endless_war/app/__init__.py`
- Create: `src/endless_war/app/view_model.py`
- Test: `tests/test_view_model.py`

**Interfaces:**
- Consumes: `endless_war.domain.models` (types only)
- Produces: `ProvinceCell`, `FactionRow`, `EventLine`, `WorldView` — all frozen dataclasses. Every later task builds or reads these.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_view_model.py
import dataclasses
from datetime import datetime, timezone

import pytest

from endless_war.app.view_model import EventLine, FactionRow, ProvinceCell, WorldView


def _cell() -> ProvinceCell:
    return ProvinceCell(
        id=0,
        name="P000",
        owner_faction_id=1,
        controller_faction_id=2,
        color_key="red",
        is_capital=False,
        is_contested=True,
        has_armies=True,
        has_supply_problem=False,
    )


def test_a_province_cell_cannot_be_mutated() -> None:
    cell = _cell()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.controller_faction_id = 3


def test_a_world_view_cannot_be_mutated() -> None:
    view = WorldView(
        simulated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        tick_count=4,
        speed="1x",
        faulted=False,
        fault_message=None,
        bound_faction_id=None,
        provinces=(_cell(),),
        factions=(),
        recent_events=(),
        active_wars=0,
        total_wars=0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.tick_count = 5


def test_collections_on_a_view_are_tuples_not_lists() -> None:
    view = WorldView(
        simulated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        tick_count=0,
        speed="paused",
        faulted=False,
        fault_message=None,
        bound_faction_id=2,
        provinces=(_cell(),),
        factions=(
            FactionRow(
                id=2,
                name="Meridian Compact",
                color_key="blue",
                provinces=21,
                population=11_255_752,
                manpower=1_000,
                treasury=5.0,
                casualties=0,
                exhaustion=0.0,
                war_support=0.5,
                stability=1.0,
                at_war_with=(1,),
            ),
        ),
        recent_events=(
            EventLine(
                id=7,
                simulated_at=datetime(2030, 6, 1, tzinfo=timezone.utc),
                category="diplomacy",
                severity="critical",
                title="War declared",
                body="A has declared war on B.",
            ),
        ),
        active_wars=1,
        total_wars=1,
    )
    assert isinstance(view.provinces, tuple)
    assert isinstance(view.factions, tuple)
    assert isinstance(view.recent_events, tuple)
    assert isinstance(view.factions[0].at_war_with, tuple)


def test_a_view_holds_no_simulation_objects() -> None:
    """A view must be safe to read while the simulation mutates its own state."""
    fields = {f.name: f.type for f in dataclasses.fields(WorldView)}
    joined = " ".join(str(t) for t in fields.values())
    for forbidden in ("WorldState", "Province]", "Faction]", "Army", "War]"):
        assert forbidden not in joined, f"view model leaks a simulation type: {forbidden}"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_view_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.app'`

- [ ] **Step 3: Create the package and the view model**

```python
# src/endless_war/app/__init__.py
"""Application services: the layer between the simulation and any interface.

Nothing here imports GTK, tray or persistence code. Everything in this package
is testable headlessly.
"""
```

```python
# src/endless_war/app/view_model.py
"""Immutable view of the world, safe to read from another thread.

A view holds plain values only — never a reference to a live simulation object.
That is what lets the GTK thread read one while the simulation keeps mutating
its own state, with no lock and no possibility of a UI handler writing back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ProvinceCell:
    """One province as the map needs it (docs/superpowers/specs/02-ui-and-tray.md)."""

    id: int
    name: str
    owner_faction_id: int | None
    controller_faction_id: int | None
    color_key: str
    is_capital: bool
    is_contested: bool
    has_armies: bool
    has_supply_problem: bool


@dataclass(frozen=True, slots=True)
class FactionRow:
    """One faction as the status panel and tray summary need it."""

    id: int
    name: str
    color_key: str
    provinces: int
    population: int
    manpower: int
    treasury: float
    casualties: int
    exhaustion: float
    war_support: float
    stability: float
    at_war_with: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EventLine:
    """One logged event, without its related-entity ids."""

    id: int
    simulated_at: datetime
    category: str
    severity: str
    title: str
    body: str


@dataclass(frozen=True, slots=True)
class WorldView:
    """Everything a consumer may see about the world at one instant."""

    simulated_at: datetime
    tick_count: int
    speed: str
    faulted: bool
    fault_message: str | None
    bound_faction_id: int | None
    provinces: tuple[ProvinceCell, ...]
    factions: tuple[FactionRow, ...]
    recent_events: tuple[EventLine, ...]
    active_wars: int
    total_wars: int
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_view_model.py -v`
Expected: PASS — 4 tests

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — 91 (87 existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/app/__init__.py src/endless_war/app/view_model.py tests/test_view_model.py
git commit -m "feat: immutable view model for consumers outside the simulation"
```

---

### Task 2: The snapshot builder

**Files:**
- Create: `src/endless_war/app/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `view_model.ProvinceCell/FactionRow/EventLine/WorldView` (Task 1); `endless_war.simulation.systems.movement.hostile_armies_in`
- Produces: `RECENT_EVENT_LIMIT: int`, and
  `build_view(world, config, *, bound_faction_id, speed, fault_message=None) -> WorldView`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_snapshot.py
from endless_war.app.snapshot import RECENT_EVENT_LIMIT, build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world


def _world():
    cfg = load_config()
    return generate_world(seed=42, config=cfg), cfg


def test_every_province_appears_exactly_once_in_stable_order() -> None:
    world, cfg = _world()
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    ids = [cell.id for cell in view.provinces]
    assert ids == sorted(world.provinces)
    assert len(ids) == len(set(ids))


def test_faction_rows_carry_controlled_totals() -> None:
    world, cfg = _world()
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    rows = {row.id: row for row in view.factions}
    assert set(rows) == set(world.factions)
    for fid, row in rows.items():
        controlled = [
            p for p in world.provinces.values() if p.controller_faction_id == fid
        ]
        assert row.provinces == len(controlled)
        assert row.population == sum(p.population for p in controlled)
        assert row.name == world.factions[fid].name


def test_at_war_with_is_a_sorted_tuple_not_a_set() -> None:
    world, cfg = _world()
    world.factions[0].at_war_with = {3, 2}
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    row = next(r for r in view.factions if r.id == 0)
    assert row.at_war_with == (2, 3)


def test_binding_a_faction_is_recorded_and_unbound_is_none() -> None:
    world, cfg = _world()
    assert build_view(world, cfg, bound_faction_id=2, speed="1x").bound_faction_id == 2
    assert build_view(world, cfg, bound_faction_id=None, speed="1x").bound_faction_id is None


def test_an_occupied_province_is_contested() -> None:
    world, cfg = _world()
    target = next(
        pid for pid in sorted(world.provinces)
        if world.provinces[pid].owner_faction_id == 0
    )
    assert world.provinces[target].controller_faction_id == 0, "premise: owner controls it"
    world.provinces[target].controller_faction_id = 3
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    cell = next(c for c in view.provinces if c.id == target)
    assert cell.is_contested


def test_a_province_holding_a_hostile_army_is_contested() -> None:
    world, cfg = _world()
    army = world.armies[0]
    here = world.provinces[army.province_id]
    assert here.controller_faction_id == army.faction_id, "premise: army is at home"
    enemy = next(
        fid for fid in sorted(world.factions) if fid != army.faction_id
    )
    world.factions[army.faction_id].at_war_with = {enemy}
    world.factions[enemy].at_war_with = {army.faction_id}
    world.armies[army.id] = army
    intruder = next(a for a in world.armies.values() if a.faction_id == enemy)
    intruder.province_id = here.id
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    cell = next(c for c in view.provinces if c.id == here.id)
    assert cell.is_contested
    assert cell.has_armies


def test_a_starved_province_is_flagged() -> None:
    world, cfg = _world()
    threshold = cfg["balance"]["low_supply_threshold"]
    pid = sorted(world.provinces)[0]
    assert world.provinces[pid].supply_value >= threshold, "premise: starts supplied"
    world.provinces[pid].supply_value = threshold - 0.01
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert next(c for c in view.provinces if c.id == pid).has_supply_problem


def test_the_event_window_is_bounded_and_newest_last() -> None:
    world, cfg = _world()
    engine = SimulationEngine(world, cfg)
    for _ in range(600):
        engine.tick()
    assert len(world.events) > RECENT_EVENT_LIMIT, "premise: the run logged enough events"
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert len(view.recent_events) == RECENT_EVENT_LIMIT
    newest = list(world.events)[-1]
    assert view.recent_events[-1].id == newest.id
    assert [line.id for line in view.recent_events] == sorted(
        line.id for line in view.recent_events
    )


def test_war_counts_are_reported() -> None:
    world, cfg = _world()
    engine = SimulationEngine(world, cfg)
    for _ in range(1500):
        engine.tick()
    assert world.wars, "premise: the run declared at least one war"
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert view.total_wars == len(world.wars)
    assert view.active_wars == sum(
        1 for w in world.wars.values() if w.status == "active"
    )


def test_speed_and_fault_are_carried_through() -> None:
    world, cfg = _world()
    ok = build_view(world, cfg, bound_faction_id=None, speed="16x")
    assert ok.speed == "16x" and ok.faulted is False and ok.fault_message is None
    bad = build_view(world, cfg, bound_faction_id=None, speed="paused", fault_message="boom")
    assert bad.faulted is True and bad.fault_message == "boom"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_snapshot.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.app.snapshot'`

- [ ] **Step 3: Write the snapshot builder**

```python
# src/endless_war/app/snapshot.py
"""Turn live world state into an immutable view.

This is the only place where simulation objects become view data. A view that
needs a field it does not carry extends the view model here, rather than a
consumer reaching into WorldState.
"""

from __future__ import annotations

from typing import Any

from endless_war.app.view_model import EventLine, FactionRow, ProvinceCell, WorldView
from endless_war.domain.models import WorldState
from endless_war.simulation.systems.movement import hostile_armies_in

RECENT_EVENT_LIMIT = 12


def _province_cells(
    world: WorldState, low_supply_threshold: float
) -> tuple[ProvinceCell, ...]:
    occupied: dict[int, bool] = {}
    armies_here: dict[int, bool] = {}
    for aid in sorted(world.armies):
        armies_here[world.armies[aid].province_id] = True

    cells = []
    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        controller = province.controller_faction_id
        contested = controller != province.owner_faction_id
        if not contested and controller is not None:
            contested = bool(hostile_armies_in(world, pid, controller))
        occupied[pid] = contested
        color = (
            world.factions[controller].color_key
            if controller in world.factions
            else "grey"
        )
        cells.append(
            ProvinceCell(
                id=pid,
                name=province.name,
                owner_faction_id=province.owner_faction_id,
                controller_faction_id=controller,
                color_key=color,
                is_capital=province.is_capital,
                is_contested=contested,
                has_armies=armies_here.get(pid, False),
                has_supply_problem=province.supply_value < low_supply_threshold,
            )
        )
    return tuple(cells)


def _faction_rows(world: WorldState) -> tuple[FactionRow, ...]:
    controlled: dict[int, list[int]] = {fid: [] for fid in sorted(world.factions)}
    for pid in sorted(world.provinces):
        controller = world.provinces[pid].controller_faction_id
        if controller in controlled:
            controlled[controller].append(pid)

    rows = []
    for fid in sorted(world.factions):
        faction = world.factions[fid]
        mine = controlled[fid]
        rows.append(
            FactionRow(
                id=fid,
                name=faction.name,
                color_key=faction.color_key,
                provinces=len(mine),
                population=sum(world.provinces[pid].population for pid in mine),
                manpower=faction.manpower,
                treasury=faction.treasury,
                casualties=faction.casualties,
                exhaustion=faction.exhaustion,
                war_support=faction.war_support,
                stability=faction.stability,
                at_war_with=tuple(sorted(faction.at_war_with)),
            )
        )
    return tuple(rows)


def _recent_events(world: WorldState) -> tuple[EventLine, ...]:
    window = list(world.events)[-RECENT_EVENT_LIMIT:]
    return tuple(
        EventLine(
            id=event.id,
            simulated_at=event.simulated_at,
            category=event.category,
            severity=event.severity,
            title=event.title,
            body=event.body,
        )
        for event in window
    )


def build_view(
    world: WorldState,
    config: dict[str, Any],
    *,
    bound_faction_id: int | None,
    speed: str,
    fault_message: str | None = None,
) -> WorldView:
    """Snapshot `world`. The result shares no mutable object with it."""
    return WorldView(
        simulated_at=world.current_time,
        tick_count=world.tick_count,
        speed=speed,
        faulted=fault_message is not None,
        fault_message=fault_message,
        bound_faction_id=bound_faction_id,
        provinces=_province_cells(world, config["balance"]["low_supply_threshold"]),
        factions=_faction_rows(world),
        recent_events=_recent_events(world),
        active_wars=sum(1 for w in world.wars.values() if w.status == "active"),
        total_wars=len(world.wars),
    )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_snapshot.py -v`
Expected: PASS — 10 tests

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — 101

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/app/snapshot.py tests/test_snapshot.py
git commit -m "feat: build immutable world snapshots for view consumers"
```

---

### Task 3: Speeds, the tick schedule, and commands

**Files:**
- Create: `src/endless_war/app/clock.py`
- Create: `src/endless_war/app/commands.py`
- Modify: `config/default.toml` (add one key to `[simulation]`)
- Test: `tests/test_clock.py`

**Interfaces:**
- Consumes: nothing from earlier tasks
- Produces: `SPEEDS: dict[str, float]`, `seconds_per_tick(speed, live_tick_seconds) -> float | None`,
  `ticks_due(elapsed_seconds, speed, live_tick_seconds, max_catchup) -> int`;
  command types `Pause`, `Resume`, `SetSpeed(speed: str)`, `BindFaction(faction_id: int | None)`, `Shutdown`, and the union alias `Command`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_clock.py
import pytest

from endless_war.app.clock import SPEEDS, seconds_per_tick, ticks_due
from endless_war.app.commands import BindFaction, Pause, Resume, SetSpeed, Shutdown
from endless_war.config import load_config


def test_the_four_speeds_are_paused_1x_4x_16x() -> None:
    assert sorted(SPEEDS) == sorted(["paused", "1x", "4x", "16x"])
    assert SPEEDS["paused"] == 0.0
    assert SPEEDS["1x"] == 1.0
    assert SPEEDS["4x"] == 4.0
    assert SPEEDS["16x"] == 16.0


def test_a_faster_speed_means_less_time_per_tick() -> None:
    assert seconds_per_tick("1x", 1.0) == 1.0
    assert seconds_per_tick("4x", 1.0) == 0.25
    assert seconds_per_tick("16x", 1.0) == 0.0625


def test_paused_has_no_tick_interval() -> None:
    assert seconds_per_tick("paused", 1.0) is None


def test_an_unknown_speed_is_rejected() -> None:
    with pytest.raises(ValueError):
        seconds_per_tick("ludicrous", 1.0)


def test_no_ticks_are_due_before_the_interval_elapses() -> None:
    assert ticks_due(0.5, "1x", 1.0, max_catchup=8) == 0


def test_ticks_accumulate_with_elapsed_time() -> None:
    assert ticks_due(1.0, "1x", 1.0, max_catchup=8) == 1
    assert ticks_due(3.7, "1x", 1.0, max_catchup=8) == 3
    assert ticks_due(1.0, "4x", 1.0, max_catchup=8) == 4


def test_a_paused_clock_never_owes_a_tick() -> None:
    assert ticks_due(10_000.0, "paused", 1.0, max_catchup=8) == 0


def test_a_long_sleep_is_capped_rather_than_simulating_a_week() -> None:
    assert ticks_due(86_400.0, "1x", 1.0, max_catchup=8) == 8


def test_the_catchup_cap_is_configured_not_hardcoded() -> None:
    cfg = load_config()
    assert cfg["simulation"]["max_catchup_ticks_per_wake"] >= 1


def test_commands_are_frozen_values() -> None:
    assert SetSpeed("4x").speed == "4x"
    assert BindFaction(2).faction_id == 2
    assert BindFaction(None).faction_id is None
    for command in (Pause(), Resume(), Shutdown()):
        assert command == type(command)()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_clock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.app.clock'`

- [ ] **Step 3: Add the config key**

In `config/default.toml`, inside the existing `[simulation]` table (leave every other table untouched):

```toml
# How many ticks the service may run in one wake-up. Caps catch-up after a
# laptop sleep or a stalled reader so the world does not simulate a week at once.
max_catchup_ticks_per_wake = 8
```

- [ ] **Step 4: Write the clock and the commands**

```python
# src/endless_war/app/clock.py
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
```

```python
# src/endless_war/app/commands.py
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
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_clock.py -v`
Expected: PASS — 10 tests

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — 111

- [ ] **Step 7: Commit**

```bash
git add src/endless_war/app/clock.py src/endless_war/app/commands.py config/default.toml tests/test_clock.py
git commit -m "feat: tick schedule, speeds, and the service command set"
```

---

### Task 4: The simulation service

**Files:**
- Create: `src/endless_war/app/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `clock.SPEEDS/ticks_due` and every command type (Task 3); `snapshot.build_view` (Task 2); `WorldView` (Task 1); `endless_war.simulation.engine.SimulationEngine`
- Produces: `SimulationService(world, config, *, bound_faction_id=None, speed="1x", monotonic=time.monotonic, sleep=time.sleep, poll_seconds=0.02)` with public methods `start()`, `stop(timeout=2.0)`, `latest_view()`, `submit(command)`

The injected `monotonic` and `sleep` are what keep the tests instant: a fake clock advances time by returning rising numbers, and a fake sleep records calls instead of waiting.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_service.py
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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.app.service'`

- [ ] **Step 3: Write the service**

```python
# src/endless_war/app/service.py
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_service.py -v`
Expected: PASS — 9 tests

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS — 120

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/app/service.py tests/test_service.py
git commit -m "feat: background simulation service with commands and snapshots"
```

---

### Task 5: Determinism equivalence and a real-time smoke test

**Files:**
- Test: `tests/test_service_determinism.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4
- Produces: nothing new — this task proves the spec's load-bearing claim

This task is tests only. It exists because the whole design rests on one
promise: wall-clock policy changes *when* a tick happens, never *what* it does.
If this fails, the design is wrong rather than the test.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_service_determinism.py
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
    """Everything a tick can change, in a stable order."""
    return (
        world.tick_count,
        world.current_time,
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
            )
            for aid in sorted(world.armies)
        ),
        tuple(
            (
                fid,
                world.factions[fid].casualties,
                round(world.factions[fid].exhaustion, 9),
                tuple(sorted(world.factions[fid].at_war_with)),
            )
            for fid in sorted(world.factions)
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


def test_pausing_and_resuming_changes_nothing_about_the_history() -> None:
    _assert_history_matches(
        load_config(), {50: [Pause()], 51: [Resume()], 200: [Pause(), Resume()]}
    )


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
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_service_determinism.py -v`
Expected: FAIL — collection succeeds only once Tasks 1–4 are merged; before then, `ModuleNotFoundError`. If Tasks 1–4 are already in place, run the file and record the genuine first-run output.

- [ ] **Step 3: Make it pass**

No production code should be required. If a test fails, the bug is real: a
command is touching world state, a tick is running while commands are being
applied, or catch-up is dropping or duplicating ticks. Fix the service, not the
test, and report what was wrong.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_service_determinism.py -v`
Expected: PASS — 4 tests

- [ ] **Step 5: Run the full suite and time it**

Run: `time .venv/bin/pytest`
Expected: PASS — 124. Record the wall-clock figure in the commit message; the
new tests drive hundreds of ticks and should add seconds, not minutes.

- [ ] **Step 6: Commit**

```bash
git add tests/test_service_determinism.py
git commit -m "test: wall-clock policy cannot change simulated history"
```

---

### Task 6: Document the layer

**Files:**
- Modify: `docs/architecture.md`
- Modify: `docs/decisions.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the finished layer from Tasks 1–5
- Produces: nothing executable

- [ ] **Step 1: Record the layer in the architecture doc**

In `docs/architecture.md`, in the layer list, describe the application service
layer between the AI/persistence entries and the UI entry: it owns the live
clock and the background simulation thread, publishes immutable `WorldView`
snapshots, and accepts commands that never touch world state. State the
one-way rule explicitly: `app/` imports `simulation`; nothing in `domain/`,
`simulation/` or `ai/` imports `app/`.

- [ ] **Step 2: Add a dated decisions entry**

Append to `docs/decisions.md`, following the file's existing template
(`## YYYY-MM-DD — Title`, then **Decision:**, **Reason:**, **Alternatives
considered:**, **Consequences:**). Date it 2026-09-23. Cover: the frozen view
model over a `WorldState` deep copy or shared state under a lock; commands
applied only at tick boundaries; the four speeds; and the catch-up cap. Under
**Consequences**, state that offline catch-up across process restarts is NOT
provided by this layer and requires persistence.

- [ ] **Step 3: Note the layer in the README**

In the `Running it` section, add a short paragraph: the simulation can now run
on a live clock in a background thread via `endless_war.app.SimulationService`,
which is what the GTK shell will consume; there is still no graphical interface,
and `run_cli.sh` remains the way to watch a run.

- [ ] **Step 4: Verify nothing broke**

Run: `.venv/bin/pytest`
Expected: PASS — 124

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md docs/decisions.md README.md
git commit -m "docs: record the application service layer"
```

---

## Notes for the executor

- **The determinism tests in Task 5 are the point of this plan.** If one fails, do not adjust it to pass — find out which command or scheduling path is changing history and report it.
- **Never let a test wait on real time** except `test_the_service_advances_against_the_real_clock`. Every other test drives the fake clock. A test that sleeps is a test that flakes on a loaded machine.
- **Always stop the service in a `finally` block.** A leaked thread turns an unrelated later test red and is miserable to diagnose.
- If the GTK shell seems to need something the `WorldView` does not carry, add the field to the view model and the snapshot builder — never hand a consumer the `WorldState`.
- Do not add persistence, GTK, tray code, or player control levers. They are separate sub-projects (see the spec's decomposition table).
