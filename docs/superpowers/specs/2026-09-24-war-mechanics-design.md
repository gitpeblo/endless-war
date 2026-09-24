# War mechanics: fronts that move, factions that die, peace that settles land

Date: 2026-09-24
Status: approved in conversation, ready for an implementation plan
Phase: simulation, the "linked pair" parked in `docs/decisions.md` (2026-09-23), plus the approved occupation-at-peace rule

## Why this exists

The user reported that "isolated tanks on isolated cells never get conquered (a faction is never destroyed)". A 10-year diagnostic at seed 42 found two causes:

1. **Idle armies all go to one place.** `choose_strategic_actions` sends every army that is not next to an enemy to `sorted(threatened)[0]`, the lowest-numbered threatened friendly province, and never moves armies more than one step. After ten years faction 3's three armies sat only in provinces 1 and 7. Enemy provinces P54 and P87 stayed empty, at war with faction 3 and adjacent to it, and were never taken. Of 1,467 samples of an enemy-surrounded island province, 1,466 had no hostile army present at all.
2. **A faction without supply is stuck forever.** This was already documented (`docs/decisions.md`, 2026-09-23, fix round 2): its armies' organisation decays to 0 and never recovers, and `_defenders_in` counts raw headcount. So faction 0's last province, with 158,000 men at organisation 0 and morale 0, looked impregnable. Nobody attacked it, and the faction could neither fight nor die.

The decision log also records two fixes that were each reverted because they failed alone and "may only work as a pair":
- quality-based defender scoring caused capture churn (4,416 captures from 163 battles);
- defender retreat caused stasis (map changes fell from 9 of 9 to 2 of 9 at seed 99).

This spec applies them together, fixes the routing and the churn they depend on, lets factions die, and adds the occupation-at-peace rule the user approved earlier.

## Decisions made in conversation

| Question | Answer |
|---|---|
| Can a faction be destroyed? | Yes, permanently, when it controls no province. |
| What if one faction takes everything? | Let it happen, but measure it: the 10-year runs must show that no faction exceeds 70 % of the map. Rebellions and new factions are a later sub-project. |
| When does occupied land change owner? | At peace. For every province controlled by a belligerent of the ending war whose owner it is no longer at war with, the owner becomes the controller. |

## Scope

In:

1. Front-aware routing of idle armies (AI).
2. Attack decisions by combat strength (AI).
3. Beaten defenders retreat, or surrender when trapped (control).
4. Occupation delay against capture churn (control).
5. Faction elimination (diplomacy and events).
6. Occupation settled at peace (diplomacy and events).
7. A measurement tool, and the gate below.

Out: rebellion, revived or new factions, alliances, negotiated peace, and any UI change beyond what elimination requires (the legend skips eliminated factions).

## 1. Routing idle armies: `ai/strategic.py`

- **Front provinces** of faction F: provinces F controls that are adjacent to a province controlled by a faction F is at war with.
- **Front pressure** of a front province p: the effective power of the hostile armies in p's hostile neighbours, minus F's own effective power already in p. It is computed once per tick per faction, in sorted order.
- An army that is **not broken and has no hostile neighbour** targets the front province with the highest pressure. Ties go to the shortest distance over F-controlled provinces, then the lowest id. The army then steps one province along a shortest path to that target, where the path is a BFS over F-controlled provinces with ties broken by lowest id.
- If F is at war but has no path to any front province (no route through its own land), the army stays put.
- If F is at peace, there are no front provinces and the army stays put.
- Distances are recomputed each tick; fronts move. The cost is one BFS per faction per tick over at most 96 provinces.

## 2. Attacks by combat strength: `ai/strategic.py`

- `_defenders_in(world, province, faction)` becomes `_defence_of(world, province, attacker_faction)`. It is the sum of `battle.effective_power(a, world, True, terrain_defence)` over armies in the province **hostile to the attacker** (at war with it), not every other faction.
- An army attacks its weakest hostile neighbour when `_defence_of(target) < effective_power(army, attacking) × attack_strength_ratio`.
- An empty hostile province (defence 0) is always attackable.

## 3. Defender retreat and surrender: `simulation/systems/control.py`

- `record["defender_broke"]` is now read: a broken defender retreats to a friendly neighbouring province, using the existing `_retreat`.
- **Surrender:** a broken army (attacker or defender) that has no friendly neighbour to retreat to, while hostile armies share its province, surrenders. It is removed. Its manpower is counted as casualties of its faction, and the event log records "X's army in P surrendered".
- `defender_break_organization` stops being dead config.

