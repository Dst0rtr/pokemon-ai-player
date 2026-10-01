# Game Boy MCP Player

An MCP (Model Context Protocol) server that lets an AI agent play **any Game Boy game** through a
small, token-efficient set of tools, and records benchmark metrics while it plays.

Pokémon Red/Blue/Yellow get a built-in *game profile* that reads party, battle, map and dialogue
straight from memory, so the agent plays mostly from text instead of screenshots, and gets
high-level helpers (pathfinding, whole-battle turns, conversations, shops, party management).
Any other ROM works with the generic profile (button scripts, screenshots, save states, raw memory).

## Status

* Played from power-on to the Boulder Badge by a scripted reference agent using only the public
  tools, cleanly on four different RNG seeds (`examples/reference_run.py`, about 35 s of real time
  and 1,400 tool calls per run).
* A second scripted run (`examples/extended_run.py`) continues from the Boulder Badge through Mt. Moon
  to Cerulean City and Misty, covering caves, trainers, in-battle items, field moves and the world graph.
* 57 automated tests, including a replay of the game's opening, an MCP client round-trip and the
  benchmark harness's stream parsers.
* A public **benchmark**: agent CLIs (Claude Code, Codex) play from power-on toward the Champion with
  the same prompt and budgets; see [RESULTS.md](RESULTS.md) and [BENCHMARKING.md](BENCHMARKING.md).
* Save states are not included in the repository (they contain emulator memory derived from the
  ROM). Create your own with `save_state("after-brock")` at the post-Brock point and reload it with
  `load_state("after-brock")`.

## Why this version is fast and cheap

| | Before | Now |
|---|---|---|
| Tools exposed to the model | 15 low-level tools (about 1.2k tokens of schema, no guide) | 14 higher-level tools (about 1.6k tokens of schema plus a 320-token agent guide) |
| Actions per call | 1 button, or a JSON array | scripts and goals: `press("A*4 DOWN A")`, `walk("to Pewter City")`, `battle("auto")`, `talk()` |
| Seeing the result | separate screenshot call after every action (one extra model turn each) | every action returns status, on-screen text, a hint when the game asks something, and an image only if the screen changed |
| Reading dialogue / menus | image only | decoded from VRAM as text (Pokémon) |
| Navigation | blind button holds | full text map of every area (walls, grass, doors, ledges, NPCs, exits), pathfinding on the map and across visited maps, stops at doors, battles, dialogue |
| Battles, shops, NPCs | 5-10 blind presses each | one call each, stopping only at real questions |
| Metrics | manual `update_metrics` calls | automatic: badges, captures, evolutions, landmarks, black-outs, tool calls, images sent |
| Emulation | 1 frame per tick call | batched ticks, render only for screenshots (about 30,000 fps headless) |
| Resilience | none | atomic autosave every 20 actions, `--resume`, named save states |

## Quick start

