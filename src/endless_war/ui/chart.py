"""The casualty chart.

`render_casualty_chart` draws onto any cairo context, so it is tested against
an image surface with no display; the helpers it uses are plain functions.
`CasualtyChart` is the GTK widget wrapped around them.
"""

from __future__ import annotations

import bisect
import math
from datetime import datetime, timedelta

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402

from endless_war.app.view_model import CasualtyReading, FactionRow  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.map_view import BACKGROUND  # noqa: E402

MARGIN_LEFT = 66.0  # room for the rotated y title and the tick values
MARGIN_RIGHT = 150.0  # room for the direct labels
MARGIN_TOP = 12.0
MARGIN_BOTTOM = 40.0  # room for the date ticks and the x title
FONT_SIZE = 11.0
LINE_WIDTH = 2.0
LABEL_GAP = FONT_SIZE + 3
MIN_X_LABEL_SPACING = 50.0
Y_TITLE = "Cumulative deaths"
X_TITLE = "Simulated date"
TEXT_RGB = (0.85, 0.85, 0.85)
MUTED_RGB = (0.58, 0.59, 0.62)
GRID_RGBA = (1.0, 1.0, 1.0, 0.08)
CROSSHAIR_RGBA = (1.0, 1.0, 1.0, 0.35)
TOOLTIP_BG = (0.16, 0.17, 0.20)
TOOLTIP_BORDER = (0.32, 0.33, 0.37)


# -- pure helpers -----------------------------------------------------------


def compact_number(n: int) -> str:
    """950, 1.5k, 20k, 1.2M."""
    for divisor, suffix in ((1_000_000, "M"), (1_000, "k")):
        if n >= divisor:
            value = n / divisor
            text = f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.1f}"
            return text + suffix
    return str(n)


def nice_ticks(max_value: int) -> list[int]:
    """0 and round 1-2-5 steps up to the first one at or above `max_value`."""
    if max_value <= 0:
        return [0, 1]
    raw = max_value / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= raw)
    step = max(1, int(round(step)))
    return [i * step for i in range(math.ceil(max_value / step) + 1)]


def _month_starts(t0: datetime, t1: datetime) -> list[datetime]:
    out = []
    year, month = t0.year, t0.month
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        start = datetime(year, month, 1, tzinfo=t0.tzinfo)
        if start > t1:
            return out
        out.append(start)


def x_ticks(t0: datetime, t1: datetime) -> list[tuple[datetime, str]]:
    """Each 1 January in (t0, t1]; failing that, each first of the month."""
    years = [datetime(y, 1, 1, tzinfo=t0.tzinfo) for y in range(t0.year + 1, t1.year + 1)]
    if years:
        return [(d, str(d.year)) for d in years]
    return [(d, d.strftime("%b")) for d in _month_starts(t0, t1)]


def series_for(readings, faction_id: int) -> list[tuple[datetime, int]]:
    return [(r.simulated_at, dict(r.casualties).get(faction_id, 0)) for r in readings]


def nearest_reading(readings, x: float, width: float) -> int | None:
    """Index of the reading under pointer `x`, or None outside the plot."""
    x0, x1 = MARGIN_LEFT, width - MARGIN_RIGHT
    if not readings or x1 <= x0 or x < x0 or x > x1:
        return None
    t0 = readings[0].simulated_at
    span = (readings[-1].simulated_at - t0).total_seconds()
    if span <= 0:
        return len(readings) - 1
    target = t0 + timedelta(seconds=(x - x0) / (x1 - x0) * span)
    i = bisect.bisect_left(readings, target, key=lambda r: r.simulated_at)
    if i >= len(readings):
        return len(readings) - 1
    if i > 0 and target - readings[i - 1].simulated_at <= readings[i].simulated_at - target:
        return i - 1
    return i


def spread_labels(ys: list[float], min_gap: float, lowest: float | None = None) -> list[float]:
    """Space label positions `min_gap` apart, never below `lowest`.

    Overlaps are pushed down first; if that runs past `lowest`, the stack is
    pushed back up from the bottom instead.
    """
    order = sorted(range(len(ys)), key=lambda k: ys[k])
    out = list(ys)
    previous: float | None = None
    for i in order:
        if previous is not None and out[i] < previous + min_gap:
            out[i] = previous + min_gap
        previous = out[i]
    if lowest is not None:
        ceiling = lowest
        for i in reversed(order):
            if out[i] > ceiling:
                out[i] = ceiling
            ceiling = out[i] - min_gap
    return out


# -- rendering --------------------------------------------------------------


