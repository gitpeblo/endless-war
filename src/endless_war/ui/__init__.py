"""GTK interface.

Imports `endless_war.app` and nothing else from this project: never the
simulation, the domain models or the AI. The UI reads immutable snapshots and
submits commands; it cannot reach world state.
"""
