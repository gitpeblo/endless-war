# Application service layer — live clock, snapshots, commands

Date: 2026-09-23
Status: approved, ready for an implementation plan
Phase: 6 (Desktop shell), sub-project A of four

## Why this exists

The headless simulation core is merged: 96 provinces, five AI factions, a
deterministic tick pipeline, and a ten-year checkpoint that produces readable
history in about six seconds (`docs/decisions.md`, 2026-09-23). Nothing yet
drives `engine.tick()` except a `for` loop inside the observatory, and nothing
can observe the world while it runs.

A graphical shell is the first consumer that needs both: a simulation advancing
on wall-clock time in the background, and a safe way to look at it from another
thread. This document specifies that machinery. It contains no GTK code.

## Phase 6 decomposition

`specs/02-ui-and-tray.md` describes eight tabs, a seven-field tray summary,
seven tray actions, a strategic map and a notification system. That is several
projects. Phase 6 is therefore built as four sub-projects, each with its own
spec, plan and implementation cycle:

| | Sub-project | Delivers |
|---|---|---|
| **A** | **Application service layer** | **This document.** Live clock, background thread, immutable snapshots, command queue. |
| C | GTK shell | Main window, strategic map, Ayatana tray indicator, pause/speed/quit. `Save` present but disabled. |
| B | Persistence (roadmap Phase 5) | SQLite schema, save/load, offline catch-up across restarts. Enables `Save`. |
| D | Remaining views | Fronts, Faction Overview, Economy, Military, History, Policies, Settings; notification system. |

Build order is A → C → B → D: the shell is brought forward ahead of persistence
so the simulation becomes visible one plan sooner. The `Save` menu item exists
from C but is disabled until B lands, which is honest about what works.

Decisions taken during design, recorded so they are not re-litigated:

- **Optional faction binding, observe-only.** The shell may be launched bound to
  a faction or unbound. Bound, the status panel and tray summary describe that
  faction; unbound, they describe the world. Neither mode offers control levers
  — the player's actual strategy inputs are roadmap Phase 7. This satisfies the
  tray summary in `specs/02-ui-and-tray.md` while honouring the architectural
  requirement that the simulation stay valid with no player selected.
- **Purpose-built frozen view model**, not a deep copy of `WorldState` and not
  shared state under a lock. See "Why not the alternatives" below.

## Scope of sub-project A

In scope:

1. A view model: immutable dataclasses describing what a view needs.
2. A snapshot builder turning `WorldState` into that view model.
3. A simulation service owning the engine, a background thread, a wall-clock
   tick schedule, a command queue and a latest-wins snapshot slot.
4. Headless tests for all of the above, including a determinism equivalence
   test.

Out of scope, explicitly: any GTK or tray code; persistence of any kind; offline
catch-up across process restarts; player control over the simulation beyond
pausing and speed; the notification system.

## Architecture

One new package, `src/endless_war/app/`, sitting between `simulation/` and the
future `ui/`, consistent with the layer order in `docs/architecture.md`. The
dependency direction is one-way: `app/` imports `domain` and `simulation`;
nothing in `domain/`, `simulation/` or `ai/` may import `app/`.

| Unit | Responsibility | Depends on |
|---|---|---|
| `app/view_model.py` | Frozen dataclasses: `WorldView` and its parts `ProvinceCell`, `FactionRow`, `EventLine`. Pure data, no behaviour, no simulation imports beyond types. | `domain` |
| `app/snapshot.py` | `build_view(world, bound_faction_id) -> WorldView`. The single place where simulation state becomes view data. | `domain`, `view_model` |
| `app/service.py` | `SimulationService`: owns engine and thread, runs the clock, applies commands at tick boundaries, publishes snapshots. | `simulation`, `snapshot` |
| `app/commands.py` | The command types the service accepts. | — |

### Public interface

The GTK shell consumes exactly three members of `SimulationService`:

```python
service.start()                   # spawn the simulation thread
service.latest_view() -> WorldView | None   # never blocks, never mutates
service.submit(command) -> None   # enqueue; applied at the next tick boundary
```

`stop()` exists for tests and shutdown. Everything else is private. A view that
needs data the `WorldView` does not carry extends the view model explicitly —
views never reach past this interface into `WorldState`.

