# Post-modern isometric (2:1) pixel sprites, 32x32: concrete, glass, industry.
import math
import sys

import cairo

N = 32
OX, OY = 16, 22  # screen position of world (0, 0, 0): the footprint centre

OUTLINE = (0x14, 0x16, 0x1a)
CONCRETE = ((0xa0, 0xa2, 0xa0), (0x80, 0x82, 0x80), (0x5e, 0x60, 0x60))   # top, left, right
GLASS = ((0x6a, 0x7a, 0x82), (0x44, 0x55, 0x5f), (0x30, 0x3c, 0x44))
PANEL = ((0x94, 0x90, 0x88), (0x76, 0x72, 0x6a), (0x56, 0x53, 0x4e))
METAL = ((0x7c, 0x84, 0x88), (0x62, 0x69, 0x6e), (0x47, 0x4d, 0x52))
LIT, UNLIT = (0xd8, 0xb8, 0x5a), (0x26, 0x2c, 0x32)
RUST = (0x8a, 0x3c, 0x2c)
FLAG = (0xa8, 0x32, 0x2e)
MAST = (0x2a, 0x2c, 0x31)
STEAM = ((0x9a, 0x9c, 0xa0), (0xc0, 0xc2, 0xc4))
# The capital has its own colours so it cannot be mistaken for grey housing.
MARBLE = ((0xde, 0xda, 0xcc), (0xbc, 0xb8, 0xaa), (0x90, 0x8c, 0x80))
GOLD_GLASS = ((0xc8, 0xa2, 0x52), (0x9c, 0x7a, 0x38), (0x72, 0x56, 0x26))
PALE_LIT = (0xf4, 0xe8, 0xc0)


def P(u, v, z):
    return OX + (u - v), OY + (u + v) / 2 - z


def rgb(cr, c):
    cr.set_source_rgb(*(x / 255 for x in c))


def poly(cr, pts, c):
    rgb(cr, c)
    cr.move_to(*P(*pts[0]))
    for p in pts[1:]:
        cr.line_to(*P(*p))
    cr.close_path()
    cr.fill()


def pixel(cr, x, y, c, w=1, h=1):
    rgb(cr, c)
    cr.rectangle(round(x), round(y), w, h)
    cr.fill()


def box(cr, u0, v0, U, V, H, pal, z0=0):
    top, left, right = pal
    u1, v1, z1 = u0 + U, v0 + V, z0 + H
    poly(cr, [(u0, v1, z0), (u1, v1, z0), (u1, v1, z1), (u0, v1, z1)], left)
    poly(cr, [(u1, v0, z0), (u1, v1, z0), (u1, v1, z1), (u1, v0, z1)], right)
    poly(cr, [(u0, v0, z1), (u1, v0, z1), (u1, v1, z1), (u0, v1, z1)], top)


def windows(cr, u0, v0, U, V, H, z0=0, du=2, dz=2, lit_every=3, seed=0):
    """A grid of 1 px windows on both visible faces; some lit, most dark."""
    k = seed
    for z in range(z0 + 1, z0 + H - 1, dz):
        for u in range(1, U, du):                       # left face (v = v0 + V)
            k += 1
            x, y = P(u0 + u, v0 + V, z + 1)
            pixel(cr, x, y, LIT if k % lit_every == 0 else UNLIT)
        for v in range(1, V, du):                       # right face (u = u0 + U)
            k += 1
            x, y = P(u0 + U, v0 + v, z + 1)
            pixel(cr, x - 1, y, LIT if k % (lit_every + 1) == 0 else UNLIT)


def capital(cr):
    box(cr, -8, -8, 16, 16, 3, MARBLE)                          # marble plinth
    box(cr, -4, -4, 8, 8, 13, GOLD_GLASS, z0=3)                 # gold glass tower
    windows(cr, -4, -4, 8, 8, 13, z0=3, du=2, dz=2, lit_every=2, seed=1)
    box(cr, -4, -4, 8, 8, 1, MARBLE, z0=16)                     # roof slab
    x, y = P(0, 0, 17)
    pixel(cr, x, y - 6, MAST, 1, 6)                             # mast
    pixel(cr, x + 1, y - 6, FLAG, 3, 2)
    pixel(cr, x + 1, y - 4, FLAG, 2, 1)
    for u in (-7, 5):                                           # plinth lights
        px, py = P(u, 8, 2)
        pixel(cr, px, py, PALE_LIT)


