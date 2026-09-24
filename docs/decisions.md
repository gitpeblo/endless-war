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
The graphical interface is GTK 3 accessed from Python through PyGObject (`gi`), and the Ubuntu MATE tray icon uses the `AyatanaAppIndicator3` GObject-Introspection namespace. This confirms the stack already suggested in `README.md` and `docs/superpowers/specs/04-roadmap.md` (Phase 6); it is recorded here so it is not re-litigated.

**Reason:**
- MATE is a GTK 3 desktop, so GTK 3 is the native toolkit for the target platform and needs no extra runtime.
- The whole stack is already present on the development machine as distribution packages (see Consequences), so Phase 6 requires no installation step.
- PyGObject exposes both the window toolkit and the tray indicator through one binding, so there is no second GUI dependency.

**Alternatives considered:**
- *GTK 4* — not available on this machine (`Gtk 4.0` namespace is absent; only 3.24.41 is installed) and not the MATE-native version. Would require pulling in a newer toolkit for no benefit to a province-map view.
- *Legacy `AppIndicator3` (Canonical libappindicator)* — the namespace is **not** installed here; Ubuntu 24.04 ships the Ayatana fork instead. Code must require `AyatanaAppIndicator3`, not `AppIndicator3`.
- *Qt/PySide, Tk, or a web UI* — would add a large dependency, and a browser/Electron shell conflicts with the low-attention, tray-resident design pillar in `docs/superpowers/specs/00-project-brief.md`.

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
5. **The recovery rule: organization recovery is gated on whether the army
   actually MARCHED this tick, not on whether it holds an order.** An army that
   is under orders it cannot execute, or that holds position, rests; an army
   that advances does not, because it already pays the `-0.03` march cost. And
   **the AI no longer orders a broken army to withdraw when it is already
   safe** -- nothing hostile adjacent, nothing hostile standing where it is.
   Covered by `tests/test_movement.py::
   test_army_that_advances_does_not_recover_that_tick`,
   `tests/test_movement.py::test_army_too_disorganized_to_move_recovers` and
   `tests/test_engine.py::test_broken_army_in_safe_territory_recovers`.
6. **Defender scoring by combat quality was ruled, implemented, measured and
   REVERTED.** `_defenders_in` still scores a garrison by raw headcount, so
   three zero-organization divisions read as 158,365 defenders. The fix (score
   with `battle.effective_power`, and count only armies hostile to the mover)
   was written with two passing regression tests, then measured over ten years
   on three seeds and reverted because it did not clear its evidence gate. See
   the fix round 3 addendum for the numbers. **A future session should expect
   this to be re-applied together with a fix for capture churn, not alone.**

**Refusals — do not re-litigate these without new evidence:**

- **No fallback supply source.** A faction that holds neither its capital nor
  an industrial province supplies nothing, so all its territory sits at
  `min_supply` and its armies can never reach movement's recovery branch. That
  is an absorbing state, and it is the direct cause of the wind-down after year
  5. It is nonetheless *deliberate* (Task 5, `supply.py`): a rump government
  that has lost its capital and every industrial centre being unable to project
  force is an explainable consequence, not a bug. Ruled: the consequence stays.
- **No manpower demobilisation or treasury sink in this branch.**
  `docs/superpowers/specs/03-mvp.md` defers that depth and the checkpoint is met without it.
  **Consequence, stated plainly so nobody tunes it blind:
  `peace_exhaustion_threshold` (0.75) is currently DEAD CONFIG.** Measured peak
  exhaustion for any faction across the whole decade is **0.0434** -- about 6% of
  the threshold -- and every war ends on `peace_stalemate_ticks` instead. The
  cause is not the multiplier: exhaustion accrues as
  `new_casualties / (that faction's manpower + that faction's army strength)`,
  and that **per-faction** denominator grows several-fold over the decade because
  recruitment fills the national pool while nothing moves men from the pool into
  armies. Measured per faction, start -> end: f0 446,963 -> 759,171;
  f1 356,004 -> 1,583,066; f2 350,055 -> 1,312,501; f3 429,841 -> 1,946,696;
  f4 211,862 -> 1,315,209. (Across the world the pool alone runs 1.79M -> 6.92M
  and the army share of manpower falls 0.48 -> 0.07, but that world total is not
  what the formula divides by.) Reaching the threshold would need roughly a 25x
  bump to `exhaustion_per_casualty_fraction`, which would be tuning around the
  missing reinforcement mechanic. **Fix demobilisation/reinforcement first; do
  not raise the multiplier.**

  **The same phantom pool distorts Task 9's war declarations, which is a
  second and more visible consequence than the exhaustion denominator.**
  `diplomacy.py` scores strength as army manpower + pool x 0.5, so a faction
  that has lost its territory still reads as strong: faction 3's pool freezes at
  **1,855,937** and it keeps declaring wars on that basis. War 12 is a
  27-province faction declaring on a 33-province one purely on pool strength,
  and wars 18, 22, 23 and 25 all target a **one-province** faction. `_strength`
  is deliberately NOT being changed here -- that is next-phase work -- but a
  future session must know that the pool decides *which wars happen*, not just
  how slowly exhaustion accrues.

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
  `docs/superpowers/specs/01-game-design.md` asks for, and it makes casualties uninformative.
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

