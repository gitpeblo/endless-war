# Simulation Notes

> **These are design intentions, written before the systems existed.** For what
> the code actually computes — the real formulas, the config keys that tune them,
> and the known gaps — see `game-logic.md`.

## Combat philosophy
Combat should create plausible strategic movement, not tactical realism.

Prefer formulas that are:

- bounded
- explainable
- testable
- stable under long simulations

Avoid exponential snowballing without counterforces.

## Supply
A simple initial model:

1. Capitals/cities generate supply.
2. Supply propagates through friendly connected provinces.
3. Distance and damaged infrastructure reduce delivered supply.
4. Armies consume local delivered supply.
5. Undersupplied armies lose effectiveness and organization.

## Battle resolution
Possible inputs:

- attacker effective power
- defender effective power
- terrain
- fortification
- supply
- morale
- organization
- randomness within a narrow range

Outputs:

- casualties
- equipment losses
- morale/organization loss
- retreat or continued battle
- province control change

## Anti-snowball systems
Potential mechanisms:

- occupation burden
- longer supply lines
- rising war exhaustion
- reinforcement delay
- infrastructure damage
- resistance
- diplomatic balancing

Use only as needed after observing simulation behavior.
