# Claude Context: Game Boy MCP Player

## What this is

An MCP server (`server.py`) that lets an AI agent play **any Game Boy ROM** through PyBoy, with a
rich profile for Pokémon Red/Blue/Yellow and automatic benchmark metrics. It was rebuilt in
September 2026 around two goals: **speed** (batched headless emulation) and **token efficiency**
(few high-level tools, compact text results, screenshots only when the screen changed, dialogue and
menus decoded from VRAM as text). It has been played from power-on to the Boulder Badge by a
scripted agent on four RNG seeds with zero anomalies (`examples/reference_run.py`).

## Files

| File | Purpose |
|---|---|
| `server.py` | FastMCP server: 14 tools, agent guide in the `instructions` field, CLI flags |
| `emulator.py` | `Emulator`: PyBoy wrapper, button-script parser, walk executor (steps, pathfinding, cross-map hops, `on_battle`), screenshots with change detection, atomic save states, autosave, memory access, per-action bookkeeping |
| `metrics.py` | `MetricsTracker`: real/emulated time, tool-call and image counts, milestones, JSON + text reports |
| `games/__init__.py` | profile registry; `detect_profile()` matches the cartridge title |
| `games/base.py` | `GameProfile` interface (generic profile) and `decode_visible_tilemap()` |
| `games/pokemon_gen1.py` | Red/Blue/Yellow: state sections, screen text, full-map decode, pathfinding, world graph, battle/talk/shop/manage helpers, hints, milestones |
| `games/gen1_data.py` | verified WRAM addresses, charmap, species/move/item/map tables, ledge tiles |
| `games/pyboy_wrapped.py` | score/lives for games PyBoy has wrappers for (Tetris, Mario Land, Kirby, Pinball) |
| `examples/reference_run.py` | scripted agent: power-on → Brock with the public tools; logs every odd reply (`ODD:`) |
| `examples/extended_run.py` | scripted agent: after-Brock state → Mt. Moon → Cerulean → Misty (needs a local `saves/<rom>/after-brock.state`) |
| `examples/_agentlib.py` | `ScriptedAgent`: tool wrappers, battle resolver, travel/heal helpers shared by the scripted runs |
| `bench/run.py` | benchmark harness: launches Claude Code / Codex headless in resumable chunks, budgets, rate-limit pauses, writes `results/<run>.json` |
| `bench/report.py` | derives per-run summaries and renders `RESULTS.md` from `results/*.json` |
| `bench/stream.py`, `bench/providers.py` | CLI event-stream parsers (tested on captured streams) and per-CLI command builders |
| `tests/` | pytest (57): parser unit tests, ROM-driven gameplay tests, opening replay, MCP stdio round-trip, harness parsers/report |
| `test_emulator.py` | CLI smoke test (`--play-intro` plays to the overworld) |
| `.backup-original/` | the pre-rewrite code, kept for reference (gitignored) |

Docs: `README.md`, `QUICKSTART.md`, `AGENT_GUIDE.md`, `BENCHMARKING.md`.

## Running

```bash
source venv/bin/activate            # venv has pyboy 2.6, mcp 1.24, pillow, numpy, pytest, pyflakes
python -m pytest tests -q           # ~5 s with a Pokémon Red ROM in the project root
python examples/reference_run.py Pokemon-Red_Version.gb [seed]   # ~35 s; expect "0 oddities" and 1 badge
python test_emulator.py Pokemon-Red_Version.gb --play-intro
python server.py --rom Pokemon-Red_Version.gb --ai-model NAME [--resume]
python examples/extended_run.py Pokemon-Red_Version.gb       # ~15 s from the local after-brock state; expect "0 oddities"
python bench/run.py --provider claude --model claude-haiku-4-5-20251001 --smoke   # harness checklist (uses the real CLI)
python bench/run.py --provider codex --model gpt-5.6-sol      # a full 12 h / 20k-call benchmark run -> results/, RESULTS.md
```

Clients must run the interpreter that has the dependencies (use the venv path in the config).
`stdout` is the MCP transport: never `print()` in server code; use `logging` (stderr).
Scripts that call `Emulator.stop()` write `<rom>.ram` next to the ROM (PyBoy battery save); use a
ROM copy for experiments, as the reference run does. The tests pick NEW GAME even if a battery save
exists, but keep the project ROM free of a `.ram` file for reproducible runs.