### Fix round 2 addendum (same day) — the checkpoint's stated criteria are now met

Applying the recovery rule (decision 5) transformed the decade. Seed 42, ten
years, round 1 → round 2:

| Measure | Round 1 | Round 2 |
| --- | --- | --- |
| Battles | 17, all in year 1 | 60, spread over years 1, 3, 4, 5, 6, 8 |
| Casualties | 29,315 | 103,468 |
| Captures | 178 | 620 |
| Wars declared / ended | 43 / 39 | 26 / 24 |
| Events | 262 | 670 |
| Year-over-year transitions in which the map changed | 1 of 9 | 6 of 9 |
| Invariant violations | 0 | 0 |

Territory swings through the middle of the decade: Free Cities 15 → 33 → 3,
Astaran 27 → 44 → 30, Korsk 15 → 40 → 28, Meridian 22 → 34, Valdran 17 → 1. Of
the nine year-over-year transitions, six change the map; years 6, 7 and 10 repeat
their predecessor, which is the wind-down described at the end of this addendum.
Wars start, fronts move, wars end, nothing explodes — `CONTINUE_OFFLINE.md`'s
criteria are satisfied, with the caveat below.

**Neighbour-only war declaration was ruled conditionally and is NOT needed.**
Instrumenting all 26 declarations shows **0 were between factions that did not
share a border**: `update_diplomacy` already draws candidates from
`_neighbouring_factions`, computed from current controllers. The condition on
that ruling was not met, so nothing was changed.

**Remaining defect, escalated rather than fixed — the capital-loss doom
spiral.** Years 9–10 produce no battles, and 9 of 15 armies end the run at
`organization = 0.00, morale = 0.00, supply = 0.05`. Cause, measured at year 10:

- `update_supply` gives a faction no supply at all unless it controls its
  capital or a province with `industry >= 1.5`; every province then sits at
  `min_supply` (0.05).
- Valdran (1 province) and Free Cities (3 provinces) have lost their capitals
  and hold no industrial province, so all their territory is at 0.05.
- `update_movement` takes the low-supply penalty branch whenever supply < 0.35,
  so those armies can *never* reach the recovery branch. Organization decays to
  0 and stays there; below 0.15 they cannot even move.

That is an absorbing state with no exit: the faction cannot fight, cannot
recover, and cannot be finished off either, because `_defenders_in` scores a
garrison by raw headcount and three divisions at zero organization still look
like 158,000 defenders. It is the same class as the two defects already ruled
on — one system's rule making another's unreachable — but the supply rule is
documented as deliberate in Task 5 and there are credible fixes in two different
systems, so it is left for a ruling rather than improvised.

**No `[balance]` value was tuned in this round either, and exhaustion is the
reason it would have been wrong to.** Exhaustion never exceeds 0.03 in ten
years, so `peace_exhaustion_threshold` (0.75) remains dead config and all 24
wars ended on the stalemate timer. But the cause is not the multiplier: exhaustion
accrues as `new_casualties / (faction manpower + army strength)`, and that
denominator grows from 1.79M to 6.92M over the decade because recruitment fills
the national pool while nothing moves men from the pool into armies (army share
of manpower falls 0.48 → 0.07). Raising `exhaustion_per_casualty_fraction` by
the ~25x needed would be tuning around the ledgered manpower-demobilisation
defect, not balancing. Fix the reinforcement gap first; exhaustion should then
work at something near its current value.

### Fix round 3 addendum (same day) — defender scoring: measured, reverted, parked

