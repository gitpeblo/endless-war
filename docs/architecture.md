# Technical Architecture

## Principle
The simulation engine must not depend on GTK or tray code.

The application should be divided into:

1. **Domain model** — pure state objects.
2. **Simulation systems** — deterministic state transitions.
3. **AI systems** — generate strategic decisions.
4. **Persistence** — SQLite and save metadata.
5. **Application services** — simulation loop, catch-up, commands.
6. **UI** — GTK views and tray integration.

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
11. event generation
12. persistence checkpoint when due

## UI stack
GTK 3 through PyGObject (`gi`), with `AyatanaAppIndicator3` for the MATE tray. Decision and verified package versions: `decisions.md` (2026-09-22).

Practical notes:

- Always call `gi.require_version("Gtk", "3.0")` / `gi.require_version("AyatanaAppIndicator3", "0.1")` before importing from `gi.repository`.
- Use `AyatanaAppIndicator3`, not the legacy `AppIndicator3` — the latter is not installed on Ubuntu 24.04.
- Nothing needs installing on the current machine, but PyGObject is a system dist-package: a virtualenv needs `--system-site-packages` to see it.

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
