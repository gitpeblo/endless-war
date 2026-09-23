import random

from endless_war.config import load_config
from endless_war.simulation.systems.economy import update_economy, update_recruitment
from endless_war.simulation.worldgen import generate_world


def test_treasury_grows_in_peacetime() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    before = {fid: f.treasury for fid, f in w.factions.items()}
    update_economy(w, random.Random(1), cfg)
    assert all(w.factions[fid].treasury > before[fid] for fid in before)


def test_treasury_never_goes_negative() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for fac in w.factions.values():
        fac.treasury = 0.0
    for _ in range(50):
        update_economy(w, random.Random(1), cfg)
    assert all(f.treasury >= 0.0 for f in w.factions.values())


def test_recruitment_converges_to_mobilization_ceiling() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    for _ in range(4000):
        update_recruitment(w, random.Random(1), cfg)
    for fid, fac in w.factions.items():
        # `update_recruitment` derives the ceiling from CONTROLLED population,
        # so the fixture must too. They coincide at generation and diverge the
        # moment anything is occupied -- this repo's recurring fixture defect.
        population = sum(
            p.population for p in w.provinces.values() if p.controller_faction_id == fid
        )
        cap = population * cfg["balance"]["mobilization_ceiling"]
        assert fac.manpower <= cap + 1, "manpower must never exceed the mobilization ceiling"
        assert fac.manpower > cap * 0.5, "manpower should approach the ceiling over time"


def test_recruitment_slows_as_exhaustion_rises() -> None:
    cfg = load_config()
    w = generate_world(seed=42, config=cfg)
    fac = w.factions[0]
    fac.manpower = 0
    fac.exhaustion = 0.0
    update_recruitment(w, random.Random(1), cfg)
    calm = fac.manpower

    fac.manpower = 0
    fac.exhaustion = 0.9
    update_recruitment(w, random.Random(1), cfg)
    assert fac.manpower < calm
