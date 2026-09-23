# How wars work

## Why a war starts

A faction will declare war when all of these are true:

- it is not already at war
- it is not too war-weary
- the target is a faction it actually **borders**
- it is meaningfully stronger than that target — roughly a third stronger,
  counting armies in the field plus half the reserve pool

Even then it only happens on a chance roll, so strength creates the
*opportunity*, not the certainty. Nobody declares war on a faction across the
map: with no shared border there is no way to reach them.

## How a battle is fought

A battle happens wherever two hostile armies stand in the same province. The
province's controller defends; whoever walked in attacks.

Each side's strength combines its numbers with its condition — equipment, morale,
organisation, training and supply — and the defender gets a terrain bonus.
Mountains are worth roughly 60% extra; plains nothing.

Then the important part: **losses are shared out by how strong each side is
relative to the other.** The stronger side loses proportionally less, the weaker
side proportionally more, and the two rates always add up to the same total. A
battle can be one-sided but it can never be annihilating in a single tick — at
most a few percent of the engaged force dies per six hours.

That bound is why a decade-long war grinds rather than exploding.

Battles continue tick after tick while both sides remain. An army whose
organisation collapses has **broken** — a broken attacker is thrown back out of
the province it was assaulting.

## How ground changes hands

Two ways:

- **Walk into an undefended province.** No battle, no casualties — the vast
  majority of territory changes this way.
- **Beat the defenders until none remain**, then hold the ground.

## How a war ends

Either:

- **Exhaustion** — both sides are worn past breaking point, or
- **Stalemate** — 120 days pass without either side taking a single province.

The stalemate timer is per war, so a breakthrough in one war does not keep an
unrelated one alive.

In practice, most wars in the current build end on the stalemate clock rather
than through exhaustion. That is a known imbalance, recorded in
`docs/decisions.md`: war exhaustion is measured against a manpower pool that
keeps growing, so it never climbs high enough to force a peace.