Quality-based defender scoring was implemented exactly as ruled (score with
`battle.effective_power`; count only armies hostile to the mover) with two
passing regression tests, then measured over ten years on three seeds against
the round 2 baseline. It was reverted because it did not clear its gate.

| Seed | Variant | Battles (years with one) | Captures | Casualties | Map changed | Max prov | Events |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 42 | headcount | 60 (6/10) | 620 | 103,468 | 6/9 | 34 | 670 |
| 42 | **quality** | **163 (9/10)** | **4,416** | **270,369** | **4/9** | 38 | **2000 (cap)** |
| 7 | headcount | 146 (8/10) | 475 | 117,407 | 5/9 | 46 | 534 |
| 7 | **quality** | **259 (9/10)** | 581 | 185,920 | **8/9** | 46 | 649 |
| 99 | headcount | 235 (10/10) | 993 | 228,222 | 9/9 | 42 | 1088 |
| 99 | **quality** | 168 (8/10) | 635 | 150,998 | 7/9 | 34 | 722 |

The gate was "as good or better than round 2: battles spread across multiple
years, the map still changing in most years, no faction running away, invariants
clean." On the canonical seed 42 the change is clearly better on combat
(60 → 163 battles, 6 → 9 years with fighting, casualties 103k → 270k) and
clearly worse on territory (map changes in 4 of 9 year transitions, down from 6)
and on log readability (the event deque **hits its 2000 cap**, against 670
before). Across seeds it is a wash: better on 7, worse on 99. "As good or
better" was therefore not established, so it was reverted per the ruling.

**The finding that matters more than the verdict — capture churn.** Seed 42
under quality scoring produced **4,416 captures from only 163 battles**: roughly
4,250 bloodless walk-in flips, adjacent armies alternately occupying the same
undefended province forever. That is what saturates the event log and what makes
net territory look frozen while the front thrashes. The pathology **pre-exists
this change** in milder form — round 2 already ran 620 captures against 60
battles, a 10:1 ratio — and it is the likely reason territory freezes while
fighting continues. Quality scoring amplified it on one seed rather than causing
it. A future session should fix churn (an undefended province should not be
able to change hands every other tick) and re-apply defender scoring together
with it.

**Correction already applied above:** the round 2 addendum originally claimed the
map changed in "9 of 10 years" at seed 42. That was eyeballed from the printed
tables and was wrong; the programmatic count is **6 of 9 year-over-year
transitions**. The round 2 addendum has been corrected in place — this note
records only that the figure was retracted, so nobody reintroduces it from an
older copy. The round 2 verdict is unaffected.

### Final fix wave addendum (same day) — review findings

**Defender retreat: measured and reverted.** `defender_broke` is computed by
`resolve_battles` and read by nobody; only `attacker_broke` drives a retreat.
Measured over the decade at seed 42, **defender_broke fires on 26 of 60
battle-ticks against attacker_broke's 3**, so `defender_break_organization`
(0.20) is dead config and a beaten garrison fights to annihilation. Wiring a
symmetric retreat was implemented with two regression tests and measured on
three seeds against the current baseline:

| Seed | Metric | Now | With defender retreat |
| --- | --- | --- | --- |
| 42 | battles / capture-years / map changes | 60 / 8 / 6 of 9 | 94 / 6 / 5 of 9 |
| 7 | battles / capture-years / map changes | 146 / 7 / 5 of 9 | 130 / 6 / 5 of 9 |
| 99 | battles / capture-years / map changes | 235 / 10 / **9 of 9** | 277 / 3 / **2 of 9** |

It was reverted for failing its gate on "the map still changing". **The reason is
worth keeping:** a defender that retreats *survives*, so more armies remain alive
to garrison more provinces, and the front locks. Captures fall (620 → 480 at seed
42, 993 → 317 at seed 99) precisely because capture-churn is walking into *empty*
ground, and there is now less empty ground. Defender retreat therefore cures the
churn pathology by overshooting into stasis. A future session should expect to
re-apply it **together with** quality-based defender scoring (the other reverted
change, which makes armies more willing to attack a weak garrison); the two pull
in opposite directions and may only work as a pair.

**Battle events were unreachable; the threshold is now config.**
`SIGNIFICANT_BATTLE_LOSSES = 5_000` was a single-tick figure, but `resolve_battles`
bounds combined per-tick losses at `2 x base_casualty_rate` of engaged manpower.
Measured maximum single-tick total over three decades: **2,978 / 3,687 / 3,404** —
the threshold could never be met, so ten years logged **zero** military events
while 103,468 men died. It is now `balance.significant_battle_losses = 2000`,
chosen from the measured distribution: 2,000 sits at or above the 75th percentile
on all three seeds and yields 18 / 16 / 28 military events per decade against 620
territory events — a readable tail rather than a flood or silence. (1,500 was
suggested but logs 50% of all engagements at seed 42, which is not "significant".)