### View model shape

`WorldView` carries: the simulated date, tick count, current speed, a faulted
flag, the bound faction id (or `None`), a `ProvinceCell` per province, a
`FactionRow` per faction, the most recent `EventLine`s, and active/total war
counts. `ProvinceCell` carries what the map must communicate per
`specs/02-ui-and-tray.md` — controller, owner, contested state, whether armies
are present, capital status and a supply-problem flag — as plain values, not
object references.

The event list in a view is bounded: a view carries a recent window, not the
whole 2000-entry log, so snapshot cost stays flat over a long run.

## Data flow

The simulation thread runs one loop:

1. Is a tick due, given the current speed and the last tick's timestamp?
2. If so, drain the command queue and apply each command.
3. `engine.tick()`.
4. `build_view(...)` and publish it to the slot.
5. Sleep briefly and repeat.

The slot is latest-wins: publishing overwrites whatever is unread. A UI
redrawing on a 250 ms timer therefore never falls behind a simulation running at
16×, and no unbounded queue of stale snapshots can accumulate.

Commands are applied only between ticks, never during one. The command set is
`Pause`, `Resume`, `SetSpeed(multiplier)`, `BindFaction(id | None)` and
`Shutdown`. Speeds are paused, 1×, 4× and 16×, where 1× is `live_tick_seconds`
from `config/default.toml`.

### Determinism

This is the load-bearing property of the whole design, and the project's hardest
constraint (`CLAUDE.md`: same initial state + seed + commands reproduce the same
history).

No command in the set above touches world state. Wall-clock time decides only
*when* a tick happens, never *what* it does. Consequently a world run for N
ticks produces byte-identical state whether those ticks were spread over an hour
at 1×, taken in a burst at 16×, or interrupted by a pause. A regression test
asserts exactly this by comparing a paused-and-resumed run against a
straight-through run at the same tick count.

Missed wall-clock time is capped: on each wake the service performs at most
`max_catchup_ticks_per_wake` ticks rather than working off an unbounded backlog,
so a laptop resuming from sleep does not freeze the UI while it simulates a
week. That key is new and belongs in `config/default.toml` under `[simulation]`,
per the rule that tunable numbers do not live in code.
True offline catch-up across process restarts requires knowing when the process
last stopped, which requires persistence, and belongs to sub-project B.

## Error handling

If `engine.tick()` raises, the service stops ticking, retains the exception, and
publishes a view with its faulted flag set. It does not exit the process, does
not die silently, and does not take a future UI down with it. The shell will
render this as a banner; at this stage it is simply an observable state that a
test asserts.

`latest_view()` returning `None` before the first tick is a legitimate state
that consumers must handle, not an error.

## Testing

All tests are headless; nothing here needs a display.

- Command application happens at tick boundaries, never mid-tick.
- Latest-wins publishing: a slow reader sees the newest snapshot, never a queue
  of stale ones.
- **Determinism equivalence:** paused/resumed and speed-changed runs produce
  state identical to a straight-through run of the same tick count.
- Snapshot construction, bound and unbound, including that a `WorldView` holds
  no reference reachable back into `WorldState`.
- Bounded event window: a long run does not grow snapshot size.
- Clean shutdown: `stop()` leaves no thread running.
- A raised tick surfaces as a faulted view rather than a silent stall.
- A short real-time smoke test: the service started at 16× advances its clock.

Fixture discipline applies as elsewhere in this repo: any test selecting a
faction or province asserts the premise it relies on, rather than assuming
properties of the seed-42 map (`docs/decisions.md`; five tasks on the previous
branch shipped fixtures that assumed false things about it).

## Why not the alternatives

**Deep-copying `WorldState` each tick** was rejected: it lets view code depend on
simulation internals, so the one-way layer rule would hold only by convention,
and copy cost grows with the event log.

**Shared state under a lock** was rejected: the UI thread could stall the
simulation, a missed lock is a race that manifests as a rare wrong pixel, and
nothing structurally prevents a UI handler from writing to world state — which
`docs/architecture.md` forbids outright.

The frozen view model costs one bounded build per tick and makes both failure
modes impossible by construction.
