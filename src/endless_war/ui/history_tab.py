"""The History tab: per-faction toggles, the casualty chart, the full log.

Toggling a faction changes only what the chart draws. It never reaches the
simulation, so it goes nowhere near `service.submit()`.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from endless_war.app.view_model import WorldView  # noqa: E402
from endless_war.ui.chart import CasualtyChart  # noqa: E402
from endless_war.ui.colors import faction_rgb  # noqa: E402
from endless_war.ui.panels import event_line  # noqa: E402

SWATCH_PX = 12


def _swatch(color_key: str) -> Gtk.DrawingArea:
    area = Gtk.DrawingArea()
    area.set_size_request(SWATCH_PX, SWATCH_PX)
    rgb = faction_rgb(color_key)

    def draw(_widget, cr) -> bool:
        cr.set_source_rgb(*rgb)
        cr.rectangle(0, 0, SWATCH_PX, SWATCH_PX)
        cr.fill()
        return False

    area.connect("draw", draw)
    return area


class HistoryTab(Gtk.Box):
    """Toggle row (which doubles as the legend), chart, then the event log."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.toggles: dict[int, Gtk.CheckButton] = {}
        self._visible: set[int] = set()
        self._newest_event_id: int | None = None

        self._toggle_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.pack_start(self._toggle_row, False, False, 0)

        self.chart = CasualtyChart()
        self.pack_start(self.chart, False, False, 0)

        # A list view, not a Label: re-laying out one Label holding the whole
        # log stalled the main loop by ~0.2-0.8 s per new event in long games.
        # The view lays out only the rows on screen, and rows are added and
        # removed one by one. Store order is newest first: (event id, line).
        self._store = Gtk.ListStore(int, str)
        self.log = Gtk.TreeView(model=self._store)
        self.log.set_headers_visible(False)
        column = Gtk.TreeViewColumn("Event", Gtk.CellRendererText(), text=1)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        self.log.append_column(column)
        self.log.set_fixed_height_mode(True)
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.log)
        self.pack_start(scroller, True, True, 0)

    def set_view(self, view: WorldView) -> None:
        for faction in view.factions:
            if faction.id not in self.toggles:
                self._add_toggle(faction.id, faction.name, faction.color_key)
        self.chart.set_data(view.casualty_history, view.factions)
        self.chart.set_visible(frozenset(self._visible))
        self._update_log(view.event_log)

    def log_lines(self) -> list[str]:
        """The log as shown, newest first."""
        return [row[1] for row in self._store]

    def mark_oldest_row(self, text: str) -> None:
        """Test hook: overwrite the bottom row's text, to prove it is kept."""
        self._store[len(self._store) - 1][1] = text

    def _update_log(self, events) -> None:
        newest = events[-1].id if events else None
        if newest == self._newest_event_id:
            return  # evictions only ever accompany new events
        store = self._store
        shown_newest = self._newest_event_id
        self._newest_event_id = newest
        if newest is None or shown_newest is None or shown_newest > newest:
            # Nothing shown yet, or a log that is not a continuation of it.
            store.clear()
            fresh = events
        else:
            count = newest - shown_newest
            fresh = events[-count:] if count < len(events) else events
            if count >= len(events):
                store.clear()
        oldest = events[0].id if events else None
        while len(store) and store[len(store) - 1][0] < oldest:
            store.remove(store.get_iter(len(store) - 1))
        for event in fresh:
            store.insert(0, [event.id, event_line(event)])

    def _add_toggle(self, faction_id: int, name: str, color_key: str) -> None:
        button = Gtk.CheckButton()
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content.pack_start(_swatch(color_key), False, False, 0)
        content.pack_start(Gtk.Label(label=name), False, False, 0)
        button.add(content)
        button.set_active(True)
        self._visible.add(faction_id)
        button.connect("toggled", self._on_toggled, faction_id)
        button.show_all()
        self._toggle_row.pack_start(button, False, False, 0)
        self.toggles[faction_id] = button

    def _on_toggled(self, button: Gtk.CheckButton, faction_id: int) -> None:
        if button.get_active():
            self._visible.add(faction_id)
        else:
            self._visible.discard(faction_id)
        self.chart.set_visible(frozenset(self._visible))
