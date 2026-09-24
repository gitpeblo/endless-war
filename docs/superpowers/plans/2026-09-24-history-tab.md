# History Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the War Room into Map and History tabs; the History tab shows a per-faction-toggleable cumulative casualty chart over the full event log, with the factions recoloured to a validated palette.

**Architecture:** The simulation records one frozen `CasualtyReading` per simulated date into world state (step 11 of the tick pipeline). `build_view` exposes the readings and the full event log on `WorldView`, reusing the previous view's event lines so the snapshot stays cheap. The UI adds a `Gtk.Notebook`; the chart is a pure cairo renderer plus pure helpers, wrapped by a thin `Gtk.DrawingArea`, exactly like `render_map`/`MapView`.

**Tech Stack:** Python 3.12, GTK 3 via PyGObject, pycairo, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-history-tab-design.md`

## Global Constraints

- Layer rule: `ui/` imports `app/` and `endless_war.config` and nothing else from the project at module scope. `CasualtyReading` reaches `ui/` through `app/view_model.py`.
- Determinism: no `random`, no wall clock, no `id()`, no unsorted-set iteration in simulation code. The recorder uses only `world.current_time` and faction totals.
- Tick pipeline order is fixed. `record_history` runs after `record_events`, inside the `SYSTEM PIPELINE` markers, as part of step 11.
- The simulation thread never touches GTK; widgets are fed only from `WarRoom.refresh()` on the GTK thread.
- `gi.require_version(...)` precedes every `gi.repository` import; module imports after it carry `# noqa: E402`.
- Colours, exact: blue `#3987e5`, orange `#d95926`, teal `#199e70`, gold `#c98500`, pink `#d55181`; fallback `grey` stays `(0.45, 0.45, 0.45)`. Map background is `#1c1f24` (`BACKGROUND = (0.11, 0.12, 0.14)`).
- Performance budget: median `build_view` < 1 ms with 10 years of readings and a full 2000-event log; 10-year CLI run < 5.5 s (baseline 4.7 s).
- Chart: one y-axis; cumulative values; 2 px lines; text never in a series colour; colour follows the faction, never its position among the visible factions.
- Toggling a faction never calls `service.submit()`.
- Run tests with `.venv/bin/python -m pytest` (the venv has `--system-site-packages`; widget tests need `DISPLAY`, which is `:0` on this machine).

## Review Focus

1. A very long game (100 years ≈ 36,500 readings): the chart must still draw, by sampling one reading per horizontal pixel rather than stroking all of them. Test in Task 4.
2. A chart with a single reading, or all-zero casualties (the first days of a game): no division by zero, the axis still reads `0`. Test in Task 4.
3. The pointer over the chart's margins, or over an empty chart: no crosshair, no exception. Test in Task 4.
4. The window resized very small: rendering returns early instead of drawing negative-size plots. Test in Task 4.
5. The event log at its 2000-entry cap, where every new event evicts the oldest: the reused lines must match a full rebuild exactly. Test in Task 3.

---

### Task 1: Validated faction palette

**Files:**
- Modify: `src/endless_war/ui/colors.py`
- Modify: `src/endless_war/simulation/worldgen.py:81`
- Modify: `tests/test_ui_geometry.py:18-23`
- Modify: `tests/test_view_model.py:16`

**Interfaces:**
- Consumes: nothing new.
- Produces: `FACTION_RGB` keys `blue`, `orange`, `teal`, `gold`, `pink`, `grey`; `faction_rgb(color_key) -> RGB` unchanged in signature. `worldgen.FACTION_COLORS == ["blue", "orange", "teal", "gold", "pink"]`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ui_geometry.py`:

```python
def test_faction_colours_are_the_validated_palette() -> None:
    # Checked with the dataviz palette validator against the map background
    # (#1c1f24); see docs/decisions.md, 2026-09-24. Change these only by
    # re-running the validator.
    expected = {
        "blue": "#3987e5",
        "orange": "#d95926",
        "teal": "#199e70",
        "gold": "#c98500",
        "pink": "#d55181",
    }
    for key, code in expected.items():
        want = tuple(int(code[i : i + 2], 16) / 255 for i in (1, 3, 5))
        assert faction_rgb(key) == pytest.approx(want), key
    assert FACTION_COLORS == list(expected)
