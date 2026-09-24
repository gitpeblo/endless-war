# War Mechanics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fronts move and wars finish:
- idle armies go to the front that needs them;
- attacks weigh real combat strength;
- beaten defenders retreat or surrender;
- walk-in captures take a day;
- landless factions are eliminated;
- peace settles occupied land.

It is all measured against a written gate.

**Architecture:** Changes stay inside the existing fixed tick pipeline:
- AI: `ai/strategic.py`.
- Occupation, retreat and surrender: `systems/control.py`.
- Elimination and settlement at the diplomacy step: `systems/diplomacy.py`.
- Event rendering: `systems/events.py`.
- A new `endless_war.measure` module runs the ten-year gate. `SimulationEngine.tick()` returns a small count summary so the tool can count battles and captures.

**Tech Stack:** Python 3.12, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-war-mechanics-design.md`

## Global Constraints

- Determinism: iterate `sorted(...)` everywhere; no new RNG draws beyond the existing ones; same seed gives the same decade.
- Tick pipeline order is unchanged. New work sits inside the existing steps: AI (5), control (8), diplomacy (10), events (11).
- `[balance] occupation_ticks = 4`, inserted **before** the `[balance.terrain_defence]` sub-table (TOML assigns later keys to the sub-table).
- Gate, on every seed of 42, 7 and 99, over ten years:
  - no enemy-surrounded island province lasts more than 180 days;
  - no more than 3 captures per battle;
  - the map changes in at least 6 of the 9 year-over-year transitions;
  - fewer than 2000 events;
  - the largest faction stays at or below 70 % of provinces;
  - invariants stay clean, and the 10-year CLI run takes under 6 s.
- Failures are reported, never tuned away.
- Run tests with `.venv/bin/python -m pytest -q`.

## Review Focus

1. **A war whose last defender is eliminated mid-war:** the war must end, flags must clear on both sides, and the peace settlement must run once, not twice.
2. **Routing when a faction has several disconnected pieces of land:** armies on an island with no front path must stay put, not raise or wander.
3. **A province with armies of three factions**, two of them at war with the controller: no occupation counter may advance.
4. **Surrender of an attacker broken inside an enemy province with no friendly neighbour:** it must be removed, and its manpower counted once.
5. **An eliminated faction bound in the UI** (`--faction`): the status panel says "destroyed" and nothing raises.

---

### Task 1: Measurement tool and baseline

**Files:**
- Modify: `src/endless_war/simulation/engine.py` (`tick()` returns `{"battles": int, "captures": int}`)
- Create: `src/endless_war/measure.py`
- Test: `tests/test_measure.py`

- [ ] **Step 1: Failing test.** `tests/test_measure.py`:

```python
from endless_war.measure import measure


def test_measure_reports_every_gate_figure_for_a_short_run() -> None:
    row = measure(seed=42, years=1)
    for key in ("battles", "captures", "captures_per_battle", "map_changes", "largest_share",
                "longest_island_days", "events", "eliminated", "wars_started", "wars_ended",
                "violations", "seconds"):
        assert key in row, key
    assert 0 < row["largest_share"] <= 1
```

- [ ] **Step 2: Implement.** In `engine.tick()`, return `{"battles": len(battle_records), "captures": len(capture_records)}` at the end; `run()` stays unchanged. Create `measure.py`:

```python
"""Ten-year measurement of the war model against the gate in docs/decisions.md.

    PYTHONPATH=src python3 -m endless_war.measure --seeds 42 7 99
"""

from __future__ import annotations

import argparse
import time

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_DAY = 4
GATE = {
    "longest_island_days": 180,
    "captures_per_battle": 3.0,
    "map_changes": 6,
    "events": 2000,
    "largest_share": 0.70,
    "seconds": 6.0,
}


def _islands(world) -> set[int]:
    found = set()
    for pid, province in world.provinces.items():
        mine = province.controller_faction_id
        if province.neighbors and all(
            world.provinces[n].controller_faction_id != mine for n in province.neighbors
        ):
            found.add(pid)
    return found


