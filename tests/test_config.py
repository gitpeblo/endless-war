from endless_war.config import load_config


def test_load_config_reads_defaults() -> None:
    cfg = load_config()
    assert cfg["simulation"]["tick_hours"] == 6
    assert cfg["world"]["default_provinces"] == 96
    assert cfg["world"]["grid_cols"] == 12


def test_load_config_grid_matches_province_count() -> None:
    cfg = load_config()
    cols = cfg["world"]["grid_cols"]
    assert cfg["world"]["default_provinces"] % cols == 0
