# Technical Architecture

## Principle
The simulation engine must not depend on GTK or tray code.

The application should be divided into:

1. **Domain model** — pure state objects.
2. **Simulation systems** — deterministic state transitions.
3. **AI systems** — generate strategic decisions.
4. **Persistence** — SQLite and save metadata.
5. **Application services** — background simulation thread, live clock, command queue, and immutable view snapshots.
6. **UI** — GTK views and tray integration.

## Application services layer

`src/endless_war/app/` owns the `SimulationService`: a daemon thread that advances the engine on a live wall-clock schedule, publishes immutable `WorldView` snapshots to a lock-protected reader, and accepts commands (pause, resume, speed change, faction binding, shutdown) that are applied only at tick boundaries — never during world state mutation. Commands applied at tick boundaries preserves determinism: a paused, resumed, or sped-up run reproduces byte-for-byte the same history as a straight-through run of equivalent length and seed.

The frozen view model (`WorldView`, `ProvinceCell`, `FactionRow`, `EventLine`) is built fresh from world state after every tick. A consumer sees a plain-value snapshot, never a live simulation object, so the GTK thread may read a view while the simulation thread mutates state, without a lock and without risk of a UI handler reaching back into the world.

Speeds are `paused`, `1x` (from `config/default.toml`'s `live_tick_seconds`), `4x`, `16x`, `32x` and `64x`; `clock.RUNNING_SPEEDS` is the list the window's buttons and the tray's Speed menu offer. Catch-up when the service wakes from a stall is capped at `max_catchup_ticks_per_wake`; this prevents the world from simulating a week at once on a laptop wake.

A tick that raises, or a command that fails to apply, sets a fault message and publishes a view flagged as faulted; a faulted service stops ticking and cannot recover within the process lifetime. Offline catch-up across restarts is not provided by this layer — it requires knowledge of when the process last stopped, which is a persistence-layer responsibility.

**Import rule:** `app/` imports `simulation` and `domain`; nothing in `domain/`, `simulation/`, or `ai/` imports `app/`.

## Suggested tick pipeline

For each strategic tick:

1. advance time
2. update economy/production
3. update manpower/recruitment
4. calculate supply
5. AI strategic decisions
6. movement
7. battles
8. occupation/control changes
9. morale/exhaustion/stability
10. diplomacy/war termination checks
11. event generation and the daily casualty reading (`systems/history.py`)
12. persistence checkpoint when due

## UI stack
GTK 3 through PyGObject (`gi`), with `AyatanaAppIndicator3` for the MATE tray. Decision and verified package versions: `decisions.md` (2026-09-22).

Practical notes:

- Always call `gi.require_version("Gtk", "3.0")` / `gi.require_version("AyatanaAppIndicator3", "0.1")` before importing from `gi.repository`.
- Use `AyatanaAppIndicator3`, not the legacy `AppIndicator3` — the latter is not installed on Ubuntu 24.04.
- Nothing needs installing on the current machine, but PyGObject is a system dist-package: a virtualenv needs `--system-site-packages` to see it.

### The `ui/` package

`src/endless_war/ui/` is the War Room: a GTK 3 window (`app.py`) with two tabs in a `Gtk.Notebook`, and an Ayatana tray indicator (`tray.py`). **Map** holds the cairo-drawn province map (`map_view.py`): an isometric board (`iso.py`: positions, back-to-front order, integer fit-to-window scale) whose terrain tiles come from a CC0 sheet in `ui/assets/`, darkened once at load (`terrain.py`), with each province washed in its controller's colour. The scroll wheel zooms in whole-scale steps around the cursor and a middle-button drag pans (`iso.Camera`, `zoom_at`, `pan_by`); that is widget state only; a legend drawn with the map's own cell painters (`legend.py`), a status panel and the recent-events strip. **History** (`history_tab.py`) holds per-faction toggles that double as the legend, the cairo casualty chart (`chart.py`) and the full event log, newest first. Toggles only change what the chart draws; they never submit a command. A `GLib.timeout_add` timer on the GTK thread pulls `SimulationService.latest_view()` every 250 ms and repaints; buttons and tray items only `submit()` commands. No widget method is ever called from the simulation thread, and the timer callback has an exception boundary, because GLib silently drops a timeout source whose callback raises; a caught failure stays in the header as `UI FAULT: …`.

Everything worth testing is a pure function with no display: `colors.py`, `geometry.py` (grid shape), `iso.py` (board geometry and province id ↔ screen point), `terrain.py` (terrain → tile, darkening), `panels.py` (text formatting), `chart.py`'s helpers (`nice_ticks`, `compact_number`, `x_ticks`, `nearest_reading`, `spread_labels`), and the `render_map` / `render_legend` / `render_casualty_chart` functions, which draw on any cairo context. The widgets are a thin shell around them.

**Import rule:** `ui/` imports `app/` and `endless_war.config` (a leaf module with no project imports) and nothing else from the project. `ui/app.py`'s `main()` imports `generate_world` locally so the module-scope import graph stays UI-only.

## Determinism
All random decisions should use a seeded RNG owned by simulation state or simulation context.

Given identical initial state, seed, and commands, the simulation should reproduce the same outcome.

This simplifies debugging and automated tests.

## Time model
Recommended initial scale:

- one simulation tick = 6 simulated hours
- four ticks = one simulated day

Live speed can process ticks at configurable wall-clock intervals.

Offline catch-up can process day-sized aggregate ticks if needed.

## Concurrency
For the first implementation, prefer a single simulation thread/process and communicate with the GTK UI through safe scheduled callbacks or message queues.

Avoid mutating simulation state directly from UI event handlers.
