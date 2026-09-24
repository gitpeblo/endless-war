# Game Design Specification

## Player role
The player acts as a high-level strategic authority. They may control one faction, observe all factions, or later switch perspective depending on game mode.

The player does **not** issue orders to individual squads or manually resolve battles.

## Core loop

Peace → rearmament → tension → war → expansion → overstretch → exhaustion → peace/collapse → recovery → renewed tension.

Individual wars must end. The world does not.

## World structure

- Procedurally generated strategic map.
- Provinces connected as a graph.
- Provinces may contain cities, resources, infrastructure, industry, population, and terrain.
- Borders are determined by province ownership.
- Supply flows through controlled connected territory and transport links.

## Factions
Each faction has:

- population
- treasury
- industrial capacity
- manpower pool
- military stockpiles
- government stability
- war support
- exhaustion
- doctrine
- diplomatic relationships
- strategic goals
- controlled provinces
- armed forces

Factions may later split, collapse, merge, revolt, or re-form.

## Military model

Initial unit classes:

- Infantry
- Armor
- Artillery
- Air power
- Logistics/support

Army effectiveness should derive from multiple factors rather than raw manpower alone:

`effective_power = manpower × equipment × training × morale × supply × doctrine × commander × terrain`

Use normalized multipliers and bounded formulas rather than multiplying raw values directly in implementation.

## Fronts
A front is a set of adjacent contested provinces between hostile factions.

Front states should be summarized as:

- advancing
- stable
- pressured
- retreating
- collapsing

The player may assign a stance:

- delay
- defensive
- balanced
- aggressive
- breakthrough
- withdrawal

AI commanders translate stance into local decisions.

## Logistics
Logistics should be central.

Armies consume:

- food/supplies
- ammunition
- fuel where applicable
- replacement manpower
- replacement equipment

Poor supply reduces combat effectiveness and movement speed, increases attrition, and can force retreat.

## Economy
Initial economic resources:

- civilian output
- military production
- food/supply output
- infrastructure capacity
- treasury

The player or AI allocates national effort between:

- military production
- civilian economy
- infrastructure
- research/doctrine
- recruitment/training

## War exhaustion and instability
Long wars must have consequences.

Inputs may include:

- casualties
- territory lost
- taxation
- shortages
- destroyed infrastructure
- mobilization duration
- defeats
- occupation

High exhaustion can reduce productivity, morale, stability, recruitment, and political cohesion.

Possible later outcomes:

- peace pressure
- government change
- mutiny
- separatism
- civil war
- state collapse

## Diplomacy
Minimum viable diplomacy:

- neutral
- hostile
- at war
- ceasefire
- allied

Later additions:

- guarantees
- coalitions
- trade
- sanctions
- negotiated peace
- territorial demands

## Commanders
Commanders are persistent named entities with traits and records.

Possible statistics:

- aggression
- caution
- logistics
- organization
- initiative
- loyalty
- experience

They should accumulate a history of battles and assignments.

## Emergent history
The game should log important events such as:

- war declarations
- peace agreements
- major battles
- capital captures
- encirclements
- coups
- revolts
- faction creation/collapse
- famous commanders appointed/killed/retired
- prolonged sieges
- economic crises

The history log is a major reward loop.

## Background-play requirements

- The simulation must progress without user input.
- Noncritical events resolve automatically according to policy.
- Critical events may notify the player but should not freeze the world indefinitely.
- The main window can remain closed while the simulation continues.
- Tray controls expose only high-value state and actions.

## Offline catch-up
Store a last-simulated timestamp. On startup, calculate elapsed real time and process a bounded catch-up simulation.

Catch-up may use coarser ticks than live play to avoid long startup times.
