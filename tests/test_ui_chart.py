from datetime import datetime, timedelta, timezone

import cairo

from endless_war.app.view_model import CasualtyReading, FactionRow
from endless_war.ui.chart import (
    MARGIN_LEFT,
    MARGIN_RIGHT,
    TOOLTIP_BG,
    compact_number,
    nearest_reading,
    nice_ticks,
    render_casualty_chart,
    series_for,
    spread_labels,
    x_ticks,
)
from endless_war.ui.colors import faction_rgb

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
WIDTH, HEIGHT = 600, 300


def _faction(fid: int, key: str, name: str) -> FactionRow:
    return FactionRow(
        id=fid, name=name, color_key=key, provinces=1, population=1, manpower=1,
        treasury=0.0, casualties=0, exhaustion=0.0, war_support=0.5,
        stability=0.5, at_war_with=(),
    )


FACTIONS = (_faction(0, "blue", "Valdran"), _faction(1, "teal", "Korsk"))


def _readings(days: int, rate0: int = 100, rate1: int = 400):
    return tuple(
        CasualtyReading(T0 + timedelta(days=d), ((0, d * rate0), (1, d * rate1)))
        for d in range(days)
    )


def _render(readings, visible, width=WIDTH, height=HEIGHT, hover_x=None):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, width, height)
    render_casualty_chart(
        cairo.Context(surface), readings, FACTIONS, frozenset(visible), width, height, hover_x
    )
    surface.flush()
    return surface


def _count(surface, rgb, tolerance=3) -> int:
    want = [round(c * 255) for c in rgb]
    data, stride = surface.get_data(), surface.get_stride()
    found = 0
    for y in range(surface.get_height()):
        row = y * stride
        for x in range(surface.get_width()):
            o = row + x * 4
            if (abs(data[o + 2] - want[0]) <= tolerance
                    and abs(data[o + 1] - want[1]) <= tolerance
                    and abs(data[o] - want[2]) <= tolerance):
                found += 1
    return found


def test_compact_number() -> None:
    assert compact_number(0) == "0"
    assert compact_number(950) == "950"
    assert compact_number(1_500) == "1.5k"
    assert compact_number(20_000) == "20k"
    assert compact_number(1_000_000) == "1M"
    assert compact_number(1_200_000) == "1.2M"


def test_nice_ticks() -> None:
    assert nice_ticks(0) == [0, 1]
    assert nice_ticks(1) == [0, 1]
    assert nice_ticks(3) == [0, 1, 2, 3]
    assert nice_ticks(7) == [0, 2, 4, 6, 8]
    assert nice_ticks(40_000) == [0, 10_000, 20_000, 30_000, 40_000]
    assert nice_ticks(43_000) == [0, 20_000, 40_000, 60_000]
    big = nice_ticks(123_456_789)
    assert big[0] == 0 and big[-1] >= 123_456_789 and 3 <= len(big) <= 5


def test_x_ticks_mark_years_or_else_months() -> None:
    years = x_ticks(T0, datetime(2032, 6, 1, tzinfo=timezone.utc))
    assert [label for _, label in years] == ["2031", "2032"]
    assert years[0][0] == datetime(2031, 1, 1, tzinfo=timezone.utc)
    months = x_ticks(T0, datetime(2030, 4, 15, tzinfo=timezone.utc))
    assert [label for _, label in months] == ["Feb", "Mar", "Apr"]


def test_series_for_reads_one_faction() -> None:
    readings = _readings(3)
    assert series_for(readings, 1) == [(T0 + timedelta(days=d), d * 400) for d in range(3)]
    assert series_for(readings, 9) == [(T0 + timedelta(days=d), 0) for d in range(3)]


def test_nearest_reading() -> None:
    readings = _readings(3)
    x0, x1 = MARGIN_LEFT, WIDTH - MARGIN_RIGHT
    assert nearest_reading(readings, x0, WIDTH) == 0
    assert nearest_reading(readings, (x0 + x1) / 2, WIDTH) == 1
    assert nearest_reading(readings, x1, WIDTH) == 2
    assert nearest_reading(readings, x0 - 1, WIDTH) is None, "left margin"
    assert nearest_reading(readings, x1 + 1, WIDTH) is None, "label margin"
    assert nearest_reading((), (x0 + x1) / 2, WIDTH) is None


