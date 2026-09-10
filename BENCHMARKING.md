# Benchmarking AI models

Metrics are recorded automatically from the moment the server starts. Nothing needs to be
called except `metrics("finalize")` at the end (the tracker also checkpoints on autosave and
shutdown, so a crashed run still leaves `metrics/<session>_checkpoint.json`).

## What is recorded

* real-time seconds, emulated frames, in-game seconds
* tool calls (total and per tool), images sent, text characters sent (a proxy for tokens)
* milestones with timestamp, frame and tool-call count:
  * Pokémon: `game started`, `badge: Boulder`, `obtained: Pidgey` (caught or received),
    `evolved: Caterpie → Metapod`, `reached: Viridian City` (towns, routes, dungeons),
    `blacked out (lost a battle)`, `champion defeated (Hall of Fame)`
  * PyBoy-wrapped games (Tetris, Mario, Kirby, Pinball): world / level changes
  * anything you add with `metrics("milestone", "name")`
* a final state snapshot from the game profile (badges, Pokédex counts, party, money, map,
  maps visited, battles fought, playtime; or score/lives)

## Files

```
metrics/<model>_<timestamp>.json             full data
metrics/<model>_<timestamp>_summary.txt      human-readable
metrics/<model>_<timestamp>_checkpoint.json  in-progress copy (deleted on finalize)
```

## Compare runs

```bash
python compare_benchmarks.py            # table of all runs + time-to-milestone comparison
python compare_benchmarks.py --dir other/metrics
```

The comparison lists, per model, real time, tool calls, images, badges/score, and how many
tool calls each model needed to reach every milestone that at least two runs share.

## A baseline to compare against

`examples/reference_run.py` is a scripted (non-LLM) agent that plays from power-on to the Boulder
Badge with the public tools. It needs about 1,400 tool calls, mostly wild battles while levelling,
and finishes in about 35 seconds of real time. A model that reaches Brock in fewer calls is
planning better than the script; one that needs far more is wasting turns on screenshots or
single presses. Its metrics land in a temp folder (printed at the end of the run).

## Tips for fair comparisons

* Start each run with the same command line, including `--ai-model`.
* Use `--no-fast-text` only if you want to compare against the game's default options
  (it makes every run slower in real time but does not change difficulty).
* Keep memory writes disabled (the default). The `memory` tool can still read RAM.
* Use `reset_game(confirm=true)` or delete `saves/<rom>/autosave.state` between runs so a
  `--resume` does not carry progress over, and delete `<rom>.ram` if an in-game save exists.
* Game outcomes vary with RNG (the reference agent loses the rival fight on some seeds and
  recovers); compare several runs per model.