def town(cr):
    box(cr, -8, -7, 4, 10, 12, PANEL)                           # long slab block
    windows(cr, -8, -7, 4, 10, 12, du=2, dz=2, lit_every=4, seed=2)
    box(cr, -7, -5, 2, 2, 2, METAL, z0=12)                      # water tank
    box(cr, -2, -8, 9, 4, 8, PANEL)                             # mid block
    windows(cr, -2, -8, 9, 4, 8, du=2, dz=2, lit_every=3, seed=5)
    box(cr, 0, 1, 6, 6, 5, CONCRETE)                            # low block
    windows(cr, 0, 1, 6, 6, 5, du=2, dz=2, lit_every=2, seed=3)


def cooling_tower(cr, u, v, height=13):
    """A hyperboloid of stacked iso ellipses: base 5, waist 3.2 at 70 %, open top."""
    waist, z_waist = 3.2, 0.7 * height
    c = z_waist / math.sqrt((5.0 / waist) ** 2 - 1)

    def radius(z):
        return waist * math.sqrt(1 + ((z - z_waist) / c) ** 2)

    for step in range(0, height * 2 + 1):
        z = step / 2
        cx, cy = P(u, v, z)
        r = radius(z) * 1.414
        for side, col in ((0, CONCRETE[1]), (1, CONCRETE[2])):
            a0, a1 = (math.pi / 2, 3 * math.pi / 2) if side == 0 else (-math.pi / 2, math.pi / 2)
            cr.save(); cr.translate(cx, cy); cr.scale(1, 0.5)
            cr.move_to(0, 0); cr.arc(0, 0, r, a0, a1); cr.close_path()
            cr.restore(); rgb(cr, col); cr.fill()
    cx, cy = P(u, v, height)                                    # rim, then the dark mouth
    cr.save(); cr.translate(cx, cy); cr.scale(1, 0.5); cr.arc(0, 0, radius(height) * 1.414, 0, 2 * math.pi); cr.restore()
    rgb(cr, CONCRETE[0]); cr.fill()
    cr.save(); cr.translate(cx, cy); cr.scale(1, 0.5); cr.arc(0, 0, radius(height) * 1.414 - 1.5, 0, 2 * math.pi); cr.restore()
    rgb(cr, OUTLINE); cr.fill()


def industry(cr):
    box(cr, -6, -7, 2, 2, 16, CONCRETE)                         # stack
    for z in (12, 14):
        x, y = P(-4, -5, z)
        pixel(cr, x - 2, y, RUST, 2, 1)                         # stack bands
    box(cr, -8, -1, 10, 8, 5, METAL)                            # shed
    for u in range(-7, 2, 2):                                   # roof ribs
        a, b = P(u, -1, 5), P(u, 7, 5)
        rgb(cr, METAL[2]); cr.move_to(a[0] + 0.5, a[1]); cr.line_to(b[0] + 0.5, b[1]); cr.set_line_width(1); cr.stroke()
    x, y = P(-4, 7, 0)
    pixel(cr, x, y - 3, UNLIT, 3, 3)                            # loading bay
    cooling_tower(cr, 4, -3)


def outline(surface):
    surface.flush()
    data, stride = surface.get_data(), surface.get_stride()
    alpha = [[data[y * stride + x * 4 + 3] for x in range(N)] for y in range(N)]
    cr = cairo.Context(surface)
    for y in range(N):
        for x in range(N):
            if not alpha[y][x] and any(
                0 <= x + dx < N and 0 <= y + dy < N and alpha[y + dy][x + dx]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                pixel(cr, x, y, OUTLINE)


def render(fn, path, steam=None):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, N, N)
    cr = cairo.Context(surface)
    cr.set_antialias(cairo.ANTIALIAS_NONE)
    fn(cr)
    outline(surface)
    if steam:
        cr = cairo.Context(surface)
        x, y = P(*steam)
        for dx, dy, w, i in ((-2, -2, 4, 0), (-1, -3, 4, 1), (0, -4, 3, 1), (1, -5, 3, 0),
                             (1, -6, 2, 1), (3, -6, 2, 0), (2, -7, 2, 1), (4, -8, 1, 0)):
            pixel(cr, x + dx, y + dy, STEAM[i], w, 1)
    surface.write_to_png(path)
    print("wrote", path)


if __name__ == "__main__":
    out = sys.argv[1]
    render(capital, f"{out}/capital.png")
    render(town, f"{out}/town.png")
    render(industry, f"{out}/industry.png", steam=(4, -3, 13))