## 4. Occupation takes time: `simulation/systems/control.py`

- New config `[balance] occupation_ticks = 4` (one simulated day).
- New state `Province.occupation: tuple[int, int] | None`, meaning `(faction_id, ticks_held)`, default None.
- When exactly one faction at war with the controller has armies in a province and no hostile army to that faction is present, `ticks_held` increments. The province changes controller when it reaches `occupation_ticks`.
- If that faction's armies leave, or a hostile army arrives, the counter resets to None.
- A capture through battle works the same way: once the defenders are gone (retreated, dead or surrendered), the counter starts.
- Captures, `note_captures` and the capture events fire only when control actually changes.
- The effect: an army that walks in and out captures nothing, so two armies trading an empty province every other tick stop generating captures.

## 5. Elimination: `simulation/systems/diplomacy.py` and `events.py`

- New `Faction.eliminated: bool = False`.
- At the diplomacy step: a faction that is not eliminated and controls no province becomes eliminated.
  - Its armies are removed; their manpower is counted as casualties.
  - It leaves every war. A war left with no attacker or no defender ends (status "ended"), and its peace settlement (section 6) runs.
  - The event log records "X has been destroyed" at critical severity.
- Eliminated factions never declare war, are never targeted, never recruit and never appear as neighbours.
- They stay in `world.factions`, so the History chart keeps their lines.
- `test_long_run`'s "every faction owns something" assertion is replaced: every province still has a live controller, and a faction with no provinces is eliminated.
- The legend skips eliminated factions. The status panel for a bound eliminated faction shows "destroyed".

## 6. Occupation at peace: `simulation/systems/diplomacy.py`

When a war ends, whether by exhaustion, stalemate or elimination:
- for every province whose controller was a belligerent of that war,
- if the owner is not the controller, and the owner is not at war with the controller after the war's flags are cleared,
- the owner becomes the controller.
- Provinces are visited in sorted order.
- The peace event lists the provinces that changed owner, for example "Peace: Valdran Hegemony annexes 3 provinces from Free Cities League". Ownership never changes at any other time, and `control.py`'s docstring says so.

## 7. Measurement and gate

- A new module `src/endless_war/measure.py`, run as `python3 -m endless_war.measure --seeds 42 7 99`, runs ten years per seed and prints one table.
- It reports per seed:
  - battles and the years with battles;
  - captures;
  - the captures-per-battle ratio;
  - casualties;
  - year-over-year map changes (out of 9);
  - the largest faction's share of the map;
  - eliminated factions and the year each was eliminated;
  - the longest-lived enemy-surrounded island province, in days;
  - total events and whether they hit the cap;
  - wars started and wars ended.
- The baseline is measured on `main` before the change and recorded in the plan.

**Gate** (every seed must pass; failures are reported, never tuned away):

- no enemy-surrounded island province lasts more than 180 days;
- no more than 3 captures per battle;
- the map changes in at least 6 of the 9 year-over-year transitions;
- total events stay under the 2000-entry cap;
- no faction exceeds 70 % of provinces within ten years;
- invariants stay clean, and the 10-year CLI run finishes in under 6 s.

## Testing

Unit tests, one or more per mechanism:
- **Routing:** an idle army at the rear steps toward the highest-pressure front; two idle armies with two equal fronts go to different ones; at peace nobody moves.
- **Attack decision:** a broken stack no longer deters an attacker; an empty hostile province is attacked.
- **Retreat and surrender:** a broken defender with a friendly neighbour leaves; one without surrenders, its men counted as casualties.
- **Occupation delay:** a single tick in a province does not capture it; `occupation_ticks` uninterrupted ticks do; an interrupted hold resets.
- **Elimination:** a faction losing its last province is eliminated, its armies and wars removed, and an event logged; an eliminated faction never declares war.
- **Peace settlement:** land transfers to the occupier; the third-party case transfers; land still disputed with the owner does not transfer.
- **Determinism:** the same seed gives the same decade.

Every existing test must still pass, or be changed with a stated reason. Two are expected to change: `test_long_run`'s ownership assertion, and `test_control.py`'s "occupation must not transfer ownership" test, which still holds during a war.

## Documentation

- `docs/game-logic.md`: the routing, attack, retreat and surrender, occupation, elimination and peace sections.
- `docs/decisions.md`: a dated entry with the before and after gate table, closing the "linked pair" note.
- `README.md`: nothing (behaviour only).
