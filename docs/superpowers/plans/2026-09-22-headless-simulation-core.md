# Headless Simulation Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic headless war simulation that runs 5 factions over 96 provinces for 10 simulated years without player input, printing yearly territory/population/casualties/events, with wars that start, fronts that move, and wars that end.

**Architecture:** A pure-Python domain layer (dataclasses, no I/O) is mutated by a fixed, ordered pipeline of stateless system functions. `SimulationEngine` owns the clock and the single seeded RNG and calls each system in the order fixed by `docs/architecture.md`. Nothing imports GTK, and persistence is deliberately out of scope for this slice. A CLI observatory (`endless_war.tools.observe`) drives the loop and asserts numeric invariants after every simulated year.

**Tech Stack:** Python 3.12, stdlib only (`dataclasses`, `random`, `tomllib`, `datetime`, `collections.deque`), pytest 8 for tests. No third-party runtime dependencies.

**Spec:** `specs/00-project-brief.md`, `specs/01-game-design.md`, `specs/03-mvp.md`, `docs/architecture.md`, `docs/data-model.md`, `docs/simulation-notes.md`, `docs/development-rules.md`, `CONTINUE_OFFLINE.md`

## Global Constraints

- Python `>=3.12` (from `pyproject.toml`). Standard library only — do not add runtime dependencies.
- **No UI imports.** Nothing under `src/endless_war/{domain,simulation,ai,tools}/` may import `gi`, GTK, or anything from `src/endless_war/ui/`.
- **All randomness comes from the engine's seeded RNG.** Never call module-level `random.*`. Never seed from the clock. Systems receive an RNG; they do not create one.
- **Deterministic iteration.** Always iterate `dict` collections via `sorted(d)` or `sorted(d.items())` before making a random or state-changing decision. Never iterate a `set`.
- One tick = 6 simulated hours; 4 ticks = 1 simulated day (`docs/architecture.md`). `tick_hours` comes from `config/default.toml`.
- **Bounded values.** `morale`, `organization`, `supply`, `training`, `equipment`, `stability`, `war_support`, `exhaustion`, `infrastructure` are all clamped to `[0.0, 1.0]` after every write. `manpower`, `population`, `treasury` are clamped at `>= 0`.
- Balancing numbers live in `config/default.toml`, not hardcoded in systems (`docs/development-rules.md`).
- Type-annotate public interfaces. Prefer pure functions for calculations.
- Every simulation bug affecting state gets a regression test.
- Existing test `tests/test_engine.py::test_tick_advances_time_by_six_hours` must keep passing throughout.

## Out of Scope for This Plan

`specs/03-mvp.md` lists the full prototype. This plan stops at the `CONTINUE_OFFLINE.md`
checkpoint and deliberately leaves the following MVP items unbuilt — do not add them here:

| MVP item | Why it is not in this plan |
|---|---|
| Faction-level equipment stockpile | Armies carry an `equipment` quality factor; a produced-and-consumed national stockpile is an economy expansion, better tuned once battles generate real attrition figures. |
| Pause / speed controls | A wall-clock concern of the application-services layer, not the tick pipeline. |
| Save / load, SQLite schema | Roadmap Phase 5. The world is in-memory only for this slice. |
| Main window, tray, map rendering | Roadmap Phase 6, gated behind this checkpoint being interesting. |
| Commanders, doctrine, civil wars, tech | `specs/03-mvp.md` explicitly defers them. |


---

### Task 0: Development environment and version control

**Files:**
- Create: `.gitignore` entries verified (already present), `docs/superpowers/plans/` (already present)
- Modify: `config/default.toml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `endless_war.config.load_config(path: Path | None = None) -> dict[str, Any]`; a git repository at the project root; a working `pytest` on PATH

- [ ] **Step 1: Create the virtualenv and install pytest**

PyGObject is a system dist-package, so create the venv with `--system-site-packages` (see `docs/decisions.md`, 2026-09-22) — the headless work does not need it, but the same venv will later run UI code.

```bash
cd /media/work/endless-war
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e '.[dev]'
.venv/bin/pytest --version
```

Expected: `pytest 8.x.x`. Use `.venv/bin/pytest` for every test command in this plan.

- [ ] **Step 2: Initialize git and make the baseline commit**

The project is not yet a git repository, but `.gitignore` already exists and expects one. `.venv/` is covered by the existing `.venv/` entry.

```bash
cd /media/work/endless-war
git init -q
git add -A
git commit -q -m "chore: baseline skeleton, specs, docs, and UI stack decision"
git log --oneline | head -1
```

- [ ] **Step 3: Write the failing config test**

```python
# tests/test_config.py
from endless_war.config import load_config


def test_load_config_reads_defaults() -> None:
    cfg = load_config()
    assert cfg["simulation"]["tick_hours"] == 6
    assert cfg["world"]["default_provinces"] == 96
    assert cfg["world"]["grid_cols"] == 12


def test_load_config_grid_matches_province_count() -> None:
    cfg = load_config()
    cols = cfg["world"]["grid_cols"]
    assert cfg["world"]["default_provinces"] % cols == 0
```

- [ ] **Step 4: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.config'`

- [ ] **Step 5: Add the new balance keys to config**

Append to `config/default.toml`. The existing `[simulation]` and `[world]` sections gain `grid_cols`; `[balance]` gains the constants every later task reads. `base_recruitment_rate` is reinterpreted here as *fraction of remaining mobilization headroom per tick*, which is self-limiting and cannot explode.

```toml
[simulation]
tick_hours = 6
live_tick_seconds = 1.0
max_offline_days_per_startup = 365

[world]
default_factions = 5
default_provinces = 96
grid_cols = 12

[balance]
base_recruitment_rate = 0.001
base_supply_decay_per_hop = 0.08
mobilization_ceiling = 0.08
income_per_industry = 100.0
upkeep_per_manpower = 0.002
base_casualty_rate = 0.02
organization_recovery_per_tick = 0.02
morale_recovery_per_tick = 0.015
attacker_break_organization = 0.25
defender_break_organization = 0.20
exhaustion_per_casualty_fraction = 1.5
exhaustion_decay_per_tick = 0.0008
war_declaration_strength_ratio = 1.35
war_declaration_max_exhaustion = 0.45
peace_exhaustion_threshold = 0.75
peace_stalemate_ticks = 480
min_supply = 0.05
```

- [ ] **Step 6: Write the config loader**

```python
# src/endless_war/config.py
"""Configuration loading.

Balancing values live in config/default.toml, never hardcoded in systems.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default.toml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and return the TOML configuration as a plain dict."""
    target = path or DEFAULT_CONFIG_PATH
    with target.open("rb") as handle:
        return tomllib.load(handle)
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 3 passed (2 new, plus the existing engine test)

- [ ] **Step 8: Commit**

```bash
git add config/default.toml src/endless_war/config.py tests/test_config.py
git commit -m "feat: add config loader and balance constants"
```

---

### Task 1: Deterministic RNG ownership and tick clock

**Files:**
- Modify: `src/endless_war/simulation/engine.py`
- Modify: `src/endless_war/domain/models.py`
- Test: `tests/test_determinism.py`

**Interfaces:**
- Consumes: `load_config` from Task 0
- Produces: `SimulationEngine(world: WorldState, config: dict | None = None)` with attributes `.world`, `.rng: random.Random`, `.config: dict`, `.tick_hours: int`; method `tick(self) -> None`; `WorldState.tick_count: int`

- [ ] **Step 1: Write the failing determinism test**

```python
# tests/test_determinism.py
from datetime import datetime, timezone

from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine


def _engine(seed: int) -> SimulationEngine:
    world = WorldState(seed=seed, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))
    return SimulationEngine(world)


def test_same_seed_produces_same_random_stream() -> None:
    a = [_engine(7).rng.random() for _ in range(1)][0]
    b = [_engine(7).rng.random() for _ in range(1)][0]
    assert a == b


def test_different_seed_produces_different_stream() -> None:
    assert _engine(7).rng.random() != _engine(8).rng.random()


def test_tick_increments_tick_count() -> None:
    eng = _engine(1)
    assert eng.world.tick_count == 0
    eng.tick()
    eng.tick()
    assert eng.world.tick_count == 2


def test_tick_hours_comes_from_config() -> None:
    assert _engine(1).tick_hours == 6
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_determinism.py -v`
Expected: FAIL — `AttributeError` / `TypeError` on `tick_count` and `tick_hours`

- [ ] **Step 3: Add `tick_count` to `WorldState`**

In `src/endless_war/domain/models.py`, extend the `WorldState` dataclass. Keep the existing fields; add `tick_count` after `current_time`:

```python
@dataclass(slots=True)
class WorldState:
    seed: int
    current_time: datetime
    tick_count: int = 0
    provinces: dict[int, Province] = field(default_factory=dict)
    factions: dict[int, Faction] = field(default_factory=dict)
    armies: dict[int, Army] = field(default_factory=dict)
```

- [ ] **Step 4: Rewrite the engine to own config and RNG**

```python
# src/endless_war/simulation/engine.py
"""Simulation orchestration.

The engine owns the clock and the single seeded RNG. Systems are stateless
functions called in the fixed order documented in docs/architecture.md.
"""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from endless_war.config import load_config
from endless_war.domain.models import WorldState


class SimulationEngine:
    def __init__(self, world: WorldState, config: dict[str, Any] | None = None) -> None:
        self.world = world
        self.config = config or load_config()
        self.rng = random.Random(world.seed)
        self.tick_hours: int = self.config["simulation"]["tick_hours"]

    def tick(self, hours: int | None = None) -> None:
        """Advance the world by one strategic tick.

        Systems run in the fixed order from docs/architecture.md. Later tasks
        insert their calls between the markers below; do not reorder them.
        """
        step = self.tick_hours if hours is None else hours
        self.world.current_time += timedelta(hours=step)
        self.world.tick_count += 1
        # --- SYSTEM PIPELINE START (fixed order, do not reorder) ---
        # economy
        # recruitment
        # supply
        # AI decisions
        # movement
        # battles
        # control changes
        # exhaustion/stability
        # diplomacy
        # events
        # --- SYSTEM PIPELINE END ---

    def run(self, ticks: int) -> None:
        """Advance the world by `ticks` strategic ticks."""
        for _ in range(ticks):
            self.tick()