def measure(seed: int, years: int = 10) -> dict:
    cfg = load_config()
    world = generate_world(seed=seed, config=cfg)
    engine = SimulationEngine(world, cfg)
    battles = captures = violations = 0
    battle_years: set[int] = set()
    island_since: dict[int, int] = {}
    longest = 0
    yearly: list[tuple] = []
    largest = 0.0
    eliminated: dict[int, int] = {}
    total = len(world.provinces)
    start = time.perf_counter()
    for tick in range(years * 365 * TICKS_PER_DAY):
        counts = engine.tick()
        year = tick // (365 * TICKS_PER_DAY)
        battles += counts["battles"]
        captures += counts["captures"]
        if counts["battles"]:
            battle_years.add(year)
        if tick % TICKS_PER_DAY:
            continue
        day = tick // TICKS_PER_DAY
        islands = _islands(world)
        for pid in list(island_since):
            if pid not in islands:
                longest = max(longest, day - island_since.pop(pid))
        for pid in islands:
            island_since.setdefault(pid, day)
        held: dict[int, int] = {}
        for province in world.provinces.values():
            held[province.controller_faction_id] = held.get(province.controller_faction_id, 0) + 1
        largest = max(largest, max(held.values()) / total)
        for fid in world.factions:
            if fid not in held and fid not in eliminated:
                eliminated[fid] = year + 1
        if (tick + TICKS_PER_DAY) % (365 * TICKS_PER_DAY) == 0:
            yearly.append(tuple(world.provinces[p].controller_faction_id for p in sorted(world.provinces)))
            violations += len(check_invariants(world))
    last_day = years * 365
    for since in island_since.values():
        longest = max(longest, last_day - since)
    return {
        "seed": seed,
        "battles": battles,
        "battle_years": len(battle_years),
        "captures": captures,
        "captures_per_battle": captures / battles if battles else float(captures),
        "map_changes": sum(1 for a, b in zip(yearly, yearly[1:]) if a != b),
        "largest_share": largest,
        "longest_island_days": longest,
        "events": world.next_event_id,
        "eliminated": eliminated,
        "wars_started": len(world.wars),
        "wars_ended": sum(1 for w in world.wars.values() if w.status == "ended"),
        "violations": violations,
        "seconds": time.perf_counter() - start,
    }


def _passes(row: dict) -> dict[str, bool]:
    return {
        "longest_island_days": row["longest_island_days"] <= GATE["longest_island_days"],
        "captures_per_battle": row["captures_per_battle"] <= GATE["captures_per_battle"],
        "map_changes": row["map_changes"] >= GATE["map_changes"],
        "events": row["events"] < GATE["events"],
        "largest_share": row["largest_share"] <= GATE["largest_share"],
        "violations": row["violations"] == 0,
        "seconds": row["seconds"] < GATE["seconds"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="endless-war-measure")
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 7, 99])
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args(argv)
    cols = ("seed", "battles", "battle_years", "captures", "captures_per_battle", "map_changes",
            "largest_share", "longest_island_days", "events", "wars_started", "wars_ended",
            "eliminated", "violations", "seconds")
    print(" | ".join(cols))
    for seed in args.seeds:
        row = measure(seed, args.years)
        cells = []
        for c in cols:
            v = row[c]
            cells.append(f"{v:.2f}" if isinstance(v, float) else str(v))
        verdict = _passes(row)
        print(" | ".join(cells), "|", "PASS" if all(verdict.values()) else
              "FAIL: " + ", ".join(k for k, ok in verdict.items() if not ok))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the tests.** Expect all to pass.
- [ ] **Step 4: Measure the baseline** with `PYTHONPATH=src python3 -m endless_war.measure` and paste the table into the ledger. The baseline is expected to FAIL the island and captures-per-battle criteria.
- [ ] **Step 5: Commit** with the message `feat: ten-year measurement tool; engine.tick returns counts`.

### Task 2: Routing idle armies to the front

**Files:** Modify `src/endless_war/ai/strategic.py`. Test in `tests/test_strategic_ai.py`.

- [ ] **Step 1: Failing tests** (append):

```python
def _war_world():
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    return w, cfg


def _rear_province(w, fid, enemy):
    fronts = {p for p in w.provinces if w.provinces[p].controller_faction_id == fid
              and any(w.provinces[n].controller_faction_id == enemy for n in w.provinces[p].neighbors)}
    for pid in sorted(w.provinces):
        p = w.provinces[pid]
        if p.controller_faction_id == fid and pid not in fronts and not any(
            w.provinces[n].controller_faction_id != fid for n in p.neighbors
        ):
            return pid
    raise AssertionError("premise: faction has an interior province")


def test_an_idle_army_in_the_rear_steps_toward_the_front() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    rear = _rear_province(w, 0, 3)
    w.armies[1] = Army(id=1, faction_id=0, province_id=rear, manpower=20_000)
    choose_strategic_actions(w, random.Random(1), cfg)
    step = w.armies[1].destination_id
    assert step is not None and step in w.provinces[rear].neighbors
    assert w.provinces[step].controller_faction_id == 0


def test_idle_armies_spread_over_the_front_instead_of_stacking() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    rear = _rear_province(w, 0, 3)
    for aid in range(1, 5):
        w.armies[aid] = Army(id=aid, faction_id=0, province_id=rear, manpower=20_000)
    w.armies[9] = Army(id=9, faction_id=3, province_id=next(
        p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 3), manpower=40_000)
    choose_strategic_actions(w, random.Random(1), cfg)
    assert len({w.armies[a].destination_id for a in range(1, 5)} - {None}) >= 2
```

