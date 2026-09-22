# Development Rules

- Keep simulation code independent of UI code.
- Prefer pure functions for calculations.
- Type annotate public interfaces.
- Use dataclasses initially unless another model library becomes clearly useful.
- Seed all randomness.
- Write a regression test for every simulation bug that affects state.
- Avoid hidden global mutable state.
- Store balancing values in config where practical.
- Favor readable systems over prematurely optimized systems.
- Profile before optimizing.
- The simulation must remain valid when no player faction is selected.
