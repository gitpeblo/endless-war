# Isometric Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat-rectangle map with an isometric pixel-art board. Terrain comes from the simulation, is drawn darkened, and each province carries a full-strength faction-colour wash (mockup D).

**Architecture:** Two new pure modules, `ui/iso.py` (board geometry) and `ui/terrain.py` (sheet loading, darkening, terrain→tile). `render_map` and `render_legend` are rewritten on top of them and keep drawing onto any cairo context, so every test runs on an image surface with no display. The view model gains `ProvinceCell.terrain`.

**Tech Stack:** Python 3.12, pycairo, GTK 3 via PyGObject, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-24-isometric-map-design.md`

## Global Constraints

- Asset: newc-42 "Pixel Art Isometric Map Tileset", CC0 1.0, https://newc-42.itch.io/pixel-art-isometric-map-tileset. Commit only `Spritesheet.png`, as `src/endless_war/ui/assets/terrain.png` (432×384, 9×8 cells of 48×48).
- Never modify or delete the user's `assets/maps/`; ignore it in git.
- Tile geometry: top face is a 48×24 diamond with top vertex at (24, 16) in the 48×48 cell; iso step (+24, +12) per column and (−24, +12) per row.
- Pixel art: integer scale only, `cairo.FILTER_NEAREST`.
- `DESATURATE = 0.40`, `DARKEN = 0.60`, `WASH_ALPHA = 0.45`, `SUPPLY_ALPHA = 0.35`, `BORDER = 1`, `WATER_DROP = 4`.
- Layer rule: `ui/` imports `app/` and `endless_war.config` only. `terrain.py` and `iso.py` import nothing from the project except `ui/geometry.grid_shape`.
- An unknown terrain falls back to plains; the map must never raise inside the GTK refresh.
- Run tests with `.venv/bin/python -m pytest` (DISPLAY=:0 exists for widget tests).

## Review Focus

1. A window resized larger or smaller: the board must re-pick its integer scale and stay centred. No half-pixel smearing, and nothing clipped at the default 980×640. Test in Task 2.
2. A tall tile (forest, mountain) in front of a province with markers: back-to-front order must let the nearer tile cover the farther markers, not the reverse. Test in Task 4.
3. The first frame, before the sheet has loaded: `load_sheet()` darkens 166k pixels in Python once, and the one-off delay must be acceptable. Measure in Task 1.
4. A province whose terrain string is unknown (a future terrain type): plains, never an exception. Test in Task 1.
5. The legend's terrain section with a long window height: the rows must not overflow the side column at the default window size. Check by eye in Task 6.

---

### Task 1: Terrain sheet and tiles

**Files:**
- Create: `src/endless_war/ui/assets/terrain.png` (copied from `assets/maps/Isometric Terrain Tiles/Spritesheet.png`)
- Create: `src/endless_war/ui/assets/README.md`
- Create: `src/endless_war/ui/terrain.py`
- Modify: `pyproject.toml` (package data), `.gitignore` (`/assets/maps/`)
- Test: `tests/test_ui_terrain.py`

**Interfaces:**
- Produces: `SHEET_PATH: Path`, `DESATURATE`, `DARKEN`, `TILES: dict[str, tuple[tuple[int, int], ...]]`, `WATER: tuple[int, int]`, `FALLBACK = "plains"`, `tile_for(terrain: str, province_id: int) -> tuple[int, int]` (sheet row, col), `grim(surface: cairo.ImageSurface) -> cairo.ImageSurface`, `load_sheet() -> cairo.ImageSurface`.

- [ ] **Step 1: Copy the asset and write its README**

```bash
mkdir -p src/endless_war/ui/assets
cp "assets/maps/Isometric Terrain Tiles/Spritesheet.png" src/endless_war/ui/assets/terrain.png
```

`src/endless_war/ui/assets/README.md`:

```markdown
# UI assets

`terrain.png` is `Spritesheet.png` from **Pixel Art Isometric Map Tileset** by
newc-42 — https://newc-42.itch.io/pixel-art-isometric-map-tileset — released
under **CC0 1.0** (public domain; no attribution required). Unmodified; the game
darkens it at load time (`ui/terrain.py`).

Layout: 9 × 8 cells of 48 × 48 px. Each tile's top face is a 48 × 24 diamond
whose top vertex is at (24, 16) in its cell; the side is 8 px deep.
```

Append to `.gitignore`:

```
# the user's raw asset downloads (Unity packages, .aseprite); the game uses
# src/endless_war/ui/assets/ instead
/assets/maps/
```

Append to `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"endless_war.ui" = ["assets/*.png", "assets/*.md"]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_ui_terrain.py`:

```python
import cairo
import pytest

from endless_war.config import load_config
from endless_war.ui import terrain
from endless_war.ui.terrain import FALLBACK, TILES, WATER, grim, load_sheet, tile_for


def _lum(r: float, g: float, b: float) -> float:
    return 0.30 * r + 0.59 * g + 0.11 * b


def test_the_sheet_ships_with_the_package() -> None:
    assert terrain.SHEET_PATH.exists(), terrain.SHEET_PATH
    sheet = cairo.ImageSurface.create_from_png(str(terrain.SHEET_PATH))
    assert (sheet.get_width(), sheet.get_height()) == (432, 384)


def test_every_simulation_terrain_has_a_tile() -> None:
    for name in load_config()["balance"]["terrain_defence"]:
        assert name in TILES, name


def test_every_tile_is_inside_the_sheet() -> None:
    for variants in list(TILES.values()) + [(WATER,)]:
        for row, col in variants:
            assert 0 <= row < 8 and 0 <= col < 9, (row, col)


def test_a_province_always_gets_the_same_variant() -> None:
    assert tile_for("forest", 17) == tile_for("forest", 17)
    assert {tile_for("forest", pid) for pid in range(8)} == set(TILES["forest"])


def test_an_unknown_terrain_falls_back_to_plains() -> None:
    assert tile_for("swamp", 3) == tile_for(FALLBACK, 3)