- [ ] **Step 2: Implement.** Add to `strategic.py`:
  - `_front_pressure(world, fid, terrain) -> dict[int, float]`: for each front province (F-controlled, adjacent to an at-war controller), the enemy effective power in its hostile neighbours minus F's own effective power standing in it.
  - `_route(world, army, pressure) -> int | None`: a BFS from the army's province over F-controlled provinces, with neighbours expanded in sorted order, recording each province's parent.
    - Target: the reachable front with key `(-pressure, dist, pid)`.
    - Subtract `effective_power(army, world, False, terrain)` from that front's pressure, so the next idle army is sent elsewhere.
    - Return the first step on the path, or None if the army already stands on the target or nothing is reachable.
  - In `choose_strategic_actions`, replace the `threatened` block with the router. The pressure is cached per faction per tick in a dict local to the call.
- [ ] **Step 3: Run the tests.** All pass, including the existing ones: "at peace no offensive orders" and "destinations always adjacent" still hold.
- [ ] **Step 4: Commit** with the message `feat: route idle armies to the front that needs them`.

### Task 3: Attacks judged by combat strength

**Files:** Modify `src/endless_war/ai/strategic.py`. Test in `tests/test_strategic_ai.py`.

- [ ] **Step 1: Failing tests:**

```python
def test_a_broken_stack_does_not_deter_an_attack() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    border = next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 0
                  and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[p].neighbors))
    target = next(n for n in w.provinces[border].neighbors if w.provinces[n].controller_faction_id == 3)
    w.armies[1] = Army(id=1, faction_id=0, province_id=border, manpower=20_000)
    w.armies[2] = Army(id=2, faction_id=3, province_id=target, manpower=150_000,
                       organization=0.0, morale=0.0)
    choose_strategic_actions(w, random.Random(1), cfg)
    assert w.armies[1].destination_id == target


def test_an_empty_hostile_province_is_always_attackable() -> None:
    from endless_war.domain.models import Army
    w, cfg = _war_world()
    w.armies.clear()
    border = next(p for p in sorted(w.provinces) if w.provinces[p].controller_faction_id == 0
                  and any(w.provinces[n].controller_faction_id == 3 for n in w.provinces[p].neighbors))
    w.armies[1] = Army(id=1, faction_id=0, province_id=border, manpower=500)
    choose_strategic_actions(w, random.Random(1), cfg)
    assert w.provinces[w.armies[1].destination_id].controller_faction_id == 3
```

- [ ] **Step 2: Implement.** Replace `_defenders_in` with `_defence_of(world, pid, attacker_fid, terrain)`: the sum of `effective_power(a, world, True, terrain)` for armies in `pid` whose faction is in `attacker_fid`'s `at_war_with`. The attack condition becomes `_defence_of(weakest) < effective_power(army, world, False, terrain) * attack_ratio`, sorting hostile neighbours by `(_defence_of, pid)`.
- [ ] **Step 3: Run the tests; then commit** with the message `feat: attack decisions weigh combat strength of hostile armies only`.

### Task 4: Defender retreat and surrender

**Files:**
- Modify `src/endless_war/simulation/systems/control.py`: read `defender_broke`, and add `surrender_trapped_armies`.
- Modify `engine.py`: call it after `apply_control_changes`, and pass its records to `record_events`.
- Modify `events.py`: `record_events(..., surrender_records=())`.
- Tests: `tests/test_control.py`.