**`OCCUPIED_SUPPLY_PENALTY` deleted as a no-op.** `apply_control_changes`
multiplied `supply_value` by 0.5 on capture, but `update_supply` resets every
province to the floor at the top of the next tick and nothing reads it in
between. Confirmed empirically: removing it leaves all three decade runs
**byte-identical** on every measured figure. No durable occupation mechanic was
invented to justify it — that is next-phase design.

**Balance constants moved to `[balance]`, values unchanged:** `terrain_defence`
(as a sub-table), `broken_organization`, `broken_morale`, `attack_strength_ratio`,
`min_advance_organization`, `low_supply_threshold` and
`significant_battle_losses`. Proven value-preserving: after the move the decade
is identical to baseline on battles, captures, capture-years, casualties, map
changes, max provinces, break counts and invariants across all three seeds — the
only difference is the military-event count, which is the threshold change above.
**Deliberately left in code:** the `effective_power` quality coefficients and
`_TERRAIN_WEIGHTS`, because they are the shape of the model rather than balance
dials — tuning them would silently change what "power" and "map" mean.
`effective_power` now takes the terrain table as a parameter rather than
importing a module constant.

## 2026-09-23 — Application service layer: background thread, command queueing, and frozen views

**Decision:**
The application service layer (`src/endless_war/app/`) publishes immutable `WorldView` snapshots instead of allowing direct read access to mutable `WorldState`. Commands submitted to the service are queued and applied only at tick boundaries, never while the engine is mutating state. Four discrete speeds control the wall-clock rate: `paused`, `1x` (from config), `4x`, and `16x`. Catch-up after a sleep or stall is capped per wake to prevent the world from simulating a week at once.

**Reason:**
- Frozen views allow GTK and other consumers to read the world without locks. A copy happens once per tick, not on every view access, and the copy contains no mutable object shared with the live simulation state — the GTK thread cannot accidentally hold a reference to a live `Faction` and see it mutate mid-read.
- Commands applied only at tick boundaries preserves determinism: a paused, resumed, or sped-up run produces byte-identical history to a straight-through run of the same length and seed. If commands touched state during a tick, the same tick would have different effects depending on when a command arrived, breaking reproducibility.
- Discrete speeds (rather than arbitrary multipliers) are easier to understand and cheaper to schedule — the scheduler has only four branches rather than computing a divisor for every interval.
- The catch-up cap prevents the world from falling catastrophically behind wall-clock time. A ten-second stall at 1× speed would normally earn 10 ticks of catch-up; without a cap, a one-minute stall would simulate a day in one go, and a night's sleep would force a month-long sprint. Capping at 8 ticks (48 simulated hours) keeps the catch-up burst brief while letting a brief stall recover.

**Alternatives considered:**
- *Deep-copy `WorldState` into the view.* This is simple but expensive: every tick copies tens of thousands of objects, and a frequent reader (e.g., a UI that redraws every 100ms) would copy far more than necessary.
- *Share state under a read-write lock.* This adds latency to every tick (lock contention) and complexity (deadlock risk, unfair scheduling). A copy-once model is simpler and lighter.
- *Arbitrary speed multipliers.* A consumer submits `SetSpeed(2.5)` for a custom speed. This requires dynamic arithmetic on every interval calculation and is harder to test exhaustively; discrete speeds are easier to verify.
- *No catch-up cap, or a per-tick cap.* Unlimited catch-up can force the simulation to sprint for minutes after a stall. A tiny per-tick cap (e.g., 1) means a brief stall never recovers. The 8-tick compromise is measured from expected use: a reader stalled for 48 simulated hours (6 wall-seconds) is routine; a sprint longer than that should not happen silently.

