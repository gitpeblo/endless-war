import dataclasses
import re
from datetime import datetime, timezone

import pytest

from endless_war.app.view_model import EventLine, FactionRow, ProvinceCell, WorldView


def _cell() -> ProvinceCell:
    return ProvinceCell(
        id=0,
        name="P000",
        owner_faction_id=1,
        controller_faction_id=2,
        color_key="blue",
        is_capital=False,
        is_contested=True,
        has_armies=True,
        has_supply_problem=False,
    )


def test_a_province_cell_cannot_be_mutated() -> None:
    cell = _cell()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cell.controller_faction_id = 3


def test_a_world_view_cannot_be_mutated() -> None:
    view = WorldView(
        simulated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        tick_count=4,
        speed="1x",
        faulted=False,
        fault_message=None,
        bound_faction_id=None,
        provinces=(_cell(),),
        factions=(),
        recent_events=(),
        active_wars=0,
        total_wars=0,
        casualty_history=(),
        event_log=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.tick_count = 5


def test_collections_on_a_view_are_tuples_not_lists() -> None:
    view = WorldView(
        simulated_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        tick_count=0,
        speed="paused",
        faulted=False,
        fault_message=None,
        bound_faction_id=2,
        provinces=(_cell(),),
        factions=(
            FactionRow(
                id=2,
                name="Meridian Compact",
                color_key="blue",
                provinces=21,
                population=11_255_752,
                manpower=1_000,
                treasury=5.0,
                casualties=0,
                exhaustion=0.0,
                war_support=0.5,
                stability=1.0,
                at_war_with=(1,),
            ),
        ),
        recent_events=(
            EventLine(
                id=7,
                simulated_at=datetime(2030, 6, 1, tzinfo=timezone.utc),
                category="diplomacy",
                severity="critical",
                title="War declared",
                body="A has declared war on B.",
            ),
        ),
        active_wars=1,
        total_wars=1,
        casualty_history=(),
        event_log=(),
    )
    assert isinstance(view.provinces, tuple)
    assert isinstance(view.factions, tuple)
    assert isinstance(view.recent_events, tuple)
    assert isinstance(view.factions[0].at_war_with, tuple)


def test_a_view_holds_no_simulation_objects() -> None:
    """A view must be safe to read while the simulation mutates its own state."""
    forbidden_types = ("WorldState", "Province", "Faction", "Army", "War", "Event")

    for cls in (ProvinceCell, FactionRow, EventLine, WorldView):
        for field in dataclasses.fields(cls):
            annotation_str = str(field.type)
            for forbidden in forbidden_types:
                assert not re.search(rf"\b{forbidden}\b", annotation_str), \
                    f"{cls.__name__}.{field.name} leaks {forbidden}: {annotation_str}"
