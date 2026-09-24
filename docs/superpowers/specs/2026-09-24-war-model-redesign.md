# War model redesign: land that defends itself, wars that end, more wars

Date: 2026-09-24
Status: decided by the implementer on the user's instruction ("redesign and implement, do not ask me")
Builds on: `2026-09-24-war-mechanics-design.md` (routing, strength-based attacks, retreat and surrender, occupation delay, elimination, peace settlement)

## Why

Three fixes on top of the war-mechanics branch each exposed a new failure. The root cause is structural: **land has no defence of its own**.
- Any province without an army fell to any army standing in it for a day.
- Armies raided empty land instead of fighting: seed 42 recorded 13,927 captures from 6 battles.
- Territory flipped back and forth in deterministic circles.
- A war ends only after 120 days without a capture, so the raiding kept wars alive forever.

The user also saw only about two factions acting at a time: on `main` a mean of 1.9 of 5 factions were at war, because a faction at war cannot declare another war.

## 1. Garrisons: every province defends itself

- `Province.garrison: float`, in the same units as `battle.effective_power`.
- **Cap:** `population × garrison_per_capita × terrain_defence[terrain]`, multiplied by `occupied_garrison_factor` while the province is held by someone other than its owner.
- A province starts at its cap. It regrows toward the cap by `garrison_regen_per_tick × cap` each tick, but only while no army hostile to its controller stands in it.
- **In battle:** a province containing an army hostile to its controller is a battle even when the controller has no army there. The garrison fights as a defender, alongside any defending armies.
  - Its power is its current value.
  - It takes `defender_rate × garrison_loss_multiplier` of itself as losses. Those losses count as its controller's casualties.
- **Occupation:** the occupation counter only advances once the garrison is below 1 % of its cap, so a province must be *fought* for. The one-day hold then still applies.
- **AI:** `_defence_of` includes the garrison, so an army attacks only land it can beat, and undefended-looking land is no longer free.

## 2. Wars end

- **War weariness:** while at war, a faction's exhaustion also grows by `war_weariness_per_tick` each tick, on top of the casualty term. This makes `peace_exhaustion_threshold` reachable; the decision log noted it was unreachable. Exhaustion still decays in peace.
- **Capitulation:** a side capitulates when all of the following hold for every faction on it:
  - it has lost its capital (another faction controls it);
  - it holds less than `capitulation_land_fraction` of the provinces it held when the war began, as stored on the war.

  The war ends, and the settlement runs.
- The stalemate rule (480 ticks without a capture) and elimination stay.

## 3. More wars at once

- A faction may declare a war while already at war, as long as it is in fewer than `max_concurrent_wars` wars and its exhaustion is below `war_declaration_max_exhaustion`.
- A target may already be at war: it is an opportunity.
- The strength-ratio rule and the per-tick chance are unchanged.

## Parameters (`[balance]`, before the `terrain_defence` sub-table)

| key | value | meaning |
|---|---|---|
| `garrison_per_capita` | 0.02 | cap per inhabitant, before terrain |
| `garrison_regen_per_tick` | 0.01 | share of the cap regained per quiet tick |
| `occupied_garrison_factor` | 0.3 | an occupier's garrison cap, relative to the owner's |
| `garrison_loss_multiplier` | 1.5 | garrisons break faster than field armies |
| `war_weariness_per_tick` | 0.0004 | exhaustion added per tick at war (0.75 in about 1.3 years) |
| `capitulation_land_fraction` | 0.5 | below this share of pre-war land, with the capital lost, a side gives up |
| `max_concurrent_wars` | 2 | wars one faction may be in at once |

These are first values for new mechanisms, chosen from the magnitudes involved: a 30,000-man army has about 15,000 effective power, and a garrison has about 4,000 to 30,000. Each value is recorded with the measured result. They may be recalibrated once against the gate, with the numbers recorded, but the existing `[balance]` values are not touched.

## Gate

The same gate as the war-mechanics spec, on seeds 42, 7 and 99. `longest_enclave_days` is reported alongside it, as the figure that matches the user's report.

## Out of scope

Alliances, negotiated peace terms, rebellion, and UI for garrisons.
