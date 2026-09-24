# GTK shell — window, strategic map, tray

Date: 2026-09-23
Status: approved in conversation, ready for an implementation plan
Phase: 6 (Desktop shell), sub-project C of four

## Why this exists

`docs/superpowers/specs/2026-09-23-app-service-layer-design.md` decomposed Phase 6
into four sub-projects and set their order: **A → C → B → D**. Sub-project A is
merged — the simulation now runs on a live wall-clock in a background thread and
publishes immutable `WorldView` snapshots through `SimulationService`. This
document specifies **C**: the first thing a person can actually look at.

The point of C is a window that shows a war happening and a tray icon that keeps
it out of the way. Nothing in it decides anything about the simulation.

## Verified environment

Checked on this machine before writing this document, rather than assumed:

- GTK 3.24 imports and a window realizes, draws through cairo, and exits cleanly.
- `AyatanaAppIndicator3 0.1` imports (the Ayatana fork, not the legacy
  `AppIndicator3`, which is absent on Ubuntu 24.04).
- Session is MATE on `DISPLAY=:0.0`.
- The venv at `.venv/` was created with `--system-site-packages`, so it sees
  PyGObject, which is a distribution package and invisible to a plain venv.

## Scope

In scope:

1. A main window: strategic map, status panel, event feed, and a header with the
   simulated date and speed controls.
2. A cairo-drawn province map on a 12×8 grid.
3. An Ayatana tray indicator with a summary and a menu; closing the window hides
   to tray rather than exiting.
4. Optional faction binding via a command-line flag.
5. A launcher script, and tests for everything that can be tested without a
   display.

Out of scope, explicitly: the seven other tabs from `docs/superpowers/specs/02-ui-and-tray.md`
(sub-project D); the notification system (D); persistence and a working Save
(sub-project B); any player control over the simulation beyond pause and speed
(roadmap Phase 7); map polish beyond flat rectangles — `docs/superpowers/specs/02-ui-and-tray.md`
says a first prototype may use a grid and warns against delaying on graphics.

## Architecture

One new package, `src/endless_war/ui/`. The layer rule from
`docs/architecture.md` is absolute here: `ui/` imports `app/`; it must never
import `simulation/`, `domain/` or `ai/`, and nothing may import `ui/`.

| Unit | Responsibility |
|---|---|
| `ui/colors.py` | `color_key` → RGB, plus the derived tints the map needs. Pure. |
| `ui/geometry.py` | Province id ↔ grid cell ↔ pixel rectangle, for a given widget size. Pure. |
| `ui/map_view.py` | A `Gtk.DrawingArea` that renders a `WorldView` using the two modules above. |
| `ui/panels.py` | `WorldView` → the text rows the status panel and event feed display. The formatting functions are pure; the widgets are a thin shell. |
| `ui/tray.py` | The Ayatana indicator, its menu, and the one-line summary text. |
| `ui/app.py` | The window, the 250 ms refresh timer, and the wiring to `SimulationService`. |

### How the UI talks to the simulation

The only contact surface is three calls on `SimulationService`:

```python
service.latest_view()      # read, on a GLib timer
service.submit(command)    # write, from a button or menu item
service.start() / stop()   # lifecycle, at app startup and shutdown
```

A `GLib.timeout_add(250, ...)` callback pulls the newest `WorldView` and updates
the widgets. There is no other path. UI code holds no reference to `WorldState`,
so a handler cannot mutate simulation state even by mistake — the frozen view
model makes it a type error rather than a convention.

Redraw is unconditional on each timer tick at this stage: 96 rectangles is
nothing, and skipping redraws when the view is unchanged is an optimisation to
make when a profile says so.

### The map

`row, col = divmod(province_id, grid_cols)` — verified against
`worldgen.generate_province_grid`, which builds ids as `row * cols + col`. With
the shipped config that is 96 provinces in 12 columns by 8 rows.

Each cell is a filled rectangle in its controller's colour. On top of that:

- **contested** (`ProvinceCell.is_contested`): a diagonal hatch over the fill.
- **capital** (`is_capital`): a small diamond.
- **armies present** (`has_armies`): a dot.
- **supply problem** (`has_supply_problem`): the fill darkened.
- **bound faction**: a brighter outline around every province it controls.

Colour keys in play are `red`, `blue`, `green`, `amber`, `violet`, with `grey` as
the fallback for an unknown or absent controller.

### The tray

An `AyatanaAppIndicator3.Indicator` with a menu: Open War Room, Pause/Resume,
Speed (1× / 4× / 16×), Save, Quit. **Save is present but disabled** until
sub-project B lands persistence — a visibly greyed item is honest about what
exists, where hiding it would misrepresent the roadmap.

Closing the window hides it to the tray; the simulation keeps running. Quit stops
the service and exits.

## Testing

GTK widgets are awkward to test and this design does not pretend otherwise. The
response is to keep the logic out of the widgets:

- `colors.py` and `geometry.py` are pure and get ordinary unit tests, including
  that every colour key worldgen emits has a mapping, and that the grid maths
  round-trips for every province id at several widget sizes.
- `panels.py`'s formatting functions take a `WorldView` and return strings/rows;
  tested against a view built by the real `build_view`, not a mock.
- `tray.py`'s summary text is a pure function of a `WorldView`; tested the same
  way.
- The widget layer gets one smoke test that constructs the window, runs a few
  main-loop iterations against a real `SimulationService`, and tears down —
  **skipped automatically when `DISPLAY` is unset**, so the suite stays green on
  a headless machine.

A cairo rendering pass is also exercised headlessly by drawing onto an
`ImageSurface` and asserting the centre pixel of a known province carries its
controller's colour. That catches a broken render without needing a window.

## Manual verification before this is called done

Launch it against a live service, watch the map change colour as provinces change
hands, confirm pause actually freezes it and that speed changes visibly alter the
rate, and confirm closing the window leaves the tray icon with the simulation
still running.

## Why not the alternatives

**Polling on a GLib timer** rather than pushing from the simulation thread: GTK is
not thread-safe, so a push would have to hop threads via `GLib.idle_add` anyway,
and the service's slot is already latest-wins. Polling is simpler and cannot
queue up stale frames.

**Flat rectangles** rather than province polygons: `docs/superpowers/specs/02-ui-and-tray.md`
explicitly permits a grid for the first prototype and warns against delaying the
simulation for map graphics. Polygons need a map generator that does not exist.
