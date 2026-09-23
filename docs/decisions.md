# Architecture Decision Log

Use this file to record decisions that would otherwise be lost between development sessions.

Format:

## YYYY-MM-DD — Decision title

**Decision:**

**Reason:**

**Alternatives considered:**

**Consequences:**

## 2026-09-22 — Desktop UI stack: GTK 3 via PyGObject, with Ayatana AppIndicator for the tray

**Decision:**
The graphical interface is GTK 3 accessed from Python through PyGObject (`gi`), and the Ubuntu MATE tray icon uses the `AyatanaAppIndicator3` GObject-Introspection namespace. This confirms the stack already suggested in `README.md` and `specs/04-roadmap.md` (Phase 6); it is recorded here so it is not re-litigated.

**Reason:**
- MATE is a GTK 3 desktop, so GTK 3 is the native toolkit for the target platform and needs no extra runtime.
- The whole stack is already present on the development machine as distribution packages (see Consequences), so Phase 6 requires no installation step.
- PyGObject exposes both the window toolkit and the tray indicator through one binding, so there is no second GUI dependency.

**Alternatives considered:**
- *GTK 4* — not available on this machine (`Gtk 4.0` namespace is absent; only 3.24.41 is installed) and not the MATE-native version. Would require pulling in a newer toolkit for no benefit to a province-map view.
- *Legacy `AppIndicator3` (Canonical libappindicator)* — the namespace is **not** installed here; Ubuntu 24.04 ships the Ayatana fork instead. Code must require `AyatanaAppIndicator3`, not `AppIndicator3`.
- *Qt/PySide, Tk, or a web UI* — would add a large dependency, and a browser/Electron shell conflicts with the low-attention, tray-resident design pillar in `specs/00-project-brief.md`.

**Consequences:**
- No installation is required for development on this machine. Verified present:
  - `python3-gi` 3.48.2 (PyGObject, `gi` importable from system `python3` 3.12.3)
  - `gir1.2-gtk-3.0` / `libgtk-3-0t64` 3.24.41-4ubuntu1.3 (`Gtk 3.0` namespace imports)
  - `gir1.2-ayatanaappindicator3-0.1` 0.5.93-1build3 (`AyatanaAppIndicator3 0.1` namespace imports)
  - Session is `XDG_CURRENT_DESKTOP=MATE`, `XDG_SESSION_TYPE=x11`.
- On a fresh machine the equivalent is:
  `sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1`
- **PyGObject is a system dist-package, not a wheel.** A plain `python3 -m venv` cannot see it (`ModuleNotFoundError: No module named 'gi'`). Any virtualenv used for UI work must be created with `python3 -m venv --system-site-packages` (verified working). A plain venv is fine for headless simulation and test work.
- `ui/` code must pin namespace versions with `gi.require_version(...)` before importing from `gi.repository`, and must stay import-isolated from the simulation core per `architecture.md`.

## 2026-09-23 — Simulation core balance decisions, and the ten-year checkpoint verdict

**Decision:**
Three things are recorded together, because they were settled by the same
ten-year observation run (`python -m endless_war --years 10 --seed 42`):

1. **Battle losses are driven by each side's *share* of combined power, not by a
   raw power ratio.** `resolve_battles` computes
   `attacker_share = att_power / (att_power + def_power)`, then
   `attacker_rate = base_casualty_rate * 2 * (1 - attacker_share)` and
   `defender_rate = base_casualty_rate * 2 * attacker_share`.
2. **`base_recruitment_rate` is a convergence rate toward a ceiling, not a
   growth rate.** `update_recruitment` adds
   `(population * mobilization_ceiling - manpower) * base_recruitment_rate *
   (1 - exhaustion)` men per tick.
3. **No `[balance]` value was tuned at the checkpoint.** The ten-year history is
   *not* interesting, but the cause is structural rather than a balance
   problem, and tuning config would have hidden it. See Consequences.
4. **The contact rule: moving into a hostile-held province IS the attack.**
   Tasks 6 and 7 shipped contradictory combat models; this resolves them in
   favour of the one `battle.py` and `control.py` already presuppose. The
   blocking branch in `update_movement` was removed, so an army ordered into a
   province holding hostile armies enters it, and `resolve_battles` — which runs
   later in the same tick — resolves the engagement there, with the province
   controller's armies as defenders. **A future session must not re-introduce
   the block.** Covered by `tests/test_movement.py::
   test_move_into_hostile_province_is_the_attack` and the engine-level
   regression `tests/test_engine.py::test_armies_in_contact_produce_combat`.

**Reason:**
- A raw ratio (`att_power / def_power`) is unbounded: a ten-to-one advantage
  gives a rate ten times base, and a defender reduced to near-zero power drives
  the rate toward infinity. Share is confined to `[0, 1]` by construction, so
  every per-tick casualty rate is confined to `[0, 2 * base_casualty_rate]` no
  matter how lopsided the fight. That is the "bounded, explainable, stable over
  long simulations" requirement in `docs/simulation-notes.md`.
- A recruitment rate applied to the existing pool (`manpower * rate`) is
  exponential and snowballs without limit. Applied to the *headroom* below a
  population-derived ceiling it is a first-order lag: it converges on the
  ceiling, slows as it approaches, and shrinks automatically when a faction
  loses the provinces whose population set that ceiling. Ten years of
  observation confirm manpower stays inside one order of magnitude.
