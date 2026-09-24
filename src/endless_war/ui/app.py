"""The War Room window.

Do not import from the simulation core here. The only contact with the
simulation is `service.latest_view()` and `service.submit(...)`, which is what
makes it impossible for a UI handler to mutate world state.
"""

from __future__ import annotations

import argparse
import traceback

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from endless_war.app.commands import BindFaction, Pause, Resume, SetSpeed  # noqa: E402
from endless_war.app.service import SimulationService  # noqa: E402
from endless_war.config import load_config  # noqa: E402
from endless_war.ui.legend import LegendView  # noqa: E402
from endless_war.ui.map_view import MapView  # noqa: E402
from endless_war.ui.panels import (  # noqa: E402
    event_lines,
    header_text,
    status_rows,
    tray_summary,
)
from endless_war.ui.tray import Tray  # noqa: E402

REFRESH_MS = 250


class WarRoom:
    """Window, widgets, and the timer that pulls snapshots."""

    def __init__(self, service: SimulationService, cols: int) -> None:
        self._service = service
        self._paused = False
        self._timer_id: int | None = None
        # Sticky: once shown, a UI fault stays in the header for the rest of
        # the session, because stderr is invisible when launched from a menu.
        self._ui_fault: str | None = None

        self.window = Gtk.Window(title="Endless War")
        self.window.set_default_size(980, 640)
        self.window.connect("delete-event", self._on_delete)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        outer.set_border_width(6)
        self.window.add(outer)

        self.toolbar_buttons: list[Gtk.Button] = []
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.header = Gtk.Label(label="")
        self.header.set_xalign(0.0)
        bar.pack_start(self.header, True, True, 0)
        for speed in ("1x", "4x", "16x"):
            button = Gtk.Button(label=speed)
            button.connect("clicked", lambda _b, s=speed: self._set_speed(s))
            bar.pack_start(button, False, False, 0)
            self.toolbar_buttons.append(button)
        self._pause_button = Gtk.Button(label="Pause")
        self._pause_button.connect("clicked", lambda _b: self._toggle_pause())
        bar.pack_start(self._pause_button, False, False, 0)
        self.toolbar_buttons.append(self._pause_button)
        outer.pack_start(bar, False, False, 0)

        middle = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.map_view = MapView(cols)
        middle.pack_start(self.map_view, True, True, 0)
        self.status = Gtk.Label(label="")
        self.status.set_xalign(0.0)
        self.status.set_yalign(0.0)
        self.legend = LegendView()
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        side.set_size_request(220, -1)
        side.pack_start(self.status, False, False, 0)
        side.pack_start(self.legend, False, False, 0)
        middle.pack_start(side, False, False, 0)
        outer.pack_start(middle, True, True, 0)

        self.events = Gtk.Label(label="")
        self.events.set_xalign(0.0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_size_request(-1, 120)
        scroller.add(self.events)
        outer.pack_start(scroller, False, False, 0)

        self.tray = Tray(
            on_open=self._on_open,
            on_toggle_pause=self._toggle_pause,
            on_speed=self._set_speed,
            on_quit=self._on_quit,
        )

        self._timer_id = GLib.timeout_add(REFRESH_MS, self._on_timer)

    # -- commands out -----------------------------------------------------

    def _toggle_pause(self) -> None:
        self._service.submit(Resume() if self._paused else Pause())

    def _set_speed(self, speed: str) -> None:
        self._service.submit(SetSpeed(speed))

    # Intentionally unwired: no widget calls this until a faction picker
    # exists. `--faction` binds at launch through the service instead.
    def bind_faction(self, faction_id: int | None) -> None:
        self._service.submit(BindFaction(faction_id))

    # -- snapshots in -----------------------------------------------------

    def refresh(self) -> None:
        view = self._service.latest_view()
        if view is None:
            return
        self._paused = view.speed == "paused"
        self._pause_button.set_label("Resume" if self._paused else "Pause")
        header = header_text(view)
        if self._ui_fault is not None:
            header += f"   ·   UI FAULT: {self._ui_fault}"
        self.header.set_text(header)
        self.status.set_text(
            "\n".join(f"{label}  {value}".rstrip() for label, value in status_rows(view))
        )
        # Newest first: the feed's scroller opens at the top.
        self.events.set_text("\n".join(reversed(event_lines(view))))
        self.map_view.set_view(view)
        self.legend.set_view(view)
        self.tray.set_summary(tray_summary(view))
        self.tray.set_paused(self._paused)

    def _on_timer(self) -> bool:
        # GLib silently drops a timeout source whose callback raises, which
        # would freeze the window for good with only a stderr traceback --
        # invisible when launched from the tray or a desktop file. Mirror
        # the service's `_safe_publish`: report the failure where the user
        # can see it, and keep the timer alive.
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            traceback.print_exc()
            self._ui_fault = f"{type(exc).__name__}: {exc}"
            try:
                self.header.set_text(f"UI FAULT: {self._ui_fault}")
            except Exception:  # noqa: BLE001 - the timer must survive
                pass
        return True

    # -- lifecycle --------------------------------------------------------

    def show(self) -> None:
        self.window.show_all()
        self.window.present()
        # Showing the window gives it keyboard focus, and GTK hands that to
        # the first focusable widget -- the 1x button -- so a space typed into
        # another app at that moment changed the speed. Clear it; Tab still
        # reaches every button once the user is deliberately in the window.
        self.window.set_focus(None)

    def _on_open(self) -> None:
        self.show()

    def _on_delete(self, _widget, _event) -> bool:
        self.window.hide()
        return True

    def _on_quit(self) -> None:
        self.shutdown()
        self._service.stop()
        Gtk.main_quit()

    def shutdown(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self.tray.close()
        # GTK keeps every `Gtk.Window` on its own internal list of toplevels
        # until it is explicitly destroyed; hiding it (as `_on_delete` does
        # to keep the app alive in the tray) is not enough to let it, this
        # WarRoom, and everything closed over by its signal handlers be
        # freed. This is the real teardown, so destroy it here.
        self.window.destroy()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="endless-war-gui")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--faction", type=int, default=None)
    parser.add_argument("--speed", default="1x")
    args = parser.parse_args(argv)

    # Imported here so the module's import graph stays UI-only at module scope.
    from endless_war.simulation.worldgen import generate_world

    config = load_config()
    world = generate_world(seed=args.seed, config=config)

    # A typo in --faction must be caught here, at the command line, rather
    # than papered over by the formatters' unknown-id fallback three layers
    # down (that fallback is the last line of defence, not the first).
    if args.faction is not None and args.faction not in world.factions:
        valid_ids = sorted(world.factions.keys())
        raise SystemExit(
            f"--faction {args.faction} is not a valid faction id; "
            f"valid ids are {valid_ids}"
        )

    service = SimulationService(
        world, config, bound_faction_id=args.faction, speed=args.speed
    )
    room = WarRoom(service, cols=config["world"]["grid_cols"])
    service.start()
    room.show()
    try:
        Gtk.main()
    finally:
        room.shutdown()
        service.stop()


if __name__ == "__main__":
    main()
