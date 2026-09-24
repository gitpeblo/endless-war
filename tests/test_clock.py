import pytest

from endless_war.app.clock import SPEEDS, seconds_per_tick, ticks_due
from endless_war.app.commands import BindFaction, Pause, Resume, SetSpeed, Shutdown
from endless_war.config import load_config


def test_the_speeds_run_from_paused_to_64x() -> None:
    assert list(SPEEDS) == ["paused", "1x", "4x", "16x", "32x", "64x"]
    assert SPEEDS["paused"] == 0.0
    assert SPEEDS["1x"] == 1.0
    assert SPEEDS["4x"] == 4.0
    assert SPEEDS["16x"] == 16.0
    assert SPEEDS["32x"] == 32.0
    assert SPEEDS["64x"] == 64.0


def test_a_faster_speed_means_less_time_per_tick() -> None:
    assert seconds_per_tick("1x", 1.0) == 1.0
    assert seconds_per_tick("4x", 1.0) == 0.25
    assert seconds_per_tick("16x", 1.0) == 0.0625
    assert seconds_per_tick("32x", 1.0) == 0.03125
    assert seconds_per_tick("64x", 1.0) == 0.015625


def test_paused_has_no_tick_interval() -> None:
    assert seconds_per_tick("paused", 1.0) is None


def test_an_unknown_speed_is_rejected() -> None:
    with pytest.raises(ValueError):
        seconds_per_tick("ludicrous", 1.0)


def test_no_ticks_are_due_before_the_interval_elapses() -> None:
    assert ticks_due(0.5, "1x", 1.0, max_catchup=8) == 0


def test_ticks_accumulate_with_elapsed_time() -> None:
    assert ticks_due(1.0, "1x", 1.0, max_catchup=8) == 1
    assert ticks_due(3.7, "1x", 1.0, max_catchup=8) == 3
    assert ticks_due(1.0, "4x", 1.0, max_catchup=8) == 4


def test_a_paused_clock_never_owes_a_tick() -> None:
    assert ticks_due(10_000.0, "paused", 1.0, max_catchup=8) == 0


def test_a_long_sleep_is_capped_rather_than_simulating_a_week() -> None:
    assert ticks_due(86_400.0, "1x", 1.0, max_catchup=8) == 8


def test_the_catchup_cap_is_configured_not_hardcoded() -> None:
    cfg = load_config()
    assert cfg["simulation"]["max_catchup_ticks_per_wake"] >= 1


def test_commands_are_frozen_values() -> None:
    assert SetSpeed("4x").speed == "4x"
    assert BindFaction(2).faction_id == 2
    assert BindFaction(None).faction_id is None
    for command in (Pause(), Resume(), Shutdown()):
        assert command == type(command)()
