from collections import deque

from endless_war.config import load_config
from endless_war.simulation.worldgen import generate_world


def test_creates_configured_faction_count() -> None:
    w = generate_world(seed=42, config=load_config())
    assert len(w.factions) == 5


def test_every_province_is_owned_and_controlled_by_owner() -> None:
    w = generate_world(seed=42, config=load_config())
    for prov in w.provinces.values():
        assert prov.owner_faction_id in w.factions
        assert prov.controller_faction_id == prov.owner_faction_id


def test_each_faction_has_exactly_one_capital_it_owns() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        caps = [p for p in w.provinces.values() if p.is_capital and p.owner_faction_id == fid]
        assert len(caps) == 1
        assert caps[0].id == fac.capital_province_id


def test_territory_is_contiguous_per_faction() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        owned = {p.id for p in w.provinces.values() if p.owner_faction_id == fid}
        seen = {fac.capital_province_id}
        queue = deque(seen)
        while queue:
            for nid in w.provinces[queue.popleft()].neighbors:
                if nid in owned and nid not in seen:
                    seen.add(nid)
                    queue.append(nid)
        assert seen == owned, f"faction {fid} territory is not contiguous"


def test_every_faction_starts_with_provinces_and_manpower() -> None:
    w = generate_world(seed=42, config=load_config())
    for fid, fac in w.factions.items():
        owned = [p for p in w.provinces.values() if p.owner_faction_id == fid]
        assert len(owned) >= 5
        assert fac.manpower > 0
        assert fac.at_war_with == set()


def test_world_generation_is_reproducible() -> None:
    a = generate_world(seed=42, config=load_config())
    b = generate_world(seed=42, config=load_config())
    assert [p.owner_faction_id for p in a.provinces.values()] == [
        p.owner_faction_id for p in b.provinces.values()
    ]
