# Endless War Simulator

An offline-first project skeleton for a persistent autonomous war simulation designed to run mostly unattended on Ubuntu MATE.

The game simulates multiple AI-controlled factions, shifting front lines, logistics, economy, manpower, morale, war exhaustion, diplomacy, internal instability, commanders, and emergent history. The player intervenes at a strategic level rather than micromanaging individual units.

## Running it

The War Room window shows an isometric pixel-art map of the provinces and their terrain (scroll to zoom, drag with the middle button to pan), a status panel (the whole world, or one faction with `--faction`), a legend and the event feed, and keeps running in the tray when you close it. A History tab charts each faction's cumulative dead over time (tick factions on and off to compare) above the full event log:

```bash
bin/endless-war                                  # watch, seed 42, 1x (a 6-hour tick per second)
bin/endless-war --faction 0 --speed 16x --seed 7 # follow faction 0, fast
```

It uses the system GTK 3 and Ayatana indicator packages that Ubuntu MATE already ships. Quit from the tray menu; closing the window only hides it.

For a headless run that prints a yearly report instead:

```bash
PYTHONPATH=src python3 -m endless_war                        # 10 simulated years, seed 42
PYTHONPATH=src python3 -m endless_war --years 1 --seed 7     # a shorter run, different world
```

Nothing to install — no virtualenv, no dependencies beyond the Python standard library. Ten simulated years take about six seconds.

It prints one block per simulated year: each faction's provinces, population, casualties and war exhaustion, then the war count and that year's major events. It ends with `Completed N simulated years with no invariant violations`, or exits non-zero and says what went wrong.

The same seed always produces the same history, so runs are directly comparable.

## How it works

Start with **[`docs/guides/`](docs/guides/README.md)** — the world, a day in the
war, how wars work, and how to read a run. Plain language, no code.

For the exact formulas and the config values that tune them, see
`docs/game-logic.md`.

## Core experience

- Runs continuously in the background.
- Minimizes to the Ubuntu MATE system tray.
- Remains meaningful when ignored for minutes or hours.
- Multiple autonomous factions act without player input.
- The player sets priorities, policies, doctrines, objectives, and risk tolerance.
- Wars end, but the world simulation continues.
- History accumulates as a first-class game feature.

## Suggested technology

- Python 3.12+
- GTK 3 / PyGObject for the desktop UI
- Ayatana AppIndicator for Ubuntu MATE tray integration
- SQLite for persistent world state and event history
- pytest for tests

## Repository layout

- `docs/superpowers/specs/` — the authoritative product and game specifications (`00-`…`04-`) and the dated per-feature designs
- `docs/` — architecture, algorithms, decisions, and implementation notes
- `src/endless_war/` — application source tree
- `tests/` — automated tests
- `config/` — default configuration and balancing values
- `assets/` — future icons, map assets, and UI resources
- `data/saves/` — local save-game location placeholder
- `bin/` — `endless-war`, the game launcher

## Recommended development order

1. Implement deterministic world state and simulation clock.
2. Add factions, provinces, economy, manpower, and armies.
3. Add movement, supply, and battle resolution.
4. Add autonomous strategic AI.
5. Add event/history logging and save/load.
6. Add a basic GTK map/status window.
7. Add Ubuntu MATE tray integration.
8. Add offline elapsed-time catch-up.
9. Expand diplomacy, instability, commanders, doctrine, and balancing.

## First milestone

The first playable prototype should run a 4–6 faction war on a simple province graph, display territory/front changes, log important events, save/load correctly, and require no player interaction to continue.

See `docs/superpowers/specs/00-project-brief.md` and `docs/superpowers/specs/01-game-design.md` first.
