from endless_war.measure import measure


def test_measure_reports_every_gate_figure_for_a_short_run() -> None:
    row = measure(seed=42, years=1)
    for key in ("battles", "captures", "captures_per_battle", "map_changes", "largest_share",
                "longest_island_days", "events", "eliminated", "wars_started", "wars_ended",
                "violations", "seconds"):
        assert key in row, key
    assert 0 < row["largest_share"] <= 1
