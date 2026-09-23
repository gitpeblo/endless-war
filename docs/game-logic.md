# Game Logic

What the simulation actually computes, as implemented. `simulation-notes.md`
records the design *intent* from before the code existed; this file describes the
code that exists, with the real formulas and the config keys that tune them.

Every number named here lives in `config/default.toml` unless stated otherwise.

**Looking for the plain-language version?** `guides/` describes the same systems
without formulas: the world, a day in the war, how wars work, and how to read a
run.

## The tick

One tick is **6 simulated hours** (`simulation.tick_hours`); four ticks make a
day. `SimulationEngine.tick()` advances the clock and then runs the systems in a
fixed order that `docs/architecture.md` pins down. Order matters: supply is
computed before the AI decides, the AI decides before armies move, armies move
before battles resolve, and control changes before diplomacy considers peace.

The only randomness in the whole simulation is worldgen and a ±10% roll on each
side of a battle, both drawn from one RNG seeded from `WorldState.seed`. Same
seed plus the same commands reproduces the same history exactly.

## 1. Economy — `systems/economy.py`

```
income = Σ over controlled provinces of  industry × infrastructure × income_per_industry
upkeep = Σ over own armies of            manpower × upkeep_per_manpower
treasury = max(0, treasury + income − upkeep)
```

Income comes from provinces you **control**, not ones you own, so occupation
transfers revenue immediately. Treasury is floored at zero.

*Known gap:* nothing currently spends the treasury, so it grows without a sink.
Recorded in `decisions.md`.

## 2. Recruitment — `systems/economy.py`

```
cap      = controlled population × mobilization_ceiling      (8%)
headroom = max(0, cap − manpower)
recruits = headroom × base_recruitment_rate × (1 − exhaustion)
```

A first-order lag: each tick closes a fixed fraction of the remaining gap, so the
pool converges on the ceiling instead of growing without bound, and an exhausted
nation refills more slowly.

*Known gap:* manpower accumulates in the national pool and nothing moves it into
armies, so armies never reinforce. This also inflates the exhaustion denominator
— see below.

## 3. Supply — `systems/supply.py`

Every province is reset to `min_supply` (0.05), then for each faction:

- **Sources** are provinces it controls that are capitals or have
  `industry >= 1.5` (`INDUSTRIAL_SOURCE_THRESHOLD`, in code).
- Supply spreads by breadth-first search **through that faction's own territory
  only**. Each hop costs `base_supply_decay_per_hop / max(0.3, infrastructure)`,
  so poor roads cost more.
- A province's supply is `1 − accumulated cost`, floored at `min_supply`.

Consequences worth knowing: cutting a province off from its capital starves it,
and **a faction that loses its capital and holds no industrial province has no
source at all** — all its territory sits at 0.05 permanently, and its armies can
never recover. That is a deliberate rule, not a bug, and it is why a rump state
stops being able to fight.

## 4. AI decisions — `ai/strategic.py`

One decision per army per tick, from **local information only**. There is no
global planner; fronts are what many local decisions look like from a distance.

In order:

1. **Broken?** (`organization < broken_organization` or `morale < broken_morale`)
   — withdraw to the friendly neighbour with the best supply, *unless already
   standing somewhere safe*, in which case hold still and recover.
2. **Enemy adjacent?** Pick the hostile neighbour with the fewest defenders.
   Attack it only if those defenders total less than
   `your manpower × attack_strength_ratio` (1.2). Otherwise stand defensive.
3. **Otherwise** reinforce the first friendly neighbour that borders an enemy.

*Known gap:* the defender count is raw headcount, so three shattered divisions
still read as a large garrison.

## 5. Movement — `systems/movement.py`

An army advances at most one province per tick, toward `destination_id`.

- It draws the supply of the province it stands in.
- Below `low_supply_threshold` (0.35) it loses organization and morale; otherwise,
  if it did not move this tick, it recovers them.
- **Moving into a province held by a hostile faction IS the attack** — the army
  enters and the battle system resolves the engagement later in the same tick.
