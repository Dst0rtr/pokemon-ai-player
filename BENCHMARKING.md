# Benchmarking AI models

Two layers: the server records **metrics** for every session automatically, and the **harness**
in `bench/` drives agent CLIs headless against the server, enforces budgets and publishes the
results as `results/*.json` and [RESULTS.md](RESULTS.md).

## What the server records

Nothing needs to be called except `metrics("finalize")` at the end (or start the server with
`--finalize-on-exit`); the tracker also checkpoints on every autosave and on shutdown, so a crashed
run still leaves `metrics/<session>_checkpoint.json`.

* real-time seconds (accumulated across launches of the same session), emulated frames, in-game playtime
* tool calls (total and per tool), images sent, text characters sent, state reloads, agent notes
* milestones with timestamp, frame, tool-call count and a snapshot of the team (levels, HP, moves, stats):
  * Pokémon: `game started`, `starter: Charmander`, `badge: Boulder`, `obtained: Pidgey`,
    `evolved: Caterpie → Metapod`, `reached: Viridian City` (towns, routes, dungeons, Elite Four rooms),
    `defeated: Lorelei` … `defeated: Champion`, `champion defeated (Hall of Fame)`,
    `blacked out (lost a battle)`, `loaded state 'x'`
  * PyBoy-wrapped games (Tetris, Mario, Kirby, Pinball): world / level changes
  * anything the agent adds with `metrics("milestone", "name")`
* a final state snapshot (badges, Pokédex counts, party, money, map, maps visited, battles, playtime)

Session flags: `--session-id ID` continues the same metrics session across server launches (together
with `--resume` for the game state); `--max-tool-calls N` and `--max-real-seconds S` make every game
action answer `BUDGET EXHAUSTED` once a budget is used up and finalize the report; `--log-file` keeps
the server log.

```
metrics/<session>.json             full data (written by finalize)
metrics/<session>_summary.txt      human-readable
metrics/<session>_checkpoint.json  in-progress copy (deleted on finalize)
```

## The harness

`bench/run.py` plays one benchmark run with an agent CLI:

```bash
venv/bin/python bench/run.py --provider claude --model claude-haiku-4-5-20251001
venv/bin/python bench/run.py --provider codex  --model gpt-5.6-sol
venv/bin/python bench/run.py --provider claude --smoke        # two 4-minute chunks + a checklist
venv/bin/python bench/report.py                                # rebuild RESULTS.md from results/
```

Every run gets its own directory under `bench/runs/<run_id>/` (gitignored) with a copy of the ROM,
its own `data/` (saves, metrics, server log), the exact prompt, the CLI config and the raw JSON
streams of every chunk. The CLI is launched headless with only the `gameboy` MCP server (no shell,
no file tools) and the same prompt for every model (`bench/PROMPT.md`). It runs in chunks of at most
60 minutes: when a chunk ends (the model stops, the chunk rotates, or it stalls for 15 minutes) the
CLI session is resumed with `bench/CONTINUE.md`, and the server resumes from its autosave and the
same metrics session. The run ends on the Hall of Fame milestone, after 12 hours of active play or
20,000 tool calls (whichever comes first), or after three CLI failures in a row. Rate-limit pauses
are not counted as active time.

Providers: `claude` (Claude Code CLI, any Claude model id) and `codex` (OpenAI Codex CLI). Tokens
and cost come from the CLI's own stream; when a chunk ends without a cost figure the cost is
estimated from `bench/prices.json` and marked as such.

## Results

`results/<run_id>.json` (schema 1) holds three blocks: `harness` (provider, CLI version, model,
prompt hash, server commit, chunks with tokens and exit reasons, totals), `metrics` (the server's
metrics file verbatim) and `derived` (starter, badges, time and tool calls to each badge, Elite Four
member and the Champion, furthest story point, final team with stats and moves).

`RESULTS.md` is generated from those files: a leaderboard (Champion first by time, then badges,
then furthest point, then fewer tool calls) and a section per run with the final team, the milestone
timeline, the agent's notes and the chunk table.

## Baselines

* `examples/reference_run.py`: scripted (non-LLM) agent, power-on to the Boulder Badge in about
  1,400-1,700 tool calls and under a minute of real time.
* `examples/extended_run.py`: continues from a local after-Brock state through Mt. Moon to Cerulean
  City and Misty, exercising caves, trainers, heals, in-battle items and the world graph.

Both log every unexpected tool reply as `ODD:` and end with an oddity count; they are the regression
gate before any model hours are spent.

## Fairness notes

* Same prompt, same server flags, same budgets for every model; runs are sequential on one machine.
* Memory writes stay disabled; the `memory` tool can still read RAM.
* Each run starts from power-on with its own ROM copy (no battery save, no autosave).
* Outcomes vary with RNG and with the model's own choices (starter, team); one run per model is a
  sample, not a verdict.
