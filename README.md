# Endless War Simulator

An offline-first project skeleton for a persistent autonomous war simulation designed to run mostly unattended on Ubuntu MATE.

The game simulates multiple AI-controlled factions, shifting front lines, logistics, economy, manpower, morale, war exhaustion, diplomacy, internal instability, commanders, and emergent history. The player intervenes at a strategic level rather than micromanaging individual units.

## Running it

The headless simulation core works today; there is no graphical interface yet (see `specs/04-roadmap.md`). The entry point is an *observatory*: it runs the world forward for N simulated years with every faction under AI control, and prints a report once per simulated year.

```bash
./scripts/run_cli.sh                        # 10 simulated years, seed 42 (the defaults)
./scripts/run_cli.sh --years 10 --seed 42   # the same run, stated explicitly
./scripts/run_cli.sh --years 1 --seed 7     # a quick look at a different world
```

A ten-year run takes about six seconds. The script needs no virtualenv — the simulation has no runtime dependencies beyond the standard library — but it must be run from the repository root. The equivalent direct invocation is `python3 -m endless_war --years 10 --seed 42` with `src/` on `PYTHONPATH`.

Each yearly block lists, per faction, the provinces it controls, the population under its control, its cumulative casualties and its war exhaustion, followed by the active/total war count and that year's last few major events. The run ends with `Completed N simulated years with no invariant violations`, or exits non-zero and prints what went out of range.

**Runs are deterministic**: the same seed always produces the same history, so two runs are directly comparable and every figure recorded in `docs/decisions.md` can be reproduced by re-running its seed.

The simulation also runs on a live wall-clock in a background thread via `endless_war.app.SimulationService`, which accepts pause, resume, speed, and faction-binding commands. This is what the future GTK shell will consume. There is still no graphical interface, and `run_cli.sh` remains the way to observe and verify a run.

### Tests

```bash
python3 -m pytest                  # the full suite
python3 -m pytest -m "not slow"    # skips the ten-year checkpoint run
```

`pytest` is not installed in the system Python. Create a virtualenv and install the dev extra first (`python3 -m venv --system-site-packages .venv && .venv/bin/pip install -e '.[dev]'`); the `--system-site-packages` flag matters for later UI work, because PyGObject is a distribution package a plain venv cannot see.

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

- `specs/` — authoritative product and game specifications
- `docs/` — architecture, algorithms, decisions, and implementation notes
- `src/endless_war/` — application source tree
- `tests/` — automated tests
- `config/` — default configuration and balancing values
- `assets/` — future icons, map assets, and UI resources
- `data/saves/` — local save-game location placeholder
- `scripts/` — development and run helpers

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

See `specs/00-project-brief.md` and `specs/01-game-design.md` first.
