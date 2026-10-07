# Benchmark results

Each row is one autonomous playthrough of Pokémon Red from power-on by an agent CLI driving the [Game Boy MCP server](README.md), with the same prompt, the same server flags and a budget of 12 hours of active play or 20,000 tool calls. Time cells are `active hours:minutes · tool calls` when the milestone was reached; `—` means never. Ranking: Champion first (by time), then badges, then the furthest story point, then fewer tool calls. Cost is the CLI's own API-equivalent figure (runs on a subscription are not billed per token); `(est.)` marks an estimate from list prices. Raw data: `results/*.json`; regenerate with `python bench/report.py`.

| # | Model | Provider | Starter | Badges | Furthest | Boulder | Cascade | Thunder | Rainbow | Soul | Marsh | Volcano | Earth | Lorelei | Bruno | Agatha | Lance | Rival (Champion) | Hall of Fame | Active h | Tool calls | Tokens uncached in / cache reads / out | Cost | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `gpt-5.6-sol` | codex | Bulbasaur | 8 | defeated: Lance | 0:11 · 178 | 0:19 · 315 | 0:42 · 610 | 1:08 · 947 | 2:33 · 17998 | 3:22 · 18669 | 3:58 · 19128 | 4:03 · 19196 | 4:24 · 19564 | 4:24 · 19577 | 4:43 · 19846 | 4:44 · 19857 | — | — | 4.9 | 20000 | 2.3M / 419.1M / 376k | — | budget_calls |
| 2 | `claude-haiku-4-5-20251001` | claude | Squirtle | 1 | reached: Mt. Moon 1F | 1:07 · 1347 | — | — | — | — | — | — | — | — | — | — | — | — | — | 5.2 | 20000 | 0.1M / 766.6M / 1611k | $171.62 | budget_calls |

## Runs

### gpt-5.6-sol via codex (codex_gpt-5.6-sol_20261006_135640)

- CLI: `codex` codex-cli 0.156.1 · server commit `9f87da0` · prompt `49106d19e201a25e`
- Started 2026-10-06T13:56:40 · ended 2026-10-07T00:42:05 · active 4:54 h · wall 10:45 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 20000 · images 7194 · reloads 7125 · black-outs 0 · in-game playtime 10:53:03 · Pokédex 6 owned · maps visited 144
- Tokens uncached in / cache reads / out: 2.3M / 419.1M / 376k (from codex session rollouts) · cost — · chunks 17 · save/load scumming: 7127 reloads

