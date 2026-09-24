# History tab — casualty time series, full event log, validated faction colours

Date: 2026-09-24
Status: approved in conversation, ready for an implementation plan
Phase: 6, pulled forward from sub-project D at the user's request

## Why this exists

The War Room (sub-project C, merged) has one view: the map. The user asked for
two tabs, **Map** and **History**, with the History tab opening on "the time
series of the death toll, toggleable per faction". `docs/superpowers/specs/02-ui-and-tray.md`
lists History as tab 6 of 8; the other six tabs stay in sub-project D.

Nothing in the simulation keeps a history today. `Faction.casualties` is a
single running total, so the series has to be recorded before it can be drawn.

## Decisions made in conversation

| Question | Answer |
|---|---|
| What the chart plots | **Cumulative** dead per faction since the start. Lines only rise. |
| What else is on the History tab | The **complete event log** below the chart, newest first. The Map tab keeps its short recent-events strip. |
| Faction colours | Switch to a **validated palette** on both map and chart (see Colours). |
| Where the series is recorded | **In the simulation**, as world state, so persistence (sub-project B) saves it with no extra work. |

## Scope

In:

1. A history recorder in the simulation and the world-state field it fills.
2. Two new `WorldView` fields: the casualty series and the full event log.
3. A `Gtk.Notebook` with **Map** and **History** tabs.
4. The casualty chart: pure cairo renderer, per-faction toggles, hover readout.
5. The full event log on the History tab.
6. The new faction palette.

Out: the other six tabs, a deaths-per-month view, a table view of the series,
notifications, persistence. The occupation-at-peace change is a separate spec.

## 1. Recording the series (simulation)

New system `src/endless_war/simulation/systems/history.py`:

```python
def record_history(world: WorldState) -> None:
    """Append one casualty reading when the simulated date has moved on."""
```

- **When:** at the end of `SimulationEngine.tick()`, after `record_events`. It
  is part of step 11 (event generation) of the fixed pipeline; nothing is
  reordered.
- **Cadence is by date, not by tick count.** A reading is appended whenever
  `world.current_time.date()` is later than the last reading's date, or when
  there is no reading yet. `tick(hours=...)` may run longer ticks (offline
  catch-up can use day-sized ticks), so "every 4 ticks" would be wrong.
- **Shape:** `WorldState.casualty_history: list[CasualtyReading]`, where

  ```python
  @dataclass(frozen=True, slots=True)
  class CasualtyReading:
      simulated_at: datetime
      casualties: tuple[tuple[int, int], ...]   # (faction_id, cumulative), sorted by id
  ```

  Frozen and made of tuples, so a snapshot can share the readings instead of
  copying them.
- **No randomness, no reading of anything but the clock and faction totals.**
  Same seed and commands, same series.
- **Retention:** every daily reading, forever. A 100-year game is ~36,500
  readings of five integers each. No downsampling until a run shows a need.

## 2. The view model

`WorldView` gains:

- `casualty_history: tuple[CasualtyReading, ...]`: `tuple(world.casualty_history)`.
  The readings are immutable, so this is a pointer copy.
- `event_log: tuple[EventLine, ...]`: every event in `world.events` (capped at
  2000 by `systems/events.py`), oldest first like `recent_events`. The UI shows
  it reversed.

`CasualtyReading` lives in `domain/models.py`, next to the world state that
holds it. `app/view_model.py` re-exports it, so `ui/` keeps importing only
from `app/`.

**Performance budget.** Measured before this change, after 5 simulated years at
seed 42: `build_view` 0.19 ms, `tick` 0.32 ms, and the 10-year CLI run 4.7 s.
After the change, with a full 2000-event log and 10 years of readings,
`build_view` must stay **under 1 ms** and the 10-year run under 5.5 s. If the
event log breaks the budget, `build_view` caches `EventLine`s by event id,
since events are never edited after they are appended.

## 3. Window structure

```
+-----------------------------------------------------------+
| 2031-03-02 · 16x                     [1x][4x][16x][Pause] |  shared header
+-----------------------------------------------------------+
| [ Map ][ History ]                                        |  Gtk.Notebook
+-----------------------------------------------------------+
```

- **Map tab:** exactly today's content: map, status panel, legend, and the
  short event strip.
- **History tab:** the faction toggle row, the chart, then the full event log in
  a scroller that fills the rest.
- The header, speed buttons and focus handling (`WarRoom.show()`) are unchanged
  and sit above the notebook.
- `WarRoom.refresh()` updates both tabs from the same view. A hidden tab may skip
  redrawing (GTK does not draw unmapped widgets), but its data is set every
  refresh so switching tabs never shows stale content.

## 4. The casualty chart

### Toggles and legend

A row of `Gtk.CheckButton`s, one per faction, each showing a colour swatch and
the faction name. That makes the row the legend as well, so identity never rests
on colour alone. All are on at start. Toggle state is **UI-only**: it never
calls `service.submit()`. The checkbuttons can take keyboard focus, and
`WarRoom.show()` still clears focus on present, so a stray key cannot toggle one.

### Rendering

A pure function, like `render_map`:

```python
def render_casualty_chart(
    cr, readings, factions, visible: frozenset[int],
    width: float, height: float, hover_x: float | None = None,
) -> None
```

