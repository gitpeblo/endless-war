# The world

A game is one map, generated from a seed. The same seed always gives the same
world.

## Provinces

The map is a grid of **96 provinces**, each with a population, some industry,
infrastructure, and a terrain type — plains, forest, hills, mountain or urban.
Terrain matters in one specific way: it helps whoever is *defending* there.
Attacking into mountains is much harder than attacking across plains.

Every province has two separate owners:

- its **owner** — who it belongs to historically
- its **controller** — whose army holds it right now

Conquest changes the controller, never the owner. That is why a captured
province still produces income for whoever holds it, and why a faction pushed
off the map entirely still has ownership records and can, in principle, take
its land back.

## Factions

**Five factions** start with a capital each and a contiguous block of territory
grown outward from it. They have a treasury, a manpower pool, stability, war
support, and war exhaustion. None of them is the player — the world runs whether
anyone is watching or not.

## Supply

This is the most important thing on the map, and the least visible.

Supply comes from **capitals and industrial provinces**. It spreads outward
through territory that faction controls, weakening with every province it
crosses — faster where infrastructure is poor. An army sitting in
well-supplied territory recovers its strength. An army in a starved province
degrades instead.

Two consequences follow, and they drive most of what you will see:

- **Cut a province off from its capital and it starves**, even if nobody has
  attacked it. A salient deep in enemy land is weak for this reason alone.
- **A faction that loses its capital and has no industrial province left has no
  supply at all.** Its whole territory drops to the minimum and its armies can
  never recover. This is usually the moment a faction stops being able to fight
  back, and it is deliberate.
