# Isometric map — pixel-art terrain, dark palette, faction wash

Date: 2026-09-24
Status: approved in conversation, ready for an implementation plan
Phase: 6, map revamp requested by the user

## Why this exists

The map is a grid of flat coloured rectangles. The user asked for a graphical
revamp using 8-bit assets, then narrowed that down to "serious, not cartoonish;
grim and dark". They chose the tile pack now in `assets/maps/Isometric Terrain
Tiles/`, and picked mockup **D** from four rendered from a real game: dark,
desaturated terrain with a full-strength faction-colour wash on each province.

The simulation already has terrain (`Province.terrain` ∈ plains, forest, hills,
mountain, urban; `[balance.terrain_defence]` scales defence by it), but the map
has never shown it.

## The asset

- **Pack:** "Pixel Art Isometric Map Tileset" by newc-42,
  https://newc-42.itch.io/pixel-art-isometric-map-tileset
- **Licence:** CC0 1.0. No attribution required; redistribution is allowed, so
  the PNG may be committed. No generative AI was used in it.
- **Sheet:** `Spritesheet.png`, 432×384, a 9×8 grid of 48×48 cells, 69 tiles,
  Endesga 32 palette.
- **Tile geometry, measured from the pixels:** the top face is a diamond 48 wide
  and 24 tall whose top vertex is at (24, 16) in the cell; the side is 8 px
  deep. Isometric step: +24 px x and +12 px y per column, −24 px x and +12 px y
  per row. Tall tiles (forest, mountains) draw above the top face within the
  same 48×48 cell.

Only `Spritesheet.png` is committed, copied to
`src/endless_war/ui/assets/terrain.png`, with
`src/endless_war/ui/assets/README.md` stating the source URL and licence. The
user's download folder `assets/maps/` (which also holds Unity packages and the
`.aseprite` source) is added to `.gitignore` and left in place untouched.
`pyproject.toml` gains `[tool.setuptools.package-data]` so the PNG ships with
the package.

## Scope

In:

1. `ProvinceCell.terrain` in the view model.
2. `ui/iso.py`: pure isometric geometry.
3. `ui/terrain.py`: sheet loading, darkening, terrain→tile mapping.
4. `ui/map_view.py`: `render_map` rewritten on the isometric board.
5. `ui/legend.py`: diamond swatches and a terrain section.
6. The committed asset, its README, the package-data entry, the `.gitignore` line.

Out: clicking or selecting provinces, animation, rivers or roads between
provinces, sea provinces, new terrain types, hex maps.

## 1. View model

`ProvinceCell` gains `terrain: str` (the simulation's value, verbatim).
`build_view` fills it from `world.provinces[pid].terrain`. It is a plain string,
so the view stays immutable.

## 2. Geometry — `ui/iso.py`

The province grid is unchanged: province `id` sits at column `id % cols`, row
`id // cols`, with `rows = ceil(count / cols)` (`geometry.grid_shape`).

```python
TILE_W, TILE_H = 48, 48          # sheet cell
STEP_X, STEP_Y = 24, 12          # isometric step
FACE_TOP = 16                    # y of the top vertex of the top face in the cell
FACE_W, FACE_H = 48, 24
BORDER = 1                       # ring of water tiles around the board

@dataclass(frozen=True, slots=True)
class Board:
    cols: int
    rows: int
    scale: int                   # integer, >= 1
    origin_x: float              # screen x of cell (0, 0)'s top-left corner
    origin_y: float

def board_for(province_count, cols, width, height) -> Board
def tile_origin(board, col, row) -> tuple[float, float]   # top-left of the 48x48 cell, screen px
def face_centre(board, col, row) -> tuple[float, float]
def draw_order(cols, rows, border=BORDER) -> list[tuple[int, int]]  # back to front
def province_at(board, x, y, province_count) -> int | None
```

- **Scale** is the largest integer at which the whole board, including the water
  ring and the 16 px of tall-tile headroom above the top row, fits `width ×
  height`; never below 1. Pixel art is only ever scaled by integers, and sampled
  with `cairo.FILTER_NEAREST`.
- **Origin** centres the board in the widget.
- **Draw order** is by `col + row` ascending, then `col` ascending. Ring cells
  (col or row in `[-BORDER, -1]` or `[cols, cols + BORDER - 1]`) are included, so
  water draws in the same back-to-front pass.
- **`province_at`** inverts the projection to fractional grid coordinates and
  floors them; outside the grid, or beyond `province_count` on a ragged last
  row, it returns `None`. Invariant: for every province, `province_at` of its
  `face_centre` is that province, at every scale.

`geometry.py`'s `cell_for` and `province_at` are removed (nothing but the old
map and its tests used them); `Cell` and `grid_shape` stay, because the legend
uses `Cell`.

## 3. Terrain tiles — `ui/terrain.py`

