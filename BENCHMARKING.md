# Benchmarking AI models

Two layers: the server records **metrics** for every session automatically, and the **harness**
in `bench/` drives agent CLIs headless against the server, enforces budgets and publishes the
results as `results/*.json` and [RESULTS.md](RESULTS.md).

## What the server records

Nothing needs to be called except `metrics("finalize")` at the end (or start the server with
`--finalize-on-exit`); the tracker also checkpoints on every autosave and on shutdown, so a crashed
run still leaves `metrics/<session>_checkpoint.json`.

* active real seconds (accumulated across launches of the same session; a gap of more than five minutes
  between tool calls counts as five minutes, so a stalled or disconnected client does not run the clock),
  emulated frames, in-game playtime
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

If a resumed CLI session produces no tool call within five minutes (Codex, for example, cannot resume a
very long thread when its remote compaction fails) the harness abandons that session and starts a fresh
one with the continue prompt; the game state and the agent's notes live on the server, so nothing is lost.

Providers: `claude` (Claude Code CLI, any Claude model id), `codex` (OpenAI Codex CLI) and `jev` (see
the Jev track below; it is reported separately because it gets code scaffolding). Tokens
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

## Jev track (TypeSafe System One)

Jev (`jev-latest`, docs.typesafe.ai) answers typed questions about a `state`: a Choice over options we
define (with a probability per option and a `confidence`), a yes/no Noul, or a Score. It cannot write
text or call tools, so it cannot drive the MCP server the way an agent CLI does. Jev runs therefore get
code scaffolding and are reported in a **separate table** in `RESULTS.md`.

```bash
# the key is read from TYPESAFE_API_KEY only; load it per command, never store it in the repo
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --smoke                     # jev-solo
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant hybrid --smoke
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant battles --smoke
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant assist --smoke
venv/bin/python bench/run.py --provider jev --variant solo --mock     # offline: MockJev, no network, never a result
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev    # a full 12 h / 20k-call jev-solo run
```

How it plays (`bench/jev_agent.py`, `bench/jev.py`, `bench/jev_solo.py`): the agent is an MCP client of
`server.py`, launched by `run.py` like a CLI (same chunks, budgets, autosave resume and metrics session;
it prints a JSON event stream). Every step it parses the server's reply, classifies the situation
(intro, prompt, dialogue, battle, overworld), lists the legal actions as a closed set (walk to each exit,
connection, objective waypoint or nearby person/object; each usable move, switch, item, run; menu
presses) and asks Jev one Choice: "which action makes progress toward `objective`?". The option order
is shuffled per question (Jev 1.13 leans toward the first option). Situations with a single sensible
action (continue a dialogue, press A through battle text) are executed by code and logged as `forced`.

Variants (`--variant`):

* **solo** (default; the final exam): no LLM is called at any point, and a run with no progress for
  `--stuck-fail-steps` (2000) steps ends as `stuck` (a fail). Long-horizon structure is code:
  a whole-game objective graph (`jev_solo.GRAPH`, 33 nodes from the intro to the Champion) whose `done`
  tests read badges, bag contents (key items, HMs, ever-held items), moves the party knows, maps visited
  and milestones; rules that override the objective (heal at a Poké Center under 35% team HP, train to a
  per-gym level target, teach an HM as soon as it is in the bag, use Cut/Surf/Strength when the hint
  says an obstacle is in front); stuck recovery (frontier exploration of unvisited exits after 60 idle
  steps, longer walks and menu resets after 150, START/B menu reset after 15 steps without moving, reload
  the last `jev-progress` checkpoint after 45). Jev picks every action and answers Nouls: "are we
  stuck?" and, for story events code cannot see (Silph Co. cleared), "is this objective done?" (three
  answers >= 0.8 in a row mark it done).
