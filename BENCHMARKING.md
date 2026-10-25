# Benchmarking AI models

Two layers: the server records **metrics** for every session automatically, and the **harness**
in `bench/` drives agent CLIs headless against the server, enforces budgets and publishes the
results as `results/*.json` and [RESULTS.md](RESULTS.md).

The main benchmark is LLM agents playing through the MCP server (`--mode llm`). The optional autonomous Jev mode
(`--mode jev-*`, [Jev track](#jev-track-typesafe-system-one)) is a separate, code-scaffolded track with its own tables
in RESULTS.md; its results are not comparable with the LLM leaderboard.

## Running a benchmark (copy-paste)

### Prerequisites

* Python 3.11+ venv with `requirements.txt` (`python3 -m venv venv && venv/bin/pip install -r requirements.txt`).
* `Pokemon-Red_Version.gb` in the project root (your own dump; never committed). `--rom PATH` picks another file.
* Check the setup first: `venv/bin/python -m pytest tests -q` (about 20 s) and
  `venv/bin/python examples/reference_run.py Pokemon-Red_Version.gb` (expect "0 oddities").
* LLM providers need their CLI on `PATH`, already logged in: `claude` (Claude Code) and/or `codex` (OpenAI Codex CLI).
  The harness runs them headless with only the game server attached (no shell or file tools).
* Jev needs a TypeSafe API key (docs.typesafe.ai). Put it in **`~/.typesafe-api-key`**, outside the repo, readable
  only by you (`chmod 600 ~/.typesafe-api-key`). Never put it in the repo, `.env`, logs or commits. The harness
  reads only the env var `TYPESAFE_API_KEY`, so load it **per command**:
  `TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py ...`.
  Without the key, a real Jev run exits immediately; `--mock` works offline.
* Segment runs (`--segment`) need the local save states named in `bench/segments.json` under
  `saves/Pokemon-Red_Version/` (gitignored). `power-on` needs none.

### Play modes

Every run picks one play mode with `--mode` (`--provider`/`--variant` still work; the mode is recorded in the result).

| `--mode` | What decides each action | LLM calls | Use it when |
|---|---|---|---|
| `jev-solo` | Jev picks from code-listed options; code holds the objective graph, map routes, heal/train rules, stuck recovery | none | the final exam / headline Jev result: can Jev finish with code scaffolding only? Stuck = fail |
| `jev-assist` | as jev-solo, but an LLM (`--fallback-model haiku\|sonnet\|opus`) picks the action when Jev is unsure (confidence < 0.3) or code detects stuck/looping; every fallback logged | only on fallbacks, capped by `--fallback-budget-usd` (default $25) / `--max-fallbacks` | improving the scaffolding: the fallbacks show where Jev cannot decide (self-improvement loop) |
| `jev-hybrid` | Jev picks actions; an LLM (`--model`, default Haiku) sets the objective every 40 steps and when Jev is stuck | every ~40 steps | comparing code objectives with LLM objectives |
| `jev-scripted` | Jev picks actions toward a short fixed route list, no rules or recovery | none | an ablation: how much the scaffolding matters (for a fully scripted, AI-free baseline use `examples/reference_run.py`) |
| `jev-battles` | the LLM agent CLI plays (Claude Code + `--model`), Jev decides each `battle('auto')` turn | the whole run | testing Jev as a battle module inside an LLM run |
| `llm` + `--provider claude\|codex` | an agent CLI alone with the MCP tools and the shared prompt | the whole run | the main leaderboard: model vs. model, no code help |

Jev runs also pick where map knowledge comes from, `--map-source`:

| `--map-source` | What the Jev player knows about maps | Use it when |
|---|---|---|
| `learned` (default) | nothing at the start; Jev builds an atlas while playing (`bench/jev_atlas.py`): the map view and wWarpEntries (WRAM 0xD3AE) of each map it enters, and where each warp or edge it takes really leads. It explores frontier-first (untaken warps to unvisited maps, then uncrossed edges). Saved as `data/jev_atlas.json`; `--atlas FILE` carries an earlier run's atlas into a new run. Results record whether a run started blank or with a carried atlas | every benchmark run, including the jev-solo goal and the full run (started blank): exploring is the better test of the model |
| `rom` | the whole world/warp graph decoded from the ROM map headers and warp tables (`bench/jev_nav.py`): which ladder on which floor leads where, every edge connection | comparison and debugging only: needs `--experiment LABEL` (run ids get `-rommap`) |

**Rule for benchmark and goal runs:** every run builds its own map and finishes on its own: `--mode jev-solo`, `--map-source learned`, no `--atlas` (the atlas starts blank; results record `atlas_seed: null`). A rom map or a carried atlas (`--atlas FILE`) is refused unless the run is labelled with `--experiment LABEL`; such runs are marked "experiment" in RESULTS.md.

### One command per mode

Add `--smoke` to any of these first: short chunks and small budgets, then a pass/fail checklist (a few minutes,
cents for Jev). A run without `--smoke` is a full run: 12 h of active play or 20,000 tool calls, whichever
comes first.

```bash
# Jev, no LLM at all, exploring from a blank atlas (the final exam; stuck for 2,000 steps = fail)
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo
# Jev + an LLM fallback on uncertain or stuck decisions (the self-improvement run mode)
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-assist --fallback-model haiku --fallback-budget-usd 25 --segment mt-moon --iteration 3
# experiments only (labelled): carry an earlier run's atlas over, or compare with the ROM map graph
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo --atlas bench/runs/<earlier_run>/data/jev_atlas.json --experiment carry
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo --map-source rom --experiment rommap
# Jev picks actions, an LLM plans objectives
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-hybrid --model haiku
# Jev picks actions toward a fixed route list (ablation)
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-scripted
# Claude Code + Haiku plays; Jev decides every battle('auto') turn
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-battles --model haiku
# any Claude model through Claude Code (aliases: haiku, sonnet, opus, fable)
venv/bin/python bench/run.py --mode llm --provider claude --model claude-haiku-4-5-20251001
# any OpenAI model through the Codex CLI
venv/bin/python bench/run.py --mode llm --provider codex --model gpt-5.6-sol
# offline check of the Jev track (MockJev, no network, no key, never a result)
venv/bin/python bench/run.py --mode jev-solo --mock
```

Useful flags: `--segment NAME` (start from a fixed save state, stop at its goal; see `bench/segments.json`), `--iteration N` (label for the
improvement table), `--budget-hours`, `--max-calls`, `--resume-run bench/runs/<run_id>` (continue an interrupted
run), `--jev-model jev-preview`. Run `venv/bin/python bench/run.py -h` for the rest. Runs are sequential: start
the next one only after the previous one has exited.

### What the outputs mean

* `bench/runs/<run_id>/` (gitignored): everything about one run. `harness.log` (one line per chunk and the exit
  reason), `harness.json` (state), `chunks/` (raw event streams), `data/` (server saves, metrics, server log).
  Jev runs add `data/jev_decisions.jsonl` (every decision: options, choice, p, confidence, latency, cost,
  outcome label), `data/jev_objectives.jsonl` (objective changes) and, for assist, `fallbacks.jsonl`.
* `results/<run_id>.json`: the published record of a full run (not written for `--smoke`/`--mock`).
  `RESULTS.md` is regenerated from all of them: LLM runs in the main leaderboard, Jev runs in the separate,
  code-scaffolded Jev track with a calibration table and the self-improvement table.
* Exit reasons: `champion` (Hall of Fame), `segment_goal` (the segment's goal milestone), `budget_calls`,
  `budget_time`, `stuck` (Jev solo/assist: no progress for `--stuck-fail-steps`), `max_chunks`, `cli_failures`.
* Key Jev numbers: fallbacks per 1k steps (assist; goal 0), Jev latency p50/p95, calibration (accuracy per
  confidence bin; "correct" is a proxy label, see below), cost split Jev / Haiku / Opus.

### Costs (October 2026 measurements)

| Mode | Typical cost |
|---|---|
| jev-solo | Jev only: $0.042 per million input tokens, output free; about $0.03 per 1,000 decisions |
| jev-assist | Jev plus about $0.008-0.01 per Haiku fallback (8-20 s each); iteration 1: 225 fallbacks = $1.87 |
| jev-hybrid | Jev plus about $0.01 per Haiku planner call (one per 40 steps or when stuck) |
| jev-battles | the Claude Code + Haiku run (the bulk) plus Jev per battle turn |
| claude / codex | the model's own tokens: Haiku 4.5 full run $172, Fable 5.1 to the Champion $196 (see RESULTS.md) |
| improve.py `--call` | one Opus 5.5 call per iteration, roughly $1-3 (the prompt holds the Jev source + clusters) |

### Troubleshooting

* **"TYPESAFE_API_KEY is not set"**: the key was not loaded for this command; use the `"$(cat ~/.typesafe-api-key)"`
  prefix. 401 = wrong key. 429/529 are retried with backoff by the client.
* **Oak's lab "Don't go away yet!"**: after the push-back the game ignores directions until a menu opens and
  closes. The Jev agent opens and closes START automatically and retries the walk; an LLM agent may need to press
  START then B itself.
* **A run seems stuck**: `tail bench/runs/<run_id>/harness.log`; for Jev, the last lines of
  `data/jev_decisions.jsonl` show the repeating choice. Stop with Ctrl-C (or `kill` the `run.py` process); continue
  later with `--resume-run`.
* **"segment ... needs the local save state"**: create it (for example from a run's `data/saves/autosave.state`
  at the segment goal) and copy it to the path in `bench/segments.json`.
* **CLI errors / rate limits** (claude, codex): the harness pauses on rate limits and resumes; three CLI failures
  in a row end the run. Make sure the CLI is logged in by running it once interactively.
* **No `.ram` next to the ROM**: keep the project ROM free of a battery save for reproducible runs (each run uses
  its own ROM copy anyway).

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

Results so far (details in RESULTS.md, "Jev full-game benchmark entries"):
* the one run under the standard limits (12 h / 20,000 calls, blank map, unassisted) reached 5 badges, stopped by the
  call cap;
* `uncapped-2` (2026-10-21, blank map, unassisted, one RNG seed, limits raised to 48 h / 1,000,000 calls, so outside the
  standard limits) reached the Hall of Fame at 35,360 tool calls / 58 min / $0.34.

Jev chooses among options code lists; the objective graph, healing/training/HM rules and stuck recovery are
Pokémon-Red-specific code tuned over about 90 iterations. These results are about Jev plus that code.

```bash
# the key is read from TYPESAFE_API_KEY only; load it per command, never store it in the repo
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo --smoke
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-hybrid --smoke
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-battles --smoke
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-assist --smoke
venv/bin/python bench/run.py --mode jev-solo --mock     # offline: MockJev, no network, never a result
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo    # a full 12 h / 20k-call jev-solo run
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
  the last `jev-progress` checkpoint after 45, and on any screen after 500 steps without progress; a menu,
  dialog or prompt screen seen 3 times without progress offers only the options not yet tried there). Jev
  picks every action and answers Nouls: "are we
  stuck?" and, for story events code cannot see (Silph Co. cleared), "is this objective done?" (three
  answers >= 0.8 in a row mark it done).
* **assist** (the run mode of the self-improvement loop): jev-solo's scaffolding plus a safety net. When
  Jev's confidence is below `--fallback-threshold` (0.3), or code detects stuck (on the map: recovery level 2
  or 10 steps without moving; on any menu, dialog or prompt screen: the same screen came back 3 times without
  progress and every option there was tried) or a loop (an option's identical result 3 times in the last 12
  actions; code-forced presses, logged as `(auto)`, do not count, and `press A` on a prompt is never dropped),
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
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-assist --segment after-brock --iteration 1
# analysis: cluster the fallbacks and write the Opus prompt (dry run); --call sends it to claude-opus-5-5
venv/bin/python bench/improve.py analyze bench/runs/<run_id> --iteration 1            # -> bench/iterations/it1/{clusters.json,prompt.md}
venv/bin/python bench/improve.py analyze bench/runs/<run_id> --iteration 1 --call     # -> summary.md, proposal.patch, analysis.json (cost)
# apply on a new branch jev-iter-2 (refuses main; nothing committed), review, run the tests, rerun the same segment
venv/bin/python bench/improve.py apply --iteration 1
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-assist --segment after-brock --iteration 2
venv/bin/python bench/improve.py compare --segment after-brock                       # fallbacks/1k, badges, time, cost per iteration
# final exam once fallbacks are ~0: strict solo, no LLM, stuck = fail
TYPESAFE_API_KEY="$(cat ~/.typesafe-api-key)" venv/bin/python bench/run.py --mode jev-solo --segment after-brock --iteration 2
```

Segments (`bench/segments.json`): `power-on` → Boulder Badge, `after-brock` → Cerulean City, `mt-moon` (1F entrance) → Cerulean City,
`cerulean` → Cascade Badge, `viridian-gym` → Earth Badge. The states are local files (gitignored); a run
ends with exit reason `segment_goal` when the goal milestone appears. The Opus prompt contains the
largest clusters (trigger × graph node × map × situation) with sample events and the full source of
`bench/jev_solo.py`, `bench/jev.py` and `bench/jev_agent.py`, and asks for a per-cluster diagnosis
(including "Jev cannot do this" when that is the answer) and one unified diff. `RESULTS.md` shows a
self-improvement table per segment (iteration, steps, fallbacks, per 1k, goal reached, badges, hours,
Jev / Haiku / Opus / total cost); `run.py --iteration N` records the cost of the analysis in
`bench/iterations/it<N-1>/analysis.json`. Multi-hour runs and Opus analysis batches need Bijan's go.

Where Jev alone cannot decide, and what code does instead: Jev never produces arguments, so every
destination, move and menu path is enumerated by code; which ladder or door leads on is a map-knowledge question
(by default from what Jev has explored, `--map-source learned`; `rom` answers it from the ROM for comparison), offered as a 'follow the map
route' option that Jev still has to pick; arithmetic (HP fractions, level targets, damage)
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
