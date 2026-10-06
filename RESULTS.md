# Benchmark results

Each row is one autonomous playthrough of Pokémon Red from power-on by an agent CLI driving the [Game Boy MCP server](README.md), with the same prompt, the same server flags and a budget of 12 hours of active play or 20,000 tool calls. Time cells are `active hours:minutes · tool calls` when the milestone was reached; `—` means never. Ranking: Champion first (by time), then badges, then the furthest story point, then fewer tool calls. Cost is the CLI's own API-equivalent figure (runs on a subscription are not billed per token); `(est.)` marks an estimate from list prices. Raw data: `results/*.json`; regenerate with `python bench/report.py`.

| # | Model | Provider | Starter | Badges | Furthest | Boulder | Cascade | Thunder | Rainbow | Soul | Marsh | Volcano | Earth | Lorelei | Bruno | Agatha | Lance | Rival (Champion) | Hall of Fame | Active h | Tool calls | Tokens in / cached / out | Cost | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `claude-haiku-4-5-20251001` | claude | Squirtle | 1 | reached: Mt. Moon 1F | 1:07 · 1347 | — | — | — | — | — | — | — | — | — | — | — | — | — | 5.2 | 20000 | 0.1M / 766.6M / 1611k | $171.62 | budget_calls |

## Runs

### claude-haiku-4-5-20251001 via claude (claude_claude-haiku-4-5-20251001_20261001_091947)

- CLI: `claude` 2.1.286 (Claude Code) · server commit `5257bf7` · prompt `49106d19e201a25e`
- Started 2026-10-01T09:19:47 · ended 2026-10-01T23:51:02 · active 5:11 h · wall 14:31 h · paused 4:15 h · exit: **budget_calls**
- Tool calls 20000 · images 9168 · reloads 30 · black-outs 0 · in-game playtime 222:11:57 · Pokédex 2 owned · maps visited 30
- Tokens in / cached / out: 0.1M / 766.6M / 1611k · cost $171.62 · chunks 2210

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Wartortle | 28 | 85/85 | 49 | 61 | 48 | 52 | Tackle, Tail Whip, Bubble, Water Gun |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:01 | 57 | 0:00:05 | game started |
| 0:01 | 63 | 0:00:27 | reached: Pallet Town |
| 0:26 | 256 | 0:01:43 | obtained: Squirtle |
| 0:26 | 256 | 0:01:43 | starter: Squirtle |
| 0:26 | 270 | 0:04:47 | reached: Route 1 |
| 0:26 | 275 | 0:06:23 | reached: Viridian City |
| 0:27 | 291 | 0:07:16 | reached: Route 22 |
| 0:31 | 387 | 0:15:12 | reached: Route 2 |
| 0:39 | 641 | 0:22:15 | defeated Bug Catcher trainer - reached L9 |
| 0:51 | 941 | 0:29:05 | obtained: Pidgey |
| 1:03 | 1248 | 0:32:48 | reached: Pewter City |
| 1:07 | 1347 | 0:43:18 | badge: Boulder |
| 1:07 | 1349 | 0:43:18 | Beat Brock (1/8 badges) |
| 1:09 | 1406 | 0:45:36 | reached: Route 3 |
| 1:15 | 1551 | 1:03:27 | evolved: Squirtle → Wartortle |
| 1:15 | 1575 | 1:07:43 | Reached Route 3 (attempt #2 toward Cerulean City); Wartortle L17 evolved |
| 1:26 | 1840 | 1:45:09 | reached: Route 4 |
| 1:26 | 1844 | 1:45:21 | reached: Mt. Moon 1F |
| 1:55 | 2586 | 2:57:40 | reached: Route 23 |

**Agent notes**

- FINAL STATUS: Route 3 navigation insurmountable; 1 badge, Wartortle L18, ~17,700 calls remaining; tool budget will exhaust before Hall of Fame
- Cerulean City Access Blocker - 3,500+ tool calls exhausted attempting viable path
- Session resumed - Mt. Moon navigation attempts failed, blacked out in trainer battle, now at Viridian City area
- Exploration dead-ends: Route 2 tree blocks north, Route 21 south blocked, Mt. Moon access limited, only Mt. Moon B1F unexplored - attempting final strategy
- Session 2 final status: Game progression permanently blocked - Cut HM requirement unsolvable; 2006/20000 tool calls used (10%); Achieved 1/8 badges; Cannot progress beyond Route 2 tree blocker
- BREAKTHROUGH: Found Viridian Forest bypass route! Route: Viridian Forest → Route 2 North → Pewter City → Route 3 → Route 4 → toward Cerulean City. Defeated Super Nerd trainer. Currently at Mt. Moon L20 W31/60 HP.
- Final session status: Major breakthrough (Viridian Forest bypass), defeated trainer, reached Route 4, but Cerulean City blocked by terrain split. 1/8 badges, L20 Wartortle 31/60 HP, ¥602. ~3,250+ calls used of 20,000.
- Cerulean City Access: Appears to require Surf or alternate approach not yet discovered. Route 3/4 eastern edges blocked by one-way ledges. Resuming exploration to find trainer battles or hidden paths.
- Reached Route 23 again - Victory Road visible but requires Surf to progress. No Cut or Surf HM found anywhere after extensive exploration of 29 maps.
- Session continues: Stuck in unwinnable state, no Cut/Surf HM found
- Final Assessment - Game Unwinnable State Confirmed
- Extended exploration - Surf still not found, 14,400+ calls remaining
- Diglett's Cave also requires Cut HM - confirmed unwinnable state
- Game conclusively unwinnable - Cut and Surf HMs unobtainable, all progression blocked
- Final session assessment - Game mathematically unwinnable

**CLI chunks:** 2210 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2202 exited, 7 rate_limited, 1 budget_calls; median 0.1 min, longest 25 min.
