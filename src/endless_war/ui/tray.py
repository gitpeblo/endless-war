"""Ayatana tray indicator.

Ubuntu 24.04 ships the Ayatana fork; the legacy AppIndicator3 namespace is not
installed. Save is present but disabled until persistence lands.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gtk  # noqa: E402

from endless_war.app.clock import RUNNING_SPEEDS  # noqa: E402

INDICATOR_ID = "endless-war"


class Tray:
    """The tray icon and its menu."""

    def __init__(
        self,
        on_open: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_speed: Callable[[str], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._indicator = AppIndicator.Indicator.new(
            INDICATOR_ID,
            "applications-games",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

        menu = Gtk.Menu()

        self._summary = Gtk.MenuItem(label="starting…")
        self._summary.set_sensitive(False)
        menu.append(self._summary)
        menu.append(Gtk.SeparatorMenuItem())

        open_item = Gtk.MenuItem(label="Open War Room")
        open_item.connect("activate", lambda _i: on_open())
        menu.append(open_item)

        self._pause_item = Gtk.MenuItem(label="Pause")
        self._pause_item.connect("activate", lambda _i: on_toggle_pause())
        menu.append(self._pause_item)

        speed_item = Gtk.MenuItem(label="Speed")
        speed_menu = Gtk.Menu()
        for speed in RUNNING_SPEEDS:
            entry = Gtk.MenuItem(label=speed)
            entry.connect("activate", lambda _i, s=speed: on_speed(s))
            speed_menu.append(entry)
        speed_item.set_submenu(speed_menu)
        menu.append(speed_item)

        save_item = Gtk.MenuItem(label="Save (needs persistence)")
        save_item.set_sensitive(False)
        menu.append(save_item)

        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _i: on_quit())
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)
        self._menu = menu

    def set_summary(self, text: str) -> None:
        self._summary.set_label(text)

    def set_paused(self, paused: bool) -> None:
        self._pause_item.set_label("Resume" if paused else "Pause")

    def close(self) -> None:
        """Release the indicator and drop its menu.

        A `WarRoom` is torn down by dropping references to it, never by an
        explicit "destroy everything" call from GTK itself (unlike a
        top-level `Gtk.Window`, an `AppIndicator.Indicator` is not tracked
        on any internal list that would otherwise keep it alive). But the
        indicator's D-Bus StatusNotifierItem registration is still live
        until the indicator, and the menu it owns, are actually released:
        without this, a second `Tray` created later in the same process
        (as happens across tests, all using the fixed `INDICATOR_ID`) logs
        libayatana/dbusmenu warnings about the object path still being
        exported by the one that came before it.
        """
        self._indicator.set_status(AppIndicator.IndicatorStatus.PASSIVE)
        self._menu.destroy()
