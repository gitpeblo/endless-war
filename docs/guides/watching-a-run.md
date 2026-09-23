# Watching a run

```bash
./scripts/run_cli.sh                        # 10 simulated years, seed 42
./scripts/run_cli.sh --years 1 --seed 7     # a shorter run, a different world
```

Ten simulated years take about six seconds.

## Reading a year

Each block is one simulated year:

```
Faction                 Prov    Population   Casualties    Exh
Valdran Hegemony          18     9,929,272       10,458   0.03
Korsk Federation          15     7,175,765            0   0.00
...
wars: 1 active, 9 total
  · 2032-12-23  Province captured: Free Cities League has taken P013…
```

- **Prov** — provinces controlled right now. Watch this column across years; it
  is the clearest sign of who is actually winning.
- **Population** — people living under that faction's control, which sets both
  its income and its recruiting ceiling.
- **Casualties** — cumulative dead, for the whole game.
- **Exh** — war exhaustion, 0 to 1.

Then the war counts, then that year's last few events.

The run ends with `Completed N simulated years with no invariant violations` —
meaning nothing went out of range. If something does, it stops and tells you
what broke instead of carrying on with nonsense numbers.

## What an interesting run looks like

Territory that moves in most years, wars that start *and* finish, and no single
faction swallowing the map. At seed 42 you should see provinces changing hands
in eight of ten years, a couple of dozen wars declared and nearly as many ended,
and a faction that rises to a third of the map then gets pushed back.

If you want to compare two runs, keep the seed fixed — the same seed always
produces exactly the same history, so any difference you see comes from a change
to the game, not from luck.
