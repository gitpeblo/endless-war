# Offline Continuation Checklist

When continuing development without ChatGPT/Work:

1. Read `README.md`.
2. Read the numbered specifications (`00-`…`04-`) under `docs/superpowers/specs/`.
3. Start from `src/endless_war/domain/models.py` and `simulation/engine.py`.
4. Implement one system at a time with tests.
5. Keep the simulator runnable without GTK.
6. Build a CLI/debug runner before the graphical UI.
7. Record major architecture decisions in `docs/decisions.md`.
8. Do not expand scope before the autonomous war loop is demonstrably interesting.