def _sample(surface, x, y):
    surface.flush()
    d, s = surface.get_data(), surface.get_stride()
    o = y * s + x * 4
    return d[o + 2], d[o + 1], d[o], d[o + 3]  # r, g, b, a


def test_grim_darkens_desaturates_and_leaves_the_input_alone() -> None:
    src = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 1)
    cr = cairo.Context(src)
    for x, rgb in enumerate(((0.9, 0.2, 0.1), (0.1, 0.8, 0.3), (0.2, 0.3, 0.9), (0.5, 0.5, 0.5))):
        cr.set_source_rgb(*rgb)
        cr.rectangle(x, 0, 1, 1)
        cr.fill()
    before = [_sample(src, x, 0) for x in range(4)]
    out = grim(src)
    assert [_sample(src, x, 0) for x in range(4)] == before, "input mutated"
    for x in range(4):
        r0, g0, b0, a0 = before[x]
        r1, g1, b1, a1 = _sample(out, x, 0)
        assert a1 == a0
        assert _lum(r1, g1, b1) <= _lum(r0, g0, b0)
        assert max(r1, g1, b1) - min(r1, g1, b1) <= max(r0, g0, b0) - min(r0, g0, b0)


def test_grim_keeps_transparent_pixels_transparent() -> None:
    src = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2, 2)
    out = grim(src)
    assert all(v == 0 for v in bytes(out.get_data()))


def test_load_sheet_is_cached() -> None:
    assert load_sheet() is load_sheet()
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_terrain.py -v`
Expected: collection ERROR, `cannot import name 'terrain' from 'endless_war.ui'` (the module does not exist).

- [ ] **Step 4: Implement**

Create `src/endless_war/ui/terrain.py`:

```python
"""Terrain tiles from the CC0 isometric sheet (see assets/README.md).

The sheet is darkened and desaturated once, on first use: the map is meant to
read grim, with the faction colour carrying the only saturated colour on it.
"""

from __future__ import annotations

from pathlib import Path

import cairo

SHEET_PATH = Path(__file__).parent / "assets" / "terrain.png"
DESATURATE = 0.40  # keep 40 % of each pixel's saturation
DARKEN = 0.60  # then scale its brightness to 60 %

# (sheet row, sheet col). Several variants give a varied map; a province's
# variant is fixed by its id, so it never flickers between frames.
TILES: dict[str, tuple[tuple[int, int], ...]] = {
    "plains": ((0, 6), (6, 7), (1, 6), (2, 6), (3, 6)),
    "forest": ((0, 0), (1, 0), (2, 0), (3, 0)),
    "hills": ((5, 8),),
    "mountain": ((6, 6),),
    "urban": ((6, 8),),
}
WATER = (4, 7)
FALLBACK = "plains"

_sheet: cairo.ImageSurface | None = None


def tile_for(terrain: str, province_id: int) -> tuple[int, int]:
    """The sheet cell for `terrain`, stable per province; plains if unknown."""
    variants = TILES.get(terrain, TILES[FALLBACK])
    return variants[province_id % len(variants)]


def grim(surface: cairo.ImageSurface) -> cairo.ImageSurface:
    """A darkened, desaturated copy of `surface`; the input is not touched.

    Works on premultiplied ARGB: moving each channel toward the luminance and
    scaling it down can never exceed alpha, so the result stays valid.
    """
    width, height = surface.get_width(), surface.get_height()
    out = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(surface, 0, 0)
    cr.paint()
    out.flush()
    data = out.get_data()
    for i in range(0, len(data), 4):
        alpha = data[i + 3]
        if alpha == 0:
            continue
        b, g, r = data[i], data[i + 1], data[i + 2]
        lum = 0.30 * r + 0.59 * g + 0.11 * b
        data[i] = min(alpha, int((lum + (b - lum) * DESATURATE) * DARKEN))
        data[i + 1] = min(alpha, int((lum + (g - lum) * DESATURATE) * DARKEN))
        data[i + 2] = min(alpha, int((lum + (r - lum) * DESATURATE) * DARKEN))
    out.mark_dirty()
    return out


def load_sheet() -> cairo.ImageSurface:
    """The darkened sheet, loaded and processed once."""
    global _sheet
    if _sheet is None:
        if not SHEET_PATH.exists():
            raise FileNotFoundError(f"terrain sheet missing: {SHEET_PATH}")
        _sheet = grim(cairo.ImageSurface.create_from_png(str(SHEET_PATH)))
    return _sheet
```

- [ ] **Step 5: Run tests; measure the one-off load**

Run: `.venv/bin/python -m pytest tests/test_ui_terrain.py -v` → all 8 PASS.
Run: `PYTHONPATH=src python3 -c "import time; t=time.perf_counter(); from endless_war.ui.terrain import load_sheet; load_sheet(); print(round((time.perf_counter()-t)*1000), 'ms')"`
Expected: well under 1000 ms. Report the number. If it is over 1000 ms, stop and report.
Run: `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add src/endless_war/ui/assets/terrain.png src/endless_war/ui/assets/README.md src/endless_war/ui/terrain.py tests/test_ui_terrain.py pyproject.toml .gitignore
git commit -m "feat: CC0 isometric terrain sheet, darkened at load"
```

---

### Task 2: Isometric board geometry

**Files:**
- Create: `src/endless_war/ui/iso.py`
- Test: `tests/test_ui_iso.py`

**Interfaces:**
- Consumes: `endless_war.ui.geometry.grid_shape(province_count, cols) -> (cols, rows)` (raises `ValueError` on a ragged grid or `cols <= 0`).
- Produces: constants `TILE_W = TILE_H = 48`, `STEP_X = 24`, `STEP_Y = 12`, `FACE_TOP = 16`, `FACE_W = 48`, `FACE_H = 24`, `BORDER = 1`, `WATER_DROP = 4`; `Board(cols, rows, scale, origin_x, origin_y)` (frozen); `board_for(province_count, cols, width, height) -> Board`; `tile_origin(board, col, row) -> (x, y)`; `face_centre(board, col, row) -> (x, y)`; `draw_order(cols, rows, border=BORDER) -> list[(col, row)]`; `province_at(board, x, y, province_count) -> int | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_iso.py`:

```python
from endless_war.ui.iso import (
    BORDER,
    STEP_X,
    STEP_Y,
    board_for,
    draw_order,
    face_centre,
    province_at,
    tile_origin,
)