```

In the same file, replace `test_components_stay_in_range` with:

```python
def test_components_stay_in_range() -> None:
    for key in ("blue", "orange", "teal", "gold", "pink", "grey"):
        for component in faction_rgb(key):
            assert 0.0 <= component <= 1.0
    for component in darken(faction_rgb("orange")) + lighten(faction_rgb("orange")):
        assert 0.0 <= component <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ui_geometry.py -v`
Expected: FAIL in `test_faction_colours_are_the_validated_palette` (`orange` falls back to grey).

- [ ] **Step 3: Implement**

In `src/endless_war/ui/colors.py`, replace the `FACTION_RGB` block with:

```python
def _hex(code: str) -> RGB:
    return tuple(int(code[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


# Validated with the dataviz palette checker against the map background
# (#1c1f24): lightness band, chroma floor, adjacent-pair colour-blind
# separation, normal-vision floor and contrast all pass. No five colours can
# pass all-pairs; the legend, the bound-faction outline and the chart's direct
# labels are the secondary encoding. See docs/decisions.md, 2026-09-24.
FACTION_RGB: dict[str, RGB] = {
    "blue": _hex("#3987e5"),
    "orange": _hex("#d95926"),
    "teal": _hex("#199e70"),
    "gold": _hex("#c98500"),
    "pink": _hex("#d55181"),
    "grey": (0.45, 0.45, 0.45),
}
```

In `src/endless_war/simulation/worldgen.py`, line 81:

```python
FACTION_COLORS: list[str] = ["blue", "orange", "teal", "gold", "pink"]
```

In `tests/test_view_model.py`, line 16: `color_key="red",` → `color_key="blue",`.

Then confirm nothing else names an old key:

Run: `grep -rn '"red"\|"green"\|"amber"\|"violet"' src tests`
Expected: no output.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass (168 + 1 new). `color_key` never touches the RNG, so the determinism and long-run tests are unaffected. If one fails, stop and report; do not adjust it.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/colors.py src/endless_war/simulation/worldgen.py tests/test_ui_geometry.py tests/test_view_model.py
git commit -m "feat: recolour factions to a validated palette"
```

---

### Task 2: Casualty history recorder

**Files:**
- Modify: `src/endless_war/domain/models.py` (new `CasualtyReading`; new `WorldState` field)
- Create: `src/endless_war/simulation/systems/history.py`
- Modify: `src/endless_war/simulation/engine.py` (import; one call after `record_events`)
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `WorldState.current_time`, `Faction.casualties`.
- Produces:
  - `CasualtyReading(simulated_at: datetime, casualties: tuple[tuple[int, int], ...])`, frozen, slots; `casualties` is `(faction_id, cumulative)` sorted by id.
  - `WorldState.casualty_history: list[CasualtyReading]` (default empty).
  - `record_history(world: WorldState) -> None` in `endless_war.simulation.systems.history`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.systems.history import record_history
from endless_war.simulation.worldgen import generate_world


def _engine(seed: int = 42) -> SimulationEngine:
    cfg = load_config()
    return SimulationEngine(generate_world(seed=seed, config=cfg), cfg)


def test_a_fresh_world_has_no_readings() -> None:
    assert _engine().world.casualty_history == []


def test_one_reading_per_simulated_date() -> None:
    engine = _engine()
    dates = []
    for _ in range(40):
        engine.tick()
        dates.append(engine.world.current_time.date())
    recorded = [r.simulated_at.date() for r in engine.world.casualty_history]
    assert recorded == sorted(set(dates))


def test_day_sized_ticks_still_record_every_date() -> None:
    # Offline catch-up may tick a day at a time; "every 4 ticks" would be wrong.
    engine = _engine()
    for _ in range(5):
        engine.tick(hours=24)
    readings = engine.world.casualty_history
    assert len(readings) == 5
    assert all(
        b.simulated_at - a.simulated_at == timedelta(days=1)
        for a, b in zip(readings, readings[1:])
    )


def test_a_reading_holds_every_factions_total_at_that_moment() -> None:
    world = _engine().world
    world.factions[0].casualties = 1234
    world.factions[3].casualties = 99
    record_history(world)
    reading = world.casualty_history[-1]
    assert reading.simulated_at == world.current_time
    assert reading.casualties == tuple(
        (fid, world.factions[fid].casualties) for fid in sorted(world.factions)
    )


def test_a_second_call_on_the_same_date_adds_nothing() -> None:
    world = _engine().world
    record_history(world)
    record_history(world)
    assert len(world.casualty_history) == 1


def test_readings_are_frozen() -> None:
    world = _engine().world
    record_history(world)
    with pytest.raises(FrozenInstanceError):
        world.casualty_history[0].casualties = ()  # type: ignore[misc]


def test_the_same_seed_records_the_same_series() -> None:
    a, b = _engine(7), _engine(7)
    a.run(4 * 60)
    b.run(4 * 60)
    assert a.world.casualty_history == b.world.casualty_history


def test_a_year_of_war_records_real_losses() -> None:
    # Premise guard: a series of zeros would pass every test above.
    engine = _engine()
    engine.run(4 * 365)
    last = dict(engine.world.casualty_history[-1].casualties)
    assert sum(last.values()) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_history.py -v`
Expected: collection ERROR, `No module named 'endless_war.simulation.systems.history'`.

- [ ] **Step 3: Implement**

In `src/endless_war/domain/models.py`, add directly above `class WorldState`:

```python
@dataclass(frozen=True, slots=True)
class CasualtyReading:
    """Every faction's cumulative casualties at one simulated instant.

    Frozen and built from tuples, so a view can share a reading instead of
    copying it.
    """

    simulated_at: datetime
    casualties: tuple[tuple[int, int], ...]  # (faction_id, cumulative), sorted by id
```

and add this field as the last line of `WorldState`:

```python
    casualty_history: list[CasualtyReading] = field(default_factory=list)
```

Create `src/endless_war/simulation/systems/history.py`:

```python
"""Casualty history: one reading per simulated date.

Runs at the end of step 11 (event generation). The cadence is by date rather
than by tick count, because `SimulationEngine.tick(hours=...)` can run ticks
longer than six hours.
"""

from __future__ import annotations

from endless_war.domain.models import CasualtyReading, WorldState


def record_history(world: WorldState) -> None:
    """Append one casualty reading when the simulated date has moved on."""
    history = world.casualty_history
    if history and history[-1].simulated_at.date() >= world.current_time.date():
        return
    history.append(
        CasualtyReading(
            simulated_at=world.current_time,
            casualties=tuple(
                (fid, world.factions[fid].casualties) for fid in sorted(world.factions)
            ),
        )
    )
```

In `src/endless_war/simulation/engine.py`, add the import next to the other systems:

```python
from endless_war.simulation.systems.history import record_history
```

and inside the pipeline markers, directly after the `record_events(...)` call and before `# --- SYSTEM PIPELINE END ---`:

```python
        record_history(self.world)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_history.py -v` → all 8 PASS.
Run: `.venv/bin/python -m pytest -q` → everything passes.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/domain/models.py src/endless_war/simulation/systems/history.py src/endless_war/simulation/engine.py tests/test_history.py
git commit -m "feat: record one casualty reading per simulated date"
```

---

### Task 3: View model — casualty series and full event log

**Files:**
- Modify: `src/endless_war/app/view_model.py` (re-export `CasualtyReading`; two `WorldView` fields)
- Modify: `src/endless_war/app/snapshot.py` (`_event_line`, `_event_log`, `previous=` parameter)
- Modify: `src/endless_war/app/service.py:123-132` (`_publish` passes `previous=self._view`)
- Test: `tests/test_snapshot.py` (append)

**Interfaces:**
- Consumes: `WorldState.casualty_history` (Task 2), `world.events` (ids are consecutive: `systems/events.py` assigns `next_event_id` and evicts only from the left).
- Produces:
  - `WorldView.casualty_history: tuple[CasualtyReading, ...]`, oldest first.
  - `WorldView.event_log: tuple[EventLine, ...]`, every event in `world.events`, oldest first.
  - `build_view(world, config, *, bound_faction_id, speed, fault_message=None, previous: WorldView | None = None) -> WorldView`. `previous` must be an earlier view **of the same world**; it lets unchanged event lines be reused.
  - `from endless_war.app.view_model import CasualtyReading` works.

**Why `previous`:** measured on this machine, turning 2000 events into `EventLine`s costs 1.5 ms per snapshot, over the 1 ms budget. Reusing the previous tuple costs ~0.0001 ms. Because ids are consecutive and the log only evicts from the left, the reused lines are a slice of the previous log, and only the events after its last id are new.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_snapshot.py` (it already imports `build_view`, `load_config`, `generate_world`; add any missing import at the top):

```python
import dataclasses

from endless_war.app.view_model import CasualtyReading, EventLine
from endless_war.simulation.engine import SimulationEngine


def _ticked(ticks: int):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    engine.run(ticks)
    return engine, world, cfg


def test_the_view_carries_the_casualty_series_oldest_first() -> None:
    engine, world, cfg = _ticked(40)
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert isinstance(view.casualty_history, tuple)
    assert view.casualty_history == tuple(world.casualty_history)
    assert all(isinstance(r, CasualtyReading) for r in view.casualty_history)
    engine.run(8)
    assert len(view.casualty_history) < len(world.casualty_history), (
        "the view must not follow the live list"
    )


def test_the_view_carries_the_whole_event_log() -> None:
    engine, world, cfg = _ticked(0)
    for _ in range(4 * 365):
        if len(world.events) > 20:
            break
        engine.tick()
    assert len(world.events) > 20, "premise: more events than the recent strip holds"
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert len(view.event_log) == len(world.events)
    assert [line.id for line in view.event_log] == [e.id for e in world.events]
    assert all(isinstance(line, EventLine) for line in view.event_log)
    assert view.recent_events == view.event_log[-len(view.recent_events):]


def test_reusing_the_previous_view_matches_a_full_rebuild() -> None:
    engine, world, cfg = _ticked(0)
    for _ in range(4 * 365):
        if len(world.events) > 5:
            break
        engine.tick()
    first = build_view(world, cfg, bound_faction_id=None, speed="1x")
    engine.run(4 * 60)
    reused = build_view(world, cfg, bound_faction_id=None, speed="1x", previous=first)
    fresh = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert reused.event_log == fresh.event_log


def test_reuse_is_correct_at_the_cap_when_old_events_are_evicted() -> None:
    engine, world, cfg = _ticked(0)
    for _ in range(4 * 365):
        if len(world.events) > 5:
            break
        engine.tick()
    first = build_view(world, cfg, bound_faction_id=None, speed="1x")
    # Emulate the cap: evict the three oldest, append two new, as record_events does.
    for _ in range(3):
        world.events.popleft()
    for _ in range(2):
        world.events.append(dataclasses.replace(world.events[-1], id=world.next_event_id))
        world.next_event_id += 1
    reused = build_view(world, cfg, bound_faction_id=None, speed="1x", previous=first)
    fresh = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert reused.event_log == fresh.event_log
    assert [line.id for line in reused.event_log] == [e.id for e in world.events]


def test_reuse_survives_every_old_line_being_evicted() -> None:
    engine, world, cfg = _ticked(0)
    for _ in range(4 * 365):
        if len(world.events) > 5:
            break
        engine.tick()
    first = build_view(world, cfg, bound_faction_id=None, speed="1x")
    template = world.events[-1]
    world.events.clear()
    for _ in range(4):
        world.events.append(dataclasses.replace(template, id=world.next_event_id))
        world.next_event_id += 1
    reused = build_view(world, cfg, bound_faction_id=None, speed="1x", previous=first)
    assert [line.id for line in reused.event_log] == [e.id for e in world.events]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_snapshot.py -v`
Expected: ImportError for `CasualtyReading` from `endless_war.app.view_model`.

- [ ] **Step 3: Implement**

In `src/endless_war/app/view_model.py`, below `from datetime import datetime`:

```python
# Re-exported so ui/ can import it from app/. It is frozen and built from
# tuples, so sharing it with the live world breaks nothing above.
from endless_war.domain.models import CasualtyReading  # noqa: F401
```

and add as the last two fields of `WorldView`:

```python
    casualty_history: tuple[CasualtyReading, ...]
    event_log: tuple[EventLine, ...]
```

In `src/endless_war/app/snapshot.py`, replace `_recent_events` with:

```python
def _event_line(event) -> EventLine:
    return EventLine(
        id=event.id,
        simulated_at=event.simulated_at,
        category=event.category,
        severity=event.severity,
        title=event.title,
        body=event.body,
    )


def _event_log(world: WorldState, previous: WorldView | None) -> tuple[EventLine, ...]:
    """Every event, oldest first, reusing `previous`'s lines where it can.

    Converting 2000 events costs ~1.5 ms, too much to do every tick. Event ids
    are consecutive and `record_events` evicts only from the left, so the lines
    still present are a slice of the previous log and only events after its
    last id are new.
    """
    events = world.events
    if not events:
        return ()
    old = previous.event_log if previous is not None else ()
    first_id, last_id = events[0].id, events[-1].id
    if not old or old[0].id > first_id or old[-1].id > last_id:
        return tuple(_event_line(e) for e in events)
    new_count = last_id - old[-1].id
    if new_count >= len(events):
        return tuple(_event_line(e) for e in events)
    kept = old[first_id - old[0].id :]
    fresh = tuple(_event_line(events[i]) for i in range(len(events) - new_count, len(events)))
    return kept + fresh
```

In `build_view`, add the keyword parameter `previous: WorldView | None = None` after `fault_message`, and build the log once:

```python
    event_log = _event_log(world, previous)
    return WorldView(
        simulated_at=world.current_time,
        tick_count=world.tick_count,
        speed=speed,
        faulted=fault_message is not None,
        fault_message=fault_message,
        bound_faction_id=bound_faction_id,
        provinces=_province_cells(world, config["balance"]["low_supply_threshold"]),
        factions=_faction_rows(world),
        recent_events=event_log[-RECENT_EVENT_LIMIT:],
        active_wars=sum(1 for w in world.wars.values() if w.status == "active"),
        total_wars=len(world.wars),
        casualty_history=tuple(world.casualty_history),
        event_log=event_log,
    )
```

In `src/endless_war/app/service.py` `_publish`, add `previous=self._view,` to the `build_view(...)` call. Only the simulation thread assigns `self._view`, so reading it here without the lock is safe; say so in a one-line comment.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass, including the existing `recent_events` tests in `tests/test_snapshot.py` (the recent strip is now a tail slice of the log, same content and order).

- [ ] **Step 5: Measure the budget and report the numbers**

```bash
PYTHONPATH=src python3 - <<'EOF'
import dataclasses, statistics, time
from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world
cfg = load_config()
w = generate_world(seed=42, config=cfg)
SimulationEngine(w, cfg).run(4 * 365 * 10)
while len(w.events) < 2000:
    w.events.append(dataclasses.replace(w.events[-1], id=w.next_event_id)); w.next_event_id += 1
previous = build_view(w, cfg, bound_faction_id=None, speed="1x")
times = []
for _ in range(200):
    t = time.perf_counter()
    previous = build_view(w, cfg, bound_faction_id=None, speed="1x", previous=previous)
    times.append(time.perf_counter() - t)
print("readings", len(w.casualty_history), "events", len(w.events))
print("build_view median ms", round(statistics.median(times) * 1000, 3))
EOF
/usr/bin/time -f "10-year run %e s" env PYTHONPATH=src python3 -m endless_war > /dev/null
```

Expected: median < 1 ms; 10-year run < 5.5 s. Put both numbers in the task report. If either misses, stop and report — do not tune anything else.

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/app/view_model.py src/endless_war/app/snapshot.py src/endless_war/app/service.py tests/test_snapshot.py
git commit -m "feat: expose the casualty series and full event log on the view"
```

---

### Task 4: The casualty chart

**Files:**
- Create: `src/endless_war/ui/chart.py`
- Test: `tests/test_ui_chart.py`

**Interfaces:**
- Consumes: `CasualtyReading`, `FactionRow` from `endless_war.app.view_model`; `faction_rgb` from `endless_war.ui.colors`; `BACKGROUND` from `endless_war.ui.map_view`.
- Produces (all in `endless_war.ui.chart`):
  - `compact_number(n: int) -> str`
  - `nice_ticks(max_value: int) -> list[int]`: `[0, step, …]`, last ≥ `max_value`; `[0, 1]` when `max_value <= 0`. Steps are 1-2-5 multiples of a power of ten; 2–4 steps for large values. (This refines the spec's "3–6": four target intervals give 2–4.)
  - `x_ticks(t0: datetime, t1: datetime) -> list[tuple[datetime, str]]`: 1 January of each year after `t0` up to `t1` labelled `"2031"`; if there are none, the first of each month labelled `"Feb"`.
  - `series_for(readings, faction_id: int) -> list[tuple[datetime, int]]`
  - `nearest_reading(readings, x: float, width: float) -> int | None`
  - `spread_labels(ys: list[float], min_gap: float) -> list[float]`
  - `render_casualty_chart(cr, readings, factions, visible: frozenset[int], width: float, height: float, hover_x: float | None = None) -> None`
  - `class CasualtyChart(Gtk.DrawingArea)` with `set_data(readings, factions)`, `set_visible(visible: frozenset[int])`, attribute `visible: frozenset[int]`.
  - Constants `MARGIN_LEFT = 52.0`, `MARGIN_RIGHT = 150.0`, `TOOLTIP_BG`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_chart.py`:

```python
from datetime import datetime, timedelta, timezone

import cairo

from endless_war.app.view_model import CasualtyReading, FactionRow
from endless_war.ui.chart import (
    MARGIN_LEFT,
    MARGIN_RIGHT,
    TOOLTIP_BG,
    compact_number,
    nearest_reading,
    nice_ticks,
    render_casualty_chart,
    series_for,
    spread_labels,
    x_ticks,
)
from endless_war.ui.colors import faction_rgb

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
WIDTH, HEIGHT = 600, 300


def _faction(fid: int, key: str, name: str) -> FactionRow:
    return FactionRow(
        id=fid, name=name, color_key=key, provinces=1, population=1, manpower=1,
        treasury=0.0, casualties=0, exhaustion=0.0, war_support=0.5,
        stability=0.5, at_war_with=(),
    )


FACTIONS = (_faction(0, "blue", "Valdran"), _faction(1, "teal", "Korsk"))


def _readings(days: int, rate0: int = 100, rate1: int = 400):
    return tuple(
        CasualtyReading(T0 + timedelta(days=d), ((0, d * rate0), (1, d * rate1)))
        for d in range(days)
    )


def _render(readings, visible, width=WIDTH, height=HEIGHT, hover_x=None):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    render_casualty_chart(
        cairo.Context(surface), readings, FACTIONS, frozenset(visible), width, height, hover_x
    )
    surface.flush()
    return surface


def _count(surface, rgb, tolerance=3) -> int:
    want = [round(c * 255) for c in rgb]
    data, stride = surface.get_data(), surface.get_stride()
    found = 0
    for y in range(surface.get_height()):
        row = y * stride
        for x in range(surface.get_width()):
            o = row + x * 4
            if (abs(data[o + 2] - want[0]) <= tolerance
                    and abs(data[o + 1] - want[1]) <= tolerance
                    and abs(data[o] - want[2]) <= tolerance):
                found += 1
    return found


def test_compact_number() -> None:
    assert compact_number(0) == "0"
    assert compact_number(950) == "950"
    assert compact_number(1_500) == "1.5k"
    assert compact_number(20_000) == "20k"
    assert compact_number(1_000_000) == "1M"
    assert compact_number(1_200_000) == "1.2M"


def test_nice_ticks() -> None:
    assert nice_ticks(0) == [0, 1]
    assert nice_ticks(1) == [0, 1]
    assert nice_ticks(3) == [0, 1, 2, 3]
    assert nice_ticks(7) == [0, 2, 4, 6, 8]
    assert nice_ticks(40_000) == [0, 10_000, 20_000, 30_000, 40_000]
    assert nice_ticks(43_000) == [0, 20_000, 40_000, 60_000]
    big = nice_ticks(123_456_789)
    assert big[0] == 0 and big[-1] >= 123_456_789 and 3 <= len(big) <= 5


def test_x_ticks_mark_years_or_else_months() -> None:
    years = x_ticks(T0, datetime(2032, 6, 1, tzinfo=timezone.utc))
    assert [label for _, label in years] == ["2031", "2032"]
    assert years[0][0] == datetime(2031, 1, 1, tzinfo=timezone.utc)
    months = x_ticks(T0, datetime(2030, 4, 15, tzinfo=timezone.utc))
    assert [label for _, label in months] == ["Feb", "Mar", "Apr"]


def test_series_for_reads_one_faction() -> None:
    readings = _readings(3)
    assert series_for(readings, 1) == [(T0 + timedelta(days=d), d * 400) for d in range(3)]
    assert series_for(readings, 9) == [(T0 + timedelta(days=d), 0) for d in range(3)]


def test_nearest_reading() -> None:
    readings = _readings(3)
    x0, x1 = MARGIN_LEFT, WIDTH - MARGIN_RIGHT
    assert nearest_reading(readings, x0, WIDTH) == 0
    assert nearest_reading(readings, (x0 + x1) / 2, WIDTH) == 1
    assert nearest_reading(readings, x1, WIDTH) == 2
    assert nearest_reading(readings, x0 - 1, WIDTH) is None, "left margin"
    assert nearest_reading(readings, x1 + 1, WIDTH) is None, "label margin"
    assert nearest_reading((), (x0 + x1) / 2, WIDTH) is None


def test_spread_labels_pushes_overlaps_apart_and_keeps_order() -> None:
    assert spread_labels([100.0, 105.0, 300.0], 14.0) == [100.0, 114.0, 300.0]
    assert spread_labels([105.0, 100.0], 14.0) == [114.0, 100.0]
    assert spread_labels([], 14.0) == []


def test_a_visible_factions_line_is_drawn_in_its_colour() -> None:
    surface = _render(_readings(60), {0, 1})
    assert _count(surface, faction_rgb("blue")) > 20
    assert _count(surface, faction_rgb("teal")) > 20


def test_a_hidden_faction_is_drawn_nowhere() -> None:
    surface = _render(_readings(60), {0})
    assert _count(surface, faction_rgb("blue")) > 20
    assert _count(surface, faction_rgb("teal")) == 0


def test_hiding_the_larger_series_rescales_the_axis() -> None:
    # Faction 1 dwarfs faction 0. With 1 hidden, faction 0's line must climb
    # to the top of the plot instead of hugging the baseline.
    def highest_blue_row(surface) -> int:
        want = [round(c * 255) for c in faction_rgb("blue")]
        data, stride = surface.get_data(), surface.get_stride()
        for y in range(surface.get_height()):
            for x in range(int(MARGIN_LEFT), int(WIDTH - MARGIN_RIGHT)):
                o = y * stride + x * 4
                if all(abs(data[o + 2 - k] - want[k]) <= 3 for k in range(3)):
                    return y
        return HEIGHT

    both = highest_blue_row(_render(_readings(60), {0, 1}))
    alone = highest_blue_row(_render(_readings(60), {0}))
    assert alone < both - 50


def test_empty_states_render_without_raising() -> None:
    _render((), {0, 1})
    _render(_readings(30), set())
    _render((), set(), hover_x=200.0)


def test_one_reading_and_all_zero_values_render() -> None:
    _render(_readings(1), {0, 1})
    zeros = tuple(CasualtyReading(T0 + timedelta(days=d), ((0, 0), (1, 0))) for d in range(5))
    _render(zeros, {0, 1}, hover_x=200.0)


def test_a_tiny_widget_renders_without_raising() -> None:
    _render(_readings(30), {0, 1}, width=50, height=30, hover_x=10.0)


def test_hover_draws_a_tooltip_inside_the_plot_and_not_in_the_margin() -> None:
    readings = _readings(60)
    inside = _render(readings, {0, 1}, hover_x=(MARGIN_LEFT + WIDTH - MARGIN_RIGHT) / 2)
    margin = _render(readings, {0, 1}, hover_x=MARGIN_LEFT / 2)
    assert _count(inside, TOOLTIP_BG, tolerance=1) > 100
    assert _count(margin, TOOLTIP_BG, tolerance=1) == 0


def test_a_century_of_readings_renders() -> None:
    readings = tuple(
        CasualtyReading(T0 + timedelta(days=d), ((0, d), (1, d * 3))) for d in range(36_500)
    )
    _render(readings, {0, 1}, hover_x=300.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_chart.py -v`
Expected: collection ERROR, `No module named 'endless_war.ui.chart'`.

- [ ] **Step 3: Implement**

Create `src/endless_war/ui/chart.py`:

```python
"""The casualty chart.

`render_casualty_chart` draws onto any cairo context, so it is tested against
an image surface with no display; the helpers it uses are plain functions.
`CasualtyChart` is the GTK widget wrapped around them.
"""

from __future__ import annotations

import bisect
import math
from datetime import datetime, timedelta

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from endless_war.app.view_model import CasualtyReading, FactionRow  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.map_view import BACKGROUND  # noqa: E402

MARGIN_LEFT = 52.0
MARGIN_RIGHT = 150.0  # room for the direct labels
MARGIN_TOP = 12.0
MARGIN_BOTTOM = 26.0
FONT_SIZE = 11.0
LINE_WIDTH = 2.0
LABEL_GAP = FONT_SIZE + 3
MIN_X_LABEL_SPACING = 50.0
TEXT_RGB = (0.85, 0.85, 0.85)
MUTED_RGB = (0.58, 0.59, 0.62)
GRID_RGBA = (1.0, 1.0, 1.0, 0.08)
CROSSHAIR_RGBA = (1.0, 1.0, 1.0, 0.35)
TOOLTIP_BG = (0.16, 0.17, 0.20)
TOOLTIP_BORDER = (0.32, 0.33, 0.37)


# -- pure helpers -----------------------------------------------------------


def compact_number(n: int) -> str:
    """950, 1.5k, 20k, 1.2M."""
    for divisor, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= divisor:
            value = n / divisor
            text = f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}"
            return text + suffix
    return str(n)


def nice_ticks(max_value: int) -> list[int]:
    """0 and round 1-2-5 steps up to the first one at or above `max_value`."""
    if max_value <= 0:
        return [0, 1]
    raw = max_value / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= raw)
    step = max(1, int(round(step)))
    return [i * step for i in range(math.ceil(max_value / step) + 1)]


def _month_starts(t0: datetime, t1: datetime) -> list[datetime]:
    out = []
    year, month = t0.year, t0.month
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        start = datetime(year, month, 1, tzinfo=t0.tzinfo)
        if start > t1:
            return out
        out.append(start)


def x_ticks(t0: datetime, t1: datetime) -> list[tuple[datetime, str]]:
    """Each 1 January in (t0, t1]; failing that, each first of the month."""
    years = [datetime(y, 1, 1, tzinfo=t0.tzinfo) for y in range(t0.year + 1, t1.year + 1)]
    if years:
        return [(d, str(d.year)) for d in years]
    return [(d, d.strftime("%b")) for d in _month_starts(t0, t1)]


def series_for(readings, faction_id: int) -> list[tuple[datetime, int]]:
    return [(r.simulated_at, dict(r.casualties).get(faction_id, 0)) for r in readings]


def nearest_reading(readings, x: float, width: float) -> int | None:
    """Index of the reading under pointer `x`, or None outside the plot."""
    x0, x1 = MARGIN_LEFT, width - MARGIN_RIGHT
    if not readings or x1 <= x0 or x < x0 or x > x1:
        return None
    t0 = readings[0].simulated_at
    span = (readings[-1].simulated_at - t0).total_seconds()
    if span <= 0:
        return len(readings) - 1
    target = t0 + timedelta(seconds=(x - x0) / (x1 - x0) * span)
    i = bisect.bisect_left(readings, target, key=lambda r: r.simulated_at)
    if i >= len(readings):
        return len(readings) - 1
    if i > 0 and target - readings[i - 1].simulated_at <= readings[i].simulated_at - target:
        return i - 1
    return i


def spread_labels(ys: list[float], min_gap: float) -> list[float]:
    """Push overlapping label positions down until each is `min_gap` apart."""
    out = list(ys)
    previous: float | None = None
    for i in sorted(range(len(ys)), key=lambda k: ys[k]):
        if previous is not None and out[i] < previous + min_gap:
            out[i] = previous + min_gap
        previous = out[i]
    return out


# -- rendering --------------------------------------------------------------


def _x_at(t: datetime, t0: datetime, span: float, x0: float, x1: float) -> float:
    if span <= 0:
        return x1
    return x0 + (t - t0).total_seconds() / span * (x1 - x0)


def _centred_text(cr, text: str, x: float, y: float) -> None:
    extents = cr.text_extents(text)
    cr.set_source_rgb(*MUTED_RGB)
    cr.move_to(x - extents.x_advance / 2, y)
    cr.show_text(text)


def _y_axis(cr, ticks: list[int], y_of, x0: float, x1: float) -> None:
    cr.set_line_width(1.0)
    for value in ticks:
        y = round(y_of(value)) + 0.5
        cr.set_source_rgba(*GRID_RGBA)
        cr.move_to(x0, y)
        cr.line_to(x1, y)
        cr.stroke()
        label = compact_number(value)
        cr.set_source_rgb(*MUTED_RGB)
        cr.move_to(x0 - 8 - cr.text_extents(label).x_advance, y + FONT_SIZE * 0.35)
        cr.show_text(label)


def _x_axis(cr, t0: datetime, t1: datetime, x_of, x0: float, x1: float, y1: float) -> None:
    ticks = x_ticks(t0, t1)
    if not ticks:
        return
    stride = max(1, math.ceil(len(ticks) * MIN_X_LABEL_SPACING / (x1 - x0)))
    cr.set_line_width(1.0)
    for moment, label in ticks[::stride]:
        x = round(x_of(moment)) + 0.5
        cr.set_source_rgba(*GRID_RGBA)
        cr.move_to(x, y1)
        cr.line_to(x, y1 + 4)
        cr.stroke()
        cr.set_source_rgb(*MUTED_RGB)
        cr.move_to(x - cr.text_extents(label).x_advance / 2, y1 + 4 + FONT_SIZE)
        cr.show_text(label)


def _direct_labels(cr, ends: list[tuple[FactionRow, float]], x1: float) -> None:
    ys = spread_labels([y for _, y in ends], LABEL_GAP)
    for (faction, _), y in zip(ends, ys):
        cr.set_source_rgb(*faction_rgb(faction.color_key))
        cr.set_line_width(LINE_WIDTH)
        cr.move_to(x1 + 6, y)
        cr.line_to(x1 + 16, y)
        cr.stroke()
        cr.set_source_rgb(*TEXT_RGB)
        cr.move_to(x1 + 20, y + FONT_SIZE * 0.35)
        cr.show_text(faction.name)


def _hover(cr, reading: CasualtyReading, shown, x: float, y0: float, y1: float, width: float) -> None:
    cr.set_source_rgba(*CROSSHAIR_RGBA)
    cr.set_line_width(1.0)
    cr.move_to(round(x) + 0.5, y0)
    cr.line_to(round(x) + 0.5, y1)
    cr.stroke()

    values = dict(reading.casualties)
    rows = sorted(shown, key=lambda f: (-values.get(f.id, 0), f.id))
    lines = [(None, reading.simulated_at.date().isoformat())] + [
        (f, f"{f.name}  {values.get(f.id, 0):,}") for f in rows
    ]
    line_h, pad, swatch = FONT_SIZE + 5, 6.0, 8.0
    box_w = max(cr.text_extents(text).x_advance for _, text in lines) + 2 * pad + swatch + 6
    box_h = len(lines) * line_h + 2 * pad
    bx = x + 10 if x + 10 + box_w <= width else x - 10 - box_w
    by = y0 + 4
    cr.set_source_rgb(*TOOLTIP_BG)
    cr.rectangle(bx, by, box_w, box_h)
    cr.fill_preserve()
    cr.set_source_rgb(*TOOLTIP_BORDER)
    cr.stroke()
    for k, (faction, text) in enumerate(lines):
        baseline = by + pad + (k + 1) * line_h - 5
        if faction is not None:
            cr.set_source_rgb(*faction_rgb(faction.color_key))
            cr.rectangle(bx + pad, baseline - swatch, swatch, swatch)
            cr.fill()
        cr.set_source_rgb(*TEXT_RGB)
        cr.move_to(bx + pad + swatch + 6, baseline)
        cr.show_text(text)


def render_casualty_chart(
    cr,
    readings,
    factions,
    visible: frozenset[int],
    width: float,
    height: float,
    hover_x: float | None = None,
) -> None:
    """Draw cumulative casualties of the `visible` factions into `width` x `height`."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    x0, x1 = MARGIN_LEFT, width - MARGIN_RIGHT
    y0, y1 = MARGIN_TOP, height - MARGIN_BOTTOM
    if x1 - x0 < 20 or y1 - y0 < 20:
        return
    cr.select_font_face("Sans")
    cr.set_font_size(FONT_SIZE)

    shown = [f for f in factions if f.id in visible]
    if not readings or not shown:
        cr.set_source_rgba(*GRID_RGBA)
        cr.set_line_width(1.0)
        cr.move_to(x0, round(y1) + 0.5)
        cr.line_to(x1, round(y1) + 0.5)
        cr.stroke()
        message = "No history yet" if not readings else "No faction selected"
        _centred_text(cr, message, (x0 + x1) / 2, (y0 + y1) / 2)
        return

    # Cumulative totals never fall, so the maximum is in the latest reading.
    latest = dict(readings[-1].casualties)
    ticks = nice_ticks(max(latest.get(f.id, 0) for f in shown))
    top = ticks[-1]

    def y_of(value: int) -> float:
        return y1 - value / top * (y1 - y0)

    t0, t1 = readings[0].simulated_at, readings[-1].simulated_at
    span = (t1 - t0).total_seconds()

    def x_of(moment: datetime) -> float:
        return _x_at(moment, t0, span, x0, x1)

    _y_axis(cr, ticks, y_of, x0, x1)
    _x_axis(cr, t0, t1, x_of, x0, x1, y1)

    # One reading per horizontal pixel is all the line can show.
    stride = max(1, len(readings) // max(1, int(x1 - x0)))
    sample = list(readings[::stride])
    if sample[-1] is not readings[-1]:
        sample.append(readings[-1])
    sample_values = [dict(r.casualties) for r in sample]
    xs = [x_of(r.simulated_at) for r in sample]

    cr.set_line_width(LINE_WIDTH)
    ends = []
    for faction in shown:
        cr.set_source_rgb(*faction_rgb(faction.color_key))
        for k, (x, values) in enumerate(zip(xs, sample_values)):
            y = y_of(values.get(faction.id, 0))
            if k == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        ends.append((faction, y_of(latest.get(faction.id, 0))))
    _direct_labels(cr, ends, x1)

    if hover_x is not None:
        index = nearest_reading(readings, hover_x, width)
        if index is not None:
            reading = readings[index]
            _hover(cr, reading, shown, x_of(reading.simulated_at), y0, y1, width)


# -- widget -----------------------------------------------------------------


class CasualtyChart(Gtk.DrawingArea):
    """Paints the newest readings and tracks the pointer for the hover readout."""

    def __init__(self) -> None:
        super().__init__()
        self._readings: tuple[CasualtyReading, ...] = ()
        self._factions: tuple[FactionRow, ...] = ()
        self.visible: frozenset[int] = frozenset()
        self._hover_x: float | None = None
        self.set_size_request(-1, 260)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._on_draw)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", self._on_leave)

    def set_data(self, readings, factions) -> None:
        self._readings = readings
        self._factions = factions
        self.queue_draw()

    def set_visible(self, visible: frozenset[int]) -> None:
        self.visible = visible
        self.queue_draw()

    def _on_motion(self, _widget, event) -> bool:
        self._hover_x = event.x
        self.queue_draw()
        return False

    def _on_leave(self, _widget, _event) -> bool:
        self._hover_x = None
        self.queue_draw()
        return False

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        render_casualty_chart(
            cr, self._readings, self._factions, self.visible,
            allocation.width, allocation.height, self._hover_x,
        )
        return False
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ui_chart.py -v` → all PASS.
Run: `.venv/bin/python -m pytest -q` → everything passes.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/chart.py tests/test_ui_chart.py
git commit -m "feat: cumulative casualty chart renderer and widget"
```

---

### Task 5: History tab and the Map/History notebook

**Files:**
- Modify: `src/endless_war/ui/panels.py` (`_event_line`, `event_log_lines`)
- Create: `src/endless_war/ui/history_tab.py`
- Modify: `src/endless_war/ui/app.py` (notebook; `self.history.set_view(view)` in `refresh`)
- Test: `tests/test_ui_panels.py` (append), `tests/test_ui_history_tab.py` (new), `tests/test_ui_app.py` (append)

**Interfaces:**
- Consumes: `WorldView.casualty_history`, `WorldView.event_log`, `WorldView.factions` (Task 3); `CasualtyChart` (Task 4).
- Produces:
  - `event_log_lines(view) -> list[str]`, every event newest first, same line format as `event_lines`.
  - `class HistoryTab(Gtk.Box)` with `set_view(view)`, `toggles: dict[int, Gtk.CheckButton]`, `chart: CasualtyChart`, `log: Gtk.Label`.
  - `WarRoom.notebook: Gtk.Notebook` with pages "Map" and "History"; `WarRoom.history: HistoryTab`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ui_panels.py` (it already has a `_view()` helper; if it builds from a fresh world, the log is empty, so build a ticked view here):

```python
from endless_war.app.snapshot import build_view as _build_view
from endless_war.config import load_config as _load_config
from endless_war.simulation.engine import SimulationEngine as _Engine
from endless_war.simulation.worldgen import generate_world as _generate_world
from endless_war.ui.panels import event_log_lines


def test_event_log_lines_are_every_event_newest_first() -> None:
    cfg = _load_config()
    world = _generate_world(seed=42, config=cfg)
    engine = _Engine(world, cfg)
    for _ in range(4 * 365):
        if len(world.events) > 20:
            break
        engine.tick()
    view = _build_view(world, cfg, bound_faction_id=None, speed="1x")
    lines = event_log_lines(view)
    assert len(lines) == len(view.event_log) > 20
    newest = view.event_log[-1]
    assert lines[0] == f"{newest.simulated_at.date().isoformat()}  {newest.title}: {newest.body}"
```

Create `tests/test_ui_history_tab.py`:

```python
import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs an X display")

import dataclasses  # noqa: E402

from endless_war.app.snapshot import build_view  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.simulation.engine import SimulationEngine  # noqa: E402
from endless_war.simulation.worldgen import generate_world  # noqa: E402
from endless_war.ui.history_tab import HistoryTab  # noqa: E402


def _view_with_events():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(4 * 365):
        if len(world.events) >= 2:
            break
        engine.tick()
    assert len(world.events) >= 2, "premise: at least two events"
    return engine, world, cfg, build_view(world, cfg, bound_faction_id=None, speed="1x")


def test_every_faction_gets_a_toggle_and_all_start_visible() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    assert sorted(tab.toggles) == [f.id for f in view.factions]
    assert all(button.get_active() for button in tab.toggles.values())
    assert tab.chart.visible == frozenset(f.id for f in view.factions)


def test_unticking_a_faction_hides_it_from_the_chart() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    tab.toggles[1].set_active(False)
    assert 1 not in tab.chart.visible
    tab.set_view(view)
    assert 1 not in tab.chart.visible, "a refresh must not re-tick a hidden faction"
    tab.toggles[1].set_active(True)
    assert 1 in tab.chart.visible


def test_a_faction_that_appears_later_gets_a_toggle_without_resetting_others() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(dataclasses.replace(view, factions=view.factions[:2]))
    tab.toggles[0].set_active(False)
    tab.set_view(view)
    assert sorted(tab.toggles) == [f.id for f in view.factions]
    assert not tab.toggles[0].get_active()
    assert 0 not in tab.chart.visible


def test_the_log_is_newest_first() -> None:
    *_, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    newest = view.event_log[-1]
    first = tab.log.get_text().splitlines()[0]
    assert newest.title in first and newest.body in first


def test_the_log_is_not_reset_when_no_new_event_arrived() -> None:
    # Re-setting a Label's text every 250 ms would throw away the reader's
    # scroll position, so the log only changes when the newest event does.
    engine, world, cfg, view = _view_with_events()
    tab = HistoryTab()
    tab.set_view(view)
    tab.log.set_text("sentinel")
    tab.set_view(view)
    assert tab.log.get_text() == "sentinel"
    for _ in range(4 * 365):
        if world.events[-1].id != view.event_log[-1].id:
            break
        engine.tick()
    tab.set_view(build_view(world, cfg, bound_faction_id=None, speed="1x"))
    assert tab.log.get_text() != "sentinel"
```

Append to `tests/test_ui_app.py`:

```python
def test_the_window_has_a_map_tab_and_a_history_tab() -> None:
    service, cfg = _service()
    room = WarRoom(service, cols=cfg["world"]["grid_cols"])
    try:
        pages = room.notebook.get_n_pages()
        labels = [room.notebook.get_tab_label_text(room.notebook.get_nth_page(i)) for i in range(pages)]
        assert labels == ["Map", "History"]
    finally:
        room.shutdown()


def test_toggling_a_faction_sends_no_command() -> None:
    from endless_war.app.snapshot import build_view
    from endless_war.simulation.engine import SimulationEngine

    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    SimulationEngine(world, cfg).run(40)
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")

    class RecordingService:
        def __init__(self) -> None:
            self.submitted = []

        def latest_view(self):
            return view

        def submit(self, command) -> None:
            self.submitted.append(command)

    service = RecordingService()
    room = WarRoom(service, cols=cfg["world"]["grid_cols"])
    try:
        room.refresh()
        room.history.toggles[0].set_active(False)
        room.history.toggles[0].set_active(True)
        assert service.submitted == []
    finally:
        room.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_panels.py tests/test_ui_history_tab.py tests/test_ui_app.py -v`
Expected: ImportError for `event_log_lines` and `endless_war.ui.history_tab`; `AttributeError: 'WarRoom' object has no attribute 'notebook'`.

- [ ] **Step 3: Implement**

In `src/endless_war/ui/panels.py`, replace `event_lines` with:

```python
def _event_line(event) -> str:
    return f"{event.simulated_at.date().isoformat()}  {event.title}: {event.body}"


def event_lines(view: WorldView) -> list[str]:
    """One line per recent event, oldest first."""
    return [_event_line(event) for event in view.recent_events]


def event_log_lines(view: WorldView) -> list[str]:
    """One line per logged event, newest first."""
    return [_event_line(event) for event in reversed(view.event_log)]
```

Create `src/endless_war/ui/history_tab.py`:

```python
"""The History tab: per-faction toggles, the casualty chart, the full log.

Toggling a faction changes only what the chart draws. It never reaches the
simulation, so it goes nowhere near `service.submit()`.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import WorldView  # noqa: E402
from endless_war.ui.chart import CasualtyChart  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.panels import event_log_lines  # noqa: E402

SWATCH_PX = 12


def _swatch(color_key: str) -> Gtk.DrawingArea:
    area = Gtk.DrawingArea()
    area.set_size_request(SWATCH_PX, SWATCH_PX)
    rgb = faction_rgb(color_key)

    def draw(_widget, cr) -> bool:
        cr.set_source_rgb(*rgb)
        cr.rectangle(0, 0, SWATCH_PX, SWATCH_PX)
        cr.fill()
        return False

    area.connect("draw", draw)
    return area


class HistoryTab(Gtk.Box):
    """Toggle row (which doubles as the legend), chart, then the event log."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.toggles: dict[int, Gtk.CheckButton] = {}
        self._visible: set[int] = set()
        self._newest_event_id: int | None = None

        self._toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.pack_start(self._toggle_row, False, False, 0)

        self.chart = CasualtyChart()
        self.pack_start(self.chart, False, False, 0)

        self.log = Gtk.Label(label="")
        self.log.set_xalign(0.0)
        self.log.set_yalign(0.0)
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.log)
        self.pack_start(scroller, True, True, 0)

    def set_view(self, view: WorldView) -> None:
        for faction in view.factions:
            if faction.id not in self.toggles:
                self._add_toggle(faction.id, faction.name, faction.color_key)
        self.chart.set_data(view.casualty_history, view.factions)
        self.chart.set_visible(frozenset(self._visible))
        newest = view.event_log[-1].id if view.event_log else None
        if newest != self._newest_event_id:
            self._newest_event_id = newest
            self.log.set_text("\n".join(event_log_lines(view)))

    def _add_toggle(self, faction_id: int, name: str, color_key: str) -> None:
        button = Gtk.CheckButton()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(_swatch(color_key), False, False, 0)
        content.pack_start(Gtk.Label(label=name), False, False, 0)
        button.add(content)
        button.set_active(True)
        self._visible.add(faction_id)
        button.connect("toggled", self._on_toggled, faction_id)
        button.show_all()
        self._toggle_row.pack_start(button, False, False, 0)
        self.toggles[faction_id] = button

    def _on_toggled(self, button: Gtk.CheckButton, faction_id: int) -> None:
        if button.get_active():
            self._visible.add(faction_id)
        else:
            self._visible.discard(faction_id)
        self.chart.set_visible(frozenset(self._visible))
```

In `src/endless_war/ui/app.py`:

1. Add the import next to the other `endless_war.ui` imports:

```python
from endless_war.ui.history_tab import HistoryTab  # noqa: E402
```

2. Replace these lines of `WarRoom.__init__`:

```python
        outer.pack_start(middle, True, True, 0)

        self.events = Gtk.Label(label="")
        self.events.set_xalign(0.0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_size_request(-1, 120)
        scroller.add(self.events)
        outer.pack_start(scroller, False, False, 0)
```

with:

```python
        map_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        map_page.pack_start(middle, True, True, 0)

        self.events = Gtk.Label(label="")
        self.events.set_xalign(0.0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_size_request(-1, 120)
        scroller.add(self.events)
        map_page.pack_start(scroller, False, False, 0)

        self.history = HistoryTab()
        self.notebook = Gtk.Notebook()
        self.notebook.append_page(map_page, Gtk.Label(label="Map"))
        self.notebook.append_page(self.history, Gtk.Label(label="History"))
        outer.pack_start(self.notebook, True, True, 0)
```

3. In `refresh()`, directly after `self.legend.set_view(view)`:

```python
        self.history.set_view(view)
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest -q`
Expected: everything passes, including the earlier `WarRoom` tests (focus, sticky fault, newest-first strip).

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/panels.py src/endless_war/ui/history_tab.py src/endless_war/ui/app.py tests/test_ui_panels.py tests/test_ui_history_tab.py tests/test_ui_app.py
git commit -m "feat: Map and History tabs with toggleable casualty chart and full log"
```

---

### Task 6: Launch it, look at it, document it

**Files:**
- Modify: `README.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/game-logic.md`

**Interfaces:**
- Consumes: everything.
- Produces: nothing executable.

- [ ] **Step 1: Launch and look**

```bash
bin/run_gui.sh --faction 0 --speed 16x &
```

Let it run for ~90 seconds (about a simulated year at 16x). Capture both tabs. `import -window "Endless War" <file>` works on this machine, and root-window capture comes back blank. To show the History tab without a mouse, launch a second copy from a Python snippet that builds `WarRoom` exactly as `main()` does, then calls `room.notebook.set_current_page(1)`.

Answer, from what you actually see:
- Does the map show the new colours, with the legend matching?
- Does the chart grow as the date advances, one line per faction, each labelled at its end?
- Do the y-axis labels read like `20k`, and do the x-axis labels read as years or months?
- Do the direct labels ever overlap or run off the right edge?
- Does unticking a faction remove its line and rescale the axis?
- Does the log start with the newest event, and does it keep its scroll position between refreshes?

Fix only what is genuinely broken, with a regression test for each fix, and report anything left as is.

Stop the instance by PID: `kill $(ps -eo pid,args | awk '/[p]ython3 -m endless_war.ui.app/{print $1}')`. Never use `pkill -f` inside a compound command, because it matches its own shell.

- [ ] **Step 2: Update the docs**

`README.md`, in "Running it", after the sentence ending "keeps running in the tray when you close it:", add a sentence: "A History tab charts each faction's cumulative dead over time (tick factions on and off to compare) above the full event log."

`docs/architecture.md`: in the `ui/` section, change the first sentence so that it describes the window as two tabs (`Gtk.Notebook`): Map (map, status, legend, recent events) and History (`history_tab.py`: per-faction toggles, the cairo casualty chart in `chart.py`, the full event log). In the "Everything worth testing is a pure function" paragraph, add `chart.py`'s helpers and `render_casualty_chart`. In "Suggested tick pipeline", item 11 becomes "event generation and the daily casualty reading (`systems/history.py`)".

`docs/game-logic.md`: after the "## 10. Events" section, add:

```markdown
## 11. Casualty history — `systems/history.py`

At the end of every tick whose simulated date is later than the last reading's,
one `CasualtyReading` is appended: the date and time, and every faction's
cumulative casualties, sorted by id. The cadence is by date, not by tick count,
so a day-sized catch-up tick still records exactly one reading per day. Readings
are frozen and kept forever (about 36,500 in a century). The History tab draws them.
```

`docs/decisions.md`: append a dated entry in the file's template:

```markdown
## 2026-09-24 — History tab: casualties recorded in the simulation, cumulative, validated palette

**Decision:**
The casualty series is recorded by the simulation (`systems/history.py`, one frozen reading per simulated date, kept in `WorldState`) rather than sampled by the window. The chart plots cumulative totals. The factions were recoloured to the dataviz reference palette's dark steps (blue, orange, teal, gold, pink). `build_view` reuses the previous view's event lines.

**Reason:**
- A series recorded in world state is saved by persistence (sub-project B) with no extra work, so a loaded game keeps its history; a window-side sample would belong to one window and vanish on restart.
- Cumulative totals only rise, read at a glance, and compare factions directly; the user chose it over deaths-per-month.
- The old palette failed the validator on the map background (#1c1f24): violet vs blue at normal-vision ΔE 11.6 (floor 15) and colour-blind ΔE 3.7; amber outside the lightness band. The new five pass every check for line charts.
- Converting a full 2000-event log to view lines measured 1.5 ms per snapshot against a 1 ms budget; ids are consecutive and the log evicts only from the left, so the previous tuple can be sliced and only new events converted.

**Alternatives considered:**
- *Sample in the window.* Rejected for the persistence reason above.
- *Keep the old colours and rely on labels.* Rejected: violet/blue is hard to tell apart even with full colour vision, on the map as much as the chart.
- *Rebuild the event log every snapshot.* Rejected on the measurement above.

**Consequences:**
- No five colours can pass all-pairs colour-blind separation (the reference palette validates only its first three). On the map the legend and the bound-faction outline are the secondary encoding; on the chart, the direct labels.
- `build_view(previous=...)` must be given a view of the same world; only `SimulationService` passes it.
- Readings are never downsampled. A century is ~36,500 readings; the chart strokes at most one per horizontal pixel.
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass. Report the count.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/architecture.md docs/decisions.md docs/game-logic.md
git commit -m "docs: record the History tab"
```