**Corrections:** 2026-10-06 20:50: chunks 2-13 (14:57-20:45) made no tool calls because Codex could not resume its thread (remote compaction failed: 'workspace routing discovery failed'); the server clock had kept running. Active time reset to 3700 s (chunk 1 + 2 calls); the run continues in a fresh Codex session with the continue prompt.

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Venusaur | 67 | 225/225 | 151 | 151 | 140 | 166 | Cut, Double Team, Sleep Powder, Mega Drain |
| 2 | Diglett | 22 | 43/43 | 33 | 23 | 51 | 32 | Scratch, Growl, Dig |
| 3 | Rhyhorn | 28 | 87/87 | 55 | 63 | 20 | 27 | Horn Attack, Strength, Dig |
| 4 | Poliwag | 15 | 38/38 | 21 | 21 | 32 | 17 | Bubble, Surf, Blizzard |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:01 | 14 | 0:00:03 | game started |
| 0:01 | 17 | 0:00:13 | reached: Pallet Town |
| 0:01 | 30 | 0:01:37 | obtained: Bulbasaur |
| 0:01 | 30 | 0:01:37 | starter: Bulbasaur |
| 0:02 | 39 | 0:04:29 | reached: Route 1 |
| 0:02 | 40 | 0:04:46 | reached: Viridian City |
| 0:04 | 75 | 0:10:22 | reached: Route 2 |
| 0:07 | 105 | 0:22:06 | reached: Pewter City |
| 0:11 | 178 | 0:42:25 | badge: Boulder |
| 0:11 | 186 | 0:43:23 | reached: Route 3 |
| 0:11 | 192 | 0:47:24 | evolved: Bulbasaur → Ivysaur |
| 0:12 | 207 | 0:55:37 | reached: Route 4 |
| 0:13 | 213 | 0:56:09 | reached: Mt. Moon 1F |
| 0:17 | 291 | 1:29:29 | reached: Cerulean City |
| 0:19 | 315 | 1:34:36 | badge: Cascade |
| 0:20 | 335 | 1:39:23 | reached: Route 24 |
| 0:22 | 363 | 1:49:42 | reached: Route 25 |
| 0:33 | 438 | 2:01:28 | reached: Route 5 |
| 0:33 | 443 | 2:02:00 | reached: Route 6 |
| 0:35 | 487 | 2:17:11 | reached: Vermilion City |
| 0:36 | 499 | 2:18:12 | reached: Vermilion Dock |
| 0:38 | 530 | 2:28:21 | reached: Route 11 |
| 0:39 | 540 | 2:29:47 | obtained: Diglett |
| 0:42 | 610 | 2:40:30 | badge: Thunder |
| 0:43 | 636 | 2:43:15 | reached: Route 9 |
| 0:44 | 654 | 2:48:41 | reached: Route 10 |
| 0:45 | 660 | 2:49:23 | reached: Rock Tunnel 1F |
| 0:45 | 668 | 2:52:51 | reached: Rock Tunnel B1F |
| 0:47 | 696 | 3:05:14 | evolved: Ivysaur → Venusaur |
| 1:02 | 835 | 3:44:33 | reached: Lavender Town |
| 1:04 | 867 | 3:45:44 | reached: Route 8 |
| 1:05 | 881 | 3:50:17 | reached: Route 7 |
| 1:05 | 882 | 3:50:25 | reached: Celadon City |
| 1:08 | 947 | 4:06:26 | badge: Rainbow |
| 1:09 | 967 | 4:09:07 | reached: Rocket Hideout B1F |
| 1:48 | 17377 | 4:28:58 | reached: Pokémon Tower 1F |
| 1:54 | 17463 | 4:49:04 | reached: Route 12 |
| 1:56 | 17487 | 4:56:14 | reached: Route 13 |
| 1:58 | 17510 | 5:03:01 | reached: Route 14 |
| 2:17 | 17793 | 5:07:59 | reached: Route 16 |
| 2:18 | 17801 | 5:10:18 | reached: Route 17 |
| 2:19 | 17814 | 5:14:26 | reached: Route 18 |
| 2:19 | 17817 | 5:14:43 | reached: Fuchsia City |
| 2:19 | 17823 | 5:15:40 | reached: Safari Zone Gate |
| 2:20 | 17838 | 5:16:34 | reached: Safari Zone Center |
| 2:20 | 17840 | 5:16:58 | reached: Safari Zone East |
| 2:20 | 17841 | 5:17:27 | reached: Safari Zone North |
| 2:20 | 17842 | 5:17:57 | reached: Safari Zone West |
| 2:25 | 17894 | 5:23:55 | obtained: Rhyhorn |
| 2:26 | 17908 | 5:25:58 | reached: Route 19 |
| 2:27 | 17918 | 5:28:32 | obtained: Poliwag |
| 2:33 | 17998 | 5:48:20 | badge: Soul |
| 2:41 | 18090 | 6:01:57 | reached: Route 15 |
| 3:04 | 18347 | 7:02:24 | reached: Saffron City |
| 3:04 | 18348 | 7:02:33 | reached: Silph Co. 1F |
| 3:22 | 18669 | 7:37:08 | badge: Marsh |
| 3:25 | 18715 | 7:43:40 | reached: Route 21 |
| 3:26 | 18726 | 7:46:00 | reached: Cinnabar Island |
| 3:27 | 18734 | 7:46:44 | reached: Pokémon Mansion 1F |
| 3:58 | 19128 | 8:25:03 | badge: Volcano |
| 4:03 | 19196 | 8:41:41 | badge: Earth |
| 4:04 | 19212 | 8:44:28 | reached: Route 22 |
| 4:06 | 19237 | 8:50:28 | reached: Route 23 |
| 4:08 | 19261 | 8:52:38 | reached: Victory Road 1F |
| 4:16 | 19379 | 9:00:54 | reached: Victory Road 2F |
| 4:16 | 19395 | 9:02:30 | reached: Victory Road 3F |
| 4:20 | 19510 | 9:13:46 | reached: Indigo Plateau |
| 4:20 | 19511 | 9:13:52 | reached: Indigo Plateau Lobby |
| 4:23 | 19551 | 9:16:59 | reached: Lorelei's Room |
| 4:24 | 19564 | 9:20:02 | defeated: Lorelei |
| 4:24 | 19567 | 9:20:11 | reached: Bruno's Room |
| 4:24 | 19577 | 9:23:02 | defeated: Bruno |
| 4:25 | 19579 | 9:23:09 | reached: Agatha's Room |
| 4:43 | 19846 | 10:25:08 | defeated: Agatha |
| 4:43 | 19849 | 10:25:54 | reached: Lance's Room |
| 4:44 | 19857 | 10:30:48 | defeated: Lance |
| 4:45 | 19861 | 10:32:04 | reached: Champion's Room |

