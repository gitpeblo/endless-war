# Endless War Simulator

An offline-first project skeleton for a persistent autonomous war simulation designed to run mostly unattended on Ubuntu MATE.

The game simulates multiple AI-controlled factions, shifting front lines, logistics, economy, manpower, morale, war exhaustion, diplomacy, internal instability, commanders, and emergent history. The player intervenes at a strategic level rather than micromanaging individual units.

## Running it

There is no graphical interface yet. Run the simulation from the repository root:

```bash
./scripts/run_cli.sh                        # 10 simulated years, seed 42
./scripts/run_cli.sh --years 1 --seed 7     # a shorter run, different world
```

Nothing to install — no virtualenv, no dependencies beyond the Python standard library. Ten simulated years take about six seconds.

It prints one block per simulated year: each faction's provinces, population, casualties and war exhaustion, then the war count and that year's major events. It ends with `Completed N simulated years with no invariant violations`, or exits non-zero and says what went wrong.

The same seed always produces the same history, so runs are directly comparable.

## How it works

`docs/game-logic.md` describes what the simulation computes each tick — economy,
supply, the army AI, battle resolution, and how wars start and end — with the
actual formulas and the config values that tune them.

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
