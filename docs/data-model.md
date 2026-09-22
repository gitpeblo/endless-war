# Initial Data Model

## World
- id
- seed
- current_datetime
- factions
- provinces
- armies
- wars
- events

## Province
- id
- name
- owner_faction_id
- controller_faction_id
- neighbors[]
- terrain
- population
- industry
- infrastructure
- supply_value
- is_capital

## Faction
- id
- name
- color_key
- capital_province_id
- treasury
- manpower
- stability
- war_support
- exhaustion
- doctrine
- policies
- stockpiles

## Army
- id
- faction_id
- province_id
- destination_id
- manpower
- equipment
- morale
- organization
- training
- supply
- stance

## War
- id
- attackers[]
- defenders[]
- started_at
- status
- war_score_summary

## Event
- id
- simulated_at
- category
- severity
- title
- body
- related_entity_ids