def test_spread_labels_pushes_overlaps_apart_and_keeps_order() -> None:
    assert spread_labels([100.0, 105.0, 300.0], 14.0) == [100.0, 114.0, 300.0]
    assert spread_labels([105.0, 100.0], 14.0) == [114.0, 100.0]
    assert spread_labels([], 14.0) == []


def test_a_visible_factions_line_is_drawn_in_its_colour() -> None:
    surface = _render(_readings(60), {0, 1})
    assert _count(surface, faction_rgb("blue")) > 20
    assert _count(surface, faction_rgb("teal")) > 20


def test_a_hidden_faction_is_drawn_nowhere() -> None:
    surface = _render(_readings(60), {0})
    assert _count(surface, faction_rgb("blue")) > 20
    assert _count(surface, faction_rgb("teal")) == 0


def test_hiding_the_larger_series_rescales_the_axis() -> None:
    # Faction 1 dwarfs faction 0. With 1 hidden, faction 0's line must climb
    # to the top of the plot instead of hugging the baseline.
    def highest_blue_row(surface) -> int:
        want = [round(c * 255) for c in faction_rgb("blue")]
        data, stride = surface.get_data(), surface.get_stride()
        for y in range(surface.get_height()):
            for x in range(int(MARGIN_LEFT), int(WIDTH - MARGIN_RIGHT)):
                o = y * stride + x * 4
                if all(abs(data[o + 2 - k] - want[k]) <= 3 for k in range(3)):
                    return y
        return HEIGHT

    both = highest_blue_row(_render(_readings(60), {0, 1}))
    alone = highest_blue_row(_render(_readings(60), {0}))
    assert alone < both - 50


def test_empty_states_render_without_raising() -> None:
    _render((), {0, 1})
    _render(_readings(30), set())
    _render((), set(), hover_x=200.0)


def test_one_reading_and_all_zero_values_render() -> None:
    _render(_readings(1), {0, 1})
    zeros = tuple(CasualtyReading(T0 + timedelta(days=d), ((0, 0), (1, 0))) for d in range(5))
    _render(zeros, {0, 1}, hover_x=200.0)


def test_a_tiny_widget_renders_without_raising() -> None:
    _render(_readings(30), {0, 1}, width=50, height=30, hover_x=10.0)


def test_hover_draws_a_tooltip_inside_the_plot_and_not_in_the_margin() -> None:
    readings = _readings(60)
    inside = _render(readings, {0, 1}, hover_x=(MARGIN_LEFT + WIDTH - MARGIN_RIGHT) / 2)
    margin = _render(readings, {0, 1}, hover_x=MARGIN_LEFT / 2)
    assert _count(inside, TOOLTIP_BG, tolerance=1) > 100
    assert _count(margin, TOOLTIP_BG, tolerance=1) == 0


def test_a_century_of_readings_renders() -> None:
    readings = tuple(
        CasualtyReading(T0 + timedelta(days=d), ((0, d), (1, d * 3))) for d in range(36_500)
    )
    _render(readings, {0, 1}, hover_x=300.0)


def _bright_pixels(surface, xs: range, ys: range) -> int:
    # Anything clearly lighter than the background is ink: text or a mark.
    data, stride = surface.get_data(), surface.get_stride()
    return sum(
        1
        for y in ys
        for x in xs
        if sum(data[y * stride + x * 4 + k] for k in range(3)) > 3 * 80
    )


def test_the_axes_have_titles() -> None:
    # Asked for by the user: tick values alone do not say what is measured.
    surface = _render(_readings(60), {0, 1})
    assert _bright_pixels(surface, range(0, 16), range(HEIGHT)) > 20, "y-axis title"
    assert _bright_pixels(surface, range(WIDTH), range(HEIGHT - 9, HEIGHT)) > 20, "x-axis title"