**Agent notes**

- Beat Brock with Bulbasaur L15; next east through Route 3 to Mt. Moon/Cerulean.
- Beat Misty; next Route 24/25 to Bill for S.S. Ticket, then south to Vermilion.
- Beat Lt. Surge; Diglett L22 swept. Next return Cerulean, Cut east tree to Route 9, cross Rock Tunnel to Lavender/Celadon.

**CLI chunks:** 17 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 10 stall, 4 rotate, 1 cli_error, 1 exited, 1 budget_calls; median 29.4 min, longest 63 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-06T13:56:40 | 63 | rotate | 803 | 0.0M / 0.0M / 0k |
| 2 | 2026-10-06T14:59:37 | 15 | stall | 0 | 0.0M / 0.0M / 0k |
| 3 | 2026-10-06T15:14:40 | 52 | stall | 2 | 0.0M / 0.0M / 0k |
| 4 | 2026-10-06T16:22:55 | 16 | stall | 0 | 0.0M / 0.0M / 0k |
| 5 | 2026-10-06T16:38:56 | 28 | stall | 0 | 0.0M / 0.0M / 0k |
| 6 | 2026-10-06T17:06:56 | 16 | stall | 0 | 0.0M / 0.0M / 0k |
| 7 | 2026-10-06T17:37:42 | 29 | stall | 0 | 0.0M / 0.0M / 0k |
| 8 | 2026-10-06T18:07:07 | 36 | stall | 0 | 0.0M / 0.0M / 0k |
| 9 | 2026-10-06T18:42:54 | 28 | stall | 0 | 0.0M / 0.0M / 0k |
| 10 | 2026-10-06T19:26:14 | 45 | stall | 0 | 0.0M / 0.0M / 0k |
| 11 | 2026-10-06T20:11:32 | 17 | stall | 0 | 0.0M / 0.0M / 0k |
| 12 | 2026-10-06T20:28:47 | 0 | cli_error | 0 | 0.0M / 0.0M / 0k |
| 13 | 2026-10-06T20:42:37 | 3 | exited | 11 | 0.0M / 0.0M / 0k |
| 14 | 2026-10-06T20:48:00 | 60 | rotate | 16742 | 0.0M / 0.0M / 0k |
| 15 | 2026-10-06T21:48:06 | 60 | rotate | 733 | 0.0M / 0.0M / 0k |
| 16 | 2026-10-06T22:48:14 | 60 | rotate | 880 | 0.0M / 0.0M / 0k |
| 17 | 2026-10-06T23:48:21 | 54 | budget_calls | 839 | 0.0M / 0.0M / 0k |

</details>

### claude-haiku-4-5-20251001 via claude (claude_claude-haiku-4-5-20251001_20261001_091947)

- CLI: `claude` 2.1.286 (Claude Code) · server commit `5257bf7` · prompt `49106d19e201a25e`
- Started 2026-10-01T09:19:47 · ended 2026-10-01T23:51:02 · active 5:11 h · wall 14:31 h · paused 4:15 h · exit: **budget_calls**
- Tool calls 20000 · images 9168 · reloads 30 · black-outs 0 · in-game playtime 222:11:57 · Pokédex 2 owned · maps visited 30
- Tokens uncached in / cache reads / out: 0.1M / 766.6M / 1611k · cost $171.62 · chunks 2210

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