```

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — the existing `test_tick_advances_time_by_six_hours` still passes because `tick()` defaults to 6 hours.

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/engine.py src/endless_war/domain/models.py tests/test_determinism.py
git commit -m "feat: engine owns seeded rng, config, and tick count"
```

---

### Task 2: Province graph generation

**Files:**
- Create: `src/endless_war/simulation/worldgen.py`
- Modify: `src/endless_war/domain/models.py`
- Test: `tests/test_worldgen_map.py`

**Interfaces:**
- Consumes: `WorldState`, `Province`, config from Tasks 0–1
- Produces: `generate_province_grid(world: WorldState, rng: random.Random, config: dict) -> None`; `Province.terrain: str`; `TERRAIN_DEFENCE: dict[str, float]`

- [ ] **Step 1: Write the failing map test**

```python
# tests/test_worldgen_map.py
import random
from datetime import datetime, timezone

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.worldgen import TERRAIN_DEFENCE, generate_province_grid


def _world() -> WorldState:
    return WorldState(seed=42, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))


def test_generates_expected_province_count() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    assert len(w.provinces) == 96


def test_neighbours_are_symmetric() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    for pid, prov in w.provinces.items():
        for nid in prov.neighbors:
            assert pid in w.provinces[nid].neighbors


def test_corner_province_has_two_neighbours() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    assert len(w.provinces[0].neighbors) == 2


def test_graph_is_connected() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    seen = {0}
    stack = [0]
    while stack:
        for nid in w.provinces[stack.pop()].neighbors:
            if nid not in seen:
                seen.add(nid)
                stack.append(nid)
    assert len(seen) == len(w.provinces)


def test_terrain_is_known_and_population_positive() -> None:
    w = _world()
    generate_province_grid(w, random.Random(42), load_config())
    for prov in w.provinces.values():
        assert prov.terrain in TERRAIN_DEFENCE
        assert prov.population > 0
        assert 0.0 <= prov.infrastructure <= 1.0


def test_generation_is_reproducible_for_same_seed() -> None:
    a, b = _world(), _world()
    generate_province_grid(a, random.Random(42), load_config())
    generate_province_grid(b, random.Random(42), load_config())
    assert [(p.terrain, p.population) for p in a.provinces.values()] == [
        (p.terrain, p.population) for p in b.provinces.values()
    ]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_worldgen_map.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.worldgen'`

- [ ] **Step 3: Add `terrain` to `Province`**

In `src/endless_war/domain/models.py`, add the field to the existing `Province` dataclass, after `infrastructure`:

```python
    terrain: str = "plains"
    supply_value: float = 1.0
    is_capital: bool = False
```

- [ ] **Step 4: Write the grid generator**

```python
# src/endless_war/simulation/worldgen.py
"""Deterministic world generation.

A rectangular grid graph is the simplest province topology that still produces
real fronts and salients. docs/data-model.md treats provinces as a graph, so
nothing downstream may assume the grid: always walk `Province.neighbors`.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Province, WorldState

# Defensive multiplier applied to the defender's power in battle.
TERRAIN_DEFENCE: dict[str, float] = {
    "plains": 1.00,
    "forest": 1.20,
    "hills": 1.35,
    "mountain": 1.60,
    "urban": 1.45,
}

_TERRAIN_WEIGHTS: list[tuple[str, int]] = [
    ("plains", 40), ("forest", 22), ("hills", 18), ("mountain", 10), ("urban", 10),
]


def _pick_terrain(rng: random.Random) -> str:
    total = sum(weight for _, weight in _TERRAIN_WEIGHTS)
    roll = rng.randrange(total)
    upto = 0
    for name, weight in _TERRAIN_WEIGHTS:
        upto += weight
        if roll < upto:
            return name
    return _TERRAIN_WEIGHTS[-1][0]


def generate_province_grid(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Populate `world.provinces` with a connected 4-neighbour grid graph."""
    count: int = config["world"]["default_provinces"]
    cols: int = config["world"]["grid_cols"]
    if count % cols:
        raise ValueError(f"default_provinces ({count}) must be divisible by grid_cols ({cols})")
    rows = count // cols

    for row in range(rows):
        for col in range(cols):
            pid = row * cols + col
            terrain = _pick_terrain(rng)
            world.provinces[pid] = Province(
                id=pid,
                name=f"P{pid:03d}",
                population=rng.randint(180_000, 900_000),
                industry=round(rng.uniform(0.4, 2.0), 3),
                infrastructure=round(rng.uniform(0.55, 1.0), 3),
                terrain=terrain,
            )

    for row in range(rows):
        for col in range(cols):
            pid = row * cols + col
            neighbours: list[int] = []
            if col > 0:
                neighbours.append(pid - 1)
            if col < cols - 1:
                neighbours.append(pid + 1)
            if row > 0:
                neighbours.append(pid - cols)
            if row < rows - 1:
                neighbours.append(pid + cols)
            world.provinces[pid].neighbors = sorted(neighbours)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_worldgen_map.py -v`
Expected: PASS — 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/worldgen.py src/endless_war/domain/models.py tests/test_worldgen_map.py
git commit -m "feat: deterministic province grid generation"
```

---

### Task 3: Faction seeding and contiguous territory

**Files:**
- Modify: `src/endless_war/simulation/worldgen.py`
- Modify: `src/endless_war/domain/models.py`
- Test: `tests/test_worldgen_factions.py`

**Interfaces:**
- Consumes: `generate_province_grid` from Task 2
- Produces: `generate_factions(world, rng, config) -> None`; `generate_world(seed: int, config: dict) -> WorldState`; `FACTION_NAMES: list[str]`; `Faction.at_war_with: set[int]`, `Faction.casualties: int`

- [ ] **Step 1: Write the failing faction test**

```python
# tests/test_worldgen_factions.py
from collections import deque

from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world


def test_creates_configured_faction_count() -> None:
    w = generate_world(seed=42, config=load_config())
    assert len(w.factions) == 5


def test_every_province_is_owned_and_controlled_by_owner() -> None:
    w = generate_world(seed=42, config=load_config())
    for prov in w.provinces.values():
        assert prov.owner_faction_id in w.factions
        assert prov.controller_faction_id == prov.owner_faction_id


def test_each_faction_has_exactly_one_capital_it_owns() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        caps = [p for p in w.provinces.values() if p.is_capital and p.owner_faction_id == fid]
        assert len(caps) == 1
        assert caps[0].id == fac.capital_province_id


def test_territory_is_contiguous_per_faction() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        owned = {p.id for p in w.provinces.values() if p.owner_faction_id == fid}
        seen = {fac.capital_province_id}
        queue = deque(seen)
        while queue:
            for nid in w.provinces[queue.popleft()].neighbors:
                if nid in owned and nid not in seen:
                    seen.add(nid)
                    queue.append(nid)
        assert seen == owned, f"faction {fid} territory is not contiguous"


def test_every_faction_starts_with_provinces_and_manpower() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        owned = [p for p in w.provinces.values() if p.owner_faction_id == fid]
        assert len(owned) >= 5
        assert fac.manpower > 0
        assert fac.at_war_with == set()


def test_world_generation_is_reproducible() -> None:
    a = generate_world(seed=42, config=load_config())
    b = generate_world(seed=42, config=load_config())
    assert [p.owner_faction_id for p in a.provinces.values()] == [
        p.owner_faction_id for p in b.provinces.values()
    ]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_worldgen_factions.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_world'`

- [ ] **Step 3: Extend the `Faction` dataclass**

In `src/endless_war/domain/models.py`, add these fields to `Faction` after `exhaustion`:

```python
    at_war_with: set[int] = field(default_factory=set)
    casualties: int = 0
    color_key: str = "grey"
```

- [ ] **Step 4: Append faction generation to worldgen.py**

Multi-source BFS from the capitals guarantees contiguous territory by construction, which is what `test_territory_is_contiguous_per_faction` checks.

```python
# appended to src/endless_war/simulation/worldgen.py
from collections import deque
from datetime import datetime, timezone

from endless_war.domain.models import Faction

FACTION_NAMES: list[str] = [
    "Valdran Hegemony",
    "Korsk Federation",
    "Meridian Compact",
    "Astaran Dominion",
    "Free Cities League",
]
FACTION_COLORS: list[str] = ["red", "blue", "green", "amber", "violet"]


def _pick_capitals(world: WorldState, rng: random.Random, count: int, cols: int) -> list[int]:
    """Choose `count` well-separated provinces as capitals (greedy farthest-point)."""
    ids = sorted(world.provinces)
    chosen = [rng.choice(ids)]
    while len(chosen) < count:
        best_id, best_dist = ids[0], -1.0
        for pid in ids:
            if pid in chosen:
                continue
            row, col = divmod(pid, cols)
            nearest = min(
                abs(row - divmod(c, cols)[0]) + abs(col - divmod(c, cols)[1]) for c in chosen
            )
            if nearest > best_dist:
                best_dist, best_id = float(nearest), pid
        chosen.append(best_id)
    return chosen


def generate_factions(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Create factions and assign contiguous starting territory."""
    count: int = config["world"]["default_factions"]
    cols: int = config["world"]["grid_cols"]
    ceiling: float = config["balance"]["mobilization_ceiling"]
    if count > len(FACTION_NAMES):
        raise ValueError(f"only {len(FACTION_NAMES)} faction names are defined")

    capitals = _pick_capitals(world, rng, count, cols)
    for fid, capital in enumerate(capitals):
        world.factions[fid] = Faction(
            id=fid,
            name=FACTION_NAMES[fid],
            capital_province_id=capital,
            color_key=FACTION_COLORS[fid],
            treasury=round(rng.uniform(400_000, 900_000), 2),
            stability=round(rng.uniform(0.55, 0.9), 3),
            war_support=round(rng.uniform(0.35, 0.6), 3),
        )
        world.provinces[capital].is_capital = True

    # Multi-source BFS: every province goes to the nearest capital, so each
    # faction's territory is contiguous by construction.
    queue: deque[int] = deque()
    for fid, capital in enumerate(capitals):
        world.provinces[capital].owner_faction_id = fid
        world.provinces[capital].controller_faction_id = fid
        queue.append(capital)
    while queue:
        pid = queue.popleft()
        owner = world.provinces[pid].owner_faction_id
        for nid in world.provinces[pid].neighbors:
            neighbour = world.provinces[nid]
            if neighbour.owner_faction_id is None:
                neighbour.owner_faction_id = owner
                neighbour.controller_faction_id = owner
                queue.append(nid)

    for fid, fac in sorted(world.factions.items()):
        population = sum(
            p.population for p in world.provinces.values() if p.owner_faction_id == fid
        )
        fac.manpower = int(population * ceiling * rng.uniform(0.35, 0.6))


def generate_world(seed: int, config: dict[str, Any]) -> WorldState:
    """Build a complete starting world. This is the only entry point callers need."""
    world = WorldState(seed=seed, current_time=datetime(2030, 1, 1, tzinfo=timezone.utc))
    world.expected_province_count = config["world"]["default_provinces"]
    rng = random.Random(seed)
    generate_province_grid(world, rng, config)
    generate_factions(world, rng, config)
    return world
```

