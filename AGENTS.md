# AGENTS.md

This file provides guidance to coding agents (Claude Code, Codex, and others) when working with code in this repository. `CLAUDE.md` is a symlink to this file.

## What this repository currently is

A **spec-first skeleton**, not a working game. `src/endless_war/` is ~140 lines of placeholders: dataclasses with no behavior, a `SimulationEngine.tick()` that only advances the clock past a list of `TODO` comments, and `ui/`, `persistence/`, `ai/` modules that intentionally raise or return empty. The real content of the repo is in `docs/superpowers/specs/` (the numbered `00-`…`04-` files are the authoritative product + game design; the dated `*-design.md` files are per-feature designs) and `docs/` (architecture, algorithms, rules). Read those before writing code — implementation decisions are already made there.

Reading order for a new session: `README.md` → `docs/superpowers/specs/00-project-brief.md` → `docs/superpowers/specs/01-game-design.md` → `docs/superpowers/specs/03-mvp.md` → `docs/architecture.md` → `docs/development-rules.md`, then `docs/decisions.md` for anything decided in a prior session.

## Commands

```bash
python3 -m pytest              # full suite
python3 -m pytest tests/test_engine.py::test_tick_advances_time_by_six_hours   # single test
bin/run_gui.sh                 # run the game (War Room window + tray)
PYTHONPATH=src python3 -m endless_war   # headless: yearly text report
```

`pytest` is an optional dependency and is **not installed in the system python3** — install it (`pip install -e '.[dev]'` in a venv) before claiming tests pass. Create that venv with `python3 -m venv --system-site-packages` if it will also run UI code: PyGObject is a system dist-package and is invisible to a plain venv (see `docs/decisions.md`, 2026-09-22). `pyproject.toml` sets `pythonpath = ["src"]`, so pytest imports the package without an install; `bin/run_gui.sh` exports `PYTHONPATH` itself and works from any directory.

No linter or formatter is configured.

## Architecture constraints

These are non-negotiable and already specified in `docs/architecture.md` and `docs/development-rules.md`:

- **Layer direction is one-way**: domain → simulation → AI → persistence → app services → UI. Simulation code must never import GTK, tray, or persistence internals. `ui/app.py` carries an explicit "do not import from the simulation core" warning.
- **Determinism is a hard requirement**. All randomness comes from the seeded RNG owned by the simulation (`SimulationEngine.rng`, seeded from `WorldState.seed`). Same initial state + seed + commands must reproduce the same history. Never call the `random` module directly or introduce unseeded sources (time, dict ordering of unsorted sets, `id()`).
- **The tick pipeline has a fixed order**, mirrored by the `TODO` comments in `simulation/engine.py`: advance time → economy/production → manpower/recruitment → supply → AI decisions → movement → battles → occupation/control → morale/exhaustion/stability → diplomacy/war termination → events → persistence checkpoint. Add systems into that order rather than inventing a new one.
- **Time scale**: one tick = 6 simulated hours, 4 ticks = 1 simulated day. Live speed and offline catch-up are wall-clock policies layered on top of the same tick; offline catch-up may aggregate into day-sized ticks. Config lives in `config/default.toml` (`tick_hours`, `live_tick_seconds`, `max_offline_days_per_startup`).
- **Single simulation thread.** The GTK UI communicates via scheduled callbacks or a message queue; UI event handlers must not mutate world state directly.
- **The simulation must stay valid with no player faction selected** — every faction is AI-driven by default, and the player is an optional overlay.

## Working conventions

- Balancing numbers belong in `config/default.toml` (`[balance]`), not hardcoded in systems.
- Prefer pure functions for calculations; keep combat/supply formulas **bounded, explainable, and stable over long simulations** (see `docs/simulation-notes.md`). Anti-snowball mechanisms are deliberately deferred until observed behavior demands them.
- `effective_power` in the design spec (`manpower × equipment × training × ...`) is conceptual — implement it with normalized, bounded multipliers, not raw products.
- Every simulation bug that affects state gets a regression test.
- Record anything a future session would otherwise re-litigate in `docs/decisions.md` using its dated template.
- `data/saves/` is gitignored except for `.gitkeep`; SQLite files (`*.db`, `*.sqlite3`) are ignored everywhere.

## Scope discipline

`CONTINUE_OFFLINE.md` and `docs/superpowers/specs/04-roadmap.md` set the sequencing, and it is deliberate: **build a headless autonomous simulation before any GTK or tray work.** The stated checkpoint is 5 factions, ~100 provinces, several armies, 10 simulated years under AI control, printing yearly territory/population/casualties/major events, with wars that start, fronts that move, wars that end, and no numeric explosions. Graphics, tray polish, diplomacy, commanders, and doctrine come after that loop is demonstrably interesting. `docs/superpowers/specs/03-mvp.md` lists what is explicitly deferred — do not pull deferred features forward without being asked.
