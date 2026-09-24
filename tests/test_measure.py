from endless_war.measure import measure


def test_measure_reports_every_gate_figure_for_a_short_run() -> None:
    row = measure(seed=42, years=1)
    for key in ("battles", "captures", "captures_per_battle", "map_changes", "largest_share",
                "longest_island_days", "events", "eliminated", "wars_started", "wars_ended",
                "violations", "seconds"):
        assert key in row, key
    assert 0 < row["largest_share"] <= 1


def test_an_enclave_among_factions_at_peace_is_not_an_island() -> None:
    from endless_war.config import load_config
    from endless_war.measure import _islands
    from endless_war.simulation.worldgen import generate_world

    w = generate_world(seed=42, config=load_config())
    pid = 0
    for n in w.provinces[pid].neighbors:
        w.provinces[n].controller_faction_id = 3
    w.provinces[pid].controller_faction_id = 0
    assert pid not in _islands(w), "at peace: not a stuck front"
    w.factions[0].at_war_with = {3}
    w.factions[3].at_war_with = {0}
    assert pid in _islands(w)