Move the `from collections import deque` and `from datetime import ...` imports to the top of the file with the others.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_worldgen_factions.py -v`
Expected: PASS — 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/worldgen.py src/endless_war/domain/models.py tests/test_worldgen_factions.py
git commit -m "feat: faction seeding with contiguous starting territory"
```

---

### Task 4: Economy and recruitment systems

**Files:**
- Create: `src/endless_war/simulation/systems/__init__.py`
- Create: `src/endless_war/simulation/systems/economy.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_economy.py`

**Interfaces:**
- Consumes: `generate_world` from Task 3
- Produces: `update_economy(world, rng, config) -> None`; `update_recruitment(world, rng, config) -> None`; `clamp(value: float, low: float = 0.0, high: float = 1.0) -> float` in `endless_war.simulation.systems`

- [ ] **Step 1: Write the failing economy test**

```python
# tests/test_economy.py
import random

from endless_war.config import load_config
from endless_war.simulation.systems.economy import update_economy, update_recruitment
from endless_war.simulation.worldgen import generate_world


def test_treasury_grows_in_peacetime() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    before = {fid: f.treasury for fid, f in w.factions.items()}
    update_economy(w, random.Random(1), cfg)
    assert all(w.factions[fid].treasury > before[fid] for fid in before)


def test_treasury_never_goes_negative() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for fac in w.factions.values():
        fac.treasury = 0.0
    for _ in range(50):
        update_economy(w, random.Random(1), cfg)
    assert all(f.treasury >= 0.0 for f in w.factions.values())


def test_recruitment_converges_to_mobilization_ceiling() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(4000):
        update_recruitment(w, random.Random(1), cfg)
    for fid, fac in w.factions.items():
        population = sum(p.population for p in w.provinces.values() if p.owner_faction_id == fid)
        cap = population * cfg["balance"]["mobilization_ceiling"]
        assert fac.manpower <= cap + 1, "manpower must never exceed the mobilization ceiling"
        assert fac.manpower > cap * 0.5, "manpower should approach the ceiling over time"


def test_recruitment_slows_as_exhaustion_rises() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.manpower = 0
    fac.exhaustion = 0.0
    update_recruitment(w, random.Random(1), cfg)
    calm = fac.manpower

    fac.manpower = 0
    fac.exhaustion = 0.9
    update_recruitment(w, random.Random(1), cfg)
    assert fac.manpower < calm
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_economy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems'`

- [ ] **Step 3: Create the systems package with the shared clamp helper**

```python
# src/endless_war/simulation/systems/__init__.py
"""Simulation systems: stateless functions that mutate WorldState in place.

Every system has the signature (world, rng, config) -> None and is called by
SimulationEngine.tick() in the fixed order from docs/architecture.md.
"""

from __future__ import annotations


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp to [low, high]. Every bounded field is written through this."""
    return max(low, min(high, value))
```

- [ ] **Step 4: Write the economy and recruitment systems**

```python
# src/endless_war/simulation/systems/economy.py
"""Economy and manpower.

Recruitment fills the gap between the current pool and a population-derived
ceiling, so it converges rather than growing without bound (docs/simulation-notes.md,
"avoid exponential snowballing").
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState


def _controlled_provinces(world: WorldState, faction_id: int) -> list[Any]:
    return [
        world.provinces[pid]
        for pid in sorted(world.provinces)
        if world.provinces[pid].controller_faction_id == faction_id
    ]


def update_economy(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Accrue income from controlled industry and pay army upkeep."""
    income_rate: float = config["balance"]["income_per_industry"]
    upkeep_rate: float = config["balance"]["upkeep_per_manpower"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        income = sum(
            p.industry * p.infrastructure * income_rate for p in _controlled_provinces(world, fid)
        )
        upkeep = sum(
            army.manpower * upkeep_rate
            for army in world.armies.values()
            if army.faction_id == fid
        )
        fac.treasury = max(0.0, fac.treasury + income - upkeep)


def update_recruitment(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Draw recruits toward the mobilization ceiling, slowed by exhaustion."""
    rate: float = config["balance"]["base_recruitment_rate"]
    ceiling: float = config["balance"]["mobilization_ceiling"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        population = sum(p.population for p in _controlled_provinces(world, fid))
        cap = population * ceiling
        headroom = max(0.0, cap - fac.manpower)
        recruits = headroom * rate * (1.0 - fac.exhaustion)
        fac.manpower = max(0, int(fac.manpower + recruits))
```

- [ ] **Step 5: Wire both systems into the engine pipeline**

In `src/endless_war/simulation/engine.py`, add the import and replace the `# economy` and `# recruitment` markers:

```python
from endless_war.simulation.systems.economy import update_economy, update_recruitment
```

```python
        # --- SYSTEM PIPELINE START (fixed order, do not reorder) ---
        update_economy(self.world, self.rng, self.config)
        update_recruitment(self.world, self.rng, self.config)
        # supply
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — all tests, including the 4 new economy tests

- [ ] **Step 7: Commit**

```bash
git add src/endless_war/simulation/systems/ src/endless_war/simulation/engine.py tests/test_economy.py
git commit -m "feat: converging economy and recruitment systems"
```

---

### Task 5: Supply propagation

**Files:**
- Create: `src/endless_war/simulation/systems/supply.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_supply.py`

**Interfaces:**
- Consumes: `clamp` from Task 4, `generate_world` from Task 3
- Produces: `update_supply(world, rng, config) -> None` writing `Province.supply_value`

- [ ] **Step 1: Write the failing supply test**

```python
# tests/test_supply.py
import random

from endless_war.config import load_config
from endless_war.simulation.systems.supply import update_supply
from endless_war.simulation.worldgen import generate_world


def test_capital_is_fully_supplied() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    for fac in w.factions.values():
        assert w.provinces[fac.capital_province_id].supply_value == 1.0


def test_supply_decays_with_distance_from_capital() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    fac = w.factions[0]
    capital = w.provinces[fac.capital_province_id]
    neighbour = w.provinces[
        next(n for n in capital.neighbors if w.provinces[n].controller_faction_id == fac.id)
    ]
    assert neighbour.supply_value < capital.supply_value


def test_supply_is_always_within_bounds() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    update_supply(w, random.Random(1), cfg)
    floor = cfg["balance"]["min_supply"]
    for prov in w.provinces.values():
        assert floor <= prov.supply_value <= 1.0


