"""Default entry point: run the headless observation.

The GTK shell is Phase 6; until then `python -m endless_war` observes.
"""

from endless_war.tools.observe import main

if __name__ == "__main__":
    main()