```python
SHEET_PATH = Path(__file__).parent / "assets" / "terrain.png"
DESATURATE = 0.40   # keep 40 % of each pixel's saturation
DARKEN = 0.60       # then scale brightness to 60 %

TILES: dict[str, tuple[tuple[int, int], ...]] = {   # (sheet row, sheet col)
    "plains":   ((0, 6), (6, 7), (1, 6), (2, 6), (3, 6)),
    "forest":   ((0, 0), (1, 0), (2, 0), (3, 0)),
    "hills":    ((5, 8),),
    "mountain": ((6, 6),),
    "urban":    ((6, 8),),
}
WATER = (4, 7)
FALLBACK = "plains"

def tile_for(terrain: str, province_id: int) -> tuple[int, int]
def grim(surface) -> cairo.ImageSurface        # a darkened copy; never mutates the input
def load_sheet() -> cairo.ImageSurface          # the grim sheet, loaded and darkened once, cached
```

- A province's variant is `variants[province_id % len(variants)]`: stable across
  frames and runs, varied across the map.
- An unknown terrain falls back to plains rather than raising (the map must not
  kill the refresh timer).
- `grim` works per pixel on the premultiplied ARGB data: luminance
  `0.30 R + 0.59 G + 0.11 B`, each channel moved to `lum + (c − lum) ×
  DESATURATE`, then multiplied by `DARKEN`, and clamped to alpha.
- The sheet is loaded lazily on first use and cached at module level. A missing
  file raises `FileNotFoundError` with the path in the message; a test pins
  that the file ships.

## 4. The map — `render_map`

Signature unchanged: `render_map(cr, view, width, height, cols)`.

1. Fill the background (`BACKGROUND`, #1c1f24).
2. Compute the `Board`; if the view has no provinces or the size is not
   positive, stop.
3. For each cell in `draw_order`: blit its tile at `tile_origin`, scaled by
   `board.scale` with nearest-neighbour sampling. Ring cells get `WATER` (drawn
   4 px lower, so the sea sits below the land); province cells get
   `tile_for(terrain, id)`.
4. After the tile, in the same pass (so a nearer tall tile correctly covers a
   farther province's markers), draw that province's overlays, clipped to its
   top-face diamond:
   - **faction wash:** `faction_rgb(color_key)` at alpha `WASH_ALPHA = 0.45`;
   - **supply problem:** an extra black wash at alpha `0.35`;
   - **contested:** the existing diagonal hatch, clipped to the diamond;
   - **bound faction:** a 2 px `lighten(faction_rgb)` outline just inside the diamond;
   - **capital:** a white diamond marker at the face centre, 0.22 of the face width;
   - **armies:** a dark dot on the face, offset toward its front corner;
   - **urban:** a small building glyph (three dark rectangles) at the face centre,
     because the fields tile alone does not read as a town.
   Marker sizes scale with `board.scale`.

Performance: at most `(cols + 2) × (rows + 2)` = 140 blits per repaint at seed 42.
The widget repaints at most every 250 ms.

## 5. Legend

- Faction rows and symbol rows keep their order and wording. Each swatch
  becomes a small diamond painted with the same overlay painters as the map,
  on a darkened plains tile.
- A new **Terrain** section follows, one row per simulation terrain in
  `[balance.terrain_defence]` order: plains, forest, hills, mountain, urban.
  Each row shows the darkened tile thumbnail at scale 1 and the terrain's name.
  Defence multipliers are not shown: the view model carries no config, and they
  are balance values that belong in the docs.
- `legend_height` accounts for the terrain rows, whose thumbnails are 48 px
  cells; the row height for terrain is 30 px (the thumbnail's top face and a
  little of its side, clipped).

## Testing

- **iso:** `board_for` picks the largest fitting integer scale (1 at 600×400
  with the 12×8 grid, 2 at 1400×800, and 1 when nothing fits); `tile_origin`
  steps by (24, 12) and (−24, 12) × scale; `draw_order` is sorted by `col + row`
  and includes the ring; `province_at(face_centre(p)) == p` for every province
  at scales 1, 2 and 3, and outside the board returns `None`, as does the ragged
  last row.
- **terrain:** every key of `[balance.terrain_defence]` has a tile; `tile_for` is
  stable per id and falls back for an unknown terrain; `grim` never brightens a
  pixel, never raises alpha, leaves the input untouched, and reduces saturation;
  the sheet file ships and is 432×384.
- **view:** `ProvinceCell.terrain` equals the world's terrain for every province.
- **render (cairo image surface, no display):** at a province's face centre the
  pixel is closer to its own faction colour than to any other faction's; a
  contested province's face contains hatch-dark pixels and an uncontested one's
  does not; water appears outside the board; an empty view and a 20×20 surface
  render without raising.
- **legend:** the terrain section lists the five terrains in order; the legend
  still paints each faction's colour.
- **By eye:** launch `bin/endless-war --faction 0 --speed 16x`, capture the Map
  tab with `window.draw()` into a cairo surface, and check ownership, markers,
  legend and scaling at the default and a maximised window.

## Documentation

- `docs/architecture.md`: the `ui/` section names `iso.py` and `terrain.py`, and the asset.
- `docs/decisions.md`: a dated entry recording the pack and its CC0 licence, the
  isometric switch, integer scaling, dark terrain with a faction wash (mockup D)
  and why the other three mockups lost, and terrain now being visible.
- `README.md`: one sentence that the map shows terrain.