## Tool set (keep it small)

`press`, `walk`, `battle` (incl. `auto`, `bait`, `rock`), `talk`, `shop`, `manage` (`lead`, `swap`, `use`,
`field`, `save`), `wait`, `screen`, `state`, `save_state`, `load_state`, `reset_game`, `memory`, `metrics`
(incl. `note`). Tool schema JSON stays under 10 KB (enforced by a
test, currently ~6.5 KB) and the agent guide under 1.5 KB. If you add a tool, ask whether it could
be a parameter of an existing one instead.

`battle` (incl. `auto`), `talk`, `shop`, `manage` live in the Pokémon profile (`battle_action`,
`battle_auto`, `talk`, `shop`, `manage`) and drive the game through `emu.press(..., settle=1)` plus
screen-text parsing (`▶` cursor, `TYPE/`, `FIGHT`/`RUN` rows, `dialog_text()` = rows 12-17).

Action tools return: head line, status line, `EVENT:` milestones, screen text (or the map view
after a walk), `hint:` (from `profile.hint()`), then an image only if the screen hash changed.

## Key technical facts (verified against the ROM)

* PyBoy `tick(n, render=False)` runs ~30k fps; render once before reading the screen.
* Walking: 16 frames per tile, ~2 extra frames to turn; input is ignored ~70 frames after a warp;
  ledge jumps move 2 cells and take ~3x a step.
* Pokémon text lives in the window tilemap (0x9C00) when LCDC bit 5 is set and WY = 0; tile IDs
  equal character codes. Decode only when the font is loaded (tile 0x80 == `FONT_A_TILE`),
  otherwise the title screen produces fake text.
* Play time: hours 0xDA41, minutes 0xDA43, seconds 0xDA44.
* `started()` = sprite table 0xC100 non-zero **and** map width/height non-zero.
* Warp dest 0xFF = "back to the last outdoor map" (`wLastMap` 0xD365).
* Full maps: block grid at 0xC6E8 (3-block border) + 16-byte block definitions in the tileset ROM
  bank (0xD52B/0xD52C) + walkable-tile list (0xD530); a metatile is walkable if its bottom-left
  tile is in that list. Grass tile 0xD535. Edge connections: bits at 0xD370, map ids at
  0xD371/0xD37C/0xD387/0xD392. One-way ledges (outdoor tileset 0): tiles 0x36/0x37 down, 0x27
  left, 0x0D/0x1D right (pokered `LedgeTiles`), drawn `v < >`, traversed by BFS as 2-cell moves.
* Every press is followed by `_settle()`: advance until the tilemaps stop changing and
  `profile.busy()` is false (cap 300 frames). `busy()` = a sound effect/jingle playing
  (0xC02A-0xC02D), a battle animation (in battle, no menu/cursor/▼), or a cutscene ignoring all
  input (`wJoyIgnore` 0xCD6B == 0xFF).
* Scripted scenes: `wJoyIgnore` non-zero (directions masked) while a cutscene controls the
  player; `talk()` waits through the silent walking parts, `walk` refuses with a hint.
* Map-edge connections: coordinates leave the map a few frames before the map id changes;
  `_walk_segment` waits for the new map (`profile.off_map`).
* Options 0xC1 (text FAST, animations OFF, battle style SET) are written to 0xD355 after every
  action unless `--no-fast-text`.