* **assist** (the run mode of the self-improvement loop): jev-solo's scaffolding plus a safety net. When
  Jev's confidence is below `--fallback-threshold` (0.3), or on the map code detects stuck (recovery level 2
  or 10 steps without moving) or a loop (an option's identical result 3 times in the last 12 actions),
  Claude Haiku 4.5 picks that one action from the same option list (at most every 3 steps). Every
  fallback is a structured event in `bench/runs/<id>/fallbacks.jsonl`: trigger, map/position, objective
  and graph node, a state summary (badges, money, party, bag, moves, recent milestones), screen text,
  recent actions, Jev's options with probabilities and its pick and confidence, Haiku's pick and reason,
  agreement, cost, latency, and the outcome 10 steps later (moved, new maps/milestones/items =
  progress). Key metric: fallbacks per 1k steps (goal 0). Decisions Haiku overrode are kept out of Jev's
  calibration curve.
* **hybrid**: Claude Haiku 4.5 (`claude -p`, no tools) sets the objective and waypoints at the start,
  every 40 steps, after a badge, when Jev's confidence falls below 0.3 or its "stuck" Noul reaches 0.7
  (then Jev is asked again with the new objective). Jev picks every action.
* **scripted**: a short code-side objective list (`jev.ROUTE`) with no rules and no recovery.
* **battles**: the normal Claude Code + Haiku run (same tools; the prompt gains one line), but the
  server's `battle('auto')` asks Jev for every turn (`server.py --battle-advisor jev`).

### Self-improvement loop (jev-assist → analysis → next iteration)

```bash
# iteration N: run from a fixed segment state (bench/segments.json; its sha256 is recorded) until the segment goal
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant assist --segment after-brock --iteration 1
# analysis: cluster the fallbacks and write the Opus prompt (dry run); --call sends it to claude-opus-5-5
venv/bin/python bench/improve.py analyze bench/runs/<run_id> --iteration 1            # -> bench/iterations/it1/{clusters.json,prompt.md}
venv/bin/python bench/improve.py analyze bench/runs/<run_id> --iteration 1 --call     # -> summary.md, proposal.patch, analysis.json (cost)
# apply on a new branch jev-iter-2 (refuses main; nothing committed), review, run the tests, rerun the same segment
venv/bin/python bench/improve.py apply --iteration 1
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant assist --segment after-brock --iteration 2
venv/bin/python bench/improve.py compare --segment after-brock                       # fallbacks/1k, badges, time, cost per iteration
# final exam once fallbacks are ~0: strict solo, no LLM, stuck = fail
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --provider jev --variant solo --segment after-brock --iteration 2
```

Segments (`bench/segments.json`): `power-on` → Boulder Badge, `after-brock` → Cerulean City (Mt. Moon),
`cerulean` → Cascade Badge, `viridian-gym` → Earth Badge. The states are local files (gitignored); a run
ends with exit reason `segment_goal` when the goal milestone appears. The Opus prompt contains the
largest clusters (trigger × graph node × map × situation) with sample events and the full source of
`bench/jev_solo.py`, `bench/jev.py` and `bench/jev_agent.py`, and asks for a per-cluster diagnosis
(including "Jev cannot do this" when that is the answer) and one unified diff. `RESULTS.md` shows a
self-improvement table per segment (iteration, steps, fallbacks, per 1k, goal reached, badges, hours,
Jev / Haiku / Opus / total cost); `run.py --iteration N` records the cost of the analysis in
`bench/iterations/it<N-1>/analysis.json`. Multi-hour runs and Opus analysis batches need Bijan's go.

Where Jev alone cannot decide, and what code does instead: Jev never produces arguments, so every
destination, move and menu path is enumerated by code; arithmetic (HP fractions, level targets, damage)
stays in code (Jev is not a calculator); story progress is read from game data, not judged, except the
few `jev_check` nodes; the START/B reset after Oak's "Don't go away yet!" push-back (the game ignores
directions until a menu opens and closes; seen with mock runs, it can affect any agent) is a code fix.

Logged per decision (`bench/runs/<id>/data/jev_decisions.jsonl`): situation kind, number of options,
choice, p(choice), confidence, top-two ratio, option position, latency, input tokens, cost, model
version, the reply head and an outcome label. **Correct** is a proxy: the action was accepted and did
what it is for (a battle action that hurt the foe at least as much, as a share of max HP, as the turn
hurt us, or ended the battle; a walk that moved the player or started something new; a press that
changed the screen); refusals, black-outs and a result already seen twice in the last 12 actions count
as wrong. `report.py` bins decisions by Jev's confidence into a calibration table (accuracy vs. mean
confidence and mean p(choice), ECE) and adds Jev latency p50/p95, Jev cost ($0.042 per million input
tokens, output free) and LLM cost per run. Objective changes (graph, rules, planner, Jev "done") are in
`data/jev_objectives.jsonl`.

## Round one notes (October 2026)

* **Call budgets reward save-state scumming.** `save_state`/`load_state` are tool calls like any other, and
  gpt-5.6-sol spent about 9,000 of its 20,000 calls on 7,100 reloads (re-rolling battles and encounters).
  It still reached the Champion's room. A future round may count only game actions toward the budget, or
  cap reloads; until then the reload count is shown in each run's section.
* **Codex cannot resume very long threads** (its remote compaction step fails); the harness falls back to
  a fresh session. Codex also reports token usage only when a turn completes, so the harness reads the
  usage back from `~/.codex/sessions/**/rollout-*.jsonl` after the run (`tokens_source` in the result).
* **Token columns** are uncached input / cache reads / output for both providers (Codex counts cache reads
  inside its input figure; the harness subtracts them). Claude Code's cost is the CLI's own cumulative
  API-equivalent figure; Codex reports none.
* **Model behaviour dominates.** Haiku 4.5 ended its turn about 2,200 times and declared the game
  unwinnable after one badge; gpt-5.6-sol played continuously and took eight badges plus four Elite Four
  wins in under five active hours.

## Claude Fable 5.1 (October 2026)

* `claude-fable-5-1` via Claude Code, same prompt and budgets: Squirtle start, all eight badges by 2:51 active
  hours, Victory Road's boulder puzzles took another 1.5 hours, then the Elite Four and the Champion in one pass:
  **Hall of Fame at 4:23 active hours and 3,904 tool calls** with 19 reloads and no black-outs. The Claude
  subscription's session limit paused the run for 75 minutes (not counted as active time).
* **Claude Code's stream undercounts output tokens** (each streamed assistant message carries a partial output
  count) and a rotated chunk never sees the final cost figure. The harness now reads token usage back from the
  CLI's session transcripts (`~/.claude/projects/*/<session>.jsonl`, `tokens_source` in the result), and when the
  session's last working chunk reported no cost it uses the list-price estimate if that is higher than the last
  reported figure (marked `(est.)`). Checked on this run: the estimate up to the last reported figure was $106.88
  against the CLI's $107.36. The Haiku 4.5 result is unchanged (its transcript matches its stream totals and its
  CLI figure is higher than the estimate).