- **One y-axis**, from 0 to a "nice" maximum over the *visible* factions only.
  Hiding a faction rescales the axis. It never repaints the others: colour
  follows the faction, not its position in the visible set.
- Tick labels in compact form (`0`, `20k`, `40k`, `1.2M`) in secondary text
  colour, never in a series colour. Gridlines faint; no chart border.
- **x-axis** spans the first reading to the latest; ticks at each 1 January
  (year labels). If less than a year is shown, ticks fall on the first of each month.
- **2 px lines**, one per visible faction, in the faction's colour.
- **Direct label** at each line's right end, the faction name in text colour
  beside a short stroke of its colour. When two labels would overlap, they are
  pushed apart vertically.
- **Empty states:** no readings yet, or no faction toggled on, draws the axes
  and a centred muted message ("No history yet" / "No faction selected")
  instead of failing.

### Hover

Pointer motion over the chart sets `hover_x` and queues a redraw. The renderer
draws a vertical crosshair at the nearest reading and a tooltip box listing the
date and each visible faction's total, largest first. Leaving the chart clears
it. The nearest-reading lookup is its own pure function.

### Pure helpers (testable with no display)

- `nice_ticks(max_value) -> list[int]`: 0 plus 3–6 round steps covering the max.
- `compact_number(n) -> str`: `950`, `20k`, `1.2M`.
- `series_for(readings, faction_id) -> list[tuple[datetime, int]]`.
- `nearest_reading(readings, x, width) -> int | None`: index under the pointer.
- `spread_labels(ys, min_gap) -> list[float]`: de-overlapped label positions.

These live in `src/endless_war/ui/chart.py` with the renderer and the
`CasualtyChart(Gtk.DrawingArea)` widget.

## 5. Full event log

A `Gtk.Label` in a `Gtk.ScrolledWindow`, filled from `view.event_log` reversed
(newest first), one line per event in the same format as the map tab's strip
(`panels.event_lines`). The text is only re-set when the newest event id
changes, so the scroll position is not thrown away every 250 ms.

## 6. Colours

The current five fail the palette validator on the dark map background
(`#1c1f24`): violet vs blue is below the normal-vision floor (ΔE 11.6 < 15), and
amber is outside the lightness band. The replacement is the dataviz reference
palette's dark steps, first five slots, which pass every check on that
surface for line charts:

| Faction (seed 42) | key | hex |
|---|---|---|
| 0 Valdran Hegemony | `blue` | `#3987e5` |
| 1 Korsk Federation | `orange` | `#d95926` |
| 2 Meridian Compact | `teal` | `#199e70` |
| 3 Astaran Dominion | `gold` | `#c98500` |
| 4 Free Cities League | `pink` | `#d55181` |

- `worldgen.FACTION_COLORS` becomes `["blue", "orange", "teal", "gold", "pink"]`,
  so the key names say what the colour is. `color_key` is cosmetic and never
  touches the RNG, so the simulated history is unchanged; the determinism tests
  prove it.
- `ui/colors.FACTION_RGB` gets the new keys and values; `grey` stays as the
  fallback. The map, legend and chart all read it.
- All-pairs separation for five colours cannot pass (the reference documents
  that only its first three slots do). On the map, where any two factions can
  border, the secondary encoding is the legend plus the bound-faction outline;
  on the chart it is the direct labels. This is recorded as a known limit.
- Tests that hard-code `"red"` etc. are updated to the new keys.

## Testing

- **Recorder:** one reading per simulated date, including across a day-sized
  `tick(hours=24)`; values equal the faction totals at that moment; readings
  are frozen; two runs of the same seed give identical series.
- **Snapshot:** `casualty_history` and `event_log` are present, oldest first,
  and share no mutable object with world state; `event_log` length equals
  `len(world.events)`.
- **Performance:** measured and reported, not asserted in the suite (a timing
  assertion is flaky on a busy machine). Build a world with 10 years of readings
  and a full 2000-event log, time the median of 200 `build_view` calls, and time
  the 10-year CLI run; both must meet the budget in section 2.
- **Chart helpers:** `nice_ticks`, `compact_number`, `nearest_reading`,
  `spread_labels` against fixed inputs, including 0, 1, and very large values.
- **Chart rendering (cairo image surface):** a visible faction's colour appears
  on its line; a hidden faction's colour appears nowhere; empty readings and an
  empty `visible` set render without raising.
- **Widgets (need `DISPLAY`):** the notebook has tabs "Map" and "History";
  toggling a checkbutton changes the chart's visible set and submits no command
  (stub service records submits); the History log shows the newest event first.
- **By eye:** launch `bin/run_gui.sh --speed 16x`, let it run a simulated
  year, screenshot both tabs, and check for label collisions and legibility.

## Documentation

- `docs/architecture.md`: the `ui/` section gains the notebook and `chart.py`;
  the tick-pipeline section notes `record_history` inside step 11.
- `docs/decisions.md`: a dated entry for recording history in the simulation
  rather than the UI, cumulative rather than rate, and the palette change with
  its measured failure and known all-pairs limit.
- `docs/game-logic.md`: one paragraph on the recorder.
- `README.md`: one sentence mentioning the History tab.