- On the config question: the checkpoint run showed zero battles, zero
  casualties and zero exhaustion across all 14,600 ticks. A config sweep over
  `war_declaration_strength_ratio` (1.0), `war_declaration_max_exhaustion`
  (1.0), `peace_stalemate_ticks` (100000), `base_casualty_rate` (0.2),
  `base_supply_decay_per_hop` (0.01) and a combined war-maximising config
  produced **zero battles in every case**. No balance value can reach this
  behaviour, so changing one would only have obscured the defect below.

**Alternatives considered:**
- *Raw power ratio for battle losses* — rejected as unbounded (above).
- *Deterministic winner-takes-all battle resolution* — rejected: it produces
  step-function fronts rather than the attritional give-and-take
  `specs/01-game-design.md` asks for, and it makes casualties uninformative.
- *Exponential recruitment with a hard cap* — rejected: the cap becomes the only
  thing that matters, and every faction sits pinned at it within months.
- *Lowering `war_declaration_strength_ratio` from 1.35 at the checkpoint* — this
  was the anticipated remedy for a boring run, and it does raise war count
  (17 → 47 over ten years at 1.0). It was rejected because wars are not the
  missing ingredient: the wars that do start never produce a single battle.

**Consequences:**
- **The ten-year checkpoint does not pass its "is this interesting?" bar, and
  GTK work must not start.** Seed 42, ten years: 17 wars declared, 144 provinces
  captured, **0 battles, 0 casualties, 0 exhaustion**. Captures are 123 in year
  one, 21 in year two and **0 in years three through ten** — the map is frozen
  at `[18, 18, 22, 3, 35]` provinces for eight straight years while the same two
  factions declare war on each other every four months and sign peace on the
  stalemate timer. All invariants hold throughout; nothing explodes, but nothing
  happens either.
- **Root cause: battles are unreachable in the live tick pipeline.**
  `update_movement` refuses to advance an army into a province occupied by
  hostile armies (`if hostile_armies_in(...): continue  # blocked: the battle
  system resolves this`), but `resolve_battles` only fires for provinces where
  armies of two mutually hostile factions are already *co-located*. Movement is
  the only way an army changes province, so co-location never occurs — measured
  at 0 hostile-co-located province-ticks in 14,600 ticks, against 968 blocked
  advances. A garrisoned border province is therefore an impassable wall, which
  is what freezes the map.
- Consequently `base_casualty_rate`, `attacker_break_organization`,
  `defender_break_organization`, `exhaustion_per_casualty_fraction` and
  `peace_exhaustion_threshold` are all currently dead config, and wars can only
  ever end on `peace_stalemate_ticks`.
- The intended shape of the model is visible elsewhere in the code and
  contradicts the movement block: `resolve_battles` designates the province
  controller as the defender and hostile armies *in that province* as
  attackers, and `apply_control_changes` retreats a broken attacker out to a
  friendly neighbour. Both presuppose that attackers stand inside the defended
  province. Removing the movement block is therefore the leading candidate
  remedy — but it is not sufficient on its own: a scratchpad experiment that
  removed only that block produced 17 battles and ~29,000 casualties in year
  one and then froze again, with the front calcified from year two onward. A
  second contributor, most likely the AI's attack threshold in
  `choose_strategic_actions` (`_defenders_in(...) < army.manpower * 1.2`, which
  turns any adequately garrisoned province into a permanent standoff), needs
  investigating alongside it.
- This is left for a follow-up task deliberately. It is a change to the shape of
  the model in Tasks 6/7/10, not a balance tweak, and the observatory committed
  here is the instrument that will show whether a fix works.

### Fix round 1 addendum (same day) — the contact rule is in, the checkpoint is still unmet

Removing the movement block did exactly what the model predicted, and no more.
Seed 42, ten years, before → after: **0 → 17 battles**, **0 → 29,315 casualties**,
first-year territory [18, 18, 22, 24, 14] → [20, 14, 22, 31, 9]. Combat is now
reachable and the `attacker_broke` retreat path in `control.py` is live code.

**The decade is still frozen, for a second and independent reason.** All 17
battles happen in year 1; years 2–10 produce none. The measured cause is *not*
the AI attack gate — instrumenting all 14,600 ticks shows armies had a hostile
neighbour on 229 army-ticks and chose to attack on **229 of 229**, declining
zero times, so `_defenders_in` counting non-hostile third parties is real but
currently inert, and it was left alone.

The actual blocker is a **recovery deadlock between the AI and movement**:

- `ai/strategic.py` gives a broken army (`organization < 0.30`) a `withdrawal`
  order, setting `destination_id` to a friendly neighbour, *every tick*.
- `movement.py` only recovers organization and morale in the branch guarded by
  `elif army.destination_id is None`.

So an army cannot recover because it is retreating, and it retreats because it
has not recovered. Measured: **76.0% of army-ticks carry a destination** and
**75.9% are in the broken state** — the two figures coincide because they are
the same armies. By the end of year 1, **12 of 15 armies are broken, and the
lowest organizations sit at exactly [0.0, 0.0, 0.04, 0.07, 0.07] in every one of
years 1 through 10** — not a slow decline, a hard stop. Organization has only
one source of increase in the whole simulation, and it is behind that gate.

Two candidate remedies were measured in a scratchpad (neither applied): letting
recovery run regardless of `destination_id`, and having a broken army hold when
its province is already safe. Each extends the fighting to year 2 or 3 (12/17/15
and 21/67 battles respectively, and the second leaves only 1 of 15 armies
broken) but **neither unfreezes the decade**, so a third constraint remains
beyond them. That is a change to the shape of Tasks 6/10 rather than a balance
value, so it is escalated rather than improvised, and **no `[balance]` value was
tuned in this round either**: tuning is only meaningful once the mechanism
sustains combat, and it does not yet.