def _x_at(t: datetime, t0: datetime, span: float, x0: float, x1: float) -> float:
    if span <= 0:
        return x1
    return x0 + (t - t0).total_seconds() / span * (x1 - x0)


def _centred_text(cr, text: str, x: float, y: float) -> None:
    extents = cr.text_extents(text)
    cr.set_source_rgb(*MUTED_RGB)
    cr.move_to(x - extents.x_advance / 2, y)
    cr.show_text(text)


def _y_axis(cr, ticks: list[int], y_of, x0: float, x1: float) -> None:
    cr.set_line_width(1.0)
    for value in ticks:
        y = round(y_of(value)) + 0.5
        cr.set_source_rgba(*GRID_RGBA)
        cr.move_to(x0, y)
        cr.line_to(x1, y)
        cr.stroke()
        label = compact_number(value)
        cr.set_source_rgb(*MUTED_RGB)
        cr.move_to(x0 - 8 - cr.text_extents(label).x_advance, y + FONT_SIZE * 0.35)
        cr.show_text(label)


def _x_axis(cr, t0: datetime, t1: datetime, x_of, x0: float, x1: float, y1: float) -> None:
    ticks = x_ticks(t0, t1)
    if not ticks:
        return
    stride = max(1, math.ceil(len(ticks) * MIN_X_LABEL_SPACING / (x1 - x0)))
    cr.set_line_width(1.0)
    for moment, label in ticks[::stride]:
        x = round(x_of(moment)) + 0.5
        cr.set_source_rgba(*GRID_RGBA)
        cr.move_to(x, y1)
        cr.line_to(x, y1 + 4)
        cr.stroke()
        cr.set_source_rgb(*MUTED_RGB)
        cr.move_to(x - cr.text_extents(label).x_advance / 2, y1 + 4 + FONT_SIZE)
        cr.show_text(label)


def _axis_titles(cr, x0: float, x1: float, y0: float, y1: float, height: float) -> None:
    cr.set_source_rgb(*MUTED_RGB)
    extents = cr.text_extents(X_TITLE)
    cr.move_to((x0 + x1) / 2 - extents.x_advance / 2, height - 4)
    cr.show_text(X_TITLE)
    extents = cr.text_extents(Y_TITLE)
    cr.save()
    cr.move_to(4 + FONT_SIZE, (y0 + y1) / 2 + extents.x_advance / 2)
    cr.rotate(-math.pi / 2)
    cr.show_text(Y_TITLE)
    cr.restore()


def _direct_labels(cr, ends: list[tuple[FactionRow, float]], x1: float, lowest: float) -> None:
    ys = spread_labels([y for _, y in ends], LABEL_GAP, lowest=lowest)
    for (faction, _), y in zip(ends, ys):
        cr.set_source_rgb(*faction_rgb(faction.color_key))
        cr.set_line_width(LINE_WIDTH)
        cr.move_to(x1 + 6, y)
        cr.line_to(x1 + 16, y)
        cr.stroke()
        cr.set_source_rgb(*TEXT_RGB)
        cr.move_to(x1 + 20, y + FONT_SIZE * 0.35)
        cr.show_text(faction.name)


def _hover(cr, reading: CasualtyReading, shown, x: float, y0: float, y1: float, width: float) -> None:
    cr.set_source_rgba(*CROSSHAIR_RGBA)
    cr.set_line_width(1.0)
    cr.move_to(round(x) + 0.5, y0)
    cr.line_to(round(x) + 0.5, y1)
    cr.stroke()

    values = dict(reading.casualties)
    rows = sorted(shown, key=lambda f: (-values.get(f.id, 0), f.id))
    lines = [(None, reading.simulated_at.date().isoformat())] + [
        (f, f"{f.name}  {values.get(f.id, 0):,}") for f in rows
    ]
    line_h, pad, swatch = FONT_SIZE + 5, 6.0, 8.0
    box_w = max(cr.text_extents(text).x_advance for _, text in lines) + 2 * pad + swatch + 6
    box_h = len(lines) * line_h + 2 * pad
    bx = x + 10 if x + 10 + box_w <= width else x - 10 - box_w
    by = y0 + 4
    cr.set_source_rgb(*TOOLTIP_BG)
    cr.rectangle(bx, by, box_w, box_h)
    cr.fill_preserve()
    cr.set_source_rgb(*TOOLTIP_BORDER)
    cr.stroke()
    for k, (faction, text) in enumerate(lines):
        baseline = by + pad + (k + 1) * line_h - 5
        if faction is not None:
            cr.set_source_rgb(*faction_rgb(faction.color_key))
            cr.rectangle(bx + pad, baseline - swatch, swatch, swatch)
            cr.fill()
        cr.set_source_rgb(*TEXT_RGB)
        cr.move_to(bx + pad + swatch + 6, baseline)
        cr.show_text(text)