**Consequences:**
- Commands are queued and idempotent to their own domain (pause, resume, speed, faction binding, shutdown). A command submitted while a tick is in progress is applied at the next tick boundary, not discarded; a command submitted while paused is applied immediately at the next tick.
- A tick that raises an exception sets a fault message and publishes a faulted view. The service stops ticking thereafter. There is currently no mechanism to clear a fault — a faulted service must be stopped and restarted (a process-level action). This is acceptable for the headless observatory and will be addressed by persistence (which knows how to load from a checkpoint, implicitly skipping the fault).
- Offline catch-up across process restarts is **not** provided by the application layer. It requires knowledge of when the process last stopped, which only persistence (with a save file and its modification time, or a boot log) can provide. The headless core handles a restart as a new game — see `max_offline_days_per_startup` in config.
- The simulation thread is single-threaded and single-instance per `SimulationService`. Starting a service twice on the same world state will deadlock or corrupt state; this is by design, not a limitation — one world, one thread.

## 2026-09-23 — GTK shell: a polled, thin window over the service

**Decision:**
The War Room polls `SimulationService.latest_view()` from a 250 ms `GLib.timeout_add` timer on the GTK thread; the simulation thread never touches GTK. The first map draws provinces as flat rectangles on a grid laid out by id, not as polygons. All logic lives in pure functions (colours, grid geometry, text formatting, cairo rendering onto any context) and the widgets are a thin shell, so the suite stays testable without a display. The tray shows Save as a disabled item rather than hiding it.

**Reason:**
- Polling needs no cross-thread signalling: the service already publishes immutable views, so the UI simply reads the newest one. Pushing from the simulation thread would need `GLib.idle_add` marshalling on every tick and would couple the tick rate to redraw cost; at 16× the service ticks far faster than a window can usefully repaint.
- Worldgen has no province shapes, only ids on a grid. Polygons would mean inventing geography the simulation does not have. Rectangles show ownership, contested ground, capitals, armies and supply faithfully.
- Only the widget layer needs an X display. `render_map` is tested pixel by pixel against a cairo image surface, and the formatters against plain views.
- A disabled Save says that saving is coming and not yet there; a missing one reads as an oversight.

**Alternatives considered:**
- *Push views with `GLib.idle_add` from the simulation thread.* Rejected for the coupling above, and because an exception in that path would sit on the simulation thread.
- *Province polygons (Voronoi or hand-drawn).* Deferred until worldgen produces geography worth drawing.
- *Hide Save until persistence exists.* Rejected as above.

**Consequences:**
- A view can be up to 250 ms stale, and at 16× the service ticks about every 62 ms, so one repaint can jump several ticks. That reads as smooth enough at every speed tried; nothing is lost, because each view is a complete snapshot.
- An exception in the refresh path is caught, printed to stderr and shown in the header as `UI FAULT: …` for the rest of the session (sticky, so a one-off failure is not erased by the next good refresh), and the timer keeps running. Found in review: GLib drops a timeout source whose callback raises, which would freeze the window with only a stderr trace.
- Found by running it: showing or presenting the window handed keyboard focus to the 1x button, so a space typed into another app at that moment changed the speed. `WarRoom.show()` clears the focus after presenting. The buttons stay focusable, so Tab still reaches them; making them unfocusable was tried first and rejected in review as a permanent keyboard-access loss for a momentary problem.
- The event feed is shown newest-first, because its scroller opens at the top.
- The map legend paints its swatches with the map's own cell painters, so it cannot drift from what the map shows.

## 2026-09-24 — History tab: casualties recorded in the simulation, cumulative, validated palette

**Decision:**
The casualty series is recorded by the simulation (`systems/history.py`, one frozen reading per simulated date, kept in `WorldState`) rather than sampled by the window. The chart plots cumulative totals. The factions were recoloured to the dataviz reference palette's dark steps (blue, orange, teal, gold, pink). `build_view` reuses the previous view's event lines.