def test_the_scale_is_the_largest_integer_that_fits() -> None:
    # 12 x 8 provinces plus the water ring is 576 x 316 unscaled.
    assert board_for(96, 12, 600, 400).scale == 1
    assert board_for(96, 12, 1400, 800).scale == 2
    assert board_for(96, 12, 1800, 1000).scale == 3


def test_the_scale_never_drops_below_one() -> None:
    assert board_for(96, 12, 50, 30).scale == 1
    assert board_for(96, 12, 0, 0).scale == 1


def test_the_board_is_centred() -> None:
    small, big = board_for(96, 12, 600, 400), board_for(96, 12, 800, 400)
    assert big.origin_x - small.origin_x == 100  # 200 px wider, same scale


def test_tiles_step_isometrically() -> None:
    for scale_size in ((600, 400), (1400, 800)):
        board = board_for(96, 12, *scale_size)
        x0, y0 = tile_origin(board, 0, 0)
        x1, y1 = tile_origin(board, 1, 0)
        x2, y2 = tile_origin(board, 0, 1)
        assert (x1 - x0, y1 - y0) == (STEP_X * board.scale, STEP_Y * board.scale)
        assert (x2 - x0, y2 - y0) == (-STEP_X * board.scale, STEP_Y * board.scale)


def test_draw_order_is_back_to_front_and_includes_the_ring() -> None:
    order = draw_order(12, 8)
    assert len(order) == (12 + 2 * BORDER) * (8 + 2 * BORDER)
    depths = [c + r for c, r in order]
    assert depths == sorted(depths)
    assert (-1, -1) in order and (12, 8) in order