def render_casualty_chart(
    cr,
    readings,
    factions,
    visible: frozenset[int],
    width: float,
    height: float,
    hover_x: float | None = None,
) -> None:
    """Draw cumulative casualties of the `visible` factions into `width` x `height`."""
    cr.set_source_rgb(*BACKGROUND)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    x0, x1 = MARGIN_LEFT, width - MARGIN_RIGHT
    y0, y1 = MARGIN_TOP, height - MARGIN_BOTTOM
    if x1 - x0 < 20 or y1 - y0 < 20:
        return
    cr.select_font_face("Sans")
    cr.set_font_size(FONT_SIZE)

    shown = [f for f in factions if f.id in visible]
    if not readings or not shown:
        cr.set_source_rgba(*GRID_RGBA)
        cr.set_line_width(1.0)
        cr.move_to(x0, round(y1) + 0.5)
        cr.line_to(x1, round(y1) + 0.5)
        cr.stroke()
        _axis_titles(cr, x0, x1, y0, y1, height)
        message = "No history yet" if not readings else "No faction selected"
        _centred_text(cr, message, (x0 + x1) / 2, (y0 + y1) / 2)
        return

    # Cumulative totals never fall, so the maximum is in the latest reading.
    latest = dict(readings[-1].casualties)
    ticks = nice_ticks(max(latest.get(f.id, 0) for f in shown))
    top = ticks[-1]

    def y_of(value: int) -> float:
        return y1 - value / top * (y1 - y0)

    t0, t1 = readings[0].simulated_at, readings[-1].simulated_at
    span = (t1 - t0).total_seconds()

    def x_of(moment: datetime) -> float:
        return _x_at(moment, t0, span, x0, x1)

    _y_axis(cr, ticks, y_of, x0, x1)
    _x_axis(cr, t0, t1, x_of, x0, x1, y1)
    _axis_titles(cr, x0, x1, y0, y1, height)

    # One reading per horizontal pixel is all the line can show.
    stride = max(1, len(readings) // max(1, int(x1 - x0)))
    sample = list(readings[::stride])
    if sample[-1] is not readings[-1]:
        sample.append(readings[-1])
    sample_values = [dict(r.casualties) for r in sample]
    xs = [x_of(r.simulated_at) for r in sample]

    cr.set_line_width(LINE_WIDTH)
    ends = []
    for faction in shown:
        cr.set_source_rgb(*faction_rgb(faction.color_key))
        for k, (x, values) in enumerate(zip(xs, sample_values)):
            y = y_of(values.get(faction.id, 0))
            if k == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        ends.append((faction, y_of(latest.get(faction.id, 0))))
    _direct_labels(cr, ends, x1, lowest=height - FONT_SIZE)

    if hover_x is not None:
        index = nearest_reading(readings, hover_x, width)
        if index is not None:
            reading = readings[index]
            _hover(cr, reading, shown, x_of(reading.simulated_at), y0, y1, width)


# -- widget -----------------------------------------------------------------


class CasualtyChart(Gtk.DrawingArea):
    """Paints the newest readings and tracks the pointer for the hover readout."""

    def __init__(self) -> None:
        super().__init__()
        self._readings: tuple[CasualtyReading, ...] = ()
        self._factions: tuple[FactionRow, ...] = ()
        self.visible: frozenset[int] = frozenset()
        self._hover_x: float | None = None
        self.set_size_request(-1, 260)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw", self._on_draw)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("leave-notify-event", self._on_leave)

    def set_data(self, readings, factions) -> None:
        self._readings = readings
        self._factions = factions
        self.queue_draw()

    def set_visible(self, visible: frozenset[int]) -> None:
        self.visible = visible
        self.queue_draw()

    def _on_motion(self, _widget, event) -> bool:
        self._hover_x = event.x
        self.queue_draw()
        return False

    def _on_leave(self, _widget, _event) -> bool:
        self._hover_x = None
        self.queue_draw()
        return False

    def _on_draw(self, _widget, cr) -> bool:
        allocation = self.get_allocation()
        render_casualty_chart(
            cr, self._readings, self._factions, self.visible,
            allocation.width, allocation.height, self._hover_x,
        )
        return False