**Reason:**
- A series recorded in world state is saved by persistence (sub-project B) with no extra work, so a loaded game keeps its history; a window-side sample would belong to one window and vanish on restart.
- Cumulative totals only rise, read at a glance, and compare factions directly; the user chose it over deaths-per-month.
- The old palette failed the validator on the map background (#1c1f24): violet vs blue at normal-vision ΔE 11.6 (floor 15) and colour-blind ΔE 3.7; amber outside the lightness band. The new five pass every check for line charts.
- Converting a full 2000-event log to view lines measured 1.5 ms per snapshot against a 1 ms budget; ids are consecutive and the log evicts only from the left, so the previous tuple can be sliced and only new events converted. Measured after: 0.17 ms with 10 years of readings and 2000 events; the 10-year CLI run 4.78 s (was 4.7 s).

**Alternatives considered:**
- *Sample in the window.* Rejected for the persistence reason above.
- *Keep the old colours and rely on labels.* Rejected: violet/blue is hard to tell apart even with full colour vision, on the map as much as the chart.
- *Rebuild the event log every snapshot.* Rejected on the measurement above.

**Consequences:**
- No five colours can pass all-pairs colour-blind separation (the reference palette validates only its first three). On the map the legend and the bound-faction outline are the secondary encoding; on the chart, the direct labels.
- `build_view(previous=...)` must be given a view of the same world; only `SimulationService` passes it.
- Readings are never downsampled. A century is ~36,500 readings; the chart strokes at most one per horizontal pixel.
- Coincident series (two factions with equal mutual losses) draw on top of each other; the later faction's line shows, and the hover tooltip gives exact values. Their direct labels are spread apart and kept inside the widget.

## 2026-09-24 — Speeds extended to 32x and 64x

**Decision:**
Two speeds were added above 16x, at the user's request: `32x` and `64x`. `clock.RUNNING_SPEEDS` is now the single list both the toolbar and the tray menu read.

**Reason:**
- A decade at 16x takes about 23 minutes of wall-clock time; at 64x it takes under 6.
- Measured at 64x on this machine: exactly 64 ticks/s (16 simulated days per second), 12.5% of one core, no fault. The service polls every 20 ms, so each wake runs one or two ticks, far below `max_catchup_ticks_per_wake`.

**Alternatives considered:**
- *64x only.* Rejected by the user in favour of a denser ladder (1x 4x 16x 32x 64x).

**Consequences:**
- The earlier 2026-09-23 entry's "four discrete speeds" is superseded: there are now six, including `paused`.

## 2026-09-24 — Isometric pixel-art map: dark terrain under a faction wash

**Decision:**
The map is an isometric board built from newc-42's "Pixel Art Isometric Map Tileset" (CC0 1.0, https://newc-42.itch.io/pixel-art-isometric-map-tileset), committed as `src/endless_war/ui/assets/terrain.png`. Terrain is the simulation's own (`Province.terrain`), drawn darkened and desaturated; each province is washed in its controller's colour at 35 % (first 45 %; lowered at the user's request so more terrain shows through). The map opens at the scale at which the land exactly fills its area (the sea ring may run off the edges), sampled nearest-neighbour; zoom steps above that are whole numbers.

**Reason:**
- The user asked for 8-bit art that is serious rather than cartoonish, "grim and dark", and chose this pack. It is CC0, so it can live in the repo.
- Terrain already changes battles (`[balance.terrain_defence]`) but was invisible; the map now shows it.
- Of four mockups rendered from a real game, the user chose D. The per-tile outline (A, C) was busy and read weakly on dense forest, and bright terrain (A, B) was not grim.
- The first build used whole-number scales only, to keep every pixel square. At the default window that meant 1×, and the user found it too zoomed out; they chose "fill the space" over half steps or a bigger default window. Fitting land and sea together still opened too far out (about 1.26×), so the fit ignores the sea ring (about 1.51× at the default window). Nearest-neighbour keeps hard edges; some pixel rows come out one screen pixel wider than others, which is barely visible at this size.

**Alternatives considered:**
- *Fantasy Hex Tiles (CC-BY 4.0).* A hex pack; would have changed the grid, and its towns and castles are medieval, which the user ruled out.
- *Paid military packs.* Not free, and their licences forbid committing the files.

**Consequences:**
- Hills and urban have no exact tile in the pack. Hills use the low mountain range; urban uses the plotted fields, with a town glyph drawn on top.
- The pack's snow, desert and lava tiles are unused; water forms a one-tile sea around the board.
- `geometry.cell_for` / `province_at` are gone; `iso.province_at` replaces them, ready for province selection.
- Darkening the sheet costs one Python pass over its pixels at first draw: 66 ms, measured.
- The legend's terrain section makes the side column taller than the default 640 px window, so the side column scrolls.
- Zoom (scroll wheel) and pan (middle-button drag) were added at the user's request. Zoom moves in whole-scale steps from the fitted scale up to 8×, anchored at the cursor; zooming back down to the fitted scale recentres and clears the pan; panning is clamped on the board's diamond, not its bounding box (whose empty corners let the map vanish, per the final review): the diamond's point nearest the widget centre stays at least 48 px inside. A resize drops a camera at or below the new fit and re-clamps any other. Smooth-scroll deltas accumulate, so a touchpad swipe zooms one step per unit of scroll, not per event. The state lives in `MapView`, never in the simulation.