- [ ] **Step 1: Failing tests:** a broken defender with a friendly neighbour ends in that neighbour after `apply_control_changes` with a `defender_broke` record. A broken army with hostiles present and no friendly neighbour is removed by `surrender_trapped_armies(world, cfg)`: its faction's casualties rise by its manpower, and one record `{"kind": "surrender", "province_id", "faction", "men"}` is returned.
- [ ] **Step 2: Implement** as specified:
  - Surrender applies to armies with `organization < broken_organization or morale < broken_morale`, with a hostile army in the same province and no neighbour controlled by the army's own faction, visiting army ids in sorted order.
  - Event: "Army surrendered", category military, severity major, body `"{faction}'s army of {men:,} surrendered in {province}."`
- [ ] **Step 3: Run the tests; then commit** with the message `feat: beaten defenders retreat; trapped broken armies surrender`.

### Task 5: Occupation takes time

**Files:** `domain/models.py` (`Province.occupation: tuple[int, int] | None = None`), `config/default.toml` (`occupation_ticks = 4`), `systems/control.py`, `tests/test_control.py`.

- [ ] **Step 1: Failing tests:**
  - one `apply_control_changes` call does not capture;
  - `occupation_ticks` consecutive calls capture exactly once;
  - a hold interrupted by the army leaving resets the counter;
  - a province holding two hostile factions' armies never advances.
  - Update `test_lone_army_captures_an_undefended_hostile_province` and `test_owner_is_unchanged_by_occupation` to call it `occupation_ticks` times. The stated reason: capture now takes a day.
- [ ] **Step 2: Implement** the counter as the spec describes:
  - `province.occupation = None` whenever the province holds zero or several factions' armies, or the single occupier is the controller or not at war with it;
  - otherwise increment it, and capture once it reaches `occupation_ticks`.
- [ ] **Step 3: Run the tests; then commit** with the message `feat: walk-in captures take a day (occupation_ticks)`.

### Task 6: Elimination

**Files:**
- `domain/models.py`: `Faction.eliminated = False`.
- `systems/diplomacy.py`: `eliminate_landless(world) -> list[dict]`, called first in `update_diplomacy`; wars whose attackers or defenders are all eliminated end, with reason "elimination"; eliminated factions skip declarations.
- `events.py`: "Faction destroyed", critical; the peace rendering for an elimination.
- `invariants.py`: a province controlled by an eliminated faction is a violation.
- `app/view_model.py` and `snapshot.py`: `FactionRow.eliminated: bool = False`.
- `ui/legend.py`: skip eliminated factions.
- `ui/panels.py`: the bound eliminated faction shows `(name, "destroyed")`.
- `tests/test_long_run.py`: replace the ownership assertion, as the spec says.
- Tests: `tests/test_diplomacy.py`.

- [ ] **Step 1: Failing tests:** a faction whose provinces are all set to another controller is eliminated on the next `update_diplomacy`: its armies are gone, `at_war_with` is empty on both sides, its war is ended, and it's reported in the returned events. An eliminated faction never declares war over 400 ticks.
- [ ] **Step 2: Implement; run the full suite; commit** with the message `feat: landless factions are eliminated`.

### Task 7: Occupation settled at peace

**Files:** `systems/diplomacy.py` (`_settle(world, war) -> list[tuple[int, int | None, int]]`, run for every war that ends, with the result on the peace event as `"annexed"`), `events.py` (one "Territory ceded" event per `(to, from)` pair: "X annexes N provinces from Y"), `control.py` docstring, tests in `tests/test_diplomacy.py`.

- [ ] **Step 1: Failing tests:**
  - the loser's occupied land goes to the occupier;
  - the third-party case transfers (the owner is not at war with the controller);
  - land still disputed with the owner (the owner is at war with the controller in another war) does not transfer;
  - one settlement per war end.
- [ ] **Step 2: Implement; run the full suite; commit** with the message `feat: peace settles occupied land`.

### Task 8: Gate, fixes found by measuring, docs

- [ ] **Step 1: Measure** with `PYTHONPATH=src python3 -m endless_war.measure` and paste the table into the ledger next to the baseline.
- [ ] **Step 2: If a criterion fails,** find the cause (systematic-debugging). Fix only mechanism bugs, each with a test. Never change a `[balance]` number to pass. If it still fails, report the table to the user and stop.
- [ ] **Step 3: Update the docs:**
  - `docs/game-logic.md`: sections on routing, attack decisions, retreat and surrender, occupation, elimination and peace settlement.
  - `docs/decisions.md`: a dated entry with the before and after gate tables, closing the 2026-09-23 "linked pair" and "absorbing state" notes.
- [ ] **Step 4: Run the full suite, then commit** with the message `docs: record the war mechanics`.