No ROM is included and none will be accepted into the repository. Use a cartridge dump you legally
own; the `.gitignore` excludes `*.gb`, `*.gbc`, `*.ram`, `saves/`, `screenshots/` and `metrics/`.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python test_emulator.py path/to/game.gb                  # smoke test (add --play-intro for Pokémon)
python -m pytest tests                                    # full suite (needs a Pokémon Red/Blue ROM in the folder)
python examples/reference_run.py path/to/pokemon-red.gb   # scripted agent: power-on to Brock
```

Then point your MCP client at `server.py` (see [QUICKSTART.md](QUICKSTART.md)):

```json
{
  "mcpServers": {
    "gameboy": {
      "command": "/ABS/PATH/pokemon-ai-player/venv/bin/python",
      "args": ["/ABS/PATH/pokemon-ai-player/server.py", "--rom", "/ABS/PATH/game.gb", "--ai-model", "claude-fable-5-1"]
    }
  }
}
```

## Tools

| Tool | What it does |
|---|---|
| `press(buttons, screenshot=true)` | Button script: `A B START SELECT UP DOWN LEFT RIGHT`, `A*5` repeats, `UP:16` holds, `W60` waits. Each press waits for text and animations to finish |
| `walk(path, screenshot=true, on_battle="stop")` | Steps (`"up 5, right 3"`) or goals: `"to 23,25"`, `"to Viridian Mart"`, `"to north edge"`, `"to Pewter City"` (routes through maps you have visited). Stops when blocked, at doors, or when a battle/dialogue starts and says why. `on_battle="run"` or `"auto"` resolves wild encounters and keeps going |
| `battle(action, target)` | Pokémon: `fight` (move name or 1-4), `auto` (whole routine battle), `run`, `switch` (party number or name), `item` (item name, or `"Potion: Pidgey"`), `bait` / `rock` (Safari Zone). Reports messages and HP changes, marks moves locked by Disable; stops at YES/NO or learn-move prompts |
| `talk()` | Interact with what you face and read the whole conversation, including cutscenes; stops at any choice |
| `shop(item, qty)` | Pokémon: buy from a clerk by item name; reports money and bag |
| `manage(action, target, target2)` | Pokémon: `lead` (put a Pokémon first), `swap`, `use` (item, optional Pokémon; TMs/HMs with `"Charmander: Growl"` naming the move to forget), `field` (Cut / Surf / Strength / Flash / Fly / Dig / Teleport from the party menu), `save` (in-game save) |
| `wait(frames=60)` | Let the game run |
| `screen(mode="image"\|"text"\|"both", scale)` | Explicit look at the screen |
| `state(section)` | `summary`, `map` (whole area decoded from RAM), `nearby` (10x9 window), `party`, `battle`, `items`, `full` (Pokémon); score/lives for PyBoy-wrapped games |
| `save_state(slot)` / `load_state(slot)` | Emulator checkpoints; `load_state("list")` lists them; `autosave` is automatic |
| `reset_game(confirm=true)` | Power-cycle |
| `memory(action, address, length, values)` | Hex dump any RAM; writes need `--allow-memory-write` |
| `metrics(action, name)` | `report`, `milestone`, `note` (a reminder to yourself, shown in `report`), `start`, `checkpoint`, `finalize` |

Every action returns the same compact block: a status line (position, party, money, badges), `EVENT:`
lines for milestones, the decoded screen text (or the map after a walk), a `hint:` line whenever the
game is waiting for an answer, and a PNG only when the screen changed. The server also sends a short
agent guide as MCP instructions; [AGENT_GUIDE.md](AGENT_GUIDE.md) is the long version.

## Server options

```
python3 server.py --rom GAME.gb [--ai-model NAME] [--profile auto|generic|pokemon-gen1|pyboy-wrapper]
                  [--scale 1-4] [--resume] [--autosave-every N] [--no-fast-text]
                  [--no-screenshot-files] [--allow-memory-write] [--charmap map.json] [--data-dir DIR]
                  [--session-id ID] [--max-tool-calls N] [--max-real-seconds S] [--finalize-on-exit]
                  [--log-file FILE]
```

* `--resume` continues from `saves/<rom>/autosave.state`.
* `--no-fast-text` disables the Pokémon quality-of-life tweak (text speed FAST, battle animations OFF,
  battle style SET; identical to the in-game OPTION menu).
* `--charmap` lets the generic profile decode on-screen text for other games: a JSON object mapping
  tile IDs (hex strings) to characters.
* `--data-dir` puts `screenshots/`, `saves/` and `metrics/` somewhere other than next to `server.py`.
* `--session-id` continues one metrics session across launches (with `--resume`); `--max-tool-calls` /
  `--max-real-seconds` end a benchmark run cleanly (`BUDGET EXHAUSTED`); `--finalize-on-exit` writes the
  final report when the server stops.

## Layout

```
server.py               MCP entry point (FastMCP), tool definitions, agent guide
emulator.py             PyBoy wrapper: scripts, walking, pathfinding executor, screenshots, save states, memory
metrics.py              generic benchmark tracker
games/__init__.py       profile registry (matched on the ROM header title)
games/base.py           GameProfile interface + generic tilemap text decoder
games/pokemon_gen1.py   Red/Blue/Yellow profile: state, maps, routing, battle/talk/shop/manage helpers, milestones
games/gen1_data.py      verified addresses, charmap, species/move/item/map tables
games/pyboy_wrapped.py  Tetris / Super Mario Land / Kirby / Pinball via PyBoy wrappers
examples/reference_run.py  scripted agent that plays to Brock with the public tools (also a regression run)
examples/extended_run.py   scripted agent: Boulder Badge -> Mt. Moon -> Cerulean -> Misty
examples/_agentlib.py      helpers shared by the scripted agents
bench/                  benchmark harness: run.py (drives Claude Code / Codex headless), report.py (RESULTS.md)
results/                one JSON per published benchmark run; RESULTS.md is generated from them
tests/                  pytest suite: parsers, ROM-driven gameplay, opening replay, MCP round-trip, harness
```

Docs: [QUICKSTART.md](QUICKSTART.md), [AGENT_GUIDE.md](AGENT_GUIDE.md), [BENCHMARKING.md](BENCHMARKING.md),
[CLAUDE.md](CLAUDE.md) (maintainer notes and verified ROM facts).

## Adding a game profile

Subclass `games.base.GameProfile`, implement `status_line()`, `state()`, `snapshot()` and
`milestones()`, and optionally `position()` (enables smart walking), `screen_text()`, `find_path()`,
`battle_action()`, `talk()`, `shop()` and `manage()`. Register a cartridge-title regex in
`games/__init__.py`.

## Legal

No ROMs are included. Use only games you own.

## License

MIT, see `LICENSE`. Pokémon and Game Boy are trademarks of Nintendo; no ROM is included.