def test_every_province_round_trips_through_its_face_centre() -> None:
    for size in ((600, 400), (1400, 800), (1800, 1000), (313, 197)):
        board = board_for(96, 12, *size)
        for pid in range(96):
            x, y = face_centre(board, pid % 12, pid // 12)
            assert province_at(board, x, y, 96) == pid, (size, pid)


def test_points_off_the_board_hit_nothing() -> None:
    board = board_for(96, 12, 600, 400)
    assert province_at(board, 0, 0, 96) is None
    assert province_at(board, 599, 399, 96) is None
    x, y = face_centre(board, -1, 0)  # a water cell
    assert province_at(board, x, y, 96) is None


def test_the_whole_board_fits_inside_the_widget() -> None:
    for size in ((600, 400), (980, 640), (1400, 800)):
        board = board_for(96, 12, *size)
        xs, ys = [], []
        for c, r in draw_order(12, 8):
            x, y = tile_origin(board, c, r)
            xs += [x, x + 48 * board.scale]
            ys += [y, y + (48 + 4) * board.scale]
        assert min(xs) >= 0 and max(xs) <= size[0], size
        assert min(ys) >= 0 and max(ys) <= size[1], size
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ui_iso.py -v`
Expected: collection ERROR, `No module named 'endless_war.ui.iso'`.

- [ ] **Step 3: Implement**

Create `src/endless_war/ui/iso.py`:

```python
"""Isometric board geometry. Pure: no GTK, no cairo.

Province `id` sits at column `id % cols`, row `id // cols`. Cell (c, r)'s
48 x 48 tile has its top-left corner at `origin + ((c - r) * 24, (c + r) * 12)`,
times the integer scale; its top face is the diamond whose top vertex is 16 px
down the cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from endless_war.ui.geometry import grid_shape

TILE_W = TILE_H = 48
STEP_X, STEP_Y = 24, 12
FACE_TOP = 16
FACE_W, FACE_H = 48, 24
BORDER = 1  # ring of water tiles around the board
WATER_DROP = 4  # water sits this far below the land


@dataclass(frozen=True, slots=True)
class Board:
    cols: int
    rows: int
    scale: int
    origin_x: float  # screen x of cell (0, 0)'s top-left corner
    origin_y: float


def _extent(cols: int, rows: int) -> tuple[int, int, int, int]:
    """Unscaled (width, height, left, top) of the board and its ring, relative to cell (0, 0)."""
    c0, r0 = -BORDER, -BORDER
    c1, r1 = cols - 1 + BORDER, rows - 1 + BORDER
    left = (c0 - r1) * STEP_X
    right = (c1 - r0) * STEP_X + TILE_W
    top = (c0 + r0) * STEP_Y
    bottom = (c1 + r1) * STEP_Y + TILE_H + WATER_DROP
    return right - left, bottom - top, left, top


def board_for(province_count: int, cols: int, width: float, height: float) -> Board:
    """The largest integer scale that fits, centred in `width` x `height`."""
    columns, rows = grid_shape(province_count, cols)
    w, h, left, top = _extent(columns, rows)
    scale = max(1, int(min(width / w, height / h)))
    origin_x = (width - w * scale) / 2 - left * scale
    origin_y = (height - h * scale) / 2 - top * scale
    return Board(columns, rows, scale, math.floor(origin_x), math.floor(origin_y))


def tile_origin(board: Board, col: int, row: int) -> tuple[float, float]:
    return (
        board.origin_x + (col - row) * STEP_X * board.scale,
        board.origin_y + (col + row) * STEP_Y * board.scale,
    )


def face_centre(board: Board, col: int, row: int) -> tuple[float, float]:
    x, y = tile_origin(board, col, row)
    return x + FACE_W / 2 * board.scale, y + (FACE_TOP + FACE_H / 2) * board.scale


def draw_order(cols: int, rows: int, border: int = BORDER) -> list[tuple[int, int]]:
    """Every cell including the ring, back to front."""
    cells = [
        (c, r)
        for c in range(-border, cols + border)
        for r in range(-border, rows + border)
    ]
    return sorted(cells, key=lambda cell: (cell[0] + cell[1], cell[0]))


def province_at(board: Board, x: float, y: float, province_count: int) -> int | None:
    """The province whose top face contains (x, y), or None."""
    u = (x - board.origin_x) / board.scale - FACE_W / 2
    v = (y - board.origin_y) / board.scale - (FACE_TOP + FACE_H / 2)
    col = math.floor((u / STEP_X + v / STEP_Y) / 2 + 0.5)
    row = math.floor((v / STEP_Y - u / STEP_X) / 2 + 0.5)
    if not (0 <= col < board.cols and 0 <= row < board.rows):
        return None
    pid = row * board.cols + col
    return pid if pid < province_count else None
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ui_iso.py -v` → all PASS.
Run: `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/iso.py tests/test_ui_iso.py
git commit -m "feat: isometric board geometry"
```

---

### Task 3: Terrain on the view model

**Files:**
- Modify: `src/endless_war/app/view_model.py` (`ProvinceCell.terrain`), `src/endless_war/app/snapshot.py` (fill it), `src/endless_war/ui/legend.py:68` and `tests/test_view_model.py:11` (constructors)
- Test: `tests/test_snapshot.py` (append)

**Interfaces:**
- Produces: `ProvinceCell.terrain: str`, the last field, no default.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_snapshot.py`:

```python
def test_every_province_carries_its_terrain() -> None:
    world, cfg = _world()
    view = build_view(world, cfg, bound_faction_id=None, speed="1x")
    assert [c.terrain for c in view.provinces] == [
        world.provinces[pid].terrain for pid in sorted(world.provinces)
    ]
    assert len({c.terrain for c in view.provinces}) > 1, "premise: seed 42 has varied terrain"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_snapshot.py -q`
Expected: FAIL with `AttributeError: 'ProvinceCell' object has no attribute 'terrain'`.

- [ ] **Step 3: Implement**

In `src/endless_war/app/view_model.py`, add as the last field of `ProvinceCell`:

```python
    terrain: str
```

In `src/endless_war/app/snapshot.py`, add `terrain=province.terrain,` to the `ProvinceCell(...)` call, after `has_supply_problem=...`.

In `src/endless_war/ui/legend.py` `_province()` and `tests/test_view_model.py` `_cell()`, add `terrain="plains",` after `has_supply_problem=...`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/app/view_model.py src/endless_war/app/snapshot.py src/endless_war/ui/legend.py tests/test_view_model.py tests/test_snapshot.py
git commit -m "feat: carry province terrain in the view"
```

---

### Task 4: The isometric map

**Files:**
- Modify: `src/endless_war/ui/map_view.py` (rewrite everything above `class MapView`; `MapView` itself is unchanged)
- Modify: `src/endless_war/ui/geometry.py` (remove `Cell`, `cell_for`, `province_at`, `CELL_PADDING`)
- Rewrite: `tests/test_ui_map_render.py`
- Modify: `tests/test_ui_geometry.py` (remove the six `cell_for`/`province_at` tests and the import)

**Interfaces:**
- Consumes: Task 1 `load_sheet`, `tile_for`, `WATER`; Task 2 `board_for`, `tile_origin`, `face_centre`, `draw_order`, `TILE_W`, `TILE_H`, `FACE_TOP`, `FACE_W`, `FACE_H`, `WATER_DROP`; Task 3 `ProvinceCell.terrain`.
- Produces (in `endless_war.ui.map_view`): `render_map(cr, view, width, height, cols)` (same signature); constants `BACKGROUND`, `HATCH_RGBA`, `CAPITAL_RGB`, `ARMY_RGB`, `WASH_ALPHA = 0.45`, `SUPPLY_ALPHA = 0.35`; painters used by the legend in Task 5, each taking the tile's top-left `(x, y)` and scale `s`: `_face(cr, x, y, s, inset=0.0)`, `_wash(cr, x, y, s, rgb, alpha)`, `_hatch(cr, x, y, s)`, `_outline(cr, x, y, s, rgb)`, `_capital(cr, x, y, s)`, `_army(cr, x, y, s)`, `_town(cr, x, y, s)`, `_blit(cr, sheet, cell, x, y, s)`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_ui_map_render.py` entirely with:

```python
import dataclasses

import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.engine import SimulationEngine
from endless_war.simulation.worldgen import generate_world
from endless_war.ui import map_view
from endless_war.ui.colors import faction_rgb
from endless_war.ui.iso import board_for, face_centre, tile_origin
from endless_war.ui.map_view import BACKGROUND, render_map

WIDTH, HEIGHT, COLS = 600, 400, 12


def _view(ticks: int = 0, bound=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    SimulationEngine(world, cfg).run(ticks)
    return build_view(world, cfg, bound_faction_id=bound, speed="1x")


def _render(view, width=WIDTH, height=HEIGHT):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    render_map(cairo.Context(surface), view, width, height, COLS)
    surface.flush()
    return surface


def _pixel(surface, x: float, y: float) -> tuple[int, int, int]:
    data, stride = surface.get_data(), surface.get_stride()
    o = int(y) * stride + int(x) * 4
    return data[o + 2], data[o + 1], data[o]


def _probe(pid: int, width=WIDTH, height=HEIGHT) -> tuple[float, float]:
    # Left part of the top face: clear of the capital, army and town markers.
    board = board_for(96, COLS, width, height)
    x, y = face_centre(board, pid % COLS, pid // COLS)
    return x - 10 * board.scale, y


def _with(view, pid: int, **changes):
    cells = tuple(
        dataclasses.replace(c, **changes) if c.id == pid else c for c in view.provinces
    )
    return dataclasses.replace(view, provinces=cells)


def _plain(view, pid: int):
    return _with(view, pid, is_contested=False, has_supply_problem=False, has_armies=False, is_capital=False)


def test_the_wash_is_the_provinces_faction_colour(monkeypatch) -> None:
    # Alpha blending is exact: washed = base + alpha * (colour - base). Render
    # once without the wash to get base, then solve for the colour.
    view = _view()
    pid = next(c.id for c in view.provinces if not c.is_capital)
    view = _plain(view, pid)
    washed = _pixel(_render(view), *_probe(pid))
    monkeypatch.setattr(map_view, "WASH_ALPHA", 0.0)
    base = _pixel(_render(view), *_probe(pid))
    cell = next(c for c in view.provinces if c.id == pid)
    want = [round(v * 255) for v in faction_rgb(cell.color_key)]
    got = [b + (w - b) / 0.45 for w, b in zip(washed, base)]
    assert all(abs(g - v) <= 6 for g, v in zip(got, want)), (got, want)


def test_a_contested_province_is_hatched() -> None:
    view = _plain(_view(), 5)
    calm = _render(view)
    fought = _render(_with(view, 5, is_contested=True))
    board = board_for(96, COLS, WIDTH, HEIGHT)
    cx, cy = face_centre(board, 5, 0)
    changed = sum(
        1
        for dx in range(-14, 15)
        for dy in range(-5, 6)
        if sum(_pixel(fought, cx + dx, cy + dy)) < sum(_pixel(calm, cx + dx, cy + dy)) - 10
    )
    assert changed > 15


def test_a_supply_problem_darkens_the_province() -> None:
    view = _plain(_view(), 7)
    fine = sum(_pixel(_render(view), *_probe(7)))
    starved = sum(_pixel(_render(_with(view, 7, has_supply_problem=True)), *_probe(7)))
    assert starved < fine - 10


def test_the_sea_surrounds_the_board() -> None:
    surface = _render(_view())
    board = board_for(96, COLS, WIDTH, HEIGHT)
    x, y = face_centre(board, -1, 3)
    assert _pixel(surface, x, y + 4) != tuple(round(c * 255) for c in BACKGROUND)


def test_a_nearer_tall_tile_covers_the_province_behind_it() -> None:
    # Back-to-front order: the mountain at (1, 1) rises into the top face of
    # the province at (0, 0), so the farther province's wash must not show
    # through the nearer peak.
    view = _view()
    board = board_for(96, COLS, WIDTH, HEIGHT)
    behind, front = 0, 13  # cells (0, 0) and (1, 1)
    base = _with(_plain(_plain(view, behind), front), front, terrain="mountain")
    fx, fy = tile_origin(board, 1, 1)
    x, y = fx + 24 * board.scale, fy + 10 * board.scale  # on the peak, inside (0, 0)'s face
    orange = _pixel(_render(_with(base, behind, color_key="orange")), x, y)
    blue = _pixel(_render(_with(base, behind, color_key="blue")), x, y)
    assert orange == blue, "the farther province's wash showed through the nearer peak"
    flat = _with(_with(base, front, terrain="plains"), behind, color_key="orange")
    assert _pixel(_render(flat), x, y) != orange, "premise: the peak covers this point"


def test_an_empty_view_and_a_tiny_surface_render() -> None:
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    world.provinces.clear()
    empty = build_view(world, cfg, bound_faction_id=None, speed="paused")
    _render(empty)
    _render(_view(), width=20, height=20)


def test_an_unknown_terrain_renders_as_plains() -> None:
    view = _with(_view(), 3, terrain="swamp")
    _render(view)


def test_rendering_is_stable_for_the_same_view() -> None:
    view = _view(4 * 30)
    first, second = _render(view), _render(view)
    assert bytes(first.get_data()) == bytes(second.get_data())
```

In `tests/test_ui_geometry.py`: change the import line to `from endless_war.ui.geometry import grid_shape`, and delete `test_cells_tile_the_widget_without_overlapping`, `test_a_province_id_round_trips_through_its_own_centre`, `test_a_point_outside_the_widget_hits_nothing`, `test_round_trip_at_small_and_irregular_widget_sizes` and `test_tiling_holds_at_small_sizes`. Their replacements are in `tests/test_ui_iso.py`.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ui_map_render.py -q`
Expected: failures. `test_the_wash_is_the_provinces_faction_colour` fails (no `WASH_ALPHA` attribute), and the probes land on the old rectangle layout.

- [ ] **Step 3: Implement**

In `src/endless_war/ui/geometry.py`, delete `CELL_PADDING`, `Cell`, `cell_for` and `province_at`, keeping only `grid_shape` and its imports, and change the module docstring to: "The province grid's shape. Provinces are generated as `pid = row * cols + col`; the isometric board built on it is `ui/iso.py`. Pure: no GTK, no cairo." (`Cell` was only used by the rectangle map and the old legend; Task 5 replaces the legend, and Task 4's legend breakage is expected until then.)

Replace everything in `src/endless_war/ui/map_view.py` above `class MapView` with:

```python
"""The strategic map: an isometric board of darkened pixel-art terrain.

`render_map` draws onto any cairo context, so it can be tested against an
image surface with no display. `MapView` is the GTK widget wrapped around it.
Each province is its terrain tile, washed in its controller's colour; the
markers sit on the tile's top face.
"""

from __future__ import annotations

import cairo
import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import ProvinceCell, WorldView  # noqa: E402
from endless_war.ui import iso  # noqa: E402
from endless_war.ui.colors import faction_rgb, lighten  # noqa: E402
from endless_war.ui.terrain import WATER, load_sheet, tile_for  # noqa: E402

BACKGROUND = (0.11, 0.12, 0.14)
HATCH_RGBA = (0.05, 0.05, 0.05, 0.55)
CAPITAL_RGB = (1.0, 1.0, 1.0)
ARMY_RGB = (0.08, 0.08, 0.08)
TOWN_RGB = (0.10, 0.10, 0.11)
WASH_ALPHA = 0.45
SUPPLY_ALPHA = 0.35


def _blit(cr, sheet, cell: tuple[int, int], x: float, y: float, s: float) -> None:
    row, col = cell
    cr.save()
    cr.translate(x, y)
    cr.scale(s, s)
    cr.rectangle(0, 0, iso.TILE_W, iso.TILE_H)
    cr.clip()
    cr.set_source_surface(sheet, -col * iso.TILE_W, -row * iso.TILE_H)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    cr.restore()


def _face(cr, x: float, y: float, s: float, inset: float = 0.0) -> None:
    """The top-face diamond of the tile whose cell's top-left is (x, y)."""
    cx, top = x + iso.FACE_W / 2 * s, y + iso.FACE_TOP * s
    half_h = iso.FACE_H / 2 * s
    cr.move_to(cx, top + inset)
    cr.line_to(x + iso.FACE_W * s - 2 * inset, top + half_h)
    cr.line_to(cx, top + 2 * half_h - inset)
    cr.line_to(x + 2 * inset, top + half_h)
    cr.close_path()


def _wash(cr, x: float, y: float, s: float, rgb, alpha: float) -> None:
    _face(cr, x, y, s)
    cr.set_source_rgba(*rgb, alpha)
    cr.fill()


def _hatch(cr, x: float, y: float, s: float) -> None:
    cr.save()
    _face(cr, x, y, s)
    cr.clip()
    cr.set_source_rgba(*HATCH_RGBA)
    cr.set_line_width(1.5 * s)
    top, height = y + iso.FACE_TOP * s, iso.FACE_H * s
    offset = -height
    while offset < iso.FACE_W * s:
        cr.move_to(x + offset, top)
        cr.line_to(x + offset + height, top + height)
        offset += 6 * s
    cr.stroke()
    cr.restore()


def _outline(cr, x: float, y: float, s: float, rgb) -> None:
    _face(cr, x, y, s, inset=1.5 * s)
    cr.set_source_rgb(*lighten(rgb))
    cr.set_line_width(2.0 * s)
    cr.stroke()


def _centre(x: float, y: float, s: float) -> tuple[float, float]:
    return x + iso.FACE_W / 2 * s, y + (iso.FACE_TOP + iso.FACE_H / 2) * s


def _capital(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    half_w, half_h = 5.5 * s, 3.5 * s
    cr.set_source_rgb(*CAPITAL_RGB)
    cr.move_to(cx, cy - half_h)
    cr.line_to(cx + half_w, cy)
    cr.line_to(cx, cy + half_h)
    cr.line_to(cx - half_w, cy)
    cr.close_path()
    cr.fill()


def _army(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    cr.set_source_rgb(*ARMY_RGB)
    cr.arc(cx + 9 * s, cy + 4 * s, 3.0 * s, 0, 6.2832)
    cr.fill()


def _town(cr, x: float, y: float, s: float) -> None:
    cx, cy = _centre(x, y, s)
    cr.set_source_rgb(*TOWN_RGB)
    for dx, h in ((-5, 4), (-1, 6), (3, 3)):
        cr.rectangle(cx + dx * s, cy + (1 - h) * s, 3 * s, h * s)
    cr.fill()


def _province(cr, sheet, province: ProvinceCell, x: float, y: float, s: float, bound: int | None) -> None:
    _blit(cr, sheet, tile_for(province.terrain, province.id), x, y, s)
    rgb = faction_rgb(province.color_key)
    _wash(cr, x, y, s, rgb, WASH_ALPHA)
    if province.has_supply_problem:
        _wash(cr, x, y, s, (0.0, 0.0, 0.0), SUPPLY_ALPHA)
    if province.is_contested:
        _hatch(cr, x, y, s)
    if bound is not None and province.controller_faction_id == bound:
        _outline(cr, x, y, s, rgb)
    if province.terrain == "urban":
        _town(cr, x, y, s)
    if province.is_capital:
        _capital(cr, x, y, s)
    if province.has_armies:
        _army(cr, x, y, s)


def render_map(cr, view: WorldView, width: float, height: float, cols: int) -> None:
    """Draw every province of `view` as an isometric board in `width` x `height`."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    count = len(view.provinces)
    if count == 0 or width <= 0 or height <= 0:
        return

    board = iso.board_for(count, cols, width, height)
    sheet = load_sheet()
    by_cell = {(p.id % cols, p.id // cols): p for p in view.provinces}
    s = board.scale
    for col, row in iso.draw_order(board.cols, board.rows):
        x, y = iso.tile_origin(board, col, row)
        province = by_cell.get((col, row))
        if province is None:
            _blit(cr, sheet, WATER, x, y + iso.WATER_DROP * s, s)
        else:
            _province(cr, sheet, province, x, y, s, view.bound_faction_id)
```

Keep `class MapView` exactly as it is.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_ui_map_render.py tests/test_ui_geometry.py -v` → all PASS.
Run: `.venv/bin/python -m pytest -q`. Expected: everything passes **except** `tests/test_ui_legend.py`, which still imports the old painters (`_fill`, `_bound_outline`) and `Cell`-based swatches. Task 5 rewrites it. Record which legend tests fail and why in the task report; do not patch them here.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/map_view.py src/endless_war/ui/geometry.py tests/test_ui_map_render.py tests/test_ui_geometry.py
git commit -m "feat: isometric pixel-art map with a faction wash"
```

---

### Task 5: The legend on diamonds, with a terrain section

**Files:**
- Rewrite: `src/endless_war/ui/legend.py` (everything above `class LegendView`; `LegendView` unchanged)
- Rewrite: `tests/test_ui_legend.py`

**Interfaces:**
- Consumes: Task 4's painters and constants from `endless_war.ui.map_view`; Task 1 `load_sheet`, `tile_for`.
- Produces: `LegendEntry(kind, label, color_key, terrain="")`, with kinds faction, bound, contested, supply, capital, army, heading, terrain; `legend_entries(view)`; `legend_height(view)`; `render_legend(cr, view, width, height)`; `TERRAIN_ORDER = ("plains", "forest", "hills", "mountain", "urban")`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_ui_legend.py` entirely with:

```python
import cairo

from endless_war.app.snapshot import build_view
from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world
from endless_war.ui.colors import faction_rgb
from endless_war.ui.legend import (
    PAD,
    TERRAIN_ORDER,
    legend_entries,
    legend_height,
    render_legend,
    row_height,
    swatch_centre,
)
from endless_war.ui.map_view import WASH_ALPHA


def _view(bound=None):
    cfg = load_config()
    world = generate_world(seed=42, config=cfg)
    return build_view(world, cfg, bound_faction_id=bound, speed="1x")


def test_every_faction_is_named_with_its_colour() -> None:
    view = _view()
    factions = [e for e in legend_entries(view) if e.kind == "faction"]
    assert [(e.label, e.color_key) for e in factions] == [
        (f.name, f.color_key) for f in view.factions
    ]


def test_every_map_symbol_is_explained() -> None:
    kinds = [e.kind for e in legend_entries(_view())]
    for kind in ("contested", "supply", "capital", "army"):
        assert kind in kinds


def test_the_outline_is_explained_only_when_a_faction_is_bound() -> None:
    assert "bound" not in [e.kind for e in legend_entries(_view())]
    bound = [e for e in legend_entries(_view(bound=0)) if e.kind == "bound"]
    assert len(bound) == 1 and bound[0].color_key == _view(bound=0).factions[0].color_key


def test_a_terrain_section_lists_every_simulation_terrain_in_order() -> None:
    entries = legend_entries(_view())
    kinds = [e.kind for e in entries]
    start = kinds.index("heading")
    assert entries[start].label == "Terrain"
    terrains = [e.terrain for e in entries[start + 1 :]]
    assert terrains == list(TERRAIN_ORDER)
    assert set(TERRAIN_ORDER) == set(load_config()["balance"]["terrain_defence"])


def test_the_height_covers_every_row() -> None:
    view = _view()
    assert legend_height(view) == 2 * PAD + sum(row_height(e) for e in legend_entries(view))


def test_each_faction_swatch_shows_its_wash() -> None:
    # The swatch is the map's wash over dark ground: the pixel at the swatch
    # centre must be nearer its own faction's washed colour than any other's.
    view = _view()
    height = legend_height(view)
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 240, height)
    render_legend(cairo.Context(surface), view, 240, height)
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    entries = legend_entries(view)
    for index, entry in enumerate(entries):
        if entry.kind != "faction":
            continue
        x, y = swatch_centre(entries, index)
        o = int(y) * stride + int(x) * 4
        got = (data[o + 2], data[o + 1], data[o])

        def distance(key: str) -> float:
            rgb = [c * 255 for c in faction_rgb(key)]
            return sum((g - (WASH_ALPHA * c)) ** 2 for g, c in zip(got, rgb))

        others = [f.color_key for f in view.factions if f.color_key != entry.color_key]
        assert all(distance(entry.color_key) < distance(k) for k in others), entry.label
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ui_legend.py -q`
Expected: collection ERROR, `cannot import name 'TERRAIN_ORDER'` (or `row_height`, `swatch_centre`).

- [ ] **Step 3: Implement**

Replace everything in `src/endless_war/ui/legend.py` above `class LegendView` with:

```python
"""The map legend.

Swatches are painted with the map's own painters on a small top-face diamond,
so the legend cannot drift from what the map shows. The terrain section shows
the same darkened tiles the map uses. `legend_entries` and `render_legend`
need no display; `LegendView` is the GTK widget wrapped around them.
"""

from __future__ import annotations

from dataclasses import dataclass

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import WorldView  # noqa: E402
from endless_war.ui import iso  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.map_view import (  # noqa: E402
    BACKGROUND,
    SUPPLY_ALPHA,
    WASH_ALPHA,
    _army,
    _blit,
    _capital,
    _face,
    _hatch,
    _outline,
    _wash,
)
from endless_war.ui.terrain import load_sheet, tile_for  # noqa: E402

PAD = 8
ROW = 24
TERRAIN_ROW = 30
THUMB_W = 48  # the terrain thumbnail column; symbol swatches centre in it
SWATCH_S = 0.5  # symbol swatches are a half-size tile face
TEXT_RGB = (0.85, 0.85, 0.85)
HEADING_RGB = (0.60, 0.61, 0.64)
GROUND_RGB = (0.0, 0.0, 0.0)
FONT_SIZE = 12
NEUTRAL_KEY = "grey"
TERRAIN_ORDER = ("plains", "forest", "hills", "mountain", "urban")


@dataclass(frozen=True, slots=True)
class LegendEntry:
    kind: str  # faction | bound | contested | supply | capital | army | heading | terrain
    label: str
    color_key: str
    terrain: str = ""


def legend_entries(view: WorldView) -> list[LegendEntry]:
    """Faction colours, then what each map symbol means, then the terrains."""
    entries = [LegendEntry("faction", f.name, f.color_key) for f in view.factions]
    bound = next((f for f in view.factions if f.id == view.bound_faction_id), None)
    if bound is not None:
        entries.append(LegendEntry("bound", "Your territory", bound.color_key))
    entries += [
        LegendEntry("contested", "Occupied or under attack", NEUTRAL_KEY),
        LegendEntry("supply", "Supply problem", NEUTRAL_KEY),
        LegendEntry("capital", "Capital", NEUTRAL_KEY),
        LegendEntry("army", "Army present", NEUTRAL_KEY),
        LegendEntry("heading", "Terrain", NEUTRAL_KEY),
    ]
    entries += [LegendEntry("terrain", t.capitalize(), NEUTRAL_KEY, t) for t in TERRAIN_ORDER]
    return entries


def row_height(entry: LegendEntry) -> int:
    return TERRAIN_ROW if entry.kind == "terrain" else ROW


def legend_height(view: WorldView) -> int:
    return 2 * PAD + sum(row_height(e) for e in legend_entries(view))


def _row_top(entries: list[LegendEntry], index: int) -> int:
    return PAD + sum(row_height(e) for e in entries[:index])


def _swatch_origin(entries: list[LegendEntry], index: int) -> tuple[float, float]:
    """Top-left of the half-size tile cell whose face is centred in the row."""
    s = SWATCH_S
    top = _row_top(entries, index)
    face_mid = (iso.FACE_TOP + iso.FACE_H / 2) * s
    return PAD + (THUMB_W - iso.TILE_W * s) / 2, top + ROW / 2 - face_mid


def swatch_centre(entries: list[LegendEntry], index: int) -> tuple[float, float]:
    x, y = _swatch_origin(entries, index)
    return x + iso.FACE_W / 2 * SWATCH_S, y + (iso.FACE_TOP + iso.FACE_H / 2) * SWATCH_S


def _symbol(cr, entry: LegendEntry, x: float, y: float) -> None:
    s = SWATCH_S
    _face(cr, x, y, s)
    cr.set_source_rgb(*GROUND_RGB)
    cr.fill()
    rgb = faction_rgb(entry.color_key)
    if entry.kind in ("faction", "bound"):
        _wash(cr, x, y, s, rgb, WASH_ALPHA)
    if entry.kind == "bound":
        _outline(cr, x, y, s, rgb)
    elif entry.kind == "contested":
        _hatch(cr, x, y, s)
    elif entry.kind == "supply":
        _wash(cr, x, y, s, (0.0, 0.0, 0.0), SUPPLY_ALPHA)
    elif entry.kind == "capital":
        _capital(cr, x, y, s)
    elif entry.kind == "army":
        _army(cr, x, y, s)


def _thumbnail(cr, sheet, terrain: str, top: float) -> None:
    # The top face and a little of the tall features above it, clipped to the row.
    cr.save()
    cr.rectangle(PAD, top, THUMB_W, TERRAIN_ROW)
    cr.clip()
    _blit(cr, sheet, tile_for(terrain, 0), PAD, top - 12, 1)
    cr.restore()


def render_legend(cr, view: WorldView, width: float, height: float) -> None:
    """Draw the legend for `view` into a `width` x `height` area."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    cr.select_font_face("Sans")
    cr.set_font_size(FONT_SIZE)
    sheet = load_sheet()
    entries = legend_entries(view)
    text_x = PAD + THUMB_W + 8
    for index, entry in enumerate(entries):
        top = _row_top(entries, index)
        h = row_height(entry)
        if entry.kind == "terrain":
            _thumbnail(cr, sheet, entry.terrain, top)
        elif entry.kind != "heading":
            _symbol(cr, entry, *_swatch_origin(entries, index))
        cr.set_source_rgb(*(HEADING_RGB if entry.kind == "heading" else TEXT_RGB))
        cr.move_to(PAD if entry.kind == "heading" else text_x, top + h / 2 + FONT_SIZE * 0.35)
        cr.show_text(entry.label)
```

Keep `class LegendView` as it is. It already re-requests its height whenever `legend_height` changes.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest -q`
Expected: everything passes, the legend tests included.

- [ ] **Step 5: Commit**

```bash
git add src/endless_war/ui/legend.py tests/test_ui_legend.py
git commit -m "feat: legend on diamond swatches with a terrain section"
```

---

### Task 6: Look at it, fix what's broken, document

**Files:**
- Modify: `README.md`, `docs/architecture.md`, `docs/decisions.md`

- [ ] **Step 1: Launch and capture**

Capture the Map tab from a driver that builds `WarRoom` as `main()` does (`bound_faction_id=0`, speed `16x`). Paint the window into a cairo surface with `room.window.draw(cr)`; X capture with `import` is unreliable on this machine. Take one capture at the default 980×640 after ~20 s, and one after `room.window.resize(1500, 900)` (the map should jump to scale 2 if it fits). Answer from what you actually see:
- Is ownership readable at a glance on every terrain, forest and mountains included?
- Are capitals, armies, towns, occupied hatching and your faction's outline distinguishable?
- Does the board sit centred, with no smeared pixels and nothing clipped?
- Does the legend fit the side column at the default size, terrain section included?

Fix only what is genuinely broken, each with a regression test, and ledger anything left as it is.

- [ ] **Step 2: Update the docs**

`README.md`: in "Running it", change "The War Room window shows the map," to "The War Room window shows an isometric pixel-art map of the provinces and their terrain,".

`docs/architecture.md`, `ui/` section: after the sentence that introduces `map_view.py`, add: "The board is isometric (`iso.py`: positions, back-to-front order, integer fit-to-window scale); terrain tiles come from a CC0 sheet in `ui/assets/`, darkened once at load (`terrain.py`), and each province carries its controller's colour as a wash over the tile." In the pure-functions paragraph, add `iso.py` and `terrain.py`.

`docs/decisions.md`: append

```markdown
## 2026-09-24 — Isometric pixel-art map: dark terrain under a faction wash

**Decision:**
The map is an isometric board built from newc-42's "Pixel Art Isometric Map Tileset" (CC0 1.0, https://newc-42.itch.io/pixel-art-isometric-map-tileset), committed as `src/endless_war/ui/assets/terrain.png`. Terrain is the simulation's own (`Province.terrain`), drawn darkened and desaturated; each province is washed in its controller's colour at 45 %. Tiles are scaled by whole numbers only, with nearest-neighbour sampling.

**Reason:**
- The user asked for 8-bit art that is serious rather than cartoonish, "grim and dark", and chose this pack. It is CC0, so it can live in the repo.
- Terrain already changes battles (`[balance.terrain_defence]`) but was invisible; the map now shows it.
- Of four mockups rendered from a real game, the user chose D. The per-tile outline (A, C) was busy and read weakly on dense forest, and bright terrain (A, B) was not grim.
- Pixel art blurs at fractional scales, so the board picks the largest integer scale that fits and centres itself.

**Alternatives considered:**
- *Fantasy Hex Tiles (CC-BY 4.0).* A hex pack; would have changed the grid, and its towns and castles are medieval, which the user ruled out.
- *Paid military packs.* Not free, and their licences forbid committing the files.

**Consequences:**
- Hills and urban have no exact tile in the pack. Hills use the low mountain range; urban uses the plotted fields, with a town glyph drawn on top.
- The pack's snow, desert and lava tiles are unused; water forms a one-tile sea around the board.
- `geometry.cell_for` / `province_at` are gone; `iso.province_at` replaces them, ready for province selection.
- Darkening the sheet costs one Python pass over its pixels at first draw.
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest -q` → all pass. Report the count.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/architecture.md docs/decisions.md
git commit -m "docs: record the isometric map"
```
