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
from endless_war.ui.panels import event_log_lines  # noqa: E402

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

        self.log = Gtk.Label(label="")
        self.log.set_xalign(0.0)
        self.log.set_yalign(0.0)
        scroller = Gtk.ScrolledWindow()
        scroller.add(self.log)
        self.pack_start(scroller, True, True, 0)

    def set_view(self, view: WorldView) -> None:
        for faction in view.factions:
            if faction.id not in self.toggles:
                self._add_toggle(faction.id, faction.name, faction.color_key)
        self.chart.set_data(view.casualty_history, view.factions)
        self.chart.set_visible(frozenset(self._visible))
        newest = view.event_log[-1].id if view.event_log else None
        if newest != self._newest_event_id:
            self._newest_event_id = newest
            self.log.set_text("\n".join(event_log_lines(view)))

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