def test_province_cut_off_from_its_capital_drops_to_minimum() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    # Find one of this faction's provinces that is not the capital, then hand
    # every one of its neighbours to another faction, isolating it.
    target = next(
        p for p in w.provinces.values()
        if p.controller_faction_id == fac.id and not p.is_capital
    )
    for nid in target.neighbors:
        w.provinces[nid].controller_faction_id = 1 if fac.id != 1 else 2
    update_supply(w, random.Random(1), cfg)
    assert target.supply_value == cfg["balance"]["min_supply"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_supply.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.supply'`

- [ ] **Step 3: Write the supply system**

```python
# src/endless_war/simulation/systems/supply.py
"""Supply propagation.

Follows the model in docs/simulation-notes.md: capitals and industrial centres
generate supply, it spreads only through provinces the same faction controls,
and poor infrastructure makes each hop cost more.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems import clamp

INDUSTRIAL_SOURCE_THRESHOLD = 1.5


def update_supply(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Recompute `supply_value` for every province by BFS from supply sources."""
    decay: float = config["balance"]["base_supply_decay_per_hop"]
    floor: float = config["balance"]["min_supply"]

    for prov in world.provinces.values():
        prov.supply_value = floor

    for fid in sorted(world.factions):
        sources = [
            pid
            for pid in sorted(world.provinces)
            if world.provinces[pid].controller_faction_id == fid
            and (
                world.provinces[pid].is_capital
                or world.provinces[pid].industry >= INDUSTRIAL_SOURCE_THRESHOLD
            )
        ]
        # A faction that controls neither its capital nor any industrial centre
        # supplies nothing; every province stays at the floor.
        if not sources:
            continue

        cost: dict[int, float] = {pid: 0.0 for pid in sources}
        queue: deque[int] = deque(sources)
        while queue:
            pid = queue.popleft()
            prov = world.provinces[pid]
            for nid in prov.neighbors:
                neighbour = world.provinces[nid]
                if neighbour.controller_faction_id != fid:
                    continue
                hop = decay / max(0.3, neighbour.infrastructure)
                candidate = cost[pid] + hop
                if candidate < cost.get(nid, float("inf")):
                    cost[nid] = candidate
                    queue.append(nid)

        for pid, total in cost.items():
            world.provinces[pid].supply_value = clamp(1.0 - total, floor, 1.0)
```

- [ ] **Step 4: Wire it into the pipeline**

In `engine.py`, add the import and replace the `# supply` marker with `update_supply(self.world, self.rng, self.config)`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 4 new supply tests pass

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/systems/supply.py src/endless_war/simulation/engine.py tests/test_supply.py
git commit -m "feat: supply propagation with infrastructure-weighted decay"
```

---

### Task 6: Armies, movement, and army supply draw

**Files:**
- Create: `src/endless_war/simulation/systems/movement.py`
- Modify: `src/endless_war/simulation/worldgen.py`
- Modify: `src/endless_war/domain/models.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_movement.py`

**Interfaces:**
- Consumes: Tasks 3–5
- Produces: `generate_armies(world, rng, config) -> None`; `update_movement(world, rng, config) -> None`; `Army.destination_id: int | None`, `Army.stance: str`; `armies_in(world, province_id) -> list[Army]`

- [ ] **Step 1: Write the failing movement test**

```python
# tests/test_movement.py
import random

from endless_war.config import load_config
from endless_war.simulation.systems.movement import armies_in, update_movement
from endless_war.simulation.worldgen import generate_world


def test_every_faction_starts_with_armies() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid in w.factions:
        assert [a for a in w.armies.values() if a.faction_id == fid]


def test_army_moves_only_to_an_adjacent_province() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    origin = army.province_id
    army.destination_id = w.provinces[origin].neighbors[0]
    update_movement(w, random.Random(1), cfg)
    assert army.province_id in (origin, w.provinces[origin].neighbors[0])


def test_army_without_destination_stays_put() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    army.destination_id = None
    origin = army.province_id
    update_movement(w, random.Random(1), cfg)
    assert army.province_id == origin


def test_move_into_hostile_province_is_blocked_until_battle_resolves() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    target = w.provinces[army.province_id].neighbors[0]
    enemy = (army.faction_id + 1) % len(w.factions)
    w.factions[army.faction_id].at_war_with = {enemy}
    w.factions[enemy].at_war_with = {army.faction_id}
    w.provinces[target].controller_faction_id = enemy
    defender = next(
        a for a in w.armies.values() if a.faction_id == enemy
    )
    defender.province_id = target
    army.destination_id = target
    update_movement(w, random.Random(1), cfg)
    assert army.province_id != target, "cannot walk into a defended hostile province"


def test_armies_in_returns_only_that_province() -> None:
    w = generate_world(seed=42, config=load_config())
    army = w.armies[0]
    found = armies_in(w, army.province_id)
    assert army in found
    assert all(a.province_id == army.province_id for a in found)


def test_organization_recovers_when_well_supplied_and_idle() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    army = w.armies[0]
    army.organization = 0.4
    army.supply = 1.0
    army.destination_id = None
    update_movement(w, random.Random(1), cfg)
    assert army.organization > 0.4


def test_bounded_attributes_stay_in_range_over_many_ticks() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    rng = random.Random(1)
    for _ in range(500):
        update_movement(w, rng, cfg)
    for army in w.armies.values():
        for attr in ("morale", "organization", "supply", "training", "equipment"):
            assert 0.0 <= getattr(army, attr) <= 1.0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_movement.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.movement'`

- [ ] **Step 3: Add the new `Army` fields**

In `src/endless_war/domain/models.py`, add to `Army` after `supply`:

```python
    destination_id: int | None = None
    stance: str = "balanced"
```

- [ ] **Step 4: Add army generation to worldgen.py**

Append to `src/endless_war/simulation/worldgen.py`, and call it from `generate_world` after `generate_factions`:

```python
ARMIES_PER_FACTION = 3


def generate_armies(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Place each faction's starting armies on its capital and border provinces."""
    from endless_war.domain.models import Army

    next_id = 0
    for fid in sorted(world.factions):
        fac = world.factions[fid]
        owned = [
            pid for pid in sorted(world.provinces)
            if world.provinces[pid].owner_faction_id == fid
        ]
        border = [
            pid for pid in owned
            if any(
                world.provinces[n].owner_faction_id != fid
                for n in world.provinces[pid].neighbors
            )
        ]
        placements = [fac.capital_province_id]
        placements += rng.sample(border, k=min(ARMIES_PER_FACTION - 1, len(border)))
        while len(placements) < ARMIES_PER_FACTION:
            placements.append(rng.choice(owned))

        for province_id in placements:
            strength = int(fac.manpower * rng.uniform(0.08, 0.16))
            fac.manpower = max(0, fac.manpower - strength)
            world.armies[next_id] = Army(
                id=next_id,
                faction_id=fid,
                province_id=province_id,
                manpower=strength,
                equipment=round(rng.uniform(0.6, 0.95), 3),
                morale=round(rng.uniform(0.6, 0.9), 3),
                organization=round(rng.uniform(0.7, 1.0), 3),
                training=round(rng.uniform(0.5, 0.85), 3),
            )
            next_id += 1
```

In `generate_world`, add `generate_armies(world, rng, config)` after `generate_factions(world, rng, config)`.

- [ ] **Step 5: Write the movement system**

```python
# src/endless_war/simulation/systems/movement.py
"""Army movement, supply draw, and recovery.

An army advances at most one province per tick and cannot enter a province
defended by a hostile army — that is a battle, resolved by the battle system
before movement is retried on a later tick.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState
from endless_war.simulation.systems import clamp


def armies_in(world: WorldState, province_id: int) -> list[Army]:
    """Every army standing in `province_id`, in deterministic id order."""
    return [world.armies[aid] for aid in sorted(world.armies)
            if world.armies[aid].province_id == province_id]


def hostile_armies_in(world: WorldState, province_id: int, faction_id: int) -> list[Army]:
    """Armies in `province_id` belonging to a faction at war with `faction_id`."""
    at_war = world.factions[faction_id].at_war_with
    return [a for a in armies_in(world, province_id) if a.faction_id in at_war]


def update_movement(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Draw supply, recover, then advance one province toward the destination."""
    org_recovery: float = config["balance"]["organization_recovery_per_tick"]
    morale_recovery: float = config["balance"]["morale_recovery_per_tick"]

    for aid in sorted(world.armies):
        army = world.armies[aid]
        here = world.provinces[army.province_id]

        # Armies draw the supply delivered to the province they occupy.
        army.supply = clamp(army.supply + (here.supply_value - army.supply) * 0.5)

        if army.supply < 0.35:
            army.organization = clamp(army.organization - (0.35 - army.supply) * 0.1)
            army.morale = clamp(army.morale - (0.35 - army.supply) * 0.05)
        elif army.destination_id is None:
            army.organization = clamp(army.organization + org_recovery * army.supply)
            army.morale = clamp(army.morale + morale_recovery * army.supply)

        if army.destination_id is None:
            continue

        target_id = army.destination_id
        if target_id not in here.neighbors:
            army.destination_id = None
            continue
        if hostile_armies_in(world, target_id, army.faction_id):
            continue  # blocked: the battle system resolves this
        if army.organization < 0.15:
            army.destination_id = None
            continue

        army.province_id = target_id
        army.destination_id = None
        army.organization = clamp(army.organization - 0.03)
```

- [ ] **Step 6: Wire it into the pipeline**

In `engine.py`, import `update_movement` and replace the `# movement` marker with `update_movement(self.world, self.rng, self.config)`.

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 7 new movement tests pass

- [ ] **Step 8: Commit**

```bash
git add src/endless_war/simulation/systems/movement.py src/endless_war/simulation/worldgen.py src/endless_war/domain/models.py src/endless_war/simulation/engine.py tests/test_movement.py
git commit -m "feat: armies, movement, and supply draw"
```

---

### Task 7: Battle resolution

**Files:**
- Create: `src/endless_war/simulation/systems/battle.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_battle.py`

**Interfaces:**
- Consumes: `armies_in`, `hostile_armies_in` from Task 6; `TERRAIN_DEFENCE` from Task 2
- Produces: `effective_power(army, world, defending: bool) -> float`; `resolve_battles(world, rng, config) -> list[dict]` returning battle records `{"province_id", "attacker_faction", "defender_faction", "attacker_losses", "defender_losses", "attacker_broke", "defender_broke"}`

- [ ] **Step 1: Write the failing battle test**

```python
# tests/test_battle.py
import random

from endless_war.config import load_config
from endless_war.domain.models import Army
from endless_war.simulation.systems.battle import effective_power, resolve_battles
from endless_war.simulation.worldgen import generate_world


def _two_army_standoff(cfg):
    """Put one army from faction 0 and one from faction 1 in the same province, at war."""
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    province = w.factions[1].capital_province_id
    w.provinces[province].controller_faction_id = 1
    w.armies[0] = Army(id=0, faction_id=0, province_id=province, manpower=50_000,
                       equipment=0.8, morale=0.8, organization=0.9, training=0.7, supply=0.9)
    w.armies[1] = Army(id=1, faction_id=1, province_id=province, manpower=50_000,
                       equipment=0.8, morale=0.8, organization=0.9, training=0.7, supply=0.9)
    return w


def test_effective_power_rises_with_manpower() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    weak = effective_power(w.armies[0], w, defending=False)
    w.armies[0].manpower = 100_000
    assert effective_power(w.armies[0], w, defending=False) > weak


def test_effective_power_is_zero_for_an_empty_army() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].manpower = 0
    assert effective_power(w.armies[0], w, defending=False) == 0.0


def test_defender_gains_a_terrain_bonus() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.provinces[w.armies[0].province_id].terrain = "mountain"
    attacking = effective_power(w.armies[0], w, defending=False)
    defending = effective_power(w.armies[0], w, defending=True)
    assert defending > attacking


def test_battle_inflicts_casualties_on_both_sides() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    records = resolve_battles(w, random.Random(1), cfg)
    assert len(records) == 1
    assert records[0]["attacker_losses"] > 0
    assert records[0]["defender_losses"] > 0
    assert w.armies[0].manpower < 50_000
    assert w.armies[1].manpower < 50_000


def test_casualties_are_bounded_per_tick() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    records = resolve_battles(w, random.Random(1), cfg)
    # No side may lose more than 10% of its strength in a single 6-hour tick.
    assert records[0]["attacker_losses"] < 5_000
    assert records[0]["defender_losses"] < 5_000


def test_stronger_side_loses_a_smaller_fraction() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].manpower = 200_000
    records = resolve_battles(w, random.Random(1), cfg)
    # Absolute losses scale with army size, so compare FRACTIONS lost.
    attacker_fraction = records[0]["attacker_losses"] / 200_000
    defender_fraction = records[0]["defender_losses"] / 50_000
    assert attacker_fraction < defender_fraction


def test_battle_never_drives_values_out_of_bounds() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    rng = random.Random(1)
    for _ in range(300):
        resolve_battles(w, rng, cfg)
    for army in w.armies.values():
        assert army.manpower >= 0
        for attr in ("morale", "organization", "supply"):
            assert 0.0 <= getattr(army, attr) <= 1.0


def test_broken_army_is_flagged_and_retreats_next_tick() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    w.armies[0].organization = 0.05
    records = resolve_battles(w, random.Random(1), cfg)
    assert records[0]["attacker_broke"] is True


def test_faction_casualty_counters_accumulate() -> None:
    cfg = load_config()
    w = _two_army_standoff(cfg)
    resolve_battles(w, random.Random(1), cfg)
    assert w.factions[0].casualties > 0
    assert w.factions[1].casualties > 0
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_battle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.battle'`

- [ ] **Step 3: Write the battle system**

The formula is a *share of combined power*, never a raw ratio, so it is bounded on `[0, 1]` no matter how lopsided the fight. Per-tick casualty rates are therefore capped at `2 × base_casualty_rate` = 4%.

```python
# src/endless_war/simulation/systems/battle.py
"""Battle resolution.

docs/simulation-notes.md asks for bounded, explainable, testable formulas that
stay stable over long simulations. Power is combined multiplicatively from
normalized factors; losses are driven by each side's SHARE of combined power,
which keeps every per-tick rate on [0, 2 x base_casualty_rate].
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState
from endless_war.simulation.systems import clamp
from endless_war.simulation.systems.movement import armies_in
from endless_war.simulation.worldgen import TERRAIN_DEFENCE


def effective_power(army: Army, world: WorldState, defending: bool) -> float:
    """Combat power from normalized factors. Zero for an army with no men."""
    if army.manpower <= 0:
        return 0.0
    province = world.provinces[army.province_id]
    quality = (
        clamp(army.equipment)
        * (0.35 + 0.65 * clamp(army.morale))
        * (0.30 + 0.70 * clamp(army.organization))
        * (0.50 + 0.50 * clamp(army.training))
        * (0.40 + 0.60 * clamp(army.supply))
    )
    terrain = TERRAIN_DEFENCE.get(province.terrain, 1.0) if defending else 1.0
    return army.manpower * quality * terrain


def _battle_provinces(world: WorldState) -> list[int]:
    """Provinces holding armies of two mutually hostile factions."""
    contested: list[int] = []
    for pid in sorted(world.provinces):
        present = armies_in(world, pid)
        factions = {a.faction_id for a in present if a.manpower > 0}
        if len(factions) < 2:
            continue
        for fid in sorted(factions):
            if world.factions[fid].at_war_with & (factions - {fid}):
                contested.append(pid)
                break
    return contested


def resolve_battles(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve one tick of combat in every contested province."""
    base: float = config["balance"]["base_casualty_rate"]
    attacker_break: float = config["balance"]["attacker_break_organization"]
    defender_break: float = config["balance"]["defender_break_organization"]
    records: list[dict[str, Any]] = []

    for pid in _battle_provinces(world):
        province = world.provinces[pid]
        present = [a for a in armies_in(world, pid) if a.manpower > 0]
        defender_faction = province.controller_faction_id
        defenders = [a for a in present if a.faction_id == defender_faction]
        attackers = [a for a in present if a.faction_id != defender_faction]
        if not defenders or not attackers:
            continue
        attacker_faction = attackers[0].faction_id

        att_power = sum(effective_power(a, world, defending=False) for a in attackers)
        def_power = sum(effective_power(a, world, defending=True) for a in defenders)
        att_power *= rng.uniform(0.9, 1.1)
        def_power *= rng.uniform(0.9, 1.1)
        total = att_power + def_power
        if total <= 0:
            continue

        attacker_share = att_power / total          # bounded [0, 1]
        attacker_rate = base * 2.0 * (1.0 - attacker_share)
        defender_rate = base * 2.0 * attacker_share

        attacker_losses = _apply_losses(attackers, attacker_rate)
        defender_losses = _apply_losses(defenders, defender_rate)

        world.factions[attacker_faction].casualties += attacker_losses
        world.factions[defender_faction].casualties += defender_losses

        attacker_broke = all(a.organization <= attacker_break for a in attackers)
        defender_broke = all(d.organization <= defender_break for d in defenders)

        records.append({
            "province_id": pid,
            "attacker_faction": attacker_faction,
            "defender_faction": defender_faction,
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "attacker_broke": attacker_broke,
            "defender_broke": defender_broke,
        })
    return records


def _apply_losses(armies: list[Army], rate: float) -> int:
    """Apply a per-tick casualty rate, returning total men lost."""
    lost = 0
    for army in armies:
        casualties = int(army.manpower * rate)
        army.manpower = max(0, army.manpower - casualties)
        army.organization = clamp(army.organization - rate * 2.5)
        army.morale = clamp(army.morale - rate * 1.2)
        army.equipment = clamp(army.equipment - rate * 0.4)
        lost += casualties
    return lost
```

- [ ] **Step 4: Wire it into the pipeline**

In `engine.py`, import `resolve_battles` and replace the `# battles` marker. Keep the returned records — the next task consumes them:

```python
        battle_records = resolve_battles(self.world, self.rng, self.config)
        # control changes
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 9 new battle tests pass

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/systems/battle.py src/endless_war/simulation/engine.py tests/test_battle.py
git commit -m "feat: bounded battle resolution by power share"
```

---

### Task 8: Territory control changes

**Files:**
- Create: `src/endless_war/simulation/systems/control.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_control.py`

**Interfaces:**
- Consumes: battle records from Task 7, `armies_in` from Task 6
- Produces: `apply_control_changes(world, rng, config, battle_records) -> list[dict]` returning capture records `{"province_id", "from_faction", "to_faction"}`

- [ ] **Step 1: Write the failing control test**

```python
# tests/test_control.py
import random

from endless_war.config import load_config
from endless_war.domain.models import Army
from endless_war.simulation.systems.control import apply_control_changes
from endless_war.simulation.worldgen import generate_world


def _border_province(w, faction_id, enemy_id):
    """A province controlled by `faction_id` that touches `enemy_id` territory."""
    for pid in sorted(w.provinces):
        prov = w.provinces[pid]
        if prov.controller_faction_id != faction_id or prov.is_capital:
            continue
        if any(w.provinces[n].controller_faction_id == enemy_id for n in prov.neighbors):
            return pid
    raise AssertionError(f"no border province between {faction_id} and {enemy_id}")


def test_lone_army_captures_an_undefended_hostile_province() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    target = _border_province(w, 1, 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    captures = apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].controller_faction_id == 0
    assert captures == [{"province_id": target, "from_faction": 1, "to_faction": 0}]


def test_owner_is_unchanged_by_occupation() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    target = _border_province(w, 1, 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].owner_faction_id == 1, "occupation must not transfer ownership"


def test_defended_province_does_not_change_hands() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    target = _border_province(w, 1, 0)
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000)
    w.armies[1] = Army(id=1, faction_id=1, province_id=target, manpower=30_000)
    apply_control_changes(w, random.Random(1), cfg, [])
    assert w.provinces[target].controller_faction_id == 1


def test_broken_attacker_retreats_to_a_friendly_neighbour() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    target = _border_province(w, 1, 0)
    friendly = next(
        n for n in w.provinces[target].neighbors if w.provinces[n].controller_faction_id == 0
    )
    w.armies[0] = Army(id=0, faction_id=0, province_id=target, manpower=30_000, organization=0.05)
    apply_control_changes(w, random.Random(1), cfg, [
        {"province_id": target, "attacker_faction": 0, "defender_faction": 1,
         "attacker_losses": 10, "defender_losses": 10,
         "attacker_broke": True, "defender_broke": False},
    ])
    assert w.armies[0].province_id == friendly


def test_annihilated_army_is_removed() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.armies.clear()
    w.armies[0] = Army(id=0, faction_id=0, province_id=0, manpower=0)
    apply_control_changes(w, random.Random(1), cfg, [])
    assert 0 not in w.armies


def test_province_count_is_conserved() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    for _ in range(100):
        apply_control_changes(w, random.Random(1), cfg, [])
    controlled = [p.controller_faction_id for p in w.provinces.values()]
    assert len(controlled) == 96
    assert all(c in w.factions for c in controlled)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_control.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.control'`

- [ ] **Step 3: Write the control system**

```python
# src/endless_war/simulation/systems/control.py
"""Occupation, retreat, and army cleanup.

Control changes; ownership does not. Keeping `owner_faction_id` fixed is what
lets later work model liberation, resistance, and war-goal evaluation.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import WorldState
from endless_war.simulation.systems.movement import armies_in

OCCUPIED_SUPPLY_PENALTY = 0.5


def apply_control_changes(
    world: WorldState,
    rng: random.Random,
    config: dict[str, Any],
    battle_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Transfer control of undefended provinces, retreat broken armies, cull the dead."""
    captures: list[dict[str, Any]] = []

    for record in battle_records:
        if not record["attacker_broke"]:
            continue
        province_id = record["province_id"]
        for army in armies_in(world, province_id):
            if army.faction_id != record["attacker_faction"]:
                continue
            friendly = [
                n for n in world.provinces[province_id].neighbors
                if world.provinces[n].controller_faction_id == army.faction_id
            ]
            if friendly:
                army.province_id = friendly[0]
                army.destination_id = None

    for pid in sorted(world.provinces):
        province = world.provinces[pid]
        present = [a for a in armies_in(world, pid) if a.manpower > 0]
        if not present:
            continue
        occupiers = {a.faction_id for a in present}
        if len(occupiers) != 1:
            continue
        occupier = next(iter(occupiers))
        current = province.controller_faction_id
        if occupier == current:
            continue
        if current is not None and occupier not in world.factions[current].at_war_with:
            continue
        captures.append(
            {"province_id": pid, "from_faction": current, "to_faction": occupier}
        )
        province.controller_faction_id = occupier
        province.supply_value *= OCCUPIED_SUPPLY_PENALTY

    for aid in [aid for aid in sorted(world.armies) if world.armies[aid].manpower <= 0]:
        del world.armies[aid]

    return captures
```

- [ ] **Step 4: Wire it into the pipeline**

In `engine.py`, import `apply_control_changes` and replace the `# control changes` marker:

```python
        capture_records = apply_control_changes(
            self.world, self.rng, self.config, battle_records
        )
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 6 new control tests pass

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/simulation/systems/control.py src/endless_war/simulation/engine.py tests/test_control.py
git commit -m "feat: occupation, retreat, and army cleanup"
```

---

### Task 9: War exhaustion, declarations, and peace

**Files:**
- Create: `src/endless_war/simulation/systems/diplomacy.py`
- Modify: `src/endless_war/domain/models.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_diplomacy.py`

**Interfaces:**
- Consumes: Tasks 3–8
- Produces: `War` dataclass; `update_exhaustion(world, rng, config) -> None`; `update_diplomacy(world, rng, config) -> list[dict]` returning `{"kind": "war_declared"|"peace", "attacker", "defender"}`; `WorldState.wars: dict[int, War]`, `WorldState.next_war_id: int`

- [ ] **Step 1: Write the failing diplomacy test**

```python
# tests/test_diplomacy.py
import random

from endless_war.config import load_config
from endless_war.simulation.systems.diplomacy import update_diplomacy, update_exhaustion
from endless_war.simulation.worldgen import generate_world


def test_exhaustion_rises_with_casualties_and_stays_bounded() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {1}
    w.factions[1].at_war_with = {0}
    fac.casualties = fac.manpower * 2
    for _ in range(200):
        update_exhaustion(w, random.Random(1), cfg)
    assert 0.0 <= fac.exhaustion <= 1.0
    assert fac.exhaustion > 0.0


def test_exhaustion_decays_in_peacetime() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = set()
    fac.exhaustion = 0.5
    for _ in range(50):
        update_exhaustion(w, random.Random(1), cfg)
    assert fac.exhaustion < 0.5


def test_war_support_falls_as_exhaustion_rises() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.at_war_with = {1}
    fac.exhaustion = 0.9
    fac.war_support = 0.8
    update_exhaustion(w, random.Random(1), cfg)
    assert fac.war_support < 0.8


def test_a_war_eventually_gets_declared() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    # Guarantee faction 0 clears the strength ratio, so this tests the code path
    # rather than the luck of the seed.
    w.factions[0].manpower *= 10
    rng = random.Random(1)
    for _ in range(5000):
        update_diplomacy(w, rng, cfg)
        if w.wars:
            break
    assert w.wars, "no war was ever declared"


def test_declaration_is_mutual_and_recorded() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].manpower *= 10
    rng = random.Random(1)
    for _ in range(5000):
        events = update_diplomacy(w, rng, cfg)
        declared = [e for e in events if e["kind"] == "war_declared"]
        if declared:
            a, d = declared[0]["attacker"], declared[0]["defender"]
            assert d in w.factions[a].at_war_with
            assert a in w.factions[d].at_war_with
            return
    raise AssertionError("no war was declared")


def test_exhausted_factions_make_peace() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    from endless_war.domain.models import War
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    w.wars[0] = War(id=0, attackers={0}, defenders={1},
                    started_at=w.current_time, status="active")
    w.next_war_id = 1
    w.factions[0].exhaustion = 0.9
    w.factions[1].exhaustion = 0.9
    events = update_diplomacy(w, random.Random(1), cfg)
    assert any(e["kind"] == "peace" for e in events)
    assert w.factions[0].at_war_with == set()
    assert w.wars[0].status == "ended"


def test_a_faction_is_never_at_war_with_itself() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    rng = random.Random(1)
    for _ in range(3000):
        update_diplomacy(w, rng, cfg)
    for fid, fac in w.factions.items():
        assert fid not in fac.at_war_with
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_diplomacy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.diplomacy'`

- [ ] **Step 3: Add the `War` dataclass and world fields**

In `src/endless_war/domain/models.py`, add after `Army`:

```python
@dataclass(slots=True)
class War:
    id: int
    attackers: set[int]
    defenders: set[int]
    started_at: datetime
    status: str = "active"
    last_capture_tick: int = 0
```

And extend `WorldState` with:

```python
    wars: dict[int, War] = field(default_factory=dict)
    next_war_id: int = 0
    expected_province_count: int = 0
```

- [ ] **Step 4: Write the diplomacy system**

```python
# src/endless_war/simulation/systems/diplomacy.py
"""War exhaustion, declarations, and peace.

specs/01-game-design.md requires that individual wars end while the world does
not. Peace triggers on mutual exhaustion or on a stalemate with no captures.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import War, WorldState
from endless_war.simulation.systems import clamp


def update_exhaustion(world: WorldState, rng: random.Random, config: dict[str, Any]) -> None:
    """Grow exhaustion from accumulated casualties; decay it in peacetime."""
    factor: float = config["balance"]["exhaustion_per_casualty_fraction"]
    decay: float = config["balance"]["exhaustion_decay_per_tick"]

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.at_war_with:
            army_strength = sum(
                a.manpower for a in world.armies.values() if a.faction_id == fid
            )
            base = max(1, fac.manpower + army_strength)
            fac.exhaustion = clamp(fac.exhaustion + (fac.casualties / base) * factor * 0.001)
        else:
            fac.exhaustion = clamp(fac.exhaustion - decay)
        fac.war_support = clamp(0.9 - fac.exhaustion * 0.8)
        fac.stability = clamp(fac.stability + (0.002 if not fac.at_war_with else -0.0005))


def _strength(world: WorldState, faction_id: int) -> float:
    army = sum(a.manpower for a in world.armies.values() if a.faction_id == faction_id)
    return army + world.factions[faction_id].manpower * 0.5


def _neighbouring_factions(world: WorldState, faction_id: int) -> list[int]:
    found: set[int] = set()
    for pid in sorted(world.provinces):
        prov = world.provinces[pid]
        if prov.controller_faction_id != faction_id:
            continue
        for nid in prov.neighbors:
            other = world.provinces[nid].controller_faction_id
            if other is not None and other != faction_id:
                found.add(other)
    return sorted(found)


def update_diplomacy(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Declare new wars and end exhausted or stalemated ones."""
    ratio_needed: float = config["balance"]["war_declaration_strength_ratio"]
    max_exhaustion: float = config["balance"]["war_declaration_max_exhaustion"]
    peace_exhaustion: float = config["balance"]["peace_exhaustion_threshold"]
    stalemate: int = config["balance"]["peace_stalemate_ticks"]
    events: list[dict[str, Any]] = []

    for war_id in sorted(world.wars):
        war = world.wars[war_id]
        if war.status != "active":
            continue
        involved = sorted(war.attackers | war.defenders)
        worn_out = all(world.factions[f].exhaustion >= peace_exhaustion for f in involved)
        stalled = world.tick_count - war.last_capture_tick > stalemate
        if not (worn_out or stalled):
            continue
        war.status = "ended"
        for a in war.attackers:
            for d in war.defenders:
                world.factions[a].at_war_with.discard(d)
                world.factions[d].at_war_with.discard(a)
        events.append({
            "kind": "peace",
            "attacker": sorted(war.attackers)[0],
            "defender": sorted(war.defenders)[0],
        })

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.at_war_with or fac.exhaustion > max_exhaustion:
            continue
        if rng.random() > 0.004:
            continue
        candidates = [
            other for other in _neighbouring_factions(world, fid)
            if not world.factions[other].at_war_with
            and _strength(world, fid) > _strength(world, other) * ratio_needed
        ]
        if not candidates:
            continue
        target = rng.choice(candidates)
        fac.at_war_with.add(target)
        world.factions[target].at_war_with.add(fid)
        world.wars[world.next_war_id] = War(
            id=world.next_war_id,
            attackers={fid},
            defenders={target},
            started_at=world.current_time,
            last_capture_tick=world.tick_count,
        )
        world.next_war_id += 1
        events.append({"kind": "war_declared", "attacker": fid, "defender": target})

    return events
```

- [ ] **Step 5: Wire it into the pipeline**

In `engine.py`, import both functions and replace the `# exhaustion/stability` and `# diplomacy` markers. Also record captures against the active war so the stalemate timer works:

```python
        update_exhaustion(self.world, self.rng, self.config)
        if capture_records:
            for war in self.world.wars.values():
                if war.status == "active":
                    war.last_capture_tick = self.world.tick_count
        diplomacy_events = update_diplomacy(self.world, self.rng, self.config)
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 7 new diplomacy tests pass

- [ ] **Step 7: Commit**

```bash
git add src/endless_war/simulation/systems/diplomacy.py src/endless_war/domain/models.py src/endless_war/simulation/engine.py tests/test_diplomacy.py
git commit -m "feat: war exhaustion, declarations, and peace"
```

---

### Task 10: Strategic AI

**Files:**
- Modify: `src/endless_war/ai/strategic.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_strategic_ai.py`

**Interfaces:**
- Consumes: Tasks 3–9
- Produces: `choose_strategic_actions(world, rng, config) -> None` — replaces the existing placeholder, sets `Army.destination_id` and `Army.stance`

- [ ] **Step 1: Write the failing AI test**

```python
# tests/test_strategic_ai.py
import random

from endless_war.ai.strategic import choose_strategic_actions
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world


def test_at_peace_armies_are_given_no_offensive_orders() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert w.provinces[army.destination_id].controller_faction_id == army.faction_id


def test_at_war_some_army_is_ordered_toward_the_enemy() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    # Place one of faction 0's armies on the shared border explicitly; the
    # starting layout does not guarantee 0 and 1 are neighbours.
    border = next(
        pid for pid in sorted(w.provinces)
        if w.provinces[pid].controller_faction_id == 0
        and any(w.provinces[n].controller_faction_id == 1 for n in w.provinces[pid].neighbors)
    )
    next(a for a in w.armies.values() if a.faction_id == 0).province_id = border
    choose_strategic_actions(w, random.Random(1), cfg)
    ordered = [
        a for a in w.armies.values()
        if a.faction_id == 0
        and a.destination_id is not None
        and w.provinces[a.destination_id].controller_faction_id == 1
    ]
    assert ordered, "faction 0 should push into faction 1 territory"


def test_destinations_are_always_adjacent() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    choose_strategic_actions(w, random.Random(1), cfg)
    for army in w.armies.values():
        if army.destination_id is not None:
            assert army.destination_id in w.provinces[army.province_id].neighbors


def test_broken_army_is_ordered_to_withdraw_to_friendly_ground() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    w.factions[0].at_war_with = {1}
    w.factions[1].at_war_with = {0}
    army = next(a for a in w.armies.values() if a.faction_id == 0)
    army.organization = 0.1
    army.morale = 0.1
    choose_strategic_actions(w, random.Random(1), cfg)
    if army.destination_id is not None:
        assert w.provinces[army.destination_id].controller_faction_id == 0
    assert army.stance == "withdrawal"


def test_ai_is_deterministic_for_a_given_seed() -> None:
    cfg = load_config()
    a = generate_world(seed=42, config=cfg)
    b = generate_world(seed=42, config=cfg)
    for w in (a, b):
        w.factions[0].at_war_with = {1}
        w.factions[1].at_war_with = {0}
    choose_strategic_actions(a, random.Random(7), cfg)
    choose_strategic_actions(b, random.Random(7), cfg)
    assert [x.destination_id for x in a.armies.values()] == [
        x.destination_id for x in b.armies.values()
    ]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_strategic_ai.py -v`
Expected: FAIL — `TypeError` / assertion failures, because the placeholder returns `[]` and sets nothing

- [ ] **Step 3: Replace the AI placeholder**

```python
# src/endless_war/ai/strategic.py
"""Strategic AI.

One decision per army per tick, from local information only: withdraw when
broken, attack the weakest adjacent hostile province, otherwise reinforce a
threatened friendly border province. No global planner — fronts emerge.
"""

from __future__ import annotations

import random
from typing import Any

from endless_war.domain.models import Army, WorldState

BROKEN_ORGANIZATION = 0.30
BROKEN_MORALE = 0.25


def _hostile_neighbours(world: WorldState, army: Army) -> list[int]:
    at_war = world.factions[army.faction_id].at_war_with
    return [
        nid for nid in world.provinces[army.province_id].neighbors
        if world.provinces[nid].controller_faction_id in at_war
    ]


def _friendly_neighbours(world: WorldState, army: Army) -> list[int]:
    return [
        nid for nid in world.provinces[army.province_id].neighbors
        if world.provinces[nid].controller_faction_id == army.faction_id
    ]


def _defenders_in(world: WorldState, province_id: int, faction_id: int) -> int:
    return sum(
        a.manpower for a in world.armies.values()
        if a.province_id == province_id and a.faction_id != faction_id
    )


def choose_strategic_actions(
    world: WorldState, rng: random.Random, config: dict[str, Any]
) -> None:
    """Set `destination_id` and `stance` for every army."""
    for aid in sorted(world.armies):
        army = world.armies[aid]
        army.destination_id = None

        broken = army.organization < BROKEN_ORGANIZATION or army.morale < BROKEN_MORALE
        friendly = _friendly_neighbours(world, army)
        if broken:
            army.stance = "withdrawal"
            if friendly:
                friendly.sort(key=lambda pid: -world.provinces[pid].supply_value)
                army.destination_id = friendly[0]
            continue

        hostile = _hostile_neighbours(world, army)
        if hostile:
            hostile.sort(key=lambda pid: (_defenders_in(world, pid, army.faction_id), pid))
            weakest = hostile[0]
            if _defenders_in(world, weakest, army.faction_id) < army.manpower * 1.2:
                army.stance = "aggressive"
                army.destination_id = weakest
            else:
                army.stance = "defensive"
            continue

        army.stance = "balanced"
        threatened = [
            pid for pid in friendly
            if any(
                world.provinces[n].controller_faction_id
                in world.factions[army.faction_id].at_war_with
                for n in world.provinces[pid].neighbors
            )
        ]
        if threatened:
            army.destination_id = sorted(threatened)[0]
```

- [ ] **Step 4: Wire it into the pipeline**

In `engine.py`, import `choose_strategic_actions` and replace the `# AI decisions` marker with `choose_strategic_actions(self.world, self.rng, self.config)`. It must sit **before** `update_movement`.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 5 new AI tests pass

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/ai/strategic.py src/endless_war/simulation/engine.py tests/test_strategic_ai.py
git commit -m "feat: local-information strategic AI"
```

---

### Task 11: Event log

**Files:**
- Create: `src/endless_war/simulation/systems/events.py`
- Modify: `src/endless_war/domain/models.py`
- Modify: `src/endless_war/simulation/engine.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: battle, capture, and diplomacy records from Tasks 7–9
- Produces: `Event` dataclass; `record_events(world, config, battle_records, capture_records, diplomacy_events) -> None`; `WorldState.events: deque[Event]`, `WorldState.next_event_id: int`

- [ ] **Step 1: Write the failing events test**

```python
# tests/test_events.py
from datetime import datetime, timezone

from endless_war.config import load_config
from endless_war.simulation.systems.events import MAX_EVENTS, record_events
from endless_war.simulation.worldgen import generate_world


def test_war_declaration_is_logged_as_critical() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [], [], [{"kind": "war_declared", "attacker": 0, "defender": 1}])
    assert len(w.events) == 1
    event = w.events[-1]
    assert event.category == "diplomacy"
    assert event.severity == "critical"
    assert "Valdran Hegemony" in event.title or "Valdran Hegemony" in event.body


def test_capture_is_logged_with_both_factions() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [], [{"province_id": 5, "from_faction": 1, "to_faction": 0}], [])
    assert len(w.events) == 1
    assert w.events[-1].category == "territory"
    assert w.events[-1].related_entity_ids == [5, 1, 0]


def test_small_battles_are_not_logged() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [{"province_id": 3, "attacker_faction": 0, "defender_faction": 1,
                            "attacker_losses": 4, "defender_losses": 3,
                            "attacker_broke": False, "defender_broke": False}], [], [])
    assert len(w.events) == 0, "trivial skirmishes must not flood the log"


def test_large_battles_are_logged() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    record_events(w, cfg, [{"province_id": 3, "attacker_faction": 0, "defender_faction": 1,
                            "attacker_losses": 9_000, "defender_losses": 8_000,
                            "attacker_broke": False, "defender_broke": False}], [], [])
    assert len(w.events) == 1
    assert w.events[-1].category == "military"


def test_event_ids_are_unique_and_increasing() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(10):
        record_events(w, cfg, [], [], [{"kind": "peace", "attacker": 0, "defender": 1}])
    ids = [e.id for e in w.events]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_log_is_capped_and_keeps_the_newest() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(MAX_EVENTS + 50):
        record_events(w, cfg, [], [], [{"kind": "peace", "attacker": 0, "defender": 1}])
    assert len(w.events) == MAX_EVENTS
    assert w.events[-1].id > w.events[0].id
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.systems.events'`

- [ ] **Step 3: Add the `Event` dataclass and world fields**

In `src/endless_war/domain/models.py`, add `from collections import deque` at the top, then after `War`:

```python
@dataclass(slots=True)
class Event:
    id: int
    simulated_at: datetime
    category: str
    severity: str
    title: str
    body: str
    related_entity_ids: list[int] = field(default_factory=list)
```

And extend `WorldState`:

```python
    events: deque[Event] = field(default_factory=deque)
    next_event_id: int = 0
```

- [ ] **Step 4: Write the events system**

```python
# src/endless_war/simulation/systems/events.py
"""Event log.

specs/02-ui-and-tray.md: only surface events that matter. The thresholds here
are the first line of defence against a log nobody can read.
"""

from __future__ import annotations

from typing import Any

from endless_war.domain.models import Event, WorldState

MAX_EVENTS = 2000
SIGNIFICANT_BATTLE_LOSSES = 5_000


def _add(world: WorldState, category: str, severity: str, title: str,
         body: str, related: list[int]) -> None:
    world.events.append(Event(
        id=world.next_event_id,
        simulated_at=world.current_time,
        category=category,
        severity=severity,
        title=title,
        body=body,
        related_entity_ids=related,
    ))
    world.next_event_id += 1
    while len(world.events) > MAX_EVENTS:
        world.events.popleft()


def record_events(
    world: WorldState,
    config: dict[str, Any],
    battle_records: list[dict[str, Any]],
    capture_records: list[dict[str, Any]],
    diplomacy_events: list[dict[str, Any]],
) -> None:
    """Turn this tick's system records into history."""
    name = lambda fid: world.factions[fid].name if fid in world.factions else "unknown"  # noqa: E731

    for event in diplomacy_events:
        attacker, defender = event["attacker"], event["defender"]
        if event["kind"] == "war_declared":
            _add(world, "diplomacy", "critical", "War declared",
                 f"{name(attacker)} has declared war on {name(defender)}.",
                 [attacker, defender])
        elif event["kind"] == "peace":
            _add(world, "diplomacy", "critical", "Peace signed",
                 f"{name(attacker)} and {name(defender)} have signed a ceasefire.",
                 [attacker, defender])

    for capture in capture_records:
        _add(world, "territory", "major", "Province captured",
             f"{name(capture['to_faction'])} has taken "
             f"{world.provinces[capture['province_id']].name} from "
             f"{name(capture['from_faction'])}.",
             [capture["province_id"], capture["from_faction"], capture["to_faction"]])

    for battle in battle_records:
        total = battle["attacker_losses"] + battle["defender_losses"]
        if total < SIGNIFICANT_BATTLE_LOSSES:
            continue
        _add(world, "military", "major", "Major engagement",
             f"{total:,} casualties in {world.provinces[battle['province_id']].name} "
             f"between {name(battle['attacker_faction'])} and "
             f"{name(battle['defender_faction'])}.",
             [battle["province_id"]])
```

- [ ] **Step 5: Wire it into the pipeline**

In `engine.py`, import `record_events` and replace the `# events` marker:

```python
        record_events(
            self.world, self.config, battle_records, capture_records, diplomacy_events
        )
        # --- SYSTEM PIPELINE END ---
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS — 6 new event tests pass

- [ ] **Step 7: Commit**

```bash
git add src/endless_war/simulation/systems/events.py src/endless_war/domain/models.py src/endless_war/simulation/engine.py tests/test_events.py
git commit -m "feat: event log with significance thresholds"
```

---

### Task 12: Observatory harness and the 10-year checkpoint

**Files:**
- Create: `src/endless_war/tools/__init__.py`
- Create: `src/endless_war/tools/observe.py`
- Create: `src/endless_war/simulation/invariants.py`
- Modify: `src/endless_war/__main__.py`
- Modify: `pyproject.toml` (register the `slow` marker)
- Test: `tests/test_invariants.py`
- Test: `tests/test_long_run.py`

**Interfaces:**
- Consumes: everything
- Produces: `check_invariants(world) -> list[str]`; `run_observation(seed: int, years: int, config: dict, emit=print) -> WorldState`; `python -m endless_war --years 10 --seed 42`

- [ ] **Step 1: Write the failing invariant and long-run tests**

```python
# tests/test_invariants.py
from endless_war.config import load_config
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world


def test_fresh_world_has_no_violations() -> None:
    assert check_invariants(generate_world(seed=42, config=load_config())) == []


def test_detects_out_of_range_morale() -> None:
    w = generate_world(seed=42, config=load_config())
    w.armies[0].morale = 1.4
    assert any("morale" in v for v in check_invariants(w))


def test_detects_negative_manpower() -> None:
    w = generate_world(seed=42, config=load_config())
    w.factions[0].manpower = -5
    assert any("manpower" in v for v in check_invariants(w))


def test_detects_lost_province() -> None:
    w = generate_world(seed=42, config=load_config())
    del w.provinces[0]
    assert any("province count" in v for v in check_invariants(w))


def test_detects_nan() -> None:
    w = generate_world(seed=42, config=load_config())
    w.factions[0].treasury = float("nan")
    assert any("finite" in v for v in check_invariants(w))
```

```python
# tests/test_long_run.py
"""The CONTINUE_OFFLINE.md checkpoint, as an automated test.

SLOW: the ten-year fixture runs 14 600 ticks and takes minutes, not seconds.
Skip it during tight loops with `-m "not slow"`.
"""

import pytest

pytestmark = pytest.mark.slow

from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_YEAR = 4 * 365


@pytest.fixture(scope="module")
def ten_year_world():
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    engine = SimulationEngine(world, cfg)
    for _ in range(10 * TICKS_PER_YEAR):
        engine.tick()
    return world


def test_invariants_hold_after_ten_years(ten_year_world) -> None:
    assert check_invariants(ten_year_world) == []


def test_wars_started_and_ended(ten_year_world) -> None:
    assert ten_year_world.wars, "no war ever started"
    assert any(w.status == "ended" for w in ten_year_world.wars.values()), "no war ever ended"


def test_fronts_moved(ten_year_world) -> None:
    captures = [e for e in ten_year_world.events if e.category == "territory"]
    assert captures, "no province ever changed hands"


def test_history_accumulated(ten_year_world) -> None:
    assert len(ten_year_world.events) > 10


def test_no_faction_was_silently_annihilated_by_a_bug(ten_year_world) -> None:
    for fid in ten_year_world.factions:
        controlled = [
            p for p in ten_year_world.provinces.values() if p.controller_faction_id == fid
        ]
        owned = [p for p in ten_year_world.provinces.values() if p.owner_faction_id == fid]
        assert owned, f"faction {fid} lost its ownership records entirely"
        _ = controlled  # conquest to zero controlled provinces is legitimate


def test_run_is_reproducible() -> None:
    cfg = load_config()
    results = []
    for _ in range(2):
        world = generate_world(seed=99, config=cfg)
        engine = SimulationEngine(world, cfg)
        for _ in range(TICKS_PER_YEAR):
            engine.tick()
        results.append([
            (p.controller_faction_id, p.supply_value) for p in world.provinces.values()
        ])
    assert results[0] == results[1]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/pytest tests/test_invariants.py tests/test_long_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'endless_war.simulation.invariants'`

- [ ] **Step 3: Write the invariant checker**

```python
# src/endless_war/simulation/invariants.py
"""Numeric invariants.

"No obvious numerical system explodes" from CONTINUE_OFFLINE.md, made checkable.
Returns a list of human-readable violations; empty means healthy.
"""

from __future__ import annotations

import math

from endless_war.domain.models import WorldState

UNIT_FIELDS_ARMY = ("morale", "organization", "supply", "training", "equipment")
UNIT_FIELDS_FACTION = ("stability", "war_support", "exhaustion")


def check_invariants(world: WorldState) -> list[str]:
    """Return every violated invariant, or an empty list."""
    violations: list[str] = []

    expected = world.expected_province_count
    if expected and len(world.provinces) != expected:
        violations.append(
            f"province count is {len(world.provinces)}, expected {expected}"
        )

    for pid in sorted(world.provinces):
        prov = world.provinces[pid]
        if prov.controller_faction_id not in world.factions:
            violations.append(f"province {pid} controlled by unknown faction")
        if not math.isfinite(prov.supply_value):
            violations.append(f"province {pid} supply_value is not finite")
        elif not 0.0 <= prov.supply_value <= 1.0:
            violations.append(f"province {pid} supply_value out of range")
        if prov.population < 0:
            violations.append(f"province {pid} has negative population")

    for fid in sorted(world.factions):
        fac = world.factions[fid]
        if fac.manpower < 0:
            violations.append(f"faction {fid} has negative manpower")
        if not math.isfinite(fac.treasury):
            violations.append(f"faction {fid} treasury is not finite")
        elif fac.treasury < 0:
            violations.append(f"faction {fid} has negative treasury")
        if fid in fac.at_war_with:
            violations.append(f"faction {fid} is at war with itself")
        for name in UNIT_FIELDS_FACTION:
            value = getattr(fac, name)
            if not math.isfinite(value):
                violations.append(f"faction {fid} {name} is not finite")
            elif not 0.0 <= value <= 1.0:
                violations.append(f"faction {fid} {name} out of range ({value})")

    for aid in sorted(world.armies):
        army = world.armies[aid]
        if army.manpower < 0:
            violations.append(f"army {aid} has negative manpower")
        if army.province_id not in world.provinces:
            violations.append(f"army {aid} stands in a province that does not exist")
        for name in UNIT_FIELDS_ARMY:
            value = getattr(army, name)
            if not math.isfinite(value):
                violations.append(f"army {aid} {name} is not finite")
            elif not 0.0 <= value <= 1.0:
                violations.append(f"army {aid} {name} out of range ({value})")

    return violations
```

- [ ] **Step 4: Write the observatory**

```python
# src/endless_war/tools/__init__.py
"""Developer-facing tools. Never imported by the simulation core."""
```

```python
# src/endless_war/tools/observe.py
"""Headless observatory.

Runs the simulation for N simulated years and prints a yearly report. This is
the CONTINUE_OFFLINE.md checkpoint: if the output here is not interesting,
do not start building the GTK interface.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from endless_war.config import load_config
from endless_war.domain.models import WorldState
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.invariants import check_invariants
from endless_war.simulation.worldgen import generate_world

TICKS_PER_YEAR = 4 * 365


def _summarize(world: WorldState) -> list[tuple[int, str, int, int, int]]:
    rows = []
    for fid in sorted(world.factions):
        fac = world.factions[fid]
        controlled = sum(
            1 for p in world.provinces.values() if p.controller_faction_id == fid
        )
        population = sum(
            p.population for p in world.provinces.values() if p.controller_faction_id == fid
        )
        rows.append((fid, fac.name, controlled, population, fac.casualties))
    return rows


def run_observation(
    seed: int,
    years: int,
    config: dict[str, Any],
    emit: Callable[[str], None] = print,
) -> WorldState:
    """Run `years` simulated years, reporting once per year."""
    world = generate_world(seed=seed, config=config)
    engine = SimulationEngine(world, config)

    emit(f"Endless War — headless observation, seed {seed}, {years} simulated years")
    for year in range(1, years + 1):
        for _ in range(TICKS_PER_YEAR):
            engine.tick()

        emit("")
        emit(f"=== Year {year} — {world.current_time.date().isoformat()} ===")
        emit(f"{'Faction':<22}{'Prov':>6}{'Population':>14}{'Casualties':>13}{'Exh':>7}")
        for fid, name, provinces, population, casualties in _summarize(world):
            emit(
                f"{name:<22}{provinces:>6}{population:>14,}{casualties:>13,}"
                f"{world.factions[fid].exhaustion:>7.2f}"
            )

        active = [w for w in world.wars.values() if w.status == "active"]
        emit(f"wars: {len(active)} active, {len(world.wars)} total")
        for event in list(world.events)[-4:]:
            emit(f"  · {event.simulated_at.date().isoformat()}  {event.title}: {event.body}")

        violations = check_invariants(world)
        if violations:
            emit("!! INVARIANT VIOLATIONS !!")
            for violation in violations[:10]:
                emit(f"   {violation}")
            raise SystemExit(1)

    emit("")
    emit(f"Completed {years} simulated years with no invariant violations.")
    return world


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="endless-war-observe")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args(argv)
    run_observation(seed=args.seed, years=args.years, config=load_config())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Point `__main__` at the observatory**

Replace `src/endless_war/__main__.py` entirely:

```python
"""Default entry point: run the headless observation.

The GTK shell is Phase 6; until then `python -m endless_war` observes.
"""

from endless_war.tools.observe import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the tests**

First the fast suite, then everything:

```bash
.venv/bin/pytest tests/ -v -m "not slow"
.venv/bin/pytest tests/ -v
```

Expected: PASS. `tests/test_long_run.py` runs 14 600 ticks and takes **minutes, not seconds** — time it once and record the figure in the commit message so future regressions in simulation cost are visible.

Register the marker in `pyproject.toml` so `-m "not slow"` does not warn:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
markers = ["slow: runs many simulated years; minutes, not seconds"]
```

- [ ] **Step 7: Run the checkpoint by hand and read the output**

```bash
cd /media/work/endless-war
.venv/bin/python -m endless_war --years 10 --seed 42
```

Expected: ten yearly tables, provinces changing hands between factions, at least one war declared and at least one ended, and the closing line `Completed 10 simulated years with no invariant violations.`

**This is the judgement step, not a pass/fail step.** Read the output and answer: do fronts move, or does one faction snowball to 96 provinces? Do wars end, or does everyone sit at maximum exhaustion forever? If the history is boring, tune `config/default.toml` — not the code — and record what you changed and why in `docs/decisions.md`.

- [ ] **Step 8: Commit**

```bash
git add src/endless_war/tools/ src/endless_war/simulation/invariants.py src/endless_war/__main__.py pyproject.toml tests/test_invariants.py tests/test_long_run.py
git commit -m "feat: headless observatory and ten-year invariant checkpoint"
```

- [ ] **Step 9: Record the outcome**

Append a dated entry to `docs/decisions.md` covering: the battle formula chosen (power share, not raw ratio), the recruitment ceiling reinterpretation of `base_recruitment_rate`, and any balance values you tuned in Step 7 with the behaviour that prompted each change.

```bash
git add docs/decisions.md
git commit -m "docs: record simulation core balance decisions"
```

---

## Notes for the executor

- **Run the full suite after every task**, not just the new file. The long-run test in Task 12 is the canary: a change that passes its own unit tests but breaks the 10-year run has broken the simulation.
- **If a formula produces boring history, tune `config/default.toml` first.** Only change code if the *shape* of the model is wrong, and say so in `docs/decisions.md`.
- **Do not add persistence, GTK, commanders, or diplomacy beyond war/peace.** `specs/03-mvp.md` defers them, and this plan stops at the `CONTINUE_OFFLINE.md` checkpoint.
- The pipeline order in `SimulationEngine.tick()` is fixed by `docs/architecture.md`. If a task seems to need a different order, that is a finding to raise, not a change to make quietly.