* Scripts (Oak's lab) briefly scribble on the Pokédex owned flags: a capture is only reported when
  the species is also in the party or the current PC box (0xDA80); a species that replaces another
  in the same slot is reported as an evolution.
* Pathfinding: Dijkstra on `full_map_cells()` (grass costs 4) with NPC tiles blocked; re-planned
  up to 3 times when "blocked". Building doors are solid tiles you walk *into*, so a solid warp
  tile is allowed only as the destination. Two-wide gate doorways often have one solid half:
  `_goto` retries the twin warp (`alternate_warps`). Arriving on a walkable warp tile takes one
  extra step off the map edge (`edge_direction`) or in the last direction.
* World graph: `snapshot()` records each visited map's warps, connections and `wLastMap` in
  `profile.world`; `_resolve_far` BFSes it for `walk("to <map>")`, one hop per iteration in
  `Emulator.walk`; `on_battle` wraps `_walk_once` and resolves wild battles with `run`/`auto`.
* After `battle`/`talk`/`shop`/`manage` the emulator settles and, if a battle just ended, waits
  60 frames so a black-out teleport has loaded the new map before the next call reads it.
* Battle helper: `_wait_menu` presses A through text while sampling the message box every 6
  frames (`_watch`), classifies `main` / `choose` / `prompt` / `over`, and backs out of optional
  lists with B. Prompts are only YES/NO cursors or "forgotten/Abandon/Which move" lists;
  "X learned Y!" is plain text.
* Brock strategy that works with a Charmander start: catch a Caterpie/Metapod in Viridian Forest,
  level it as lead (switch out when low) to Butterfree with Confusion (L12); Charmeleon's Ember
  does ¼ damage to Rock/Ground. A local `saves/Pokemon-Red_Version/after-brock.state` (gitignored,
  not in the repo) is that state if you have generated one.
* Species table is by *internal* index (Bulbasaur = 0x99); Pokédex bits are by national number.
* Hall of Fame counter is `0xD5A2` (`0xD5A0` is the current PC box number). Map ids come from the
  ROM's header table (`MapHeaderPointers` at ROM 0x01AE, banks at 0xC23D; a test checks the table):
  82 Rock Tunnel 1F, 83 Power Plant, 92 Vermilion Gym, 232 Rock Tunnel B1F, 233-236 Silph 9F-11F +
  elevator, 245/246/247 Lorelei/Bruno/Agatha, 113 Lance, 120 Champion, 118 Hall of Fame.
* `0xD700` = walk/bike/surf state (2 = surfing). Water tile `$14` (surfable in pokered's water
  tilesets), cut trees `$3D` (overworld) / `$50` (gym); `wTileInFrontOfPlayer` 0xCFC6. Cave/forest
  elevation steps are pokered's `TilePairCollisionsLand/Water` (tileset 17 and 3), applied by the pathfinder.
* Disable: `0xD06D` high nibble = the player's disabled move slot (1-4); `battle()` reports it and
  `fight`/`auto` skip it. Rage locks the user for the whole battle, so `auto` treats it as a status move.
* Pathfinding: other warps are never crossed en route; NPC sprites cost +40 instead of blocking
  (objects hidden by events keep their sprite slot); a cell that turns out solid while walking is
  remembered and the route re-planned. A "blocked" step waits while `wJoyIgnore` is set (a trainer who
  spotted the player is walking over) and reports "dialogue appeared" instead.
* Party menus remember their cursor: helpers read the `▶` row (on TM lists it sits on the entry's
  second row) instead of assuming the top. In-battle item use shows "Use item on which POKéMON?".
* Metrics: a session resumes from `metrics/<id>_checkpoint.json` when `--session-id` is reused; frames
  never rewind on `load_state` (reloads are milestones); the world graph persists in `saves/<rom>/world.json`.

## Adding a game

Subclass `GameProfile`, implement `status_line`, `state`, `sections`, `snapshot`, `milestones`,
optionally `position` (enables smart walking and door/battle detection), `screen_text`,
`find_path`, `resolve_target`, `battle_action`, `talk`, `shop`, `manage`, `hint`, `busy`,
`scripted`, `after_load`, `agent_hints`. Register a title regex in `games/__init__.py`. Generic
games can also pass `--charmap file.json` to decode text.

## Conventions

* Results are short. No JSON dumps with indentation, no marketing text in tool descriptions.
* Every emulator behavior change should have a test in `tests/test_gameplay.py`; anything that
  touches input timing, walking or battle parsing should also pass `tests/test_playthrough.py`
  and a `reference_run.py` with "0 oddities".
* `saves/`, `metrics/`, `screenshots/`, `bench/runs/`, ROMs and `.ram` files are runtime data, not source;
  `results/*.json` and the generated `RESULTS.md` are the published benchmark data.
* Commits: identity `Dst0rtr <135249234+Dst0rtr@users.noreply.github.com>`, no AI attribution lines.