- Advancing costs 0.03 organization. An army below `min_advance_organization`
  (0.15) cannot advance at all.

## 6. Battle — `systems/battle.py`

A battle happens in any province holding armies of two mutually hostile factions.
The province's controller defends; hostile armies present attack.

```
power  = manpower × equipment × morale × organization × training × supply × terrain
share  = attacker_power / (attacker_power + defender_power)        → 0..1
attacker_loss_rate = 2 × base_casualty_rate × (1 − share)
defender_loss_rate = 2 × base_casualty_rate × share
```

The quality factors are normalized into bands rather than multiplied raw (for
example morale contributes `0.35 + 0.65 × morale`), so no single zeroed stat
annihilates a force. Terrain multiplies the **defender** only:
`terrain_defence` gives plains 1.00, forest 1.20, hills 1.35, urban 1.45,
mountain 1.60. Each side's power is then multiplied by a `rng.uniform(0.9, 1.1)`
roll.

The two loss rates always sum to exactly `2 × base_casualty_rate`, so however
lopsided the fight, per-tick attrition is bounded at 4% of the engaged force.
That bound is the main thing keeping long runs stable.

An attacker whose armies are all below `attacker_break_organization` (0.25) has
broken; the same for defenders at `defender_break_organization` (0.20).

*Known gap:* `defender_broke` is computed and nothing reads it, so a beaten
defender does not yield ground. See `decisions.md` — it is paired with capture
churn and must be fixed together with the defender-scoring change.

## 7. Occupation and control — `systems/control.py`

- A hostile province with no defenders present changes controller.
- A broken attacker is pushed back out to a friendly neighbour.
- Armies reduced to zero manpower are removed.

Ownership never changes — only control. That distinction is why income, supply
and recruitment all read `controller_faction_id`, and reading `owner_faction_id`
by mistake is a recurring bug class here.

## 8. Exhaustion — `systems/diplomacy.py`

Exhaustion grows from **new** casualties since the last tick, as a fraction of
the faction's force, scaled by `exhaustion_per_casualty_fraction`, and decays by
`exhaustion_decay_per_tick` in peace. It is clamped to [0, 1].

It deliberately tracks the war being fought rather than lifetime losses: a
veteran nation does not start its next war already exhausted.

*Known gap:* because the pool grows and armies do not, the denominator inflates
over a decade and exhaustion barely moves — `peace_exhaustion_threshold` is
currently unreachable, so wars end on the stalemate timer instead.

## 9. Diplomacy — `systems/diplomacy.py`

**Strength** is `own army manpower + national pool × 0.5`.

**Declaring war** requires all of: not already at war, exhaustion below
`war_declaration_max_exhaustion` (0.45), a target drawn from factions you
actually **border**, being at least `war_declaration_strength_ratio` (1.35) times
stronger, and a per-tick random chance.

**Peace** comes when either every belligerent is at or above
`peace_exhaustion_threshold` (0.75), or no province has changed hands in that
war for `peace_stalemate_ticks` (480 ticks = 120 days). The timer is per war, so
a capture in one war does not hold open another.

## 10. Events — `systems/events.py`

Records war declarations and peace (critical), province captures (major), and
battles whose combined single-tick losses exceed `significant_battle_losses`.
The log is capped at 2000 entries, oldest evicted first.

## Invariants — `simulation/invariants.py`

After any tick the world must satisfy: province count unchanged, every province
controlled by a known faction, all unit-interval fields (morale, organization,
supply, training, equipment, stability, war support, exhaustion) within [0, 1],
no negative manpower or treasury, every value finite, and no faction at war with
itself. `check_invariants` returns the violations; the observatory aborts on any.

## Where to look next

- `docs/decisions.md` — every balance and mechanism decision, dated, with the
  measurements behind it. The known gaps above are recorded there in full.
- `docs/architecture.md` — layering and the fixed pipeline order.
- `docs/simulation-notes.md` — the original design intent, useful for judging
  whether a change moves toward or away from it.
