# Benchmark results

Each row is one autonomous playthrough of Pokémon Red from power-on by an agent CLI driving the [Game Boy MCP server](README.md), with the same prompt, the same server flags and a budget of 12 hours of active play or 20,000 tool calls. Time cells are `active hours:minutes · tool calls` when the milestone was reached; `—` means never. Ranking: Champion first (by time), then badges, then the furthest story point, then fewer tool calls. Cost is the CLI's own API-equivalent figure (runs on a subscription are not billed per token); `(est.)` marks an estimate from list prices. Raw data: `results/*.json`; regenerate with `python bench/report.py`. Each result records the server commit it ran on (`harness.server_commit`): the server has gained features since round one (October 2026), so compare runs made on the same server version.

| # | Model | Provider | Starter | Badges | Furthest | Boulder | Cascade | Thunder | Rainbow | Soul | Marsh | Volcano | Earth | Lorelei | Bruno | Agatha | Lance | Rival (Champion) | Hall of Fame | Active h | Tool calls | Tokens uncached in / cache reads / out | Cost | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `claude-fable-5-1` | claude | Squirtle | 8 | champion defeated (Hall of Fame) | 0:07 · 152 | 0:21 · 460 | 0:42 · 966 | 2:04 · 2336 | 2:00 · 2255 | 2:16 · 2701 | 2:35 · 3013 | 2:51 · 3119 | 4:21 · 3838 | 4:21 · 3852 | 4:21 · 3863 | 4:22 · 3880 | 4:23 · 3901 | 4:23 · 3904 | 4.4 | 3904 | 0.0M / 342.7M / 1135k | $195.78 (est.) | champion |
| 2 | `gpt-5.6-sol` | codex | Bulbasaur | 8 | defeated: Lance | 0:11 · 178 | 0:19 · 315 | 0:42 · 610 | 1:08 · 947 | 2:33 · 17998 | 3:22 · 18669 | 3:58 · 19128 | 4:03 · 19196 | 4:24 · 19564 | 4:24 · 19577 | 4:43 · 19846 | 4:44 · 19857 | — | — | 4.9 | 20000 | 2.3M / 419.1M / 376k | — | budget_calls |
| 3 | `claude-haiku-4-5-20251001` | claude | Squirtle | 1 | reached: Mt. Moon 1F | 1:07 · 1347 | — | — | — | — | — | — | — | — | — | — | — | — | — | 5.2 | 20000 | 0.1M / 766.6M / 1611k | $171.62 | budget_calls |

## Jev track (code-scaffolded, not comparable with the table above)

Jev (TypeSafe's System One model) answers typed questions; it cannot write text or call tools. In these runs code does what an agent CLI does for itself: it reads the server's replies, lists the legal actions as a closed set every step and executes the one Jev picks. **jev-solo uses heavy code scaffolding**: a whole-game objective graph, progress checks, healing/training/HM rules and stuck recovery are written in code, and no LLM is called. Cost is Jev's input tokens ($0.042/MTok, output free) plus any LLM the variant uses.

Variants: **solo**: The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event). **assist**: jev-solo's scaffolding plus a safety net: when Jev's confidence is low or code detects stuck/looping, Claude Haiku picks that one action and a fallback event is logged; fallbacks per 1k steps should trend to 0 across self-improvement iterations (bench/improve.py). **hybrid**: Claude Haiku sets the objective (every N steps, on low Jev confidence, when Jev says stuck, after a badge); code enumerates the actions; Jev picks every action. **scripted**: A short code-side objective list (no rules, no recovery); code enumerates the actions; Jev picks every action. **battles**: The normal Claude Code run (same tools and prompt plus one line), except battle('auto') turns are picked by Jev from the legal moves/switches/items.

### Jev full-game benchmark entries

Jev full-game runs from power-on (jev-solo: no LLM). The label says how each was run. An entry outside the standard limits is not comparable with a capped run.

| Entry | Variant | Badges | Furthest | Hall of Fame | Tool calls | Steps | Active h | Total cost | Exit |
|---|---|---|---|---|---|---|---|---|---|
| standard limits (12 h / 20,000 calls), unassisted, blank atlas, one seed: stopped by the call cap | jev-solo | 5 | reached: Silph Co. 1F | — | 20003 | 6563 | 2.2 | $0.28 | budget_calls |
| unassisted (no interventions), blank atlas, one seed, OUTSIDE the standard 20,000-call cap (no call or time cap); Jev code at 402e35e (the recorded server_commit 69ef71e is that code plus a results commit, since rebased) | jev-solo | 8 | champion defeated (Hall of Fame) | 0:57 · 35360 | 35361 | 11868 | 1.0 | $0.34 | champion |

### All Jev runs (iterations, segments and labelled experiments included)

| # | Variant | Model | Maps | Segment | Badges | Furthest | Hall of Fame | Active h | Tool calls | Jev calls | Fallbacks (/1k steps) | Jev latency p50 / p95 ms | Jev cost | LLM cost | Total cost | Correct | ECE | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game | 8 | champion defeated (Hall of Fame) | 0:57 · 35360 | 1.0 | 35361 | 7173 | — | 151 / 495 | $0.34 | $0.00 | $0.34 | 72% | 0.192 | champion |
| 2 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it91 | 8 | champion defeated (Hall of Fame) | 0:59 · 24714 | 1.0 | 24715 | 6207 | — | 67 / 176 | $0.31 | $0.00 | $0.31 | 71% | 0.167 | champion |
| 3 | jev-solo | `jev-latest` | learned (blank) — experiment — outside the 20k cap | full game | 8 | champion defeated (Hall of Fame) | 2:30 · 53252 | 2.5 | 53253 | 9822 | — | 64 / 134 | $0.45 | $0.00 | $0.45 | 74% | 0.237 | champion |
| 4 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it90 | 8 | reached: Victory Road 1F | — | 1.8 | 27339 | 7320 | — | 68 / 148 | $0.38 | $0.00 | $0.38 | 66% | 0.145 | manual |
| 5 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it88 | 8 | reached: Victory Road 1F | — | 1.3 | 32634 | 8406 | — | 65 / 136 | $0.44 | $0.00 | $0.44 | 65% | 0.156 | manual |
| 6 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | after-sabrina | 6 | reached: Pokémon Mansion 1F | — | 0.0 | 461 | 131 | — | 84 / 315 | $0.01 | $0.00 | $0.01 | 81% | 0.181 | segment_goal |
| 7 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | cinnabar-island | 6 | reached: Pokémon Mansion 1F | — | 0.1 | 1243 | 359 | — | 82 / 307 | $0.02 | $0.00 | $0.02 | 66% | 0.248 | manual |
| 8 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | cinnabar-island | 6 | reached: Pokémon Mansion 1F | — | 0.0 | 1275 | 381 | — | 86 / 332 | $0.02 | $0.00 | $0.02 | 58% | 0.131 | manual |
| 9 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | cinnabar-island | 6 | reached: Pokémon Mansion 1F | — | 0.2 | 1356 | 408 | — | 84 / 207 | $0.02 | $0.00 | $0.02 | 64% | 0.213 | manual |
| 10 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it85 | 6 | reached: Pokémon Mansion 1F | — | 1.1 | 21510 | 5685 | — | 61 / 136 | $0.28 | $0.00 | $0.28 | 71% | 0.185 | manual |
| 11 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it86 | 6 | reached: Pokémon Mansion 1F | — | 1.0 | 28979 | 7317 | — | 61 / 136 | $0.39 | $0.00 | $0.39 | 68% | 0.206 | manual |
| 12 | jev-solo | `jev-latest` | learned (carried atlas) — experiment — outside the 20k cap | full game | 6 | badge: Marsh | — | 2.8 | 22530 | 5885 | — | 76 / 327 | $0.30 | $0.00 | $0.30 | 63% | 0.133 | manual |
| 13 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it75 | 6 | badge: Marsh | — | 5.2 | 51842 | 18428 | — | 112 / 224 | $1.05 | $0.00 | $1.05 | 61% | 0.213 | stuck |
| 14 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | after-sabrina | 6 | reached: Silph Co. 1F | — | 0.1 | 422 | 120 | — | 80 / 333 | $0.01 | $0.00 | $0.01 | 57% | 0.122 | manual |
| 15 | jev-solo | `jev-latest` | learned (carried atlas) — experiment | after-sabrina | 6 | reached: Silph Co. 1F | — | 0.1 | 495 | 149 | — | 87 / 247 | $0.01 | $0.00 | $0.01 | 54% | 0.091 | manual |
| 16 | jev-solo | `jev-latest` | learned (blank) — experiment | after-sabrina | 6 | reached: Silph Co. 1F | — | 0.0 | 2612 | 639 | — | 83 / 168 | $0.04 | $0.00 | $0.04 | 58% | 0.141 | manual |
| 17 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it89 | 5 | reached: Silph Co. 1F | — | 1.1 | 19923 | 5260 | — | 67 / 140 | $0.27 | $0.00 | $0.27 | 65% | 0.138 | manual |
| 18 | jev-solo | `jev-latest` | learned (blank) | full game | 5 | reached: Silph Co. 1F | — | 2.2 | 20003 | 5391 | — | 76 / 339 | $0.28 | $0.00 | $0.28 | 62% | 0.126 | budget_calls |
| 19 | jev-solo | `jev-latest` | learned (carried atlas) — experiment — outside the 20k cap | full game | 5 | reached: Silph Co. 1F | — | 2.5 | 20911 | 5587 | — | 76 / 335 | $0.29 | $0.00 | $0.29 | 62% | 0.128 | manual |
| 20 | jev-solo | `jev-latest` | learned (carried atlas) — experiment — outside the 20k cap | full game | 5 | reached: Silph Co. 1F | — | 2.6 | 21570 | 5704 | — | 76 / 331 | $0.30 | $0.00 | $0.30 | 62% | 0.130 | manual |
| 21 | jev-solo | `jev-latest` | learned (carried atlas) — experiment — outside the 20k cap | full game | 5 | reached: Silph Co. 1F | — | 2.6 | 21572 | 5672 | — | 76 / 332 | $0.29 | $0.00 | $0.29 | 62% | 0.129 | manual |
| 22 | jev-solo | `jev-latest` | learned (carried atlas) — experiment — outside the 20k cap | full game | 5 | reached: Silph Co. 1F | — | 2.6 | 23003 | 5925 | — | 75 / 326 | $0.31 | $0.00 | $0.31 | 63% | 0.133 | budget_calls |
| 23 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it64 | 5 | reached: Silph Co. 1F | — | 1.3 | 28966 | 9155 | — | 81 / 297 | $0.46 | $0.00 | $0.46 | 63% | 0.188 | stuck |
| 24 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it72 | 5 | reached: Silph Co. 1F | — | 0.8 | 33433 | 9801 | — | 76 / 143 | $0.50 | $0.00 | $0.50 | 59% | 0.159 | stuck |
| 25 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it71 | 5 | reached: Silph Co. 1F | — | 4.6 | 33839 | 10774 | — | 78 / 148 | $0.60 | $0.00 | $0.60 | 55% | 0.170 | stuck |
| 26 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it62 | 5 | reached: Silph Co. 1F | — | 1.9 | 38929 | 12306 | — | 80 / 307 | $0.65 | $0.00 | $0.65 | 57% | 0.185 | stuck |
| 27 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it76 | 5 | reached: Silph Co. 1F | — | 2.2 | 39115 | 9528 | — | 80 / 230 | $0.49 | $0.00 | $0.49 | 64% | 0.156 | stuck |
| 28 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it61 | 5 | reached: Silph Co. 1F | — | 1.7 | 39508 | 12277 | — | 77 / 299 | $0.62 | $0.00 | $0.62 | 57% | 0.164 | stuck |
| 29 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it73 | 5 | reached: Silph Co. 1F | — | 1.8 | 45011 | 14516 | — | 80 / 148 | $0.74 | $0.00 | $0.74 | 80% | 0.307 | stuck |
| 30 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it87 | 5 | badge: Soul | — | 0.6 | 19315 | 5072 | — | 60 / 133 | $0.25 | $0.00 | $0.25 | 65% | 0.140 | manual |
| 31 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it63 | 5 | badge: Soul | — | 1.5 | 33039 | 10142 | — | 81 / 298 | $0.53 | $0.00 | $0.53 | 62% | 0.178 | stuck |
| 32 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it59 | 5 | badge: Soul | — | 1.9 | 52493 | 15750 | — | 74 / 144 | $0.80 | $0.00 | $0.80 | 57% | 0.160 | stuck |
| 33 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it84 | 4 | reached: Pokémon Tower 1F | — | 0.5 | 17626 | 4405 | — | 60 / 158 | $0.22 | $0.00 | $0.22 | 66% | 0.162 | manual |
| 34 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it80 | 4 | reached: Pokémon Tower 1F | — | 0.6 | 20968 | 5499 | — | 63 / 284 | $0.28 | $0.00 | $0.28 | 64% | 0.156 | manual |
| 35 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it77 | 4 | reached: Pokémon Tower 1F | — | 1.0 | 21644 | 6615 | — | 69 / 169 | $0.33 | $0.00 | $0.33 | 65% | 0.187 | manual |
| 36 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it52 | 4 | reached: Pokémon Tower 1F | — | 0.8 | 23361 | 7192 | — | 79 / 176 | $0.39 | $0.00 | $0.39 | 62% | 0.152 | stuck |
| 37 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it81 | 4 | reached: Pokémon Tower 1F | — | 1.0 | 23978 | 6890 | — | 62 / 168 | $0.36 | $0.00 | $0.36 | 65% | 0.158 | manual |
| 38 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it70 | 4 | reached: Pokémon Tower 1F | — | 1.9 | 26198 | 7780 | — | 79 / 157 | $0.40 | $0.00 | $0.40 | 58% | 0.135 | stuck |
| 39 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it56 | 4 | reached: Pokémon Tower 1F | — | 1.4 | 27137 | 7877 | — | 77 / 163 | $0.41 | $0.00 | $0.41 | 52% | 0.123 | stuck |
| 40 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it74 | 4 | reached: Pokémon Tower 1F | — | 0.6 | 27164 | 7467 | — | 85 / 154 | $0.42 | $0.00 | $0.42 | 62% | 0.147 | stuck |
| 41 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it67 | 4 | reached: Pokémon Tower 1F | — | 1.8 | 27671 | 8861 | — | 77 / 146 | $0.51 | $0.00 | $0.51 | 56% | 0.175 | stuck |
| 42 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it49 | 4 | reached: Pokémon Tower 1F | — | 1.2 | 28012 | 8450 | — | 81 / 242 | $0.44 | $0.00 | $0.44 | 50% | 0.131 | stuck |
| 43 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it65 | 4 | reached: Pokémon Tower 1F | — | 2.9 | 28722 | 9723 | — | 83 / 196 | $0.58 | $0.00 | $0.58 | 56% | 0.204 | stuck |
| 44 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it47 | 4 | reached: Pokémon Tower 1F | — | 1.4 | 30552 | 9967 | — | 83 / 164 | $0.51 | $0.00 | $0.51 | 51% | 0.102 | stuck |
| 45 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it55 | 4 | reached: Pokémon Tower 1F | — | 1.1 | 31665 | 9582 | — | 77 / 206 | $0.53 | $0.00 | $0.53 | 59% | 0.181 | stuck |
| 46 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it54 | 4 | reached: Pokémon Tower 1F | — | 1.7 | 32849 | 10814 | — | 82 / 239 | $0.60 | $0.00 | $0.60 | 63% | 0.256 | stuck |
| 47 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it48 | 4 | reached: Pokémon Tower 1F | — | 1.9 | 33501 | 11032 | — | 81 / 180 | $0.56 | $0.00 | $0.56 | 52% | 0.141 | stuck |
| 48 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it68 | 4 | reached: Pokémon Tower 1F | — | 3.2 | 40510 | 14343 | — | 76 / 149 | $0.75 | $0.00 | $0.75 | 55% | 0.181 | stuck |
| 49 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it57 | 4 | reached: Pokémon Tower 1F | — | 1.0 | 41250 | 11417 | — | 74 / 149 | $0.57 | $0.00 | $0.57 | 62% | 0.182 | stuck |
| 50 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it53 | 3 | reached: Pokémon Tower 1F | — | 0.7 | 21789 | 5869 | — | 77 / 211 | $0.28 | $0.00 | $0.28 | 63% | 0.174 | stuck |
| 51 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it60 | 3 | reached: Pokémon Tower 1F | — | 0.5 | 25114 | 6393 | — | 77 / 188 | $0.35 | $0.00 | $0.35 | 57% | 0.141 | stuck |
| 52 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it44 | 3 | reached: Pokémon Tower 1F | — | 1.1 | 33081 | 8968 | — | 80 / 161 | $0.50 | $0.00 | $0.50 | 53% | 0.160 | stuck |
| 53 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it82 | 3 | reached: Rock Tunnel 1F | — | 0.4 | 17340 | 4758 | — | 60 / 176 | $0.23 | $0.00 | $0.23 | 63% | 0.185 | manual |
| 54 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it78 | 3 | reached: Rock Tunnel 1F | — | 0.8 | 19137 | 5315 | — | 70 / 201 | $0.26 | $0.00 | $0.26 | 67% | 0.204 | manual |
| 55 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it79 | 3 | reached: Rock Tunnel 1F | — | 0.5 | 20441 | 5365 | — | 65 / 192 | $0.27 | $0.00 | $0.27 | 65% | 0.171 | manual |
| 56 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it58 | 3 | reached: Rock Tunnel 1F | — | 1.5 | 28016 | 8594 | — | 76 / 151 | $0.45 | $0.00 | $0.45 | 67% | 0.248 | stuck |
| 57 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it51 | 3 | reached: Rock Tunnel 1F | — | 1.6 | 28166 | 8434 | — | 80 / 178 | $0.43 | $0.00 | $0.43 | 69% | 0.241 | stuck |
| 58 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it43 | 3 | badge: Thunder | — | 0.8 | 16900 | 5129 | — | 82 / 310 | $0.24 | $0.00 | $0.24 | 64% | 0.188 | stuck |
| 59 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it41 | 2 | reached: Rock Tunnel 1F | — | 2.2 | 32543 | 10886 | — | 78 / 167 | $0.54 | $0.00 | $0.54 | 62% | 0.240 | stuck |
| 60 | jev-solo | `jev-latest` | learned (blank) | bills-house · it35 | 2 | reached: Vermilion City | — | 0.0 | 696 | 183 | — | 74 / 161 | $0.01 | $0.00 | $0.01 | 60% | 0.111 | segment_goal |
| 61 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it42 | 2 | reached: Vermilion City | — | 0.3 | 17731 | 4545 | — | 80 / 318 | $0.25 | $0.00 | $0.25 | 51% | 0.205 | stuck |
| 62 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it40 | 2 | reached: Vermilion City | — | 1.1 | 19552 | 6036 | — | 80 / 147 | $0.30 | $0.00 | $0.30 | 53% | 0.161 | stuck |
| 63 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it39 | 2 | reached: Vermilion City | — | 0.3 | 19987 | 4925 | — | 79 / 148 | $0.27 | $0.00 | $0.27 | 63% | 0.129 | stuck |
| 64 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it45 | 2 | reached: Vermilion City | — | 1.0 | 21187 | 6805 | — | 81 / 165 | $0.33 | $0.00 | $0.33 | 64% | 0.218 | stuck |
| 65 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it46 | 2 | reached: Vermilion City | — | 0.3 | 24548 | 6162 | — | 84 / 165 | $0.36 | $0.00 | $0.36 | 53% | 0.201 | stuck |
| 66 | jev-solo | `jev-latest` | learned (blank) | cerulean · it21 | 2 | badge: Cascade | — | 0.0 | 3837 | 859 | — | 85 / 181 | $0.04 | $0.00 | $0.04 | 70% | 0.117 | segment_goal |
| 67 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it24 | 2 | badge: Cascade | — | 0.2 | 16647 | 4250 | — | 80 / 211 | $0.23 | $0.00 | $0.23 | 47% | 0.182 | stuck |
| 68 | jev-solo | `jev-latest` | learned (blank) | bills-house · it31 | 2 | reached: Cerulean City | — | 0.0 | 4362 | 37 | — | 97 / 338 | $0.00 | $0.00 | $0.00 | 57% | 0.207 | budget_time |
| 69 | jev-solo | `jev-latest` | learned (blank) | bills-house · it34 | 2 | reached: Cerulean City | — | 0.1 | 4483 | 1552 | — | 76 / 148 | $0.08 | $0.00 | $0.08 | 40% | 0.158 | stuck |
| 70 | jev-solo | `jev-latest` | learned (blank) | bills-house · it32 | 2 | reached: Cerulean City | — | 0.1 | 7165 | 2126 | — | 81 / 172 | $0.12 | $0.00 | $0.12 | 33% | 0.157 | stuck |
| 71 | jev-solo | `jev-latest` | learned (blank) | bills-house · it33 | 2 | reached: Cerulean City | — | 0.1 | 7656 | 2211 | — | 82 / 190 | $0.13 | $0.00 | $0.13 | 27% | 0.183 | stuck |
| 72 | jev-solo | `jev-latest` | learned (blank) | bills-house · it28 | 2 | reached: Cerulean City | — | 0.1 | 7995 | 2251 | — | 80 / 171 | $0.14 | $0.00 | $0.14 | 53% | 0.197 | stuck |
| 73 | jev-solo | `jev-latest` | learned (blank) | bills-house · it30 | 2 | reached: Cerulean City | — | 0.1 | 8876 | 2676 | — | 82 / 236 | $0.14 | $0.00 | $0.14 | 36% | 0.112 | stuck |
| 74 | jev-solo | `jev-latest` | learned (blank) | bills-house · it25 | 2 | reached: Cerulean City | — | 0.1 | 9489 | 2707 | — | 80 / 161 | $0.17 | $0.00 | $0.17 | 50% | 0.190 | stuck |
| 75 | jev-solo | `jev-latest` | learned (blank) | bills-house · it29 | 2 | reached: Cerulean City | — | 0.2 | 15003 | 4513 | — | 83 / 188 | $0.25 | $0.00 | $0.25 | 34% | 0.137 | budget_calls |
| 76 | jev-solo | `jev-latest` | learned (blank) | bills-house · it26 | 2 | game started | — | 0.1 | 4588 | 1982 | — | 81 / 191 | $0.12 | $0.00 | $0.12 | 61% | 0.324 | stuck |
| 77 | jev-solo | `jev-latest` | learned (blank) | bills-house · it27 | 2 | game started | — | 0.1 | 5791 | 1912 | — | 84 / 206 | $0.11 | $0.00 | $0.11 | 39% | 0.170 | stuck |
| 78 | jev-solo | `jev-latest` | rom | mt-moon · it8 | 1 | reached: Cerulean City | — | 0.0 | 139 | 50 | — | 106 / 198 | $0.00 | $0.00 | $0.00 | 88% | 0.171 | segment_goal |
| 79 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it11 | 1 | reached: Cerulean City | — | 0.0 | 306 | 98 | — | 74 / 159 | $0.00 | $0.00 | $0.00 | 76% | 0.197 | segment_goal |
| 80 | jev-solo | `jev-latest` | learned (carried atlas) | mt-moon · it9 | 1 | reached: Cerulean City | — | 0.0 | 2109 | 584 | — | 77 / 146 | $0.03 | $0.00 | $0.03 | 81% | 0.331 | segment_goal |
| 81 | jev-solo | `jev-latest` | learned (blank) | cerulean · it17 | 1 | reached: Cerulean City | — | 0.1 | 5984 | 2721 | — | 83 / 178 | $0.14 | $0.00 | $0.14 | 51% | 0.186 | stuck |
| 82 | jev-solo | `jev-latest` | learned (blank) | cerulean · it14 | 1 | reached: Cerulean City | — | 0.1 | 6214 | 2658 | — | 84 / 167 | $0.14 | $0.00 | $0.14 | 57% | 0.289 | stuck |
| 83 | jev-solo | `jev-latest` | learned (blank) | cerulean · it12 | 1 | reached: Cerulean City | — | 0.1 | 6561 | 2677 | — | 79 / 150 | $0.14 | $0.00 | $0.14 | 61% | 0.302 | stuck |
| 84 | jev-solo | `jev-latest` | learned (blank) | cerulean · it19 | 1 | reached: Cerulean City | — | 0.1 | 7557 | 1999 | — | 87 / 175 | $0.15 | $0.00 | $0.15 | 13% | 0.601 | stuck |
| 85 | jev-solo | `jev-latest` | learned (blank) | cerulean · it15 | 1 | reached: Cerulean City | — | 0.1 | 7643 | 2023 | — | 78 / 138 | $0.11 | $0.00 | $0.11 | 62% | 0.283 | stuck |
| 86 | jev-solo | `jev-latest` | learned (blank) | cerulean · it13 | 1 | reached: Cerulean City | — | 0.1 | 8000 | 2845 | — | 85 / 157 | $0.15 | $0.00 | $0.15 | 64% | 0.295 | budget_calls |
| 87 | jev-solo | `jev-latest` | learned (blank) | cerulean · it18 | 1 | reached: Cerulean City | — | 0.1 | 8128 | 2540 | — | 80 / 155 | $0.13 | $0.00 | $0.13 | 75% | 0.447 | stuck |
| 88 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it38 | 1 | reached: Cerulean City | — | 0.2 | 11821 | 3352 | — | 81 / 162 | $0.21 | $0.00 | $0.21 | 59% | 0.176 | stuck |
| 89 | jev-solo | `jev-latest` | learned (blank) | cerulean · it16 | 1 | reached: Cerulean City | — | 0.1 | 12000 | 2099 | — | 85 / 174 | $0.11 | $0.00 | $0.11 | 55% | 0.185 | budget_calls |
| 90 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it37 | 1 | reached: Cerulean City | — | 0.2 | 13115 | 3577 | — | 75 / 145 | $0.22 | $0.00 | $0.22 | 62% | 0.193 | stuck |
| 91 | jev-solo | `jev-latest` | learned (blank) | cerulean · it20 | 1 | reached: Cerulean City | — | 0.2 | 15000 | 4479 | — | 78 / 174 | $0.25 | $0.00 | $0.25 | 54% | 0.174 | budget_calls |
| 92 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it50 | 1 | reached: Cerulean City | — | 0.2 | 15239 | 3874 | — | 81 / 160 | $0.22 | $0.00 | $0.22 | 63% | 0.189 | stuck |
| 93 | jev-solo | `jev-latest` | rom | mt-moon · it3 | 1 | reached: Mt. Moon 1F | — | 0.1 | 4000 | 1549 | — | 85 / 215 | $0.08 | $0.00 | $0.08 | 55% | 0.238 | budget_calls |
| 94 | jev-solo | `jev-latest` | rom | mt-moon · it4 | 1 | reached: Mt. Moon 1F | — | 0.1 | 4000 | 1570 | — | 81 / 162 | $0.07 | $0.00 | $0.07 | 67% | 0.271 | budget_calls |
| 95 | jev-solo | `jev-latest` | rom | mt-moon · it5 | 1 | reached: Mt. Moon 1F | — | 0.1 | 4001 | 922 | — | 84 / 172 | $0.04 | $0.00 | $0.04 | 82% | 0.183 | budget_calls |
| 96 | jev-assist | `jev-latest + claude-haiku-4-5-20251001 fallback` | rom | after-brock · it2 | 1 | reached: Mt. Moon 1F | — | 1.6 | 4296 | 1339 | 375 (145.91) | 92 / 191 | $0.06 | $4.39 | $4.45 | 71% | 0.309 | manual |
| 97 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it10 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 1743 | — | 76 / 144 | $0.09 | $0.00 | $0.09 | 72% | 0.297 | budget_calls |
| 98 | jev-solo | `jev-latest` | rom | mt-moon · it6 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 1973 | — | 82 / 158 | $0.09 | $0.00 | $0.09 | 84% | 0.188 | budget_calls |
| 99 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it6 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 1884 | — | 95 / 213 | $0.10 | $0.00 | $0.10 | 67% | 0.283 | budget_calls |
| 100 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it7 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 2345 | — | 77 / 144 | $0.12 | $0.00 | $0.12 | 59% | 0.165 | budget_calls |
| 101 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it8 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 1733 | — | 80 / 153 | $0.08 | $0.00 | $0.08 | 81% | 0.296 | budget_calls |
| 102 | jev-solo | `jev-latest` | learned (blank) | mt-moon · it9 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6000 | 1351 | — | 74 / 142 | $0.07 | $0.00 | $0.07 | 78% | 0.349 | budget_calls |
| 103 | jev-solo | `jev-latest` | rom | mt-moon · it7 | 1 | reached: Mt. Moon 1F | — | 0.1 | 6001 | 1929 | — | 80 / 148 | $0.09 | $0.00 | $0.09 | 82% | 0.183 | budget_calls |
| 104 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it83 | 1 | reached: Mt. Moon 1F | — | 0.2 | 7870 | 2134 | — | 59 / 171 | $0.10 | $0.00 | $0.10 | 57% | 0.180 | manual |
| 105 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it36 | 1 | reached: Mt. Moon 1F | — | 1.1 | 50797 | 21816 | — | 75 / 154 | $0.94 | $0.00 | $0.94 | 44% | 0.192 | stuck |
| 106 | jev-solo | `jev-latest` | learned (blank) | power-on · it23 | 1 | badge: Boulder | — | 0.0 | 2187 | 567 | — | 88 / 245 | $0.02 | $0.00 | $0.02 | 77% | 0.194 | segment_goal |
| 107 | jev-solo | `jev-latest` | learned (blank) — outside the 20k cap | full game · it69 | 0 | reached: Viridian City | — | 0.4 | 22996 | 10100 | — | 76 / 159 | $0.45 | $0.00 | $0.45 | 62% | 0.298 | stuck |
| 108 | jev-solo | `jev-latest` | learned (blank) | power-on · it22 | 0 | game started | — | 0.1 | 4083 | 2019 | — | 85 / 211 | $0.11 | $0.00 | $0.11 | 26% | 0.187 | stuck |

### Self-improvement iterations (jev-assist → bench/improve.py → next iteration; goal: 0 fallbacks, then pass jev-solo)

| Segment (state) | Iter | Variant | Maps | Steps | Fallbacks | Per 1k steps | Goal | Badges | Active h | Jev $ | Haiku $ | Opus $ | Total $ | Exit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| full game | 24 | solo | learned (blank) — outside the 20k cap | 5054 | — | — | ✗ — | 2 | 0.20 | $0.23 | $0.00 | $0.00 | $0.23 | stuck |
| full game | 36 | solo | learned (blank) — outside the 20k cap | 23256 | — | — | ✗ — | 1 | 1.06 | $0.94 | $0.00 | $0.00 | $0.94 | stuck |
| full game | 37 | solo | learned (blank) — outside the 20k cap | 4109 | — | — | ✗ — | 1 | 0.17 | $0.22 | $0.00 | $0.00 | $0.22 | stuck |
| full game | 38 | solo | learned (blank) — outside the 20k cap | 3658 | — | — | ✗ — | 1 | 0.16 | $0.21 | $0.00 | $0.00 | $0.21 | stuck |
| full game | 39 | solo | learned (blank) — outside the 20k cap | 5976 | — | — | ✗ — | 2 | 0.26 | $0.27 | $0.00 | $0.00 | $0.27 | stuck |
| full game | 40 | solo | learned (blank) — outside the 20k cap | 7403 | — | — | ✗ — | 2 | 1.07 | $0.30 | $0.00 | $0.00 | $0.30 | stuck |
| full game | 41 | solo | learned (blank) — outside the 20k cap | 12821 | — | — | ✗ — | 2 | 2.24 | $0.54 | $0.00 | $0.00 | $0.54 | stuck |
| full game | 42 | solo | learned (blank) — outside the 20k cap | 5468 | — | — | ✗ — | 2 | 0.26 | $0.25 | $0.00 | $0.00 | $0.25 | stuck |
| full game | 43 | solo | learned (blank) — outside the 20k cap | 6711 | — | — | ✗ — | 3 | 0.78 | $0.24 | $0.00 | $0.00 | $0.24 | stuck |
| full game | 44 | solo | learned (blank) — outside the 20k cap | 10769 | — | — | ✗ — | 3 | 1.08 | $0.50 | $0.00 | $0.00 | $0.50 | stuck |
| full game | 45 | solo | learned (blank) — outside the 20k cap | 8499 | — | — | ✗ — | 2 | 0.97 | $0.33 | $0.00 | $0.00 | $0.33 | stuck |
| full game | 46 | solo | learned (blank) — outside the 20k cap | 7266 | — | — | ✗ — | 2 | 0.31 | $0.36 | $0.00 | $0.00 | $0.36 | stuck |
| full game | 47 | solo | learned (blank) — outside the 20k cap | 12109 | — | — | ✗ — | 4 | 1.42 | $0.51 | $0.00 | $0.00 | $0.51 | stuck |
| full game | 48 | solo | learned (blank) — outside the 20k cap | 13283 | — | — | ✗ — | 4 | 1.88 | $0.56 | $0.00 | $0.00 | $0.56 | stuck |
| full game | 49 | solo | learned (blank) — outside the 20k cap | 10432 | — | — | ✗ — | 4 | 1.22 | $0.44 | $0.00 | $0.00 | $0.44 | stuck |
| full game | 50 | solo | learned (blank) — outside the 20k cap | 4626 | — | — | ✗ — | 1 | 0.20 | $0.22 | $0.00 | $0.00 | $0.22 | stuck |
| full game | 51 | solo | learned (blank) — outside the 20k cap | 10882 | — | — | ✗ — | 3 | 1.55 | $0.43 | $0.00 | $0.00 | $0.43 | stuck |
| full game | 52 | solo | learned (blank) — outside the 20k cap | 8982 | — | — | ✗ — | 4 | 0.85 | $0.39 | $0.00 | $0.00 | $0.39 | stuck |
| full game | 53 | solo | learned (blank) — outside the 20k cap | 7933 | — | — | ✗ — | 3 | 0.65 | $0.28 | $0.00 | $0.00 | $0.28 | stuck |
| full game | 54 | solo | learned (blank) — outside the 20k cap | 12288 | — | — | ✗ — | 4 | 1.71 | $0.60 | $0.00 | $0.00 | $0.60 | stuck |
| full game | 55 | solo | learned (blank) — outside the 20k cap | 11128 | — | — | ✗ — | 4 | 1.15 | $0.53 | $0.00 | $0.00 | $0.53 | stuck |
| full game | 56 | solo | learned (blank) — outside the 20k cap | 9652 | — | — | ✗ — | 4 | 1.45 | $0.41 | $0.00 | $0.00 | $0.41 | stuck |
| full game | 57 | solo | learned (blank) — outside the 20k cap | 13850 | — | — | ✗ — | 4 | 1.03 | $0.57 | $0.00 | $0.00 | $0.57 | stuck |
| full game | 58 | solo | learned (blank) — outside the 20k cap | 10535 | — | — | ✗ — | 3 | 1.52 | $0.45 | $0.00 | $0.00 | $0.45 | stuck |
| full game | 59 | solo | learned (blank) — outside the 20k cap | 25086 | — | — | ✗ — | 5 | 1.92 | $0.80 | $0.00 | $0.00 | $0.80 | stuck |
| full game | 60 | solo | learned (blank) — outside the 20k cap | 7931 | — | — | ✗ — | 3 | 0.55 | $0.35 | $0.00 | $0.00 | $0.35 | stuck |
| full game | 61 | solo | learned (blank) — outside the 20k cap | 14419 | — | — | ✗ — | 5 | 1.66 | $0.62 | $0.00 | $0.00 | $0.62 | stuck |
| full game | 62 | solo | learned (blank) — outside the 20k cap | 14654 | — | — | ✗ — | 5 | 1.90 | $0.65 | $0.00 | $0.00 | $0.65 | stuck |
| full game | 63 | solo | learned (blank) — outside the 20k cap | 12191 | — | — | ✗ — | 5 | 1.52 | $0.53 | $0.00 | $0.00 | $0.53 | stuck |
| full game | 64 | solo | learned (blank) — outside the 20k cap | 11369 | — | — | ✗ — | 5 | 1.30 | $0.46 | $0.00 | $0.00 | $0.46 | stuck |
| full game | 65 | solo | learned (blank) — outside the 20k cap | 11003 | — | — | ✗ — | 4 | 2.86 | $0.58 | $0.00 | $0.00 | $0.58 | stuck |
| full game | 67 | solo | learned (blank) — outside the 20k cap | 10304 | — | — | ✗ — | 4 | 1.77 | $0.51 | $0.00 | $0.00 | $0.51 | stuck |
| full game | 68 | solo | learned (blank) — outside the 20k cap | 16063 | — | — | ✗ — | 4 | 3.15 | $0.75 | $0.00 | $0.00 | $0.75 | stuck |
| full game | 69 | solo | learned (blank) — outside the 20k cap | 11278 | — | — | ✗ — | 0 | 0.42 | $0.45 | $0.00 | $0.00 | $0.45 | stuck |
| full game | 70 | solo | learned (blank) — outside the 20k cap | 9578 | — | — | ✗ — | 4 | 1.95 | $0.40 | $0.00 | $0.00 | $0.40 | stuck |
| full game | 71 | solo | learned (blank) — outside the 20k cap | 12475 | — | — | ✗ — | 5 | 4.62 | $0.60 | $0.00 | $0.00 | $0.60 | stuck |
| full game | 72 | solo | learned (blank) — outside the 20k cap | 11689 | — | — | ✗ — | 5 | 0.83 | $0.50 | $0.00 | $0.00 | $0.50 | stuck |
| full game | 73 | solo | learned (blank) — outside the 20k cap | 17948 | — | — | ✗ — | 5 | 1.82 | $0.74 | $0.00 | $0.00 | $0.74 | stuck |
| full game | 74 | solo | learned (blank) — outside the 20k cap | 8928 | — | — | ✗ — | 4 | 0.62 | $0.42 | $0.00 | $0.00 | $0.42 | stuck |
| full game | 75 | solo | learned (blank) — outside the 20k cap | 20725 | — | — | ✗ — | 6 | 5.23 | $1.05 | $0.00 | $0.00 | $1.05 | stuck |
| full game | 76 | solo | learned (blank) — outside the 20k cap | 15875 | — | — | ✗ — | 5 | 2.24 | $0.49 | $0.00 | $0.00 | $0.49 | stuck |
| full game | 77 | solo | learned (blank) — outside the 20k cap | 8234 | — | — | ✗ — | 4 | 1.03 | $0.33 | $0.00 | $0.00 | $0.33 | manual |
| full game | 78 | solo | learned (blank) — outside the 20k cap | 6599 | — | — | ✗ — | 3 | 0.78 | $0.26 | $0.00 | $0.00 | $0.26 | manual |
| full game | 79 | solo | learned (blank) — outside the 20k cap | 6818 | — | — | ✗ — | 3 | 0.51 | $0.27 | $0.00 | $0.00 | $0.27 | manual |
| full game | 80 | solo | learned (blank) — outside the 20k cap | 7047 | — | — | ✗ — | 4 | 0.56 | $0.28 | $0.00 | $0.00 | $0.28 | manual |
| full game | 81 | solo | learned (blank) — outside the 20k cap | 8513 | — | — | ✗ — | 4 | 1.04 | $0.36 | $0.00 | $0.00 | $0.36 | manual |
| full game | 82 | solo | learned (blank) — outside the 20k cap | 6164 | — | — | ✗ — | 3 | 0.38 | $0.23 | $0.00 | $0.00 | $0.23 | manual |
| full game | 83 | solo | learned (blank) — outside the 20k cap | 2673 | — | — | ✗ — | 1 | 0.17 | $0.10 | $0.00 | $0.00 | $0.10 | manual |
| full game | 84 | solo | learned (blank) — outside the 20k cap | 5878 | — | — | ✗ — | 4 | 0.54 | $0.22 | $0.00 | $0.00 | $0.22 | manual |
| full game | 85 | solo | learned (blank) — outside the 20k cap | 7932 | — | — | ✗ — | 6 | 1.09 | $0.28 | $0.00 | $0.00 | $0.28 | manual |
| full game | 86 | solo | learned (blank) — outside the 20k cap | 9230 | — | — | ✗ — | 6 | 0.96 | $0.39 | $0.00 | $0.00 | $0.39 | manual |
| full game | 87 | solo | learned (blank) — outside the 20k cap | 6717 | — | — | ✗ — | 5 | 0.57 | $0.25 | $0.00 | $0.00 | $0.25 | manual |
| full game | 88 | solo | learned (blank) — outside the 20k cap | 11096 | — | — | ✗ — | 8 | 1.31 | $0.44 | $0.00 | $0.00 | $0.44 | manual |
| full game | 89 | solo | learned (blank) — outside the 20k cap | 6795 | — | — | ✗ — | 5 | 1.09 | $0.27 | $0.00 | $0.00 | $0.27 | manual |
| full game | 90 | solo | learned (blank) — outside the 20k cap | 9455 | — | — | ✗ — | 8 | 1.80 | $0.38 | $0.00 | $0.00 | $0.38 | manual |
| full game | 91 | solo | learned (blank) — outside the 20k cap | 8379 | — | — | ✗ — | 8 | 0.99 | $0.31 | $0.00 | $0.00 | $0.31 | champion |
| after-brock (`cbba8272940afafb`) | 2 | assist | rom | 2570 | 375 | 145.91 | ✗ reached: Cerulean City | 1 | 1.63 | $0.06 | $4.39 | $0.00 | $4.45 | manual |
| bills-house (`93bd0cba50dac4a2`) | 25 | solo | learned (blank) | 2713 | — | — | ✗ reached: Vermilion City | 2 | 0.12 | $0.17 | $0.00 | $0.00 | $0.17 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 26 | solo | learned (blank) | 2011 | — | — | ✗ reached: Vermilion City | 2 | 0.07 | $0.12 | $0.00 | $0.00 | $0.12 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 27 | solo | learned (blank) | 2013 | — | — | ✗ reached: Vermilion City | 2 | 0.07 | $0.11 | $0.00 | $0.00 | $0.11 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 28 | solo | learned (blank) | 2256 | — | — | ✗ reached: Vermilion City | 2 | 0.09 | $0.14 | $0.00 | $0.00 | $0.14 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 29 | solo | learned (blank) | 4522 | — | — | ✗ reached: Vermilion City | 2 | 0.18 | $0.25 | $0.00 | $0.00 | $0.25 | budget_calls |
| bills-house (`93bd0cba50dac4a2`) | 30 | solo | learned (blank) | 2681 | — | — | ✗ reached: Vermilion City | 2 | 0.11 | $0.14 | $0.00 | $0.00 | $0.14 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 31 | solo | learned (blank) | 39 | — | — | ✗ reached: Vermilion City | 2 | 0.04 | $0.00 | $0.00 | $0.00 | $0.00 | budget_time |
| bills-house (`93bd0cba50dac4a2`) | 32 | solo | learned (blank) | 2141 | — | — | ✗ reached: Vermilion City | 2 | 0.08 | $0.12 | $0.00 | $0.00 | $0.12 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 33 | solo | learned (blank) | 2216 | — | — | ✗ reached: Vermilion City | 2 | 0.09 | $0.13 | $0.00 | $0.00 | $0.13 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 34 | solo | learned (blank) | 2678 | — | — | ✗ reached: Vermilion City | 2 | 0.07 | $0.08 | $0.00 | $0.00 | $0.08 | stuck |
| bills-house (`93bd0cba50dac4a2`) | 35 | solo | learned (blank) | 205 | — | — | ✓ reached: Vermilion City | 2 | 0.01 | $0.01 | $0.00 | $0.00 | $0.01 | segment_goal |
| cerulean (`a5099e91a099f2d9`) | 12 | solo | learned (blank) | 2728 | — | — | ✗ badge: Cascade | 1 | 0.09 | $0.14 | $0.00 | $0.00 | $0.14 | stuck |
| cerulean (`a5099e91a099f2d9`) | 13 | solo | learned (blank) | 2912 | — | — | ✗ badge: Cascade | 1 | 0.11 | $0.15 | $0.00 | $0.00 | $0.15 | budget_calls |
| cerulean (`a5099e91a099f2d9`) | 14 | solo | learned (blank) | 2680 | — | — | ✗ badge: Cascade | 1 | 0.09 | $0.14 | $0.00 | $0.00 | $0.14 | stuck |
| cerulean (`a5099e91a099f2d9`) | 15 | solo | learned (blank) | 2854 | — | — | ✗ badge: Cascade | 1 | 0.08 | $0.11 | $0.00 | $0.00 | $0.11 | stuck |
| cerulean (`a5099e91a099f2d9`) | 16 | solo | learned (blank) | 3736 | — | — | ✗ badge: Cascade | 1 | 0.10 | $0.11 | $0.00 | $0.00 | $0.11 | budget_calls |
| cerulean (`a5099e91a099f2d9`) | 17 | solo | learned (blank) | 2825 | — | — | ✗ badge: Cascade | 1 | 0.10 | $0.14 | $0.00 | $0.00 | $0.14 | stuck |
| cerulean (`a5099e91a099f2d9`) | 18 | solo | learned (blank) | 2797 | — | — | ✗ badge: Cascade | 1 | 0.11 | $0.13 | $0.00 | $0.00 | $0.13 | stuck |
| cerulean (`a5099e91a099f2d9`) | 19 | solo | learned (blank) | 2002 | — | — | ✗ badge: Cascade | 1 | 0.07 | $0.15 | $0.00 | $0.00 | $0.15 | stuck |
| cerulean (`a5099e91a099f2d9`) | 20 | solo | learned (blank) | 4739 | — | — | ✗ badge: Cascade | 1 | 0.16 | $0.25 | $0.00 | $0.00 | $0.25 | budget_calls |
| cerulean (`a5099e91a099f2d9`) | 21 | solo | learned (blank) | 1275 | — | — | ✓ badge: Cascade | 2 | 0.04 | $0.04 | $0.00 | $0.00 | $0.04 | segment_goal |
| mt-moon (`f9707b75ecb54c8a`) | 3 | solo | rom | 2051 | — | — | ✗ reached: Cerulean City | 1 | 0.07 | $0.08 | $0.00 | $0.00 | $0.08 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 4 | solo | rom | 2298 | — | — | ✗ reached: Cerulean City | 1 | 0.07 | $0.07 | $0.00 | $0.00 | $0.07 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 5 | solo | rom | 1993 | — | — | ✗ reached: Cerulean City | 1 | 0.05 | $0.04 | $0.00 | $0.00 | $0.04 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 6 | solo | rom | 3499 | — | — | ✗ reached: Cerulean City | 1 | 0.13 | $0.09 | $0.00 | $0.00 | $0.09 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 6 | solo | learned (blank) | 2293 | — | — | ✗ reached: Cerulean City | 1 | 0.12 | $0.10 | $0.00 | $0.00 | $0.10 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 7 | solo | rom | 3357 | — | — | ✗ reached: Cerulean City | 1 | 0.14 | $0.09 | $0.00 | $0.00 | $0.09 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 7 | solo | learned (blank) | 2947 | — | — | ✗ reached: Cerulean City | 1 | 0.09 | $0.12 | $0.00 | $0.00 | $0.12 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 8 | solo | rom | 86 | — | — | ✓ reached: Cerulean City | 1 | 0.00 | $0.00 | $0.00 | $0.00 | $0.00 | segment_goal |
| mt-moon (`f9707b75ecb54c8a`) | 8 | solo | learned (blank) | 2487 | — | — | ✗ reached: Cerulean City | 1 | 0.07 | $0.08 | $0.00 | $0.00 | $0.08 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 9 | solo | learned (blank) | 2086 | — | — | ✗ reached: Cerulean City | 1 | 0.05 | $0.07 | $0.00 | $0.00 | $0.07 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 9 | solo | learned (carried atlas) | 798 | — | — | ✓ reached: Cerulean City | 1 | 0.02 | $0.03 | $0.00 | $0.00 | $0.03 | segment_goal |
| mt-moon (`f9707b75ecb54c8a`) | 10 | solo | learned (blank) | 2220 | — | — | ✗ reached: Cerulean City | 1 | 0.06 | $0.09 | $0.00 | $0.00 | $0.09 | budget_calls |
| mt-moon (`f9707b75ecb54c8a`) | 11 | solo | learned (blank) | 132 | — | — | ✓ reached: Cerulean City | 1 | 0.00 | $0.00 | $0.00 | $0.00 | $0.00 | segment_goal |
| power-on | 22 | solo | learned (blank) | 2074 | — | — | ✗ badge: Boulder | 0 | 0.08 | $0.11 | $0.00 | $0.00 | $0.11 | stuck |
| power-on | 23 | solo | learned (blank) | 796 | — | — | ✓ badge: Boulder | 1 | 0.03 | $0.02 | $0.00 | $0.00 | $0.02 | segment_goal |

## Runs

### claude-fable-5-1 via claude (claude_claude-fable-5-1_20261007_214515)

- CLI: `claude` 2.1.293 (Claude Code) · server commit `8d3f6fa` · prompt `49106d19e201a25e`
- Started 2026-10-07T21:45:15 · ended 2026-10-08T03:24:52 · active 4:23 h · wall 5:39 h · paused 1:15 h · exit: **champion**
- Tool calls 3904 · images 193 · reloads 19 · black-outs 0 · in-game playtime 8:23:40 · Pokédex 10 owned · maps visited 138
- Tokens uncached in / cache reads / out: 0.0M / 342.7M / 1135k (from claude session transcripts) · cost $195.78 (est.) · chunks 9

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Blastoise | 66 | 70/218 | 142 | 173 | 152 | 154 | Blizzard, Surf, Take Down, Dig |
| 2 | Snorlax | 30 | 142/142 | 77 | 48 | 26 | 46 | Strength, Mega Punch, Rest, Thunderbolt |
| 3 | DUX (Farfetch'd) | 13 | 37/37 | 21 | 21 | 22 | 23 | Razor Wind, Fly, Toxic, Cut |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 0:00:02 | game started |
| 0:00 | 17 | 0:00:12 | reached: Pallet Town |
| 0:00 | 29 | 0:01:42 | obtained: Squirtle |
| 0:00 | 29 | 0:01:42 | starter: Squirtle |
| 0:01 | 36 | 0:03:58 | got Squirtle, beat rival 1 |
| 0:01 | 39 | 0:04:10 | reached: Route 1 |
| 0:01 | 40 | 0:05:03 | reached: Viridian City |
| 0:01 | 51 | 0:07:55 | got Pokédex |
| 0:02 | 67 | 0:10:53 | reached: Route 2 |
| 0:03 | 80 | 0:17:04 | obtained: Kakuna |
| 0:06 | 125 | 0:29:35 | obtained: Pidgey |
| 0:06 | 126 | 0:29:41 | reached: Pewter City |
| 0:07 | 152 | 0:35:36 | badge: Boulder |
| 0:07 | 153 | 0:35:36 | beat Brock (Boulder Badge) |
| 0:07 | 162 | 0:36:42 | reached: Route 3 |
| 0:08 | 181 | 0:44:06 | evolved: Squirtle → Wartortle |
| 0:08 | 191 | 0:46:21 | reached: Route 4 |
| 0:08 | 199 | 0:47:06 | reached: Mt. Moon 1F |
| 0:15 | 241 | 0:54:56 | obtained: Zubat |
| 0:17 | 313 | 1:08:10 | reached: Cerulean City |
| 0:17 | 314 | 1:08:10 | cleared Mt. Moon (Helix Fossil) |
| 0:18 | 352 | 1:13:34 | reached: Route 24 |
| 0:19 | 399 | 1:21:51 | reached: Route 25 |
| 0:21 | 460 | 1:35:46 | badge: Cascade |
| 0:21 | 461 | 1:35:46 | beat Misty (Cascade Badge) |
| 0:23 | 530 | 1:43:21 | got S.S. Ticket from Bill |
| 0:26 | 552 | 1:46:08 | reached: Route 5 |
| 0:26 | 556 | 1:46:40 | reached: Route 6 |
| 0:28 | 618 | 2:01:12 | reached: Vermilion City |
| 0:29 | 631 | 2:02:22 | reached: Vermilion Dock |
| 0:30 | 664 | 2:10:15 | reached: Route 11 |
| 0:31 | 678 | 2:11:58 | obtained: Diglett |
| 0:33 | 700 | 2:15:49 | obtained: Spearow |
| 0:33 | 710 | 2:17:05 | evolved: Spearow → Farfetch'd |
| 0:42 | 966 | 2:32:21 | badge: Thunder |
| 0:42 | 967 | 2:32:22 | beat Lt. Surge (Thunder Badge) |
| 0:43 | 986 | 2:34:07 | reached: Route 9 |
| 0:43 | 1014 | 2:38:38 | reached: Route 10 |
| 0:43 | 1031 | 2:39:44 | reached: Rock Tunnel 1F |
| 0:44 | 1048 | 2:45:38 | reached: Rock Tunnel B1F |
| 0:49 | 1169 | 3:21:14 | evolved: Wartortle → Blastoise |
| 0:51 | 1181 | 3:24:18 | reached: Lavender Town |
| 0:51 | 1204 | 3:26:19 | cleared Rock Tunnel, reached Lavender (Blastoise L36) |
| 0:52 | 1246 | 3:27:12 | reached: Route 8 |
| 0:53 | 1264 | 3:31:17 | reached: Route 7 |
| 0:53 | 1265 | 3:31:26 | reached: Celadon City |
| 1:02 | 1379 | 3:37:06 | reached: Rocket Hideout B1F |
| 1:36 | 1736 | 4:04:33 | beat Giovanni at Rocket Hideout |
| 1:37 | 1762 | 4:07:05 | reached: Pokémon Tower 1F |
| 1:39 | 1847 | 4:19:41 | got Poké Flute |
| 1:39 | 1849 | 4:19:53 | reached: Route 12 |
| 1:41 | 1886 | 4:26:01 | obtained: Snorlax |
| 1:43 | 1902 | 4:28:35 | reached: Route 13 |
| 1:44 | 1923 | 4:35:49 | reached: Route 14 |
| 1:53 | 2124 | 5:00:08 | reached: Route 15 |
| 1:54 | 2148 | 5:09:20 | reached: Fuchsia City |
| 1:54 | 2150 | 5:09:46 | reached Fuchsia City |
| 1:54 | 2159 | 5:10:41 | reached: Safari Zone Gate |
| 1:54 | 2163 | 5:11:03 | reached: Safari Zone Center |
| 1:55 | 2168 | 5:11:32 | reached: Safari Zone East |
| 1:55 | 2169 | 5:12:14 | reached: Safari Zone North |
| 1:55 | 2170 | 5:13:36 | reached: Safari Zone West |
| 1:59 | 2212 | 5:17:17 | HM03 Surf + Gold Teeth from Safari Zone |
| 2:00 | 2255 | 5:26:14 | badge: Soul |
| 2:00 | 2257 | 5:26:33 | beat Koga (Soul Badge) |
| 2:04 | 2336 | 5:37:59 | badge: Rainbow |
| 2:04 | 2337 | 5:37:59 | beat Erika (Rainbow Badge) - 5 badges |
| 2:04 | 2357 | 5:39:25 | reached: Route 16 |
| 2:06 | 2401 | 5:43:10 | reached: Saffron City |
| 2:06 | 2402 | 5:43:20 | reached: Silph Co. 1F |
| 2:12 | 2588 | 6:04:19 | beat Giovanni at Silph Co. |
| 2:16 | 2701 | 6:20:22 | badge: Marsh |
| 2:16 | 2702 | 6:20:22 | beat Sabrina (Marsh Badge) - 6 badges |
| 2:16 | 2725 | 6:21:48 | reached: Route 21 |
| 2:17 | 2739 | 6:24:20 | reached: Cinnabar Island |
| 2:17 | 2748 | 6:25:16 | reached: Pokémon Mansion 1F |
| 2:32 | 2929 | 6:48:12 | got Secret Key (Pokémon Mansion) |
| 2:35 | 3013 | 6:54:34 | badge: Volcano |
| 2:35 | 3014 | 6:54:35 | beat Blaine (Volcano Badge) - 7 badges |
| 2:51 | 3119 | 7:07:36 | badge: Earth |
| 2:51 | 3121 | 7:07:51 | beat Giovanni (Earth Badge) - 8 badges |
| 2:53 | 3177 | 7:15:34 | reached: Route 22 |
| 2:54 | 3207 | 7:20:53 | reached: Route 23 |
| 2:55 | 3237 | 7:23:02 | reached: Victory Road 1F |
| 3:58 | 3556 | 7:26:21 | reached: Victory Road 2F |
| 4:02 | 3593 | 7:28:24 | reached: Victory Road 3F |
| 4:12 | 3727 | 7:52:20 | cleared Victory Road |
| 4:12 | 3729 | 7:52:36 | reached: Indigo Plateau |
| 4:16 | 3730 | 7:52:36 | reached Indigo Plateau |
| 4:16 | 3731 | 7:52:42 | reached: Indigo Plateau Lobby |
| 4:19 | 3800 | 7:58:51 | reached: Lorelei's Room |
| 4:21 | 3838 | 8:05:23 | defeated: Lorelei |
| 4:21 | 3844 | 8:06:05 | reached: Bruno's Room |
| 4:21 | 3852 | 8:07:53 | defeated: Bruno |
| 4:21 | 3855 | 8:07:59 | reached: Agatha's Room |
| 4:21 | 3863 | 8:10:12 | defeated: Agatha |
| 4:21 | 3867 | 8:10:55 | reached: Lance's Room |
| 4:22 | 3880 | 8:17:01 | defeated: Lance |
| 4:22 | 3883 | 8:17:25 | beat Elite Four (Lorelei, Bruno, Agatha, Lance) |
| 4:22 | 3885 | 8:17:30 | reached: Champion's Room |
| 4:23 | 3901 | 8:22:23 | defeated: Champion |
| 4:23 | 3902 | 8:22:23 | beat Champion Blue |
| 4:23 | 3903 | 8:23:18 | reached: Hall of Fame |
| 4:23 | 3904 | 8:23:40 | champion defeated (Hall of Fame) |

**Agent notes**

- Viridian Mart sells no Potions (only Poké Ball/Antidote/Parlyz/Burn Heal). Forest Bug Catcher at (2,18) in west column before north gate. Poison can faint Pokémon in overworld.
- Mt. Moon: only 1F top-left ladder (5,5) leads through: B1F→(21,17)→B2F main→fossils→(5,7)→B1F exit (27,3). Other ladders are dead ends. ASCII map shows some ledges as walkable; trust pathfinder 'no route'.
- Team: Wartortle solo carry (Bite/Water Gun/Bubblebeam/Tackle). Have S.S. Ticket, Helix Fossil, Nugget (unsold). Next: Route 5 -> Underground Path -> Route 6 -> Vermilion: S.S. Anne (Cut) then Lt. Surge.
- Erika too dangerous for solo Blastoise L38 (Victreebel Razor Leaf crits 72, Sleep Powder; Vileplume Mega Drain). Postpone Erika until Blastoise has Ice Beam/Blizzard or L45+. Mega Kick TM05 only 5 PP. Celadon Gym trees regrow; gym needs Cut at (35,32) and inside (5,7).
- Rocket Hideout: spinners slide over floor until a dotted stop tile; walk tool reports positions mid-slide. B2F elevator region entered via stop (8,11)->right2,down3,right1 -> slide to (15,18); then left 4 onto (11,18) down-arrow -> (11,20); then right3,down2 ... (10,25) east to (16,25), up col 16 to
- battle auto wastes PP: keeps using Dig vs Flying types (immune) until all PP gone. Vs Flying/Normal use fight Bite/BubbleBeam explicitly. Route 14 trainers down to (12,31) beaten; remaining: bikers at (4,30),(4,31),(5,39),(6,49) + Route 15.
- DUX (Farfetch'd) knows Fly+Cut; Snorlax has Strength+Thunderbolt. Plan: Saffron (Silph Co, Sabrina) -> Fly Pallet -> Surf Route 21 -> Cinnabar (Mansion key, Blaine) -> Fly Viridian -> Giovanni -> Victory Road -> E4. Lavender west exit to Route 8 is at (0,8).
- Saffron Gym pads: entrance(11,15)<->BR(19,17); BR(15,15)<->TR(19,3); TR(15,3)<->MR(15,9); MR(19,9)<->BR(19,15); BR(15,17)<->BL(5,15); BL(1,15)<->TR(19,5). Sabrina room pad (11,11). Beaten: TR(17,1), MR(17,7), BR(17,13), BL(3,13) trainers.
- 8 badges done. Viridian Gym route: entrance->(14,12)->(14,11)->middle->(10,3)->(10,2)->row2 west->(7,3)->(7,4)->Giovanni (2,1). Next: Celadon 2F TM09/TM01 for PP, Indigo mart Full Restores, Route 22/23 -> Victory Road (Strength on Snorlax) -> E4.
- VR1F solved: switch at (17,13). Push boulder B (5,15) down, right along row 16 to (9,16), stand on door tile (9,17) (enter it from (8,17) facing right), push up x2 to (9,14), right x7 to (16,14), up x2 from (16,15) to (16,12), right from (15,12) to (17,12), down from (17,11) to (17,13). Opens gate (
- VR2F: ignore boulder (5,5). Push SW boulder (4,14) left to (3,14), down to (3,16), left to switch (1,16) -> opens (6-7,8-9). Then route (5,8)->row 8->(13,8)->(13,12)->(16,12)->(16,7)->ladder (23,7) to 3F. Exit pocket (25-28,7-9) with doors (29,7)/(29,8) only reachable from 3F via ladder (27,7).
- VR3F: switch (3,5) via boulder (22,3) pushed left row 3, up to (20,1), left row 1 to (6,1), down to (6,2), left row 2 to (2,2), down to (2,5), right to (3,5) -> opens gate (7,10). Boulder (22,15) pushed right into hole (23,15) -> reveals 2F boulder (23,16); push it left to switch (9,16) -> opens 2F 

**CLI chunks:** 9 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 4 rotate, 4 rate_limited, 1 champion; median 20.9 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-07T21:45:15 | 60 | rotate | 1351 | 0.0M / 63.7M / 5k |
| 2 | 2026-10-07T22:45:19 | 60 | rotate | 899 | 0.0M / 91.4M / 2k |
| 3 | 2026-10-07T23:45:26 | 21 | rate_limited | 518 | 0.0M / 38.3M / 93k |
| 4 | 2026-10-08T00:11:20 | 0 | rate_limited | 0 | 0.0M / 0.0M / 0k |
| 5 | 2026-10-08T00:21:25 | 0 | rate_limited | 0 | 0.0M / 0.0M / 0k |
| 6 | 2026-10-08T00:41:31 | 0 | rate_limited | 0 | 0.0M / 0.0M / 0k |
| 7 | 2026-10-08T01:21:37 | 60 | rotate | 635 | 0.0M / 96.9M / 1k |
| 8 | 2026-10-08T02:21:45 | 60 | rotate | 435 | 0.0M / 40.8M / 1k |
| 9 | 2026-10-08T03:21:51 | 3 | champion | 85 | 0.0M / 11.5M / 1k |

</details>

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

### jev-solo: jev-latest (jev-solo-exp-uncapped-2__full_game_from_power-on__blank_atlas__no_call_or_time_cap__monitored__UNASSISTED__no_interventions___402e35e__jev-latest_20261021_101119)

- CLI: `jev-agent` jev_agent.py v2 · server commit `69ef71e` · prompt `49106d19e201a25e`
- Started 2026-10-21T10:11:19 · ended 2026-10-21T11:09:27 · active 0:57 h · wall 0:58 h · paused 0:00 h · exit: **champion**
- Tool calls 35361 · images 3479 · reloads 0 · black-outs 6 · in-game playtime 20:57:55 · Pokédex 5 owned · maps visited 161
- Tokens uncached in / cache reads / out: 8.2M / 0.0M / 1372k · cost $0.34 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 87 | 225/304 | 232 | 209 | 239 | 214 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 35 | 31 | 23 | 36 | Water Gun, Thunderbolt, Surf, Ice Beam |
| 3 | AAAAAAAAAA (Machop) | 24 | 70/70 | 45 | 34 | 25 | 26 | Karate Chop, Low Kick, Fire Blast |
| 4 | AAAAAAAAAA (Machop) | 24 | 67/67 | 48 | 30 | 21 | 26 | Karate Chop, Low Kick |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 131 | 0:02:32 | obtained: Charmander |
| 0:00 | 131 | 0:02:32 | starter: Charmander |
| 0:00 | 159 | 0:04:30 | reached: Route 1 |
| 0:00 | 170 | 0:05:33 | reached: Viridian City |
| 0:00 | 282 | 0:11:02 | reached: Route 2 |
| 0:00 | 375 | 0:16:56 | reached: Pewter City |
| 0:00 | 1022 | 0:41:16 | blacked out (lost a battle) |
| 0:01 | 1710 | 0:58:12 | evolved: Charmander → Charmeleon |
| 0:02 | 4451 | 2:06:04 | badge: Boulder |
| 0:02 | 4460 | 2:06:25 | reached: Route 3 |
| 0:02 | 4555 | 2:12:51 | reached: Route 4 |
| 0:02 | 4559 | 2:12:59 | reached: Mt. Moon 1F |
| 0:03 | 5001 | 2:32:35 | reached: Route 22 |
| 0:03 | 5019 | 2:33:30 | reached: Route 23 |
| 0:03 | 5487 | 2:59:27 | reached: Cerulean City |
| 0:06 | 9672 | 5:31:54 | badge: Cascade |
| 0:06 | 9702 | 5:34:09 | reached: Route 24 |
| 0:06 | 9821 | 5:40:41 | reached: Route 25 |
| 0:06 | 9892 | 5:45:34 | evolved: Charmeleon → Charizard |
| 0:06 | 10051 | 5:51:46 | reached: Route 5 |
| 0:06 | 10069 | 5:52:18 | reached: Route 6 |
| 0:06 | 10114 | 5:54:56 | reached: Vermilion City |
| 0:06 | 10147 | 5:56:08 | reached: Vermilion Dock |
| 0:06 | 10525 | 6:13:31 | badge: Thunder |
| 0:06 | 10573 | 6:15:04 | reached: Route 9 |
| 0:06 | 10632 | 6:18:32 | reached: Route 10 |
| 0:06 | 10636 | 6:18:50 | reached: Rock Tunnel 1F |
| 0:06 | 10665 | 6:20:28 | reached: Rock Tunnel B1F |
| 0:07 | 11350 | 6:47:03 | reached: Route 11 |
| 0:11 | 12552 | 7:39:00 | reached: Route 12 |
| 0:12 | 13173 | 8:08:40 | reached: Lavender Town |
| 0:12 | 13250 | 8:10:31 | reached: Route 8 |
| 0:12 | 13309 | 8:14:01 | reached: Route 7 |
| 0:12 | 13316 | 8:14:10 | reached: Celadon City |
| 0:12 | 13511 | 8:24:55 | badge: Rainbow |
| 0:13 | 13610 | 8:28:44 | reached: Rocket Hideout B1F |
| 0:17 | 14856 | 9:10:52 | reached: Pokémon Tower 1F |
| 0:21 | 16223 | 10:06:22 | reached: Route 13 |
| 0:22 | 16348 | 10:14:03 | reached: Route 14 |
| 0:22 | 16425 | 10:18:12 | reached: Route 15 |
| 0:22 | 16438 | 10:18:37 | reached: Fuchsia City |
| 0:22 | 16628 | 10:30:52 | badge: Soul |
| 0:22 | 16654 | 10:31:58 | reached: Safari Zone Gate |
| 0:22 | 16661 | 10:32:19 | reached: Safari Zone Center |
| 0:22 | 16668 | 10:32:30 | reached: Safari Zone East |
| 0:22 | 16688 | 10:33:29 | reached: Safari Zone North |
| 0:22 | 16692 | 10:33:46 | reached: Safari Zone West |
| 0:26 | 17944 | 11:21:55 | reached: Saffron City |
| 0:26 | 17973 | 11:22:55 | reached: Silph Co. 1F |
| 0:28 | 18870 | 12:08:52 | badge: Marsh |
| 0:28 | 18940 | 12:11:48 | obtained: Lapras |
| 0:28 | 19095 | 12:18:27 | reached: Route 21 |
| 0:28 | 19179 | 12:23:19 | reached: Cinnabar Island |
| 0:28 | 19201 | 12:24:01 | reached: Pokémon Mansion 1F |
| 0:52 | 31032 | 18:14:45 | badge: Volcano |
| 0:53 | 31387 | 18:36:56 | badge: Earth |
| 0:53 | 31478 | 18:42:28 | reached: Victory Road 1F |
| 0:53 | 31546 | 18:46:58 | reached: Victory Road 2F |
| 0:53 | 31560 | 18:47:44 | reached: Victory Road 3F |
| 0:54 | 31852 | 19:00:53 | reached: Indigo Plateau |
| 0:54 | 31857 | 19:00:59 | reached: Indigo Plateau Lobby |
| 0:54 | 31985 | 19:07:08 | reached: Lorelei's Room |
| 0:54 | 32008 | 19:09:09 | defeated: Lorelei |
| 0:54 | 32016 | 19:09:19 | reached: Bruno's Room |
| 0:54 | 32039 | 19:11:07 | defeated: Bruno |
| 0:54 | 32048 | 19:11:14 | reached: Agatha's Room |
| 0:54 | 32072 | 19:13:25 | defeated: Agatha |
| 0:54 | 32080 | 19:13:36 | reached: Lance's Room |
| 0:55 | 32632 | 19:28:41 | obtained: Machop |
| 0:57 | 35314 | 20:52:27 | defeated: Lance |
| 0:57 | 35331 | 20:53:34 | reached: Champion's Room |
| 0:57 | 35352 | 20:56:34 | defeated: Champion |
| 0:57 | 35353 | 20:57:30 | reached: Hall of Fame |
| 0:57 | 35360 | 20:57:55 | champion defeated (Hall of Fame) |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 58.1 min, longest 58 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-21T10:11:19 | 58 | exited | 35361 | 8.2M / 0.0M / 1372k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11868 (asked Jev 7173, forced by code 4695, labelled 7173) · models jev-1.13.0 · input tokens 8173205 · Jev $0.3433
- Jev latency mean 221 ms · p50 151 · p95 495 · max 13498
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 122 · objectives Jev marked done 0 · final objective: Beat the Elite Four and the Champion: next, Champion in Champion's Room (talk to them).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1545 | 97% | 0.63 |
| faint_switch | 1 | 0% | 0.20 |
| intro | 52 | 52% | 0.42 |
| overworld | 5286 | 66% | 0.54 |
| prompt | 289 | 43% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1917)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 150 | 0.06 | 0.39 | 74% | `███████████████     ` |
| 0.1–0.2 | 636 | 0.15 | 0.29 | 57% | `███████████         ` |
| 0.2–0.3 | 920 | 0.24 | 0.36 | 63% | `█████████████       ` |
| 0.3–0.4 | 815 | 0.34 | 0.45 | 62% | `████████████        ` |
| 0.4–0.5 | 739 | 0.44 | 0.53 | 68% | `██████████████      ` |
| 0.5–0.6 | 616 | 0.54 | 0.62 | 77% | `███████████████     ` |
| 0.6–0.7 | 633 | 0.64 | 0.70 | 83% | `█████████████████   ` |
| 0.7–0.8 | 772 | 0.74 | 0.78 | 89% | `██████████████████  ` |
| 0.8–0.9 | 655 | 0.84 | 0.87 | 89% | `██████████████████  ` |
| 0.9–1.0 | 1237 | 0.96 | 0.96 | 66% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it91_jev-latest_20261020_123511)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T12:35:11 · ended 2026-10-20T13:34:43 · active 0:59 h · wall 0:59 h · paused 0:00 h · exit: **champion**
- Tool calls 24715 · images 2441 · reloads 1 · black-outs 0 · in-game playtime 16:45:32 · Pokédex 6 owned · maps visited 175
- Tokens uncached in / cache reads / out: 7.3M / 0.0M / 1225k · cost $0.31 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 79 | 269/269 | 192 | 183 | 222 | 196 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAAAAAAA (Kakuna) | 6 | 21/21 | 8 | 11 | 10 | 9 | Harden |
| 3 | Magikarp | 5 | 17/17 | 7 | 11 | 13 | 7 | Splash |
| 4 | AAAAAJJJJJ (Lapras) | 15 | 67/67 | 31 | 32 | 27 | 37 | Water Gun, Blizzard, Surf, Thunderbolt |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:16 | reached: Pallet Town |
| 0:00 | 123 | 0:02:17 | obtained: Charmander |
| 0:00 | 123 | 0:02:17 | starter: Charmander |
| 0:00 | 151 | 0:04:11 | reached: Route 1 |
| 0:00 | 162 | 0:05:07 | reached: Viridian City |
| 0:00 | 250 | 0:09:25 | reached: Route 2 |
| 0:00 | 378 | 0:17:11 | reached: Pewter City |
| 0:01 | 1662 | 0:55:42 | obtained: Kakuna |
| 0:01 | 1784 | 0:59:45 | evolved: Charmander → Charmeleon |
| 0:01 | 1852 | 1:04:27 | badge: Boulder |
| 0:01 | 1862 | 1:04:49 | reached: Route 3 |
| 0:01 | 1984 | 1:13:24 | reached: Route 4 |
| 0:01 | 1988 | 1:13:32 | reached: Mt. Moon 1F |
| 0:01 | 2402 | 1:43:17 | obtained: Magikarp |
| 0:01 | 2553 | 1:48:27 | reached: Route 22 |
| 0:01 | 2571 | 1:49:21 | reached: Route 23 |
| 0:02 | 3197 | 2:16:26 | reached: Cerulean City |
| 0:04 | 7294 | 4:44:56 | badge: Cascade |
| 0:04 | 7341 | 4:47:31 | reached: Route 24 |
| 0:05 | 7432 | 4:52:59 | reached: Route 25 |
| 0:05 | 7754 | 5:06:55 | reached: Route 5 |
| 0:05 | 7772 | 5:07:27 | reached: Route 6 |
| 0:05 | 7817 | 5:10:10 | reached: Vermilion City |
| 0:05 | 7855 | 5:11:35 | reached: Vermilion Dock |
| 0:05 | 7886 | 5:13:47 | evolved: Charmeleon → Charizard |
| 0:05 | 8055 | 5:23:44 | badge: Thunder |
| 0:05 | 8102 | 5:25:16 | reached: Route 9 |
| 0:05 | 8161 | 5:28:46 | reached: Route 10 |
| 0:05 | 8165 | 5:29:04 | reached: Rock Tunnel 1F |
| 0:05 | 8195 | 5:30:58 | reached: Rock Tunnel B1F |
| 0:06 | 8840 | 5:59:14 | reached: Route 11 |
| 0:08 | 9610 | 6:32:45 | reached: Route 12 |
| 0:18 | 11529 | 8:01:26 | reached: Lavender Town |
| 0:19 | 11601 | 8:03:07 | reached: Route 8 |
| 0:19 | 11661 | 8:06:42 | reached: Route 7 |
| 0:19 | 11667 | 8:06:51 | reached: Celadon City |
| 0:19 | 11898 | 8:18:32 | badge: Rainbow |
| 0:19 | 11984 | 8:22:14 | reached: Rocket Hideout B1F |
| 0:21 | 13156 | 9:03:06 | reached: Pokémon Tower 1F |
| 0:29 | 14431 | 9:47:03 | reached: Route 16 |
| 0:31 | 15532 | 10:26:14 | reached: Route 13 |
| 0:31 | 15657 | 10:34:33 | reached: Route 14 |
| 0:31 | 15738 | 10:38:52 | reached: Route 15 |
| 0:31 | 15751 | 10:39:18 | reached: Fuchsia City |
| 0:32 | 15949 | 10:51:16 | badge: Soul |
| 0:32 | 15957 | 10:51:59 | reached: Safari Zone Gate |
| 0:32 | 15964 | 10:52:20 | reached: Safari Zone Center |
| 0:32 | 15971 | 10:52:32 | reached: Safari Zone East |
| 0:32 | 15992 | 10:53:32 | reached: Safari Zone North |
| 0:32 | 15996 | 10:53:50 | reached: Safari Zone West |
| 0:33 | 17067 | 11:32:20 | reached: Saffron City |
| 0:33 | 17092 | 11:33:12 | reached: Silph Co. 1F |
| 0:34 | 18010 | 12:10:35 | badge: Marsh |
| 0:34 | 18074 | 12:13:00 | obtained: Lapras |
| 0:36 | 18356 | 12:21:56 | reached: Route 21 |
| 0:36 | 18412 | 12:24:44 | reached: Cinnabar Island |
| 0:36 | 18433 | 12:25:27 | reached: Pokémon Mansion 1F |
| 0:46 | 20431 | 13:42:25 | badge: Volcano |
| 0:46 | 20744 | 14:02:36 | badge: Earth |
| 0:47 | 20838 | 14:08:34 | reached: Victory Road 1F |
| 0:47 | 20901 | 14:12:47 | reached: Victory Road 2F |
| 0:47 | 20933 | 14:14:43 | reached: Victory Road 3F |
| 0:57 | 21989 | 15:06:46 | reached: Indigo Plateau |
| 0:57 | 21994 | 15:06:52 | reached: Indigo Plateau Lobby |
| 0:57 | 22195 | 15:16:14 | reached: Lorelei's Room |
| 0:57 | 22245 | 15:22:52 | defeated: Lorelei |
| 0:57 | 22258 | 15:23:36 | reached: Bruno's Room |
| 0:57 | 22281 | 15:25:36 | defeated: Bruno |
| 0:57 | 22289 | 15:25:43 | reached: Agatha's Room |
| 0:57 | 22312 | 15:28:05 | defeated: Agatha |
| 0:57 | 22320 | 15:28:16 | reached: Lance's Room |
| 0:59 | 24663 | 16:39:44 | defeated: Lance |
| 0:59 | 24684 | 16:41:33 | reached: Champion's Room |
| 0:59 | 24705 | 16:44:11 | defeated: Champion |
| 0:59 | 24706 | 16:45:07 | reached: Hall of Fame |
| 0:59 | 24714 | 16:45:32 | champion defeated (Hall of Fame) |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 59.5 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T12:35:11 | 60 | exited | 24715 | 7.3M / 0.0M / 1225k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8379 (asked Jev 6207, forced by code 2172, labelled 6207) · models jev-1.13.0 · input tokens 7334913 · Jev $0.3081
- Jev latency mean 90 ms · p50 67 · p95 176 · max 4481
- Fallbacks: none (variant without a safety net)
- Iteration 91
- Planner calls 0 ($0.0000, errors 0) · objective changes 120 · objectives Jev marked done 0 · final objective: Beat the Elite Four and the Champion: next, Champion in Champion's Room (talk to them).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1179 | 96% | 0.65 |
| faint_switch | 14 | 64% | 0.58 |
| intro | 51 | 51% | 0.43 |
| overworld | 4662 | 67% | 0.53 |
| prompt | 301 | 38% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1669)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 78 | 0.06 | 0.40 | 80% | `████████████████    ` |
| 0.1–0.2 | 446 | 0.15 | 0.29 | 60% | `████████████        ` |
| 0.2–0.3 | 833 | 0.24 | 0.36 | 58% | `████████████        ` |
| 0.3–0.4 | 842 | 0.34 | 0.45 | 61% | `████████████        ` |
| 0.4–0.5 | 621 | 0.44 | 0.53 | 67% | `█████████████       ` |
| 0.5–0.6 | 621 | 0.55 | 0.62 | 74% | `███████████████     ` |
| 0.6–0.7 | 654 | 0.65 | 0.71 | 83% | `█████████████████   ` |
| 0.7–0.8 | 633 | 0.74 | 0.79 | 89% | `██████████████████  ` |
| 0.8–0.9 | 550 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 929 | 0.95 | 0.96 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-uncapped-1__full_game_from_power-on__blank_atlas__no_call_or_time_cap__monitored__interventions_logged_in_the_journal__5bd1aac__jev-latest_20261020_211951)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5bd1aac` · prompt `49106d19e201a25e`
- Started 2026-10-20T21:19:51 · ended 2026-10-20T23:53:15 · active 2:30 h · wall 2:33 h · paused 0:00 h · exit: **champion**
- Tool calls 53253 · images 5293 · reloads 1 · black-outs 5 · in-game playtime 28:33:00 · Pokédex 4 owned · maps visited 175
- Tokens uncached in / cache reads / out: 10.8M / 0.0M / 1723k · cost $0.45 · chunks 8

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 98 | 320/352 | 256 | 249 | 268 | 235 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 31 | 31 | 24 | 38 | Water Gun, Thunderbolt, Surf, Ice Beam |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:12 | reached: Pallet Town |
| 0:00 | 124 | 0:02:13 | obtained: Charmander |
| 0:00 | 124 | 0:02:13 | starter: Charmander |
| 0:00 | 153 | 0:04:13 | reached: Route 1 |
| 0:00 | 164 | 0:05:09 | reached: Viridian City |
| 0:00 | 251 | 0:09:32 | reached: Route 2 |
| 0:00 | 383 | 0:17:33 | reached: Pewter City |
| 0:00 | 1249 | 0:45:02 | blacked out (lost a battle) |
| 0:01 | 1921 | 1:01:26 | evolved: Charmander → Charmeleon |
| 0:01 | 2627 | 1:19:54 | badge: Boulder |
| 0:01 | 2653 | 1:20:48 | reached: Route 3 |
| 0:01 | 2748 | 1:27:30 | reached: Route 4 |
| 0:01 | 2752 | 1:27:38 | reached: Mt. Moon 1F |
| 0:02 | 3180 | 1:48:42 | reached: Route 22 |
| 0:02 | 3198 | 1:49:36 | reached: Route 23 |
| 0:02 | 3836 | 2:21:19 | reached: Cerulean City |
| 0:05 | 7950 | 4:45:22 | badge: Cascade |
| 0:05 | 7979 | 4:47:35 | reached: Route 24 |
| 0:05 | 8094 | 4:54:01 | reached: Route 25 |
| 0:05 | 8408 | 5:07:12 | reached: Route 5 |
| 0:05 | 8426 | 5:07:44 | reached: Route 6 |
| 0:05 | 8472 | 5:10:20 | reached: Vermilion City |
| 0:05 | 8501 | 5:11:22 | reached: Vermilion Dock |
| 0:05 | 8531 | 5:13:37 | evolved: Charmeleon → Charizard |
| 0:05 | 8625 | 5:17:44 | reached: Route 11 |
| 0:05 | 8802 | 5:26:24 | badge: Thunder |
| 0:05 | 8856 | 5:28:18 | reached: Route 9 |
| 0:05 | 8915 | 5:31:53 | reached: Route 10 |
| 0:05 | 8919 | 5:32:11 | reached: Rock Tunnel 1F |
| 0:05 | 8948 | 5:34:19 | reached: Rock Tunnel B1F |
| 0:13 | 11374 | 7:24:44 | reached: Lavender Town |
| 0:13 | 11411 | 7:25:52 | reached: Route 12 |
| 0:14 | 11603 | 7:33:03 | reached: Route 8 |
| 0:14 | 11663 | 7:36:21 | reached: Route 7 |
| 0:14 | 11669 | 7:36:30 | reached: Celadon City |
| 0:14 | 11854 | 7:46:09 | badge: Rainbow |
| 0:14 | 11965 | 7:50:32 | reached: Rocket Hideout B1F |
| 0:16 | 13402 | 8:37:08 | reached: Pokémon Tower 1F |
| 0:21 | 14076 | 9:00:55 | reached: Route 16 |
| 0:22 | 14703 | 9:25:07 | reached: Route 13 |
| 0:22 | 14823 | 9:32:27 | reached: Route 14 |
| 0:22 | 14904 | 9:36:48 | reached: Route 15 |
| 0:22 | 14918 | 9:37:13 | reached: Fuchsia City |
| 0:22 | 15065 | 9:46:05 | badge: Soul |
| 0:22 | 15074 | 9:46:46 | reached: Safari Zone Gate |
| 0:22 | 15081 | 9:47:07 | reached: Safari Zone Center |
| 0:22 | 15088 | 9:47:18 | reached: Safari Zone East |
| 0:22 | 15100 | 9:48:02 | reached: Safari Zone North |
| 0:22 | 15104 | 9:48:19 | reached: Safari Zone West |
| 0:24 | 16484 | 10:45:19 | reached: Saffron City |
| 0:25 | 16513 | 10:46:21 | reached: Silph Co. 1F |
| 0:26 | 17901 | 11:32:28 | badge: Marsh |
| 0:26 | 17951 | 11:34:35 | obtained: Lapras |
| 0:27 | 18176 | 11:43:29 | reached: Route 21 |
| 0:27 | 18224 | 11:46:07 | reached: Cinnabar Island |
| 0:27 | 18246 | 11:46:48 | reached: Pokémon Mansion 1F |
| 2:28 | 51970 | 27:19:27 | badge: Volcano |
| 2:28 | 52298 | 27:39:27 | badge: Earth |
| 2:29 | 52395 | 27:45:31 | reached: Victory Road 1F |
| 2:29 | 52453 | 27:49:09 | reached: Victory Road 2F |
| 2:29 | 52489 | 27:51:08 | reached: Victory Road 3F |
| 2:30 | 53027 | 28:15:48 | reached: Indigo Plateau |
| 2:30 | 53032 | 28:15:54 | reached: Indigo Plateau Lobby |
| 2:30 | 53091 | 28:19:41 | reached: Lorelei's Room |
| 2:30 | 53114 | 28:21:37 | defeated: Lorelei |
| 2:30 | 53122 | 28:21:46 | reached: Bruno's Room |
| 2:30 | 53145 | 28:23:35 | defeated: Bruno |
| 2:30 | 53154 | 28:23:42 | reached: Agatha's Room |
| 2:30 | 53177 | 28:25:34 | defeated: Agatha |
| 2:30 | 53182 | 28:25:45 | reached: Lance's Room |
| 2:30 | 53205 | 28:28:10 | defeated: Lance |
| 2:30 | 53222 | 28:29:17 | reached: Champion's Room |
| 2:30 | 53243 | 28:31:39 | defeated: Champion |
| 2:30 | 53244 | 28:32:34 | reached: Hall of Fame |
| 2:30 | 53252 | 28:33:00 | champion defeated (Hall of Fame) |

**CLI chunks:** 8 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 7 exited, 1 rotate; median 9.6 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T21:19:51 | 60 | rotate | 20900 | 6.0M / 0.0M / 1023k |
| 2 | 2026-10-20T22:20:03 | 35 | exited | 1536 | 0.2M / 0.0M / 22k |
| 3 | 2026-10-20T22:56:00 | 6 | exited | 2795 | 0.5M / 0.0M / 74k |
| 4 | 2026-10-20T23:02:36 | 10 | exited | 4281 | 0.7M / 0.0M / 116k |
| 5 | 2026-10-20T23:12:30 | 7 | exited | 3620 | 0.4M / 0.0M / 51k |
| 6 | 2026-10-20T23:19:37 | 7 | exited | 3886 | 0.5M / 0.0M / 61k |
| 7 | 2026-10-20T23:26:34 | 22 | exited | 12786 | 1.8M / 0.0M / 247k |
| 8 | 2026-10-20T23:49:13 | 4 | exited | 3448 | 0.8M / 0.0M / 128k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 18504 (asked Jev 9822, forced by code 8682, labelled 9822) · models jev-1.13.0 · input tokens 10797986 · Jev $0.4535
- Jev latency mean 73 ms · p50 64 · p95 134 · max 426
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 143 · objectives Jev marked done 0 · final objective: Beat the Elite Four and the Champion: next, Champion in Champion's Room (talk to them).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 2116 | 98% | 0.56 |
| intro | 52 | 48% | 0.40 |
| overworld | 7464 | 68% | 0.43 |
| prompt | 190 | 47% | 0.51 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2368)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 331 | 0.06 | 0.36 | 70% | `██████████████      ` |
| 0.1–0.2 | 1583 | 0.15 | 0.29 | 66% | `█████████████       ` |
| 0.2–0.3 | 1632 | 0.24 | 0.36 | 68% | `██████████████      ` |
| 0.3–0.4 | 1264 | 0.34 | 0.46 | 67% | `█████████████       ` |
| 0.4–0.5 | 1013 | 0.44 | 0.55 | 72% | `██████████████      ` |
| 0.5–0.6 | 919 | 0.54 | 0.63 | 82% | `████████████████    ` |
| 0.6–0.7 | 847 | 0.65 | 0.71 | 85% | `█████████████████   ` |
| 0.7–0.8 | 775 | 0.74 | 0.78 | 90% | `██████████████████  ` |
| 0.8–0.9 | 597 | 0.84 | 0.87 | 91% | `██████████████████  ` |
| 0.9–1.0 | 861 | 0.96 | 0.96 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it90_jev-latest_20261020_102501)

- CLI: `jev-agent` jev_agent.py v2 · server commit `8104220` · prompt `49106d19e201a25e`
- Started 2026-10-20T10:25:01 · ended 2026-10-20T12:13:26 · active 1:48 h · wall 1:48 h · paused 0:00 h · exit: **manual**
- Tool calls 27339 · images 2552 · reloads 1 · black-outs 0 · in-game playtime 17:46:16 · Pokédex 4 owned · maps visited 152
- Tokens uncached in / cache reads / out: 8.9M / 0.0M / 1600k · cost $0.38 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 70 | 227/227 | 184 | 174 | 205 | 163 | Strength, Slash, Fire Blast, Cut |
| 2 | AAAAAAAAA (Lapras) | 16 | 67/67 | 36 | 32 | 26 | 37 | Water Gun, Thunderbolt, Surf, Blizzard |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 126 | 0:02:19 | obtained: Charmander |
| 0:00 | 126 | 0:02:19 | starter: Charmander |
| 0:00 | 154 | 0:04:15 | reached: Route 1 |
| 0:00 | 159 | 0:04:35 | reached: Viridian City |
| 0:00 | 252 | 0:08:54 | reached: Route 2 |
| 0:00 | 376 | 0:17:45 | reached: Pewter City |
| 0:01 | 2566 | 1:19:54 | evolved: Charmander → Charmeleon |
| 0:02 | 4119 | 1:57:14 | badge: Boulder |
| 0:02 | 4129 | 1:57:36 | reached: Route 3 |
| 0:02 | 4218 | 2:04:05 | reached: Route 4 |
| 0:02 | 4222 | 2:04:13 | reached: Mt. Moon 1F |
| 0:03 | 4625 | 2:25:32 | reached: Route 22 |
| 0:03 | 4643 | 2:26:27 | reached: Route 23 |
| 0:04 | 5469 | 2:55:13 | reached: Cerulean City |
| 0:07 | 9623 | 5:27:12 | badge: Cascade |
| 0:07 | 9652 | 5:29:26 | reached: Route 24 |
| 0:07 | 9767 | 5:35:47 | reached: Route 25 |
| 0:07 | 9838 | 5:40:37 | evolved: Charmeleon → Charizard |
| 0:07 | 10023 | 5:47:03 | reached: Route 5 |
| 0:07 | 10041 | 5:47:35 | reached: Route 6 |
| 0:07 | 10085 | 5:50:11 | reached: Vermilion City |
| 0:07 | 10119 | 5:51:23 | reached: Vermilion Dock |
| 0:07 | 10223 | 5:56:55 | reached: Route 11 |
| 0:07 | 10473 | 6:08:08 | badge: Thunder |
| 0:07 | 10532 | 6:10:00 | reached: Route 9 |
| 0:07 | 10591 | 6:13:20 | reached: Route 10 |
| 0:07 | 10595 | 6:13:38 | reached: Rock Tunnel 1F |
| 0:07 | 10624 | 6:15:25 | reached: Rock Tunnel B1F |
| 0:12 | 12350 | 7:33:54 | reached: Route 12 |
| 0:28 | 16081 | 10:23:47 | reached: Lavender Town |
| 0:28 | 16158 | 10:25:36 | reached: Route 8 |
| 0:28 | 16297 | 10:34:01 | reached: Route 7 |
| 0:28 | 16303 | 10:34:10 | reached: Celadon City |
| 0:28 | 16492 | 10:44:20 | badge: Rainbow |
| 0:29 | 16617 | 10:49:28 | reached: Rocket Hideout B1F |
| 0:30 | 18518 | 11:33:36 | reached: Pokémon Tower 1F |
| 0:36 | 19866 | 12:29:21 | reached: Route 13 |
| 0:36 | 19987 | 12:36:46 | reached: Route 14 |
| 0:36 | 20060 | 12:41:12 | reached: Route 15 |
| 0:36 | 20073 | 12:41:38 | reached: Fuchsia City |
| 0:36 | 20247 | 12:53:15 | badge: Soul |
| 0:36 | 20255 | 12:53:59 | reached: Safari Zone Gate |
| 0:36 | 20262 | 12:54:20 | reached: Safari Zone Center |
| 0:36 | 20269 | 12:54:31 | reached: Safari Zone East |
| 0:36 | 20281 | 12:55:18 | reached: Safari Zone North |
| 0:36 | 20294 | 12:55:50 | reached: Safari Zone West |
| 0:38 | 21470 | 13:42:00 | reached: Saffron City |
| 0:38 | 21495 | 13:42:50 | reached: Silph Co. 1F |
| 0:42 | 23417 | 14:38:32 | badge: Marsh |
| 0:42 | 23467 | 14:40:38 | obtained: Lapras |
| 0:42 | 23624 | 14:47:32 | reached: Route 21 |
| 0:42 | 23696 | 14:52:01 | reached: Cinnabar Island |
| 0:42 | 23709 | 14:52:22 | reached: Pokémon Mansion 1F |
| 0:55 | 25362 | 16:01:35 | badge: Volcano |
| 0:55 | 25653 | 16:18:48 | badge: Earth |
| 1:38 | 26650 | 17:07:56 | reached: Victory Road 1F |
| 1:38 | 26700 | 17:11:35 | reached: Victory Road 2F |
| 1:39 | 26786 | 17:15:36 | reached: Victory Road 3F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.2 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T10:25:01 | 60 | rotate | 25811 | 8.5M / 0.0M / 1534k |
| 2 | 2026-10-20T11:25:12 | 48 | exited | 1525 | 0.4M / 0.0M / 66k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 9455 (asked Jev 7320, forced by code 2135, labelled 7320) · models jev-1.13.0 · input tokens 8944918 · Jev $0.3757
- Jev latency mean 78 ms · p50 68 · p95 148 · max 474
- Fallbacks: none (variant without a safety net)
- Iteration 90
- Planner calls 0 ($0.0000, errors 0) · objective changes 103 · objectives Jev marked done 0 · final objective: Go west from Viridian City on Route 22 and north on Route 23 through Victory Road to Indigo Plateau.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1147 | 96% | 0.65 |
| faint_switch | 1 | 100% | 0.09 |
| intro | 52 | 54% | 0.41 |
| overworld | 5966 | 60% | 0.50 |
| prompt | 154 | 58% | 0.45 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1449)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 91 | 0.06 | 0.35 | 74% | `███████████████     ` |
| 0.1–0.2 | 745 | 0.15 | 0.25 | 54% | `███████████         ` |
| 0.2–0.3 | 1151 | 0.24 | 0.34 | 53% | `███████████         ` |
| 0.3–0.4 | 980 | 0.34 | 0.43 | 54% | `███████████         ` |
| 0.4–0.5 | 753 | 0.44 | 0.53 | 60% | `████████████        ` |
| 0.5–0.6 | 700 | 0.54 | 0.62 | 70% | `██████████████      ` |
| 0.6–0.7 | 655 | 0.65 | 0.70 | 78% | `████████████████    ` |
| 0.7–0.8 | 647 | 0.74 | 0.78 | 84% | `█████████████████   ` |
| 0.8–0.9 | 590 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 1008 | 0.96 | 0.96 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it88_jev-latest_20261020_072112)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7869667` · prompt `49106d19e201a25e`
- Started 2026-10-20T07:21:12 · ended 2026-10-20T08:39:50 · active 1:18 h · wall 1:18 h · paused 0:00 h · exit: **manual**
- Tool calls 32634 · images 3026 · reloads 2 · black-outs 0 · in-game playtime 18:53:00 · Pokédex 4 owned · maps visited 154
- Tokens uncached in / cache reads / out: 10.6M / 0.0M / 2014k · cost $0.44 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 74 | 197/251 | 181 | 170 | 209 | 176 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAJJJJJJ (Lapras) | 15 | 65/65 | 32 | 29 | 26 | 34 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:01 | game started |
| 0:00 | 99 | 0:00:19 | reached: Pallet Town |
| 0:00 | 136 | 0:02:20 | obtained: Charmander |
| 0:00 | 136 | 0:02:20 | starter: Charmander |
| 0:00 | 164 | 0:04:24 | reached: Route 1 |
| 0:00 | 175 | 0:05:16 | reached: Viridian City |
| 0:00 | 268 | 0:10:02 | reached: Route 2 |
| 0:00 | 407 | 0:19:03 | reached: Pewter City |
| 0:01 | 2376 | 1:16:45 | evolved: Charmander → Charmeleon |
| 0:02 | 4247 | 2:01:42 | badge: Boulder |
| 0:02 | 4274 | 2:02:37 | reached: Route 3 |
| 0:02 | 4344 | 2:09:27 | reached: Route 4 |
| 0:02 | 4348 | 2:09:36 | reached: Mt. Moon 1F |
| 0:02 | 4835 | 2:34:20 | reached: Route 22 |
| 0:02 | 4846 | 2:34:52 | reached: Route 23 |
| 0:03 | 5346 | 3:02:05 | reached: Cerulean City |
| 0:05 | 9466 | 5:33:57 | badge: Cascade |
| 0:05 | 9504 | 5:36:34 | reached: Route 24 |
| 0:05 | 9584 | 5:42:20 | reached: Route 25 |
| 0:05 | 9637 | 5:47:11 | evolved: Charmeleon → Charizard |
| 0:05 | 9787 | 5:53:15 | reached: Route 5 |
| 0:05 | 9805 | 5:53:47 | reached: Route 6 |
| 0:05 | 9841 | 5:56:30 | reached: Vermilion City |
| 0:05 | 9874 | 5:57:42 | reached: Vermilion Dock |
| 0:05 | 10103 | 6:11:36 | badge: Thunder |
| 0:05 | 10155 | 6:13:12 | reached: Route 9 |
| 0:09 | 11239 | 7:00:14 | reached: Route 10 |
| 0:09 | 11244 | 7:00:32 | reached: Rock Tunnel 1F |
| 0:09 | 11270 | 7:02:10 | reached: Rock Tunnel B1F |
| 0:10 | 11740 | 7:23:41 | reached: Route 11 |
| 0:10 | 11946 | 7:32:18 | reached: Route 12 |
| 0:26 | 16327 | 10:41:50 | reached: Lavender Town |
| 0:26 | 16513 | 10:46:12 | reached: Route 8 |
| 0:27 | 16664 | 10:56:21 | reached: Pokémon Tower 1F |
| 0:32 | 17618 | 11:21:45 | reached: Route 7 |
| 0:32 | 17624 | 11:21:54 | reached: Celadon City |
| 0:33 | 17792 | 11:32:36 | badge: Rainbow |
| 0:33 | 17924 | 11:37:55 | reached: Rocket Hideout B1F |
| 0:41 | 20350 | 13:02:16 | reached: Route 13 |
| 0:42 | 20432 | 13:09:28 | reached: Route 14 |
| 0:42 | 20501 | 13:14:14 | reached: Route 15 |
| 0:42 | 20524 | 13:15:15 | reached: Fuchsia City |
| 0:42 | 20686 | 13:26:52 | badge: Soul |
| 0:42 | 20694 | 13:27:34 | reached: Safari Zone Gate |
| 0:42 | 20701 | 13:27:55 | reached: Safari Zone Center |
| 0:42 | 20708 | 13:28:06 | reached: Safari Zone East |
| 0:42 | 20721 | 13:28:49 | reached: Safari Zone North |
| 0:42 | 20725 | 13:29:07 | reached: Safari Zone West |
| 0:45 | 22099 | 14:23:40 | reached: Saffron City |
| 0:45 | 22128 | 14:24:46 | reached: Silph Co. 1F |
| 0:49 | 24180 | 15:29:15 | badge: Marsh |
| 0:49 | 24248 | 15:31:36 | obtained: Lapras |
| 0:49 | 24462 | 15:39:53 | reached: Route 21 |
| 0:50 | 24525 | 15:43:48 | reached: Cinnabar Island |
| 0:50 | 24537 | 15:44:09 | reached: Pokémon Mansion 1F |
| 0:59 | 26045 | 16:45:07 | badge: Volcano |
| 0:59 | 26305 | 17:02:40 | badge: Earth |
| 1:06 | 26517 | 17:15:11 | reached: Victory Road 1F |
| 1:06 | 26688 | 17:21:39 | reached: Victory Road 2F |
| 1:06 | 26793 | 17:26:13 | reached: Victory Road 3F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T07:21:12 | 60 | rotate | 26399 | 8.5M / 0.0M / 1509k |
| 2 | 2026-10-20T08:21:16 | 19 | exited | 6231 | 2.1M / 0.0M / 505k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11096 (asked Jev 8406, forced by code 2690, labelled 8406) · models jev-1.13.0 · input tokens 10590199 · Jev $0.4448
- Jev latency mean 74 ms · p50 65 · p95 136 · max 1897
- Fallbacks: none (variant without a safety net)
- Iteration 88
- Planner calls 0 ($0.0000, errors 0) · objective changes 123 · objectives Jev marked done 0 · final objective: Your team is weak (83% HP): heal at a Poké Center (walk in, talk to the nurse, answer YES).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1101 | 98% | 0.62 |
| faint_switch | 1 | 100% | 0.14 |
| intro | 54 | 37% | 0.43 |
| overworld | 7085 | 61% | 0.48 |
| prompt | 165 | 50% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1556)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 87 | 0.06 | 0.35 | 71% | `██████████████      ` |
| 0.1–0.2 | 864 | 0.15 | 0.26 | 59% | `████████████        ` |
| 0.2–0.3 | 1399 | 0.24 | 0.34 | 56% | `███████████         ` |
| 0.3–0.4 | 1292 | 0.34 | 0.43 | 55% | `███████████         ` |
| 0.4–0.5 | 946 | 0.45 | 0.52 | 61% | `████████████        ` |
| 0.5–0.6 | 844 | 0.54 | 0.62 | 69% | `██████████████      ` |
| 0.6–0.7 | 771 | 0.65 | 0.70 | 74% | `███████████████     ` |
| 0.7–0.8 | 655 | 0.74 | 0.78 | 84% | `█████████████████   ` |
| 0.8–0.9 | 562 | 0.84 | 0.87 | 88% | `██████████████████  ` |
| 0.9–1.0 | 986 | 0.96 | 0.97 | 66% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo-exp-cinnabar-leg-3__it75_end_state__CARRIED_it75_atlas__431e308_after-sabrina_jev-latest_20261019_181029)

- CLI: `jev-agent` jev_agent.py v2 · server commit `431e308` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:10:29 · ended 2026-10-19T18:11:20 · active 0:00 h · wall 0:00 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 461 · images 43 · reloads 0 · black-outs 0 · in-game playtime 21:33:07 · Pokédex 8 owned · maps visited 34
- Tokens uncached in / cache reads / out: 0.2M / 0.0M / 30k · cost $0.01 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 205/205 | 160 | 138 | 181 | 142 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 32 | 30 | 27 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 20 | 21:15:03 | reached: Celadon City |
| 0:00 | 26 | 21:15:20 | reached: Route 16 |
| 0:00 | 76 | 21:18:10 | reached: Route 7 |
| 0:00 | 90 | 21:18:33 | reached: Saffron City |
| 0:00 | 110 | 21:19:17 | reached: Silph Co. 1F |
| 0:00 | 165 | 21:20:40 | obtained: Lapras |
| 0:00 | 213 | 21:22:30 | reached: Route 6 |
| 0:00 | 226 | 21:22:54 | reached: Vermilion City |
| 0:00 | 247 | 21:23:39 | reached: Route 11 |
| 0:00 | 294 | 21:26:07 | reached: Route 2 |
| 0:00 | 327 | 21:27:17 | reached: Viridian City |
| 0:00 | 348 | 21:28:00 | reached: Route 1 |
| 0:00 | 358 | 21:28:41 | reached: Pallet Town |
| 0:00 | 373 | 21:29:09 | reached: Route 21 |
| 0:00 | 429 | 21:32:09 | reached: Cinnabar Island |
| 0:00 | 442 | 21:32:31 | reached: Pokémon Mansion 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 0.8 min, longest 1 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:10:29 | 1 | segment_goal | 460 | 0.2M / 0.0M / 30k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 162 (asked Jev 131, forced by code 31, labelled 131) · models jev-1.13.0 · input tokens 172480 · Jev $0.0072
- Jev latency mean 108 ms · p50 84 · p95 315 · max 614
- Fallbacks: none (variant without a safety net)
- Segment after-sabrina from state `caaa0771533ebba6` to `reached: Cinnabar Island`
- Planner calls 0 ($0.0000, errors 0) · objective changes 12 · objectives Jev marked done 0 · final objective: Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 11 | 100% | 0.67 |
| overworld | 102 | 86% | 0.64 |
| prompt | 18 | 39% | 0.33 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1808)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.1–0.2 | 3 | 0.16 | 0.30 | 67% | `█████████████       ` |
| 0.2–0.3 | 16 | 0.25 | 0.37 | 31% | `██████              ` |
| 0.3–0.4 | 13 | 0.34 | 0.44 | 38% | `████████            ` |
| 0.4–0.5 | 10 | 0.44 | 0.50 | 100% | `████████████████████` |
| 0.5–0.6 | 13 | 0.55 | 0.59 | 100% | `████████████████████` |
| 0.6–0.7 | 24 | 0.65 | 0.69 | 88% | `██████████████████  ` |
| 0.7–0.8 | 26 | 0.74 | 0.77 | 96% | `███████████████████ ` |
| 0.8–0.9 | 13 | 0.84 | 0.86 | 92% | `██████████████████  ` |
| 0.9–1.0 | 13 | 0.95 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo-exp-volcano-leg-3__cinnabar-leg-3_end_state__CARRIED_atlas__switch_YES-only_cinnabar-island_jev-latest_20261019_182823)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b9dd3ae` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:28:23 · ended 2026-10-19T18:33:56 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **manual**
- Tool calls 1243 · images 103 · reloads 0 · black-outs 0 · in-game playtime 22:13:09 · Pokédex 8 owned · maps visited 14
- Tokens uncached in / cache reads / out: 0.4M / 0.0M / 78k · cost $0.02 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 64 | 171/212 | 166 | 144 | 187 | 148 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 32 | 30 | 27 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 8 | 21:33:10 | reached: Pokémon Mansion 1F |
| 0:00 | 37 | 21:34:04 | reached: Cinnabar Island |
| 0:00 | 192 | 21:41:45 | reached: Route 21 |
| 0:00 | 425 | 21:47:51 | reached: Route 20 |
| 0:05 | 1236 | 22:13:00 | reached: Pallet Town |
| 0:05 | 1242 | 22:13:09 | reached: Route 1 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 5.5 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:28:23 | 6 | exited | 1243 | 0.4M / 0.0M / 78k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 420 (asked Jev 359, forced by code 61, labelled 359) · models jev-1.13.0 · input tokens 435890 · Jev $0.0183
- Jev latency mean 107 ms · p50 82 · p95 307 · max 705
- Fallbacks: none (variant without a safety net)
- Segment cinnabar-island from state `608074e749a01c9a` to `badge: Volcano`
- Planner calls 0 ($0.0000, errors 0) · objective changes 3 · objectives Jev marked done 0 · final objective: Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 25 | 100% | 0.66 |
| overworld | 333 | 63% | 0.31 |
| prompt | 1 | 100% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.248)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 5 | 0.07 | 0.22 | 60% | `████████████        ` |
| 0.1–0.2 | 119 | 0.15 | 0.24 | 64% | `█████████████       ` |
| 0.2–0.3 | 89 | 0.24 | 0.34 | 63% | `█████████████       ` |
| 0.3–0.4 | 44 | 0.34 | 0.46 | 57% | `███████████         ` |
| 0.4–0.5 | 24 | 0.45 | 0.53 | 62% | `████████████        ` |
| 0.5–0.6 | 23 | 0.54 | 0.62 | 70% | `██████████████      ` |
| 0.6–0.7 | 23 | 0.65 | 0.71 | 83% | `█████████████████   ` |
| 0.7–0.8 | 15 | 0.74 | 0.78 | 73% | `███████████████     ` |
| 0.8–0.9 | 7 | 0.83 | 0.88 | 71% | `██████████████      ` |
| 0.9–1.0 | 10 | 0.95 | 0.96 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo-exp-volcano-leg-2__cinnabar-leg-3_end_state__CARRIED_atlas__fab820b_cinnabar-island_jev-latest_20261019_182553)

- CLI: `jev-agent` jev_agent.py v2 · server commit `bd40038` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:25:53 · ended 2026-10-19T18:28:21 · active 0:02 h · wall 0:02 h · paused 0:00 h · exit: **manual**
- Tool calls 1275 · images 166 · reloads 0 · black-outs 0 · in-game playtime 22:11:36 · Pokédex 8 owned · maps visited 12
- Tokens uncached in / cache reads / out: 0.4M / 0.0M / 66k · cost $0.02 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 63 | 203/209 | 163 | 141 | 184 | 145 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 32 | 30 | 27 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 8 | 21:33:10 | reached: Pokémon Mansion 1F |
| 0:01 | 752 | 21:54:02 | reached: Cinnabar Island |
| 0:01 | 897 | 21:58:24 | reached: Route 21 |
| 0:01 | 1111 | 22:04:12 | reached: Route 20 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 2.4 min, longest 2 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:25:53 | 2 | exited | 1275 | 0.4M / 0.0M / 66k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 544 (asked Jev 381, forced by code 163, labelled 381) · models jev-1.13.0 · input tokens 397501 · Jev $0.0167
- Jev latency mean 111 ms · p50 86 · p95 332 · max 547
- Fallbacks: none (variant without a safety net)
- Segment cinnabar-island from state `608074e749a01c9a` to `badge: Volcano`
- Planner calls 0 ($0.0000, errors 0) · objective changes 3 · objectives Jev marked done 0 · final objective: Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 17 | 100% | 0.71 |
| overworld | 268 | 53% | 0.35 |
| prompt | 96 | 64% | 0.30 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1307)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 8 | 0.07 | 0.24 | 88% | `██████████████████  ` |
| 0.1–0.2 | 79 | 0.16 | 0.30 | 54% | `███████████         ` |
| 0.2–0.3 | 106 | 0.24 | 0.38 | 55% | `███████████         ` |
| 0.3–0.4 | 68 | 0.34 | 0.46 | 46% | `█████████           ` |
| 0.4–0.5 | 37 | 0.44 | 0.54 | 54% | `███████████         ` |
| 0.5–0.6 | 30 | 0.54 | 0.61 | 70% | `██████████████      ` |
| 0.6–0.7 | 18 | 0.63 | 0.69 | 78% | `████████████████    ` |
| 0.7–0.8 | 22 | 0.75 | 0.79 | 77% | `███████████████     ` |
| 0.8–0.9 | 8 | 0.87 | 0.90 | 62% | `████████████        ` |
| 0.9–1.0 | 5 | 0.94 | 0.95 | 80% | `████████████████    ` |

### jev-solo: jev-latest (jev-solo-exp-volcano-leg__cinnabar-leg-3_end_state__CARRIED_atlas__431e308_cinnabar-island_jev-latest_20261019_181140)

- CLI: `jev-agent` jev_agent.py v2 · server commit `431e308` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:11:40 · ended 2026-10-19T18:21:48 · active 0:10 h · wall 0:10 h · paused 0:00 h · exit: **manual**
- Tool calls 1356 · images 115 · reloads 0 · black-outs 0 · in-game playtime 22:21:04 · Pokédex 8 owned · maps visited 23
- Tokens uncached in / cache reads / out: 0.5M / 0.0M / 79k · cost $0.02 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 64 | 212/212 | 166 | 144 | 187 | 148 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 67/67 | 32 | 30 | 27 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 8 | 21:33:10 | reached: Pokémon Mansion 1F |
| 0:00 | 38 | 21:34:04 | reached: Cinnabar Island |
| 0:01 | 207 | 21:41:57 | reached: Route 21 |
| 0:01 | 495 | 21:48:28 | reached: Route 20 |
| 0:05 | 1078 | 22:08:42 | reached: Pallet Town |
| 0:05 | 1084 | 22:08:50 | reached: Route 1 |
| 0:05 | 1101 | 22:09:54 | reached: Viridian City |
| 0:05 | 1137 | 22:11:58 | reached: Route 22 |
| 0:06 | 1152 | 22:12:48 | reached: Route 23 |
| 0:08 | 1298 | 22:18:29 | reached: Route 2 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 10.1 min, longest 10 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:11:40 | 10 | exited | 1356 | 0.5M / 0.0M / 79k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 520 (asked Jev 408, forced by code 112, labelled 408) · models jev-1.13.0 · input tokens 479429 · Jev $0.0201
- Jev latency mean 108 ms · p50 84 · p95 207 · max 1126
- Fallbacks: none (variant without a safety net)
- Segment cinnabar-island from state `608074e749a01c9a` to `badge: Volcano`
- Planner calls 0 ($0.0000, errors 0) · objective changes 5 · objectives Jev marked done 0 · final objective: Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 32 | 100% | 0.65 |
| overworld | 374 | 61% | 0.31 |
| prompt | 2 | 100% | 0.61 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2128)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 7 | 0.07 | 0.21 | 86% | `█████████████████   ` |
| 0.1–0.2 | 97 | 0.15 | 0.27 | 60% | `████████████        ` |
| 0.2–0.3 | 118 | 0.24 | 0.35 | 63% | `█████████████       ` |
| 0.3–0.4 | 67 | 0.34 | 0.43 | 57% | `███████████         ` |
| 0.4–0.5 | 39 | 0.44 | 0.52 | 51% | `██████████          ` |
| 0.5–0.6 | 27 | 0.55 | 0.61 | 67% | `█████████████       ` |
| 0.6–0.7 | 18 | 0.63 | 0.68 | 89% | `██████████████████  ` |
| 0.7–0.8 | 14 | 0.74 | 0.78 | 93% | `███████████████████ ` |
| 0.8–0.9 | 13 | 0.85 | 0.87 | 92% | `██████████████████  ` |
| 0.9–1.0 | 8 | 0.94 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_it85_jev-latest_20261020_040017)

- CLI: `jev-agent` jev_agent.py v2 · server commit `4a02431` · prompt `49106d19e201a25e`
- Started 2026-10-20T04:00:17 · ended 2026-10-20T05:05:31 · active 1:05 h · wall 1:05 h · paused 0:00 h · exit: **manual**
- Tool calls 21510 · images 2082 · reloads 0 · black-outs 0 · in-game playtime 14:35:18 · Pokédex 4 owned · maps visited 149
- Tokens uncached in / cache reads / out: 6.8M / 0.0M / 1197k · cost $0.28 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 66 | 220/220 | 168 | 145 | 176 | 166 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAAAJJJJ (Lapras) | 15 | 65/65 | 34 | 32 | 26 | 37 | Water Gun, Thunderbolt, Surf, Ice Beam |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 102 | 0:00:25 | reached: Pallet Town |
| 0:00 | 139 | 0:02:26 | obtained: Charmander |
| 0:00 | 139 | 0:02:26 | starter: Charmander |
| 0:00 | 168 | 0:04:25 | reached: Route 1 |
| 0:00 | 185 | 0:06:01 | reached: Viridian City |
| 0:00 | 281 | 0:10:22 | reached: Route 2 |
| 0:00 | 393 | 0:19:26 | reached: Route 22 |
| 0:01 | 1124 | 0:55:20 | reached: Pewter City |
| 0:01 | 2100 | 1:25:36 | evolved: Charmander → Charmeleon |
| 0:01 | 2153 | 1:30:16 | badge: Boulder |
| 0:01 | 2162 | 1:30:38 | reached: Route 3 |
| 0:01 | 2254 | 1:38:12 | reached: Route 4 |
| 0:01 | 2258 | 1:38:20 | reached: Mt. Moon 1F |
| 0:02 | 3139 | 2:22:46 | reached: Route 23 |
| 0:03 | 3903 | 2:58:46 | reached: Cerulean City |
| 0:05 | 8291 | 5:41:15 | badge: Cascade |
| 0:05 | 8311 | 5:43:49 | reached: Route 24 |
| 0:05 | 8341 | 5:46:50 | evolved: Charmeleon → Charizard |
| 0:05 | 8391 | 5:49:58 | reached: Route 25 |
| 0:06 | 8635 | 6:01:58 | reached: Route 5 |
| 0:06 | 8653 | 6:02:31 | reached: Route 6 |
| 0:06 | 8689 | 6:05:05 | reached: Vermilion City |
| 0:06 | 8726 | 6:06:28 | reached: Vermilion Dock |
| 0:06 | 9114 | 6:24:56 | badge: Thunder |
| 0:06 | 9202 | 6:27:12 | reached: Route 9 |
| 0:06 | 9357 | 6:37:41 | reached: Route 10 |
| 0:06 | 9361 | 6:37:59 | reached: Rock Tunnel 1F |
| 0:06 | 9382 | 6:39:19 | reached: Rock Tunnel B1F |
| 0:11 | 11188 | 7:55:33 | reached: Route 11 |
| 0:11 | 11389 | 8:06:13 | reached: Lavender Town |
| 0:11 | 11425 | 8:07:21 | reached: Route 12 |
| 0:11 | 11566 | 8:10:26 | reached: Route 8 |
| 0:12 | 11677 | 8:18:46 | reached: Route 7 |
| 0:12 | 11683 | 8:18:55 | reached: Celadon City |
| 0:12 | 11926 | 8:33:05 | badge: Rainbow |
| 0:12 | 12012 | 8:36:12 | reached: Rocket Hideout B1F |
| 0:14 | 13384 | 9:17:56 | reached: Pokémon Tower 1F |
| 0:18 | 14509 | 10:06:08 | reached: Route 13 |
| 0:18 | 14590 | 10:13:23 | reached: Route 14 |
| 0:18 | 14647 | 10:17:36 | reached: Route 15 |
| 0:18 | 14660 | 10:18:02 | reached: Fuchsia City |
| 0:18 | 14804 | 10:29:38 | badge: Soul |
| 0:18 | 14816 | 10:30:39 | reached: Safari Zone Gate |
| 0:18 | 14823 | 10:31:00 | reached: Safari Zone Center |
| 0:18 | 14830 | 10:31:11 | reached: Safari Zone East |
| 0:18 | 14859 | 10:32:28 | reached: Safari Zone North |
| 0:18 | 14863 | 10:32:46 | reached: Safari Zone West |
| 0:18 | 15252 | 10:48:40 | reached: Route 19 |
| 0:18 | 15270 | 10:49:01 | reached: Route 18 |
| 0:21 | 16720 | 11:42:55 | reached: Saffron City |
| 0:21 | 16744 | 11:43:53 | reached: Silph Co. 1F |
| 0:25 | 18965 | 12:46:10 | badge: Marsh |
| 0:25 | 19024 | 12:48:31 | obtained: Lapras |
| 0:26 | 19331 | 13:01:36 | reached: Route 21 |
| 0:26 | 19420 | 13:07:35 | reached: Cinnabar Island |
| 0:26 | 19432 | 13:07:57 | reached: Pokémon Mansion 1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T04:00:17 | 60 | rotate | 21140 | 6.7M / 0.0M / 1193k |
| 2 | 2026-10-20T05:00:21 | 5 | exited | 367 | 0.0M / 0.0M / 3k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7932 (asked Jev 5685, forced by code 2247, labelled 5685) · models jev-1.13.0 · input tokens 6772130 · Jev $0.2844
- Jev latency mean 72 ms · p50 61 · p95 136 · max 586
- Fallbacks: none (variant without a safety net)
- Iteration 85
- Planner calls 0 ($0.0000, errors 0) · objective changes 94 · objectives Jev marked done 0 · final objective: Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 815 | 99% | 0.67 |
| intro | 53 | 57% | 0.39 |
| overworld | 4622 | 67% | 0.48 |
| prompt | 195 | 47% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1852)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 120 | 0.07 | 0.30 | 65% | `█████████████       ` |
| 0.1–0.2 | 690 | 0.15 | 0.27 | 60% | `████████████        ` |
| 0.2–0.3 | 885 | 0.24 | 0.35 | 59% | `████████████        ` |
| 0.3–0.4 | 691 | 0.34 | 0.44 | 61% | `████████████        ` |
| 0.4–0.5 | 599 | 0.44 | 0.53 | 67% | `█████████████       ` |
| 0.5–0.6 | 506 | 0.54 | 0.62 | 78% | `████████████████    ` |
| 0.6–0.7 | 474 | 0.64 | 0.70 | 80% | `████████████████    ` |
| 0.7–0.8 | 507 | 0.74 | 0.78 | 89% | `██████████████████  ` |
| 0.8–0.9 | 507 | 0.84 | 0.86 | 89% | `██████████████████  ` |
| 0.9–1.0 | 706 | 0.95 | 0.96 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it86_jev-latest_20261020_052446)

- CLI: `jev-agent` jev_agent.py v2 · server commit `0239adb` · prompt `49106d19e201a25e`
- Started 2026-10-20T05:24:46 · ended 2026-10-20T06:22:24 · active 0:57 h · wall 0:57 h · paused 0:00 h · exit: **manual**
- Tool calls 28979 · images 2198 · reloads 3 · black-outs 0 · in-game playtime 14:52:19 · Pokédex 4 owned · maps visited 156
- Tokens uncached in / cache reads / out: 9.2M / 0.0M / 1746k · cost $0.39 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 65 | 219/219 | 157 | 153 | 177 | 150 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAAAAAAA (Lapras) | 15 | 67/67 | 32 | 30 | 25 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 69 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:17 | reached: Pallet Town |
| 0:00 | 128 | 0:02:32 | obtained: Charmander |
| 0:00 | 128 | 0:02:32 | starter: Charmander |
| 0:00 | 156 | 0:04:29 | reached: Route 1 |
| 0:00 | 173 | 0:06:09 | reached: Viridian City |
| 0:00 | 272 | 0:11:36 | reached: Route 2 |
| 0:00 | 447 | 0:22:16 | reached: Pewter City |
| 0:00 | 574 | 0:29:03 | reached: Route 22 |
| 0:00 | 1338 | 0:52:00 | evolved: Charmander → Charmeleon |
| 0:02 | 3428 | 1:49:11 | badge: Boulder |
| 0:02 | 3437 | 1:49:33 | reached: Route 3 |
| 0:02 | 3502 | 1:56:19 | reached: Route 4 |
| 0:02 | 3506 | 1:56:27 | reached: Mt. Moon 1F |
| 0:02 | 3863 | 2:16:18 | reached: Cerulean City |
| 0:04 | 7960 | 4:46:52 | badge: Cascade |
| 0:04 | 7996 | 4:49:30 | reached: Route 24 |
| 0:04 | 8076 | 4:55:34 | reached: Route 25 |
| 0:04 | 8129 | 5:00:10 | evolved: Charmeleon → Charizard |
| 0:04 | 8412 | 5:10:09 | reached: Route 5 |
| 0:04 | 8431 | 5:10:41 | reached: Route 6 |
| 0:04 | 8466 | 5:13:21 | reached: Vermilion City |
| 0:04 | 8504 | 5:14:44 | reached: Vermilion Dock |
| 0:05 | 8898 | 5:33:22 | badge: Thunder |
| 0:05 | 8950 | 5:34:59 | reached: Route 9 |
| 0:05 | 9097 | 5:47:45 | reached: Route 10 |
| 0:05 | 9101 | 5:48:04 | reached: Rock Tunnel 1F |
| 0:05 | 9128 | 5:49:55 | reached: Rock Tunnel B1F |
| 0:08 | 10692 | 7:03:26 | reached: Route 11 |
| 0:09 | 11381 | 7:33:44 | reached: Lavender Town |
| 0:09 | 11450 | 7:35:22 | reached: Route 8 |
| 0:11 | 11725 | 7:51:24 | reached: Route 12 |
| 0:11 | 11784 | 7:52:38 | reached: Pokémon Tower 1F |
| 0:12 | 12485 | 8:45:10 | reached: Route 7 |
| 0:12 | 12491 | 8:45:19 | reached: Celadon City |
| 0:12 | 12652 | 8:55:30 | badge: Rainbow |
| 0:13 | 12773 | 9:00:03 | reached: Rocket Hideout B1F |
| 0:21 | 15074 | 10:17:22 | reached: Route 13 |
| 0:21 | 15155 | 10:24:45 | reached: Route 14 |
| 0:21 | 15221 | 10:29:07 | reached: Route 15 |
| 0:21 | 15406 | 10:43:11 | reached: Fuchsia City |
| 0:21 | 15548 | 10:54:51 | badge: Soul |
| 0:21 | 15556 | 10:55:34 | reached: Safari Zone Gate |
| 0:21 | 15563 | 10:55:55 | reached: Safari Zone Center |
| 0:21 | 15619 | 10:58:14 | reached: Safari Zone East |
| 0:21 | 15623 | 10:58:43 | reached: Safari Zone North |
| 0:21 | 15635 | 10:59:15 | reached: Safari Zone West |
| 0:22 | 15859 | 11:08:33 | reached: Route 19 |
| 0:22 | 15868 | 11:08:48 | reached: Route 18 |
| 0:33 | 17599 | 12:04:34 | reached: Saffron City |
| 0:33 | 17628 | 12:05:42 | reached: Silph Co. 1F |
| 0:52 | 21044 | 13:46:37 | badge: Marsh |
| 0:52 | 21093 | 13:48:18 | obtained: Lapras |
| 0:53 | 21242 | 13:55:06 | reached: Route 21 |
| 0:53 | 21299 | 13:58:36 | reached: Cinnabar Island |
| 0:53 | 21311 | 13:58:58 | reached: Pokémon Mansion 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 57.6 min, longest 58 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T05:24:46 | 58 | exited | 28979 | 9.2M / 0.0M / 1746k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 9230 (asked Jev 7317, forced by code 1913, labelled 7317) · models jev-1.13.0 · input tokens 9211563 · Jev $0.3869
- Jev latency mean 71 ms · p50 61 · p95 136 · max 422
- Fallbacks: none (variant without a safety net)
- Iteration 86
- Planner calls 0 ($0.0000, errors 0) · objective changes 161 · objectives Jev marked done 0 · final objective: Your team is weak (100% HP, your strongest Pokémon at 100%): heal at a Poké Center (walk in, talk to the nurse, answer YES).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 842 | 97% | 0.64 |
| intro | 49 | 49% | 0.42 |
| overworld | 6274 | 64% | 0.46 |
| prompt | 152 | 53% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2062)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 85 | 0.07 | 0.27 | 69% | `██████████████      ` |
| 0.1–0.2 | 1048 | 0.15 | 0.24 | 62% | `████████████        ` |
| 0.2–0.3 | 1326 | 0.24 | 0.32 | 60% | `████████████        ` |
| 0.3–0.4 | 995 | 0.34 | 0.42 | 59% | `████████████        ` |
| 0.4–0.5 | 870 | 0.44 | 0.51 | 65% | `█████████████       ` |
| 0.5–0.6 | 616 | 0.54 | 0.60 | 71% | `██████████████      ` |
| 0.6–0.7 | 540 | 0.65 | 0.70 | 78% | `████████████████    ` |
| 0.7–0.8 | 525 | 0.74 | 0.78 | 87% | `█████████████████   ` |
| 0.8–0.9 | 467 | 0.84 | 0.87 | 90% | `██████████████████  ` |
| 0.9–1.0 | 845 | 0.96 | 0.96 | 67% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo-exp-lavender-train-5__benchmark_end_state__CARRIED_all__5bd1aac_jev-latest_20261020_204733)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T21:19:23 · active 2:45 h · wall 7:43 h · paused 0:00 h · exit: **manual**
- Tool calls 22530 · images 1818 · reloads 1 · black-outs 0 · in-game playtime 13:17:15 · Pokédex 5 owned · maps visited 142
- Tokens uncached in / cache reads / out: 7.2M / 0.0M / 1315k · cost $0.30 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 210/210 | 151 | 141 | 181 | 151 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |
| 3 | AAAAAAAAAA (Lapras) | 15 | 65/65 | 34 | 32 | 25 | 36 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |
| 2:45 | 22406 | 13:11:55 | badge: Marsh |
| 2:45 | 22455 | 13:14:00 | obtained: Lapras |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 2 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |
| 4 | 2026-10-20T20:47:33 | 32 | exited | 2527 | 0.6M / 0.0M / 96k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7338 (asked Jev 5885, forced by code 1453, labelled 5885) · models jev-1.13.0 · input tokens 7252689 · Jev $0.3046
- Jev latency mean 132 ms · p50 76 · p95 327 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 90 · objectives Jev marked done 0 · final objective: Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 827 | 94% | 0.68 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4848 | 58% | 0.53 |
| prompt | 153 | 48% | 0.45 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1333)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 37 | 0.08 | 0.22 | 57% | `███████████         ` |
| 0.1–0.2 | 408 | 0.16 | 0.25 | 57% | `███████████         ` |
| 0.2–0.3 | 848 | 0.25 | 0.33 | 49% | `██████████          ` |
| 0.3–0.4 | 874 | 0.34 | 0.42 | 47% | `█████████           ` |
| 0.4–0.5 | 668 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 549 | 0.54 | 0.60 | 68% | `██████████████      ` |
| 0.6–0.7 | 483 | 0.65 | 0.70 | 82% | `████████████████    ` |
| 0.7–0.8 | 585 | 0.74 | 0.78 | 80% | `████████████████    ` |
| 0.8–0.9 | 672 | 0.84 | 0.87 | 73% | `███████████████     ` |
| 0.9–1.0 | 761 | 0.95 | 0.96 | 67% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it75_jev-latest_20261019_075901)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b619d40` · prompt `49106d19e201a25e`
- Started 2026-10-19T07:59:01 · ended 2026-10-19T17:55:13 · active 5:13 h · wall 9:56 h · paused 0:00 h · exit: **stuck**
- Tool calls 51842 · images 4942 · reloads 17 · black-outs 0 · in-game playtime 21:14:25 · Pokédex 7 owned · maps visited 164
- Tokens uncached in / cache reads / out: 24.9M / 0.0M / 5153k · cost $1.05 · chunks 7

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 111/205 | 160 | 138 | 181 | 142 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 97 | 0:00:18 | reached: Pallet Town |
| 0:00 | 134 | 0:02:19 | obtained: Charmander |
| 0:00 | 134 | 0:02:19 | starter: Charmander |
| 0:00 | 162 | 0:04:17 | reached: Route 1 |
| 0:00 | 185 | 0:06:22 | reached: Viridian City |
| 0:00 | 267 | 0:10:22 | reached: Route 2 |
| 0:00 | 295 | 0:11:24 | reached: Route 22 |
| 0:02 | 1846 | 0:42:59 | reached: Pewter City |
| 0:02 | 2680 | 1:18:49 | evolved: Charmander → Charmeleon |
| 0:02 | 2687 | 1:19:18 | badge: Boulder |
| 0:02 | 2712 | 1:20:12 | reached: Route 3 |
| 0:02 | 2820 | 1:28:46 | reached: Route 4 |
| 0:02 | 2824 | 1:28:55 | reached: Mt. Moon 1F |
| 0:03 | 3349 | 1:57:25 | reached: Route 23 |
| 0:05 | 4209 | 2:23:16 | reached: Cerulean City |
| 0:07 | 8650 | 5:09:00 | badge: Cascade |
| 0:07 | 8688 | 5:11:34 | reached: Route 24 |
| 0:09 | 9508 | 5:41:17 | reached: Route 25 |
| 0:09 | 9563 | 5:46:20 | evolved: Charmeleon → Charizard |
| 0:09 | 9736 | 5:52:07 | reached: Route 5 |
| 0:09 | 9765 | 5:52:55 | reached: Route 9 |
| 0:10 | 10060 | 6:03:57 | reached: Route 6 |
| 0:10 | 10182 | 6:10:18 | reached: Vermilion City |
| 0:10 | 10212 | 6:11:21 | reached: Vermilion Dock |
| 0:10 | 10469 | 6:26:32 | badge: Thunder |
| 0:10 | 10506 | 6:27:27 | reached: Route 11 |
| 0:12 | 11432 | 6:59:26 | reached: Route 12 |
| 0:18 | 13633 | 8:17:59 | reached: Route 10 |
| 0:18 | 13638 | 8:18:17 | reached: Rock Tunnel 1F |
| 0:18 | 13682 | 8:20:17 | reached: Rock Tunnel B1F |
| 0:24 | 15976 | 9:57:55 | reached: Lavender Town |
| 0:24 | 16155 | 10:02:08 | reached: Route 8 |
| 0:25 | 16382 | 10:14:44 | reached: Pokémon Tower 1F |
| 0:33 | 17879 | 11:13:38 | reached: Route 7 |
| 0:33 | 17885 | 11:13:47 | reached: Celadon City |
| 0:33 | 18080 | 11:24:31 | reached: Route 16 |
| 0:36 | 19157 | 12:03:22 | badge: Rainbow |
| 0:37 | 19266 | 12:07:42 | reached: Rocket Hideout B1F |
| 0:44 | 21602 | 13:34:53 | reached: Route 13 |
| 0:44 | 21665 | 13:40:57 | reached: Route 14 |
| 0:44 | 21823 | 13:49:56 | reached: Route 15 |
| 0:57 | 23605 | 15:04:50 | reached: Fuchsia City |
| 0:57 | 23740 | 15:16:15 | badge: Soul |
| 0:57 | 23752 | 15:17:16 | reached: Safari Zone Gate |
| 0:57 | 23759 | 15:17:37 | reached: Safari Zone Center |
| 0:57 | 23795 | 15:18:26 | reached: Safari Zone East |
| 0:57 | 23830 | 15:20:01 | reached: Safari Zone North |
| 0:57 | 23871 | 15:21:48 | obtained: Nidoran♂ |
| 0:57 | 23897 | 15:22:50 | obtained: Paras |
| 0:57 | 23997 | 15:27:56 | obtained: Doduo |
| 0:57 | 24048 | 15:30:27 | obtained: Nidoran♀ |
| 0:57 | 24070 | 15:32:06 | reached: Safari Zone West |
| 0:59 | 25621 | 16:17:24 | reached: Saffron City |
| 0:59 | 25649 | 16:18:28 | reached: Silph Co. 1F |
| 1:03 | 28318 | 17:30:50 | badge: Marsh |

**CLI chunks:** 7 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 4 rotate, 2 exited, 1 stuck; median 60.0 min, longest 77 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T07:59:02 | 60 | rotate | 25940 | 8.5M / 0.0M / 1563k |
| 2 | 2026-10-19T08:59:07 | 77 | rotate | 8031 | 4.5M / 0.0M / 923k |
| 3 | 2026-10-19T10:29:10 | 7 | exited | 202 | 0.1M / 0.0M / 33k |
| 4 | 2026-10-19T10:52:13 | 60 | rotate | 5402 | 3.6M / 0.0M / 803k |
| 5 | 2026-10-19T11:52:16 | 60 | rotate | 4329 | 2.7M / 0.0M / 607k |
| 6 | 2026-10-19T12:52:20 | 54 | exited | 5512 | 3.6M / 0.0M / 787k |
| 7 | 2026-10-19T17:35:56 | 19 | stuck | 2421 | 1.9M / 0.0M / 436k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 20725 (asked Jev 18428, forced by code 2297, labelled 18428) · models jev-1.13.0 · input tokens 24908390 · Jev $1.0462
- Jev latency mean 136 ms · p50 112 · p95 224 · max 32323
- Fallbacks: none (variant without a safety net)
- Iteration 75
- Planner calls 0 ($0.0000, errors 0) · objective changes 97 · objectives Jev marked done 0 · final objective: Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 727 | 98% | 0.71 |
| intro | 52 | 54% | 0.40 |
| overworld | 17419 | 60% | 0.34 |
| prompt | 230 | 63% | 0.45 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2135)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 459 | 0.08 | 0.17 | 56% | `███████████         ` |
| 0.1–0.2 | 4825 | 0.15 | 0.21 | 55% | `███████████         ` |
| 0.2–0.3 | 4528 | 0.24 | 0.30 | 54% | `███████████         ` |
| 0.3–0.4 | 2597 | 0.34 | 0.40 | 55% | `███████████         ` |
| 0.4–0.5 | 1575 | 0.44 | 0.50 | 62% | `████████████        ` |
| 0.5–0.6 | 1071 | 0.54 | 0.60 | 71% | `██████████████      ` |
| 0.6–0.7 | 986 | 0.65 | 0.69 | 80% | `████████████████    ` |
| 0.7–0.8 | 975 | 0.74 | 0.78 | 84% | `█████████████████   ` |
| 0.8–0.9 | 735 | 0.84 | 0.86 | 89% | `██████████████████  ` |
| 0.9–1.0 | 677 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-cinnabar-leg-2__it75_end_state__CARRIED_it75_atlas__f02531f_after-sabrina_jev-latest_20261019_180524)

- CLI: `jev-agent` jev_agent.py v2 · server commit `f02531f` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:05:25 · ended 2026-10-19T18:10:28 · active 0:04 h · wall 0:05 h · paused 0:00 h · exit: **manual**
- Tool calls 422 · images 34 · reloads 0 · black-outs 0 · in-game playtime 21:27:28 · Pokédex 8 owned · maps visited 21
- Tokens uncached in / cache reads / out: 0.2M / 0.0M / 27k · cost $0.01 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 205/205 | 160 | 138 | 181 | 142 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 66/66 | 31 | 29 | 24 | 35 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 21 | 21:15:03 | reached: Celadon City |
| 0:00 | 26 | 21:15:20 | reached: Route 16 |
| 0:00 | 55 | 21:17:32 | reached: Route 7 |
| 0:00 | 69 | 21:17:54 | reached: Saffron City |
| 0:00 | 89 | 21:18:39 | reached: Silph Co. 1F |
| 0:00 | 140 | 21:19:56 | obtained: Lapras |
| 0:01 | 216 | 21:22:55 | reached: Route 6 |
| 0:02 | 249 | 21:23:24 | reached: Route 5 |
| 0:02 | 260 | 21:23:39 | reached: Route 8 |
| 0:03 | 309 | 21:24:51 | reached: Vermilion City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 5.0 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:05:25 | 5 | exited | 422 | 0.2M / 0.0M / 27k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 131 (asked Jev 120, forced by code 11, labelled 120) · models jev-1.13.0 · input tokens 151534 · Jev $0.0064
- Jev latency mean 118 ms · p50 80 · p95 333 · max 2156
- Fallbacks: none (variant without a safety net)
- Segment after-sabrina from state `caaa0771533ebba6` to `reached: Cinnabar Island`
- Planner calls 0 ($0.0000, errors 0) · objective changes 8 · objectives Jev marked done 0 · final objective: Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 103 | 61% | 0.46 |
| prompt | 17 | 35% | 0.30 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1225)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 2 | 0.06 | 0.45 | 0% | `                    ` |
| 0.1–0.2 | 14 | 0.18 | 0.30 | 7% | `█                   ` |
| 0.2–0.3 | 20 | 0.24 | 0.35 | 45% | `█████████           ` |
| 0.3–0.4 | 28 | 0.34 | 0.42 | 46% | `█████████           ` |
| 0.4–0.5 | 15 | 0.44 | 0.53 | 67% | `█████████████       ` |
| 0.5–0.6 | 10 | 0.54 | 0.59 | 80% | `████████████████    ` |
| 0.6–0.7 | 9 | 0.64 | 0.71 | 100% | `████████████████████` |
| 0.7–0.8 | 8 | 0.73 | 0.76 | 75% | `███████████████     ` |
| 0.8–0.9 | 10 | 0.84 | 0.86 | 90% | `██████████████████  ` |
| 0.9–1.0 | 4 | 0.94 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo-exp-cinnabar-leg__it75_end_state__CARRIED_it75_atlas_after-sabrina_jev-latest_20261019_175858)

- CLI: `jev-agent` jev_agent.py v2 · server commit `0c91ca3` · prompt `49106d19e201a25e`
- Started 2026-10-19T17:58:58 · ended 2026-10-19T18:05:11 · active 0:06 h · wall 0:06 h · paused 0:00 h · exit: **manual**
- Tool calls 495 · images 35 · reloads 0 · black-outs 0 · in-game playtime 21:29:56 · Pokédex 8 owned · maps visited 22
- Tokens uncached in / cache reads / out: 0.2M / 0.0M / 33k · cost $0.01 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 205/205 | 160 | 138 | 181 | 142 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAAAAAA (Lapras) | 15 | 66/66 | 32 | 32 | 26 | 35 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 21 | 21:15:03 | reached: Celadon City |
| 0:00 | 26 | 21:15:20 | reached: Route 16 |
| 0:00 | 55 | 21:17:32 | reached: Route 7 |
| 0:00 | 69 | 21:17:54 | reached: Saffron City |
| 0:00 | 89 | 21:18:39 | reached: Silph Co. 1F |
| 0:00 | 146 | 21:20:03 | obtained: Lapras |
| 0:01 | 247 | 21:23:44 | reached: Route 6 |
| 0:02 | 282 | 21:24:12 | reached: Route 5 |
| 0:02 | 293 | 21:24:27 | reached: Route 8 |
| 0:03 | 348 | 21:25:54 | reached: Vermilion City |
| 0:04 | 420 | 21:28:02 | reached: Route 11 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 6.2 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T17:58:58 | 6 | exited | 495 | 0.2M / 0.0M / 33k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 160 (asked Jev 149, forced by code 11, labelled 149) · models jev-1.13.0 · input tokens 183458 · Jev $0.0077
- Jev latency mean 105 ms · p50 87 · p95 247 · max 641
- Fallbacks: none (variant without a safety net)
- Segment after-sabrina from state `caaa0771533ebba6` to `reached: Cinnabar Island`
- Planner calls 0 ($0.0000, errors 0) · objective changes 8 · objectives Jev marked done 0 · final objective: Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 130 | 57% | 0.45 |
| prompt | 19 | 37% | 0.32 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.0906)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 1 | 0.08 | 0.16 | 100% | `████████████████████` |
| 0.1–0.2 | 18 | 0.16 | 0.28 | 39% | `████████            ` |
| 0.2–0.3 | 29 | 0.24 | 0.34 | 31% | `██████              ` |
| 0.3–0.4 | 27 | 0.34 | 0.43 | 33% | `███████             ` |
| 0.4–0.5 | 22 | 0.45 | 0.53 | 59% | `████████████        ` |
| 0.5–0.6 | 17 | 0.54 | 0.60 | 65% | `█████████████       ` |
| 0.6–0.7 | 11 | 0.63 | 0.71 | 82% | `████████████████    ` |
| 0.7–0.8 | 11 | 0.75 | 0.77 | 100% | `████████████████████` |
| 0.8–0.9 | 9 | 0.87 | 0.89 | 78% | `████████████████    ` |
| 0.9–1.0 | 4 | 0.94 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo-exp-lapras-check__it75_end_state__blank_atlas_after-sabrina_jev-latest_20261019_175611)

- CLI: `jev-agent` jev_agent.py v2 · server commit `0c91ca3` · prompt `49106d19e201a25e`
- Started 2026-10-19T17:56:11 · ended 2026-10-19T17:59:08 · active 0:02 h · wall 0:02 h · paused 0:00 h · exit: **manual**
- Tool calls 2612 · images 76 · reloads 0 · black-outs 0 · in-game playtime 22:20:25 · Pokédex 8 owned · maps visited 59
- Tokens uncached in / cache reads / out: 0.8M / 0.0M / 160k · cost $0.04 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 62 | 205/205 | 160 | 138 | 181 | 142 | Slash, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 35 | 31 | 36 | 24 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 3 | AAAAAAAAAA (Paras) | 22 | 51/51 | 38 | 30 | 21 | 30 | Scratch, Stun Spore, Leech Life |
| 4 | AAAAAAAAAA (Doduo) | 26 | 55/55 | 51 | 30 | 47 | 23 | Peck, Growl, Fury Attack |
| 5 | AAAAAAAAAA (Nidoran♀) | 24 | 64/64 | 30 | 35 | 31 | 30 | Tackle, Scratch, Poison Sting, Tail Whip |
| 6 | AAAAAJJJJJ (Lapras) | 15 | 64/64 | 33 | 33 | 26 | 34 | Water Gun, Growl, Surf |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 41 | 21:16:48 | reached: Celadon City |
| 0:00 | 46 | 21:16:53 | reached: Route 7 |
| 0:00 | 542 | 21:23:27 | reached: Saffron City |
| 0:00 | 566 | 21:24:22 | reached: Silph Co. 1F |
| 0:00 | 608 | 21:25:36 | obtained: Lapras |
| 0:00 | 694 | 21:27:48 | reached: Route 6 |
| 0:00 | 716 | 21:28:11 | reached: Route 8 |
| 0:00 | 738 | 21:28:35 | reached: Route 5 |
| 0:01 | 1460 | 21:44:42 | reached: Lavender Town |
| 0:01 | 1481 | 21:45:19 | reached: Route 12 |
| 0:01 | 1500 | 21:45:45 | reached: Route 10 |
| 0:01 | 1508 | 21:45:54 | reached: Pokémon Tower 1F |
| 0:01 | 1838 | 21:55:58 | reached: Route 16 |
| 0:02 | 2514 | 22:14:44 | reached: Rocket Hideout B1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 2.9 min, longest 3 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T17:56:11 | 3 | exited | 2612 | 0.8M / 0.0M / 160k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 728 (asked Jev 639, forced by code 89, labelled 639) · models jev-1.13.0 · input tokens 847651 · Jev $0.0356
- Jev latency mean 92 ms · p50 83 · p95 168 · max 406
- Fallbacks: none (variant without a safety net)
- Segment after-sabrina from state `caaa0771533ebba6` to `reached: Cinnabar Island`
- Planner calls 0 ($0.0000, errors 0) · objective changes 8 · objectives Jev marked done 0 · final objective: Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 614 | 58% | 0.41 |
| prompt | 25 | 56% | 0.36 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1405)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 13 | 0.07 | 0.41 | 46% | `█████████           ` |
| 0.1–0.2 | 75 | 0.15 | 0.31 | 53% | `███████████         ` |
| 0.2–0.3 | 125 | 0.24 | 0.35 | 59% | `████████████        ` |
| 0.3–0.4 | 118 | 0.35 | 0.46 | 56% | `███████████         ` |
| 0.4–0.5 | 102 | 0.44 | 0.52 | 61% | `████████████        ` |
| 0.5–0.6 | 80 | 0.55 | 0.61 | 54% | `███████████         ` |
| 0.6–0.7 | 58 | 0.65 | 0.69 | 59% | `████████████        ` |
| 0.7–0.8 | 35 | 0.75 | 0.78 | 66% | `█████████████       ` |
| 0.8–0.9 | 23 | 0.84 | 0.86 | 65% | `█████████████       ` |
| 0.9–1.0 | 10 | 0.95 | 0.95 | 90% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_it89_jev-latest_20261020_090139)

- CLI: `jev-agent` jev_agent.py v2 · server commit `2829d9c` · prompt `49106d19e201a25e`
- Started 2026-10-20T09:01:39 · ended 2026-10-20T10:10:01 · active 1:05 h · wall 1:08 h · paused 0:00 h · exit: **manual**
- Tool calls 19923 · images 1830 · reloads 0 · black-outs 0 · in-game playtime 13:31:01 · Pokédex 3 owned · maps visited 152
- Tokens uncached in / cache reads / out: 6.4M / 0.0M / 1130k · cost $0.27 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 58 | 163/190 | 149 | 140 | 166 | 130 | Strength, Slash, Flamethrower, Cut |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 75 | 0:00:03 | game started |
| 0:00 | 100 | 0:00:21 | reached: Pallet Town |
| 0:00 | 142 | 0:02:36 | obtained: Charmander |
| 0:00 | 142 | 0:02:36 | starter: Charmander |
| 0:00 | 170 | 0:04:44 | reached: Route 1 |
| 0:00 | 181 | 0:05:39 | reached: Viridian City |
| 0:00 | 274 | 0:10:22 | reached: Route 2 |
| 0:00 | 390 | 0:17:39 | reached: Route 22 |
| 0:01 | 1098 | 0:47:36 | reached: Pewter City |
| 0:01 | 1173 | 0:54:13 | badge: Boulder |
| 0:01 | 1182 | 0:54:34 | reached: Route 3 |
| 0:01 | 1274 | 1:03:34 | evolved: Charmander → Charmeleon |
| 0:01 | 1341 | 1:07:38 | reached: Route 4 |
| 0:01 | 1345 | 1:07:47 | reached: Mt. Moon 1F |
| 0:01 | 1834 | 1:35:54 | reached: Route 23 |
| 0:02 | 2410 | 2:02:26 | reached: Cerulean City |
| 0:05 | 7972 | 5:22:23 | badge: Cascade |
| 0:05 | 8002 | 5:24:33 | reached: Route 24 |
| 0:05 | 8044 | 5:27:33 | evolved: Charmeleon → Charizard |
| 0:05 | 8098 | 5:30:31 | reached: Route 25 |
| 0:06 | 8320 | 5:41:40 | reached: Route 5 |
| 0:06 | 8338 | 5:42:13 | reached: Route 6 |
| 0:06 | 8389 | 5:45:31 | reached: Vermilion City |
| 0:06 | 8427 | 5:46:54 | reached: Vermilion Dock |
| 0:06 | 8668 | 6:00:19 | badge: Thunder |
| 0:06 | 8716 | 6:01:52 | reached: Route 9 |
| 0:06 | 8775 | 6:05:26 | reached: Route 10 |
| 0:06 | 8779 | 6:05:44 | reached: Rock Tunnel 1F |
| 0:06 | 8815 | 6:07:45 | reached: Rock Tunnel B1F |
| 0:10 | 9885 | 6:50:09 | reached: Route 11 |
| 0:11 | 10212 | 7:02:18 | reached: Route 12 |
| 0:20 | 12945 | 8:58:19 | reached: Lavender Town |
| 0:21 | 13147 | 9:03:02 | reached: Route 8 |
| 0:21 | 13235 | 9:08:06 | reached: Route 7 |
| 0:21 | 13241 | 9:08:15 | reached: Celadon City |
| 0:21 | 13403 | 9:17:42 | badge: Rainbow |
| 0:22 | 13534 | 9:23:06 | reached: Rocket Hideout B1F |
| 0:22 | 13987 | 9:43:57 | reached: Pokémon Tower 1F |
| 0:29 | 15491 | 10:43:05 | reached: Route 13 |
| 0:29 | 15602 | 10:50:31 | reached: Route 14 |
| 0:29 | 15678 | 10:55:01 | reached: Route 15 |
| 0:29 | 15691 | 10:55:27 | reached: Fuchsia City |
| 0:30 | 15884 | 11:08:06 | badge: Soul |
| 0:30 | 15897 | 11:09:05 | reached: Safari Zone Gate |
| 0:30 | 15904 | 11:09:26 | reached: Safari Zone Center |
| 0:30 | 15911 | 11:09:37 | reached: Safari Zone East |
| 0:30 | 15931 | 11:10:37 | reached: Safari Zone North |
| 0:30 | 15943 | 11:11:09 | reached: Safari Zone West |
| 0:31 | 16902 | 11:49:51 | reached: Saffron City |
| 0:31 | 16933 | 11:50:54 | reached: Silph Co. 1F |
| 0:47 | 19155 | 13:04:27 | reached: Route 16 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 65.5 min, longest 66 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T09:01:39 | 66 | rotate | 19789 | 6.3M / 0.0M / 1118k |
| 2 | 2026-10-20T10:07:14 | 3 | exited | 133 | 0.1M / 0.0M / 12k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6795 (asked Jev 5260, forced by code 1535, labelled 5260) · models jev-1.13.0 · input tokens 6365749 · Jev $0.2674
- Jev latency mean 77 ms · p50 67 · p95 140 · max 472
- Fallbacks: none (variant without a safety net)
- Iteration 89
- Planner calls 0 ($0.0000, errors 0) · objective changes 74 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it (face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 817 | 98% | 0.70 |
| intro | 55 | 47% | 0.42 |
| overworld | 4315 | 59% | 0.49 |
| prompt | 73 | 57% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1376)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 60 | 0.08 | 0.21 | 63% | `█████████████       ` |
| 0.1–0.2 | 614 | 0.15 | 0.24 | 50% | `██████████          ` |
| 0.2–0.3 | 788 | 0.24 | 0.33 | 51% | `██████████          ` |
| 0.3–0.4 | 659 | 0.34 | 0.43 | 50% | `██████████          ` |
| 0.4–0.5 | 513 | 0.44 | 0.52 | 56% | `███████████         ` |
| 0.5–0.6 | 466 | 0.54 | 0.62 | 68% | `██████████████      ` |
| 0.6–0.7 | 440 | 0.65 | 0.70 | 80% | `████████████████    ` |
| 0.7–0.8 | 497 | 0.74 | 0.78 | 88% | `██████████████████  ` |
| 0.8–0.9 | 479 | 0.84 | 0.86 | 88% | `██████████████████  ` |
| 0.9–1.0 | 744 | 0.96 | 0.96 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_jev-latest_20261020_133617)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T15:50:40 · active 2:14 h · wall 2:14 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 20003 · images 1554 · reloads 1 · black-outs 0 · in-game playtime 11:57:48 · Pokédex 4 owned · maps visited 142
- Tokens uncached in / cache reads / out: 6.7M / 0.0M / 1219k · cost $0.28 · chunks 3

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 59 | 198/198 | 143 | 133 | 170 | 141 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |

**CLI chunks:** 3 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 1 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6563 (asked Jev 5391, forced by code 1172, labelled 5391) · models jev-1.13.0 · input tokens 6697616 · Jev $0.2813
- Jev latency mean 136 ms · p50 76 · p95 339 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 73 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 62 (now 59).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 706 | 95% | 0.69 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4489 | 57% | 0.51 |
| prompt | 139 | 50% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1258)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 34 | 0.08 | 0.20 | 56% | `███████████         ` |
| 0.1–0.2 | 403 | 0.16 | 0.25 | 57% | `███████████         ` |
| 0.2–0.3 | 818 | 0.25 | 0.33 | 49% | `██████████          ` |
| 0.3–0.4 | 839 | 0.34 | 0.42 | 47% | `█████████           ` |
| 0.4–0.5 | 641 | 0.44 | 0.51 | 55% | `███████████         ` |
| 0.5–0.6 | 516 | 0.54 | 0.60 | 66% | `█████████████       ` |
| 0.6–0.7 | 453 | 0.65 | 0.70 | 81% | `████████████████    ` |
| 0.7–0.8 | 546 | 0.74 | 0.78 | 79% | `████████████████    ` |
| 0.8–0.9 | 543 | 0.84 | 0.87 | 72% | `██████████████      ` |
| 0.9–1.0 | 598 | 0.95 | 0.96 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-lavender-train__benchmark_end_state__CARRIED_all__3509ac3_jev-latest_20261020_192600)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T19:41:13 · active 2:28 h · wall 6:04 h · paused 0:00 h · exit: **manual**
- Tool calls 20911 · images 1637 · reloads 1 · black-outs 0 · in-game playtime 12:28:16 · Pokédex 4 owned · maps visited 142
- Tokens uncached in / cache reads / out: 6.9M / 0.0M / 1258k · cost $0.29 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 60 | 181/202 | 146 | 135 | 173 | 144 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 2 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |
| 4 | 2026-10-20T19:26:33 | 15 | exited | 908 | 0.2M / 0.0M / 39k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6845 (asked Jev 5587, forced by code 1258, labelled 5587) · models jev-1.13.0 · input tokens 6922604 · Jev $0.2908
- Jev latency mean 135 ms · p50 76 · p95 335 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 76 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 62 (now 60).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 752 | 95% | 0.69 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4639 | 57% | 0.51 |
| prompt | 139 | 50% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1278)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 34 | 0.08 | 0.20 | 56% | `███████████         ` |
| 0.1–0.2 | 404 | 0.16 | 0.25 | 57% | `███████████         ` |
| 0.2–0.3 | 830 | 0.25 | 0.33 | 49% | `██████████          ` |
| 0.3–0.4 | 860 | 0.34 | 0.42 | 47% | `█████████           ` |
| 0.4–0.5 | 655 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 533 | 0.54 | 0.60 | 67% | `█████████████       ` |
| 0.6–0.7 | 468 | 0.65 | 0.70 | 81% | `████████████████    ` |
| 0.7–0.8 | 578 | 0.74 | 0.78 | 79% | `████████████████    ` |
| 0.8–0.9 | 577 | 0.84 | 0.87 | 73% | `███████████████     ` |
| 0.9–1.0 | 648 | 0.95 | 0.96 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-lavender-train-4__benchmark_end_state__CARRIED_all__735fbad_jev-latest_20261020_202330)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T20:47:10 · active 2:37 h · wall 7:10 h · paused 0:00 h · exit: **manual**
- Tool calls 21570 · images 1696 · reloads 1 · black-outs 0 · in-game playtime 12:47:16 · Pokédex 4 owned · maps visited 142
- Tokens uncached in / cache reads / out: 7.0M / 0.0M / 1282k · cost $0.30 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 61 | 206/206 | 148 | 138 | 177 | 148 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 2 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |
| 4 | 2026-10-20T20:23:31 | 24 | exited | 1567 | 0.4M / 0.0M / 63k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7030 (asked Jev 5704, forced by code 1326, labelled 5704) · models jev-1.13.0 · input tokens 7052530 · Jev $0.2962
- Jev latency mean 134 ms · p50 76 · p95 331 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 82 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 62 (now 61).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 775 | 95% | 0.69 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4733 | 58% | 0.52 |
| prompt | 139 | 50% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1303)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 36 | 0.08 | 0.22 | 56% | `███████████         ` |
| 0.1–0.2 | 408 | 0.16 | 0.25 | 57% | `███████████         ` |
| 0.2–0.3 | 832 | 0.25 | 0.33 | 49% | `██████████          ` |
| 0.3–0.4 | 861 | 0.34 | 0.42 | 48% | `██████████          ` |
| 0.4–0.5 | 664 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 543 | 0.54 | 0.60 | 67% | `█████████████       ` |
| 0.6–0.7 | 482 | 0.64 | 0.70 | 81% | `████████████████    ` |
| 0.7–0.8 | 577 | 0.74 | 0.78 | 80% | `████████████████    ` |
| 0.8–0.9 | 614 | 0.84 | 0.87 | 72% | `██████████████      ` |
| 0.9–1.0 | 687 | 0.95 | 0.96 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-lavender-train-2__benchmark_end_state__CARRIED_all__028cf6d_jev-latest_20261020_194222)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T20:03:00 · active 2:34 h · wall 6:26 h · paused 0:00 h · exit: **manual**
- Tool calls 21572 · images 1714 · reloads 1 · black-outs 0 · in-game playtime 12:40:09 · Pokédex 4 owned · maps visited 142
- Tokens uncached in / cache reads / out: 7.0M / 0.0M / 1270k · cost $0.29 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 60 | 200/202 | 146 | 135 | 173 | 144 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 2 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |
| 4 | 2026-10-20T19:42:27 | 21 | exited | 1569 | 0.3M / 0.0M / 51k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7033 (asked Jev 5672, forced by code 1361, labelled 5672) · models jev-1.13.0 · input tokens 6998148 · Jev $0.2939
- Jev latency mean 134 ms · p50 76 · p95 332 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 77 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 62 (now 60).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 791 | 94% | 0.68 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4685 | 57% | 0.52 |
| prompt | 139 | 50% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1288)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 39 | 0.08 | 0.24 | 59% | `████████████        ` |
| 0.1–0.2 | 405 | 0.16 | 0.25 | 57% | `███████████         ` |
| 0.2–0.3 | 835 | 0.25 | 0.33 | 49% | `██████████          ` |
| 0.3–0.4 | 859 | 0.34 | 0.42 | 48% | `██████████          ` |
| 0.4–0.5 | 652 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 527 | 0.54 | 0.60 | 66% | `█████████████       ` |
| 0.6–0.7 | 467 | 0.65 | 0.70 | 81% | `████████████████    ` |
| 0.7–0.8 | 580 | 0.74 | 0.78 | 78% | `████████████████    ` |
| 0.8–0.9 | 628 | 0.84 | 0.87 | 71% | `██████████████      ` |
| 0.9–1.0 | 680 | 0.95 | 0.96 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo-exp-lavender-train-3__benchmark_end_state__CARRIED_all__99513f1_jev-latest_20261020_200312)

- CLI: `jev-agent` jev_agent.py v2 · server commit `7245498` · prompt `49106d19e201a25e`
- Started 2026-10-20T13:36:17 · ended 2026-10-20T20:23:13 · active 2:33 h · wall 6:46 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 23003 · images 1868 · reloads 1 · black-outs 0 · in-game playtime 13:20:24 · Pokédex 4 owned · maps visited 142
- Tokens uncached in / cache reads / out: 7.3M / 0.0M / 1321k · cost $0.31 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 61 | 202/206 | 148 | 138 | 177 | 148 | Strength, Slash, Flamethrower, Cut |
| 2 | AAAJJJJJJJ (Magikarp) | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:19 | obtained: Charmander |
| 0:00 | 127 | 0:02:19 | starter: Charmander |
| 0:00 | 155 | 0:04:21 | reached: Route 1 |
| 0:00 | 172 | 0:05:54 | reached: Viridian City |
| 0:00 | 288 | 0:10:38 | reached: Route 2 |
| 0:00 | 425 | 0:20:27 | reached: Pewter City |
| 0:00 | 1016 | 0:43:32 | badge: Boulder |
| 0:00 | 1025 | 0:43:53 | reached: Route 3 |
| 0:00 | 1053 | 0:46:20 | evolved: Charmander → Charmeleon |
| 0:00 | 1142 | 0:51:59 | reached: Route 4 |
| 0:00 | 1146 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1520 | 1:14:22 | obtained: Magikarp |
| 0:01 | 1670 | 1:19:23 | reached: Route 22 |
| 0:01 | 1681 | 1:19:56 | reached: Route 23 |
| 0:02 | 2386 | 1:44:47 | reached: Cerulean City |
| 0:04 | 5877 | 3:58:02 | badge: Cascade |
| 0:04 | 5925 | 4:01:03 | reached: Route 24 |
| 0:04 | 6009 | 4:06:40 | reached: Route 25 |
| 0:04 | 6379 | 4:21:51 | reached: Route 5 |
| 0:04 | 6397 | 4:22:23 | reached: Route 6 |
| 0:04 | 6442 | 4:25:15 | reached: Vermilion City |
| 0:04 | 6480 | 4:26:39 | reached: Vermilion Dock |
| 0:05 | 6638 | 4:36:22 | evolved: Charmeleon → Charizard |
| 0:05 | 6847 | 4:44:45 | badge: Thunder |
| 0:05 | 6913 | 4:46:58 | reached: Route 9 |
| 0:05 | 6972 | 4:50:42 | reached: Route 10 |
| 0:05 | 6976 | 4:51:00 | reached: Rock Tunnel 1F |
| 0:05 | 7006 | 4:52:50 | reached: Rock Tunnel B1F |
| 0:09 | 8518 | 6:03:10 | reached: Route 11 |
| 0:10 | 9037 | 6:23:17 | reached: Route 12 |
| 0:17 | 10240 | 7:20:48 | reached: Lavender Town |
| 0:18 | 10451 | 7:25:54 | reached: Route 8 |
| 0:18 | 10511 | 7:29:19 | reached: Route 7 |
| 0:18 | 10517 | 7:29:28 | reached: Celadon City |
| 0:18 | 10667 | 7:37:52 | badge: Rainbow |
| 0:18 | 10766 | 7:42:02 | reached: Rocket Hideout B1F |
| 0:20 | 12076 | 8:16:44 | reached: Pokémon Tower 1F |
| 0:26 | 13471 | 9:12:46 | reached: Route 13 |
| 0:26 | 13595 | 9:20:25 | reached: Route 14 |
| 0:26 | 13668 | 9:24:40 | reached: Route 15 |
| 0:26 | 13681 | 9:25:05 | reached: Fuchsia City |
| 0:26 | 13864 | 9:36:48 | badge: Soul |
| 0:26 | 13872 | 9:37:30 | reached: Safari Zone Gate |
| 0:26 | 13879 | 9:37:51 | reached: Safari Zone Center |
| 0:26 | 13886 | 9:38:02 | reached: Safari Zone East |
| 0:26 | 13890 | 9:38:31 | reached: Safari Zone North |
| 0:26 | 13894 | 9:38:48 | reached: Safari Zone West |
| 0:29 | 15346 | 10:31:03 | reached: Saffron City |
| 0:29 | 15379 | 10:32:04 | reached: Silph Co. 1F |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 1 exited, 1 budget_calls; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T13:36:17 | 60 | rotate | 17442 | 5.7M / 0.0M / 1022k |
| 2 | 2026-10-20T14:36:27 | 60 | rotate | 2027 | 0.8M / 0.0M / 162k |
| 3 | 2026-10-20T15:36:37 | 14 | exited | 532 | 0.2M / 0.0M / 36k |
| 4 | 2026-10-20T20:03:21 | 20 | budget_calls | 3001 | 0.6M / 0.0M / 102k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7468 (asked Jev 5925, forced by code 1543, labelled 5925) · models jev-1.13.0 · input tokens 7282064 · Jev $0.3058
- Jev latency mean 131 ms · p50 75 · p95 326 · max 5951
- Fallbacks: none (variant without a safety net)
- Full game from power-on
- Planner calls 0 ($0.0000, errors 0) · objective changes 119 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 62 (now 61).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 858 | 94% | 0.68 |
| faint_switch | 4 | 0% | 0.25 |
| intro | 53 | 51% | 0.42 |
| overworld | 4871 | 58% | 0.53 |
| prompt | 139 | 50% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1332)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 41 | 0.07 | 0.26 | 61% | `████████████        ` |
| 0.1–0.2 | 410 | 0.16 | 0.25 | 58% | `████████████        ` |
| 0.2–0.3 | 843 | 0.25 | 0.33 | 50% | `██████████          ` |
| 0.3–0.4 | 869 | 0.34 | 0.42 | 48% | `██████████          ` |
| 0.4–0.5 | 685 | 0.44 | 0.51 | 57% | `███████████         ` |
| 0.5–0.6 | 544 | 0.54 | 0.60 | 66% | `█████████████       ` |
| 0.6–0.7 | 500 | 0.65 | 0.70 | 81% | `████████████████    ` |
| 0.7–0.8 | 623 | 0.75 | 0.78 | 79% | `████████████████    ` |
| 0.8–0.9 | 682 | 0.84 | 0.87 | 72% | `██████████████      ` |
| 0.9–1.0 | 728 | 0.95 | 0.96 | 67% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it64_jev-latest_20261018_104858)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a266bd0` · prompt `49106d19e201a25e`
- Started 2026-10-18T10:48:58 · ended 2026-10-18T12:06:49 · active 1:17 h · wall 1:17 h · paused 0:00 h · exit: **stuck**
- Tool calls 28966 · images 2901 · reloads 3 · black-outs 0 · in-game playtime 17:31:48 · Pokédex 7 owned · maps visited 161
- Tokens uncached in / cache reads / out: 11.0M / 0.0M / 1993k · cost $0.46 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 61 | 180/199 | 152 | 142 | 180 | 145 | Flamethrower, Cut, Ember, Strength |
| 2 | Magikarp | 5 | 17/17 | 7 | 11 | 14 | 8 | Splash |
| 3 | AAAAAAAAAA (Venonat) | 22 | 61/61 | 35 | 30 | 26 | 27 | Tackle, Disable |
| 4 | AAAAAAAAAA (Nidoran♂) | 24 | 61/61 | 32 | 29 | 34 | 25 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 5 | AAAAAAAAAA (Rhyhorn) | 26 | 79/79 | 55 | 54 | 18 | 27 | Horn Attack |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:03 | game started |
| 0:00 | 90 | 0:00:19 | reached: Pallet Town |
| 0:00 | 123 | 0:02:08 | obtained: Charmander |
| 0:00 | 123 | 0:02:08 | starter: Charmander |
| 0:00 | 193 | 0:05:59 | reached: Route 1 |
| 0:00 | 210 | 0:07:18 | reached: Viridian City |
| 0:00 | 481 | 0:17:00 | reached: Route 2 |
| 0:00 | 534 | 0:20:31 | reached: Route 22 |
| 0:00 | 782 | 0:37:07 | reached: Pewter City |
| 0:01 | 1550 | 1:08:57 | evolved: Charmander → Charmeleon |
| 0:01 | 1908 | 1:24:05 | badge: Boulder |
| 0:01 | 1934 | 1:25:00 | reached: Route 3 |
| 0:01 | 2026 | 1:32:44 | reached: Route 4 |
| 0:01 | 2030 | 1:32:52 | reached: Mt. Moon 1F |
| 0:02 | 2475 | 1:54:05 | reached: Route 23 |
| 0:03 | 3297 | 2:29:02 | obtained: Magikarp |
| 0:04 | 4115 | 2:51:07 | reached: Cerulean City |
| 0:07 | 9353 | 6:09:16 | obtained: Charizard |
| 0:08 | 10168 | 6:39:13 | badge: Cascade |
| 0:08 | 10188 | 6:41:25 | reached: Route 24 |
| 0:09 | 11011 | 7:10:29 | reached: Route 25 |
| 0:09 | 11217 | 7:21:01 | reached: Route 5 |
| 0:09 | 11247 | 7:21:48 | reached: Route 9 |
| 0:09 | 11369 | 7:24:51 | reached: Route 6 |
| 0:09 | 11417 | 7:28:13 | reached: Vermilion City |
| 0:09 | 11460 | 7:29:45 | reached: Vermilion Dock |
| 0:09 | 11809 | 7:46:49 | badge: Thunder |
| 0:09 | 11827 | 7:47:24 | reached: Route 11 |
| 0:10 | 12066 | 7:55:42 | reached: Route 12 |
| 0:12 | 12911 | 8:28:11 | reached: Route 10 |
| 0:12 | 12966 | 8:31:37 | reached: Rock Tunnel 1F |
| 0:12 | 12998 | 8:34:19 | reached: Rock Tunnel B1F |
| 0:12 | 13390 | 8:55:20 | reached: Lavender Town |
| 0:13 | 13460 | 8:57:07 | reached: Pokémon Tower 1F |
| 0:17 | 14588 | 9:39:49 | reached: Route 8 |
| 0:20 | 15579 | 10:32:45 | reached: Route 7 |
| 0:20 | 15585 | 10:32:54 | reached: Celadon City |
| 0:20 | 15812 | 10:45:11 | badge: Rainbow |
| 0:20 | 16113 | 10:55:07 | reached: Route 16 |
| 0:32 | 17448 | 11:42:32 | reached: Rocket Hideout B1F |
| 0:54 | 21577 | 14:24:48 | reached: Route 13 |
| 0:54 | 21644 | 14:30:55 | reached: Route 14 |
| 0:55 | 21806 | 14:39:51 | reached: Route 15 |
| 0:59 | 22635 | 15:20:16 | reached: Fuchsia City |
| 1:00 | 22759 | 15:29:54 | badge: Soul |
| 1:00 | 22771 | 15:30:58 | reached: Safari Zone Gate |
| 1:00 | 22778 | 15:31:19 | reached: Safari Zone Center |
| 1:00 | 22844 | 15:33:36 | obtained: Venonat |
| 1:00 | 22855 | 15:33:46 | reached: Safari Zone East |
| 1:00 | 22897 | 15:35:18 | obtained: Nidoran♂ |
| 1:00 | 22903 | 15:35:44 | reached: Safari Zone North |
| 1:00 | 22929 | 15:37:27 | reached: Safari Zone West |
| 1:00 | 23113 | 15:46:09 | obtained: Rhyhorn |
| 1:02 | 24700 | 16:30:16 | reached: Saffron City |
| 1:02 | 24721 | 16:31:00 | reached: Silph Co. 1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T10:48:58 | 60 | rotate | 22739 | 7.2M / 0.0M / 1233k |
| 2 | 2026-10-18T11:49:02 | 18 | stuck | 6224 | 3.8M / 0.0M / 760k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11369 (asked Jev 9155, forced by code 2214, labelled 9155) · models jev-1.13.0 · input tokens 10997889 · Jev $0.4619
- Jev latency mean 101 ms · p50 81 · p95 297 · max 842
- Fallbacks: none (variant without a safety net)
- Iteration 64
- Planner calls 0 ($0.0000, errors 0) · objective changes 102 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it (face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 847 | 96% | 0.72 |
| faint_switch | 4 | 0% | 0.20 |
| intro | 54 | 52% | 0.41 |
| overworld | 8023 | 60% | 0.39 |
| prompt | 227 | 56% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1881)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 188 | 0.08 | 0.18 | 64% | `█████████████       ` |
| 0.1–0.2 | 1909 | 0.15 | 0.23 | 59% | `████████████        ` |
| 0.2–0.3 | 2000 | 0.24 | 0.32 | 56% | `███████████         ` |
| 0.3–0.4 | 1276 | 0.34 | 0.42 | 56% | `███████████         ` |
| 0.4–0.5 | 792 | 0.44 | 0.51 | 57% | `███████████         ` |
| 0.5–0.6 | 609 | 0.54 | 0.61 | 64% | `█████████████       ` |
| 0.6–0.7 | 511 | 0.64 | 0.70 | 73% | `███████████████     ` |
| 0.7–0.8 | 548 | 0.74 | 0.79 | 77% | `███████████████     ` |
| 0.8–0.9 | 564 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 758 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it72_jev-latest_20261019_043640)

- CLI: `jev-agent` jev_agent.py v2 · server commit `89ae670` · prompt `49106d19e201a25e`
- Started 2026-10-19T04:36:40 · ended 2026-10-19T05:26:31 · active 0:49 h · wall 0:49 h · paused 0:00 h · exit: **stuck**
- Tool calls 33433 · images 2573 · reloads 5 · black-outs 0 · in-game playtime 16:35:45 · Pokédex 5 owned · maps visited 157
- Tokens uncached in / cache reads / out: 12.0M / 0.0M / 2319k · cost $0.50 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 60 | 149/205 | 152 | 128 | 168 | 153 | Flamethrower, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidorino) | 33 | 85/85 | 56 | 52 | 50 | 41 | Horn Attack, Poison Sting, Focus Energy, Fury Attack |
| 3 | AAAAAAAAAA (Doduo) | 26 | 58/58 | 53 | 32 | 44 | 26 | Peck, Growl, Fury Attack |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:12 | reached: Pallet Town |
| 0:00 | 135 | 0:02:37 | obtained: Charmander |
| 0:00 | 135 | 0:02:37 | starter: Charmander |
| 0:00 | 167 | 0:05:18 | reached: Route 1 |
| 0:00 | 172 | 0:05:36 | reached: Viridian City |
| 0:00 | 267 | 0:10:25 | reached: Route 2 |
| 0:00 | 293 | 0:11:25 | reached: Route 22 |
| 0:00 | 616 | 0:31:08 | reached: Pewter City |
| 0:01 | 1465 | 1:06:28 | evolved: Charmander → Charmeleon |
| 0:01 | 2119 | 1:33:29 | badge: Boulder |
| 0:01 | 2129 | 1:33:51 | reached: Route 3 |
| 0:01 | 2193 | 1:39:55 | reached: Route 4 |
| 0:01 | 2198 | 1:40:04 | reached: Mt. Moon 1F |
| 0:02 | 3376 | 2:21:24 | reached: Route 23 |
| 0:03 | 4187 | 2:48:09 | reached: Cerulean City |
| 0:06 | 8629 | 5:32:59 | badge: Cascade |
| 0:06 | 8651 | 5:35:22 | reached: Route 24 |
| 0:06 | 8680 | 5:38:25 | evolved: Charmeleon → Charizard |
| 0:06 | 9303 | 6:00:04 | reached: Route 25 |
| 0:07 | 9608 | 6:13:43 | reached: Route 5 |
| 0:07 | 9637 | 6:14:34 | reached: Route 9 |
| 0:08 | 10065 | 6:30:15 | reached: Route 6 |
| 0:08 | 10100 | 6:32:52 | reached: Vermilion City |
| 0:08 | 10133 | 6:34:03 | reached: Vermilion Dock |
| 0:09 | 11543 | 7:04:52 | badge: Thunder |
| 0:09 | 11846 | 7:19:49 | reached: Route 11 |
| 0:12 | 13108 | 8:02:59 | reached: Route 12 |
| 0:14 | 13906 | 8:27:37 | reached: Route 10 |
| 0:14 | 13911 | 8:27:55 | reached: Rock Tunnel 1F |
| 0:14 | 14033 | 8:33:57 | reached: Rock Tunnel B1F |
| 0:19 | 16116 | 9:54:37 | reached: Lavender Town |
| 0:19 | 16191 | 9:56:27 | reached: Route 8 |
| 0:19 | 16283 | 10:03:20 | reached: Pokémon Tower 1F |
| 0:24 | 17460 | 11:19:04 | reached: Route 7 |
| 0:24 | 17466 | 11:19:13 | reached: Celadon City |
| 0:24 | 17567 | 11:25:09 | badge: Rainbow |
| 0:24 | 17700 | 11:29:23 | reached: Rocket Hideout B1F |
| 0:29 | 19967 | 12:44:09 | reached: Route 16 |
| 0:31 | 20896 | 13:16:50 | reached: Route 13 |
| 0:31 | 20955 | 13:22:44 | reached: Route 14 |
| 0:31 | 21124 | 13:32:26 | reached: Route 15 |
| 0:37 | 22517 | 14:26:57 | reached: Fuchsia City |
| 0:37 | 22632 | 14:36:11 | badge: Soul |
| 0:37 | 22641 | 14:36:52 | reached: Safari Zone Gate |
| 0:37 | 22648 | 14:37:13 | reached: Safari Zone Center |
| 0:37 | 22681 | 14:37:59 | reached: Safari Zone East |
| 0:37 | 22733 | 14:39:52 | obtained: Nidorino |
| 0:37 | 22767 | 14:41:27 | obtained: Doduo |
| 0:37 | 22781 | 14:41:55 | reached: Safari Zone North |
| 0:37 | 22793 | 14:42:58 | reached: Safari Zone West |
| 0:38 | 23639 | 15:18:42 | reached: Saffron City |
| 0:38 | 23664 | 15:19:35 | reached: Silph Co. 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 49.8 min, longest 50 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T04:36:40 | 50 | stuck | 33433 | 12.0M / 0.0M / 2319k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11689 (asked Jev 9801, forced by code 1888, labelled 9801) · models jev-1.13.0 · input tokens 11965882 · Jev $0.5026
- Jev latency mean 84 ms · p50 76 · p95 143 · max 345
- Fallbacks: none (variant without a safety net)
- Iteration 72
- Planner calls 0 ($0.0000, errors 0) · objective changes 92 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it (face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 772 | 93% | 0.70 |
| intro | 52 | 50% | 0.42 |
| overworld | 8855 | 56% | 0.40 |
| prompt | 122 | 54% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1588)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 285 | 0.08 | 0.19 | 50% | `██████████          ` |
| 0.1–0.2 | 2434 | 0.15 | 0.23 | 51% | `██████████          ` |
| 0.2–0.3 | 1840 | 0.24 | 0.32 | 52% | `██████████          ` |
| 0.3–0.4 | 1122 | 0.34 | 0.42 | 50% | `██████████          ` |
| 0.4–0.5 | 705 | 0.44 | 0.53 | 55% | `███████████         ` |
| 0.5–0.6 | 594 | 0.54 | 0.61 | 64% | `█████████████       ` |
| 0.6–0.7 | 645 | 0.65 | 0.69 | 71% | `██████████████      ` |
| 0.7–0.8 | 677 | 0.74 | 0.77 | 76% | `███████████████     ` |
| 0.8–0.9 | 676 | 0.84 | 0.86 | 80% | `████████████████    ` |
| 0.9–1.0 | 823 | 0.96 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it71_jev-latest_20261018_235434)

- CLI: `jev-agent` jev_agent.py v2 · server commit `cab4cf1` · prompt `49106d19e201a25e`
- Started 2026-10-18T23:54:34 · ended 2026-10-19T04:32:11 · active 4:37 h · wall 4:37 h · paused 0:00 h · exit: **stuck**
- Tool calls 33839 · images 3582 · reloads 9 · black-outs 0 · in-game playtime 15:03:23 · Pokédex 5 owned · maps visited 145
- Tokens uncached in / cache reads / out: 14.3M / 0.0M / 3179k · cost $0.60 · chunks 5

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 58 | 195/195 | 141 | 125 | 152 | 133 | Fire Spin, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Kangaskhan) | 25 | 90/90 | 57 | 45 | 55 | 25 | Comet Punch, Rage, Surf |
| 3 | AAAAAAAAAA (Doduo) | 26 | 59/59 | 57 | 32 | 51 | 23 | Peck, Growl, Fury Attack |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 69 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:17 | reached: Pallet Town |
| 0:00 | 124 | 0:02:18 | obtained: Charmander |
| 0:00 | 124 | 0:02:18 | starter: Charmander |
| 0:00 | 153 | 0:04:11 | reached: Route 1 |
| 0:00 | 170 | 0:05:41 | reached: Viridian City |
| 0:00 | 288 | 0:11:11 | reached: Route 2 |
| 0:00 | 315 | 0:12:11 | reached: Route 22 |
| 0:01 | 1350 | 1:26:11 | reached: Pewter City |
| 0:01 | 2190 | 2:03:29 | evolved: Charmander → Charmeleon |
| 0:02 | 2936 | 2:31:41 | badge: Boulder |
| 0:02 | 2946 | 2:32:02 | reached: Route 3 |
| 0:02 | 3018 | 2:39:25 | reached: Route 4 |
| 0:02 | 3022 | 2:39:34 | reached: Mt. Moon 1F |
| 0:02 | 3579 | 3:01:36 | reached: Route 23 |
| 0:06 | 5506 | 3:56:09 | reached: Cerulean City |
| 0:09 | 9849 | 6:32:08 | badge: Cascade |
| 0:09 | 9870 | 6:34:22 | reached: Route 24 |
| 0:09 | 10537 | 6:59:06 | reached: Route 25 |
| 0:10 | 10702 | 7:07:40 | evolved: Charmeleon → Charizard |
| 0:10 | 10931 | 7:14:35 | reached: Route 5 |
| 0:10 | 10960 | 7:15:23 | reached: Route 9 |
| 0:10 | 11222 | 7:24:19 | reached: Route 6 |
| 0:11 | 11263 | 7:27:25 | reached: Vermilion City |
| 0:11 | 11296 | 7:28:37 | reached: Vermilion Dock |
| 0:12 | 12187 | 7:50:50 | badge: Thunder |
| 0:12 | 12324 | 7:59:01 | reached: Route 10 |
| 0:12 | 12332 | 7:59:25 | reached: Rock Tunnel 1F |
| 0:12 | 12380 | 8:01:45 | reached: Rock Tunnel B1F |
| 0:12 | 12927 | 8:26:38 | reached: Route 11 |
| 0:15 | 13779 | 9:00:02 | reached: Route 12 |
| 0:15 | 14164 | 9:24:09 | reached: Lavender Town |
| 0:15 | 14240 | 9:25:58 | reached: Route 8 |
| 0:15 | 14305 | 9:32:06 | reached: Route 7 |
| 0:15 | 14311 | 9:32:15 | reached: Celadon City |
| 0:15 | 14437 | 9:40:31 | badge: Rainbow |
| 0:16 | 14624 | 9:46:17 | reached: Rocket Hideout B1F |
| 0:36 | 18877 | 10:35:02 | reached: Pokémon Tower 1F |
| 1:11 | 23694 | 11:38:16 | reached: Route 13 |
| 1:11 | 23753 | 11:44:11 | reached: Route 14 |
| 1:12 | 24082 | 12:01:46 | reached: Route 15 |
| 1:15 | 24660 | 12:32:00 | reached: Fuchsia City |
| 1:15 | 24842 | 12:46:39 | badge: Soul |
| 1:15 | 24851 | 12:47:20 | reached: Safari Zone Gate |
| 1:15 | 24860 | 12:47:43 | reached: Safari Zone Center |
| 1:15 | 24892 | 12:48:28 | reached: Safari Zone East |
| 1:15 | 24930 | 12:49:43 | obtained: Kangaskhan |
| 1:15 | 24956 | 12:51:01 | obtained: Doduo |
| 1:15 | 24961 | 12:51:08 | reached: Safari Zone North |
| 1:15 | 24976 | 12:52:19 | reached: Safari Zone West |
| 1:17 | 26212 | 13:28:40 | reached: Saffron City |
| 1:17 | 26236 | 13:29:31 | reached: Silph Co. 1F |

**CLI chunks:** 5 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 4 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T23:54:34 | 60 | rotate | 21547 | 7.9M / 0.0M / 1540k |
| 2 | 2026-10-19T00:54:38 | 60 | rotate | 7230 | 3.1M / 0.0M / 685k |
| 3 | 2026-10-19T01:54:47 | 60 | rotate | 1970 | 1.2M / 0.0M / 347k |
| 4 | 2026-10-19T02:54:53 | 60 | rotate | 1920 | 1.3M / 0.0M / 377k |
| 5 | 2026-10-19T03:54:57 | 37 | stuck | 1163 | 0.8M / 0.0M / 230k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 12475 (asked Jev 10774, forced by code 1701, labelled 10774) · models jev-1.13.0 · input tokens 14329165 · Jev $0.6018
- Jev latency mean 93 ms · p50 78 · p95 148 · max 79159
- Fallbacks: none (variant without a safety net)
- Iteration 71
- Planner calls 0 ($0.0000, errors 0) · objective changes 108 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it (face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 752 | 93% | 0.71 |
| faint_switch | 1 | 0% | 0.47 |
| intro | 49 | 49% | 0.39 |
| overworld | 9796 | 52% | 0.33 |
| prompt | 176 | 58% | 0.51 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1696)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 434 | 0.07 | 0.14 | 41% | `████████            ` |
| 0.1–0.2 | 3465 | 0.15 | 0.20 | 44% | `█████████           ` |
| 0.2–0.3 | 2203 | 0.24 | 0.30 | 50% | `██████████          ` |
| 0.3–0.4 | 1168 | 0.34 | 0.41 | 53% | `███████████         ` |
| 0.4–0.5 | 706 | 0.44 | 0.51 | 58% | `████████████        ` |
| 0.5–0.6 | 558 | 0.54 | 0.61 | 67% | `█████████████       ` |
| 0.6–0.7 | 522 | 0.64 | 0.69 | 76% | `███████████████     ` |
| 0.7–0.8 | 528 | 0.75 | 0.78 | 79% | `████████████████    ` |
| 0.8–0.9 | 482 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 708 | 0.97 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it62_jev-latest_20261018_070327)

- CLI: `jev-agent` jev_agent.py v2 · server commit `3d45c25` · prompt `49106d19e201a25e`
- Started 2026-10-18T07:03:27 · ended 2026-10-18T08:57:49 · active 1:54 h · wall 1:54 h · paused 0:00 h · exit: **stuck**
- Tool calls 38929 · images 3787 · reloads 7 · black-outs 0 · in-game playtime 19:43:44 · Pokédex 5 owned · maps visited 154
- Tokens uncached in / cache reads / out: 15.4M / 0.0M / 3062k · cost $0.65 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 61 | 203/206 | 151 | 149 | 170 | 147 | Flamethrower, Cut, Ember, Strength |
| 2 | Magikarp | 5 | 17/17 | 6 | 11 | 14 | 8 | Splash |
| 3 | AAAAAAAAAA (Exeggcute) | 25 | 66/66 | 27 | 46 | 25 | 40 | Barrage, Hypnosis, Reflect |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:19 | reached: Pallet Town |
| 0:00 | 128 | 0:02:20 | obtained: Charmander |
| 0:00 | 128 | 0:02:20 | starter: Charmander |
| 0:00 | 200 | 0:05:20 | reached: Route 1 |
| 0:00 | 211 | 0:06:13 | reached: Viridian City |
| 0:00 | 365 | 0:12:01 | reached: Route 2 |
| 0:00 | 420 | 0:15:48 | reached: Route 22 |
| 0:00 | 806 | 0:40:16 | reached: Pewter City |
| 0:01 | 1279 | 1:02:33 | evolved: Charmander → Charmeleon |
| 0:01 | 1315 | 1:06:08 | badge: Boulder |
| 0:01 | 1324 | 1:06:29 | reached: Route 3 |
| 0:01 | 1509 | 1:16:29 | reached: Route 4 |
| 0:01 | 1514 | 1:16:37 | reached: Mt. Moon 1F |
| 0:01 | 1911 | 1:36:30 | obtained: Magikarp |
| 0:01 | 2043 | 1:41:57 | reached: Route 23 |
| 0:03 | 3403 | 2:41:09 | reached: Cerulean City |
| 0:06 | 7881 | 5:29:00 | badge: Cascade |
| 0:06 | 7901 | 5:31:16 | reached: Route 24 |
| 0:06 | 7931 | 5:34:10 | evolved: Charmeleon → Charizard |
| 0:07 | 8683 | 5:58:30 | reached: Route 25 |
| 0:07 | 8981 | 6:11:21 | reached: Route 5 |
| 0:07 | 9010 | 6:12:12 | reached: Route 9 |
| 0:08 | 9169 | 6:16:47 | reached: Route 6 |
| 0:08 | 9277 | 6:22:16 | reached: Vermilion City |
| 0:08 | 9325 | 6:23:57 | reached: Vermilion Dock |
| 0:08 | 9352 | 6:24:28 | reached: Route 11 |
| 0:10 | 11896 | 7:41:28 | badge: Thunder |
| 0:13 | 12906 | 8:27:13 | reached: Route 10 |
| 0:13 | 12911 | 8:27:31 | reached: Rock Tunnel 1F |
| 0:14 | 12990 | 8:31:21 | reached: Rock Tunnel B1F |
| 0:18 | 15475 | 10:05:29 | reached: Lavender Town |
| 0:18 | 15520 | 10:06:45 | reached: Route 12 |
| 0:18 | 15552 | 10:07:30 | reached: Pokémon Tower 1F |
| 0:18 | 15567 | 10:07:51 | reached: Route 8 |
| 0:20 | 16614 | 11:24:02 | reached: Route 7 |
| 0:20 | 16620 | 11:24:11 | reached: Celadon City |
| 0:20 | 16767 | 11:32:42 | badge: Rainbow |
| 0:21 | 17125 | 11:42:58 | reached: Route 16 |
| 0:34 | 19544 | 13:11:25 | reached: Rocket Hideout B1F |
| 0:42 | 23321 | 15:21:14 | reached: Route 13 |
| 0:42 | 23410 | 15:28:22 | reached: Route 14 |
| 1:41 | 29962 | 17:28:36 | reached: Route 15 |
| 1:45 | 30759 | 18:08:12 | reached: Fuchsia City |
| 1:45 | 30872 | 18:17:55 | badge: Soul |
| 1:45 | 30885 | 18:19:04 | reached: Safari Zone Gate |
| 1:45 | 30892 | 18:19:25 | reached: Safari Zone Center |
| 1:45 | 30924 | 18:20:10 | reached: Safari Zone East |
| 1:45 | 30960 | 18:21:23 | obtained: Exeggcute |
| 1:45 | 30976 | 18:22:16 | reached: Safari Zone North |
| 1:45 | 30980 | 18:22:59 | reached: Safari Zone West |
| 1:48 | 33038 | 18:48:48 | reached: Saffron City |
| 1:48 | 33062 | 18:49:41 | reached: Silph Co. 1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T07:03:27 | 60 | rotate | 25372 | 8.6M / 0.0M / 1560k |
| 2 | 2026-10-18T08:03:32 | 54 | stuck | 13556 | 6.8M / 0.0M / 1502k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 14654 (asked Jev 12306, forced by code 2348, labelled 12306) · models jev-1.13.0 · input tokens 15435460 · Jev $0.6483
- Jev latency mean 100 ms · p50 80 · p95 307 · max 2124
- Fallbacks: none (variant without a safety net)
- Iteration 62
- Planner calls 0 ($0.0000, errors 0) · objective changes 97 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it (face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 881 | 95% | 0.68 |
| faint_switch | 3 | 0% | 0.20 |
| intro | 51 | 53% | 0.43 |
| overworld | 11189 | 54% | 0.37 |
| prompt | 182 | 67% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1849)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 248 | 0.08 | 0.20 | 50% | `██████████          ` |
| 0.1–0.2 | 2902 | 0.15 | 0.22 | 53% | `███████████         ` |
| 0.2–0.3 | 2918 | 0.24 | 0.31 | 52% | `██████████          ` |
| 0.3–0.4 | 1649 | 0.34 | 0.41 | 52% | `██████████          ` |
| 0.4–0.5 | 1054 | 0.44 | 0.51 | 58% | `████████████        ` |
| 0.5–0.6 | 779 | 0.54 | 0.61 | 65% | `█████████████       ` |
| 0.6–0.7 | 648 | 0.64 | 0.69 | 71% | `██████████████      ` |
| 0.7–0.8 | 686 | 0.74 | 0.78 | 74% | `███████████████     ` |
| 0.8–0.9 | 685 | 0.84 | 0.86 | 69% | `██████████████      ` |
| 0.9–1.0 | 737 | 0.96 | 0.97 | 62% | `████████████        ` |

### jev-solo: jev-latest (jev-solo_it76_jev-latest_20261019_182854)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b9dd3ae` · prompt `49106d19e201a25e`
- Started 2026-10-19T18:28:54 · ended 2026-10-19T20:43:20 · active 2:14 h · wall 2:14 h · paused 0:00 h · exit: **stuck**
- Tool calls 39115 · images 7278 · reloads 8 · black-outs 0 · in-game playtime 19:57:23 · Pokédex 12 owned · maps visited 155
- Tokens uncached in / cache reads / out: 11.7M / 0.0M / 2194k · cost $0.49 · chunks 3

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 64 | 205/205 | 167 | 141 | 184 | 159 | Slash, Cut, Ember, Strength |
| 2 | Magikarp | 5 | 18/18 | 6 | 11 | 14 | 7 | Splash |
| 3 | AAAAAAAAAA (Nidoran♂) | 24 | 57/57 | 39 | 30 | 30 | 29 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 4 | AAAAAAAAAA (Rhyhorn) | 25 | 77/77 | 50 | 59 | 21 | 26 | Horn Attack |
| 5 | AAAAAAAAAA (Rhyhorn) | 25 | 76/76 | 47 | 58 | 25 | 24 | Horn Attack |
| 6 | AAAAAAAAAA (Exeggcute) | 24 | 68/68 | 26 | 43 | 27 | 40 | Barrage, Hypnosis |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 126 | 0:02:19 | obtained: Charmander |
| 0:00 | 126 | 0:02:19 | starter: Charmander |
| 0:00 | 154 | 0:04:14 | reached: Route 1 |
| 0:00 | 165 | 0:05:00 | reached: Viridian City |
| 0:00 | 288 | 0:10:59 | reached: Route 2 |
| 0:00 | 315 | 0:11:59 | reached: Route 22 |
| 0:00 | 748 | 0:35:13 | reached: Pewter City |
| 0:00 | 1087 | 0:52:52 | badge: Boulder |
| 0:00 | 1096 | 0:53:14 | reached: Route 3 |
| 0:00 | 1123 | 0:57:52 | evolved: Charmander → Charmeleon |
| 0:00 | 1200 | 1:03:42 | reached: Route 4 |
| 0:00 | 1204 | 1:03:51 | reached: Mt. Moon 1F |
| 0:01 | 1660 | 1:24:06 | reached: Route 23 |
| 0:03 | 2663 | 1:59:26 | obtained: Magikarp |
| 0:04 | 3421 | 2:27:05 | reached: Cerulean City |
| 0:06 | 6223 | 4:21:13 | reached: Route 24 |
| 0:07 | 8578 | 5:51:18 | obtained: Charizard |
| 0:07 | 8625 | 5:54:17 | badge: Cascade |
| 0:07 | 8670 | 5:57:21 | reached: Route 25 |
| 0:11 | 11427 | 6:48:06 | reached: Route 5 |
| 0:11 | 11445 | 6:48:39 | reached: Route 6 |
| 0:11 | 11480 | 6:51:24 | reached: Vermilion City |
| 0:11 | 11513 | 6:52:37 | reached: Vermilion Dock |
| 0:12 | 11711 | 7:05:26 | badge: Thunder |
| 0:12 | 11763 | 7:07:02 | reached: Route 9 |
| 0:12 | 12164 | 7:28:21 | reached: Route 11 |
| 0:13 | 12339 | 7:34:20 | reached: Route 12 |
| 0:15 | 13437 | 8:04:37 | reached: Route 10 |
| 0:15 | 13442 | 8:04:55 | reached: Rock Tunnel 1F |
| 0:15 | 13483 | 8:07:06 | reached: Rock Tunnel B1F |
| 0:41 | 19675 | 11:38:29 | reached: Lavender Town |
| 0:41 | 19751 | 11:40:19 | reached: Route 8 |
| 0:41 | 19860 | 11:47:37 | reached: Pokémon Tower 1F |
| 0:46 | 20936 | 12:40:38 | reached: Route 7 |
| 0:46 | 20942 | 12:40:47 | reached: Celadon City |
| 0:46 | 21001 | 12:43:30 | reached: Route 16 |
| 0:48 | 22314 | 13:27:23 | badge: Rainbow |
| 0:49 | 22421 | 13:31:28 | reached: Rocket Hideout B1F |
| 0:51 | 24425 | 14:42:39 | reached: Route 13 |
| 0:51 | 24585 | 14:54:04 | reached: Route 14 |
| 0:51 | 24725 | 15:01:51 | reached: Route 15 |
| 0:52 | 25115 | 15:23:13 | reached: Fuchsia City |
| 0:52 | 25225 | 15:32:52 | badge: Soul |
| 0:52 | 25237 | 15:33:53 | reached: Safari Zone Gate |
| 0:52 | 25244 | 15:34:14 | reached: Safari Zone Center |
| 0:52 | 25278 | 15:35:02 | reached: Safari Zone East |
| 0:52 | 25319 | 15:37:02 | obtained: Nidoran♂ |
| 0:52 | 25325 | 15:37:09 | reached: Safari Zone North |
| 0:52 | 25345 | 15:38:49 | reached: Safari Zone West |
| 0:54 | 26517 | 16:14:11 | reached: Saffron City |
| 0:54 | 26542 | 16:15:12 | reached: Silph Co. 1F |
| 2:05 | 34208 | 19:03:10 | obtained: Rhyhorn |
| 2:05 | 34303 | 19:06:47 | obtained: Exeggcute |
| 2:06 | 34359 | 19:08:28 | obtained: Nidorino |
| 2:06 | 34585 | 19:15:58 | obtained: Parasect |
| 2:07 | 34702 | 19:20:32 | obtained: Nidorina |
| 2:08 | 35038 | 19:31:49 | obtained: Venonat |
| 2:13 | 37088 | 19:41:33 | obtained: Scyther |

**CLI chunks:** 3 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T18:28:54 | 60 | rotate | 30043 | 10.4M / 0.0M / 1952k |
| 2 | 2026-10-19T19:28:57 | 60 | rotate | 3540 | 1.1M / 0.0M / 194k |
| 3 | 2026-10-19T20:29:04 | 14 | stuck | 5529 | 0.3M / 0.0M / 48k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 15875 (asked Jev 9528, forced by code 6347, labelled 9528) · models jev-1.13.0 · input tokens 11677850 · Jev $0.4905
- Jev latency mean 101 ms · p50 80 · p95 230 · max 10021
- Fallbacks: none (variant without a safety net)
- Iteration 76
- Planner calls 0 ($0.0000, errors 0) · objective changes 101 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 66 (now 64).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 933 | 97% | 0.71 |
| faint_switch | 7 | 14% | 0.24 |
| intro | 52 | 58% | 0.39 |
| overworld | 8384 | 60% | 0.45 |
| prompt | 152 | 57% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1559)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 99 | 0.08 | 0.22 | 54% | `███████████         ` |
| 0.1–0.2 | 1341 | 0.15 | 0.23 | 54% | `███████████         ` |
| 0.2–0.3 | 1754 | 0.24 | 0.32 | 51% | `██████████          ` |
| 0.3–0.4 | 1349 | 0.34 | 0.42 | 52% | `██████████          ` |
| 0.4–0.5 | 1012 | 0.44 | 0.51 | 63% | `█████████████       ` |
| 0.5–0.6 | 800 | 0.54 | 0.60 | 70% | `██████████████      ` |
| 0.6–0.7 | 740 | 0.65 | 0.69 | 78% | `████████████████    ` |
| 0.7–0.8 | 744 | 0.74 | 0.78 | 85% | `█████████████████   ` |
| 0.8–0.9 | 727 | 0.85 | 0.87 | 88% | `██████████████████  ` |
| 0.9–1.0 | 962 | 0.96 | 0.97 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it61_jev-latest_20261018_051153)

- CLI: `jev-agent` jev_agent.py v2 · server commit `eadf70b` · prompt `49106d19e201a25e`
- Started 2026-10-18T05:11:53 · ended 2026-10-18T06:51:53 · active 1:39 h · wall 1:40 h · paused 0:00 h · exit: **stuck**
- Tool calls 39508 · images 3520 · reloads 6 · black-outs 0 · in-game playtime 20:12:58 · Pokédex 4 owned · maps visited 159
- Tokens uncached in / cache reads / out: 14.8M / 0.0M / 2808k · cost $0.62 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 60 | 202/207 | 153 | 146 | 165 | 146 | Flamethrower, Cut, Rage, Strength |
| 2 | Magikarp | 5 | 17/17 | 6 | 12 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:12 | reached: Pallet Town |
| 0:00 | 125 | 0:02:14 | obtained: Charmander |
| 0:00 | 125 | 0:02:14 | starter: Charmander |
| 0:00 | 188 | 0:05:11 | reached: Route 1 |
| 0:00 | 199 | 0:06:08 | reached: Viridian City |
| 0:00 | 448 | 0:14:53 | reached: Route 2 |
| 0:00 | 494 | 0:18:00 | reached: Route 22 |
| 0:00 | 772 | 0:35:39 | reached: Pewter City |
| 0:00 | 945 | 0:46:09 | badge: Boulder |
| 0:00 | 955 | 0:46:31 | reached: Route 3 |
| 0:00 | 1100 | 0:52:01 | evolved: Charmander → Charmeleon |
| 0:01 | 1226 | 1:00:46 | reached: Route 4 |
| 0:01 | 1231 | 1:00:54 | reached: Mt. Moon 1F |
| 0:01 | 1589 | 1:18:29 | reached: Route 23 |
| 0:02 | 2606 | 1:52:20 | obtained: Magikarp |
| 0:04 | 3410 | 2:18:14 | reached: Cerulean City |
| 0:06 | 7524 | 5:03:43 | badge: Cascade |
| 0:06 | 7545 | 5:05:51 | reached: Route 24 |
| 0:07 | 8316 | 5:38:08 | reached: Route 25 |
| 0:08 | 8810 | 5:56:44 | reached: Route 5 |
| 0:08 | 8839 | 5:57:35 | reached: Route 9 |
| 0:08 | 8938 | 6:00:07 | reached: Route 6 |
| 0:08 | 8973 | 6:02:42 | reached: Vermilion City |
| 0:08 | 9016 | 6:04:12 | reached: Vermilion Dock |
| 0:08 | 9043 | 6:06:35 | evolved: Charmeleon → Charizard |
| 0:09 | 10514 | 6:36:06 | badge: Thunder |
| 0:10 | 10816 | 6:47:13 | reached: Route 10 |
| 0:10 | 10853 | 6:48:20 | reached: Rock Tunnel 1F |
| 0:10 | 10873 | 6:50:08 | reached: Rock Tunnel B1F |
| 0:12 | 11429 | 7:12:02 | reached: Route 11 |
| 0:13 | 12281 | 7:52:33 | reached: Route 12 |
| 0:20 | 15261 | 9:13:40 | reached: Lavender Town |
| 0:20 | 15315 | 9:15:06 | reached: Pokémon Tower 1F |
| 0:20 | 15439 | 9:19:13 | reached: Route 8 |
| 0:23 | 16626 | 10:34:49 | reached: Route 7 |
| 0:23 | 16632 | 10:34:58 | reached: Celadon City |
| 0:23 | 16767 | 10:42:51 | badge: Rainbow |
| 0:24 | 16840 | 10:44:57 | reached: Route 16 |
| 0:44 | 19857 | 12:14:36 | reached: Rocket Hideout B1F |
| 1:17 | 27004 | 16:04:11 | reached: Route 13 |
| 1:20 | 27546 | 16:33:10 | reached: Route 14 |
| 1:20 | 27708 | 16:41:54 | reached: Route 15 |
| 1:28 | 29153 | 17:49:26 | reached: Fuchsia City |
| 1:28 | 29298 | 18:01:14 | badge: Soul |
| 1:28 | 29326 | 18:02:42 | reached: Safari Zone Gate |
| 1:28 | 29334 | 18:03:03 | reached: Safari Zone Center |
| 1:28 | 29353 | 18:03:28 | reached: Safari Zone East |
| 1:28 | 29378 | 18:04:15 | reached: Safari Zone North |
| 1:28 | 29408 | 18:06:03 | reached: Safari Zone West |
| 1:30 | 30922 | 18:52:24 | reached: Saffron City |
| 1:30 | 30947 | 18:53:10 | reached: Silph Co. 1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T05:11:53 | 60 | rotate | 23974 | 8.2M / 0.0M / 1469k |
| 2 | 2026-10-18T06:11:58 | 40 | stuck | 15532 | 6.6M / 0.0M / 1338k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 14419 (asked Jev 12277, forced by code 2142, labelled 12277) · models jev-1.13.0 · input tokens 14775887 · Jev $0.6206
- Jev latency mean 97 ms · p50 77 · p95 299 · max 2167
- Fallbacks: none (variant without a safety net)
- Iteration 61
- Planner calls 0 ($0.0000, errors 0) · objective changes 101 · objectives Jev marked done 0 · final objective: Enter Saffron City and clear Silph Co. (find the Card Key, beat Giovanni).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 834 | 91% | 0.72 |
| faint_switch | 9 | 0% | 0.22 |
| intro | 52 | 52% | 0.41 |
| overworld | 11162 | 55% | 0.37 |
| prompt | 220 | 56% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1639)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 235 | 0.08 | 0.19 | 52% | `██████████          ` |
| 0.1–0.2 | 2719 | 0.15 | 0.23 | 53% | `███████████         ` |
| 0.2–0.3 | 2850 | 0.24 | 0.32 | 52% | `██████████          ` |
| 0.3–0.4 | 1814 | 0.34 | 0.41 | 52% | `██████████          ` |
| 0.4–0.5 | 1135 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 832 | 0.54 | 0.60 | 57% | `███████████         ` |
| 0.6–0.7 | 777 | 0.64 | 0.69 | 65% | `█████████████       ` |
| 0.7–0.8 | 636 | 0.74 | 0.78 | 75% | `███████████████     ` |
| 0.8–0.9 | 570 | 0.84 | 0.86 | 75% | `███████████████     ` |
| 0.9–1.0 | 709 | 0.96 | 0.96 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it73_jev-latest_20261019_052829)

- CLI: `jev-agent` jev_agent.py v2 · server commit `533ea5b` · prompt `49106d19e201a25e`
- Started 2026-10-19T05:28:29 · ended 2026-10-19T07:17:30 · active 1:48 h · wall 1:49 h · paused 0:00 h · exit: **stuck**
- Tool calls 45011 · images 4041 · reloads 10 · black-outs 0 · in-game playtime 23:46:05 · Pokédex 4 owned · maps visited 161
- Tokens uncached in / cache reads / out: 17.7M / 0.0M / 3373k · cost $0.74 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 74 | 199/265 | 177 | 174 | 199 | 193 | Flamethrower, Cut, Ember, Strength |
| 2 | AAAAAAAAAA (Nidoran♂) | 22 | 56/56 | 31 | 27 | 32 | 26 | Tackle, Horn Attack, Poison Sting, Focus Energy |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 98 | 0:00:19 | reached: Pallet Town |
| 0:00 | 141 | 0:02:33 | obtained: Charmander |
| 0:00 | 141 | 0:02:33 | starter: Charmander |
| 0:00 | 171 | 0:04:46 | reached: Route 1 |
| 0:00 | 182 | 0:05:42 | reached: Viridian City |
| 0:00 | 310 | 0:11:00 | reached: Route 2 |
| 0:00 | 337 | 0:12:01 | reached: Route 22 |
| 0:00 | 674 | 0:34:36 | reached: Pewter City |
| 0:01 | 1599 | 1:15:22 | evolved: Charmander → Charmeleon |
| 0:01 | 2007 | 1:31:41 | badge: Boulder |
| 0:01 | 2033 | 1:32:36 | reached: Route 3 |
| 0:01 | 2102 | 1:38:54 | reached: Route 4 |
| 0:01 | 2107 | 1:39:04 | reached: Mt. Moon 1F |
| 0:01 | 2579 | 2:05:47 | reached: Route 23 |
| 0:04 | 4192 | 3:11:51 | reached: Cerulean City |
| 0:07 | 9284 | 6:23:48 | obtained: Charizard |
| 0:08 | 10888 | 7:21:36 | badge: Cascade |
| 0:08 | 10909 | 7:23:52 | reached: Route 24 |
| 0:09 | 11803 | 7:56:58 | reached: Route 25 |
| 0:09 | 12107 | 8:09:10 | reached: Route 5 |
| 0:09 | 12138 | 8:10:03 | reached: Route 9 |
| 0:10 | 12357 | 8:17:06 | reached: Route 6 |
| 0:10 | 12399 | 8:20:32 | reached: Vermilion City |
| 0:10 | 12431 | 8:21:44 | reached: Vermilion Dock |
| 0:10 | 12775 | 8:39:04 | badge: Thunder |
| 0:10 | 12932 | 8:45:08 | reached: Route 10 |
| 0:10 | 12937 | 8:45:26 | reached: Rock Tunnel 1F |
| 0:10 | 12979 | 8:47:38 | reached: Rock Tunnel B1F |
| 0:11 | 14471 | 10:00:34 | reached: Route 11 |
| 0:12 | 14662 | 10:06:51 | reached: Route 12 |
| 0:29 | 19625 | 12:33:37 | reached: Lavender Town |
| 0:29 | 19700 | 12:35:29 | reached: Route 8 |
| 0:29 | 19889 | 12:47:09 | reached: Pokémon Tower 1F |
| 0:34 | 21072 | 13:44:58 | reached: Route 7 |
| 0:34 | 21078 | 13:45:07 | reached: Celadon City |
| 0:34 | 21258 | 13:56:36 | badge: Rainbow |
| 0:34 | 21378 | 14:00:45 | reached: Rocket Hideout B1F |
| 0:37 | 22947 | 14:55:06 | reached: Route 16 |
| 0:39 | 24326 | 15:43:39 | reached: Route 13 |
| 0:39 | 24385 | 15:49:54 | reached: Route 14 |
| 0:41 | 24794 | 16:11:41 | reached: Route 15 |
| 0:43 | 25214 | 16:35:01 | reached: Fuchsia City |
| 0:43 | 25362 | 16:46:42 | badge: Soul |
| 0:43 | 25375 | 16:47:47 | reached: Safari Zone Gate |
| 0:43 | 25382 | 16:48:07 | reached: Safari Zone Center |
| 0:43 | 25415 | 16:48:53 | reached: Safari Zone East |
| 0:43 | 25429 | 16:49:29 | reached: Safari Zone North |
| 0:43 | 25433 | 16:49:46 | reached: Safari Zone West |
| 0:43 | 25504 | 16:52:41 | obtained: Nidoran♂ |
| 0:44 | 26599 | 17:32:43 | reached: Saffron City |
| 0:44 | 26624 | 17:33:35 | reached: Silph Co. 1F |
| 1:06 | 31206 | 19:56:32 | reached: Route 18 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T05:28:29 | 60 | rotate | 30353 | 9.8M / 0.0M / 1817k |
| 2 | 2026-10-19T06:28:34 | 49 | stuck | 14656 | 7.9M / 0.0M / 1556k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 17948 (asked Jev 14516, forced by code 3432, labelled 14516) · models jev-1.13.0 · input tokens 17663921 · Jev $0.7419
- Jev latency mean 87 ms · p50 80 · p95 148 · max 450
- Fallbacks: none (variant without a safety net)
- Iteration 73
- Planner calls 0 ($0.0000, errors 0) · objective changes 129 · objectives Jev marked done 0 · final objective: Beat Sabrina in the Saffron Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1546 | 97% | 0.70 |
| faint_switch | 3 | 0% | 0.25 |
| intro | 53 | 43% | 0.41 |
| overworld | 12754 | 78% | 0.46 |
| prompt | 160 | 51% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3066)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 104 | 0.07 | 0.21 | 48% | `██████████          ` |
| 0.1–0.2 | 1240 | 0.15 | 0.25 | 62% | `████████████        ` |
| 0.2–0.3 | 2708 | 0.25 | 0.33 | 75% | `███████████████     ` |
| 0.3–0.4 | 2643 | 0.34 | 0.42 | 82% | `████████████████    ` |
| 0.4–0.5 | 1940 | 0.44 | 0.51 | 85% | `█████████████████   ` |
| 0.5–0.6 | 1353 | 0.54 | 0.60 | 85% | `█████████████████   ` |
| 0.6–0.7 | 1029 | 0.65 | 0.69 | 87% | `█████████████████   ` |
| 0.7–0.8 | 987 | 0.74 | 0.78 | 89% | `██████████████████  ` |
| 0.8–0.9 | 934 | 0.84 | 0.87 | 91% | `██████████████████  ` |
| 0.9–1.0 | 1578 | 0.97 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it87_jev-latest_20261020_063140)

- CLI: `jev-agent` jev_agent.py v2 · server commit `4ad68cc` · prompt `49106d19e201a25e`
- Started 2026-10-20T06:31:40 · ended 2026-10-20T07:05:40 · active 0:33 h · wall 0:34 h · paused 0:00 h · exit: **manual**
- Tool calls 19315 · images 1994 · reloads 4 · black-outs 0 · in-game playtime 11:49:50 · Pokédex 3 owned · maps visited 111
- Tokens uncached in / cache reads / out: 6.1M / 0.0M / 1054k · cost $0.25 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 57 | 186/186 | 137 | 122 | 155 | 132 | Scratch, Slash, Flamethrower, Cut |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:01 | game started |
| 0:00 | 87 | 0:00:12 | reached: Pallet Town |
| 0:00 | 134 | 0:02:39 | obtained: Charmander |
| 0:00 | 134 | 0:02:39 | starter: Charmander |
| 0:00 | 162 | 0:04:33 | reached: Route 1 |
| 0:00 | 185 | 0:06:46 | reached: Viridian City |
| 0:00 | 293 | 0:11:47 | reached: Route 2 |
| 0:00 | 410 | 0:18:53 | reached: Pewter City |
| 0:01 | 1650 | 0:58:21 | evolved: Charmander → Charmeleon |
| 0:01 | 2356 | 1:20:05 | badge: Boulder |
| 0:01 | 2365 | 1:20:27 | reached: Route 3 |
| 0:01 | 2436 | 1:27:04 | reached: Route 4 |
| 0:01 | 2440 | 1:27:13 | reached: Mt. Moon 1F |
| 0:01 | 2786 | 1:48:05 | reached: Cerulean City |
| 0:04 | 8254 | 5:05:56 | badge: Cascade |
| 0:04 | 8275 | 5:08:14 | reached: Route 24 |
| 0:04 | 8306 | 5:11:13 | evolved: Charmeleon → Charizard |
| 0:04 | 8355 | 5:14:22 | reached: Route 25 |
| 0:04 | 8599 | 5:26:26 | reached: Route 5 |
| 0:04 | 8617 | 5:26:59 | reached: Route 6 |
| 0:04 | 8653 | 5:29:37 | reached: Vermilion City |
| 0:04 | 8685 | 5:30:49 | reached: Vermilion Dock |
| 0:04 | 9018 | 5:47:34 | badge: Thunder |
| 0:04 | 9061 | 5:49:03 | reached: Route 9 |
| 0:04 | 9171 | 5:58:32 | reached: Route 10 |
| 0:04 | 9175 | 5:58:50 | reached: Rock Tunnel 1F |
| 0:04 | 9195 | 6:00:08 | reached: Rock Tunnel B1F |
| 0:09 | 11455 | 7:32:16 | reached: Route 11 |
| 0:10 | 11618 | 7:38:13 | reached: Route 12 |
| 0:11 | 12469 | 8:13:07 | reached: Lavender Town |
| 0:11 | 12545 | 8:14:57 | reached: Route 8 |
| 0:12 | 13347 | 8:42:52 | reached: Route 7 |
| 0:12 | 13353 | 8:43:01 | reached: Celadon City |
| 0:12 | 13540 | 8:54:24 | badge: Rainbow |
| 0:12 | 13617 | 8:57:27 | reached: Rocket Hideout B1F |
| 0:13 | 14625 | 9:31:34 | reached: Pokémon Tower 1F |
| 0:32 | 17465 | 11:11:26 | reached: Route 13 |
| 0:32 | 17546 | 11:18:51 | reached: Route 14 |
| 0:32 | 17615 | 11:23:32 | reached: Route 15 |
| 0:32 | 17638 | 11:24:34 | reached: Fuchsia City |
| 0:33 | 17781 | 11:35:36 | badge: Soul |
| 0:33 | 17789 | 11:36:19 | reached: Safari Zone Gate |
| 0:33 | 17796 | 11:36:40 | reached: Safari Zone Center |
| 0:33 | 17803 | 11:36:52 | reached: Safari Zone East |
| 0:33 | 17808 | 11:37:22 | reached: Safari Zone North |
| 0:33 | 17820 | 11:37:55 | reached: Safari Zone West |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 34.0 min, longest 34 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T06:31:40 | 34 | exited | 19315 | 6.1M / 0.0M / 1054k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6717 (asked Jev 5072, forced by code 1645, labelled 5072) · models jev-1.13.0 · input tokens 6052061 · Jev $0.2542
- Jev latency mean 70 ms · p50 60 · p95 133 · max 456
- Fallbacks: none (variant without a safety net)
- Iteration 87
- Planner calls 0 ($0.0000, errors 0) · objective changes 78 · objectives Jev marked done 0 · final objective: Find the Safari Zone's Gold Teeth and give them to the Warden in Fuchsia for HM04 (Strength).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 699 | 99% | 0.70 |
| intro | 53 | 51% | 0.42 |
| overworld | 4205 | 60% | 0.51 |
| prompt | 115 | 46% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1398)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 52 | 0.06 | 0.30 | 35% | `███████             ` |
| 0.1–0.2 | 501 | 0.15 | 0.27 | 59% | `████████████        ` |
| 0.2–0.3 | 790 | 0.24 | 0.35 | 56% | `███████████         ` |
| 0.3–0.4 | 647 | 0.34 | 0.43 | 55% | `███████████         ` |
| 0.4–0.5 | 534 | 0.44 | 0.53 | 55% | `███████████         ` |
| 0.5–0.6 | 442 | 0.54 | 0.62 | 62% | `████████████        ` |
| 0.6–0.7 | 414 | 0.65 | 0.70 | 72% | `██████████████      ` |
| 0.7–0.8 | 419 | 0.74 | 0.78 | 84% | `█████████████████   ` |
| 0.8–0.9 | 455 | 0.84 | 0.87 | 93% | `███████████████████ ` |
| 0.9–1.0 | 818 | 0.96 | 0.96 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it63_jev-latest_20261018_090229)

- CLI: `jev-agent` jev_agent.py v2 · server commit `81ac7cc` · prompt `49106d19e201a25e`
- Started 2026-10-18T09:02:29 · ended 2026-10-18T10:33:42 · active 1:31 h · wall 1:31 h · paused 0:00 h · exit: **stuck**
- Tool calls 33039 · images 3118 · reloads 4 · black-outs 0 · in-game playtime 18:41:47 · Pokédex 9 owned · maps visited 153
- Tokens uncached in / cache reads / out: 12.6M / 0.0M / 2327k · cost $0.53 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 60 | 184/196 | 141 | 131 | 173 | 138 | Slash, Cut, Ember, Strength |
| 2 | Magikarp | 5 | 17/17 | 7 | 10 | 14 | 7 | Splash |
| 3 | AAAAAAAAAA (Doduo) | 26 | 54/54 | 52 | 31 | 48 | 27 | Peck, Growl, Fury Attack |
| 4 | AAAAAAAAAA (Exeggcute) | 25 | 66/66 | 31 | 45 | 25 | 41 | Barrage, Hypnosis, Reflect |
| 5 | AAAAAAAAAA (Paras) | 22 | 53/53 | 40 | 35 | 16 | 29 | Scratch, Stun Spore, Leech Life |
| 6 | AAAAAAAAAA (Nidorino) | 30 | 85/85 | 53 | 48 | 47 | 44 | Tackle, Horn Attack, Poison Sting, Focus Energy |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:01 | game started |
| 0:00 | 95 | 0:00:17 | reached: Pallet Town |
| 0:00 | 128 | 0:02:06 | obtained: Charmander |
| 0:00 | 128 | 0:02:06 | starter: Charmander |
| 0:00 | 219 | 0:05:41 | reached: Route 1 |
| 0:00 | 236 | 0:07:22 | reached: Viridian City |
| 0:00 | 350 | 0:12:44 | reached: Route 2 |
| 0:00 | 394 | 0:15:27 | reached: Route 22 |
| 0:00 | 591 | 0:27:43 | reached: Pewter City |
| 0:01 | 1630 | 1:09:02 | evolved: Charmander → Charmeleon |
| 0:01 | 1998 | 1:24:03 | badge: Boulder |
| 0:01 | 2012 | 1:24:45 | reached: Route 3 |
| 0:01 | 2170 | 1:33:52 | reached: Route 4 |
| 0:01 | 2175 | 1:34:00 | reached: Mt. Moon 1F |
| 0:02 | 2748 | 2:03:55 | reached: Route 23 |
| 0:03 | 3751 | 2:34:26 | obtained: Magikarp |
| 0:05 | 4573 | 3:02:16 | reached: Cerulean City |
| 0:06 | 7043 | 4:34:28 | badge: Cascade |
| 0:06 | 7110 | 4:41:03 | reached: Route 24 |
| 0:07 | 7831 | 5:06:25 | reached: Route 25 |
| 0:07 | 8205 | 5:20:33 | reached: Route 5 |
| 0:07 | 8234 | 5:21:21 | reached: Route 9 |
| 0:08 | 8452 | 5:27:21 | reached: Route 6 |
| 0:08 | 8555 | 5:32:49 | reached: Vermilion City |
| 0:08 | 8594 | 5:34:15 | reached: Vermilion Dock |
| 0:08 | 8712 | 5:42:10 | evolved: Charmeleon → Charizard |
| 0:08 | 8996 | 5:53:25 | badge: Thunder |
| 0:08 | 9014 | 5:54:00 | reached: Route 11 |
| 0:10 | 9863 | 6:38:32 | reached: Route 12 |
| 0:13 | 10717 | 7:10:41 | reached: Route 10 |
| 0:13 | 10721 | 7:10:59 | reached: Rock Tunnel 1F |
| 0:13 | 10742 | 7:12:08 | reached: Rock Tunnel B1F |
| 0:23 | 14889 | 10:10:00 | reached: Lavender Town |
| 0:23 | 14947 | 10:11:35 | reached: Pokémon Tower 1F |
| 0:23 | 15085 | 10:18:18 | reached: Route 8 |
| 0:25 | 16074 | 11:19:10 | reached: Route 7 |
| 0:25 | 16080 | 11:19:19 | reached: Celadon City |
| 0:26 | 16284 | 11:31:28 | badge: Rainbow |
| 0:26 | 16355 | 11:33:35 | reached: Route 16 |
| 0:57 | 20613 | 14:06:10 | reached: Rocket Hideout B1F |
| 1:18 | 25660 | 16:19:37 | reached: Route 13 |
| 1:18 | 25718 | 16:25:38 | reached: Route 14 |
| 1:18 | 25888 | 16:35:18 | reached: Route 15 |
| 1:24 | 26813 | 17:15:22 | reached: Fuchsia City |
| 1:24 | 26941 | 17:26:34 | badge: Soul |
| 1:24 | 26953 | 17:27:42 | reached: Safari Zone Gate |
| 1:24 | 26960 | 17:28:03 | reached: Safari Zone Center |
| 1:24 | 27011 | 17:29:51 | reached: Route 18 |
| 1:24 | 27040 | 17:30:28 | reached: Route 19 |
| 1:25 | 27214 | 17:35:29 | reached: Safari Zone East |
| 1:25 | 27270 | 17:37:39 | obtained: Doduo |
| 1:25 | 27304 | 17:39:12 | obtained: Exeggcute |
| 1:25 | 27332 | 17:40:29 | obtained: Paras |
| 1:25 | 27336 | 17:40:38 | reached: Safari Zone North |
| 1:25 | 27340 | 17:41:21 | reached: Safari Zone West |
| 1:25 | 27467 | 17:50:50 | obtained: Nidorino |
| 1:25 | 27485 | 17:52:11 | obtained: Nidoran♂ |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T09:02:29 | 60 | rotate | 20972 | 7.3M / 0.0M / 1318k |
| 2 | 2026-10-18T10:02:33 | 31 | stuck | 12066 | 5.3M / 0.0M / 1009k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 12191 (asked Jev 10142, forced by code 2049, labelled 10142) · models jev-1.13.0 · input tokens 12568150 · Jev $0.5279
- Jev latency mean 101 ms · p50 81 · p95 298 · max 1500
- Fallbacks: none (variant without a safety net)
- Iteration 63
- Planner calls 0 ($0.0000, errors 0) · objective changes 91 · objectives Jev marked done 0 · final objective: Buy a drink (Fresh Water, Soda Pop or Lemonade) from a vending machine on the Celadon Mart roof, then walk into a Saffron gate: the thirsty guard takes it and lets you through.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 786 | 96% | 0.69 |
| faint_switch | 5 | 20% | 0.13 |
| intro | 52 | 50% | 0.40 |
| overworld | 9079 | 59% | 0.37 |
| prompt | 220 | 62% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1785)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 119 | 0.08 | 0.22 | 60% | `████████████        ` |
| 0.1–0.2 | 2068 | 0.15 | 0.23 | 56% | `███████████         ` |
| 0.2–0.3 | 2418 | 0.24 | 0.32 | 54% | `███████████         ` |
| 0.3–0.4 | 1539 | 0.34 | 0.41 | 54% | `███████████         ` |
| 0.4–0.5 | 960 | 0.44 | 0.51 | 61% | `████████████        ` |
| 0.5–0.6 | 719 | 0.55 | 0.61 | 64% | `█████████████       ` |
| 0.6–0.7 | 699 | 0.64 | 0.69 | 75% | `███████████████     ` |
| 0.7–0.8 | 622 | 0.74 | 0.78 | 85% | `█████████████████   ` |
| 0.8–0.9 | 500 | 0.84 | 0.86 | 90% | `██████████████████  ` |
| 0.9–1.0 | 498 | 0.97 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it59_jev-latest_20261018_024022)

- CLI: `jev-agent` jev_agent.py v2 · server commit `8b6b5d9` · prompt `49106d19e201a25e`
- Started 2026-10-18T02:40:22 · ended 2026-10-18T04:35:34 · active 1:55 h · wall 1:55 h · paused 0:00 h · exit: **stuck**
- Tool calls 52493 · images 11171 · reloads 24 · black-outs 0 · in-game playtime 20:02:21 · Pokédex 10 owned · maps visited 155
- Tokens uncached in / cache reads / out: 18.9M / 0.0M / 3770k · cost $0.80 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 61 | 188/210 | 146 | 134 | 181 | 157 | Fire Spin, Cut, Ember, Leer |
| 2 | AAAAAAAAAA (Doduo) | 26 | 57/57 | 52 | 35 | 48 | 23 | Peck, Growl, Fury Attack |
| 3 | AAAAAAAAAA (Exeggcute) | 23 | 61/61 | 28 | 41 | 23 | 34 | Barrage, Hypnosis |
| 4 | AAAAAAAAAA (Nidoran♂) | 24 | 62/62 | 37 | 28 | 29 | 27 | Tackle, Horn Attack, Poison Sting, Focus Energy |
| 5 | AAAAAAAAAA (Exeggcute) | 25 | 71/71 | 28 | 45 | 32 | 39 | Barrage, Hypnosis, Reflect |
| 6 | AAAAAAAAAA (Paras) | 22 | 47/47 | 41 | 31 | 16 | 30 | Scratch, Stun Spore, Leech Life |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 90 | 0:00:18 | reached: Pallet Town |
| 0:00 | 123 | 0:02:08 | obtained: Charmander |
| 0:00 | 123 | 0:02:08 | starter: Charmander |
| 0:00 | 189 | 0:04:57 | reached: Route 1 |
| 0:00 | 206 | 0:06:47 | reached: Viridian City |
| 0:00 | 389 | 0:13:51 | reached: Route 2 |
| 0:00 | 431 | 0:16:38 | reached: Route 22 |
| 0:00 | 624 | 0:29:16 | reached: Pewter City |
| 0:01 | 1396 | 1:02:52 | evolved: Charmander → Charmeleon |
| 0:02 | 3472 | 2:19:26 | badge: Boulder |
| 0:02 | 3488 | 2:20:17 | reached: Route 3 |
| 0:02 | 3679 | 2:30:12 | reached: Route 4 |
| 0:02 | 3683 | 2:30:20 | reached: Mt. Moon 1F |
| 0:03 | 4385 | 3:03:58 | reached: Route 23 |
| 0:03 | 4977 | 3:22:01 | reached: Cerulean City |
| 0:05 | 8097 | 5:19:03 | badge: Cascade |
| 0:05 | 8116 | 5:21:09 | reached: Route 24 |
| 0:06 | 8967 | 5:51:07 | reached: Route 25 |
| 0:07 | 9336 | 6:05:38 | reached: Route 5 |
| 0:07 | 9365 | 6:06:26 | reached: Route 9 |
| 0:07 | 9517 | 6:10:37 | reached: Route 6 |
| 0:07 | 9558 | 6:13:34 | reached: Vermilion City |
| 0:07 | 9594 | 6:14:51 | reached: Vermilion Dock |
| 0:07 | 9621 | 6:17:14 | evolved: Charmeleon → Charizard |
| 0:07 | 9970 | 6:33:33 | badge: Thunder |
| 0:07 | 9996 | 6:34:16 | reached: Route 11 |
| 0:07 | 10210 | 6:41:15 | reached: Route 12 |
| 0:09 | 10864 | 7:04:00 | reached: Route 10 |
| 0:13 | 11843 | 7:37:31 | reached: Rock Tunnel 1F |
| 0:13 | 11873 | 7:38:46 | reached: Rock Tunnel B1F |
| 0:17 | 13697 | 8:56:14 | reached: Lavender Town |
| 0:17 | 13748 | 8:57:37 | reached: Pokémon Tower 1F |
| 0:30 | 16170 | 9:53:25 | reached: Route 8 |
| 0:36 | 17712 | 11:22:33 | reached: Route 7 |
| 0:36 | 17718 | 11:22:42 | reached: Celadon City |
| 0:36 | 17884 | 11:33:18 | badge: Rainbow |
| 0:37 | 18322 | 11:46:53 | reached: Route 16 |
| 0:51 | 20496 | 13:02:52 | reached: Rocket Hideout B1F |
| 1:03 | 25455 | 15:25:40 | reached: Route 13 |
| 1:03 | 25532 | 15:32:03 | reached: Route 14 |
| 1:03 | 25689 | 15:41:05 | reached: Route 15 |
| 1:04 | 26014 | 16:00:40 | reached: Fuchsia City |
| 1:04 | 26122 | 16:10:22 | badge: Soul |
| 1:04 | 26156 | 16:12:07 | reached: Safari Zone Gate |
| 1:04 | 26163 | 16:12:28 | reached: Safari Zone Center |
| 1:04 | 26197 | 16:13:14 | reached: Safari Zone East |
| 1:04 | 26233 | 16:14:25 | obtained: Doduo |
| 1:04 | 26282 | 16:16:36 | obtained: Exeggcute |
| 1:04 | 26314 | 16:18:04 | obtained: Nidoran♂ |
| 1:04 | 26318 | 16:18:09 | reached: Safari Zone North |
| 1:04 | 26368 | 16:20:47 | reached: Safari Zone West |
| 1:05 | 26599 | 16:30:04 | obtained: Paras |
| 1:05 | 27161 | 16:52:50 | obtained: Venonat |
| 1:05 | 27331 | 16:59:59 | obtained: Rhyhorn |
| 1:05 | 27559 | 17:07:49 | obtained: Nidorino |
| 1:08 | 31277 | 18:04:11 | reached: Route 19 |
| 1:08 | 31325 | 18:05:52 | reached: Route 18 |
| 1:18 | 34627 | 18:57:58 | obtained: Nidoran♀ |
| 1:20 | 37123 | 19:10:26 | obtained: Parasect |
| 1:25 | 42419 | 18:48:43 | obtained: Nidorina |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T02:40:22 | 60 | rotate | 24802 | 8.8M / 0.0M / 1646k |
| 2 | 2026-10-18T03:40:27 | 55 | stuck | 27688 | 10.2M / 0.0M / 2123k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 25086 (asked Jev 15750, forced by code 9336, labelled 15750) · models jev-1.13.0 · input tokens 18950361 · Jev $0.7959
- Jev latency mean 83 ms · p50 74 · p95 144 · max 610
- Fallbacks: none (variant without a safety net)
- Iteration 59
- Planner calls 0 ($0.0000, errors 0) · objective changes 90 · objectives Jev marked done 0 · final objective: Find the Safari Zone's Gold Teeth and give them to the Warden in Fuchsia for HM04 (Strength).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 904 | 95% | 0.68 |
| intro | 52 | 46% | 0.41 |
| overworld | 14566 | 54% | 0.34 |
| prompt | 228 | 74% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1601)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 300 | 0.08 | 0.18 | 54% | `███████████         ` |
| 0.1–0.2 | 3829 | 0.15 | 0.22 | 51% | `██████████          ` |
| 0.2–0.3 | 4058 | 0.24 | 0.31 | 49% | `██████████          ` |
| 0.3–0.4 | 2260 | 0.34 | 0.41 | 47% | `█████████           ` |
| 0.4–0.5 | 1336 | 0.44 | 0.51 | 56% | `███████████         ` |
| 0.5–0.6 | 1093 | 0.54 | 0.60 | 64% | `█████████████       ` |
| 0.6–0.7 | 882 | 0.64 | 0.69 | 76% | `███████████████     ` |
| 0.7–0.8 | 771 | 0.74 | 0.78 | 84% | `█████████████████   ` |
| 0.8–0.9 | 558 | 0.84 | 0.86 | 85% | `█████████████████   ` |
| 0.9–1.0 | 663 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it84_jev-latest_20261020_031931)

- CLI: `jev-agent` jev_agent.py v2 · server commit `c757cd8` · prompt `49106d19e201a25e`
- Started 2026-10-20T03:19:31 · ended 2026-10-20T03:52:01 · active 0:32 h · wall 0:32 h · paused 0:00 h · exit: **manual**
- Tool calls 17626 · images 1567 · reloads 0 · black-outs 0 · in-game playtime 11:27:43 · Pokédex 3 owned · maps visited 113
- Tokens uncached in / cache reads / out: 5.3M / 0.0M / 952k · cost $0.22 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 49 | 167/170 | 116 | 103 | 136 | 110 | Scratch, Slash, Flamethrower, Cut |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:17 | reached: Pallet Town |
| 0:00 | 124 | 0:02:19 | obtained: Charmander |
| 0:00 | 124 | 0:02:19 | starter: Charmander |
| 0:00 | 152 | 0:04:14 | reached: Route 1 |
| 0:00 | 169 | 0:05:50 | reached: Viridian City |
| 0:00 | 255 | 0:10:05 | reached: Route 2 |
| 0:00 | 359 | 0:16:45 | reached: Pewter City |
| 0:01 | 1859 | 0:59:06 | evolved: Charmander → Charmeleon |
| 0:02 | 4578 | 2:08:07 | badge: Boulder |
| 0:02 | 4587 | 2:08:28 | reached: Route 3 |
| 0:02 | 4657 | 2:15:11 | reached: Route 4 |
| 0:02 | 4661 | 2:15:20 | reached: Mt. Moon 1F |
| 0:02 | 5016 | 2:30:27 | reached: Route 22 |
| 0:02 | 5027 | 2:30:59 | reached: Route 23 |
| 0:07 | 7630 | 4:15:48 | reached: Cerulean City |
| 0:08 | 10265 | 5:53:59 | badge: Cascade |
| 0:08 | 10285 | 5:56:13 | reached: Route 24 |
| 0:08 | 10387 | 6:02:58 | reached: Route 25 |
| 0:09 | 10708 | 6:17:37 | reached: Route 5 |
| 0:09 | 10726 | 6:18:09 | reached: Route 6 |
| 0:09 | 10762 | 6:20:44 | reached: Vermilion City |
| 0:09 | 10799 | 6:22:07 | reached: Vermilion Dock |
| 0:09 | 10820 | 6:24:17 | evolved: Charmeleon → Charizard |
| 0:09 | 11490 | 6:50:00 | badge: Thunder |
| 0:09 | 11533 | 6:51:29 | reached: Route 9 |
| 0:09 | 11623 | 6:59:09 | reached: Route 10 |
| 0:09 | 11627 | 6:59:27 | reached: Rock Tunnel 1F |
| 0:09 | 11647 | 7:01:02 | reached: Rock Tunnel B1F |
| 0:14 | 13293 | 8:09:51 | reached: Route 11 |
| 0:16 | 14061 | 8:45:34 | reached: Route 12 |
| 0:17 | 14727 | 9:10:43 | reached: Lavender Town |
| 0:17 | 14898 | 9:14:42 | reached: Route 8 |
| 0:18 | 15009 | 9:24:03 | reached: Route 7 |
| 0:18 | 15015 | 9:24:12 | reached: Celadon City |
| 0:18 | 15171 | 9:34:58 | badge: Rainbow |
| 0:20 | 15886 | 9:57:20 | reached: Route 16 |
| 0:20 | 16028 | 10:02:11 | reached: Pokémon Tower 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 32.5 min, longest 32 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T03:19:31 | 32 | exited | 17626 | 5.3M / 0.0M / 952k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 5878 (asked Jev 4405, forced by code 1473, labelled 4405) · models jev-1.13.0 · input tokens 5271524 · Jev $0.2214
- Jev latency mean 78 ms · p50 60 · p95 158 · max 1140
- Fallbacks: none (variant without a safety net)
- Iteration 84
- Planner calls 0 ($0.0000, errors 0) · objective changes 75 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout Elevator, examine the panel on its wall, choose B4F and walk out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 588 | 94% | 0.69 |
| intro | 50 | 50% | 0.42 |
| overworld | 3680 | 62% | 0.54 |
| prompt | 87 | 57% | 0.47 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.162)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 30 | 0.06 | 0.33 | 67% | `█████████████       ` |
| 0.1–0.2 | 304 | 0.15 | 0.27 | 62% | `████████████        ` |
| 0.2–0.3 | 649 | 0.24 | 0.34 | 58% | `████████████        ` |
| 0.3–0.4 | 684 | 0.34 | 0.43 | 59% | `████████████        ` |
| 0.4–0.5 | 505 | 0.44 | 0.52 | 56% | `███████████         ` |
| 0.5–0.6 | 367 | 0.54 | 0.61 | 64% | `█████████████       ` |
| 0.6–0.7 | 323 | 0.64 | 0.70 | 77% | `███████████████     ` |
| 0.7–0.8 | 362 | 0.74 | 0.79 | 83% | `█████████████████   ` |
| 0.8–0.9 | 347 | 0.84 | 0.87 | 90% | `██████████████████  ` |
| 0.9–1.0 | 834 | 0.96 | 0.96 | 66% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it80_jev-latest_20261020_000623)

- CLI: `jev-agent` jev_agent.py v2 · server commit `c3b9cf4` · prompt `49106d19e201a25e`
- Started 2026-10-20T00:06:23 · ended 2026-10-20T00:39:54 · active 0:33 h · wall 0:33 h · paused 0:00 h · exit: **manual**
- Tool calls 20968 · images 1740 · reloads 0 · black-outs 0 · in-game playtime 12:54:54 · Pokédex 4 owned · maps visited 109
- Tokens uncached in / cache reads / out: 6.6M / 0.0M / 1224k · cost $0.28 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 52 | 154/165 | 117 | 122 | 141 | 115 | Flamethrower, Cut, Ember, Slash |
| 2 | Magikarp | 5 | 18/18 | 6 | 11 | 14 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 88 | 0:00:13 | reached: Pallet Town |
| 0:00 | 132 | 0:02:31 | obtained: Charmander |
| 0:00 | 132 | 0:02:31 | starter: Charmander |
| 0:00 | 160 | 0:04:53 | reached: Route 1 |
| 0:00 | 171 | 0:05:46 | reached: Viridian City |
| 0:00 | 258 | 0:10:07 | reached: Route 2 |
| 0:00 | 284 | 0:11:07 | reached: Route 22 |
| 0:00 | 655 | 0:32:45 | reached: Pewter City |
| 0:01 | 2237 | 1:21:35 | evolved: Charmander → Charmeleon |
| 0:01 | 2863 | 1:38:57 | badge: Boulder |
| 0:01 | 2872 | 1:39:19 | reached: Route 3 |
| 0:01 | 2964 | 1:46:56 | reached: Route 4 |
| 0:01 | 2968 | 1:47:04 | reached: Mt. Moon 1F |
| 0:02 | 3322 | 2:02:56 | reached: Route 23 |
| 0:03 | 4095 | 2:34:03 | obtained: Magikarp |
| 0:05 | 5047 | 3:02:41 | reached: Cerulean City |
| 0:07 | 9274 | 5:39:53 | badge: Cascade |
| 0:07 | 9295 | 5:42:07 | reached: Route 24 |
| 0:08 | 10078 | 6:09:34 | reached: Route 25 |
| 0:08 | 10101 | 6:11:47 | evolved: Charmeleon → Charizard |
| 0:09 | 11555 | 6:54:51 | reached: Route 5 |
| 0:09 | 11590 | 6:55:43 | reached: Route 9 |
| 0:11 | 12109 | 7:15:25 | reached: Route 6 |
| 0:11 | 12203 | 7:22:51 | reached: Vermilion City |
| 0:11 | 12235 | 7:24:04 | reached: Vermilion Dock |
| 0:11 | 12771 | 7:47:36 | badge: Thunder |
| 0:12 | 13048 | 8:00:53 | reached: Route 11 |
| 0:15 | 14693 | 8:59:11 | reached: Route 10 |
| 0:15 | 14697 | 8:59:30 | reached: Rock Tunnel 1F |
| 0:15 | 14752 | 9:02:56 | reached: Rock Tunnel B1F |
| 0:17 | 16122 | 9:58:05 | reached: Lavender Town |
| 0:17 | 16158 | 9:59:15 | reached: Route 12 |
| 0:17 | 16424 | 10:07:57 | reached: Route 8 |
| 0:19 | 16770 | 10:27:10 | reached: Pokémon Tower 1F |
| 0:21 | 17353 | 11:08:26 | reached: Route 7 |
| 0:21 | 17359 | 11:08:35 | reached: Celadon City |
| 0:21 | 17504 | 11:17:40 | badge: Rainbow |
| 0:21 | 17660 | 11:23:44 | reached: Rocket Hideout B1F |
| 0:32 | 20760 | 12:48:08 | reached: Route 13 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 33.5 min, longest 33 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T00:06:23 | 33 | exited | 20968 | 6.6M / 0.0M / 1224k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7047 (asked Jev 5499, forced by code 1548, labelled 5499) · models jev-1.13.0 · input tokens 6614401 · Jev $0.2778
- Jev latency mean 87 ms · p50 63 · p95 284 · max 1150
- Fallbacks: none (variant without a safety net)
- Iteration 80
- Planner calls 0 ($0.0000, errors 0) · objective changes 68 · objectives Jev marked done 0 · final objective: Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 657 | 96% | 0.68 |
| faint_switch | 4 | 0% | 0.23 |
| intro | 53 | 55% | 0.40 |
| overworld | 4657 | 60% | 0.49 |
| prompt | 128 | 56% | 0.51 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1564)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 35 | 0.08 | 0.21 | 74% | `███████████████     ` |
| 0.1–0.2 | 526 | 0.15 | 0.24 | 64% | `█████████████       ` |
| 0.2–0.3 | 973 | 0.25 | 0.33 | 57% | `███████████         ` |
| 0.3–0.4 | 853 | 0.34 | 0.41 | 55% | `███████████         ` |
| 0.4–0.5 | 616 | 0.44 | 0.51 | 55% | `███████████         ` |
| 0.5–0.6 | 510 | 0.54 | 0.60 | 60% | `████████████        ` |
| 0.6–0.7 | 429 | 0.64 | 0.69 | 72% | `██████████████      ` |
| 0.7–0.8 | 427 | 0.74 | 0.78 | 83% | `█████████████████   ` |
| 0.8–0.9 | 393 | 0.84 | 0.87 | 84% | `█████████████████   ` |
| 0.9–1.0 | 737 | 0.96 | 0.96 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it77_jev-latest_20261019_205630)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1ad3ffc` · prompt `49106d19e201a25e`
- Started 2026-10-19T20:56:30 · ended 2026-10-19T21:58:38 · active 1:02 h · wall 1:02 h · paused 0:00 h · exit: **manual**
- Tool calls 21644 · images 2047 · reloads 3 · black-outs 0 · in-game playtime 12:38:32 · Pokédex 4 owned · maps visited 120
- Tokens uncached in / cache reads / out: 8.0M / 0.0M / 1492k · cost $0.33 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 52 | 175/175 | 126 | 115 | 140 | 126 | Flamethrower, Cut, Ember, Leer |
| 2 | Magikarp | 5 | 17/17 | 6 | 11 | 14 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:16 | reached: Pallet Town |
| 0:00 | 125 | 0:02:21 | obtained: Charmander |
| 0:00 | 125 | 0:02:21 | starter: Charmander |
| 0:00 | 153 | 0:04:19 | reached: Route 1 |
| 0:00 | 170 | 0:05:47 | reached: Viridian City |
| 0:00 | 272 | 0:10:50 | reached: Route 2 |
| 0:00 | 299 | 0:11:50 | reached: Route 22 |
| 0:00 | 628 | 0:32:39 | reached: Pewter City |
| 0:00 | 1296 | 1:03:40 | evolved: Charmander → Charmeleon |
| 0:00 | 1297 | 1:03:59 | badge: Boulder |
| 0:00 | 1306 | 1:04:21 | reached: Route 3 |
| 0:00 | 1405 | 1:16:13 | reached: Route 4 |
| 0:00 | 1409 | 1:16:22 | reached: Mt. Moon 1F |
| 0:01 | 1869 | 1:37:05 | reached: Route 23 |
| 0:03 | 3334 | 2:37:48 | obtained: Magikarp |
| 0:04 | 3746 | 2:55:44 | reached: Cerulean City |
| 0:06 | 7311 | 5:06:04 | reached: Route 24 |
| 0:06 | 7788 | 5:28:48 | badge: Cascade |
| 0:06 | 7859 | 5:31:05 | reached: Route 25 |
| 0:06 | 7912 | 5:35:51 | evolved: Charmeleon → Charizard |
| 0:06 | 8146 | 5:43:09 | reached: Route 5 |
| 0:06 | 8175 | 5:44:01 | reached: Route 9 |
| 0:07 | 8494 | 5:54:34 | reached: Route 6 |
| 0:07 | 8539 | 5:57:50 | reached: Vermilion City |
| 0:07 | 8572 | 5:59:02 | reached: Vermilion Dock |
| 0:07 | 8942 | 6:17:09 | badge: Thunder |
| 0:07 | 9043 | 6:22:23 | reached: Route 10 |
| 0:07 | 9047 | 6:22:41 | reached: Rock Tunnel 1F |
| 0:07 | 9082 | 6:24:34 | reached: Rock Tunnel B1F |
| 0:09 | 10912 | 7:41:03 | reached: Route 11 |
| 0:09 | 11084 | 7:49:55 | reached: Lavender Town |
| 0:09 | 11145 | 7:51:27 | reached: Route 12 |
| 0:10 | 11291 | 7:54:36 | reached: Route 8 |
| 0:10 | 11386 | 8:01:24 | reached: Pokémon Tower 1F |
| 0:19 | 15045 | 9:22:22 | reached: Route 7 |
| 0:19 | 15051 | 9:22:31 | reached: Celadon City |
| 0:19 | 15114 | 9:25:22 | reached: Route 16 |
| 0:22 | 16267 | 10:11:10 | badge: Rainbow |
| 0:23 | 16380 | 10:15:09 | reached: Rocket Hideout B1F |
| 0:32 | 18266 | 11:24:43 | reached: Route 13 |
| 0:32 | 18329 | 11:30:39 | reached: Route 14 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T20:56:30 | 60 | rotate | 21504 | 7.9M / 0.0M / 1474k |
| 2 | 2026-10-19T21:56:35 | 2 | exited | 139 | 0.1M / 0.0M / 18k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8234 (asked Jev 6615, forced by code 1619, labelled 6615) · models jev-1.13.0 · input tokens 7954808 · Jev $0.3341
- Jev latency mean 87 ms · p50 69 · p95 169 · max 7838
- Fallbacks: none (variant without a safety net)
- Iteration 77
- Planner calls 0 ($0.0000, errors 0) · objective changes 73 · objectives Jev marked done 0 · final objective: Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 907 | 73% | 0.66 |
| faint_switch | 3 | 0% | 0.18 |
| intro | 51 | 47% | 0.42 |
| overworld | 5536 | 64% | 0.42 |
| prompt | 118 | 48% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1871)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 99 | 0.08 | 0.19 | 62% | `████████████        ` |
| 0.1–0.2 | 1120 | 0.15 | 0.22 | 58% | `████████████        ` |
| 0.2–0.3 | 1242 | 0.24 | 0.32 | 61% | `████████████        ` |
| 0.3–0.4 | 892 | 0.34 | 0.42 | 58% | `████████████        ` |
| 0.4–0.5 | 663 | 0.44 | 0.51 | 61% | `████████████        ` |
| 0.5–0.6 | 551 | 0.55 | 0.61 | 67% | `█████████████       ` |
| 0.6–0.7 | 494 | 0.64 | 0.69 | 69% | `██████████████      ` |
| 0.7–0.8 | 459 | 0.75 | 0.78 | 76% | `███████████████     ` |
| 0.8–0.9 | 493 | 0.84 | 0.87 | 82% | `████████████████    ` |
| 0.9–1.0 | 602 | 0.96 | 0.97 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it52_jev-latest_20261017_175920)

- CLI: `jev-agent` jev_agent.py v2 · server commit `00dc428` · prompt `49106d19e201a25e`
- Started 2026-10-17T17:59:20 · ended 2026-10-17T18:50:06 · active 0:50 h · wall 0:50 h · paused 0:00 h · exit: **stuck**
- Tool calls 23361 · images 2022 · reloads 4 · black-outs 0 · in-game playtime 13:20:30 · Pokédex 3 owned · maps visited 126
- Tokens uncached in / cache reads / out: 9.2M / 0.0M / 1748k · cost $0.39 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 49 | 165/165 | 114 | 104 | 137 | 118 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:01 | game started |
| 0:00 | 87 | 0:00:12 | reached: Pallet Town |
| 0:00 | 122 | 0:02:04 | obtained: Charmander |
| 0:00 | 122 | 0:02:04 | starter: Charmander |
| 0:00 | 188 | 0:05:08 | reached: Route 1 |
| 0:00 | 205 | 0:06:46 | reached: Viridian City |
| 0:00 | 471 | 0:15:43 | reached: Route 2 |
| 0:00 | 513 | 0:18:56 | reached: Route 22 |
| 0:00 | 760 | 0:32:25 | reached: Pewter City |
| 0:01 | 1610 | 1:09:53 | evolved: Charmander → Charmeleon |
| 0:01 | 2432 | 1:43:29 | badge: Boulder |
| 0:01 | 2448 | 1:44:20 | reached: Route 3 |
| 0:01 | 2515 | 1:50:40 | reached: Route 4 |
| 0:01 | 2520 | 1:50:49 | reached: Mt. Moon 1F |
| 0:02 | 2936 | 2:10:51 | reached: Route 23 |
| 0:04 | 4141 | 3:07:16 | reached: Cerulean City |
| 0:06 | 8588 | 6:06:05 | badge: Cascade |
| 0:06 | 8609 | 6:08:37 | reached: Route 24 |
| 0:06 | 8638 | 6:11:40 | evolved: Charmeleon → Charizard |
| 0:07 | 9392 | 6:36:25 | reached: Route 25 |
| 0:08 | 9658 | 6:58:58 | reached: Route 5 |
| 0:08 | 9688 | 6:59:49 | reached: Route 9 |
| 0:08 | 9819 | 7:03:20 | reached: Route 6 |
| 0:08 | 9860 | 7:06:16 | reached: Vermilion City |
| 0:08 | 9920 | 7:08:15 | reached: Vermilion Dock |
| 0:08 | 10103 | 7:20:10 | badge: Thunder |
| 0:08 | 10125 | 7:20:49 | reached: Route 11 |
| 0:09 | 10593 | 7:37:35 | reached: Route 12 |
| 0:14 | 11979 | 8:24:06 | reached: Route 10 |
| 0:14 | 11984 | 8:24:24 | reached: Rock Tunnel 1F |
| 0:14 | 12048 | 8:27:45 | reached: Rock Tunnel B1F |
| 0:17 | 13916 | 10:00:05 | reached: Lavender Town |
| 0:17 | 13970 | 10:01:34 | reached: Pokémon Tower 1F |
| 0:18 | 14125 | 10:06:26 | reached: Route 8 |
| 0:24 | 16081 | 10:56:32 | reached: Route 7 |
| 0:24 | 16087 | 10:56:41 | reached: Celadon City |
| 0:24 | 16256 | 11:08:23 | badge: Rainbow |
| 0:26 | 16820 | 11:22:24 | reached: Route 16 |
| 0:36 | 18200 | 12:23:58 | reached: Rocket Hideout B1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 50.8 min, longest 51 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T17:59:20 | 51 | stuck | 23361 | 9.2M / 0.0M / 1748k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8982 (asked Jev 7192, forced by code 1790, labelled 7192) · models jev-1.13.0 · input tokens 9176317 · Jev $0.3854
- Jev latency mean 93 ms · p50 79 · p95 176 · max 899
- Fallbacks: none (variant without a safety net)
- Iteration 52
- Planner calls 0 ($0.0000, errors 0) · objective changes 70 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout Elevator, examine the panel on its wall, choose B4F and walk out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1080 | 71% | 0.66 |
| intro | 54 | 48% | 0.42 |
| overworld | 5981 | 60% | 0.42 |
| prompt | 77 | 57% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1525)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 61 | 0.08 | 0.22 | 66% | `█████████████       ` |
| 0.1–0.2 | 917 | 0.16 | 0.24 | 55% | `███████████         ` |
| 0.2–0.3 | 1483 | 0.24 | 0.32 | 52% | `██████████          ` |
| 0.3–0.4 | 1222 | 0.34 | 0.41 | 55% | `███████████         ` |
| 0.4–0.5 | 895 | 0.44 | 0.51 | 59% | `████████████        ` |
| 0.5–0.6 | 565 | 0.54 | 0.61 | 66% | `█████████████       ` |
| 0.6–0.7 | 468 | 0.64 | 0.70 | 71% | `██████████████      ` |
| 0.7–0.8 | 479 | 0.74 | 0.79 | 71% | `██████████████      ` |
| 0.8–0.9 | 441 | 0.84 | 0.87 | 87% | `█████████████████   ` |
| 0.9–1.0 | 661 | 0.96 | 0.97 | 74% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it81_jev-latest_20261020_005716)

- CLI: `jev-agent` jev_agent.py v2 · server commit `c06d08a` · prompt `49106d19e201a25e`
- Started 2026-10-20T00:57:16 · ended 2026-10-20T01:59:47 · active 1:02 h · wall 1:02 h · paused 0:00 h · exit: **manual**
- Tool calls 23978 · images 2042 · reloads 1 · black-outs 0 · in-game playtime 15:04:36 · Pokédex 4 owned · maps visited 132
- Tokens uncached in / cache reads / out: 8.5M / 0.0M / 1555k · cost $0.36 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 57 | 193/193 | 143 | 135 | 162 | 142 | Scratch, Slash, Flamethrower, Cut |
| 2 | Magikarp | 7 | 20/20 | 7 | 13 | 17 | 9 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 102 | 0:00:25 | reached: Pallet Town |
| 0:00 | 144 | 0:02:39 | obtained: Charmander |
| 0:00 | 144 | 0:02:39 | starter: Charmander |
| 0:00 | 172 | 0:04:43 | reached: Route 1 |
| 0:00 | 195 | 0:06:46 | reached: Viridian City |
| 0:00 | 326 | 0:12:17 | reached: Route 2 |
| 0:00 | 352 | 0:13:17 | reached: Route 22 |
| 0:00 | 827 | 0:43:34 | reached: Pewter City |
| 0:01 | 1497 | 1:07:42 | evolved: Charmander → Charmeleon |
| 0:01 | 1559 | 1:12:48 | badge: Boulder |
| 0:01 | 1569 | 1:13:09 | reached: Route 3 |
| 0:01 | 1660 | 1:21:09 | reached: Route 4 |
| 0:01 | 1664 | 1:21:17 | reached: Mt. Moon 1F |
| 0:01 | 2091 | 1:40:07 | reached: Route 23 |
| 0:03 | 3047 | 2:08:38 | obtained: Magikarp |
| 0:04 | 3898 | 2:35:42 | reached: Cerulean City |
| 0:04 | 4002 | 2:44:07 | reached: Route 24 |
| 0:05 | 5612 | 3:46:08 | badge: Cascade |
| 0:05 | 5704 | 3:49:35 | reached: Route 25 |
| 0:06 | 5992 | 4:02:31 | reached: Route 5 |
| 0:06 | 6021 | 4:03:22 | reached: Route 9 |
| 0:06 | 6361 | 4:14:56 | reached: Route 6 |
| 0:06 | 6402 | 4:18:20 | reached: Vermilion City |
| 0:06 | 6435 | 4:19:33 | reached: Vermilion Dock |
| 0:06 | 6536 | 4:25:58 | reached: Route 11 |
| 0:07 | 7294 | 4:54:28 | reached: Route 12 |
| 0:08 | 7960 | 5:19:02 | badge: Thunder |
| 0:09 | 8150 | 5:28:00 | evolved: Charmeleon → Charizard |
| 0:11 | 9546 | 6:12:34 | reached: Route 10 |
| 0:11 | 9551 | 6:12:52 | reached: Rock Tunnel 1F |
| 0:11 | 9565 | 6:13:48 | reached: Rock Tunnel B1F |
| 0:33 | 16256 | 9:32:45 | reached: Lavender Town |
| 0:33 | 16394 | 9:35:59 | reached: Route 8 |
| 0:33 | 16473 | 9:41:07 | reached: Pokémon Tower 1F |
| 0:37 | 17545 | 10:35:18 | reached: Route 7 |
| 0:37 | 17551 | 10:35:27 | reached: Celadon City |
| 0:38 | 17782 | 11:00:17 | badge: Rainbow |
| 0:38 | 17914 | 11:05:38 | reached: Rocket Hideout B1F |
| 0:43 | 20208 | 12:24:20 | reached: Route 16 |
| 0:44 | 20984 | 12:52:49 | reached: Route 13 |
| 0:44 | 21047 | 12:58:44 | reached: Route 14 |
| 0:44 | 21195 | 13:07:28 | reached: Route 15 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T00:57:16 | 60 | rotate | 23628 | 8.4M / 0.0M / 1537k |
| 2 | 2026-10-20T01:57:20 | 2 | exited | 349 | 0.1M / 0.0M / 18k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8513 (asked Jev 6890, forced by code 1623, labelled 6890) · models jev-1.13.0 · input tokens 8517478 · Jev $0.3577
- Jev latency mean 80 ms · p50 62 · p95 168 · max 1015
- Fallbacks: none (variant without a safety net)
- Iteration 81
- Planner calls 0 ($0.0000, errors 0) · objective changes 63 · objectives Jev marked done 0 · final objective: Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 630 | 92% | 0.63 |
| faint_switch | 2 | 0% | 0.23 |
| intro | 53 | 55% | 0.44 |
| overworld | 6031 | 63% | 0.43 |
| prompt | 174 | 43% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1577)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 58 | 0.07 | 0.25 | 57% | `███████████         ` |
| 0.1–0.2 | 829 | 0.15 | 0.25 | 59% | `████████████        ` |
| 0.2–0.3 | 1368 | 0.24 | 0.33 | 55% | `███████████         ` |
| 0.3–0.4 | 1208 | 0.34 | 0.42 | 54% | `███████████         ` |
| 0.4–0.5 | 865 | 0.44 | 0.52 | 64% | `█████████████       ` |
| 0.5–0.6 | 696 | 0.55 | 0.61 | 70% | `██████████████      ` |
| 0.6–0.7 | 552 | 0.64 | 0.70 | 76% | `███████████████     ` |
| 0.7–0.8 | 566 | 0.74 | 0.78 | 86% | `█████████████████   ` |
| 0.8–0.9 | 359 | 0.84 | 0.86 | 88% | `██████████████████  ` |
| 0.9–1.0 | 389 | 0.95 | 0.96 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it70_jev-latest_20261018_215454)

- CLI: `jev-agent` jev_agent.py v2 · server commit `ca6bee5` · prompt `49106d19e201a25e`
- Started 2026-10-18T21:54:54 · ended 2026-10-18T23:51:57 · active 1:56 h · wall 1:57 h · paused 0:00 h · exit: **stuck**
- Tool calls 26198 · images 2548 · reloads 3 · black-outs 0 · in-game playtime 15:20:36 · Pokédex 3 owned · maps visited 130
- Tokens uncached in / cache reads / out: 9.4M / 0.0M / 1790k · cost $0.40 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 55 | 190/190 | 132 | 121 | 146 | 129 | Fire Spin, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:16 | reached: Pallet Town |
| 0:00 | 136 | 0:02:46 | obtained: Charmander |
| 0:00 | 136 | 0:02:46 | starter: Charmander |
| 0:00 | 164 | 0:04:42 | reached: Route 1 |
| 0:00 | 175 | 0:05:27 | reached: Viridian City |
| 0:00 | 398 | 0:14:35 | reached: Route 2 |
| 0:00 | 424 | 0:15:36 | reached: Route 22 |
| 0:00 | 1121 | 0:54:02 | reached: Pewter City |
| 0:01 | 1304 | 1:05:54 | badge: Boulder |
| 0:01 | 1330 | 1:06:49 | reached: Route 3 |
| 0:01 | 1349 | 1:09:48 | evolved: Charmander → Charmeleon |
| 0:01 | 1428 | 1:15:48 | reached: Route 4 |
| 0:01 | 1432 | 1:15:57 | reached: Mt. Moon 1F |
| 0:01 | 2071 | 1:45:22 | reached: Route 23 |
| 0:04 | 3534 | 2:45:35 | reached: Cerulean City |
| 0:07 | 7721 | 5:24:04 | badge: Cascade |
| 0:07 | 7757 | 5:27:06 | reached: Route 24 |
| 0:08 | 8586 | 5:57:21 | reached: Route 25 |
| 0:08 | 8645 | 6:03:00 | obtained: Charizard |
| 0:08 | 8866 | 6:09:45 | reached: Route 5 |
| 0:08 | 8893 | 6:10:33 | reached: Route 9 |
| 0:09 | 9135 | 6:18:50 | reached: Route 6 |
| 0:09 | 9176 | 6:21:37 | reached: Vermilion City |
| 0:09 | 9208 | 6:22:49 | reached: Vermilion Dock |
| 0:09 | 9410 | 6:35:33 | badge: Thunder |
| 0:09 | 9509 | 6:40:48 | reached: Route 10 |
| 0:09 | 9514 | 6:41:06 | reached: Rock Tunnel 1F |
| 0:09 | 9546 | 6:42:22 | reached: Rock Tunnel B1F |
| 0:10 | 10494 | 7:28:50 | reached: Route 11 |
| 0:12 | 11348 | 7:59:47 | reached: Route 12 |
| 0:17 | 12522 | 8:40:10 | reached: Lavender Town |
| 0:17 | 12710 | 8:44:35 | reached: Route 8 |
| 0:17 | 12811 | 8:50:45 | reached: Pokémon Tower 1F |
| 0:23 | 13899 | 9:36:52 | reached: Route 7 |
| 0:23 | 13905 | 9:37:01 | reached: Celadon City |
| 0:23 | 14027 | 9:44:55 | badge: Rainbow |
| 0:23 | 14179 | 9:50:05 | reached: Rocket Hideout B1F |
| 0:27 | 16013 | 10:52:11 | reached: Route 16 |
| 0:29 | 16926 | 11:26:02 | reached: Route 13 |
| 0:29 | 16986 | 11:32:27 | reached: Route 14 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T21:54:54 | 60 | rotate | 21161 | 6.8M / 0.0M / 1207k |
| 2 | 2026-10-18T22:55:00 | 57 | stuck | 5036 | 2.6M / 0.0M / 584k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 9578 (asked Jev 7780, forced by code 1798, labelled 7780) · models jev-1.13.0 · input tokens 9405062 · Jev $0.3950
- Jev latency mean 90 ms · p50 79 · p95 157 · max 536
- Fallbacks: none (variant without a safety net)
- Iteration 70
- Planner calls 0 ($0.0000, errors 0) · objective changes 78 · objectives Jev marked done 0 · final objective: Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 622 | 96% | 0.70 |
| intro | 51 | 53% | 0.37 |
| overworld | 6935 | 55% | 0.38 |
| prompt | 172 | 51% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1345)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 216 | 0.07 | 0.22 | 48% | `██████████          ` |
| 0.1–0.2 | 1625 | 0.15 | 0.23 | 50% | `██████████          ` |
| 0.2–0.3 | 1577 | 0.24 | 0.32 | 50% | `██████████          ` |
| 0.3–0.4 | 1138 | 0.34 | 0.42 | 48% | `██████████          ` |
| 0.4–0.5 | 730 | 0.44 | 0.52 | 57% | `███████████         ` |
| 0.5–0.6 | 636 | 0.54 | 0.61 | 63% | `█████████████       ` |
| 0.6–0.7 | 524 | 0.64 | 0.70 | 74% | `███████████████     ` |
| 0.7–0.8 | 408 | 0.74 | 0.78 | 78% | `████████████████    ` |
| 0.8–0.9 | 399 | 0.85 | 0.87 | 88% | `██████████████████  ` |
| 0.9–1.0 | 527 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it56_jev-latest_20261017_223324)

- CLI: `jev-agent` jev_agent.py v2 · server commit `4002762` · prompt `49106d19e201a25e`
- Started 2026-10-17T22:33:24 · ended 2026-10-18T00:00:17 · active 1:26 h · wall 1:26 h · paused 0:00 h · exit: **stuck**
- Tool calls 27137 · images 3042 · reloads 14 · black-outs 0 · in-game playtime 14:13:40 · Pokédex 3 owned · maps visited 127
- Tokens uncached in / cache reads / out: 9.7M / 0.0M / 1929k · cost $0.41 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 52 | 176/176 | 131 | 111 | 144 | 130 | Flamethrower, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 129 | 0:02:21 | obtained: Charmander |
| 0:00 | 129 | 0:02:21 | starter: Charmander |
| 0:00 | 185 | 0:05:09 | reached: Route 1 |
| 0:00 | 196 | 0:06:02 | reached: Viridian City |
| 0:00 | 325 | 0:10:37 | reached: Route 2 |
| 0:00 | 382 | 0:14:23 | reached: Route 22 |
| 0:00 | 563 | 0:27:16 | reached: Pewter City |
| 0:01 | 1658 | 1:09:02 | evolved: Charmander → Charmeleon |
| 0:01 | 2417 | 1:40:44 | badge: Boulder |
| 0:01 | 2427 | 1:41:06 | reached: Route 3 |
| 0:01 | 2498 | 1:47:34 | reached: Route 4 |
| 0:01 | 2503 | 1:47:43 | reached: Mt. Moon 1F |
| 0:04 | 4309 | 3:09:40 | reached: Cerulean City |
| 0:06 | 7402 | 5:17:32 | badge: Cascade |
| 0:06 | 7423 | 5:19:44 | reached: Route 24 |
| 0:06 | 8260 | 5:48:06 | reached: Route 25 |
| 0:07 | 8491 | 5:58:24 | reached: Route 5 |
| 0:07 | 8520 | 5:59:15 | reached: Route 9 |
| 0:07 | 8626 | 6:01:47 | reached: Route 6 |
| 0:07 | 8750 | 6:15:29 | reached: Vermilion City |
| 0:07 | 8791 | 6:16:56 | reached: Vermilion Dock |
| 0:07 | 8818 | 6:19:19 | evolved: Charmeleon → Charizard |
| 0:08 | 10306 | 6:48:46 | badge: Thunder |
| 0:08 | 10332 | 6:49:29 | reached: Route 11 |
| 0:09 | 10766 | 7:05:45 | reached: Route 12 |
| 0:10 | 11153 | 7:18:28 | reached: Route 10 |
| 0:10 | 11229 | 7:22:14 | reached: Rock Tunnel 1F |
| 0:10 | 11281 | 7:24:38 | reached: Rock Tunnel B1F |
| 0:10 | 11857 | 7:54:39 | reached: Lavender Town |
| 0:10 | 11903 | 7:55:58 | reached: Pokémon Tower 1F |
| 0:14 | 13525 | 8:52:02 | reached: Route 23 |
| 0:16 | 13986 | 9:12:27 | reached: Route 8 |
| 0:21 | 15246 | 10:14:03 | reached: Route 7 |
| 0:21 | 15252 | 10:14:12 | reached: Celadon City |
| 0:21 | 15451 | 10:26:30 | badge: Rainbow |
| 0:21 | 15521 | 10:29:30 | reached: Route 16 |
| 0:34 | 18297 | 11:56:31 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T22:33:24 | 60 | rotate | 23679 | 8.0M / 0.0M / 1479k |
| 2 | 2026-10-17T23:33:29 | 27 | stuck | 3457 | 1.6M / 0.0M / 450k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 9652 (asked Jev 7877, forced by code 1775, labelled 7877) · models jev-1.13.0 · input tokens 9686174 · Jev $0.4068
- Jev latency mean 89 ms · p50 77 · p95 163 · max 786
- Fallbacks: none (variant without a safety net)
- Iteration 56
- Planner calls 0 ($0.0000, errors 0) · objective changes 67 · objectives Jev marked done 0 · final objective: Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 688 | 93% | 0.69 |
| intro | 52 | 54% | 0.41 |
| overworld | 6963 | 47% | 0.38 |
| prompt | 174 | 53% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1232)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 207 | 0.08 | 0.17 | 41% | `████████            ` |
| 0.1–0.2 | 1687 | 0.15 | 0.22 | 37% | `███████             ` |
| 0.2–0.3 | 1646 | 0.24 | 0.32 | 46% | `█████████           ` |
| 0.3–0.4 | 1099 | 0.34 | 0.42 | 50% | `██████████          ` |
| 0.4–0.5 | 752 | 0.44 | 0.52 | 56% | `███████████         ` |
| 0.5–0.6 | 542 | 0.54 | 0.61 | 58% | `████████████        ` |
| 0.6–0.7 | 472 | 0.65 | 0.71 | 64% | `█████████████       ` |
| 0.7–0.8 | 436 | 0.74 | 0.79 | 70% | `██████████████      ` |
| 0.8–0.9 | 447 | 0.84 | 0.87 | 75% | `███████████████     ` |
| 0.9–1.0 | 589 | 0.96 | 0.97 | 64% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it74_jev-latest_20261019_071941)

- CLI: `jev-agent` jev_agent.py v2 · server commit `2befe07` · prompt `49106d19e201a25e`
- Started 2026-10-19T07:19:41 · ended 2026-10-19T07:56:55 · active 0:37 h · wall 0:37 h · paused 0:00 h · exit: **stuck**
- Tool calls 27164 · images 2092 · reloads 3 · black-outs 0 · in-game playtime 12:54:25 · Pokédex 3 owned · maps visited 123
- Tokens uncached in / cache reads / out: 10.1M / 0.0M / 2097k · cost $0.42 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 51 | 142/162 | 127 | 115 | 145 | 122 | Flamethrower, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:03 | game started |
| 0:00 | 102 | 0:00:30 | reached: Pallet Town |
| 0:00 | 150 | 0:02:58 | obtained: Charmander |
| 0:00 | 150 | 0:02:58 | starter: Charmander |
| 0:00 | 178 | 0:04:52 | reached: Route 1 |
| 0:00 | 189 | 0:05:47 | reached: Viridian City |
| 0:00 | 272 | 0:09:16 | reached: Route 2 |
| 0:00 | 298 | 0:10:17 | reached: Route 22 |
| 0:00 | 636 | 0:29:59 | reached: Pewter City |
| 0:01 | 1633 | 1:13:02 | evolved: Charmander → Charmeleon |
| 0:01 | 2440 | 1:43:46 | badge: Boulder |
| 0:01 | 2450 | 1:44:07 | reached: Route 3 |
| 0:01 | 2514 | 1:50:30 | reached: Route 4 |
| 0:01 | 2519 | 1:50:38 | reached: Mt. Moon 1F |
| 0:02 | 3140 | 2:13:33 | reached: Route 23 |
| 0:05 | 4810 | 3:14:28 | reached: Cerulean City |
| 0:06 | 7702 | 5:02:22 | badge: Cascade |
| 0:06 | 7723 | 5:04:29 | reached: Route 24 |
| 0:08 | 8947 | 5:47:55 | reached: Route 25 |
| 0:08 | 9113 | 5:56:40 | reached: Route 5 |
| 0:08 | 9142 | 5:57:27 | reached: Route 9 |
| 0:08 | 9479 | 6:09:24 | reached: Route 6 |
| 0:08 | 9514 | 6:12:05 | reached: Vermilion City |
| 0:09 | 9547 | 6:13:17 | reached: Vermilion Dock |
| 0:09 | 9568 | 6:15:30 | evolved: Charmeleon → Charizard |
| 0:09 | 9775 | 6:27:05 | badge: Thunder |
| 0:10 | 10150 | 6:47:29 | reached: Route 11 |
| 0:10 | 10354 | 6:54:54 | reached: Route 12 |
| 0:15 | 12539 | 8:01:47 | reached: Route 10 |
| 0:15 | 12544 | 8:02:05 | reached: Rock Tunnel 1F |
| 0:15 | 12614 | 8:05:55 | reached: Rock Tunnel B1F |
| 0:20 | 14713 | 9:25:38 | reached: Lavender Town |
| 0:20 | 14788 | 9:27:30 | reached: Route 8 |
| 0:20 | 14858 | 9:33:18 | reached: Route 7 |
| 0:20 | 14864 | 9:33:27 | reached: Celadon City |
| 0:20 | 15106 | 9:46:34 | badge: Rainbow |
| 0:21 | 15217 | 9:50:32 | reached: Rocket Hideout B1F |
| 0:22 | 16638 | 10:34:32 | reached: Pokémon Tower 1F |
| 0:27 | 17818 | 11:18:08 | reached: Route 16 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 37.2 min, longest 37 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T07:19:41 | 37 | stuck | 27164 | 10.1M / 0.0M / 2097k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8928 (asked Jev 7467, forced by code 1461, labelled 7467) · models jev-1.13.0 · input tokens 10069761 · Jev $0.4229
- Jev latency mean 92 ms · p50 85 · p95 154 · max 348
- Fallbacks: none (variant without a safety net)
- Iteration 74
- Planner calls 0 ($0.0000, errors 0) · objective changes 77 · objectives Jev marked done 0 · final objective: Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 671 | 96% | 0.69 |
| intro | 54 | 44% | 0.40 |
| overworld | 6616 | 59% | 0.43 |
| prompt | 126 | 49% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1466)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 83 | 0.07 | 0.21 | 41% | `████████            ` |
| 0.1–0.2 | 1026 | 0.16 | 0.23 | 52% | `██████████          ` |
| 0.2–0.3 | 1695 | 0.24 | 0.30 | 50% | `██████████          ` |
| 0.3–0.4 | 982 | 0.34 | 0.41 | 57% | `███████████         ` |
| 0.4–0.5 | 705 | 0.44 | 0.50 | 63% | `█████████████       ` |
| 0.5–0.6 | 700 | 0.55 | 0.60 | 63% | `█████████████       ` |
| 0.6–0.7 | 675 | 0.64 | 0.68 | 69% | `██████████████      ` |
| 0.7–0.8 | 566 | 0.74 | 0.78 | 80% | `████████████████    ` |
| 0.8–0.9 | 463 | 0.84 | 0.87 | 89% | `██████████████████  ` |
| 0.9–1.0 | 572 | 0.97 | 0.97 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it67_jev-latest_20261018_162320)

- CLI: `jev-agent` jev_agent.py v2 · server commit `999425f` · prompt `49106d19e201a25e`
- Started 2026-10-18T16:23:20 · ended 2026-10-18T18:09:49 · active 1:46 h · wall 1:46 h · paused 0:00 h · exit: **stuck**
- Tool calls 27671 · images 2650 · reloads 7 · black-outs 0 · in-game playtime 12:07:43 · Pokédex 3 owned · maps visited 120
- Tokens uncached in / cache reads / out: 12.1M / 0.0M / 2478k · cost $0.51 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 48 | 154/154 | 111 | 111 | 127 | 108 | Flamethrower, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 96 | 0:00:18 | reached: Pallet Town |
| 0:00 | 139 | 0:02:32 | obtained: Charmander |
| 0:00 | 139 | 0:02:32 | starter: Charmander |
| 0:00 | 192 | 0:05:25 | reached: Route 1 |
| 0:00 | 209 | 0:06:59 | reached: Viridian City |
| 0:00 | 437 | 0:16:23 | reached: Route 2 |
| 0:00 | 487 | 0:19:52 | reached: Route 22 |
| 0:00 | 696 | 0:32:31 | reached: Pewter City |
| 0:01 | 853 | 0:43:04 | badge: Boulder |
| 0:01 | 862 | 0:43:26 | reached: Route 3 |
| 0:01 | 1042 | 0:50:32 | evolved: Charmander → Charmeleon |
| 0:01 | 1134 | 0:57:17 | reached: Route 4 |
| 0:01 | 1138 | 0:57:25 | reached: Mt. Moon 1F |
| 0:01 | 1581 | 1:21:44 | reached: Route 23 |
| 0:07 | 4490 | 2:03:12 | reached: Cerulean City |
| 0:09 | 8357 | 4:34:10 | badge: Cascade |
| 0:09 | 8377 | 4:36:21 | reached: Route 24 |
| 0:10 | 9018 | 5:00:36 | reached: Route 25 |
| 0:10 | 9414 | 5:15:11 | reached: Route 5 |
| 0:10 | 9443 | 5:15:59 | reached: Route 9 |
| 0:11 | 9521 | 5:17:48 | reached: Route 6 |
| 0:11 | 9557 | 5:21:04 | evolved: Charmeleon → Charizard |
| 0:11 | 9563 | 5:21:08 | reached: Vermilion City |
| 0:11 | 9595 | 5:22:17 | reached: Vermilion Dock |
| 0:12 | 11111 | 5:54:30 | badge: Thunder |
| 0:12 | 11487 | 6:10:41 | reached: Route 10 |
| 0:12 | 11496 | 6:11:04 | reached: Rock Tunnel 1F |
| 0:13 | 11536 | 6:13:03 | reached: Rock Tunnel B1F |
| 0:14 | 12718 | 7:07:45 | reached: Route 11 |
| 0:14 | 12802 | 7:11:57 | reached: Route 12 |
| 0:20 | 15569 | 8:49:49 | reached: Lavender Town |
| 0:20 | 15622 | 8:51:14 | reached: Pokémon Tower 1F |
| 0:20 | 15730 | 8:54:33 | reached: Route 8 |
| 0:26 | 16898 | 9:54:57 | reached: Route 7 |
| 0:26 | 16904 | 9:55:06 | reached: Celadon City |
| 0:26 | 17067 | 10:05:09 | badge: Rainbow |
| 0:26 | 17273 | 10:10:57 | reached: Route 16 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T16:23:20 | 60 | rotate | 22952 | 8.5M / 0.0M / 1663k |
| 2 | 2026-10-18T17:23:24 | 46 | stuck | 4718 | 3.6M / 0.0M / 816k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 10304 (asked Jev 8861, forced by code 1443, labelled 8861) · models jev-1.13.0 · input tokens 12089465 · Jev $0.5078
- Jev latency mean 85 ms · p50 77 · p95 146 · max 398
- Fallbacks: none (variant without a safety net)
- Iteration 67
- Planner calls 0 ($0.0000, errors 0) · objective changes 73 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout Elevator, examine the panel on its wall, choose B4F and walk out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 619 | 96% | 0.69 |
| intro | 53 | 53% | 0.43 |
| overworld | 8118 | 53% | 0.36 |
| prompt | 71 | 55% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1749)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 113 | 0.08 | 0.17 | 48% | `██████████          ` |
| 0.1–0.2 | 2144 | 0.15 | 0.21 | 51% | `██████████          ` |
| 0.2–0.3 | 2284 | 0.24 | 0.30 | 51% | `██████████          ` |
| 0.3–0.4 | 1264 | 0.34 | 0.41 | 49% | `██████████          ` |
| 0.4–0.5 | 730 | 0.44 | 0.51 | 58% | `████████████        ` |
| 0.5–0.6 | 498 | 0.54 | 0.61 | 63% | `█████████████       ` |
| 0.6–0.7 | 444 | 0.65 | 0.70 | 70% | `██████████████      ` |
| 0.7–0.8 | 427 | 0.74 | 0.78 | 70% | `██████████████      ` |
| 0.8–0.9 | 439 | 0.84 | 0.87 | 75% | `███████████████     ` |
| 0.9–1.0 | 518 | 0.96 | 0.97 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it49_jev-latest_20261017_144803)

- CLI: `jev-agent` jev_agent.py v2 · server commit `4eaed88` · prompt `49106d19e201a25e`
- Started 2026-10-17T14:48:03 · ended 2026-10-17T16:01:08 · active 1:12 h · wall 1:13 h · paused 0:00 h · exit: **stuck**
- Tool calls 28012 · images 3016 · reloads 7 · black-outs 0 · in-game playtime 13:28:03 · Pokédex 4 owned · maps visited 125
- Tokens uncached in / cache reads / out: 10.5M / 0.0M / 2036k · cost $0.44 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 51 | 172/172 | 128 | 121 | 139 | 128 | Flamethrower, Cut, Ember, Leer |
| 2 | Magikarp | 6 | 19/19 | 8 | 12 | 15 | 9 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 100 | 0:00:24 | reached: Pallet Town |
| 0:00 | 133 | 0:02:13 | obtained: Charmander |
| 0:00 | 133 | 0:02:13 | starter: Charmander |
| 0:00 | 210 | 0:05:18 | reached: Route 1 |
| 0:00 | 221 | 0:06:14 | reached: Viridian City |
| 0:00 | 449 | 0:15:15 | reached: Route 2 |
| 0:00 | 505 | 0:18:52 | reached: Route 22 |
| 0:00 | 730 | 0:32:34 | reached: Pewter City |
| 0:00 | 1267 | 0:57:02 | evolved: Charmander → Charmeleon |
| 0:01 | 1986 | 1:24:37 | badge: Boulder |
| 0:01 | 2002 | 1:25:27 | reached: Route 3 |
| 0:01 | 2076 | 1:32:24 | reached: Route 4 |
| 0:01 | 2081 | 1:32:33 | reached: Mt. Moon 1F |
| 0:01 | 2137 | 1:35:15 | reached: Route 23 |
| 0:02 | 3090 | 2:14:52 | obtained: Magikarp |
| 0:03 | 3423 | 2:31:35 | reached: Cerulean City |
| 0:06 | 8298 | 5:57:50 | reached: Route 24 |
| 0:06 | 8362 | 6:03:22 | obtained: Charizard |
| 0:06 | 8387 | 6:05:01 | reached: Route 25 |
| 0:07 | 9831 | 7:07:37 | badge: Cascade |
| 0:07 | 10196 | 7:22:36 | reached: Route 5 |
| 0:07 | 10225 | 7:23:23 | reached: Route 9 |
| 0:07 | 10372 | 7:27:39 | reached: Route 6 |
| 0:07 | 10407 | 7:30:22 | reached: Vermilion City |
| 0:07 | 10448 | 7:31:50 | reached: Vermilion Dock |
| 0:09 | 12070 | 8:07:34 | badge: Thunder |
| 0:09 | 12096 | 8:08:16 | reached: Route 11 |
| 0:10 | 12661 | 8:29:23 | reached: Route 12 |
| 0:11 | 13009 | 8:40:37 | reached: Route 10 |
| 0:11 | 13014 | 8:40:55 | reached: Rock Tunnel 1F |
| 0:11 | 13073 | 8:43:43 | reached: Rock Tunnel B1F |
| 0:12 | 14119 | 9:40:12 | reached: Lavender Town |
| 0:12 | 14181 | 9:41:48 | reached: Pokémon Tower 1F |
| 0:12 | 14201 | 9:42:19 | reached: Route 8 |
| 0:16 | 15880 | 11:23:37 | reached: Route 7 |
| 0:16 | 15886 | 11:23:46 | reached: Celadon City |
| 0:16 | 16064 | 11:34:48 | badge: Rainbow |
| 0:16 | 16143 | 11:37:06 | reached: Route 16 |
| 1:07 | 22633 | 12:37:14 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T14:48:03 | 60 | rotate | 21000 | 7.2M / 0.0M / 1320k |
| 2 | 2026-10-17T15:48:12 | 13 | stuck | 7009 | 3.3M / 0.0M / 715k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 10432 (asked Jev 8450, forced by code 1982, labelled 8450) · models jev-1.13.0 · input tokens 10533446 · Jev $0.4424
- Jev latency mean 100 ms · p50 81 · p95 242 · max 2175
- Fallbacks: none (variant without a safety net)
- Iteration 49
- Planner calls 0 ($0.0000, errors 0) · objective changes 76 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1383 | 65% | 0.66 |
| faint_switch | 5 | 0% | 0.19 |
| intro | 53 | 53% | 0.42 |
| overworld | 6923 | 46% | 0.39 |
| prompt | 86 | 56% | 0.64 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1305)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 130 | 0.08 | 0.20 | 43% | `█████████           ` |
| 0.1–0.2 | 1816 | 0.15 | 0.21 | 37% | `███████             ` |
| 0.2–0.3 | 1708 | 0.24 | 0.31 | 42% | `████████            ` |
| 0.3–0.4 | 1116 | 0.34 | 0.41 | 45% | `█████████           ` |
| 0.4–0.5 | 770 | 0.44 | 0.51 | 48% | `██████████          ` |
| 0.5–0.6 | 554 | 0.54 | 0.61 | 58% | `████████████        ` |
| 0.6–0.7 | 464 | 0.65 | 0.71 | 57% | `███████████         ` |
| 0.7–0.8 | 473 | 0.74 | 0.79 | 68% | `██████████████      ` |
| 0.8–0.9 | 576 | 0.85 | 0.88 | 67% | `█████████████       ` |
| 0.9–1.0 | 843 | 0.96 | 0.97 | 67% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it65_jev-latest_20261018_120906)

- CLI: `jev-agent` jev_agent.py v2 · server commit `92a3cc6` · prompt `49106d19e201a25e`
- Started 2026-10-18T12:09:06 · ended 2026-10-18T15:00:59 · active 2:51 h · wall 2:51 h · paused 0:00 h · exit: **stuck**
- Tool calls 28722 · images 2926 · reloads 9 · black-outs 0 · in-game playtime 11:22:41 · Pokédex 3 owned · maps visited 113
- Tokens uncached in / cache reads / out: 13.8M / 0.0M / 2894k · cost $0.58 · chunks 3

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 48 | 163/163 | 121 | 113 | 136 | 109 | Flamethrower, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 98 | 0:00:23 | reached: Pallet Town |
| 0:00 | 138 | 0:02:29 | obtained: Charmander |
| 0:00 | 138 | 0:02:29 | starter: Charmander |
| 0:00 | 192 | 0:05:29 | reached: Route 1 |
| 0:00 | 215 | 0:07:37 | reached: Viridian City |
| 0:00 | 341 | 0:13:35 | reached: Route 2 |
| 0:00 | 392 | 0:17:15 | reached: Route 22 |
| 0:00 | 834 | 0:43:12 | reached: Pewter City |
| 0:01 | 1364 | 1:07:13 | evolved: Charmander → Charmeleon |
| 0:01 | 1403 | 1:12:09 | badge: Boulder |
| 0:01 | 1432 | 1:13:14 | reached: Route 3 |
| 0:01 | 1526 | 1:21:27 | reached: Route 4 |
| 0:01 | 1530 | 1:21:35 | reached: Mt. Moon 1F |
| 0:01 | 1814 | 1:37:36 | reached: Route 23 |
| 0:03 | 3440 | 2:34:38 | reached: Cerulean City |
| 0:05 | 5751 | 4:02:33 | badge: Cascade |
| 0:05 | 5789 | 4:05:43 | reached: Route 24 |
| 0:06 | 6583 | 4:33:33 | reached: Route 25 |
| 0:06 | 6823 | 4:44:50 | reached: Route 5 |
| 0:06 | 6858 | 4:45:42 | reached: Route 9 |
| 0:06 | 6932 | 4:47:28 | reached: Route 6 |
| 0:06 | 6969 | 4:50:22 | reached: Vermilion City |
| 0:06 | 7012 | 4:51:54 | reached: Vermilion Dock |
| 0:07 | 7339 | 5:09:47 | obtained: Charizard |
| 0:08 | 8600 | 5:50:05 | badge: Thunder |
| 0:09 | 9030 | 6:06:34 | reached: Route 10 |
| 0:10 | 9092 | 6:10:22 | reached: Rock Tunnel 1F |
| 0:10 | 9148 | 6:13:09 | reached: Rock Tunnel B1F |
| 0:11 | 9944 | 6:51:00 | reached: Lavender Town |
| 0:11 | 9988 | 6:52:15 | reached: Pokémon Tower 1F |
| 0:11 | 9999 | 6:52:26 | reached: Route 12 |
| 0:13 | 11074 | 7:37:51 | reached: Route 8 |
| 0:16 | 11970 | 8:39:33 | reached: Route 7 |
| 0:16 | 11976 | 8:39:42 | reached: Celadon City |
| 0:16 | 12104 | 8:47:54 | badge: Rainbow |
| 0:16 | 12401 | 8:55:34 | reached: Route 16 |

**CLI chunks:** 3 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T12:09:06 | 60 | rotate | 20629 | 7.7M / 0.0M / 1534k |
| 2 | 2026-10-18T13:09:11 | 60 | rotate | 4445 | 3.1M / 0.0M / 679k |
| 3 | 2026-10-18T14:09:17 | 52 | stuck | 3646 | 3.0M / 0.0M / 680k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11003 (asked Jev 9723, forced by code 1280, labelled 9723) · models jev-1.13.0 · input tokens 13835717 · Jev $0.5811
- Jev latency mean 99 ms · p50 83 · p95 196 · max 2164
- Fallbacks: none (variant without a safety net)
- Iteration 65
- Planner calls 0 ($0.0000, errors 0) · objective changes 63 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout Elevator, examine the panel on its wall, choose B4F and walk out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 571 | 95% | 0.68 |
| intro | 51 | 51% | 0.42 |
| overworld | 9011 | 53% | 0.32 |
| prompt | 90 | 64% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2039)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 157 | 0.08 | 0.15 | 54% | `███████████         ` |
| 0.1–0.2 | 2862 | 0.15 | 0.20 | 54% | `███████████         ` |
| 0.2–0.3 | 2868 | 0.24 | 0.29 | 51% | `██████████          ` |
| 0.3–0.4 | 1274 | 0.34 | 0.39 | 48% | `██████████          ` |
| 0.4–0.5 | 640 | 0.44 | 0.50 | 56% | `███████████         ` |
| 0.5–0.6 | 451 | 0.55 | 0.61 | 62% | `████████████        ` |
| 0.6–0.7 | 345 | 0.64 | 0.69 | 68% | `██████████████      ` |
| 0.7–0.8 | 315 | 0.74 | 0.78 | 82% | `████████████████    ` |
| 0.8–0.9 | 294 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 517 | 0.97 | 0.97 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it47_jev-latest_20261017_111920)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1515b56` · prompt `49106d19e201a25e`
- Started 2026-10-17T11:19:20 · ended 2026-10-17T12:44:56 · active 1:25 h · wall 1:25 h · paused 0:00 h · exit: **stuck**
- Tool calls 30552 · images 2554 · reloads 9 · black-outs 0 · in-game playtime 14:03:15 · Pokédex 4 owned · maps visited 122
- Tokens uncached in / cache reads / out: 12.2M / 0.0M / 2167k · cost $0.51 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 50 | 161/166 | 114 | 110 | 140 | 123 | Flamethrower, Cut, Ember, Leer |
| 2 | AAAAJJJJJJ (Zubat) | 17 | 42/42 | 20 | 22 | 25 | 18 | Leech Life, Supersonic, Bite |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 85 | 0:00:16 | reached: Pallet Town |
| 0:00 | 118 | 0:02:05 | obtained: Charmander |
| 0:00 | 118 | 0:02:05 | starter: Charmander |
| 0:00 | 192 | 0:05:20 | reached: Route 1 |
| 0:00 | 197 | 0:05:37 | reached: Viridian City |
| 0:00 | 409 | 0:13:42 | reached: Route 2 |
| 0:00 | 469 | 0:17:50 | reached: Route 22 |
| 0:00 | 673 | 0:31:56 | reached: Pewter City |
| 0:00 | 1279 | 0:57:25 | evolved: Charmander → Charmeleon |
| 0:00 | 1338 | 1:02:21 | badge: Boulder |
| 0:00 | 1365 | 1:03:18 | reached: Route 3 |
| 0:01 | 1552 | 1:13:02 | reached: Route 4 |
| 0:01 | 1556 | 1:13:10 | reached: Mt. Moon 1F |
| 0:01 | 1624 | 1:16:44 | reached: Route 23 |
| 0:04 | 3939 | 2:56:57 | reached: Cerulean City |
| 0:07 | 8552 | 6:03:06 | badge: Cascade |
| 0:07 | 8573 | 6:05:28 | reached: Route 24 |
| 0:07 | 8602 | 6:08:31 | evolved: Charmeleon → Charizard |
| 0:08 | 9405 | 6:34:38 | reached: Route 25 |
| 0:08 | 9695 | 6:52:58 | reached: Route 5 |
| 0:08 | 9724 | 6:53:46 | reached: Route 9 |
| 0:08 | 9832 | 6:56:29 | reached: Route 6 |
| 0:08 | 9873 | 6:59:26 | reached: Vermilion City |
| 0:08 | 9917 | 7:00:57 | reached: Vermilion Dock |
| 0:08 | 10029 | 7:04:53 | reached: Route 11 |
| 0:09 | 10833 | 7:34:56 | reached: Route 12 |
| 0:11 | 11634 | 8:06:09 | badge: Thunder |
| 0:17 | 13598 | 9:25:29 | reached: Route 10 |
| 0:17 | 13675 | 9:28:35 | reached: Rock Tunnel 1F |
| 0:17 | 13721 | 9:30:47 | reached: Rock Tunnel B1F |
| 0:20 | 14991 | 10:27:53 | reached: Lavender Town |
| 0:20 | 15021 | 10:28:50 | reached: Pokémon Tower 1F |
| 0:21 | 15754 | 10:54:21 | obtained: Zubat |
| 0:45 | 19049 | 11:22:37 | reached: Route 8 |
| 0:45 | 19099 | 11:26:40 | reached: Route 7 |
| 0:45 | 19105 | 11:26:49 | reached: Celadon City |
| 0:45 | 19225 | 11:34:22 | badge: Rainbow |
| 0:45 | 19450 | 11:40:00 | reached: Route 16 |
| 1:06 | 24869 | 13:18:05 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T11:19:21 | 60 | rotate | 23906 | 8.1M / 0.0M / 1368k |
| 2 | 2026-10-17T12:19:24 | 26 | stuck | 6642 | 4.2M / 0.0M / 799k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 12109 (asked Jev 9967, forced by code 2142, labelled 9967) · models jev-1.13.0 · input tokens 12226899 · Jev $0.5135
- Jev latency mean 94 ms · p50 83 · p95 164 · max 2982
- Fallbacks: none (variant without a safety net)
- Iteration 47
- Planner calls 0 ($0.0000, errors 0) · objective changes 74 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1780 | 56% | 0.52 |
| faint_switch | 1 | 0% | 0.51 |
| intro | 50 | 52% | 0.40 |
| overworld | 8022 | 50% | 0.36 |
| prompt | 114 | 55% | 0.60 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1025)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 232 | 0.07 | 0.22 | 49% | `██████████          ` |
| 0.1–0.2 | 2092 | 0.15 | 0.23 | 44% | `█████████           ` |
| 0.2–0.3 | 2353 | 0.24 | 0.33 | 42% | `████████            ` |
| 0.3–0.4 | 1619 | 0.34 | 0.42 | 44% | `█████████           ` |
| 0.4–0.5 | 981 | 0.44 | 0.52 | 49% | `██████████          ` |
| 0.5–0.6 | 653 | 0.54 | 0.62 | 56% | `███████████         ` |
| 0.6–0.7 | 515 | 0.64 | 0.70 | 65% | `█████████████       ` |
| 0.7–0.8 | 455 | 0.74 | 0.78 | 81% | `████████████████    ` |
| 0.8–0.9 | 448 | 0.85 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 619 | 0.97 | 0.97 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it55_jev-latest_20261017_211959)

- CLI: `jev-agent` jev_agent.py v2 · server commit `62bb5ea` · prompt `49106d19e201a25e`
- Started 2026-10-17T21:20:00 · ended 2026-10-17T22:29:01 · active 1:08 h · wall 1:09 h · paused 0:00 h · exit: **stuck**
- Tool calls 31665 · images 2552 · reloads 6 · black-outs 0 · in-game playtime 15:49:02 · Pokédex 3 owned · maps visited 125
- Tokens uncached in / cache reads / out: 12.6M / 0.0M / 2461k · cost $0.53 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 53 | 169/169 | 125 | 127 | 152 | 127 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:16 | reached: Pallet Town |
| 0:00 | 125 | 0:02:18 | obtained: Charmander |
| 0:00 | 125 | 0:02:18 | starter: Charmander |
| 0:00 | 195 | 0:05:48 | reached: Route 1 |
| 0:00 | 206 | 0:06:41 | reached: Viridian City |
| 0:00 | 461 | 0:14:44 | reached: Route 2 |
| 0:00 | 509 | 0:18:01 | reached: Route 22 |
| 0:01 | 1100 | 0:48:42 | reached: Pewter City |
| 0:01 | 1179 | 0:55:45 | badge: Boulder |
| 0:01 | 1189 | 0:56:06 | reached: Route 3 |
| 0:01 | 1203 | 0:57:32 | evolved: Charmander → Charmeleon |
| 0:01 | 1430 | 1:07:34 | reached: Route 4 |
| 0:01 | 1435 | 1:07:42 | reached: Mt. Moon 1F |
| 0:01 | 1872 | 1:31:10 | reached: Route 23 |
| 0:04 | 3942 | 3:09:23 | reached: Cerulean City |
| 0:06 | 7191 | 5:16:19 | badge: Cascade |
| 0:06 | 7211 | 5:18:30 | reached: Route 24 |
| 0:07 | 8003 | 5:47:21 | reached: Route 25 |
| 0:07 | 8247 | 6:05:44 | reached: Route 5 |
| 0:07 | 8277 | 6:06:35 | reached: Route 9 |
| 0:07 | 8381 | 6:09:14 | reached: Route 6 |
| 0:07 | 8417 | 6:12:22 | evolved: Charmeleon → Charizard |
| 0:07 | 8422 | 6:12:27 | reached: Vermilion City |
| 0:07 | 8461 | 6:13:48 | reached: Vermilion Dock |
| 0:07 | 8490 | 6:14:27 | reached: Route 11 |
| 0:08 | 9168 | 6:39:31 | reached: Route 12 |
| 0:09 | 9749 | 7:02:18 | badge: Thunder |
| 0:13 | 11182 | 8:00:06 | reached: Route 10 |
| 0:13 | 11189 | 8:00:24 | reached: Rock Tunnel 1F |
| 0:13 | 11247 | 8:03:25 | reached: Rock Tunnel B1F |
| 0:24 | 15450 | 11:14:20 | reached: Lavender Town |
| 0:24 | 15482 | 11:15:20 | reached: Pokémon Tower 1F |
| 0:24 | 15618 | 11:19:06 | reached: Route 8 |
| 0:26 | 16615 | 12:23:52 | reached: Route 7 |
| 0:26 | 16621 | 12:24:01 | reached: Celadon City |
| 0:26 | 16813 | 12:35:58 | badge: Rainbow |
| 0:27 | 16918 | 12:39:08 | reached: Route 16 |
| 0:50 | 23361 | 13:48:06 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T21:20:00 | 60 | rotate | 25021 | 9.5M / 0.0M / 1862k |
| 2 | 2026-10-17T22:20:05 | 9 | stuck | 6643 | 3.1M / 0.0M / 598k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11128 (asked Jev 9582, forced by code 1546, labelled 9582) · models jev-1.13.0 · input tokens 12645739 · Jev $0.5311
- Jev latency mean 95 ms · p50 77 · p95 206 · max 2262
- Fallbacks: none (variant without a safety net)
- Iteration 55
- Planner calls 0 ($0.0000, errors 0) · objective changes 68 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout Elevator, examine the panel on its wall, choose B4F and walk out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 745 | 90% | 0.67 |
| intro | 52 | 48% | 0.42 |
| overworld | 8714 | 57% | 0.36 |
| prompt | 71 | 55% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1806)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 214 | 0.08 | 0.17 | 53% | `███████████         ` |
| 0.1–0.2 | 2232 | 0.15 | 0.22 | 53% | `███████████         ` |
| 0.2–0.3 | 2186 | 0.24 | 0.31 | 57% | `███████████         ` |
| 0.3–0.4 | 1336 | 0.34 | 0.40 | 53% | `███████████         ` |
| 0.4–0.5 | 877 | 0.44 | 0.51 | 55% | `███████████         ` |
| 0.5–0.6 | 646 | 0.55 | 0.60 | 64% | `█████████████       ` |
| 0.6–0.7 | 633 | 0.65 | 0.70 | 66% | `█████████████       ` |
| 0.7–0.8 | 534 | 0.74 | 0.78 | 78% | `████████████████    ` |
| 0.8–0.9 | 489 | 0.84 | 0.87 | 81% | `████████████████    ` |
| 0.9–1.0 | 435 | 0.96 | 0.96 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it54_jev-latest_20261017_193509)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1592a6c` · prompt `49106d19e201a25e`
- Started 2026-10-17T19:35:09 · ended 2026-10-17T21:18:08 · active 1:42 h · wall 1:42 h · paused 0:00 h · exit: **stuck**
- Tool calls 32849 · images 2649 · reloads 7 · black-outs 0 · in-game playtime 15:31:27 · Pokédex 3 owned · maps visited 127
- Tokens uncached in / cache reads / out: 14.2M / 0.0M / 2916k · cost $0.60 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 52 | 172/180 | 132 | 116 | 141 | 126 | Scratch, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 98 | 0:00:23 | reached: Pallet Town |
| 0:00 | 136 | 0:02:24 | obtained: Charmander |
| 0:00 | 136 | 0:02:24 | starter: Charmander |
| 0:00 | 200 | 0:05:10 | reached: Route 1 |
| 0:00 | 217 | 0:06:39 | reached: Viridian City |
| 0:00 | 383 | 0:12:53 | reached: Route 2 |
| 0:00 | 436 | 0:16:14 | reached: Route 22 |
| 0:00 | 765 | 0:41:31 | reached: Pewter City |
| 0:00 | 860 | 0:50:08 | badge: Boulder |
| 0:00 | 873 | 0:50:48 | reached: Route 3 |
| 0:00 | 902 | 0:54:19 | evolved: Charmander → Charmeleon |
| 0:01 | 1152 | 1:07:48 | reached: Route 4 |
| 0:01 | 1156 | 1:07:56 | reached: Mt. Moon 1F |
| 0:01 | 1533 | 1:24:27 | reached: Route 23 |
| 0:04 | 3319 | 2:19:47 | reached: Cerulean City |
| 0:05 | 5478 | 3:42:44 | badge: Cascade |
| 0:05 | 5515 | 3:45:55 | reached: Route 24 |
| 0:06 | 6398 | 4:15:03 | reached: Route 25 |
| 0:07 | 6631 | 4:26:04 | reached: Route 5 |
| 0:07 | 6660 | 4:26:52 | reached: Route 9 |
| 0:07 | 6760 | 4:29:27 | reached: Route 6 |
| 0:07 | 6795 | 4:32:38 | reached: Vermilion City |
| 0:07 | 6836 | 4:34:01 | reached: Vermilion Dock |
| 0:07 | 6939 | 4:37:14 | reached: Route 11 |
| 0:08 | 7605 | 5:02:56 | reached: Route 12 |
| 0:10 | 8878 | 5:54:12 | evolved: Charmeleon → Charizard |
| 0:13 | 10249 | 6:41:05 | badge: Thunder |
| 0:18 | 11793 | 7:42:15 | reached: Route 10 |
| 0:18 | 11797 | 7:42:33 | reached: Rock Tunnel 1F |
| 0:18 | 11836 | 7:45:24 | reached: Rock Tunnel B1F |
| 0:18 | 12382 | 8:12:24 | reached: Lavender Town |
| 0:18 | 12464 | 8:14:35 | reached: Pokémon Tower 1F |
| 0:22 | 13950 | 9:07:08 | reached: Route 8 |
| 0:26 | 15214 | 10:23:52 | reached: Route 7 |
| 0:26 | 15220 | 10:24:01 | reached: Celadon City |
| 0:26 | 15361 | 10:33:13 | badge: Rainbow |
| 0:27 | 15925 | 10:48:54 | reached: Route 16 |
| 1:35 | 25239 | 14:18:09 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T19:35:09 | 60 | rotate | 21458 | 7.4M / 0.0M / 1384k |
| 2 | 2026-10-17T20:35:14 | 43 | stuck | 11388 | 6.8M / 0.0M / 1533k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 12288 (asked Jev 10814, forced by code 1474, labelled 10814) · models jev-1.13.0 · input tokens 14210921 · Jev $0.5969
- Jev latency mean 100 ms · p50 82 · p95 239 · max 2108
- Fallbacks: none (variant without a safety net)
- Iteration 54
- Planner calls 0 ($0.0000, errors 0) · objective changes 67 · objectives Jev marked done 0 · final objective: Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 648 | 93% | 0.66 |
| intro | 51 | 45% | 0.38 |
| overworld | 9987 | 61% | 0.32 |
| prompt | 128 | 51% | 0.51 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2557)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 236 | 0.08 | 0.17 | 59% | `████████████        ` |
| 0.1–0.2 | 3031 | 0.15 | 0.21 | 59% | `████████████        ` |
| 0.2–0.3 | 2851 | 0.24 | 0.30 | 62% | `████████████        ` |
| 0.3–0.4 | 1527 | 0.34 | 0.41 | 62% | `████████████        ` |
| 0.4–0.5 | 873 | 0.44 | 0.51 | 60% | `████████████        ` |
| 0.5–0.6 | 619 | 0.54 | 0.61 | 66% | `█████████████       ` |
| 0.6–0.7 | 462 | 0.64 | 0.70 | 68% | `██████████████      ` |
| 0.7–0.8 | 403 | 0.74 | 0.79 | 81% | `████████████████    ` |
| 0.8–0.9 | 314 | 0.84 | 0.87 | 86% | `█████████████████   ` |
| 0.9–1.0 | 498 | 0.97 | 0.98 | 65% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it48_jev-latest_20261017_125031)

- CLI: `jev-agent` jev_agent.py v2 · server commit `276c4f9` · prompt `49106d19e201a25e`
- Started 2026-10-17T12:50:31 · ended 2026-10-17T14:43:34 · active 1:52 h · wall 1:53 h · paused 0:00 h · exit: **stuck**
- Tool calls 33501 · images 2868 · reloads 10 · black-outs 0 · in-game playtime 15:13:03 · Pokédex 3 owned · maps visited 125
- Tokens uncached in / cache reads / out: 13.3M / 0.0M / 2431k · cost $0.56 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 51 | 165/170 | 125 | 114 | 139 | 125 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 88 | 0:00:16 | reached: Pallet Town |
| 0:00 | 121 | 0:02:05 | obtained: Charmander |
| 0:00 | 121 | 0:02:05 | starter: Charmander |
| 0:00 | 189 | 0:04:59 | reached: Route 1 |
| 0:00 | 194 | 0:05:17 | reached: Viridian City |
| 0:00 | 446 | 0:15:40 | reached: Route 2 |
| 0:00 | 497 | 0:19:15 | reached: Route 22 |
| 0:00 | 663 | 0:31:58 | reached: Pewter City |
| 0:01 | 1633 | 1:15:53 | evolved: Charmander → Charmeleon |
| 0:01 | 2303 | 1:50:34 | badge: Boulder |
| 0:01 | 2329 | 1:51:28 | reached: Route 3 |
| 0:01 | 2512 | 2:01:04 | reached: Route 4 |
| 0:01 | 2516 | 2:01:13 | reached: Mt. Moon 1F |
| 0:02 | 3286 | 2:41:39 | reached: Route 23 |
| 0:04 | 4633 | 3:37:04 | reached: Cerulean City |
| 0:06 | 7543 | 5:36:55 | badge: Cascade |
| 0:06 | 7564 | 5:39:01 | reached: Route 24 |
| 0:07 | 8411 | 6:07:13 | reached: Route 25 |
| 0:07 | 8648 | 6:18:36 | reached: Route 5 |
| 0:07 | 8677 | 6:19:27 | reached: Route 9 |
| 0:07 | 8776 | 6:21:53 | reached: Route 6 |
| 0:09 | 9539 | 6:47:48 | evolved: Charmeleon → Charizard |
| 0:09 | 9726 | 6:51:42 | reached: Vermilion City |
| 0:09 | 9767 | 6:53:05 | reached: Vermilion Dock |
| 0:09 | 9946 | 7:05:13 | badge: Thunder |
| 0:09 | 9964 | 7:05:48 | reached: Route 11 |
| 0:10 | 10117 | 7:11:22 | reached: Route 12 |
| 0:15 | 11647 | 8:13:16 | reached: Route 10 |
| 0:15 | 11652 | 8:13:34 | reached: Rock Tunnel 1F |
| 0:15 | 11703 | 8:16:07 | reached: Rock Tunnel B1F |
| 0:24 | 15357 | 11:01:52 | reached: Lavender Town |
| 0:24 | 15427 | 11:03:46 | reached: Pokémon Tower 1F |
| 0:24 | 15454 | 11:04:29 | reached: Route 8 |
| 0:32 | 17952 | 12:27:45 | reached: Route 7 |
| 0:32 | 17958 | 12:27:55 | reached: Celadon City |
| 0:33 | 18130 | 12:38:48 | badge: Rainbow |
| 0:33 | 18214 | 12:42:06 | reached: Route 16 |
| 1:42 | 27588 | 14:38:56 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T12:50:31 | 60 | rotate | 22696 | 7.5M / 0.0M / 1295k |
| 2 | 2026-10-17T13:50:39 | 53 | stuck | 10802 | 5.8M / 0.0M / 1136k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 13283 (asked Jev 11032, forced by code 2251, labelled 11032) · models jev-1.13.0 · input tokens 13296695 · Jev $0.5585
- Jev latency mean 96 ms · p50 81 · p95 180 · max 2105
- Fallbacks: none (variant without a safety net)
- Iteration 48
- Planner calls 0 ($0.0000, errors 0) · objective changes 69 · objectives Jev marked done 0 · final objective: Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 2161 | 45% | 0.55 |
| intro | 53 | 51% | 0.43 |
| overworld | 8742 | 54% | 0.35 |
| prompt | 76 | 55% | 0.65 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1412)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 189 | 0.08 | 0.18 | 39% | `████████            ` |
| 0.1–0.2 | 2331 | 0.15 | 0.22 | 47% | `█████████           ` |
| 0.2–0.3 | 2328 | 0.24 | 0.32 | 48% | `██████████          ` |
| 0.3–0.4 | 1834 | 0.34 | 0.43 | 48% | `██████████          ` |
| 0.4–0.5 | 1357 | 0.44 | 0.53 | 47% | `█████████           ` |
| 0.5–0.6 | 784 | 0.54 | 0.61 | 55% | `███████████         ` |
| 0.6–0.7 | 625 | 0.64 | 0.72 | 61% | `████████████        ` |
| 0.7–0.8 | 643 | 0.74 | 0.80 | 59% | `████████████        ` |
| 0.8–0.9 | 412 | 0.84 | 0.87 | 85% | `█████████████████   ` |
| 0.9–1.0 | 529 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it68_jev-latest_20261018_181214)

- CLI: `jev-agent` jev_agent.py v2 · server commit `bfde6b7` · prompt `49106d19e201a25e`
- Started 2026-10-18T18:12:14 · ended 2026-10-18T21:21:31 · active 3:09 h · wall 3:09 h · paused 0:00 h · exit: **stuck**
- Tool calls 40510 · images 4010 · reloads 12 · black-outs 0 · in-game playtime 17:24:04 · Pokédex 3 owned · maps visited 121
- Tokens uncached in / cache reads / out: 17.8M / 0.0M / 3573k · cost $0.75 · chunks 4

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 51 | 171/174 | 124 | 110 | 140 | 127 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:16 | reached: Pallet Town |
| 0:00 | 130 | 0:02:30 | obtained: Charmander |
| 0:00 | 130 | 0:02:30 | starter: Charmander |
| 0:00 | 187 | 0:06:07 | reached: Route 1 |
| 0:00 | 204 | 0:07:33 | reached: Viridian City |
| 0:00 | 329 | 0:12:28 | reached: Route 2 |
| 0:00 | 385 | 0:16:25 | reached: Route 22 |
| 0:00 | 594 | 0:29:49 | reached: Pewter City |
| 0:00 | 770 | 0:41:01 | badge: Boulder |
| 0:00 | 780 | 0:41:23 | reached: Route 3 |
| 0:00 | 801 | 0:43:58 | evolved: Charmander → Charmeleon |
| 0:00 | 969 | 0:51:58 | reached: Route 4 |
| 0:00 | 973 | 0:52:07 | reached: Mt. Moon 1F |
| 0:01 | 1494 | 1:22:30 | reached: Route 23 |
| 0:02 | 2563 | 2:01:39 | reached: Cerulean City |
| 0:04 | 6531 | 4:30:24 | badge: Cascade |
| 0:04 | 6551 | 4:32:33 | reached: Route 24 |
| 0:06 | 7530 | 5:06:00 | reached: Route 25 |
| 0:06 | 7999 | 5:27:17 | reached: Route 5 |
| 0:06 | 8028 | 5:28:09 | reached: Route 9 |
| 0:06 | 8173 | 5:32:01 | reached: Route 6 |
| 0:06 | 8220 | 5:35:14 | reached: Vermilion City |
| 0:06 | 8264 | 5:36:45 | reached: Vermilion Dock |
| 0:06 | 8284 | 5:38:57 | evolved: Charmeleon → Charizard |
| 0:07 | 8528 | 5:51:15 | badge: Thunder |
| 0:07 | 8545 | 5:51:51 | reached: Route 11 |
| 0:07 | 8972 | 6:07:41 | reached: Route 12 |
| 0:12 | 10505 | 7:00:24 | reached: Route 10 |
| 0:12 | 10510 | 7:00:42 | reached: Rock Tunnel 1F |
| 0:12 | 10556 | 7:02:53 | reached: Rock Tunnel B1F |
| 0:20 | 13806 | 9:23:58 | reached: Lavender Town |
| 0:20 | 13860 | 9:25:23 | reached: Pokémon Tower 1F |
| 0:20 | 13883 | 9:25:58 | reached: Route 8 |
| 0:20 | 13952 | 9:31:57 | reached: Route 7 |
| 0:20 | 13958 | 9:32:06 | reached: Celadon City |
| 0:20 | 14125 | 9:42:38 | badge: Rainbow |
| 0:20 | 14337 | 9:48:47 | reached: Route 16 |
| 0:21 | 14971 | 10:08:47 | reached: Rocket Hideout B1F |

**CLI chunks:** 4 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 3 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T18:12:14 | 60 | rotate | 24282 | 9.0M / 0.0M / 1641k |
| 2 | 2026-10-18T19:12:20 | 60 | rotate | 7465 | 3.7M / 0.0M / 766k |
| 3 | 2026-10-18T20:12:26 | 60 | rotate | 7667 | 4.4M / 0.0M / 972k |
| 4 | 2026-10-18T21:12:30 | 9 | stuck | 1091 | 0.8M / 0.0M / 194k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 16063 (asked Jev 14343, forced by code 1720, labelled 14343) · models jev-1.13.0 · input tokens 17846193 · Jev $0.7495
- Jev latency mean 86 ms · p50 76 · p95 149 · max 2189
- Fallbacks: none (variant without a safety net)
- Iteration 68
- Planner calls 0 ($0.0000, errors 0) · objective changes 82 · objectives Jev marked done 0 · final objective: Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 655 | 97% | 0.68 |
| intro | 52 | 48% | 0.40 |
| overworld | 13302 | 54% | 0.31 |
| prompt | 334 | 28% | 0.56 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1808)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 580 | 0.07 | 0.23 | 48% | `██████████          ` |
| 0.1–0.2 | 4435 | 0.15 | 0.22 | 52% | `██████████          ` |
| 0.2–0.3 | 3448 | 0.24 | 0.31 | 52% | `██████████          ` |
| 0.3–0.4 | 1801 | 0.34 | 0.42 | 51% | `██████████          ` |
| 0.4–0.5 | 1144 | 0.44 | 0.51 | 52% | `██████████          ` |
| 0.5–0.6 | 797 | 0.54 | 0.60 | 55% | `███████████         ` |
| 0.6–0.7 | 649 | 0.64 | 0.69 | 69% | `██████████████      ` |
| 0.7–0.8 | 537 | 0.74 | 0.79 | 74% | `███████████████     ` |
| 0.8–0.9 | 471 | 0.84 | 0.87 | 79% | `████████████████    ` |
| 0.9–1.0 | 481 | 0.96 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it57_jev-latest_20261018_000148)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5abbd33` · prompt `49106d19e201a25e`
- Started 2026-10-18T00:01:48 · ended 2026-10-18T01:03:53 · active 1:01 h · wall 1:02 h · paused 0:00 h · exit: **stuck**
- Tool calls 41250 · images 3652 · reloads 7 · black-outs 0 · in-game playtime 15:35:42 · Pokédex 3 owned · maps visited 127
- Tokens uncached in / cache reads / out: 13.5M / 0.0M / 2572k · cost $0.57 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 55 | 158/179 | 132 | 130 | 155 | 138 | Fire Spin, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 95 | 0:00:18 | reached: Pallet Town |
| 0:00 | 128 | 0:02:07 | obtained: Charmander |
| 0:00 | 128 | 0:02:07 | starter: Charmander |
| 0:00 | 196 | 0:05:09 | reached: Route 1 |
| 0:00 | 222 | 0:07:18 | reached: Viridian City |
| 0:00 | 402 | 0:14:03 | reached: Route 2 |
| 0:00 | 460 | 0:17:53 | reached: Route 22 |
| 0:00 | 674 | 0:31:51 | reached: Pewter City |
| 0:00 | 813 | 0:41:08 | badge: Boulder |
| 0:00 | 842 | 0:42:12 | reached: Route 3 |
| 0:00 | 862 | 0:44:35 | evolved: Charmander → Charmeleon |
| 0:00 | 913 | 0:49:01 | reached: Route 4 |
| 0:00 | 917 | 0:49:10 | reached: Mt. Moon 1F |
| 0:01 | 1631 | 1:18:17 | reached: Route 23 |
| 0:03 | 2885 | 2:19:31 | reached: Cerulean City |
| 0:05 | 7371 | 5:14:11 | badge: Cascade |
| 0:05 | 7392 | 5:16:31 | reached: Route 24 |
| 0:06 | 8204 | 5:45:07 | reached: Route 25 |
| 0:06 | 8299 | 5:54:03 | evolved: Charmeleon → Charizard |
| 0:06 | 8502 | 6:00:58 | reached: Route 5 |
| 0:06 | 8531 | 6:01:49 | reached: Route 9 |
| 0:07 | 8661 | 6:05:15 | reached: Route 6 |
| 0:07 | 8696 | 6:07:53 | reached: Vermilion City |
| 0:07 | 8743 | 6:09:31 | reached: Vermilion Dock |
| 0:07 | 8916 | 6:21:28 | badge: Thunder |
| 0:07 | 8942 | 6:22:11 | reached: Route 11 |
| 0:08 | 9446 | 6:40:39 | reached: Route 12 |
| 0:09 | 9821 | 6:52:49 | reached: Route 10 |
| 0:13 | 10778 | 7:27:30 | reached: Rock Tunnel 1F |
| 0:13 | 10838 | 7:31:09 | reached: Rock Tunnel B1F |
| 0:13 | 11359 | 8:02:56 | reached: Lavender Town |
| 0:13 | 11413 | 8:04:30 | reached: Pokémon Tower 1F |
| 0:13 | 11860 | 8:20:35 | reached: Route 8 |
| 0:17 | 12832 | 9:03:49 | reached: Route 7 |
| 0:17 | 12838 | 9:03:58 | reached: Celadon City |
| 0:18 | 13059 | 9:15:27 | reached: Route 16 |
| 0:22 | 16072 | 10:06:36 | badge: Rainbow |
| 0:31 | 17221 | 10:47:46 | reached: Rocket Hideout B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T00:01:48 | 60 | rotate | 38467 | 12.6M / 0.0M / 2380k |
| 2 | 2026-10-18T01:01:52 | 2 | stuck | 2782 | 0.9M / 0.0M / 192k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 13850 (asked Jev 11417, forced by code 2433, labelled 11417) · models jev-1.13.0 · input tokens 13535636 · Jev $0.5685
- Jev latency mean 84 ms · p50 74 · p95 149 · max 759
- Fallbacks: none (variant without a safety net)
- Iteration 57
- Planner calls 0 ($0.0000, errors 0) · objective changes 105 · objectives Jev marked done 0 · final objective: Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1163 | 92% | 0.66 |
| intro | 50 | 50% | 0.39 |
| overworld | 10023 | 59% | 0.42 |
| prompt | 181 | 49% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1819)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 257 | 0.08 | 0.18 | 36% | `███████             ` |
| 0.1–0.2 | 2137 | 0.15 | 0.23 | 48% | `██████████          ` |
| 0.2–0.3 | 2221 | 0.24 | 0.32 | 58% | `████████████        ` |
| 0.3–0.4 | 1453 | 0.34 | 0.41 | 63% | `█████████████       ` |
| 0.4–0.5 | 880 | 0.44 | 0.51 | 69% | `██████████████      ` |
| 0.5–0.6 | 793 | 0.55 | 0.61 | 71% | `██████████████      ` |
| 0.6–0.7 | 961 | 0.65 | 0.69 | 73% | `███████████████     ` |
| 0.7–0.8 | 1074 | 0.75 | 0.78 | 73% | `███████████████     ` |
| 0.8–0.9 | 1011 | 0.84 | 0.86 | 73% | `███████████████     ` |
| 0.9–1.0 | 630 | 0.95 | 0.96 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it53_jev-latest_20261017_185144)

- CLI: `jev-agent` jev_agent.py v2 · server commit `e501aef` · prompt `49106d19e201a25e`
- Started 2026-10-17T18:51:44 · ended 2026-10-17T19:30:59 · active 0:39 h · wall 0:39 h · paused 0:00 h · exit: **stuck**
- Tool calls 21789 · images 2175 · reloads 3 · black-outs 0 · in-game playtime 14:37:54 · Pokédex 4 owned · maps visited 93
- Tokens uncached in / cache reads / out: 6.6M / 0.0M / 1082k · cost $0.28 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 48 | 148/166 | 111 | 112 | 140 | 107 | Slash, Cut, Ember, Leer |
| 2 | Magikarp | 5 | 18/18 | 6 | 11 | 14 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 87 | 0:00:17 | reached: Pallet Town |
| 0:00 | 120 | 0:02:07 | obtained: Charmander |
| 0:00 | 120 | 0:02:07 | starter: Charmander |
| 0:00 | 206 | 0:05:49 | reached: Route 1 |
| 0:00 | 217 | 0:06:43 | reached: Viridian City |
| 0:00 | 393 | 0:13:30 | reached: Route 2 |
| 0:00 | 436 | 0:17:54 | reached: Route 22 |
| 0:00 | 631 | 0:29:31 | reached: Pewter City |
| 0:01 | 1633 | 1:11:35 | evolved: Charmander → Charmeleon |
| 0:01 | 2501 | 1:46:16 | badge: Boulder |
| 0:01 | 2527 | 1:47:10 | reached: Route 3 |
| 0:01 | 2592 | 1:53:27 | reached: Route 4 |
| 0:01 | 2596 | 1:53:36 | reached: Mt. Moon 1F |
| 0:02 | 2921 | 2:09:10 | reached: Route 23 |
| 0:03 | 4018 | 3:07:28 | obtained: Magikarp |
| 0:04 | 4653 | 3:34:58 | reached: Cerulean City |
| 0:07 | 9588 | 6:45:56 | obtained: Charizard |
| 0:07 | 9620 | 6:48:13 | badge: Cascade |
| 0:07 | 9643 | 6:50:26 | reached: Route 24 |
| 0:08 | 10491 | 7:19:51 | reached: Route 25 |
| 0:08 | 10759 | 7:40:17 | reached: Route 5 |
| 0:08 | 10788 | 7:41:05 | reached: Route 9 |
| 0:08 | 10920 | 7:44:45 | reached: Route 6 |
| 0:08 | 10971 | 7:48:25 | reached: Vermilion City |
| 0:08 | 11011 | 7:49:49 | reached: Vermilion Dock |
| 0:08 | 11036 | 7:50:16 | reached: Route 11 |
| 0:09 | 11733 | 8:19:05 | reached: Route 12 |
| 0:12 | 12793 | 8:55:10 | badge: Thunder |
| 0:14 | 13496 | 9:22:28 | reached: Route 10 |
| 0:14 | 13504 | 9:22:52 | reached: Rock Tunnel 1F |
| 0:14 | 13539 | 9:25:01 | reached: Rock Tunnel B1F |
| 0:23 | 17060 | 11:42:59 | reached: Lavender Town |
| 0:23 | 17110 | 11:44:24 | reached: Pokémon Tower 1F |
| 0:23 | 17320 | 11:52:49 | reached: Route 8 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 39.2 min, longest 39 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T18:51:44 | 39 | stuck | 21789 | 6.6M / 0.0M / 1082k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7933 (asked Jev 5869, forced by code 2064, labelled 5869) · models jev-1.13.0 · input tokens 6606795 · Jev $0.2775
- Jev latency mean 95 ms · p50 77 · p95 211 · max 1528
- Fallbacks: none (variant without a safety net)
- Iteration 53
- Planner calls 0 ($0.0000, errors 0) · objective changes 71 · objectives Jev marked done 0 · final objective: Go west from Lavender via Route 8 and the Underground Path to Route 7 and Celadon City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1760 | 57% | 0.62 |
| faint_switch | 4 | 0% | 0.11 |
| intro | 50 | 50% | 0.42 |
| overworld | 3980 | 66% | 0.47 |
| prompt | 75 | 56% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1741)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 59 | 0.08 | 0.20 | 64% | `█████████████       ` |
| 0.1–0.2 | 619 | 0.15 | 0.23 | 60% | `████████████        ` |
| 0.2–0.3 | 909 | 0.24 | 0.33 | 63% | `█████████████       ` |
| 0.3–0.4 | 825 | 0.34 | 0.43 | 56% | `███████████         ` |
| 0.4–0.5 | 675 | 0.45 | 0.53 | 56% | `███████████         ` |
| 0.5–0.6 | 544 | 0.54 | 0.62 | 59% | `████████████        ` |
| 0.6–0.7 | 528 | 0.65 | 0.71 | 63% | `█████████████       ` |
| 0.7–0.8 | 464 | 0.74 | 0.80 | 73% | `███████████████     ` |
| 0.8–0.9 | 548 | 0.85 | 0.88 | 74% | `███████████████     ` |
| 0.9–1.0 | 698 | 0.96 | 0.97 | 68% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it60_jev-latest_20261018_043718)

- CLI: `jev-agent` jev_agent.py v2 · server commit `c0b8255` · prompt `49106d19e201a25e`
- Started 2026-10-18T04:37:18 · ended 2026-10-18T05:10:07 · active 0:32 h · wall 0:32 h · paused 0:00 h · exit: **stuck**
- Tool calls 25114 · images 2043 · reloads 3 · black-outs 0 · in-game playtime 12:13:15 · Pokédex 3 owned · maps visited 119
- Tokens uncached in / cache reads / out: 8.4M / 0.0M / 1719k · cost $0.35 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 49 | 169/169 | 116 | 117 | 139 | 118 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 97 | 0:00:23 | reached: Pallet Town |
| 0:00 | 130 | 0:02:12 | obtained: Charmander |
| 0:00 | 130 | 0:02:12 | starter: Charmander |
| 0:00 | 187 | 0:04:56 | reached: Route 1 |
| 0:00 | 204 | 0:06:30 | reached: Viridian City |
| 0:00 | 400 | 0:14:15 | reached: Route 2 |
| 0:00 | 465 | 0:19:10 | reached: Route 22 |
| 0:00 | 663 | 0:34:23 | reached: Pewter City |
| 0:00 | 1448 | 1:09:01 | evolved: Charmander → Charmeleon |
| 0:00 | 1449 | 1:09:20 | badge: Boulder |
| 0:00 | 1464 | 1:10:11 | reached: Route 3 |
| 0:01 | 1637 | 1:19:41 | reached: Route 4 |
| 0:01 | 1641 | 1:19:49 | reached: Mt. Moon 1F |
| 0:01 | 1981 | 1:37:14 | reached: Route 23 |
| 0:04 | 3610 | 2:42:16 | reached: Cerulean City |
| 0:06 | 8264 | 5:38:17 | badge: Cascade |
| 0:06 | 8307 | 5:41:44 | reached: Route 24 |
| 0:06 | 8342 | 5:44:54 | obtained: Charizard |
| 0:07 | 9087 | 6:09:16 | reached: Route 25 |
| 0:07 | 9430 | 6:24:47 | reached: Route 5 |
| 0:07 | 9460 | 6:25:39 | reached: Route 9 |
| 0:07 | 9559 | 6:28:09 | reached: Route 6 |
| 0:07 | 9606 | 6:31:22 | reached: Vermilion City |
| 0:07 | 9650 | 6:32:53 | reached: Vermilion Dock |
| 0:08 | 10193 | 6:55:48 | badge: Thunder |
| 0:08 | 10211 | 6:56:23 | reached: Route 11 |
| 0:08 | 10414 | 7:02:52 | reached: Route 12 |
| 0:11 | 11815 | 8:04:10 | reached: Route 10 |
| 0:11 | 11828 | 8:04:34 | reached: Rock Tunnel 1F |
| 0:11 | 11886 | 8:07:31 | reached: Rock Tunnel B1F |
| 0:18 | 14774 | 10:01:59 | reached: Lavender Town |
| 0:18 | 14829 | 10:03:25 | reached: Pokémon Tower 1F |
| 0:18 | 14937 | 10:07:47 | reached: Route 8 |
| 0:23 | 16117 | 11:06:08 | reached: Route 7 |
| 0:23 | 16123 | 11:06:17 | reached: Celadon City |
| 0:23 | 16350 | 11:18:05 | reached: Route 16 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 32.8 min, longest 33 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T04:37:18 | 33 | stuck | 25114 | 8.4M / 0.0M / 1719k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7931 (asked Jev 6393, forced by code 1538, labelled 6393) · models jev-1.13.0 · input tokens 8383040 · Jev $0.3521
- Jev latency mean 94 ms · p50 77 · p95 188 · max 681
- Fallbacks: none (variant without a safety net)
- Iteration 60
- Planner calls 0 ($0.0000, errors 0) · objective changes 87 · objectives Jev marked done 0 · final objective: Beat Erika in the Celadon Gym (cut the tree in front of it).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 692 | 96% | 0.70 |
| intro | 50 | 44% | 0.41 |
| overworld | 5561 | 52% | 0.50 |
| prompt | 90 | 54% | 0.48 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1412)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 27 | 0.08 | 0.29 | 70% | `██████████████      ` |
| 0.1–0.2 | 554 | 0.16 | 0.26 | 56% | `███████████         ` |
| 0.2–0.3 | 1125 | 0.25 | 0.34 | 50% | `██████████          ` |
| 0.3–0.4 | 965 | 0.34 | 0.43 | 47% | `█████████           ` |
| 0.4–0.5 | 602 | 0.44 | 0.52 | 50% | `██████████          ` |
| 0.5–0.6 | 521 | 0.55 | 0.61 | 61% | `████████████        ` |
| 0.6–0.7 | 538 | 0.65 | 0.69 | 61% | `████████████        ` |
| 0.7–0.8 | 639 | 0.75 | 0.78 | 63% | `█████████████       ` |
| 0.8–0.9 | 726 | 0.84 | 0.86 | 65% | `█████████████       ` |
| 0.9–1.0 | 696 | 0.96 | 0.96 | 66% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it44_jev-latest_20261017_085126)

- CLI: `jev-agent` jev_agent.py v2 · server commit `8a3b916` · prompt `49106d19e201a25e`
- Started 2026-10-17T08:51:27 · ended 2026-10-17T09:56:16 · active 1:04 h · wall 1:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 33081 · images 2745 · reloads 5 · black-outs 0 · in-game playtime 13:46:13 · Pokédex 3 owned · maps visited 121
- Tokens uncached in / cache reads / out: 11.8M / 0.0M / 2329k · cost $0.50 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 49 | 164/167 | 126 | 103 | 133 | 109 | Flamethrower, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:00 | game started |
| 0:00 | 101 | 0:00:23 | reached: Pallet Town |
| 0:00 | 134 | 0:02:12 | obtained: Charmander |
| 0:00 | 134 | 0:02:12 | starter: Charmander |
| 0:00 | 202 | 0:05:13 | reached: Route 1 |
| 0:00 | 219 | 0:06:49 | reached: Viridian City |
| 0:00 | 442 | 0:15:05 | reached: Route 2 |
| 0:00 | 489 | 0:18:34 | reached: Route 22 |
| 0:00 | 850 | 0:41:04 | reached: Pewter City |
| 0:01 | 1406 | 1:06:45 | evolved: Charmander → Charmeleon |
| 0:01 | 1490 | 1:12:30 | badge: Boulder |
| 0:01 | 1500 | 1:12:51 | reached: Route 3 |
| 0:01 | 1669 | 1:22:56 | reached: Route 4 |
| 0:01 | 1673 | 1:23:05 | reached: Mt. Moon 1F |
| 0:01 | 2052 | 1:42:56 | reached: Route 23 |
| 0:04 | 3900 | 2:50:47 | reached: Cerulean City |
| 0:07 | 8849 | 6:00:25 | badge: Cascade |
| 0:07 | 8886 | 6:03:18 | reached: Route 24 |
| 0:07 | 8921 | 6:06:27 | obtained: Charizard |
| 0:08 | 9698 | 6:32:29 | reached: Route 25 |
| 0:08 | 9990 | 6:45:04 | reached: Route 5 |
| 0:08 | 10019 | 6:45:55 | reached: Route 9 |
| 0:08 | 10141 | 6:48:59 | reached: Route 6 |
| 0:08 | 10176 | 6:51:39 | reached: Vermilion City |
| 0:08 | 10213 | 6:52:57 | reached: Vermilion Dock |
| 0:08 | 10591 | 7:11:19 | badge: Thunder |
| 0:08 | 10609 | 7:11:55 | reached: Route 11 |
| 0:09 | 10852 | 7:19:36 | reached: Route 12 |
| 0:19 | 15321 | 8:39:13 | reached: Route 10 |
| 0:19 | 15325 | 8:39:31 | reached: Rock Tunnel 1F |
| 0:19 | 15396 | 8:43:51 | reached: Rock Tunnel B1F |
| 0:20 | 15913 | 9:13:31 | reached: Lavender Town |
| 0:20 | 15971 | 9:15:13 | reached: Pokémon Tower 1F |
| 0:20 | 16646 | 9:41:43 | reached: Route 8 |
| 0:24 | 17668 | 10:25:42 | reached: Route 7 |
| 0:24 | 17674 | 10:25:51 | reached: Celadon City |
| 0:24 | 17770 | 10:27:49 | reached: Route 16 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T08:51:27 | 60 | rotate | 26882 | 9.1M / 0.0M / 1663k |
| 2 | 2026-10-17T09:51:30 | 5 | stuck | 6197 | 2.7M / 0.0M / 666k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 10769 (asked Jev 8968, forced by code 1801, labelled 8968) · models jev-1.13.0 · input tokens 11846126 · Jev $0.4975
- Jev latency mean 91 ms · p50 80 · p95 161 · max 914
- Fallbacks: none (variant without a safety net)
- Iteration 44
- Planner calls 0 ($0.0000, errors 0) · objective changes 76 · objectives Jev marked done 0 · final objective: Beat Erika in the Celadon Gym (cut the tree in front of it).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1056 | 72% | 0.64 |
| intro | 54 | 48% | 0.43 |
| overworld | 7763 | 51% | 0.43 |
| prompt | 95 | 63% | 0.66 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1601)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 103 | 0.07 | 0.23 | 55% | `███████████         ` |
| 0.1–0.2 | 1266 | 0.16 | 0.24 | 54% | `███████████         ` |
| 0.2–0.3 | 1885 | 0.24 | 0.32 | 47% | `█████████           ` |
| 0.3–0.4 | 1327 | 0.34 | 0.42 | 48% | `██████████          ` |
| 0.4–0.5 | 932 | 0.45 | 0.52 | 50% | `██████████          ` |
| 0.5–0.6 | 691 | 0.54 | 0.60 | 52% | `██████████          ` |
| 0.6–0.7 | 699 | 0.64 | 0.69 | 49% | `██████████          ` |
| 0.7–0.8 | 795 | 0.74 | 0.78 | 56% | `███████████         ` |
| 0.8–0.9 | 637 | 0.84 | 0.86 | 74% | `███████████████     ` |
| 0.9–1.0 | 633 | 0.96 | 0.97 | 69% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it82_jev-latest_20261020_021414)

- CLI: `jev-agent` jev_agent.py v2 · server commit `77626ff` · prompt `49106d19e201a25e`
- Started 2026-10-20T02:14:14 · ended 2026-10-20T02:37:19 · active 0:22 h · wall 0:23 h · paused 0:00 h · exit: **manual**
- Tool calls 17340 · images 1644 · reloads 2 · black-outs 0 · in-game playtime 8:52:52 · Pokédex 3 owned · maps visited 62
- Tokens uncached in / cache reads / out: 5.4M / 0.0M / 1012k · cost $0.23 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 42 | 126/139 | 99 | 88 | 117 | 92 | Scratch, Slash, Ember, Cut |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 86 | 0:00:12 | reached: Pallet Town |
| 0:00 | 133 | 0:02:39 | obtained: Charmander |
| 0:00 | 133 | 0:02:39 | starter: Charmander |
| 0:00 | 162 | 0:05:11 | reached: Route 1 |
| 0:00 | 173 | 0:06:06 | reached: Viridian City |
| 0:00 | 263 | 0:10:25 | reached: Route 2 |
| 0:00 | 289 | 0:11:25 | reached: Route 22 |
| 0:02 | 2248 | 1:00:44 | reached: Pewter City |
| 0:03 | 3526 | 1:48:09 | evolved: Charmander → Charmeleon |
| 0:04 | 5162 | 2:27:15 | badge: Boulder |
| 0:04 | 5171 | 2:27:37 | reached: Route 3 |
| 0:04 | 5241 | 2:34:25 | reached: Route 4 |
| 0:04 | 5245 | 2:34:34 | reached: Mt. Moon 1F |
| 0:06 | 7203 | 3:29:51 | reached: Route 23 |
| 0:07 | 8150 | 4:04:48 | reached: Cerulean City |
| 0:10 | 12273 | 6:32:42 | badge: Cascade |
| 0:10 | 12293 | 6:34:53 | reached: Route 24 |
| 0:10 | 12829 | 6:56:12 | reached: Route 25 |
| 0:10 | 12872 | 6:59:56 | evolved: Charmeleon → Charizard |
| 0:10 | 13142 | 7:09:15 | reached: Route 5 |
| 0:10 | 13172 | 7:10:03 | reached: Route 9 |
| 0:11 | 13281 | 7:12:55 | reached: Route 6 |
| 0:11 | 13317 | 7:15:29 | reached: Vermilion City |
| 0:11 | 13349 | 7:16:40 | reached: Vermilion Dock |
| 0:11 | 13750 | 7:35:47 | badge: Thunder |
| 0:11 | 13946 | 7:45:45 | reached: Route 10 |
| 0:11 | 13950 | 7:46:04 | reached: Rock Tunnel 1F |
| 0:11 | 13991 | 7:47:17 | reached: Rock Tunnel B1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 23.0 min, longest 23 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T02:14:14 | 23 | exited | 17340 | 5.4M / 0.0M / 1012k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6164 (asked Jev 4758, forced by code 1406, labelled 4758) · models jev-1.13.0 · input tokens 5445740 · Jev $0.2287
- Jev latency mean 80 ms · p50 60 · p95 176 · max 734
- Fallbacks: none (variant without a safety net)
- Iteration 82
- Planner calls 0 ($0.0000, errors 0) · objective changes 63 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel (its ladders lead between 1F and B1F several times before the exit south).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 534 | 97% | 0.72 |
| intro | 53 | 53% | 0.41 |
| overworld | 4086 | 59% | 0.47 |
| prompt | 85 | 65% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1849)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 176 | 0.07 | 0.19 | 55% | `███████████         ` |
| 0.1–0.2 | 859 | 0.15 | 0.22 | 54% | `███████████         ` |
| 0.2–0.3 | 676 | 0.24 | 0.33 | 56% | `███████████         ` |
| 0.3–0.4 | 492 | 0.34 | 0.43 | 56% | `███████████         ` |
| 0.4–0.5 | 410 | 0.44 | 0.53 | 59% | `████████████        ` |
| 0.5–0.6 | 335 | 0.54 | 0.62 | 64% | `█████████████       ` |
| 0.6–0.7 | 310 | 0.65 | 0.70 | 73% | `███████████████     ` |
| 0.7–0.8 | 342 | 0.74 | 0.78 | 83% | `█████████████████   ` |
| 0.8–0.9 | 385 | 0.84 | 0.86 | 87% | `█████████████████   ` |
| 0.9–1.0 | 773 | 0.96 | 0.97 | 64% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it78_jev-latest_20261019_221136)

- CLI: `jev-agent` jev_agent.py v2 · server commit `2f0a35f` · prompt `49106d19e201a25e`
- Started 2026-10-19T22:11:36 · ended 2026-10-19T22:58:43 · active 0:47 h · wall 0:47 h · paused 0:00 h · exit: **manual**
- Tool calls 19137 · images 1887 · reloads 2 · black-outs 0 · in-game playtime 10:30:16 · Pokédex 3 owned · maps visited 77
- Tokens uncached in / cache reads / out: 6.3M / 0.0M / 1227k · cost $0.26 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 44 | 138/150 | 102 | 103 | 115 | 104 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 126 | 0:02:19 | obtained: Charmander |
| 0:00 | 126 | 0:02:19 | starter: Charmander |
| 0:00 | 158 | 0:04:22 | reached: Route 1 |
| 0:00 | 175 | 0:05:58 | reached: Viridian City |
| 0:00 | 275 | 0:10:26 | reached: Route 2 |
| 0:00 | 301 | 0:11:26 | reached: Route 22 |
| 0:01 | 1496 | 0:58:12 | reached: Pewter City |
| 0:01 | 1626 | 1:09:15 | badge: Boulder |
| 0:01 | 1652 | 1:10:10 | reached: Route 3 |
| 0:01 | 1671 | 1:12:42 | evolved: Charmander → Charmeleon |
| 0:01 | 1722 | 1:17:08 | reached: Route 4 |
| 0:01 | 1726 | 1:17:17 | reached: Mt. Moon 1F |
| 0:01 | 2244 | 1:44:07 | reached: Route 23 |
| 0:03 | 2955 | 2:11:17 | reached: Cerulean City |
| 0:05 | 6851 | 4:42:00 | badge: Cascade |
| 0:05 | 6872 | 4:44:07 | reached: Route 24 |
| 0:06 | 7924 | 5:20:32 | reached: Route 25 |
| 0:08 | 9857 | 6:18:59 | evolved: Charmeleon → Charizard |
| 0:08 | 9863 | 6:19:19 | reached: Route 5 |
| 0:08 | 9899 | 6:20:14 | reached: Route 9 |
| 0:09 | 10072 | 6:25:34 | reached: Route 6 |
| 0:09 | 10113 | 6:28:26 | reached: Vermilion City |
| 0:09 | 10146 | 6:29:37 | reached: Vermilion Dock |
| 0:09 | 10337 | 6:42:10 | badge: Thunder |
| 0:10 | 10613 | 6:57:08 | reached: Route 11 |
| 0:10 | 10787 | 7:03:39 | reached: Route 12 |
| 0:16 | 12598 | 8:04:26 | reached: Route 10 |
| 0:16 | 12602 | 8:04:45 | reached: Rock Tunnel 1F |
| 0:16 | 12636 | 8:06:33 | reached: Rock Tunnel B1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 47.1 min, longest 47 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T22:11:36 | 47 | exited | 19137 | 6.3M / 0.0M / 1227k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6599 (asked Jev 5315, forced by code 1284, labelled 5315) · models jev-1.13.0 · input tokens 6288677 · Jev $0.2641
- Jev latency mean 89 ms · p50 70 · p95 201 · max 832
- Fallbacks: none (variant without a safety net)
- Iteration 78
- Planner calls 0 ($0.0000, errors 0) · objective changes 62 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 554 | 98% | 0.71 |
| intro | 52 | 50% | 0.43 |
| overworld | 4633 | 64% | 0.41 |
| prompt | 76 | 57% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.204)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 108 | 0.08 | 0.17 | 72% | `██████████████      ` |
| 0.1–0.2 | 887 | 0.15 | 0.23 | 62% | `████████████        ` |
| 0.2–0.3 | 1092 | 0.24 | 0.32 | 55% | `███████████         ` |
| 0.3–0.4 | 748 | 0.34 | 0.41 | 59% | `████████████        ` |
| 0.4–0.5 | 506 | 0.44 | 0.51 | 63% | `█████████████       ` |
| 0.5–0.6 | 424 | 0.54 | 0.60 | 69% | `██████████████      ` |
| 0.6–0.7 | 357 | 0.65 | 0.69 | 79% | `████████████████    ` |
| 0.7–0.8 | 383 | 0.74 | 0.78 | 88% | `██████████████████  ` |
| 0.8–0.9 | 377 | 0.84 | 0.87 | 90% | `██████████████████  ` |
| 0.9–1.0 | 433 | 0.96 | 0.97 | 72% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it79_jev-latest_20261019_231405)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b39ac2c` · prompt `49106d19e201a25e`
- Started 2026-10-19T23:14:05 · ended 2026-10-19T23:44:56 · active 0:30 h · wall 0:30 h · paused 0:00 h · exit: **manual**
- Tool calls 20441 · images 1849 · reloads 0 · black-outs 0 · in-game playtime 12:30:07 · Pokédex 3 owned · maps visited 77
- Tokens uncached in / cache reads / out: 6.5M / 0.0M / 1210k · cost $0.27 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 47 | 147/154 | 109 | 103 | 133 | 104 | Flamethrower, Cut, Ember, Slash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 88 | 0:00:17 | reached: Pallet Town |
| 0:00 | 125 | 0:02:19 | obtained: Charmander |
| 0:00 | 125 | 0:02:19 | starter: Charmander |
| 0:00 | 154 | 0:04:38 | reached: Route 1 |
| 0:00 | 159 | 0:04:56 | reached: Viridian City |
| 0:00 | 250 | 0:09:37 | reached: Route 2 |
| 0:00 | 276 | 0:10:37 | reached: Route 22 |
| 0:00 | 589 | 0:29:28 | reached: Pewter City |
| 0:01 | 2239 | 1:14:46 | evolved: Charmander → Charmeleon |
| 0:02 | 4627 | 2:18:48 | badge: Boulder |
| 0:02 | 4636 | 2:19:10 | reached: Route 3 |
| 0:02 | 4706 | 2:25:16 | reached: Route 4 |
| 0:02 | 4710 | 2:25:25 | reached: Mt. Moon 1F |
| 0:03 | 5065 | 2:42:56 | reached: Route 23 |
| 0:06 | 7159 | 4:03:32 | reached: Cerulean City |
| 0:08 | 10322 | 5:56:00 | badge: Cascade |
| 0:08 | 10342 | 5:58:12 | reached: Route 24 |
| 0:08 | 11039 | 6:23:47 | reached: Route 25 |
| 0:10 | 12331 | 7:13:52 | reached: Route 5 |
| 0:10 | 12360 | 7:14:43 | reached: Route 9 |
| 0:10 | 12444 | 7:17:18 | reached: Route 6 |
| 0:10 | 12541 | 7:22:55 | evolved: Charmeleon → Charizard |
| 0:10 | 12546 | 7:22:59 | reached: Vermilion City |
| 0:10 | 12579 | 7:24:11 | reached: Vermilion Dock |
| 0:10 | 12835 | 7:39:54 | badge: Thunder |
| 0:11 | 12970 | 7:46:23 | reached: Route 10 |
| 0:11 | 12974 | 7:46:41 | reached: Rock Tunnel 1F |
| 0:11 | 12995 | 7:47:59 | reached: Rock Tunnel B1F |
| 0:11 | 13410 | 8:06:46 | reached: Route 11 |
| 0:14 | 15062 | 9:10:24 | reached: Route 12 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 30.8 min, longest 31 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-19T23:14:05 | 31 | exited | 20441 | 6.5M / 0.0M / 1210k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6818 (asked Jev 5365, forced by code 1453, labelled 5365) · models jev-1.13.0 · input tokens 6493705 · Jev $0.2727
- Jev latency mean 85 ms · p50 65 · p95 192 · max 906
- Fallbacks: none (variant without a safety net)
- Iteration 79
- Planner calls 0 ($0.0000, errors 0) · objective changes 66 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel (its ladders lead between 1F and B1F several times before the exit south).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 654 | 97% | 0.65 |
| intro | 51 | 53% | 0.43 |
| overworld | 4591 | 61% | 0.50 |
| prompt | 69 | 49% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1705)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 48 | 0.07 | 0.22 | 60% | `████████████        ` |
| 0.1–0.2 | 555 | 0.15 | 0.25 | 56% | `███████████         ` |
| 0.2–0.3 | 861 | 0.24 | 0.33 | 53% | `███████████         ` |
| 0.3–0.4 | 754 | 0.34 | 0.42 | 55% | `███████████         ` |
| 0.4–0.5 | 565 | 0.44 | 0.51 | 61% | `████████████        ` |
| 0.5–0.6 | 491 | 0.54 | 0.60 | 69% | `██████████████      ` |
| 0.6–0.7 | 472 | 0.65 | 0.70 | 79% | `████████████████    ` |
| 0.7–0.8 | 461 | 0.74 | 0.78 | 88% | `██████████████████  ` |
| 0.8–0.9 | 398 | 0.84 | 0.87 | 87% | `█████████████████   ` |
| 0.9–1.0 | 760 | 0.96 | 0.97 | 64% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it58_jev-latest_20261018_010611)

- CLI: `jev-agent` jev_agent.py v2 · server commit `97a7acf` · prompt `49106d19e201a25e`
- Started 2026-10-18T01:06:11 · ended 2026-10-18T02:37:18 · active 1:31 h · wall 1:31 h · paused 0:00 h · exit: **stuck**
- Tool calls 28016 · images 3231 · reloads 6 · black-outs 0 · in-game playtime 14:01:12 · Pokédex 3 owned · maps visited 78
- Tokens uncached in / cache reads / out: 10.7M / 0.0M / 2265k · cost $0.45 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 48 | 152/160 | 123 | 112 | 135 | 106 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 90 | 0:00:17 | reached: Pallet Town |
| 0:00 | 130 | 0:02:22 | obtained: Charmander |
| 0:00 | 130 | 0:02:22 | starter: Charmander |
| 0:00 | 185 | 0:05:27 | reached: Route 1 |
| 0:00 | 196 | 0:06:20 | reached: Viridian City |
| 0:00 | 354 | 0:12:26 | reached: Route 2 |
| 0:00 | 407 | 0:16:01 | reached: Route 22 |
| 0:00 | 739 | 0:37:47 | reached: Pewter City |
| 0:01 | 1682 | 1:16:57 | evolved: Charmander → Charmeleon |
| 0:01 | 2033 | 1:31:18 | badge: Boulder |
| 0:01 | 2043 | 1:31:39 | reached: Route 3 |
| 0:01 | 2285 | 1:54:00 | reached: Route 4 |
| 0:01 | 2289 | 1:54:08 | reached: Mt. Moon 1F |
| 0:01 | 2629 | 2:10:57 | reached: Route 23 |
| 0:04 | 4316 | 3:13:32 | reached: Cerulean City |
| 0:07 | 8079 | 5:49:52 | badge: Cascade |
| 0:07 | 8102 | 5:52:09 | reached: Route 24 |
| 0:08 | 8917 | 6:20:45 | reached: Route 25 |
| 0:08 | 9269 | 6:34:39 | reached: Route 5 |
| 0:08 | 9298 | 6:35:30 | reached: Route 9 |
| 0:09 | 9439 | 6:39:26 | reached: Route 6 |
| 0:09 | 9554 | 6:45:33 | reached: Vermilion City |
| 0:09 | 9587 | 6:46:44 | reached: Vermilion Dock |
| 0:09 | 9623 | 6:49:10 | evolved: Charmeleon → Charizard |
| 0:09 | 10170 | 7:11:04 | badge: Thunder |
| 0:09 | 10188 | 7:11:39 | reached: Route 11 |
| 0:09 | 10394 | 7:19:40 | reached: Route 12 |
| 0:12 | 11329 | 7:58:22 | reached: Route 10 |
| 0:12 | 11337 | 7:58:46 | reached: Rock Tunnel 1F |
| 0:12 | 11380 | 8:01:08 | reached: Rock Tunnel B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T01:06:11 | 60 | rotate | 21193 | 7.6M / 0.0M / 1571k |
| 2 | 2026-10-18T02:06:15 | 31 | stuck | 6822 | 3.1M / 0.0M / 693k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 10535 (asked Jev 8594, forced by code 1941, labelled 8594) · models jev-1.13.0 · input tokens 10716976 · Jev $0.4501
- Jev latency mean 86 ms · p50 76 · p95 151 · max 604
- Fallbacks: none (variant without a safety net)
- Iteration 58
- Planner calls 0 ($0.0000, errors 0) · objective changes 66 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 840 | 94% | 0.68 |
| intro | 53 | 53% | 0.41 |
| overworld | 7619 | 64% | 0.37 |
| prompt | 82 | 61% | 0.50 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2478)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 147 | 0.08 | 0.16 | 67% | `█████████████       ` |
| 0.1–0.2 | 1861 | 0.15 | 0.21 | 55% | `███████████         ` |
| 0.2–0.3 | 1942 | 0.24 | 0.30 | 58% | `████████████        ` |
| 0.3–0.4 | 1222 | 0.34 | 0.40 | 62% | `████████████        ` |
| 0.4–0.5 | 857 | 0.44 | 0.50 | 69% | `██████████████      ` |
| 0.5–0.6 | 617 | 0.54 | 0.60 | 81% | `████████████████    ` |
| 0.6–0.7 | 535 | 0.65 | 0.69 | 88% | `██████████████████  ` |
| 0.7–0.8 | 518 | 0.74 | 0.78 | 93% | `███████████████████ ` |
| 0.8–0.9 | 449 | 0.84 | 0.86 | 92% | `██████████████████  ` |
| 0.9–1.0 | 446 | 0.96 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it51_jev-latest_20261017_162026)

- CLI: `jev-agent` jev_agent.py v2 · server commit `18cb63e` · prompt `49106d19e201a25e`
- Started 2026-10-17T16:20:26 · ended 2026-10-17T17:53:46 · active 1:33 h · wall 1:33 h · paused 0:00 h · exit: **stuck**
- Tool calls 28166 · images 3214 · reloads 6 · black-outs 0 · in-game playtime 13:15:05 · Pokédex 3 owned · maps visited 78
- Tokens uncached in / cache reads / out: 10.4M / 0.0M / 2082k · cost $0.43 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 48 | 162/162 | 116 | 114 | 140 | 115 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 127 | 0:02:18 | obtained: Charmander |
| 0:00 | 127 | 0:02:18 | starter: Charmander |
| 0:00 | 183 | 0:04:57 | reached: Route 1 |
| 0:00 | 194 | 0:05:49 | reached: Viridian City |
| 0:00 | 329 | 0:11:34 | reached: Route 2 |
| 0:00 | 376 | 0:15:14 | reached: Route 22 |
| 0:00 | 621 | 0:29:18 | reached: Pewter City |
| 0:00 | 763 | 0:38:32 | badge: Boulder |
| 0:00 | 774 | 0:39:03 | reached: Route 3 |
| 0:00 | 800 | 0:42:23 | evolved: Charmander → Charmeleon |
| 0:00 | 998 | 0:51:21 | reached: Route 4 |
| 0:00 | 1003 | 0:51:29 | reached: Mt. Moon 1F |
| 0:01 | 1419 | 1:11:53 | reached: Route 23 |
| 0:04 | 3162 | 2:26:50 | reached: Cerulean City |
| 0:06 | 7664 | 5:30:36 | badge: Cascade |
| 0:06 | 7692 | 5:33:08 | reached: Route 24 |
| 0:06 | 7721 | 5:36:12 | evolved: Charmeleon → Charizard |
| 0:07 | 8487 | 6:02:23 | reached: Route 25 |
| 0:07 | 8812 | 6:18:19 | reached: Route 5 |
| 0:07 | 8841 | 6:19:10 | reached: Route 9 |
| 0:08 | 8938 | 6:21:45 | reached: Route 6 |
| 0:08 | 8985 | 6:24:58 | reached: Vermilion City |
| 0:08 | 9046 | 6:27:06 | reached: Vermilion Dock |
| 0:08 | 9273 | 6:41:02 | badge: Thunder |
| 0:08 | 9291 | 6:41:37 | reached: Route 11 |
| 0:09 | 9773 | 6:59:11 | reached: Route 12 |
| 0:14 | 11274 | 7:58:06 | reached: Route 10 |
| 0:14 | 11279 | 7:58:25 | reached: Rock Tunnel 1F |
| 0:14 | 11380 | 8:05:50 | reached: Rock Tunnel B1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T16:20:26 | 60 | rotate | 21212 | 7.2M / 0.0M / 1384k |
| 2 | 2026-10-17T17:20:33 | 33 | stuck | 6953 | 3.1M / 0.0M / 698k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 10882 (asked Jev 8434, forced by code 2448, labelled 8434) · models jev-1.13.0 · input tokens 10352496 · Jev $0.4348
- Jev latency mean 96 ms · p50 80 · p95 178 · max 20246
- Fallbacks: none (variant without a safety net)
- Iteration 51
- Planner calls 0 ($0.0000, errors 0) · objective changes 74 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 941 | 96% | 0.67 |
| intro | 52 | 52% | 0.41 |
| overworld | 7355 | 66% | 0.39 |
| prompt | 86 | 62% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2406)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 132 | 0.08 | 0.18 | 64% | `█████████████       ` |
| 0.1–0.2 | 1621 | 0.15 | 0.21 | 58% | `████████████        ` |
| 0.2–0.3 | 1792 | 0.24 | 0.30 | 58% | `████████████        ` |
| 0.3–0.4 | 1215 | 0.34 | 0.41 | 64% | `█████████████       ` |
| 0.4–0.5 | 784 | 0.44 | 0.51 | 72% | `██████████████      ` |
| 0.5–0.6 | 672 | 0.54 | 0.60 | 80% | `████████████████    ` |
| 0.6–0.7 | 619 | 0.65 | 0.70 | 86% | `█████████████████   ` |
| 0.7–0.8 | 573 | 0.74 | 0.78 | 91% | `██████████████████  ` |
| 0.8–0.9 | 496 | 0.84 | 0.87 | 91% | `██████████████████  ` |
| 0.9–1.0 | 530 | 0.97 | 0.97 | 75% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it43_jev-latest_20261017_080218)

- CLI: `jev-agent` jev_agent.py v2 · server commit `bb13dd8` · prompt `49106d19e201a25e`
- Started 2026-10-17T08:02:18 · ended 2026-10-17T08:48:58 · active 0:46 h · wall 0:46 h · paused 0:00 h · exit: **stuck**
- Tool calls 16900 · images 2307 · reloads 3 · black-outs 0 · in-game playtime 9:39:48 · Pokédex 3 owned · maps visited 72
- Tokens uncached in / cache reads / out: 5.7M / 0.0M / 1043k · cost $0.24 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 42 | 85/145 | 106 | 89 | 117 | 92 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 88 | 0:00:17 | reached: Pallet Town |
| 0:00 | 121 | 0:02:07 | obtained: Charmander |
| 0:00 | 121 | 0:02:07 | starter: Charmander |
| 0:00 | 190 | 0:05:08 | reached: Route 1 |
| 0:00 | 207 | 0:06:37 | reached: Viridian City |
| 0:00 | 398 | 0:14:01 | reached: Route 2 |
| 0:00 | 453 | 0:17:56 | reached: Route 22 |
| 0:00 | 598 | 0:29:08 | reached: Pewter City |
| 0:01 | 1182 | 0:56:59 | evolved: Charmander → Charmeleon |
| 0:01 | 2231 | 1:42:58 | badge: Boulder |
| 0:01 | 2247 | 1:43:48 | reached: Route 3 |
| 0:01 | 2325 | 1:50:51 | reached: Route 4 |
| 0:01 | 2329 | 1:51:00 | reached: Mt. Moon 1F |
| 0:02 | 2966 | 2:14:08 | reached: Route 23 |
| 0:05 | 4916 | 3:49:13 | reached: Cerulean City |
| 0:07 | 8682 | 6:14:43 | badge: Cascade |
| 0:07 | 8703 | 6:16:53 | reached: Route 24 |
| 0:07 | 8732 | 6:19:57 | evolved: Charmeleon → Charizard |
| 0:08 | 9480 | 6:45:02 | reached: Route 25 |
| 0:09 | 9738 | 7:03:48 | reached: Route 5 |
| 0:09 | 9768 | 7:04:40 | reached: Route 9 |
| 0:09 | 9889 | 7:08:02 | reached: Route 6 |
| 0:09 | 9924 | 7:10:45 | reached: Vermilion City |
| 0:09 | 9966 | 7:12:11 | reached: Vermilion Dock |
| 0:09 | 10188 | 7:25:41 | badge: Thunder |
| 0:09 | 10214 | 7:26:24 | reached: Route 11 |
| 0:10 | 10639 | 7:42:16 | reached: Route 12 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 46.7 min, longest 47 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T08:02:18 | 47 | stuck | 16900 | 5.7M / 0.0M / 1043k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 6711 (asked Jev 5129, forced by code 1582, labelled 5129) · models jev-1.13.0 · input tokens 5667178 · Jev $0.2380
- Jev latency mean 104 ms · p50 82 · p95 310 · max 959
- Fallbacks: none (variant without a safety net)
- Iteration 43
- Planner calls 0 ($0.0000, errors 0) · objective changes 60 · objectives Jev marked done 0 · final objective: Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 682 | 96% | 0.72 |
| intro | 51 | 55% | 0.42 |
| overworld | 4308 | 60% | 0.41 |
| prompt | 88 | 53% | 0.60 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1876)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 155 | 0.08 | 0.16 | 50% | `██████████          ` |
| 0.1–0.2 | 1023 | 0.15 | 0.22 | 54% | `███████████         ` |
| 0.2–0.3 | 903 | 0.24 | 0.32 | 55% | `███████████         ` |
| 0.3–0.4 | 666 | 0.34 | 0.42 | 56% | `███████████         ` |
| 0.4–0.5 | 458 | 0.44 | 0.53 | 61% | `████████████        ` |
| 0.5–0.6 | 372 | 0.55 | 0.62 | 70% | `██████████████      ` |
| 0.6–0.7 | 292 | 0.64 | 0.70 | 82% | `████████████████    ` |
| 0.7–0.8 | 307 | 0.74 | 0.79 | 85% | `█████████████████   ` |
| 0.8–0.9 | 346 | 0.85 | 0.87 | 92% | `██████████████████  ` |
| 0.9–1.0 | 607 | 0.97 | 0.97 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it41_jev-latest_20261017_052551)

- CLI: `jev-agent` jev_agent.py v2 · server commit `c7a0475` · prompt `49106d19e201a25e`
- Started 2026-10-17T05:25:51 · ended 2026-10-17T07:40:12 · active 2:14 h · wall 2:14 h · paused 0:00 h · exit: **stuck**
- Tool calls 32543 · images 3466 · reloads 8 · black-outs 0 · in-game playtime 13:03:06 · Pokédex 4 owned · maps visited 75
- Tokens uncached in / cache reads / out: 12.9M / 0.0M / 2570k · cost $0.54 · chunks 3

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 42 | 131/140 | 106 | 97 | 110 | 101 | Slash, Cut, Ember, Leer |
| 2 | AAJJJJJJJJ (Magikarp) | 5 | 18/18 | 6 | 10 | 13 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:03 | game started |
| 0:00 | 97 | 0:00:21 | reached: Pallet Town |
| 0:00 | 130 | 0:02:10 | obtained: Charmander |
| 0:00 | 130 | 0:02:10 | starter: Charmander |
| 0:00 | 196 | 0:05:16 | reached: Route 1 |
| 0:00 | 213 | 0:06:50 | reached: Viridian City |
| 0:00 | 525 | 0:17:51 | reached: Route 2 |
| 0:00 | 572 | 0:21:03 | reached: Route 22 |
| 0:00 | 956 | 0:42:28 | reached: Pewter City |
| 0:01 | 1468 | 1:05:19 | evolved: Charmander → Charmeleon |
| 0:01 | 1504 | 1:08:43 | badge: Boulder |
| 0:01 | 1517 | 1:09:24 | reached: Route 3 |
| 0:01 | 1602 | 1:16:32 | reached: Route 4 |
| 0:01 | 1606 | 1:16:40 | reached: Mt. Moon 1F |
| 0:01 | 1748 | 1:28:57 | reached: Route 23 |
| 0:03 | 3747 | 3:03:34 | obtained: Magikarp |
| 0:04 | 4258 | 3:22:16 | reached: Cerulean City |
| 0:07 | 8716 | 6:29:44 | badge: Cascade |
| 0:07 | 8741 | 6:32:08 | reached: Route 24 |
| 0:07 | 8770 | 6:35:12 | evolved: Charmeleon → Charizard |
| 0:08 | 9531 | 7:00:54 | reached: Route 25 |
| 0:08 | 9790 | 7:23:09 | reached: Route 5 |
| 0:08 | 9819 | 7:24:01 | reached: Route 9 |
| 0:08 | 9936 | 7:26:57 | reached: Route 6 |
| 0:08 | 9971 | 7:29:34 | reached: Vermilion City |
| 0:08 | 10017 | 7:31:02 | reached: Vermilion Dock |
| 0:08 | 10127 | 7:36:47 | reached: Route 11 |
| 0:09 | 10448 | 7:46:21 | reached: Route 12 |
| 1:21 | 24926 | 11:33:19 | reached: Route 10 |
| 1:21 | 24964 | 11:35:02 | reached: Rock Tunnel 1F |
| 1:21 | 25051 | 11:39:14 | reached: Rock Tunnel B1F |

**CLI chunks:** 3 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 2 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T05:25:51 | 60 | rotate | 20949 | 7.4M / 0.0M / 1401k |
| 2 | 2026-10-17T06:25:55 | 60 | rotate | 9874 | 4.5M / 0.0M / 954k |
| 3 | 2026-10-17T07:26:01 | 14 | stuck | 1716 | 1.0M / 0.0M / 216k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 12821 (asked Jev 10886, forced by code 1935, labelled 10886) · models jev-1.13.0 · input tokens 12894296 · Jev $0.5416
- Jev latency mean 91 ms · p50 78 · p95 167 · max 922
- Fallbacks: none (variant without a safety net)
- Iteration 41
- Planner calls 0 ($0.0000, errors 0) · objective changes 63 · objectives Jev marked done 0 · final objective: Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 751 | 90% | 0.72 |
| faint_switch | 5 | 0% | 0.19 |
| intro | 52 | 54% | 0.40 |
| overworld | 9931 | 60% | 0.32 |
| prompt | 147 | 58% | 0.53 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2403)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 310 | 0.08 | 0.16 | 64% | `█████████████       ` |
| 0.1–0.2 | 3226 | 0.15 | 0.22 | 62% | `████████████        ` |
| 0.2–0.3 | 2726 | 0.24 | 0.30 | 58% | `████████████        ` |
| 0.3–0.4 | 1360 | 0.34 | 0.41 | 58% | `████████████        ` |
| 0.4–0.5 | 741 | 0.44 | 0.51 | 54% | `███████████         ` |
| 0.5–0.6 | 545 | 0.54 | 0.60 | 58% | `████████████        ` |
| 0.6–0.7 | 495 | 0.64 | 0.69 | 70% | `██████████████      ` |
| 0.7–0.8 | 439 | 0.75 | 0.78 | 78% | `████████████████    ` |
| 0.8–0.9 | 468 | 0.84 | 0.87 | 83% | `█████████████████   ` |
| 0.9–1.0 | 576 | 0.96 | 0.97 | 74% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_bills-house_it35_jev-latest_20261017_022636)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b7513c5` · prompt `49106d19e201a25e`
- Started 2026-10-17T02:26:36 · ended 2026-10-17T02:27:08 · active 0:00 h · wall 0:00 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 696 · images 33 · reloads 0 · black-outs 0 · in-game playtime 5:50:08 · Pokédex 3 owned · maps visited 25
- Tokens uncached in / cache reads / out: 0.2M / 0.0M / 42k · cost $0.01 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 36 | 115/121 | 89 | 77 | 94 | 80 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 82 | 5:26:56 | reached: Route 25 |
| 0:00 | 87 | 5:27:16 | reached: Route 24 |
| 0:00 | 92 | 5:27:31 | reached: Cerulean City |
| 0:00 | 118 | 5:28:28 | reached: Route 4 |
| 0:00 | 405 | 5:38:36 | reached: Route 5 |
| 0:00 | 434 | 5:39:28 | reached: Route 9 |
| 0:00 | 572 | 5:42:49 | reached: Route 6 |
| 0:00 | 607 | 5:45:22 | reached: Vermilion City |
| 0:00 | 651 | 5:46:54 | reached: Vermilion Dock |
| 0:00 | 695 | 5:50:08 | evolved: Charmeleon → Charizard |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 0.5 min, longest 1 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T02:26:36 | 1 | segment_goal | 695 | 0.2M / 0.0M / 42k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 205 (asked Jev 183, forced by code 22, labelled 183) · models jev-1.13.0 · input tokens 229719 · Jev $0.0096
- Jev latency mean 89 ms · p50 74 · p95 161 · max 559
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 35
- Planner calls 0 ($0.0000, errors 0) · objective changes 6 · objectives Jev marked done 0 · final objective: Board the S.S. Anne in Vermilion harbor and talk to the captain on the top deck to get HM01 (Cut).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 5 | 100% | 0.64 |
| overworld | 175 | 58% | 0.42 |
| prompt | 3 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1111)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 2 | 0.06 | 0.22 | 0% | `                    ` |
| 0.1–0.2 | 26 | 0.16 | 0.26 | 58% | `████████████        ` |
| 0.2–0.3 | 30 | 0.24 | 0.34 | 40% | `████████            ` |
| 0.3–0.4 | 43 | 0.35 | 0.42 | 49% | `██████████          ` |
| 0.4–0.5 | 21 | 0.43 | 0.51 | 48% | `██████████          ` |
| 0.5–0.6 | 11 | 0.54 | 0.63 | 100% | `████████████████████` |
| 0.6–0.7 | 17 | 0.65 | 0.70 | 76% | `███████████████     ` |
| 0.7–0.8 | 16 | 0.74 | 0.78 | 81% | `████████████████    ` |
| 0.8–0.9 | 8 | 0.83 | 0.86 | 88% | `██████████████████  ` |
| 0.9–1.0 | 9 | 0.95 | 0.95 | 89% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_it42_jev-latest_20261017_074408)

- CLI: `jev-agent` jev_agent.py v2 · server commit `3f402e5` · prompt `49106d19e201a25e`
- Started 2026-10-17T07:44:08 · ended 2026-10-17T07:59:45 · active 0:15 h · wall 0:15 h · paused 0:00 h · exit: **stuck**
- Tool calls 17731 · images 1175 · reloads 3 · black-outs 0 · in-game playtime 7:36:53 · Pokédex 3 owned · maps visited 58
- Tokens uncached in / cache reads / out: 5.9M / 0.0M / 1222k · cost $0.25 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 37 | 118/122 | 83 | 75 | 95 | 85 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 98 | 0:00:19 | reached: Pallet Town |
| 0:00 | 131 | 0:02:08 | obtained: Charmander |
| 0:00 | 131 | 0:02:08 | starter: Charmander |
| 0:00 | 222 | 0:06:17 | reached: Route 1 |
| 0:00 | 245 | 0:08:33 | reached: Viridian City |
| 0:00 | 394 | 0:15:00 | reached: Route 2 |
| 0:00 | 448 | 0:18:43 | reached: Route 22 |
| 0:00 | 780 | 0:38:43 | reached: Pewter City |
| 0:01 | 1271 | 1:01:52 | evolved: Charmander → Charmeleon |
| 0:01 | 1319 | 1:05:29 | badge: Boulder |
| 0:01 | 1328 | 1:05:51 | reached: Route 3 |
| 0:01 | 1596 | 1:17:29 | reached: Route 4 |
| 0:01 | 1601 | 1:17:37 | reached: Mt. Moon 1F |
| 0:01 | 1669 | 1:21:11 | reached: Route 23 |
| 0:05 | 4823 | 3:48:35 | reached: Cerulean City |
| 0:07 | 8127 | 5:59:35 | badge: Cascade |
| 0:07 | 8151 | 6:01:51 | reached: Route 24 |
| 0:08 | 8977 | 6:30:19 | reached: Route 25 |
| 0:08 | 9056 | 6:38:40 | evolved: Charmeleon → Charizard |
| 0:09 | 9292 | 6:47:03 | reached: Route 5 |
| 0:09 | 9359 | 6:49:19 | reached: Route 9 |
| 0:09 | 9429 | 6:50:53 | reached: Route 6 |
| 0:09 | 9464 | 6:53:38 | reached: Vermilion City |
| 0:09 | 9511 | 6:55:17 | reached: Vermilion Dock |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 15.6 min, longest 16 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T07:44:08 | 16 | stuck | 17731 | 5.9M / 0.0M / 1222k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 5468 (asked Jev 4545, forced by code 923, labelled 4545) · models jev-1.13.0 · input tokens 5895795 · Jev $0.2476
- Jev latency mean 103 ms · p50 80 · p95 318 · max 906
- Fallbacks: none (variant without a safety net)
- Iteration 42
- Planner calls 0 ($0.0000, errors 0) · objective changes 54 · objectives Jev marked done 0 · final objective: Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 457 | 92% | 0.74 |
| intro | 53 | 45% | 0.43 |
| overworld | 3973 | 46% | 0.50 |
| prompt | 62 | 50% | 0.65 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2054)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 23 | 0.08 | 0.22 | 44% | `█████████           ` |
| 0.1–0.2 | 516 | 0.16 | 0.25 | 48% | `██████████          ` |
| 0.2–0.3 | 820 | 0.24 | 0.33 | 50% | `██████████          ` |
| 0.3–0.4 | 574 | 0.34 | 0.43 | 50% | `██████████          ` |
| 0.4–0.5 | 402 | 0.44 | 0.52 | 46% | `█████████           ` |
| 0.5–0.6 | 323 | 0.55 | 0.60 | 50% | `██████████          ` |
| 0.6–0.7 | 319 | 0.65 | 0.68 | 49% | `██████████          ` |
| 0.7–0.8 | 429 | 0.75 | 0.77 | 46% | `█████████           ` |
| 0.8–0.9 | 527 | 0.85 | 0.86 | 57% | `███████████         ` |
| 0.9–1.0 | 612 | 0.96 | 0.96 | 59% | `████████████        ` |

### jev-solo: jev-latest (jev-solo_it40_jev-latest_20261017_041843)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a03c941` · prompt `49106d19e201a25e`
- Started 2026-10-17T04:18:43 · ended 2026-10-17T05:22:48 · active 1:03 h · wall 1:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 19552 · images 2104 · reloads 5 · black-outs 0 · in-game playtime 11:33:41 · Pokédex 4 owned · maps visited 76
- Tokens uncached in / cache reads / out: 7.1M / 0.0M / 1372k · cost $0.30 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 41 | 123/131 | 93 | 87 | 112 | 96 | Slash, Growl, Ember, Leer |
| 2 | Magikarp | 5 | 18/18 | 6 | 11 | 14 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:01 | game started |
| 0:00 | 98 | 0:00:19 | reached: Pallet Town |
| 0:00 | 131 | 0:02:08 | obtained: Charmander |
| 0:00 | 131 | 0:02:08 | starter: Charmander |
| 0:00 | 188 | 0:04:47 | reached: Route 1 |
| 0:00 | 216 | 0:06:48 | reached: Viridian City |
| 0:00 | 370 | 0:13:07 | reached: Route 2 |
| 0:00 | 421 | 0:16:18 | reached: Route 22 |
| 0:00 | 1044 | 0:58:08 | reached: Pewter City |
| 0:00 | 1121 | 1:04:57 | badge: Boulder |
| 0:00 | 1131 | 1:05:19 | reached: Route 3 |
| 0:00 | 1150 | 1:08:15 | evolved: Charmander → Charmeleon |
| 0:00 | 1199 | 1:13:06 | reached: Route 4 |
| 0:00 | 1203 | 1:13:15 | reached: Mt. Moon 1F |
| 0:01 | 1870 | 1:50:52 | reached: Route 23 |
| 0:03 | 3078 | 2:39:41 | obtained: Magikarp |
| 0:03 | 3343 | 2:51:27 | reached: Cerulean City |
| 0:06 | 8119 | 6:11:56 | badge: Cascade |
| 0:06 | 8140 | 6:14:19 | reached: Route 24 |
| 0:06 | 8169 | 6:17:25 | evolved: Charmeleon → Charizard |
| 0:07 | 8916 | 6:41:35 | reached: Route 25 |
| 0:07 | 9189 | 7:00:12 | reached: Route 5 |
| 0:07 | 9221 | 7:01:05 | reached: Route 9 |
| 0:08 | 9361 | 7:04:57 | reached: Route 6 |
| 0:08 | 9402 | 7:07:57 | reached: Vermilion City |
| 0:08 | 9451 | 7:09:48 | reached: Vermilion Dock |
| 0:08 | 9725 | 7:23:37 | reached: Route 11 |
| 0:11 | 10797 | 8:31:30 | reached: Route 12 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T04:18:43 | 60 | rotate | 18992 | 6.8M / 0.0M / 1307k |
| 2 | 2026-10-17T05:18:47 | 4 | stuck | 558 | 0.3M / 0.0M / 65k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7403 (asked Jev 6036, forced by code 1367, labelled 6036) · models jev-1.13.0 · input tokens 7134397 · Jev $0.2996
- Jev latency mean 88 ms · p50 80 · p95 147 · max 6603
- Fallbacks: none (variant without a safety net)
- Iteration 40
- Planner calls 0 ($0.0000, errors 0) · objective changes 58 · objectives Jev marked done 0 · final objective: Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 617 | 90% | 0.73 |
| faint_switch | 5 | 0% | 0.15 |
| intro | 53 | 51% | 0.42 |
| overworld | 5265 | 48% | 0.42 |
| prompt | 96 | 60% | 0.59 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1606)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 85 | 0.08 | 0.18 | 61% | `████████████        ` |
| 0.1–0.2 | 1018 | 0.15 | 0.23 | 51% | `██████████          ` |
| 0.2–0.3 | 1012 | 0.24 | 0.31 | 49% | `██████████          ` |
| 0.3–0.4 | 890 | 0.34 | 0.41 | 46% | `█████████           ` |
| 0.4–0.5 | 728 | 0.44 | 0.50 | 44% | `█████████           ` |
| 0.5–0.6 | 557 | 0.54 | 0.59 | 46% | `█████████           ` |
| 0.6–0.7 | 452 | 0.64 | 0.69 | 57% | `███████████         ` |
| 0.7–0.8 | 370 | 0.74 | 0.78 | 68% | `██████████████      ` |
| 0.8–0.9 | 361 | 0.85 | 0.87 | 74% | `███████████████     ` |
| 0.9–1.0 | 563 | 0.96 | 0.97 | 66% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_it39_jev-latest_20261017_040015)

- CLI: `jev-agent` jev_agent.py v2 · server commit `67e0a39` · prompt `49106d19e201a25e`
- Started 2026-10-17T04:00:15 · ended 2026-10-17T04:15:57 · active 0:15 h · wall 0:15 h · paused 0:00 h · exit: **stuck**
- Tool calls 19987 · images 1383 · reloads 3 · black-outs 0 · in-game playtime 8:41:18 · Pokédex 4 owned · maps visited 58
- Tokens uncached in / cache reads / out: 6.4M / 0.0M / 1329k · cost $0.27 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 37 | 113/118 | 81 | 78 | 99 | 90 | Slash, Growl, Ember, Leer |
| 2 | Magikarp | 5 | 18/18 | 7 | 11 | 13 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 72 | 0:00:00 | game started |
| 0:00 | 89 | 0:00:17 | reached: Pallet Town |
| 0:00 | 124 | 0:02:10 | obtained: Charmander |
| 0:00 | 124 | 0:02:10 | starter: Charmander |
| 0:00 | 186 | 0:05:14 | reached: Route 1 |
| 0:00 | 209 | 0:07:24 | reached: Viridian City |
| 0:00 | 380 | 0:14:40 | reached: Route 2 |
| 0:00 | 428 | 0:17:16 | reached: Route 22 |
| 0:00 | 612 | 0:28:20 | reached: Pewter City |
| 0:01 | 1539 | 1:07:09 | evolved: Charmander → Charmeleon |
| 0:01 | 2321 | 1:39:39 | badge: Boulder |
| 0:01 | 2331 | 1:40:01 | reached: Route 3 |
| 0:01 | 2402 | 1:46:23 | reached: Route 4 |
| 0:01 | 2407 | 1:46:32 | reached: Mt. Moon 1F |
| 0:02 | 2680 | 1:58:30 | reached: Route 23 |
| 0:03 | 3535 | 2:44:32 | obtained: Magikarp |
| 0:06 | 5584 | 4:04:49 | reached: Cerulean City |
| 0:07 | 8723 | 6:13:24 | badge: Cascade |
| 0:07 | 8746 | 6:15:49 | reached: Route 24 |
| 0:08 | 9537 | 6:45:15 | reached: Route 25 |
| 0:08 | 9656 | 6:58:05 | evolved: Charmeleon → Charizard |
| 0:11 | 10762 | 7:40:08 | reached: Route 5 |
| 0:11 | 10791 | 7:40:59 | reached: Route 9 |
| 0:11 | 10925 | 7:44:26 | reached: Route 6 |
| 0:11 | 10966 | 7:47:28 | reached: Vermilion City |
| 0:11 | 10999 | 7:48:40 | reached: Vermilion Dock |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 15.7 min, longest 16 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T04:00:15 | 16 | stuck | 19987 | 6.4M / 0.0M / 1329k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 5976 (asked Jev 4925, forced by code 1051, labelled 4925) · models jev-1.13.0 · input tokens 6414751 · Jev $0.2694
- Jev latency mean 87 ms · p50 79 · p95 148 · max 406
- Fallbacks: none (variant without a safety net)
- Iteration 39
- Planner calls 0 ($0.0000, errors 0) · objective changes 58 · objectives Jev marked done 0 · final objective: Board the S.S. Anne in Vermilion harbor and talk to the captain on the top deck to get HM01 (Cut).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 528 | 92% | 0.74 |
| faint_switch | 3 | 0% | 0.20 |
| intro | 52 | 48% | 0.41 |
| overworld | 4259 | 60% | 0.48 |
| prompt | 83 | 52% | 0.63 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.129)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 59 | 0.08 | 0.17 | 66% | `█████████████       ` |
| 0.1–0.2 | 547 | 0.15 | 0.22 | 56% | `███████████         ` |
| 0.2–0.3 | 653 | 0.25 | 0.32 | 56% | `███████████         ` |
| 0.3–0.4 | 707 | 0.35 | 0.41 | 54% | `███████████         ` |
| 0.4–0.5 | 614 | 0.44 | 0.50 | 52% | `██████████          ` |
| 0.5–0.6 | 626 | 0.55 | 0.59 | 59% | `████████████        ` |
| 0.6–0.7 | 478 | 0.64 | 0.68 | 66% | `█████████████       ` |
| 0.7–0.8 | 341 | 0.74 | 0.77 | 77% | `███████████████     ` |
| 0.8–0.9 | 351 | 0.85 | 0.87 | 92% | `██████████████████  ` |
| 0.9–1.0 | 549 | 0.96 | 0.97 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_it45_jev-latest_20261017_095838)

- CLI: `jev-agent` jev_agent.py v2 · server commit `55da43e` · prompt `49106d19e201a25e`
- Started 2026-10-17T09:58:38 · ended 2026-10-17T10:56:55 · active 0:58 h · wall 0:58 h · paused 0:00 h · exit: **stuck**
- Tool calls 21187 · images 2567 · reloads 5 · black-outs 0 · in-game playtime 10:46:24 · Pokédex 4 owned · maps visited 71
- Tokens uncached in / cache reads / out: 7.8M / 0.0M / 1464k · cost $0.33 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 41 | 115/137 | 94 | 84 | 112 | 91 | Slash, Growl, Ember, Leer |
| 2 | Magikarp | 5 | 0/17 | 6 | 10 | 13 | 7 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 0:00:00 | game started |
| 0:00 | 85 | 0:00:12 | reached: Pallet Town |
| 0:00 | 123 | 0:02:13 | obtained: Charmander |
| 0:00 | 123 | 0:02:13 | starter: Charmander |
| 0:00 | 199 | 0:05:50 | reached: Route 1 |
| 0:00 | 219 | 0:07:15 | reached: Viridian City |
| 0:00 | 381 | 0:14:39 | reached: Route 2 |
| 0:00 | 467 | 0:20:52 | reached: Route 22 |
| 0:00 | 856 | 0:46:33 | reached: Pewter City |
| 0:01 | 1343 | 1:08:45 | evolved: Charmander → Charmeleon |
| 0:01 | 2928 | 2:16:55 | badge: Boulder |
| 0:02 | 2938 | 2:17:16 | reached: Route 3 |
| 0:02 | 3001 | 2:23:27 | reached: Route 4 |
| 0:02 | 3005 | 2:23:36 | reached: Mt. Moon 1F |
| 0:02 | 3399 | 2:39:56 | reached: Route 23 |
| 0:05 | 5671 | 4:18:11 | obtained: Magikarp |
| 0:06 | 6019 | 4:32:30 | reached: Cerulean City |
| 0:08 | 9538 | 6:53:46 | badge: Cascade |
| 0:08 | 9562 | 6:56:03 | reached: Route 24 |
| 0:08 | 9591 | 6:59:05 | evolved: Charmeleon → Charizard |
| 0:09 | 10349 | 7:24:03 | reached: Route 25 |
| 0:09 | 10672 | 7:44:54 | reached: Route 5 |
| 0:09 | 10702 | 7:45:45 | reached: Route 9 |
| 0:09 | 10794 | 7:47:46 | reached: Route 6 |
| 0:09 | 10829 | 7:50:25 | reached: Vermilion City |
| 0:09 | 10873 | 7:51:57 | reached: Vermilion Dock |
| 0:11 | 12044 | 7:58:06 | reached: Route 11 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 58.3 min, longest 58 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T09:58:38 | 58 | stuck | 21187 | 7.8M / 0.0M / 1464k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 8499 (asked Jev 6805, forced by code 1694, labelled 6805) · models jev-1.13.0 · input tokens 7791048 · Jev $0.3272
- Jev latency mean 91 ms · p50 81 · p95 165 · max 1000
- Fallbacks: none (variant without a safety net)
- Iteration 45
- Planner calls 0 ($0.0000, errors 0) · objective changes 73 · objectives Jev marked done 0 · final objective: Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 751 | 90% | 0.71 |
| faint_switch | 3 | 0% | 0.20 |
| intro | 50 | 52% | 0.41 |
| overworld | 5867 | 61% | 0.37 |
| prompt | 134 | 60% | 0.59 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2181)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 142 | 0.08 | 0.19 | 62% | `████████████        ` |
| 0.1–0.2 | 1690 | 0.15 | 0.22 | 60% | `████████████        ` |
| 0.2–0.3 | 1527 | 0.24 | 0.31 | 57% | `███████████         ` |
| 0.3–0.4 | 820 | 0.34 | 0.42 | 56% | `███████████         ` |
| 0.4–0.5 | 482 | 0.44 | 0.52 | 59% | `████████████        ` |
| 0.5–0.6 | 339 | 0.54 | 0.62 | 66% | `█████████████       ` |
| 0.6–0.7 | 347 | 0.64 | 0.69 | 79% | `████████████████    ` |
| 0.7–0.8 | 422 | 0.74 | 0.78 | 86% | `█████████████████   ` |
| 0.8–0.9 | 406 | 0.84 | 0.87 | 89% | `██████████████████  ` |
| 0.9–1.0 | 630 | 0.97 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_it46_jev-latest_20261017_105929)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5ef367d` · prompt `49106d19e201a25e`
- Started 2026-10-17T10:59:29 · ended 2026-10-17T11:17:54 · active 0:18 h · wall 0:18 h · paused 0:00 h · exit: **stuck**
- Tool calls 24548 · images 1768 · reloads 6 · black-outs 0 · in-game playtime 8:16:41 · Pokédex 3 owned · maps visited 58
- Tokens uncached in / cache reads / out: 8.5M / 0.0M / 1812k · cost $0.36 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charizard) | 38 | 124/124 | 92 | 83 | 103 | 85 | Slash, Cut, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:16 | reached: Pallet Town |
| 0:00 | 121 | 0:02:08 | obtained: Charmander |
| 0:00 | 121 | 0:02:08 | starter: Charmander |
| 0:00 | 198 | 0:05:19 | reached: Route 1 |
| 0:00 | 215 | 0:06:53 | reached: Viridian City |
| 0:00 | 471 | 0:16:22 | reached: Route 2 |
| 0:00 | 532 | 0:19:56 | reached: Route 22 |
| 0:00 | 769 | 0:36:34 | reached: Pewter City |
| 0:00 | 1244 | 0:58:41 | evolved: Charmander → Charmeleon |
| 0:01 | 2322 | 1:44:23 | badge: Boulder |
| 0:01 | 2331 | 1:44:45 | reached: Route 3 |
| 0:01 | 2404 | 1:51:13 | reached: Route 4 |
| 0:01 | 2408 | 1:51:22 | reached: Mt. Moon 1F |
| 0:02 | 2918 | 2:17:15 | reached: Route 23 |
| 0:03 | 3955 | 2:56:21 | reached: Cerulean City |
| 0:10 | 13904 | 6:05:14 | badge: Cascade |
| 0:10 | 13926 | 6:07:26 | reached: Route 24 |
| 0:10 | 13955 | 6:10:25 | evolved: Charmeleon → Charizard |
| 0:11 | 14812 | 6:37:44 | reached: Route 25 |
| 0:11 | 15100 | 6:57:03 | reached: Route 5 |
| 0:11 | 15129 | 6:57:55 | reached: Route 9 |
| 0:11 | 15255 | 7:01:00 | reached: Route 6 |
| 0:11 | 15290 | 7:03:39 | reached: Vermilion City |
| 0:11 | 15337 | 7:05:10 | reached: Vermilion Dock |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 18.4 min, longest 18 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T10:59:29 | 18 | stuck | 24548 | 8.5M / 0.0M / 1812k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 7266 (asked Jev 6162, forced by code 1104, labelled 6162) · models jev-1.13.0 · input tokens 8476487 · Jev $0.3560
- Jev latency mean 95 ms · p50 84 · p95 165 · max 1837
- Fallbacks: none (variant without a safety net)
- Iteration 46
- Planner calls 0 ($0.0000, errors 0) · objective changes 69 · objectives Jev marked done 0 · final objective: Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 546 | 95% | 0.77 |
| intro | 51 | 51% | 0.41 |
| overworld | 5497 | 49% | 0.49 |
| prompt | 68 | 52% | 0.71 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2008)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 37 | 0.08 | 0.20 | 65% | `█████████████       ` |
| 0.1–0.2 | 802 | 0.15 | 0.24 | 55% | `███████████         ` |
| 0.2–0.3 | 1289 | 0.24 | 0.32 | 50% | `██████████          ` |
| 0.3–0.4 | 710 | 0.34 | 0.41 | 41% | `████████            ` |
| 0.4–0.5 | 404 | 0.44 | 0.51 | 44% | `█████████           ` |
| 0.5–0.6 | 344 | 0.55 | 0.59 | 49% | `██████████          ` |
| 0.6–0.7 | 408 | 0.65 | 0.68 | 52% | `██████████          ` |
| 0.7–0.8 | 555 | 0.75 | 0.77 | 52% | `██████████          ` |
| 0.8–0.9 | 728 | 0.85 | 0.86 | 59% | `████████████        ` |
| 0.9–1.0 | 885 | 0.96 | 0.96 | 65% | `█████████████       ` |

### jev-solo: jev-latest (jev-solo_cerulean_it21_jev-latest_20261016_220011)

- CLI: `jev-agent` jev_agent.py v2 · server commit `26f6373` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:00:11 · ended 2026-10-16T22:02:36 · active 0:02 h · wall 0:02 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 3837 · images 492 · reloads 0 · black-outs 0 · in-game playtime 9:56:19 · Pokédex 7 owned · maps visited 5
- Tokens uncached in / cache reads / out: 1.0M / 0.0M / 168k · cost $0.04 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 33 | 64/92 | 57 | 54 | 78 | 63 | Slash, Growl, Ember, Leer |
| 2 | Butterfree | 17 | 52/52 | 26 | 27 | 31 | 38 | Stun Spore, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |
| 4 | AAAAAAAAAA (Kakuna) | 8 | 25/25 | 10 | 14 | 10 | 9 | Harden |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 20 | 7:02:09 | reached: Cerulean City |
| 0:00 | 346 | 7:22:43 | reached: Route 24 |
| 0:00 | 472 | 7:34:02 | reached: Route 25 |
| 0:01 | 3031 | 9:16:11 | obtained: Kakuna |
| 0:02 | 3804 | 9:54:19 | badge: Cascade |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 2.4 min, longest 2 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:00:11 | 2 | segment_goal | 3837 | 1.0M / 0.0M / 168k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 1275 (asked Jev 859, forced by code 416, labelled 859) · models jev-1.13.0 · input tokens 989358 · Jev $0.0416
- Jev latency mean 98 ms · p50 85 · p95 181 · max 419
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 21
- Planner calls 0 ($0.0000, errors 0) · objective changes 24 · objectives Jev marked done 0 · final objective: Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 208 | 90% | 0.71 |
| faint_switch | 10 | 60% | 0.56 |
| overworld | 615 | 64% | 0.61 |
| prompt | 26 | 62% | 0.56 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1166)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 12 | 0.07 | 0.26 | 100% | `████████████████████` |
| 0.1–0.2 | 57 | 0.15 | 0.31 | 68% | `██████████████      ` |
| 0.2–0.3 | 74 | 0.25 | 0.39 | 64% | `█████████████       ` |
| 0.3–0.4 | 60 | 0.34 | 0.45 | 52% | `██████████          ` |
| 0.4–0.5 | 69 | 0.44 | 0.53 | 55% | `███████████         ` |
| 0.5–0.6 | 77 | 0.54 | 0.60 | 47% | `█████████           ` |
| 0.6–0.7 | 85 | 0.65 | 0.69 | 61% | `████████████        ` |
| 0.7–0.8 | 97 | 0.74 | 0.77 | 80% | `████████████████    ` |
| 0.8–0.9 | 157 | 0.85 | 0.87 | 84% | `█████████████████   ` |
| 0.9–1.0 | 171 | 0.94 | 0.95 | 82% | `████████████████    ` |

### jev-solo: jev-latest (jev-solo_it24_jev-latest_20261016_221020)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5b2aa03` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:10:20 · ended 2026-10-16T22:22:21 · active 0:11 h · wall 0:12 h · paused 0:00 h · exit: **stuck**
- Tool calls 16647 · images 926 · reloads 4 · black-outs 0 · in-game playtime 5:23:51 · Pokédex 2 owned · maps visited 27
- Tokens uncached in / cache reads / out: 5.4M / 0.0M / 1113k · cost $0.23 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 96/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 74 | 0:00:01 | game started |
| 0:00 | 88 | 0:00:13 | reached: Pallet Town |
| 0:00 | 118 | 0:02:02 | obtained: Charmander |
| 0:00 | 118 | 0:02:02 | starter: Charmander |
| 0:00 | 141 | 0:04:03 | reached: Route 1 |
| 0:00 | 159 | 0:05:31 | reached: Viridian City |
| 0:00 | 704 | 0:23:10 | reached: Route 2 |
| 0:00 | 905 | 0:33:18 | reached: Pewter City |
| 0:01 | 1977 | 1:16:21 | evolved: Charmander → Charmeleon |
| 0:01 | 1978 | 1:16:40 | badge: Boulder |
| 0:01 | 1987 | 1:17:02 | reached: Route 3 |
| 0:01 | 2074 | 1:24:52 | reached: Route 4 |
| 0:01 | 2093 | 1:25:25 | reached: Mt. Moon 1F |
| 0:01 | 2236 | 1:34:12 | reached: Cerulean City |
| 0:04 | 7514 | 4:50:06 | badge: Cascade |
| 0:04 | 7533 | 4:52:15 | reached: Route 24 |
| 0:04 | 7589 | 4:57:32 | reached: Route 25 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 12.0 min, longest 12 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:10:20 | 12 | stuck | 16647 | 5.4M / 0.0M / 1113k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 5054 (asked Jev 4250, forced by code 804, labelled 4250) · models jev-1.13.0 · input tokens 5391084 · Jev $0.2264
- Jev latency mean 98 ms · p50 80 · p95 211 · max 855
- Fallbacks: none (variant without a safety net)
- Iteration 24
- Planner calls 0 ($0.0000, errors 0) · objective changes 55 · objectives Jev marked done 0 · final objective: Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 395 | 97% | 0.76 |
| intro | 54 | 41% | 0.44 |
| overworld | 3743 | 42% | 0.56 |
| prompt | 58 | 45% | 0.68 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1825)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 8 | 0.08 | 0.18 | 88% | `██████████████████  ` |
| 0.1–0.2 | 260 | 0.16 | 0.24 | 56% | `███████████         ` |
| 0.2–0.3 | 621 | 0.25 | 0.31 | 30% | `██████              ` |
| 0.3–0.4 | 615 | 0.34 | 0.41 | 35% | `███████             ` |
| 0.4–0.5 | 429 | 0.44 | 0.49 | 35% | `███████             ` |
| 0.5–0.6 | 290 | 0.55 | 0.59 | 36% | `███████             ` |
| 0.6–0.7 | 310 | 0.65 | 0.68 | 40% | `████████            ` |
| 0.7–0.8 | 453 | 0.74 | 0.77 | 42% | `████████            ` |
| 0.8–0.9 | 527 | 0.84 | 0.86 | 70% | `██████████████      ` |
| 0.9–1.0 | 737 | 0.95 | 0.96 | 70% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_bills-house_it31_jev-latest_20261016_231450)

- CLI: `jev-agent` jev_agent.py v2 · server commit `dcd4705` · prompt `49106d19e201a25e`
- Started 2026-10-16T23:14:50 · ended 2026-10-17T02:02:27 · active 0:02 h · wall 2:47 h · paused 0:00 h · exit: **budget_time**
- Tool calls 4362 · images 5 · reloads 0 · black-outs 0 · in-game playtime 5:28:33 · Pokédex 2 owned · maps visited 6
- Tokens uncached in / cache reads / out: 0.0M / 0.0M / 8k · cost $0.00 · chunks 1411

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 84 | 5:26:21 | reached: Route 25 |
| 0:00 | 97 | 5:26:46 | reached: Route 24 |
| 0:00 | 102 | 5:27:01 | reached: Cerulean City |
| 0:00 | 123 | 5:27:41 | reached: Route 4 |

**CLI chunks:** 1411 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1411 exited; median 0.1 min, longest 0 min.

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 39 (asked Jev 37, forced by code 2, labelled 37) · models jev-1.13.0 · input tokens 40797 · Jev $0.0017
- Jev latency mean 118 ms · p50 97 · p95 338 · max 340
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 31
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 35 | 54% | 0.31 |
| prompt | 2 | 100% | 0.96 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2069)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 2 | 0.07 | 0.17 | 50% | `██████████          ` |
| 0.1–0.2 | 9 | 0.16 | 0.25 | 22% | `████                ` |
| 0.2–0.3 | 13 | 0.24 | 0.33 | 62% | `████████████        ` |
| 0.3–0.4 | 5 | 0.35 | 0.44 | 80% | `████████████████    ` |
| 0.4–0.5 | 2 | 0.43 | 0.49 | 50% | `██████████          ` |
| 0.7–0.8 | 1 | 0.73 | 0.78 | 100% | `████████████████████` |
| 0.8–0.9 | 1 | 0.80 | 0.83 | 0% | `                    ` |
| 0.9–1.0 | 4 | 0.95 | 0.96 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_bills-house_it34_jev-latest_20261017_022121)

- CLI: `jev-agent` jev_agent.py v2 · server commit `4092d35` · prompt `49106d19e201a25e`
- Started 2026-10-17T02:21:21 · ended 2026-10-17T02:25:22 · active 0:03 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 4483 · images 38 · reloads 4 · black-outs 0 · in-game playtime 6:09:05 · Pokédex 2 owned · maps visited 17
- Tokens uncached in / cache reads / out: 1.9M / 0.0M / 365k · cost $0.08 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 70 | 5:26:06 | reached: Route 25 |
| 0:00 | 75 | 5:26:25 | reached: Route 24 |
| 0:00 | 80 | 5:26:41 | reached: Cerulean City |
| 0:00 | 106 | 5:27:37 | reached: Route 4 |
| 0:00 | 548 | 5:42:01 | reached: Route 5 |
| 0:00 | 577 | 5:42:53 | reached: Route 9 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.0 min, longest 4 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T02:21:21 | 4 | stuck | 4483 | 1.9M / 0.0M / 365k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2678 (asked Jev 1552, forced by code 1126, labelled 1552) · models jev-1.13.0 · input tokens 1876068 · Jev $0.0788
- Jev latency mean 86 ms · p50 76 · p95 148 · max 566
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 34
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 2 | 100% | 0.59 |
| overworld | 1548 | 40% | 0.29 |
| prompt | 2 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1579)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 12 | 0.09 | 0.16 | 33% | `███████             ` |
| 0.1–0.2 | 459 | 0.16 | 0.22 | 44% | `█████████           ` |
| 0.2–0.3 | 534 | 0.24 | 0.30 | 40% | `████████            ` |
| 0.3–0.4 | 209 | 0.34 | 0.41 | 36% | `███████             ` |
| 0.4–0.5 | 137 | 0.44 | 0.52 | 37% | `███████             ` |
| 0.5–0.6 | 94 | 0.54 | 0.61 | 28% | `██████              ` |
| 0.6–0.7 | 56 | 0.64 | 0.69 | 38% | `████████            ` |
| 0.7–0.8 | 30 | 0.73 | 0.77 | 40% | `████████            ` |
| 0.8–0.9 | 10 | 0.83 | 0.86 | 60% | `████████████        ` |
| 0.9–1.0 | 11 | 0.94 | 0.95 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_bills-house_it32_jev-latest_20261017_020528)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a6f659f` · prompt `49106d19e201a25e`
- Started 2026-10-17T02:05:28 · ended 2026-10-17T02:10:29 · active 0:04 h · wall 0:05 h · paused 0:00 h · exit: **stuck**
- Tool calls 7165 · images 701 · reloads 3 · black-outs 0 · in-game playtime 6:15:05 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 2.8M / 0.0M / 829k · cost $0.12 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 5:26:05 | reached: Route 25 |
| 0:00 | 87 | 5:26:30 | reached: Route 24 |
| 0:00 | 92 | 5:26:46 | reached: Cerulean City |
| 0:00 | 113 | 5:27:25 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 5.0 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T02:05:28 | 5 | stuck | 7165 | 2.8M / 0.0M / 829k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2141 (asked Jev 2126, forced by code 15, labelled 2126) · models jev-1.13.0 · input tokens 2847307 · Jev $0.1196
- Jev latency mean 92 ms · p50 81 · p95 172 · max 755
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 32
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 5 | 100% | 0.68 |
| overworld | 2119 | 33% | 0.27 |
| prompt | 2 | 100% | 0.95 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1573)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 115 | 0.08 | 0.12 | 71% | `██████████████      ` |
| 0.1–0.2 | 686 | 0.15 | 0.19 | 38% | `████████            ` |
| 0.2–0.3 | 688 | 0.24 | 0.28 | 28% | `██████              ` |
| 0.3–0.4 | 318 | 0.34 | 0.38 | 31% | `██████              ` |
| 0.4–0.5 | 118 | 0.44 | 0.48 | 25% | `█████               ` |
| 0.5–0.6 | 74 | 0.54 | 0.58 | 32% | `██████              ` |
| 0.6–0.7 | 34 | 0.64 | 0.68 | 21% | `████                ` |
| 0.7–0.8 | 46 | 0.75 | 0.78 | 24% | `█████               ` |
| 0.8–0.9 | 41 | 0.84 | 0.86 | 20% | `████                ` |
| 0.9–1.0 | 6 | 0.92 | 0.93 | 33% | `███████             ` |

### jev-solo: jev-latest (jev-solo_bills-house_it33_jev-latest_20261017_021330)

- CLI: `jev-agent` jev_agent.py v2 · server commit `bf6e7fe` · prompt `49106d19e201a25e`
- Started 2026-10-17T02:13:30 · ended 2026-10-17T02:19:06 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **stuck**
- Tool calls 7656 · images 703 · reloads 3 · black-outs 0 · in-game playtime 6:20:01 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 3.0M / 0.0M / 878k · cost $0.13 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 62 | 5:25:56 | reached: Route 25 |
| 0:00 | 67 | 5:26:16 | reached: Route 24 |
| 0:00 | 72 | 5:26:31 | reached: Cerulean City |
| 0:00 | 102 | 5:27:36 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 5.6 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T02:13:30 | 6 | stuck | 7656 | 3.0M / 0.0M / 878k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2216 (asked Jev 2211, forced by code 5, labelled 2211) · models jev-1.13.0 · input tokens 2988566 · Jev $0.1255
- Jev latency mean 98 ms · p50 82 · p95 190 · max 1800
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 33
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 2209 | 27% | 0.29 |
| prompt | 2 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.183)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 86 | 0.08 | 0.12 | 71% | `██████████████      ` |
| 0.1–0.2 | 642 | 0.15 | 0.19 | 34% | `███████             ` |
| 0.2–0.3 | 708 | 0.24 | 0.28 | 22% | `████                ` |
| 0.3–0.4 | 369 | 0.34 | 0.38 | 22% | `████                ` |
| 0.4–0.5 | 165 | 0.44 | 0.47 | 27% | `█████               ` |
| 0.5–0.6 | 82 | 0.54 | 0.58 | 28% | `██████              ` |
| 0.6–0.7 | 48 | 0.64 | 0.68 | 21% | `████                ` |
| 0.7–0.8 | 64 | 0.75 | 0.78 | 11% | `██                  ` |
| 0.8–0.9 | 42 | 0.84 | 0.86 | 5% | `█                   ` |
| 0.9–1.0 | 5 | 0.93 | 0.94 | 60% | `████████████        ` |

### jev-solo: jev-latest (jev-solo_bills-house_it28_jev-latest_20261016_224919)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1631427` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:49:19 · ended 2026-10-16T22:54:29 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **stuck**
- Tool calls 7995 · images 462 · reloads 3 · black-outs 0 · in-game playtime 6:21:38 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 3.3M / 0.0M / 977k · cost $0.14 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 75 | 5:26:49 | reached: Route 25 |
| 0:00 | 88 | 5:27:14 | reached: Route 24 |
| 0:00 | 93 | 5:27:30 | reached: Cerulean City |
| 0:00 | 114 | 5:28:10 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 5.2 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:49:19 | 5 | stuck | 7995 | 3.3M / 0.0M / 977k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2256 (asked Jev 2251, forced by code 5, labelled 2251) · models jev-1.13.0 · input tokens 3320254 · Jev $0.1395
- Jev latency mean 94 ms · p50 80 · p95 171 · max 656
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 28
- Planner calls 0 ($0.0000, errors 0) · objective changes 966 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 2249 | 53% | 0.33 |
| prompt | 2 | 100% | 0.95 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1965)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 94 | 0.08 | 0.12 | 78% | `████████████████    ` |
| 0.1–0.2 | 573 | 0.15 | 0.18 | 51% | `██████████          ` |
| 0.2–0.3 | 541 | 0.24 | 0.28 | 44% | `█████████           ` |
| 0.3–0.4 | 356 | 0.34 | 0.37 | 48% | `██████████          ` |
| 0.4–0.5 | 262 | 0.45 | 0.48 | 61% | `████████████        ` |
| 0.5–0.6 | 185 | 0.54 | 0.57 | 51% | `██████████          ` |
| 0.6–0.7 | 101 | 0.64 | 0.67 | 63% | `█████████████       ` |
| 0.7–0.8 | 69 | 0.74 | 0.77 | 78% | `████████████████    ` |
| 0.8–0.9 | 51 | 0.84 | 0.85 | 61% | `████████████        ` |
| 0.9–1.0 | 19 | 0.95 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_bills-house_it30_jev-latest_20261016_230650)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a16ac23` · prompt `49106d19e201a25e`
- Started 2026-10-16T23:06:50 · ended 2026-10-16T23:13:15 · active 0:06 h · wall 0:06 h · paused 0:00 h · exit: **stuck**
- Tool calls 8876 · images 875 · reloads 3 · black-outs 0 · in-game playtime 7:04:19 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 3.4M / 0.0M / 950k · cost $0.14 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 5:26:43 | reached: Route 25 |
| 0:00 | 78 | 5:27:02 | reached: Route 24 |
| 0:00 | 83 | 5:27:18 | reached: Cerulean City |
| 0:00 | 113 | 5:28:21 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 6.4 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T23:06:50 | 6 | stuck | 8876 | 3.4M / 0.0M / 950k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2681 (asked Jev 2676, forced by code 5, labelled 2676) · models jev-1.13.0 · input tokens 3431849 · Jev $0.1441
- Jev latency mean 100 ms · p50 82 · p95 236 · max 1053
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 30
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 2674 | 36% | 0.26 |
| prompt | 2 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.112)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 98 | 0.08 | 0.12 | 71% | `██████████████      ` |
| 0.1–0.2 | 841 | 0.15 | 0.19 | 38% | `████████            ` |
| 0.2–0.3 | 885 | 0.24 | 0.29 | 29% | `██████              ` |
| 0.3–0.4 | 491 | 0.34 | 0.38 | 29% | `██████              ` |
| 0.4–0.5 | 203 | 0.44 | 0.48 | 34% | `███████             ` |
| 0.5–0.6 | 88 | 0.54 | 0.58 | 57% | `███████████         ` |
| 0.6–0.7 | 41 | 0.64 | 0.67 | 56% | `███████████         ` |
| 0.7–0.8 | 23 | 0.73 | 0.76 | 56% | `███████████         ` |
| 0.8–0.9 | 2 | 0.82 | 0.84 | 50% | `██████████          ` |
| 0.9–1.0 | 4 | 0.97 | 0.97 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_bills-house_it25_jev-latest_20261016_222455)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b1d5750` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:24:55 · ended 2026-10-16T22:31:55 · active 0:06 h · wall 0:07 h · paused 0:00 h · exit: **stuck**
- Tool calls 9489 · images 531 · reloads 3 · black-outs 0 · in-game playtime 6:58:34 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 4.1M / 0.0M / 1190k · cost $0.17 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 36 | 5:24:51 | reached: Route 25 |
| 0:00 | 94 | 5:26:59 | reached: Route 24 |
| 0:00 | 99 | 5:27:15 | reached: Cerulean City |
| 0:00 | 129 | 5:28:18 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 7.0 min, longest 7 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:24:55 | 7 | stuck | 9489 | 4.1M / 0.0M / 1190k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2713 (asked Jev 2707, forced by code 6, labelled 2707) · models jev-1.13.0 · input tokens 4095116 · Jev $0.1720
- Jev latency mean 92 ms · p50 80 · p95 161 · max 595
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 25
- Planner calls 0 ($0.0000, errors 0) · objective changes 1178 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 2704 | 50% | 0.32 |
| prompt | 3 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1896)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 109 | 0.08 | 0.12 | 68% | `██████████████      ` |
| 0.1–0.2 | 738 | 0.15 | 0.18 | 52% | `██████████          ` |
| 0.2–0.3 | 662 | 0.24 | 0.27 | 42% | `████████            ` |
| 0.3–0.4 | 422 | 0.34 | 0.37 | 48% | `██████████          ` |
| 0.4–0.5 | 312 | 0.44 | 0.48 | 48% | `██████████          ` |
| 0.5–0.6 | 202 | 0.54 | 0.57 | 41% | `████████            ` |
| 0.6–0.7 | 116 | 0.64 | 0.67 | 56% | `███████████         ` |
| 0.7–0.8 | 77 | 0.74 | 0.76 | 64% | `█████████████       ` |
| 0.8–0.9 | 45 | 0.84 | 0.85 | 76% | `███████████████     ` |
| 0.9–1.0 | 24 | 0.95 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_bills-house_it29_jev-latest_20261016_225511)

- CLI: `jev-agent` jev_agent.py v2 · server commit `e7c89b3` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:55:11 · ended 2026-10-16T23:05:49 · active 0:10 h · wall 0:10 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 15003 · images 1500 · reloads 5 · black-outs 0 · in-game playtime 8:09:26 · Pokédex 2 owned · maps visited 12
- Tokens uncached in / cache reads / out: 5.9M / 0.0M / 1691k · cost $0.25 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 104/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 87 | 5:26:55 | reached: Route 25 |
| 0:00 | 92 | 5:27:14 | reached: Route 24 |
| 0:00 | 97 | 5:27:29 | reached: Cerulean City |
| 0:00 | 118 | 5:28:09 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 10.6 min, longest 11 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:55:11 | 11 | exited | 15004 | 5.9M / 0.0M / 1691k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 4522 (asked Jev 4513, forced by code 9, labelled 4513) · models jev-1.13.0 · input tokens 5921738 · Jev $0.2487
- Jev latency mean 98 ms · p50 83 · p95 188 · max 660
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 29
- Planner calls 0 ($0.0000, errors 0) · objective changes 4 · objectives Jev marked done 0 · final objective: Go south through Route 5, the Underground Path and Route 6 to Vermilion City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 1 | 100% | 0.62 |
| overworld | 4510 | 34% | 0.26 |
| prompt | 2 | 100% | 0.97 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1365)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 164 | 0.08 | 0.12 | 72% | `██████████████      ` |
| 0.1–0.2 | 1436 | 0.15 | 0.20 | 41% | `████████            ` |
| 0.2–0.3 | 1581 | 0.24 | 0.29 | 26% | `█████               ` |
| 0.3–0.4 | 758 | 0.34 | 0.38 | 26% | `█████               ` |
| 0.4–0.5 | 353 | 0.44 | 0.48 | 32% | `██████              ` |
| 0.5–0.6 | 124 | 0.54 | 0.58 | 43% | `█████████           ` |
| 0.6–0.7 | 70 | 0.64 | 0.67 | 56% | `███████████         ` |
| 0.7–0.8 | 21 | 0.74 | 0.76 | 71% | `██████████████      ` |
| 0.8–0.9 | 2 | 0.82 | 0.84 | 50% | `██████████          ` |
| 0.9–1.0 | 4 | 0.94 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_bills-house_it26_jev-latest_20261016_223553)

- CLI: `jev-agent` jev_agent.py v2 · server commit `f069644` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:35:53 · ended 2026-10-16T22:39:59 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 4588 · images 238 · reloads 3 · black-outs 0 · in-game playtime 5:49:08 · Pokédex 2 owned · maps visited 2
- Tokens uncached in / cache reads / out: 2.9M / 0.0M / 647k · cost $0.12 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 96/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 33 | 5:24:42 | reached: Route 25 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.1 min, longest 4 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:35:53 | 4 | stuck | 4588 | 2.9M / 0.0M / 647k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2011 (asked Jev 1982, forced by code 29, labelled 1982) · models jev-1.13.0 · input tokens 2909437 · Jev $0.1222
- Jev latency mean 96 ms · p50 81 · p95 191 · max 611
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 26
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket: talk to Bill (he looks like a Pokémon), then use the computer at the right end of the room (stand below it, face up, talk), then talk to Bill again when he comes out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 1964 | 60% | 0.31 |
| prompt | 18 | 94% | 0.46 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3235)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 24 | 0.09 | 0.17 | 71% | `██████████████      ` |
| 0.1–0.2 | 658 | 0.15 | 0.20 | 69% | `██████████████      ` |
| 0.2–0.3 | 608 | 0.24 | 0.28 | 62% | `████████████        ` |
| 0.3–0.4 | 238 | 0.34 | 0.38 | 43% | `█████████           ` |
| 0.4–0.5 | 118 | 0.44 | 0.47 | 25% | `█████               ` |
| 0.5–0.6 | 80 | 0.55 | 0.57 | 20% | `████                ` |
| 0.6–0.7 | 75 | 0.65 | 0.66 | 55% | `███████████         ` |
| 0.7–0.8 | 128 | 0.74 | 0.75 | 85% | `█████████████████   ` |
| 0.8–0.9 | 42 | 0.83 | 0.84 | 93% | `███████████████████ ` |
| 0.9–1.0 | 11 | 0.94 | 0.95 | 91% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_bills-house_it27_jev-latest_20261016_224348)

- CLI: `jev-agent` jev_agent.py v2 · server commit `608d922` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:43:48 · ended 2026-10-16T22:48:19 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 5791 · images 269 · reloads 3 · black-outs 0 · in-game playtime 6:02:40 · Pokédex 2 owned · maps visited 2
- Tokens uncached in / cache reads / out: 2.6M / 0.0M / 581k · cost $0.11 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 35 | 96/104 | 73 | 61 | 77 | 64 | Slash, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 37 | 5:24:51 | reached: Route 25 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.5 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:43:48 | 5 | stuck | 5791 | 2.6M / 0.0M / 581k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2013 (asked Jev 1912, forced by code 101, labelled 1912) · models jev-1.13.0 · input tokens 2605755 · Jev $0.1094
- Jev latency mean 100 ms · p50 84 · p95 206 · max 574
- Fallbacks: none (variant without a safety net)
- Segment bills-house from state `93bd0cba50dac4a2` to `reached: Vermilion City` · iteration 27
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket: talk to Bill (he looks like a Pokémon), then use the computer at the right end of the room (stand below it, face up, talk), then talk to Bill again when he comes out.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 1846 | 37% | 0.30 |
| prompt | 66 | 88% | 0.42 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1696)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 59 | 0.08 | 0.17 | 42% | `████████            ` |
| 0.1–0.2 | 609 | 0.15 | 0.20 | 44% | `█████████           ` |
| 0.2–0.3 | 539 | 0.24 | 0.30 | 36% | `███████             ` |
| 0.3–0.4 | 294 | 0.34 | 0.39 | 26% | `█████               ` |
| 0.4–0.5 | 102 | 0.44 | 0.48 | 24% | `█████               ` |
| 0.5–0.6 | 64 | 0.54 | 0.57 | 8% | `██                  ` |
| 0.6–0.7 | 67 | 0.64 | 0.66 | 39% | `████████            ` |
| 0.7–0.8 | 99 | 0.74 | 0.76 | 67% | `█████████████       ` |
| 0.8–0.9 | 59 | 0.82 | 0.84 | 63% | `█████████████       ` |
| 0.9–1.0 | 20 | 0.93 | 0.94 | 95% | `███████████████████ ` |

### jev-solo: jev-latest (jev-solo-rommap_mt-moon_it8_jev-latest_20261016_203109)

- CLI: `jev-agent` jev_agent.py v2 · server commit `9646940` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:31:09 · ended 2026-10-16T20:31:20 · active 0:00 h · wall 0:00 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 139 · images 35 · reloads 0 · black-outs 0 · in-game playtime 7:02:19 · Pokédex 6 owned · maps visited 6
- Tokens uncached in / cache reads / out: 0.1M / 0.0M / 9k · cost $0.00 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 46/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 47/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 128 | 7:01:32 | reached: Route 4 |
| 0:00 | 130 | 7:01:55 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 0.2 min, longest 0 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:31:09 | 0 | segment_goal | 138 | 0.1M / 0.0M / 9k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 86 (asked Jev 50, forced by code 36, labelled 50) · models jev-1.13.0 · input tokens 57073 · Jev $0.0024
- Jev latency mean 108 ms · p50 106 · p95 198 · max 259
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 8
- Planner calls 0 ($0.0000, errors 0) · objective changes 2 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 14 | 100% | 0.74 |
| overworld | 33 | 85% | 0.66 |
| prompt | 3 | 67% | 0.74 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1712)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 1 | 0.09 | 0.22 | 100% | `████████████████████` |
| 0.1–0.2 | 1 | 0.17 | 0.27 | 100% | `████████████████████` |
| 0.2–0.3 | 3 | 0.25 | 0.38 | 33% | `███████             ` |
| 0.3–0.4 | 3 | 0.35 | 0.44 | 33% | `███████             ` |
| 0.5–0.6 | 2 | 0.53 | 0.60 | 50% | `██████████          ` |
| 0.6–0.7 | 10 | 0.64 | 0.69 | 100% | `████████████████████` |
| 0.7–0.8 | 9 | 0.77 | 0.81 | 89% | `██████████████████  ` |
| 0.8–0.9 | 17 | 0.83 | 0.86 | 100% | `████████████████████` |
| 0.9–1.0 | 4 | 0.95 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_mt-moon_it11_jev-latest_20261016_204801)

- CLI: `jev-agent` jev_agent.py v2 · server commit `13681fc` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:48:01 · ended 2026-10-16T20:48:17 · active 0:00 h · wall 0:00 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 306 · images 42 · reloads 0 · black-outs 0 · in-game playtime 7:06:43 · Pokédex 6 owned · maps visited 6
- Tokens uncached in / cache reads / out: 0.1M / 0.0M / 19k · cost $0.00 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 52/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 47/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 9 | 6:51:04 | reached: Route 4 |
| 0:00 | 14 | 6:51:06 | reached: Mt. Moon 1F |
| 0:00 | 197 | 7:02:03 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 0.3 min, longest 0 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:48:01 | 0 | segment_goal | 305 | 0.1M / 0.0M / 19k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 132 (asked Jev 98, forced by code 34, labelled 98) · models jev-1.13.0 · input tokens 109427 · Jev $0.0046
- Jev latency mean 87 ms · p50 74 · p95 159 · max 336
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 11
- Planner calls 0 ($0.0000, errors 0) · objective changes 2 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 13 | 100% | 0.74 |
| overworld | 81 | 70% | 0.44 |
| prompt | 4 | 100% | 0.58 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1965)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 5 | 0.08 | 0.20 | 80% | `████████████████    ` |
| 0.1–0.2 | 12 | 0.15 | 0.28 | 83% | `█████████████████   ` |
| 0.2–0.3 | 18 | 0.23 | 0.35 | 50% | `██████████          ` |
| 0.3–0.4 | 9 | 0.34 | 0.46 | 44% | `█████████           ` |
| 0.4–0.5 | 9 | 0.45 | 0.52 | 56% | `███████████         ` |
| 0.5–0.6 | 4 | 0.57 | 0.62 | 100% | `████████████████████` |
| 0.6–0.7 | 9 | 0.64 | 0.69 | 89% | `██████████████████  ` |
| 0.7–0.8 | 16 | 0.75 | 0.79 | 94% | `███████████████████ ` |
| 0.8–0.9 | 12 | 0.86 | 0.88 | 92% | `██████████████████  ` |
| 0.9–1.0 | 4 | 0.93 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_mt-moon_it9_jev-latest_20261016_204053)

- CLI: `jev-agent` jev_agent.py v2 · server commit `fe40de0` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:40:53 · ended 2026-10-16T20:42:19 · active 0:01 h · wall 0:01 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 2109 · images 245 · reloads 0 · black-outs 0 · in-game playtime 8:34:15 · Pokédex 6 owned · maps visited 7
- Tokens uncached in / cache reads / out: 0.7M / 0.0M / 121k · cost $0.03 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 26 | 56/73 | 45 | 42 | 60 | 49 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 17 | 52/52 | 26 | 27 | 32 | 38 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 126 | 6:54:24 | reached: Mt. Moon 1F |
| 0:01 | 1815 | 8:08:31 | reached: Route 4 |
| 0:01 | 2058 | 8:32:06 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 1.4 min, longest 1 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:40:53 | 1 | segment_goal | 2108 | 0.7M / 0.0M / 121k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 798 (asked Jev 584, forced by code 214, labelled 584) · models jev-1.13.0 · input tokens 694952 · Jev $0.0292
- Jev latency mean 85 ms · p50 77 · p95 146 · max 305
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 9
- Planner calls 0 ($0.0000, errors 0) · objective changes 5 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 128 | 79% | 0.59 |
| faint_switch | 2 | 50% | 0.47 |
| overworld | 446 | 81% | 0.36 |
| prompt | 8 | 100% | 0.62 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3308)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 9 | 0.08 | 0.19 | 67% | `█████████████       ` |
| 0.1–0.2 | 87 | 0.15 | 0.25 | 64% | `█████████████       ` |
| 0.2–0.3 | 111 | 0.25 | 0.33 | 69% | `██████████████      ` |
| 0.3–0.4 | 100 | 0.34 | 0.41 | 86% | `█████████████████   ` |
| 0.4–0.5 | 84 | 0.45 | 0.51 | 84% | `█████████████████   ` |
| 0.5–0.6 | 82 | 0.55 | 0.60 | 90% | `██████████████████  ` |
| 0.6–0.7 | 44 | 0.64 | 0.69 | 91% | `██████████████████  ` |
| 0.7–0.8 | 34 | 0.74 | 0.78 | 94% | `███████████████████ ` |
| 0.8–0.9 | 22 | 0.85 | 0.87 | 91% | `██████████████████  ` |
| 0.9–1.0 | 11 | 0.93 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_cerulean_it17_jev-latest_20261016_212835)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a7a6eb8` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:28:35 · ended 2026-10-16T21:34:46 · active 0:06 h · wall 0:06 h · paused 0:00 h · exit: **stuck**
- Tool calls 5984 · images 874 · reloads 3 · black-outs 0 · in-game playtime 9:03:24 · Pokédex 6 owned · maps visited 7
- Tokens uncached in / cache reads / out: 3.2M / 0.0M / 830k · cost $0.14 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 28 | 73/78 | 48 | 45 | 65 | 52 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 17 | 52/52 | 26 | 27 | 31 | 38 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 12 | 34/34 | 17 | 16 | 19 | 15 | Gust, Quick Attack |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |
| 0:00 | 452 | 7:23:00 | reached: Route 24 |
| 0:00 | 711 | 7:36:53 | reached: Route 25 |
| 0:01 | 1292 | 8:06:33 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 6.2 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:28:35 | 6 | stuck | 5984 | 3.2M / 0.0M / 830k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2825 (asked Jev 2721, forced by code 104, labelled 2721) · models jev-1.13.0 · input tokens 3245243 · Jev $0.1363
- Jev latency mean 97 ms · p50 83 · p95 178 · max 580
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 17
- Planner calls 0 ($0.0000, errors 0) · objective changes 15 · objectives Jev marked done 0 · final objective: Train before the next gym: walk through tall grass and win wild battles until your best Pokémon reaches level 30 (now 28).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 58 | 83% | 0.53 |
| faint_switch | 9 | 56% | 0.56 |
| overworld | 2644 | 50% | 0.27 |
| prompt | 10 | 90% | 0.72 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1864)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 92 | 0.08 | 0.15 | 63% | `█████████████       ` |
| 0.1–0.2 | 849 | 0.15 | 0.20 | 49% | `██████████          ` |
| 0.2–0.3 | 860 | 0.24 | 0.28 | 47% | `█████████           ` |
| 0.3–0.4 | 388 | 0.34 | 0.38 | 49% | `██████████          ` |
| 0.4–0.5 | 240 | 0.44 | 0.48 | 50% | `██████████          ` |
| 0.5–0.6 | 135 | 0.54 | 0.57 | 55% | `███████████         ` |
| 0.6–0.7 | 83 | 0.64 | 0.67 | 69% | `██████████████      ` |
| 0.7–0.8 | 41 | 0.74 | 0.76 | 73% | `███████████████     ` |
| 0.8–0.9 | 19 | 0.83 | 0.85 | 68% | `██████████████      ` |
| 0.9–1.0 | 14 | 0.94 | 0.95 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_cerulean_it14_jev-latest_20261016_210553)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1d59049` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:05:53 · ended 2026-10-16T21:11:39 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **stuck**
- Tool calls 6214 · images 557 · reloads 4 · black-outs 0 · in-game playtime 7:49:05 · Pokédex 6 owned · maps visited 2
- Tokens uncached in / cache reads / out: 3.4M / 0.0M / 808k · cost $0.14 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 0/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 16 | 43/50 | 25 | 26 | 30 | 36 | Stun Spore, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 5.8 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:05:53 | 6 | stuck | 6214 | 3.4M / 0.0M / 808k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2680 (asked Jev 2658, forced by code 22, labelled 2658) · models jev-1.13.0 · input tokens 3379935 · Jev $0.1420
- Jev latency mean 96 ms · p50 84 · p95 167 · max 432
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 14
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 17 | 94% | 0.35 |
| faint_switch | 1 | 100% | 0.88 |
| overworld | 2638 | 57% | 0.25 |
| prompt | 2 | 100% | 0.54 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2886)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 115 | 0.08 | 0.14 | 69% | `██████████████      ` |
| 0.1–0.2 | 1384 | 0.15 | 0.20 | 58% | `████████████        ` |
| 0.2–0.3 | 616 | 0.23 | 0.29 | 50% | `██████████          ` |
| 0.3–0.4 | 147 | 0.34 | 0.40 | 52% | `██████████          ` |
| 0.4–0.5 | 65 | 0.44 | 0.48 | 42% | `████████            ` |
| 0.5–0.6 | 70 | 0.55 | 0.58 | 44% | `█████████           ` |
| 0.6–0.7 | 73 | 0.65 | 0.66 | 52% | `██████████          ` |
| 0.7–0.8 | 90 | 0.74 | 0.76 | 78% | `████████████████    ` |
| 0.8–0.9 | 78 | 0.84 | 0.85 | 88% | `██████████████████  ` |
| 0.9–1.0 | 20 | 0.92 | 0.92 | 95% | `███████████████████ ` |

### jev-solo: jev-latest (jev-solo_cerulean_it12_jev-latest_20261016_204844)

- CLI: `jev-agent` jev_agent.py v2 · server commit `13681fc` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:48:44 · ended 2026-10-16T20:54:14 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **stuck**
- Tool calls 6561 · images 593 · reloads 3 · black-outs 0 · in-game playtime 8:25:03 · Pokédex 6 owned · maps visited 9
- Tokens uncached in / cache reads / out: 3.3M / 0.0M / 788k · cost $0.14 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 64/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 16 | 50/50 | 25 | 26 | 30 | 36 | Stun Spore, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 16 | 7:01:55 | reached: Cerulean City |
| 0:00 | 567 | 7:21:36 | reached: Route 4 |
| 0:00 | 602 | 7:22:02 | reached: Mt. Moon 1F |
| 0:00 | 622 | 7:22:22 | reached: Route 3 |
| 0:00 | 721 | 7:24:15 | reached: Pewter City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 5.5 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:48:44 | 6 | stuck | 6561 | 3.3M / 0.0M / 788k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2728 (asked Jev 2677, forced by code 51, labelled 2677) · models jev-1.13.0 · input tokens 3333736 · Jev $0.1400
- Jev latency mean 86 ms · p50 79 · p95 150 · max 427
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 12
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 29 | 86% | 0.56 |
| faint_switch | 2 | 50% | 0.40 |
| overworld | 2644 | 61% | 0.25 |
| prompt | 2 | 100% | 0.38 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3024)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 130 | 0.08 | 0.15 | 73% | `███████████████     ` |
| 0.1–0.2 | 1343 | 0.15 | 0.21 | 59% | `████████████        ` |
| 0.2–0.3 | 602 | 0.24 | 0.29 | 56% | `███████████         ` |
| 0.3–0.4 | 192 | 0.33 | 0.39 | 53% | `███████████         ` |
| 0.4–0.5 | 73 | 0.44 | 0.48 | 59% | `████████████        ` |
| 0.5–0.6 | 85 | 0.55 | 0.57 | 67% | `█████████████       ` |
| 0.6–0.7 | 75 | 0.65 | 0.67 | 73% | `███████████████     ` |
| 0.7–0.8 | 90 | 0.75 | 0.76 | 86% | `█████████████████   ` |
| 0.8–0.9 | 67 | 0.85 | 0.85 | 88% | `██████████████████  ` |
| 0.9–1.0 | 20 | 0.92 | 0.92 | 95% | `███████████████████ ` |

### jev-solo: jev-latest (jev-solo_cerulean_it19_jev-latest_20261016_214410)

- CLI: `jev-agent` jev_agent.py v2 · server commit `ec86739` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:44:10 · ended 2026-10-16T21:48:31 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 7557 · images 3 · reloads 3 · black-outs 0 · in-game playtime 7:23:24 · Pokédex 6 owned · maps visited 2
- Tokens uncached in / cache reads / out: 3.5M / 0.0M / 995k · cost $0.15 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 38/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 47/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 13 | 7:01:49 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.3 min, longest 4 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:44:10 | 4 | stuck | 7557 | 3.5M / 0.0M / 995k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2002 (asked Jev 1999, forced by code 3, labelled 1999) · models jev-1.13.0 · input tokens 3455830 · Jev $0.1451
- Jev latency mean 100 ms · p50 87 · p95 175 · max 496
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 19
- Planner calls 0 ($0.0000, errors 0) · objective changes 1667 · objectives Jev marked done 0 · final objective: Heal at the Cerulean Poké Center once (walk in, talk to the nurse, answer YES): after a lost battle you wake up at the last Poké Center you used.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| overworld | 1999 | 13% | 0.72 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.6005)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.2–0.3 | 15 | 0.24 | 0.27 | 0% | `                    ` |
| 0.3–0.4 | 51 | 0.36 | 0.38 | 2% | `                    ` |
| 0.4–0.5 | 195 | 0.46 | 0.47 | 7% | `█                   ` |
| 0.5–0.6 | 229 | 0.54 | 0.56 | 15% | `███                 ` |
| 0.6–0.7 | 230 | 0.65 | 0.66 | 9% | `██                  ` |
| 0.7–0.8 | 466 | 0.75 | 0.76 | 11% | `██                  ` |
| 0.8–0.9 | 645 | 0.84 | 0.85 | 10% | `██                  ` |
| 0.9–1.0 | 168 | 0.93 | 0.93 | 42% | `████████            ` |

### jev-solo: jev-latest (jev-solo_cerulean_it15_jev-latest_20261016_211215)

- CLI: `jev-agent` jev_agent.py v2 · server commit `1731420` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:12:15 · ended 2026-10-16T21:16:51 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 7643 · images 405 · reloads 4 · black-outs 0 · in-game playtime 8:16:02 · Pokédex 6 owned · maps visited 14
- Tokens uncached in / cache reads / out: 2.6M / 0.0M / 600k · cost $0.11 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 25 | 70/70 | 43 | 40 | 58 | 47 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 16 | 50/50 | 25 | 26 | 30 | 36 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |
| 0:00 | 160 | 7:15:24 | reached: Route 4 |
| 0:00 | 169 | 7:15:30 | reached: Route 3 |
| 0:00 | 224 | 7:16:39 | reached: Pewter City |
| 0:00 | 270 | 7:17:35 | reached: Route 2 |
| 0:00 | 462 | 7:22:49 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.6 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:12:15 | 5 | stuck | 7643 | 2.6M / 0.0M / 600k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2854 (asked Jev 2023, forced by code 831, labelled 2023) · models jev-1.13.0 · input tokens 2583832 · Jev $0.1085
- Jev latency mean 86 ms · p50 78 · p95 138 · max 461
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 15
- Planner calls 0 ($0.0000, errors 0) · objective changes 5 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 42 | 76% | 0.47 |
| faint_switch | 8 | 38% | 0.55 |
| overworld | 1969 | 62% | 0.27 |
| prompt | 4 | 100% | 0.75 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2828)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 73 | 0.08 | 0.16 | 63% | `█████████████       ` |
| 0.1–0.2 | 912 | 0.15 | 0.21 | 60% | `████████████        ` |
| 0.2–0.3 | 468 | 0.23 | 0.29 | 56% | `███████████         ` |
| 0.3–0.4 | 163 | 0.34 | 0.40 | 66% | `█████████████       ` |
| 0.4–0.5 | 83 | 0.45 | 0.52 | 54% | `███████████         ` |
| 0.5–0.6 | 85 | 0.54 | 0.59 | 56% | `███████████         ` |
| 0.6–0.7 | 86 | 0.64 | 0.67 | 71% | `██████████████      ` |
| 0.7–0.8 | 63 | 0.75 | 0.76 | 79% | `████████████████    ` |
| 0.8–0.9 | 67 | 0.84 | 0.85 | 90% | `██████████████████  ` |
| 0.9–1.0 | 23 | 0.93 | 0.93 | 96% | `███████████████████ ` |

### jev-solo: jev-latest (jev-solo_cerulean_it13_jev-latest_20261016_205621)

- CLI: `jev-agent` jev_agent.py v2 · server commit `786d3bb` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:56:21 · ended 2026-10-16T21:02:48 · active 0:06 h · wall 0:06 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 8000 · images 582 · reloads 4 · black-outs 0 · in-game playtime 8:08:30 · Pokédex 6 owned · maps visited 12
- Tokens uncached in / cache reads / out: 3.5M / 0.0M / 804k · cost $0.15 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 25 | 68/70 | 43 | 40 | 58 | 47 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 47/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |
| 0:00 | 136 | 7:09:34 | reached: Route 4 |
| 0:00 | 178 | 7:10:09 | reached: Route 3 |
| 0:00 | 198 | 7:10:29 | reached: Mt. Moon 1F |
| 0:00 | 270 | 7:11:53 | reached: Pewter City |
| 0:01 | 1856 | 7:12:49 | reached: Route 2 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 6.4 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:56:21 | 6 | exited | 8001 | 3.5M / 0.0M / 804k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2912 (asked Jev 2845, forced by code 67, labelled 2845) · models jev-1.13.0 · input tokens 3527174 · Jev $0.1481
- Jev latency mean 93 ms · p50 85 · p95 157 · max 443
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 13
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 35 | 94% | 0.64 |
| faint_switch | 2 | 50% | 0.56 |
| overworld | 2808 | 63% | 0.28 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2948)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 148 | 0.08 | 0.16 | 75% | `███████████████     ` |
| 0.1–0.2 | 1169 | 0.14 | 0.21 | 65% | `█████████████       ` |
| 0.2–0.3 | 642 | 0.24 | 0.31 | 56% | `███████████         ` |
| 0.3–0.4 | 282 | 0.34 | 0.40 | 54% | `███████████         ` |
| 0.4–0.5 | 154 | 0.44 | 0.48 | 66% | `█████████████       ` |
| 0.5–0.6 | 128 | 0.55 | 0.58 | 61% | `████████████        ` |
| 0.6–0.7 | 131 | 0.65 | 0.67 | 67% | `█████████████       ` |
| 0.7–0.8 | 110 | 0.74 | 0.76 | 76% | `███████████████     ` |
| 0.8–0.9 | 64 | 0.84 | 0.85 | 92% | `██████████████████  ` |
| 0.9–1.0 | 17 | 0.93 | 0.93 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_cerulean_it18_jev-latest_20261016_213616)

- CLI: `jev-agent` jev_agent.py v2 · server commit `3d49c0a` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:36:16 · ended 2026-10-16T21:42:46 · active 0:06 h · wall 0:06 h · paused 0:00 h · exit: **stuck**
- Tool calls 8128 · images 324 · reloads 3 · black-outs 0 · in-game playtime 9:05:07 · Pokédex 6 owned · maps visited 22
- Tokens uncached in / cache reads / out: 3.2M / 0.0M / 704k · cost $0.13 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 24 | 68/68 | 41 | 38 | 56 | 45 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 47/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 11 | 32/32 | 16 | 15 | 18 | 14 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |
| 0:00 | 838 | 7:33:43 | reached: Route 4 |
| 0:00 | 847 | 7:33:49 | reached: Route 3 |
| 0:00 | 896 | 7:34:29 | reached: Mt. Moon 1F |
| 0:00 | 1038 | 7:37:29 | reached: Pewter City |
| 0:00 | 1077 | 7:38:19 | reached: Route 2 |
| 0:00 | 1335 | 7:45:17 | reached: Viridian City |
| 0:00 | 1340 | 7:45:31 | reached: Route 1 |
| 0:00 | 1347 | 7:45:48 | reached: Pallet Town |
| 0:01 | 2100 | 8:16:06 | reached: Route 22 |
| 0:01 | 2121 | 8:16:44 | reached: Route 23 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 6.5 min, longest 7 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:36:16 | 7 | stuck | 8128 | 3.2M / 0.0M / 704k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2797 (asked Jev 2540, forced by code 257, labelled 2540) · models jev-1.13.0 · input tokens 3172990 · Jev $0.1333
- Jev latency mean 91 ms · p50 80 · p95 155 · max 658
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 18
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 33 | 94% | 0.54 |
| faint_switch | 2 | 50% | 0.46 |
| overworld | 2505 | 75% | 0.24 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.4466)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 156 | 0.08 | 0.14 | 78% | `████████████████    ` |
| 0.1–0.2 | 1076 | 0.14 | 0.20 | 76% | `███████████████     ` |
| 0.2–0.3 | 591 | 0.24 | 0.30 | 74% | `███████████████     ` |
| 0.3–0.4 | 367 | 0.34 | 0.39 | 72% | `██████████████      ` |
| 0.4–0.5 | 161 | 0.44 | 0.49 | 80% | `████████████████    ` |
| 0.5–0.6 | 83 | 0.54 | 0.59 | 70% | `██████████████      ` |
| 0.6–0.7 | 54 | 0.64 | 0.68 | 68% | `██████████████      ` |
| 0.7–0.8 | 25 | 0.74 | 0.77 | 80% | `████████████████    ` |
| 0.8–0.9 | 25 | 0.84 | 0.86 | 80% | `████████████████    ` |
| 0.9–1.0 | 2 | 0.94 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_it38_jev-latest_20261017_034849)

- CLI: `jev-agent` jev_agent.py v2 · server commit `99a39a8` · prompt `49106d19e201a25e`
- Started 2026-10-17T03:48:49 · ended 2026-10-17T03:58:40 · active 0:09 h · wall 0:09 h · paused 0:00 h · exit: **stuck**
- Tool calls 11821 · images 933 · reloads 3 · black-outs 0 · in-game playtime 4:00:00 · Pokédex 2 owned · maps visited 35
- Tokens uncached in / cache reads / out: 4.9M / 0.0M / 1073k · cost $0.21 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 25 | 71/71 | 44 | 39 | 52 | 48 | Rage, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:12 | reached: Pallet Town |
| 0:00 | 119 | 0:02:01 | obtained: Charmander |
| 0:00 | 119 | 0:02:01 | starter: Charmander |
| 0:00 | 186 | 0:05:04 | reached: Route 1 |
| 0:00 | 191 | 0:05:24 | reached: Viridian City |
| 0:00 | 433 | 0:13:34 | reached: Route 2 |
| 0:00 | 459 | 0:14:34 | reached: Route 22 |
| 0:00 | 984 | 0:55:45 | reached: Pewter City |
| 0:00 | 1137 | 1:06:12 | evolved: Charmander → Charmeleon |
| 0:00 | 1138 | 1:06:31 | badge: Boulder |
| 0:00 | 1147 | 1:06:53 | reached: Route 3 |
| 0:01 | 1338 | 1:17:00 | reached: Route 4 |
| 0:01 | 1342 | 1:17:09 | reached: Mt. Moon 1F |
| 0:01 | 1787 | 1:36:35 | reached: Route 23 |
| 0:04 | 4261 | 3:06:57 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 9.9 min, longest 10 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T03:48:49 | 10 | stuck | 11821 | 4.9M / 0.0M / 1073k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 3658 (asked Jev 3352, forced by code 306, labelled 3352) · models jev-1.13.0 · input tokens 4908879 · Jev $0.2062
- Jev latency mean 90 ms · p50 81 · p95 162 · max 447
- Fallbacks: none (variant without a safety net)
- Iteration 38
- Planner calls 0 ($0.0000, errors 0) · objective changes 34 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 138 | 92% | 0.66 |
| intro | 51 | 49% | 0.41 |
| overworld | 3098 | 58% | 0.40 |
| prompt | 65 | 40% | 0.62 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1763)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 16 | 0.07 | 0.19 | 62% | `████████████        ` |
| 0.1–0.2 | 557 | 0.16 | 0.23 | 60% | `████████████        ` |
| 0.2–0.3 | 937 | 0.24 | 0.30 | 54% | `███████████         ` |
| 0.3–0.4 | 487 | 0.34 | 0.40 | 50% | `██████████          ` |
| 0.4–0.5 | 242 | 0.44 | 0.51 | 57% | `███████████         ` |
| 0.5–0.6 | 244 | 0.55 | 0.60 | 54% | `███████████         ` |
| 0.6–0.7 | 285 | 0.64 | 0.68 | 59% | `████████████        ` |
| 0.7–0.8 | 242 | 0.74 | 0.77 | 69% | `██████████████      ` |
| 0.8–0.9 | 202 | 0.84 | 0.86 | 77% | `███████████████     ` |
| 0.9–1.0 | 140 | 0.93 | 0.94 | 91% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_cerulean_it16_jev-latest_20261016_211754)

- CLI: `jev-agent` jev_agent.py v2 · server commit `ad0fb66` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:17:55 · ended 2026-10-16T21:23:52 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 12000 · images 727 · reloads 6 · black-outs 0 · in-game playtime 7:48:32 · Pokédex 6 owned · maps visited 6
- Tokens uncached in / cache reads / out: 2.7M / 0.0M / 558k · cost $0.11 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 27 | 75/75 | 46 | 43 | 63 | 50 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 17 | 52/52 | 26 | 27 | 31 | 38 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 14 | 7:01:52 | reached: Cerulean City |
| 0:05 | 11673 | 7:29:13 | reached: Route 24 |
| 0:05 | 11779 | 7:36:50 | reached: Route 25 |
| 0:05 | 11870 | 7:42:19 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 5.9 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:17:55 | 6 | exited | 12001 | 2.7M / 0.0M / 558k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 3736 (asked Jev 2099, forced by code 1637, labelled 2099) · models jev-1.13.0 · input tokens 2720975 · Jev $0.1143
- Jev latency mean 97 ms · p50 85 · p95 174 · max 585
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 16
- Planner calls 0 ($0.0000, errors 0) · objective changes 18 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 79 | 75% | 0.48 |
| faint_switch | 9 | 33% | 0.53 |
| overworld | 1994 | 54% | 0.41 |
| prompt | 17 | 100% | 0.69 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1848)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 21 | 0.06 | 0.27 | 76% | `███████████████     ` |
| 0.1–0.2 | 299 | 0.16 | 0.29 | 66% | `█████████████       ` |
| 0.2–0.3 | 473 | 0.25 | 0.36 | 63% | `█████████████       ` |
| 0.3–0.4 | 368 | 0.34 | 0.44 | 43% | `█████████           ` |
| 0.4–0.5 | 222 | 0.44 | 0.52 | 37% | `███████             ` |
| 0.5–0.6 | 207 | 0.54 | 0.59 | 37% | `███████             ` |
| 0.6–0.7 | 210 | 0.64 | 0.67 | 48% | `██████████          ` |
| 0.7–0.8 | 127 | 0.74 | 0.77 | 70% | `██████████████      ` |
| 0.8–0.9 | 113 | 0.85 | 0.86 | 84% | `█████████████████   ` |
| 0.9–1.0 | 59 | 0.93 | 0.93 | 83% | `█████████████████   ` |

### jev-solo: jev-latest (jev-solo_it37_jev-latest_20261017_033550)

- CLI: `jev-agent` jev_agent.py v2 · server commit `15d4cde` · prompt `49106d19e201a25e`
- Started 2026-10-17T03:35:50 · ended 2026-10-17T03:45:57 · active 0:10 h · wall 0:10 h · paused 0:00 h · exit: **stuck**
- Tool calls 13115 · images 1186 · reloads 3 · black-outs 0 · in-game playtime 4:53:35 · Pokédex 2 owned · maps visited 35
- Tokens uncached in / cache reads / out: 5.2M / 0.0M / 1108k · cost $0.22 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 27 | 69/76 | 46 | 47 | 57 | 51 | Scratch, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 84 | 0:00:10 | reached: Pallet Town |
| 0:00 | 117 | 0:01:59 | obtained: Charmander |
| 0:00 | 117 | 0:01:59 | starter: Charmander |
| 0:00 | 189 | 0:05:05 | reached: Route 1 |
| 0:00 | 206 | 0:06:39 | reached: Viridian City |
| 0:00 | 405 | 0:14:07 | reached: Route 2 |
| 0:00 | 459 | 0:17:30 | reached: Route 22 |
| 0:00 | 822 | 0:38:58 | reached: Pewter City |
| 0:01 | 2228 | 1:34:45 | evolved: Charmander → Charmeleon |
| 0:01 | 2567 | 1:49:27 | badge: Boulder |
| 0:01 | 2593 | 1:50:21 | reached: Route 3 |
| 0:01 | 2663 | 1:56:32 | reached: Route 4 |
| 0:01 | 2667 | 1:56:41 | reached: Mt. Moon 1F |
| 0:02 | 3037 | 2:11:47 | reached: Route 23 |
| 0:05 | 5565 | 4:05:27 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 10.1 min, longest 10 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T03:35:50 | 10 | stuck | 13115 | 5.2M / 0.0M / 1108k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 4109 (asked Jev 3577, forced by code 532, labelled 3577) · models jev-1.13.0 · input tokens 5161055 · Jev $0.2168
- Jev latency mean 83 ms · p50 75 · p95 145 · max 471
- Fallbacks: none (variant without a safety net)
- Iteration 37
- Planner calls 0 ($0.0000, errors 0) · objective changes 34 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 236 | 86% | 0.73 |
| intro | 51 | 53% | 0.41 |
| overworld | 3205 | 61% | 0.42 |
| prompt | 85 | 59% | 0.57 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1933)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 23 | 0.08 | 0.22 | 74% | `███████████████     ` |
| 0.1–0.2 | 560 | 0.16 | 0.23 | 62% | `████████████        ` |
| 0.2–0.3 | 937 | 0.24 | 0.31 | 60% | `████████████        ` |
| 0.3–0.4 | 474 | 0.34 | 0.41 | 53% | `███████████         ` |
| 0.4–0.5 | 252 | 0.44 | 0.51 | 54% | `███████████         ` |
| 0.5–0.6 | 233 | 0.55 | 0.60 | 61% | `████████████        ` |
| 0.6–0.7 | 304 | 0.65 | 0.68 | 58% | `████████████        ` |
| 0.7–0.8 | 284 | 0.74 | 0.77 | 68% | `██████████████      ` |
| 0.8–0.9 | 280 | 0.84 | 0.86 | 82% | `████████████████    ` |
| 0.9–1.0 | 230 | 0.95 | 0.96 | 74% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_cerulean_it20_jev-latest_20261016_214906)

- CLI: `jev-agent` jev_agent.py v2 · server commit `0317735` · prompt `49106d19e201a25e`
- Started 2026-10-16T21:49:06 · ended 2026-10-16T21:58:59 · active 0:09 h · wall 0:09 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 15000 · images 662 · reloads 6 · black-outs 0 · in-game playtime 8:46:00 · Pokédex 6 owned · maps visited 6
- Tokens uncached in / cache reads / out: 5.9M / 0.0M / 1417k · cost $0.25 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 27 | 75/75 | 46 | 43 | 62 | 50 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 17 | 52/52 | 26 | 27 | 31 | 38 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 20 | 7:02:09 | reached: Cerulean City |
| 0:00 | 1032 | 7:42:34 | reached: Route 4 |
| 0:02 | 3907 | 8:08:25 | reached: Route 24 |
| 0:03 | 5551 | 8:17:34 | reached: Route 25 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 9.9 min, longest 10 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T21:49:06 | 10 | exited | 15001 | 5.9M / 0.0M / 1417k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 4739 (asked Jev 4479, forced by code 260, labelled 4479) · models jev-1.13.0 · input tokens 5863521 · Jev $0.2463
- Jev latency mean 93 ms · p50 78 · p95 174 · max 645
- Fallbacks: none (variant without a safety net)
- Segment cerulean from state `a5099e91a099f2d9` to `badge: Cascade` · iteration 20
- Planner calls 0 ($0.0000, errors 0) · objective changes 2150 · objectives Jev marked done 0 · final objective: Heal at the Mt. Moon Poké Center once (walk in, talk to the nurse, answer YES): after a lost battle you wake up at the last Poké Center you used.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 127 | 94% | 0.67 |
| faint_switch | 7 | 57% | 0.46 |
| overworld | 4332 | 52% | 0.35 |
| prompt | 13 | 92% | 0.70 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1744)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 113 | 0.08 | 0.16 | 59% | `████████████        ` |
| 0.1–0.2 | 1101 | 0.15 | 0.21 | 64% | `█████████████       ` |
| 0.2–0.3 | 819 | 0.24 | 0.30 | 48% | `██████████          ` |
| 0.3–0.4 | 621 | 0.35 | 0.40 | 37% | `███████             ` |
| 0.4–0.5 | 697 | 0.45 | 0.48 | 46% | `█████████           ` |
| 0.5–0.6 | 496 | 0.54 | 0.57 | 50% | `██████████          ` |
| 0.6–0.7 | 269 | 0.64 | 0.66 | 59% | `████████████        ` |
| 0.7–0.8 | 139 | 0.74 | 0.76 | 71% | `██████████████      ` |
| 0.8–0.9 | 135 | 0.85 | 0.86 | 76% | `███████████████     ` |
| 0.9–1.0 | 89 | 0.94 | 0.95 | 84% | `█████████████████   ` |

### jev-solo: jev-latest (jev-solo_it50_jev-latest_20261017_160614)

- CLI: `jev-agent` jev_agent.py v2 · server commit `27b2af8` · prompt `49106d19e201a25e`
- Started 2026-10-17T16:06:14 · ended 2026-10-17T16:18:10 · active 0:11 h · wall 0:11 h · paused 0:00 h · exit: **stuck**
- Tool calls 15239 · images 1402 · reloads 3 · black-outs 0 · in-game playtime 6:06:30 · Pokédex 2 owned · maps visited 35
- Tokens uncached in / cache reads / out: 5.4M / 0.0M / 1126k · cost $0.22 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 33 | 88/97 | 63 | 55 | 72 | 60 | Rage, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:12 | reached: Pallet Town |
| 0:00 | 121 | 0:02:05 | obtained: Charmander |
| 0:00 | 121 | 0:02:05 | starter: Charmander |
| 0:00 | 205 | 0:05:29 | reached: Route 1 |
| 0:00 | 222 | 0:07:05 | reached: Viridian City |
| 0:00 | 499 | 0:17:15 | reached: Route 2 |
| 0:00 | 553 | 0:20:55 | reached: Route 22 |
| 0:00 | 728 | 0:36:01 | reached: Pewter City |
| 0:01 | 1290 | 1:00:01 | evolved: Charmander → Charmeleon |
| 0:01 | 1330 | 1:03:29 | badge: Boulder |
| 0:01 | 1339 | 1:03:51 | reached: Route 3 |
| 0:01 | 1587 | 1:22:22 | reached: Route 4 |
| 0:01 | 1591 | 1:22:31 | reached: Mt. Moon 1F |
| 0:01 | 1909 | 1:37:22 | reached: Route 23 |
| 0:04 | 3843 | 2:44:10 | reached: Cerulean City |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 11.9 min, longest 12 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T16:06:14 | 12 | stuck | 15239 | 5.4M / 0.0M / 1126k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 4626 (asked Jev 3874, forced by code 752, labelled 3874) · models jev-1.13.0 · input tokens 5354158 · Jev $0.2249
- Jev latency mean 92 ms · p50 81 · p95 160 · max 607
- Fallbacks: none (variant without a safety net)
- Iteration 50
- Planner calls 0 ($0.0000, errors 0) · objective changes 55 · objectives Jev marked done 0 · final objective: Beat Misty in the Cerulean Gym.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 363 | 98% | 0.76 |
| intro | 51 | 49% | 0.41 |
| overworld | 3395 | 60% | 0.46 |
| prompt | 65 | 46% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1893)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 12 | 0.08 | 0.19 | 42% | `████████            ` |
| 0.1–0.2 | 600 | 0.16 | 0.23 | 65% | `█████████████       ` |
| 0.2–0.3 | 897 | 0.24 | 0.31 | 55% | `███████████         ` |
| 0.3–0.4 | 457 | 0.34 | 0.41 | 54% | `███████████         ` |
| 0.4–0.5 | 224 | 0.44 | 0.51 | 53% | `███████████         ` |
| 0.5–0.6 | 232 | 0.55 | 0.60 | 64% | `█████████████       ` |
| 0.6–0.7 | 292 | 0.65 | 0.68 | 60% | `████████████        ` |
| 0.7–0.8 | 268 | 0.74 | 0.77 | 70% | `██████████████      ` |
| 0.8–0.9 | 387 | 0.85 | 0.86 | 83% | `█████████████████   ` |
| 0.9–1.0 | 505 | 0.96 | 0.97 | 71% | `██████████████      ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it3_jev-latest_20261016_193003)

- CLI: `jev-agent` jev_agent.py v2 · server commit `ad71001` · prompt `49106d19e201a25e`
- Started 2026-10-16T19:30:03 · ended 2026-10-16T19:34:35 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 4000 · images 656 · reloads 2 · black-outs 0 · in-game playtime 8:51:18 · Pokédex 6 owned · maps visited 4
- Tokens uncached in / cache reads / out: 1.9M / 0.0M / 406k · cost $0.08 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 27 | 40/76 | 47 | 44 | 63 | 51 | Scratch, Growl, Ember, Leer |
| 2 | Butterfree | 15 | 34/47 | 24 | 25 | 28 | 34 | Tackle, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 720 | 7:28:08 | reached: Mt. Moon 1F |
| 0:02 | 2269 | 8:12:16 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 4.5 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T19:30:03 | 5 | exited | 4001 | 1.9M / 0.0M / 406k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2051 (asked Jev 1549, forced by code 502, labelled 1549) · models jev-1.13.0 · input tokens 1862764 · Jev $0.0782
- Jev latency mean 102 ms · p50 85 · p95 215 · max 910
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 3
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Get through Mt. Moon (ladders down, then up to the exit) and on to Cerulean City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 461 | 74% | 0.41 |
| faint_switch | 3 | 33% | 0.28 |
| overworld | 1078 | 47% | 0.23 |
| prompt | 7 | 100% | 0.44 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2376)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 70 | 0.08 | 0.14 | 44% | `█████████           ` |
| 0.1–0.2 | 467 | 0.15 | 0.20 | 47% | `█████████           ` |
| 0.2–0.3 | 415 | 0.24 | 0.30 | 56% | `███████████         ` |
| 0.3–0.4 | 267 | 0.34 | 0.41 | 64% | `█████████████       ` |
| 0.4–0.5 | 181 | 0.44 | 0.50 | 66% | `█████████████       ` |
| 0.5–0.6 | 88 | 0.54 | 0.59 | 62% | `████████████        ` |
| 0.6–0.7 | 35 | 0.64 | 0.69 | 54% | `███████████         ` |
| 0.7–0.8 | 15 | 0.74 | 0.78 | 27% | `█████               ` |
| 0.8–0.9 | 10 | 0.83 | 0.86 | 30% | `██████              ` |
| 0.9–1.0 | 1 | 0.91 | 0.92 | 0% | `                    ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it4_jev-latest_20261016_193645)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5dbd9a1` · prompt `49106d19e201a25e`
- Started 2026-10-16T19:36:45 · ended 2026-10-16T19:40:53 · active 0:03 h · wall 0:04 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 4000 · images 719 · reloads 1 · black-outs 0 · in-game playtime 8:46:16 · Pokédex 6 owned · maps visited 3
- Tokens uncached in / cache reads / out: 1.7M / 0.0M / 310k · cost $0.07 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 25 | 17/70 | 43 | 40 | 58 | 47 | Scratch, Growl, Ember, Leer |
| 2 | Butterfree | 16 | 17/50 | 25 | 26 | 30 | 36 | Stun Spore, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 26/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 154 | 7:02:07 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 4.1 min, longest 4 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T19:36:45 | 4 | exited | 4001 | 1.7M / 0.0M / 310k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2298 (asked Jev 1570, forced by code 728, labelled 1570) · models jev-1.13.0 · input tokens 1748126 · Jev $0.0734
- Jev latency mean 93 ms · p50 81 · p95 162 · max 465
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 4
- Planner calls 0 ($0.0000, errors 0) · objective changes 1 · objectives Jev marked done 0 · final objective: Get through Mt. Moon (ladders down, then up to the exit) and on to Cerulean City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 529 | 74% | 0.41 |
| faint_switch | 3 | 0% | 0.84 |
| overworld | 1029 | 63% | 0.36 |
| prompt | 9 | 100% | 0.42 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2709)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 7 | 0.08 | 0.17 | 57% | `███████████         ` |
| 0.1–0.2 | 166 | 0.15 | 0.23 | 74% | `███████████████     ` |
| 0.2–0.3 | 343 | 0.25 | 0.32 | 74% | `███████████████     ` |
| 0.3–0.4 | 377 | 0.34 | 0.41 | 71% | `██████████████      ` |
| 0.4–0.5 | 323 | 0.45 | 0.50 | 61% | `████████████        ` |
| 0.5–0.6 | 196 | 0.54 | 0.59 | 63% | `█████████████       ` |
| 0.6–0.7 | 97 | 0.64 | 0.67 | 50% | `██████████          ` |
| 0.7–0.8 | 54 | 0.73 | 0.76 | 46% | `█████████           ` |
| 0.8–0.9 | 6 | 0.84 | 0.86 | 33% | `███████             ` |
| 0.9–1.0 | 1 | 0.96 | 0.98 | 0% | `                    ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it5_jev-latest_20261016_194414)

- CLI: `jev-agent` jev_agent.py v2 · server commit `f34abe1` · prompt `49106d19e201a25e`
- Started 2026-10-16T19:44:14 · ended 2026-10-16T19:47:22 · active 0:03 h · wall 0:03 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 4001 · images 764 · reloads 0 · black-outs 0 · in-game playtime 12:07:21 · Pokédex 7 owned · maps visited 5
- Tokens uncached in / cache reads / out: 1.0M / 0.0M / 136k · cost $0.04 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 31 | 0/87 | 55 | 52 | 73 | 59 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 21 | 0/63 | 33 | 34 | 39 | 47 | Supersonic, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 3/30 | 15 | 14 | 16 | 13 | Gust |
| 4 | AAAAAAAAAA (Zubat) | 10 | 0/28 | 14 | 12 | 19 | 13 | Leech Life, Supersonic |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 888 | 8:21:34 | obtained: Zubat |
| 0:00 | 919 | 8:27:20 | reached: Route 4 |
| 0:00 | 972 | 8:30:12 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 3.1 min, longest 3 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T19:44:14 | 3 | exited | 4002 | 1.0M / 0.0M / 136k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 1993 (asked Jev 922, forced by code 1071, labelled 922) · models jev-1.13.0 · input tokens 1048223 · Jev $0.0440
- Jev latency mean 97 ms · p50 84 · p95 172 · max 558
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 5
- Planner calls 0 ($0.0000, errors 0) · objective changes 9 · objectives Jev marked done 0 · final objective: Your team is weak (35% HP): heal at a Poké Center (walk in, talk to the nurse, answer YES).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 409 | 84% | 0.55 |
| faint_switch | 8 | 75% | 0.68 |
| overworld | 468 | 82% | 0.66 |
| prompt | 37 | 54% | 0.57 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1827)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 2 | 0.07 | 0.41 | 50% | `██████████          ` |
| 0.1–0.2 | 17 | 0.16 | 0.38 | 53% | `███████████         ` |
| 0.2–0.3 | 46 | 0.26 | 0.38 | 59% | `████████████        ` |
| 0.3–0.4 | 97 | 0.35 | 0.44 | 84% | `█████████████████   ` |
| 0.4–0.5 | 105 | 0.45 | 0.53 | 88% | `██████████████████  ` |
| 0.5–0.6 | 125 | 0.54 | 0.61 | 83% | `█████████████████   ` |
| 0.6–0.7 | 168 | 0.65 | 0.69 | 83% | `█████████████████   ` |
| 0.7–0.8 | 205 | 0.74 | 0.78 | 86% | `█████████████████   ` |
| 0.8–0.9 | 126 | 0.84 | 0.86 | 79% | `████████████████    ` |
| 0.9–1.0 | 31 | 0.93 | 0.94 | 81% | `████████████████    ` |

### jev-assist: jev-latest + claude-haiku-4-5-20251001 fallback (jev-assist_after-brock_it2_jev-latest_20261016_174138)

- CLI: `jev-agent` jev_agent.py v2 · server commit `91a5961` · prompt `49106d19e201a25e`
- Started 2026-10-16T17:41:38 · ended 2026-10-16T19:19:33 · active 1:37 h · wall 1:37 h · paused 0:00 h · exit: **manual**
- Tool calls 4296 · images 407 · reloads 2 · black-outs 0 · in-game playtime 8:23:38 · Pokédex 6 owned · maps visited 9
- Tokens uncached in / cache reads / out: 1.4M / 0.0M / 230k · cost $4.45 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Butterfree | 19 | 24/58 | 30 | 31 | 35 | 43 | Tackle, String Shot, Confusion, PoisonPowder |
| 2 | Charmeleon | 23 | 12/65 | 39 | 37 | 53 | 43 | Scratch, Growl, Ember, Leer |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 6 | 6:40:09 | reached: Pewter City |
| 0:00 | 8 | 6:40:24 | reached: Route 3 |
| 0:01 | 112 | 6:48:15 | reached: Route 4 |
| 0:09 | 213 | 6:52:48 | reached: Mt. Moon 1F |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 exited; median 60.1 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T17:41:38 | 60 | rotate | 3371 | 0.9M / 0.0M / 132k |
| 2 | 2026-10-16T18:41:47 | 38 | exited | 922 | 0.6M / 0.0M / 97k |

</details>

**Jev (assist)** — jev-solo's scaffolding plus a safety net: when Jev's confidence is low or code detects stuck/looping, Claude Haiku picks that one action and a fallback event is logged; fallbacks per 1k steps should trend to 0 across self-improvement iterations (bench/improve.py).

- Decisions 2570 (asked Jev 1339, forced by code 1231, labelled 1204) · models jev-1.13.0 · input tokens 1436662 · Jev $0.0603
- Jev latency mean 111 ms · p50 92 · p95 191 · max 2258
- Fallbacks 375 (145.91 per 1k steps; by trigger {'low': 298, 'loop': 37, 'stuck': 40}; agreed with Jev 240; progress within 10 steps 0.024; $4.3871)
- Segment after-brock from state `cbba8272940afafb` to `reached: Cerulean City` · iteration 2
- Planner calls 0 ($4.3871, errors 0) · objective changes 7 · objectives Jev marked done 0 · final objective: Get through Mt. Moon (ladders down, then up to the exit) and on to Cerulean City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 265 | 82% | 0.39 |
| faint_switch | 2 | 0% | 0.68 |
| overworld | 919 | 67% | 0.34 |
| prompt | 18 | 89% | 0.49 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3088)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 9 | 0.09 | 0.17 | 56% | `███████████         ` |
| 0.1–0.2 | 203 | 0.16 | 0.24 | 71% | `██████████████      ` |
| 0.2–0.3 | 304 | 0.24 | 0.31 | 75% | `███████████████     ` |
| 0.3–0.4 | 269 | 0.34 | 0.41 | 73% | `███████████████     ` |
| 0.4–0.5 | 192 | 0.44 | 0.50 | 67% | `█████████████       ` |
| 0.5–0.6 | 121 | 0.54 | 0.59 | 66% | `█████████████       ` |
| 0.6–0.7 | 57 | 0.64 | 0.69 | 63% | `█████████████       ` |
| 0.7–0.8 | 25 | 0.74 | 0.78 | 64% | `█████████████       ` |
| 0.8–0.9 | 9 | 0.86 | 0.88 | 78% | `████████████████    ` |
| 0.9–1.0 | 15 | 0.96 | 0.96 | 73% | `███████████████     ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it10_jev-latest_20261016_204312)

- CLI: `jev-agent` jev_agent.py v2 · server commit `efb2179` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:43:12 · ended 2026-10-16T20:47:10 · active 0:03 h · wall 0:03 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 650 · reloads 0 · black-outs 0 · in-game playtime 10:44:11 · Pokédex 6 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.0M / 0.0M / 352k · cost $0.09 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 30 | 83/84 | 53 | 50 | 71 | 57 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 20 | 60/60 | 31 | 32 | 37 | 45 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 8 | 6:51:04 | reached: Route 4 |
| 0:00 | 13 | 6:51:07 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 3.9 min, longest 4 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:43:12 | 4 | exited | 6001 | 2.0M / 0.0M / 352k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2220 (asked Jev 1743, forced by code 477, labelled 1743) · models jev-1.13.0 · input tokens 2028651 · Jev $0.0852
- Jev latency mean 84 ms · p50 76 · p95 144 · max 375
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 10
- Planner calls 0 ($0.0000, errors 0) · objective changes 8 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 288 | 84% | 0.59 |
| faint_switch | 5 | 60% | 0.55 |
| overworld | 1442 | 70% | 0.30 |
| prompt | 8 | 100% | 0.67 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2973)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 35 | 0.08 | 0.21 | 66% | `█████████████       ` |
| 0.1–0.2 | 409 | 0.15 | 0.25 | 50% | `██████████          ` |
| 0.2–0.3 | 413 | 0.25 | 0.32 | 63% | `█████████████       ` |
| 0.3–0.4 | 285 | 0.34 | 0.41 | 77% | `███████████████     ` |
| 0.4–0.5 | 183 | 0.44 | 0.51 | 87% | `█████████████████   ` |
| 0.5–0.6 | 152 | 0.54 | 0.59 | 91% | `██████████████████  ` |
| 0.6–0.7 | 129 | 0.64 | 0.68 | 95% | `███████████████████ ` |
| 0.7–0.8 | 86 | 0.74 | 0.77 | 94% | `███████████████████ ` |
| 0.8–0.9 | 39 | 0.84 | 0.87 | 95% | `███████████████████ ` |
| 0.9–1.0 | 12 | 0.93 | 0.94 | 92% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it6_jev-latest_20261016_195017)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a910501` · prompt `49106d19e201a25e`
- Started 2026-10-16T19:50:17 · ended 2026-10-16T19:57:55 · active 0:07 h · wall 0:07 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 1712 · reloads 0 · black-outs 0 · in-game playtime 16:10:35 · Pokédex 7 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.2M / 0.0M / 304k · cost $0.09 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charizard | 37 | 0/120 | 83 | 79 | 103 | 88 | Slash, Growl, Ember, Leer |
| 2 | Butterfree | 27 | 76/80 | 43 | 45 | 50 | 61 | Whirlwind, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 874 | 8:20:11 | reached: Route 4 |
| 0:00 | 928 | 8:23:01 | reached: Mt. Moon 1F |
| 0:05 | 4925 | 14:33:09 | evolved: Charmeleon → Charizard |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 7.6 min, longest 8 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T19:50:17 | 8 | exited | 6001 | 2.2M / 0.0M / 304k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 3499 (asked Jev 1973, forced by code 1526, labelled 1973) · models jev-1.13.0 · input tokens 2236921 · Jev $0.0940
- Jev latency mean 93 ms · p50 82 · p95 158 · max 694
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 6
- Planner calls 0 ($0.0000, errors 0) · objective changes 20 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 818 | 90% | 0.60 |
| faint_switch | 6 | 83% | 0.72 |
| overworld | 1070 | 80% | 0.67 |
| prompt | 79 | 71% | 0.57 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.188)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 4 | 0.07 | 0.30 | 50% | `██████████          ` |
| 0.1–0.2 | 18 | 0.15 | 0.30 | 83% | `█████████████████   ` |
| 0.2–0.3 | 93 | 0.25 | 0.38 | 75% | `███████████████     ` |
| 0.3–0.4 | 153 | 0.35 | 0.45 | 87% | `█████████████████   ` |
| 0.4–0.5 | 212 | 0.45 | 0.54 | 84% | `█████████████████   ` |
| 0.5–0.6 | 254 | 0.55 | 0.62 | 90% | `██████████████████  ` |
| 0.6–0.7 | 318 | 0.64 | 0.69 | 94% | `███████████████████ ` |
| 0.7–0.8 | 416 | 0.75 | 0.78 | 80% | `████████████████    ` |
| 0.8–0.9 | 392 | 0.84 | 0.86 | 79% | `████████████████    ` |
| 0.9–1.0 | 113 | 0.93 | 0.94 | 82% | `████████████████    ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it6_jev-latest_20261016_195755)

- CLI: `jev-agent` jev_agent.py v2 · server commit `a40b0ef` · prompt `49106d19e201a25e`
- Started 2026-10-16T19:57:56 · ended 2026-10-16T20:05:25 · active 0:07 h · wall 0:07 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 545 · reloads 0 · black-outs 0 · in-game playtime 10:49:40 · Pokédex 6 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.4M / 0.0M / 472k · cost $0.10 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 28 | 79/79 | 49 | 46 | 66 | 53 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 18 | 55/55 | 28 | 29 | 33 | 41 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 11 | 32/32 | 16 | 15 | 18 | 14 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 59 | 6:53:27 | reached: Mt. Moon 1F |
| 0:04 | 3290 | 9:08:49 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 7.4 min, longest 7 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T19:57:56 | 7 | exited | 6001 | 2.4M / 0.0M / 472k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2293 (asked Jev 1884, forced by code 409, labelled 1884) · models jev-1.13.0 · input tokens 2390497 · Jev $0.1004
- Jev latency mean 112 ms · p50 95 · p95 213 · max 675
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 6
- Planner calls 0 ($0.0000, errors 0) · objective changes 5 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 258 | 78% | 0.56 |
| faint_switch | 2 | 100% | 0.91 |
| overworld | 1604 | 65% | 0.28 |
| prompt | 20 | 70% | 0.52 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.283)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 43 | 0.08 | 0.15 | 46% | `█████████           ` |
| 0.1–0.2 | 502 | 0.15 | 0.21 | 49% | `██████████          ` |
| 0.2–0.3 | 490 | 0.24 | 0.31 | 61% | `████████████        ` |
| 0.3–0.4 | 315 | 0.34 | 0.41 | 77% | `███████████████     ` |
| 0.4–0.5 | 196 | 0.44 | 0.50 | 80% | `████████████████    ` |
| 0.5–0.6 | 143 | 0.54 | 0.59 | 84% | `█████████████████   ` |
| 0.6–0.7 | 94 | 0.64 | 0.69 | 87% | `█████████████████   ` |
| 0.7–0.8 | 62 | 0.74 | 0.77 | 90% | `██████████████████  ` |
| 0.8–0.9 | 26 | 0.85 | 0.86 | 92% | `██████████████████  ` |
| 0.9–1.0 | 13 | 0.94 | 0.95 | 92% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it7_jev-latest_20261016_202121)

- CLI: `jev-agent` jev_agent.py v2 · server commit `dbda7cc` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:21:21 · ended 2026-10-16T20:26:58 · active 0:05 h · wall 0:05 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 732 · reloads 0 · black-outs 0 · in-game playtime 12:03:46 · Pokédex 6 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.8M / 0.0M / 481k · cost $0.12 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 30 | 8/84 | 53 | 50 | 71 | 57 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 20 | 49/60 | 31 | 32 | 37 | 45 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 39 | 6:53:09 | reached: Mt. Moon 1F |
| 0:01 | 1763 | 8:30:13 | reached: Route 4 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 5.6 min, longest 6 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:21:21 | 6 | exited | 6001 | 2.8M / 0.0M / 481k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2947 (asked Jev 2345, forced by code 602, labelled 2345) · models jev-1.13.0 · input tokens 2776061 · Jev $0.1166
- Jev latency mean 86 ms · p50 77 · p95 144 · max 521
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 7
- Planner calls 0 ($0.0000, errors 0) · objective changes 7 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 357 | 83% | 0.56 |
| faint_switch | 3 | 100% | 0.79 |
| overworld | 1954 | 55% | 0.33 |
| prompt | 31 | 71% | 0.54 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1646)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 25 | 0.08 | 0.17 | 56% | `███████████         ` |
| 0.1–0.2 | 333 | 0.15 | 0.23 | 44% | `█████████           ` |
| 0.2–0.3 | 622 | 0.25 | 0.32 | 46% | `█████████           ` |
| 0.3–0.4 | 556 | 0.34 | 0.40 | 56% | `███████████         ` |
| 0.4–0.5 | 309 | 0.44 | 0.50 | 65% | `█████████████       ` |
| 0.5–0.6 | 206 | 0.54 | 0.59 | 81% | `████████████████    ` |
| 0.6–0.7 | 121 | 0.64 | 0.69 | 88% | `██████████████████  ` |
| 0.7–0.8 | 109 | 0.74 | 0.77 | 94% | `███████████████████ ` |
| 0.8–0.9 | 50 | 0.84 | 0.86 | 92% | `██████████████████  ` |
| 0.9–1.0 | 14 | 0.94 | 0.94 | 93% | `███████████████████ ` |

### jev-solo: jev-latest (jev-solo_mt-moon_it8_jev-latest_20261016_203120)

- CLI: `jev-agent` jev_agent.py v2 · server commit `9646940` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:31:20 · ended 2026-10-16T20:35:53 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 839 · reloads 0 · black-outs 0 · in-game playtime 12:30:46 · Pokédex 6 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.0M / 0.0M / 329k · cost $0.08 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 32 | 90/90 | 57 | 54 | 76 | 61 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 22 | 66/66 | 34 | 36 | 41 | 50 | Supersonic, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 9 | 6:51:04 | reached: Route 4 |
| 0:00 | 14 | 6:51:06 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 4.5 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:31:20 | 5 | exited | 6001 | 2.0M / 0.0M / 329k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2487 (asked Jev 1733, forced by code 754, labelled 1733) · models jev-1.13.0 · input tokens 2021006 · Jev $0.0849
- Jev latency mean 90 ms · p50 80 · p95 153 · max 449
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 8
- Planner calls 0 ($0.0000, errors 0) · objective changes 11 · objectives Jev marked done 0 · final objective: Your team is weak (29% HP): heal at a Poké Center (walk in, talk to the nurse, answer YES).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 468 | 81% | 0.59 |
| faint_switch | 6 | 83% | 0.65 |
| overworld | 1222 | 81% | 0.39 |
| prompt | 37 | 76% | 0.58 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2963)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 16 | 0.08 | 0.24 | 50% | `██████████          ` |
| 0.1–0.2 | 171 | 0.16 | 0.25 | 62% | `████████████        ` |
| 0.2–0.3 | 339 | 0.25 | 0.33 | 74% | `███████████████     ` |
| 0.3–0.4 | 365 | 0.34 | 0.42 | 78% | `████████████████    ` |
| 0.4–0.5 | 199 | 0.45 | 0.52 | 82% | `████████████████    ` |
| 0.5–0.6 | 170 | 0.55 | 0.60 | 84% | `█████████████████   ` |
| 0.6–0.7 | 165 | 0.64 | 0.69 | 93% | `███████████████████ ` |
| 0.7–0.8 | 147 | 0.74 | 0.78 | 95% | `███████████████████ ` |
| 0.8–0.9 | 117 | 0.84 | 0.87 | 92% | `██████████████████  ` |
| 0.9–1.0 | 44 | 0.93 | 0.94 | 100% | `████████████████████` |

### jev-solo: jev-latest (jev-solo_mt-moon_it9_jev-latest_20261016_203736)

- CLI: `jev-agent` jev_agent.py v2 · server commit `fe40de0` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:37:36 · ended 2026-10-16T20:40:53 · active 0:03 h · wall 0:03 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6000 · images 485 · reloads 1 · black-outs 0 · in-game playtime 9:26:29 · Pokédex 6 owned · maps visited 5
- Tokens uncached in / cache reads / out: 1.6M / 0.0M / 292k · cost $0.07 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charmeleon | 27 | 71/76 | 47 | 44 | 63 | 51 | Rage, Growl, Ember, Leer |
| 2 | Butterfree | 19 | 58/58 | 30 | 31 | 35 | 43 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 30/30 | 15 | 14 | 16 | 13 | Gust |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 9 | 6:51:04 | reached: Route 4 |
| 0:00 | 14 | 6:51:06 | reached: Mt. Moon 1F |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 3.3 min, longest 3 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:37:36 | 3 | exited | 6001 | 1.6M / 0.0M / 292k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2086 (asked Jev 1351, forced by code 735, labelled 1351) · models jev-1.13.0 · input tokens 1635654 · Jev $0.0687
- Jev latency mean 82 ms · p50 74 · p95 142 · max 411
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 9
- Planner calls 0 ($0.0000, errors 0) · objective changes 9 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 250 | 78% | 0.57 |
| faint_switch | 5 | 40% | 0.48 |
| overworld | 1089 | 79% | 0.32 |
| prompt | 7 | 100% | 0.63 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.3486)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 29 | 0.07 | 0.20 | 52% | `██████████          ` |
| 0.1–0.2 | 254 | 0.15 | 0.24 | 61% | `████████████        ` |
| 0.2–0.3 | 341 | 0.24 | 0.32 | 76% | `███████████████     ` |
| 0.3–0.4 | 221 | 0.34 | 0.41 | 80% | `████████████████    ` |
| 0.4–0.5 | 162 | 0.44 | 0.51 | 84% | `█████████████████   ` |
| 0.5–0.6 | 128 | 0.54 | 0.60 | 89% | `██████████████████  ` |
| 0.6–0.7 | 96 | 0.64 | 0.69 | 94% | `███████████████████ ` |
| 0.7–0.8 | 72 | 0.74 | 0.77 | 94% | `███████████████████ ` |
| 0.8–0.9 | 38 | 0.84 | 0.86 | 100% | `████████████████████` |
| 0.9–1.0 | 10 | 0.92 | 0.93 | 90% | `██████████████████  ` |

### jev-solo: jev-latest (jev-solo-rommap_mt-moon_it7_jev-latest_20261016_201251)

- CLI: `jev-agent` jev_agent.py v2 · server commit `dbda7cc` · prompt `49106d19e201a25e`
- Started 2026-10-16T20:12:51 · ended 2026-10-16T20:21:20 · active 0:08 h · wall 0:08 h · paused 0:00 h · exit: **budget_calls**
- Tool calls 6001 · images 1623 · reloads 0 · black-outs 0 · in-game playtime 16:20:06 · Pokédex 8 owned · maps visited 5
- Tokens uncached in / cache reads / out: 2.2M / 0.0M / 297k · cost $0.09 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | Charizard | 36 | 116/116 | 80 | 77 | 100 | 85 | Slash, Growl, Ember, Leer |
| 2 | Butterfree | 24 | 69/71 | 38 | 39 | 44 | 54 | Sleep Powder, String Shot, Confusion, PoisonPowder |
| 3 | Pidgey | 10 | 29/30 | 15 | 14 | 16 | 13 | Gust |
| 4 | AAAAAAAAAA (Zubat) | 10 | 5/29 | 14 | 12 | 16 | 16 | Leech Life, Supersonic |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:03 | 985 | 8:27:37 | reached: Route 4 |
| 0:03 | 1039 | 8:30:29 | reached: Mt. Moon 1F |
| 0:07 | 5169 | 15:03:04 | obtained: Zubat |
| 0:08 | 5780 | 15:58:13 | evolved: Charmeleon → Charizard |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 8.5 min, longest 8 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T20:12:51 | 8 | exited | 6002 | 2.2M / 0.0M / 297k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 3357 (asked Jev 1929, forced by code 1428, labelled 1929) · models jev-1.13.0 · input tokens 2200868 · Jev $0.0924
- Jev latency mean 88 ms · p50 80 · p95 148 · max 434
- Fallbacks: none (variant without a safety net)
- Segment mt-moon from state `f9707b75ecb54c8a` to `reached: Cerulean City` · iteration 7
- Planner calls 0 ($0.0000, errors 0) · objective changes 16 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 834 | 85% | 0.56 |
| faint_switch | 6 | 100% | 0.84 |
| overworld | 1014 | 80% | 0.68 |
| prompt | 75 | 64% | 0.57 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.183)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 5 | 0.06 | 0.31 | 100% | `████████████████████` |
| 0.1–0.2 | 22 | 0.17 | 0.33 | 77% | `███████████████     ` |
| 0.2–0.3 | 84 | 0.26 | 0.38 | 69% | `██████████████      ` |
| 0.3–0.4 | 193 | 0.35 | 0.44 | 79% | `████████████████    ` |
| 0.4–0.5 | 237 | 0.45 | 0.53 | 85% | `█████████████████   ` |
| 0.5–0.6 | 278 | 0.55 | 0.61 | 86% | `█████████████████   ` |
| 0.6–0.7 | 323 | 0.65 | 0.69 | 89% | `██████████████████  ` |
| 0.7–0.8 | 348 | 0.75 | 0.78 | 78% | `████████████████    ` |
| 0.8–0.9 | 348 | 0.84 | 0.86 | 77% | `███████████████     ` |
| 0.9–1.0 | 91 | 0.93 | 0.94 | 86% | `█████████████████   ` |

### jev-solo: jev-latest (jev-solo_it83_jev-latest_20261020_025204)

- CLI: `jev-agent` jev_agent.py v2 · server commit `63f38e2` · prompt `49106d19e201a25e`
- Started 2026-10-20T02:52:04 · ended 2026-10-20T03:02:07 · active 0:09 h · wall 0:10 h · paused 0:00 h · exit: **manual**
- Tool calls 7870 · images 717 · reloads 1 · black-outs 0 · in-game playtime 3:30:56 · Pokédex 3 owned · maps visited 32
- Tokens uncached in / cache reads / out: 2.4M / 0.0M / 484k · cost $0.10 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 23 | 61/63 | 40 | 36 | 48 | 39 | Scratch, Growl, Ember, Leer |
| 2 | Magikarp | 5 | 17/17 | 7 | 12 | 13 | 8 | Splash |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 88 | 0:00:17 | reached: Pallet Town |
| 0:00 | 125 | 0:02:18 | obtained: Charmander |
| 0:00 | 125 | 0:02:18 | starter: Charmander |
| 0:00 | 153 | 0:04:15 | reached: Route 1 |
| 0:00 | 164 | 0:05:11 | reached: Viridian City |
| 0:00 | 319 | 0:12:44 | reached: Route 2 |
| 0:00 | 422 | 0:19:22 | reached: Pewter City |
| 0:01 | 2676 | 1:17:43 | evolved: Charmander → Charmeleon |
| 0:02 | 4201 | 1:55:51 | badge: Boulder |
| 0:02 | 4226 | 1:56:46 | reached: Route 3 |
| 0:02 | 4296 | 2:03:50 | reached: Route 4 |
| 0:02 | 4300 | 2:03:59 | reached: Mt. Moon 1F |
| 0:02 | 4740 | 2:23:12 | obtained: Magikarp |
| 0:03 | 4896 | 2:27:58 | reached: Route 22 |
| 0:03 | 4914 | 2:28:52 | reached: Route 23 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 exited; median 10.0 min, longest 10 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-20T02:52:04 | 10 | exited | 7870 | 2.4M / 0.0M / 484k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2673 (asked Jev 2134, forced by code 539, labelled 2134) · models jev-1.13.0 · input tokens 2445617 · Jev $0.1027
- Jev latency mean 78 ms · p50 59 · p95 171 · max 2399
- Fallbacks: none (variant without a safety net)
- Iteration 83
- Planner calls 0 ($0.0000, errors 0) · objective changes 32 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 160 | 95% | 0.69 |
| intro | 51 | 53% | 0.40 |
| overworld | 1841 | 55% | 0.49 |
| prompt | 82 | 52% | 0.46 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1801)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 42 | 0.08 | 0.17 | 48% | `██████████          ` |
| 0.1–0.2 | 315 | 0.15 | 0.22 | 48% | `██████████          ` |
| 0.2–0.3 | 354 | 0.24 | 0.32 | 53% | `███████████         ` |
| 0.3–0.4 | 299 | 0.34 | 0.42 | 56% | `███████████         ` |
| 0.4–0.5 | 202 | 0.44 | 0.50 | 52% | `██████████          ` |
| 0.5–0.6 | 161 | 0.54 | 0.60 | 58% | `████████████        ` |
| 0.6–0.7 | 157 | 0.64 | 0.69 | 66% | `█████████████       ` |
| 0.7–0.8 | 112 | 0.74 | 0.78 | 80% | `████████████████    ` |
| 0.8–0.9 | 106 | 0.85 | 0.87 | 88% | `██████████████████  ` |
| 0.9–1.0 | 386 | 0.97 | 0.97 | 56% | `███████████         ` |

### jev-solo: jev-latest (jev-solo_it36_jev-latest_20261017_022736)

- CLI: `jev-agent` jev_agent.py v2 · server commit `b7513c5` · prompt `49106d19e201a25e`
- Started 2026-10-17T02:27:36 · ended 2026-10-17T03:31:21 · active 1:03 h · wall 1:03 h · paused 0:00 h · exit: **stuck**
- Tool calls 50797 · images 7429 · reloads 40 · black-outs 0 · in-game playtime 6:59:38 · Pokédex 2 owned · maps visited 29
- Tokens uncached in / cache reads / out: 22.4M / 0.0M / 4217k · cost $0.94 · chunks 2

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 20 | 44/56 | 34 | 36 | 41 | 35 | Scratch, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 96 | 0:00:18 | reached: Pallet Town |
| 0:00 | 134 | 0:02:20 | obtained: Charmander |
| 0:00 | 134 | 0:02:20 | starter: Charmander |
| 0:00 | 210 | 0:05:29 | reached: Route 1 |
| 0:00 | 227 | 0:07:03 | reached: Viridian City |
| 0:02 | 2603 | 1:36:34 | reached: Route 2 |
| 0:02 | 2632 | 1:37:36 | reached: Route 22 |
| 0:39 | 35567 | 5:21:37 | reached: Pewter City |
| 0:39 | 35622 | 5:25:25 | evolved: Charmander → Charmeleon |
| 0:39 | 35633 | 5:27:40 | badge: Boulder |
| 0:39 | 35649 | 5:28:31 | reached: Route 3 |
| 0:39 | 35863 | 5:39:19 | reached: Route 4 |
| 0:39 | 35867 | 5:39:28 | reached: Mt. Moon 1F |
| 0:39 | 35935 | 5:43:02 | reached: Route 23 |

**CLI chunks:** 2 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 rotate, 1 stuck; median 60.0 min, longest 60 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-17T02:27:36 | 60 | rotate | 48975 | 21.5M / 0.0M / 4043k |
| 2 | 2026-10-17T03:27:40 | 4 | stuck | 1821 | 0.9M / 0.0M / 174k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 23256 (asked Jev 21816, forced by code 1440, labelled 21816) · models jev-1.13.0 · input tokens 22372586 · Jev $0.9396
- Jev latency mean 86 ms · p50 75 · p95 154 · max 899
- Fallbacks: none (variant without a safety net)
- Iteration 36
- Planner calls 0 ($0.0000, errors 0) · objective changes 33 · objectives Jev marked done 0 · final objective: Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows which ladder leads on); beat trainers who block the way.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 462 | 96% | 0.58 |
| intro | 51 | 51% | 0.40 |
| overworld | 21221 | 43% | 0.29 |
| prompt | 82 | 58% | 0.58 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1916)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 1067 | 0.08 | 0.19 | 47% | `█████████           ` |
| 0.1–0.2 | 7110 | 0.15 | 0.23 | 47% | `█████████           ` |
| 0.2–0.3 | 5230 | 0.24 | 0.33 | 46% | `█████████           ` |
| 0.3–0.4 | 3116 | 0.34 | 0.43 | 41% | `████████            ` |
| 0.4–0.5 | 1982 | 0.44 | 0.54 | 38% | `████████            ` |
| 0.5–0.6 | 1255 | 0.54 | 0.63 | 44% | `█████████           ` |
| 0.6–0.7 | 882 | 0.64 | 0.72 | 43% | `█████████           ` |
| 0.7–0.8 | 656 | 0.74 | 0.81 | 37% | `███████             ` |
| 0.8–0.9 | 398 | 0.84 | 0.88 | 31% | `██████              ` |
| 0.9–1.0 | 120 | 0.94 | 0.96 | 45% | `█████████           ` |

### jev-solo: jev-latest (jev-solo_power-on_it23_jev-latest_20261016_220833)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5b2aa03` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:08:33 · ended 2026-10-16T22:10:09 · active 0:01 h · wall 0:01 h · paused 0:00 h · exit: **segment_goal**
- Tool calls 2187 · images 301 · reloads 0 · black-outs 0 · in-game playtime 1:30:45 · Pokédex 2 owned · maps visited 16
- Tokens uncached in / cache reads / out: 0.6M / 0.0M / 91k · cost $0.02 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmeleon) | 19 | 57/57 | 35 | 33 | 43 | 36 | Scratch, Growl, Ember, Leer |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 73 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:11 | reached: Pallet Town |
| 0:00 | 116 | 0:02:00 | obtained: Charmander |
| 0:00 | 116 | 0:02:00 | starter: Charmander |
| 0:00 | 137 | 0:03:50 | reached: Route 1 |
| 0:00 | 148 | 0:04:38 | reached: Viridian City |
| 0:00 | 226 | 0:08:38 | reached: Route 2 |
| 0:00 | 627 | 0:25:42 | reached: Pewter City |
| 0:01 | 1748 | 1:11:02 | evolved: Charmander → Charmeleon |
| 0:01 | 2121 | 1:26:00 | badge: Boulder |
| 0:01 | 2129 | 1:26:21 | reached: Route 3 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 segment_goal; median 1.6 min, longest 2 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:08:33 | 2 | segment_goal | 2185 | 0.6M / 0.0M / 91k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 796 (asked Jev 567, forced by code 229, labelled 567) · models jev-1.13.0 · input tokens 569345 · Jev $0.0239
- Jev latency mean 106 ms · p50 88 · p95 245 · max 581
- Fallbacks: none (variant without a safety net)
- Segment power-on from state `None` to `badge: Boulder` · iteration 23
- Planner calls 0 ($0.0000, errors 0) · objective changes 23 · objectives Jev marked done 0 · final objective: Go east along Route 3 to Mt. Moon (the 'follow the map route' option knows the way).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 116 | 99% | 0.75 |
| intro | 53 | 45% | 0.43 |
| overworld | 353 | 81% | 0.61 |
| prompt | 45 | 24% | 0.61 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1939)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 1 | 0.07 | 0.16 | 100% | `████████████████████` |
| 0.1–0.2 | 45 | 0.16 | 0.27 | 87% | `█████████████████   ` |
| 0.2–0.3 | 77 | 0.24 | 0.35 | 82% | `████████████████    ` |
| 0.3–0.4 | 50 | 0.34 | 0.45 | 68% | `██████████████      ` |
| 0.4–0.5 | 35 | 0.44 | 0.55 | 51% | `██████████          ` |
| 0.5–0.6 | 34 | 0.55 | 0.61 | 62% | `████████████        ` |
| 0.6–0.7 | 47 | 0.64 | 0.70 | 72% | `██████████████      ` |
| 0.7–0.8 | 51 | 0.75 | 0.79 | 72% | `██████████████      ` |
| 0.8–0.9 | 93 | 0.84 | 0.87 | 91% | `██████████████████  ` |
| 0.9–1.0 | 134 | 0.96 | 0.97 | 78% | `████████████████    ` |

### jev-solo: jev-latest (jev-solo_it69_jev-latest_20261018_212807)

- CLI: `jev-agent` jev_agent.py v2 · server commit `5749dda` · prompt `49106d19e201a25e`
- Started 2026-10-18T21:28:07 · ended 2026-10-18T21:53:10 · active 0:24 h · wall 0:25 h · paused 0:00 h · exit: **stuck**
- Tool calls 22996 · images 2300 · reloads 16 · black-outs 0 · in-game playtime 1:35:05 · Pokédex 1 owned · maps visited 11
- Tokens uncached in / cache reads / out: 10.7M / 0.0M / 2511k · cost $0.45 · chunks 1

**Final team**

| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |
|---|---|---|---|---|---|---|---|---|
| 1 | AAAAAAAAAA (Charmander) | 10 | 11/30 | 17 | 15 | 19 | 18 | Scratch, Growl, Ember |

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 86 | 0:00:16 | reached: Pallet Town |
| 0:00 | 131 | 0:02:33 | obtained: Charmander |
| 0:00 | 131 | 0:02:33 | starter: Charmander |
| 0:00 | 160 | 0:04:49 | reached: Route 1 |
| 0:00 | 165 | 0:05:06 | reached: Viridian City |
| 0:00 | 282 | 0:10:31 | reached: Route 2 |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 25.1 min, longest 25 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-18T21:28:07 | 25 | stuck | 22996 | 10.7M / 0.0M / 2511k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 11278 (asked Jev 10100, forced by code 1178, labelled 10100) · models jev-1.13.0 · input tokens 10673784 · Jev $0.4483
- Jev latency mean 87 ms · p50 76 · p95 159 · max 479
- Fallbacks: none (variant without a safety net)
- Iteration 69
- Planner calls 0 ($0.0000, errors 0) · objective changes 24 · objectives Jev marked done 0 · final objective: Find the way through Viridian Forest to Pewter City.

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| battle | 69 | 100% | 0.57 |
| intro | 51 | 53% | 0.40 |
| overworld | 9937 | 62% | 0.29 |
| prompt | 43 | 28% | 0.57 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.2985)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 265 | 0.06 | 0.37 | 26% | `█████               ` |
| 0.1–0.2 | 3095 | 0.15 | 0.24 | 58% | `████████████        ` |
| 0.2–0.3 | 3387 | 0.24 | 0.31 | 64% | `█████████████       ` |
| 0.3–0.4 | 1382 | 0.34 | 0.41 | 71% | `██████████████      ` |
| 0.4–0.5 | 584 | 0.44 | 0.50 | 81% | `████████████████    ` |
| 0.5–0.6 | 330 | 0.54 | 0.59 | 75% | `███████████████     ` |
| 0.6–0.7 | 397 | 0.65 | 0.68 | 47% | `█████████           ` |
| 0.7–0.8 | 403 | 0.74 | 0.76 | 52% | `██████████          ` |
| 0.8–0.9 | 214 | 0.83 | 0.84 | 76% | `███████████████     ` |
| 0.9–1.0 | 43 | 0.93 | 0.93 | 86% | `█████████████████   ` |

### jev-solo: jev-latest (jev-solo_power-on_it22_jev-latest_20261016_220257)

- CLI: `jev-agent` jev_agent.py v2 · server commit `26f6373` · prompt `49106d19e201a25e`
- Started 2026-10-16T22:02:57 · ended 2026-10-16T22:07:47 · active 0:04 h · wall 0:04 h · paused 0:00 h · exit: **stuck**
- Tool calls 4083 · images 985 · reloads 9 · black-outs 0 · in-game playtime 0:41:34 · Pokédex 0 owned · maps visited 4
- Tokens uncached in / cache reads / out: 2.7M / 0.0M / 602k · cost $0.11 · chunks 1

**Final team**: none

**Milestones** (first occurrence; time is active server time)

| Time | Calls | Playtime | Milestone |
|---|---|---|---|
| 0:00 | 71 | 0:00:00 | game started |
| 0:00 | 84 | 0:00:10 | reached: Pallet Town |

**CLI chunks:** 1 (the CLI is restarted whenever the model ends its turn, a chunk rotates, stalls or is rate-limited): 1 stuck; median 4.8 min, longest 5 min.

<details><summary>Chunks</summary>

| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |
|---|---|---|---|---|---|
| 1 | 2026-10-16T22:02:57 | 5 | stuck | 4083 | 2.7M / 0.0M / 602k |

</details>

**Jev (solo)** — The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks ("stuck?", "objective done?" where code cannot see a story event).

- Decisions 2074 (asked Jev 2019, forced by code 55, labelled 2019) · models jev-1.13.0 · input tokens 2687063 · Jev $0.1129
- Jev latency mean 102 ms · p50 85 · p95 211 · max 2129
- Fallbacks: none (variant without a safety net)
- Segment power-on from state `None` to `badge: Boulder` · iteration 22
- Planner calls 0 ($0.0000, errors 0) · objective changes 2 · objectives Jev marked done 0 · final objective: Leave the house, walk north out of Pallet Town; Oak takes you to his lab: choose a starter Pokémon (talk to one of the Poké Balls on the table, answer YES).

| Decision kind | Labelled | Correct | Mean confidence |
|---|---|---|---|
| intro | 51 | 51% | 0.43 |
| overworld | 1949 | 26% | 0.24 |
| prompt | 19 | 0% | 0.55 |

**Confidence vs. correctness** ("correct" = the chosen action was accepted and did what it is for: a move that hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed the screen; ECE against p(choice) = 0.1869)

| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |
|---|---|---|---|---|---|
| 0.0–0.1 | 79 | 0.08 | 0.14 | 40% | `████████            ` |
| 0.1–0.2 | 906 | 0.14 | 0.20 | 34% | `███████             ` |
| 0.2–0.3 | 514 | 0.23 | 0.28 | 22% | `████                ` |
| 0.3–0.4 | 226 | 0.34 | 0.39 | 12% | `██                  ` |
| 0.4–0.5 | 118 | 0.44 | 0.48 | 8% | `██                  ` |
| 0.5–0.6 | 76 | 0.54 | 0.58 | 10% | `██                  ` |
| 0.6–0.7 | 53 | 0.64 | 0.68 | 15% | `███                 ` |
| 0.7–0.8 | 26 | 0.74 | 0.77 | 35% | `███████             ` |
| 0.8–0.9 | 19 | 0.84 | 0.85 | 58% | `████████████        ` |
| 0.9–1.0 | 2 | 0.92 | 0.92 | 50% | `██████████          ` |
