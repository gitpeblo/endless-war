"""Text for the status panel, the event feed and the tray.

Pure functions of a WorldView. Keeping the formatting out of the widgets is
what makes any of this testable without a display.
"""

from __future__ import annotations

from endless_war.app.view_model import WorldView


def header_text(view: WorldView) -> str:
    """The one-line title bar: date, speed, and a fault if there is one."""
    date = view.simulated_at.date().isoformat()
    if view.faulted:
        return f"{date}   ·   {view.speed}   ·   FAULT: {view.fault_message}"
    return f"{date}   ·   {view.speed}"


def _faction_block(view: WorldView, faction_id: int) -> list[tuple[str, str]]:
    faction = next(f for f in view.factions if f.id == faction_id)
    at_war = ", ".join(
        other.name for other in view.factions if other.id in faction.at_war_with
    )
    return [
        (faction.name, ""),
        ("provinces", str(faction.provinces)),
        ("population", f"{faction.population:,}"),
        ("casualties", f"{faction.casualties:,}"),
        ("exhaustion", f"{faction.exhaustion:.2f}"),
        ("at war with", at_war or "nobody"),
    ]


def status_rows(view: WorldView) -> list[tuple[str, str]]:
    """Label/value pairs for the side panel."""
    if view.bound_faction_id is not None:
        return _faction_block(view, view.bound_faction_id)
    rows: list[tuple[str, str]] = [("World", "")]
    for faction in view.factions:
        rows.append((faction.name, f"{faction.provinces} prov · {faction.population:,}"))
    rows.append(("wars", f"{view.active_wars} active / {view.total_wars} total"))
    return rows


def event_lines(view: WorldView) -> list[str]:
    """One line per recent event, oldest first."""
    return [
        f"{event.simulated_at.date().isoformat()}  {event.title}: {event.body}"
        for event in view.recent_events
    ]


def tray_summary(view: WorldView) -> str:
    """A single line for the tray menu header."""
    date = view.simulated_at.date().isoformat()
    if view.bound_faction_id is not None:
        faction = next(f for f in view.factions if f.id == view.bound_faction_id)
        return (
            f"{date} · {faction.name} · {faction.provinces} prov · "
            f"{view.active_wars} wars · {view.speed}"
        )
    return (
        f"{date} · {len(view.factions)} factions · "
        f"{view.active_wars} wars active · {view.speed}"
    )
