# Codex Context: Game Boy MCP Player

## What this is

An MCP server (`server.py`) that lets an AI agent play **any Game Boy ROM** through PyBoy,
with a rich profile for Pokémon Red/Blue/Yellow and automatic benchmark metrics.
It was rebuilt in September 2026 around two goals: **speed** (batched headless emulation)
and **token efficiency** (few tools, compact text results, screenshots only when the screen changed,
dialogue/menus decoded from VRAM as text).

## Files

| File | Purpose |
|---|---|
| `server.py` | FastMCP server: 10 tools, agent guide in the `instructions` field, CLI flags |
| `emulator.py` | `Emulator` class: PyBoy wrapper, button-script parser, tile-accurate `walk`, screenshots with change detection, save states, autosave, memory access, per-action bookkeeping |
| `metrics.py` | `MetricsTracker`: real/emulated time, tool-call and image counts, milestones, JSON + text reports |
| `games/__init__.py` | profile registry; `detect_profile()` matches the cartridge title |
| `games/base.py` | `GameProfile` interface (generic profile) and `decode_visible_tilemap()` |
| `games/pokemon_gen1.py` | Red/Blue/Yellow: status line, party/battle/items/map sections, screen text, milestones |
| `games/gen1_data.py` | verified WRAM addresses, charmap, species/move/item/map tables |
| `games/pyboy_wrapped.py` | score/lives for games PyBoy has wrappers for (Tetris, Mario Land, Kirby, Pinball) |
| `tests/` | pytest (57): parser unit tests, ROM-driven gameplay tests, opening replay, MCP stdio round-trip, harness parsers/report |
| `test_emulator.py` | CLI smoke test (`--play-intro` plays to the overworld) |
| `.backup-original/` | the pre-rewrite code, kept for reference (gitignored) |

Docs: `README.md`, `QUICKSTART.md`, `AGENT_GUIDE.md`, `BENCHMARKING.md`.

## Running

```bash
source venv/bin/activate            # venv has pyboy 2.6, mcp 1.24, pillow, numpy, pytest
python -m pytest tests -q           # ~3 s with a Pokémon Red ROM in the project root
python test_emulator.py Pokemon-Red_Version.gb --play-intro
python server.py --rom Pokemon-Red_Version.gb --ai-model NAME [--resume]
python examples/extended_run.py Pokemon-Red_Version.gb       # ~15 s from the local after-brock state; expect "0 oddities"
python bench/run.py --provider claude --model claude-haiku-4-5-20251001 --smoke   # harness checklist (uses the real CLI)
python bench/run.py --provider codex --model gpt-5.6-sol      # a full 12 h / 20k-call benchmark run -> results/, RESULTS.md
```

Clients must run the interpreter that has the dependencies (use the venv path in the config).
`stdout` is the MCP transport: never `print()` in server code; use `logging` (stderr).

## Tool set (keep it small)

`press`, `walk`, `battle` (incl. `auto`, `bait`, `rock`), `talk`, `shop`, `manage` (`lead`, `swap`, `use`,
`field`, `save`), `wait`, `screen`, `state`, `save_state`, `load_state`, `reset_game`, `memory`, `metrics`
(incl. `note`). Tool schema JSON stays under 10 KB (enforced by a test) and the agent
guide under 1.5 KB. If you add a tool, ask whether it could be a parameter of an existing one instead.
`battle` (incl. `auto`), `talk`, `shop`, `manage` live in the Pokémon profile (`battle_action`, `battle_auto`, `talk`, `shop`, `manage`) and drive the game
through `emu.press(..., settle=1)` plus screen-text parsing (`▶` cursor, `TYPE/`, `FIGHT`/`RUN` rows).

Action tools return: `head` line, status line, `EVENT:` milestones, screen text (or the map when there
is no text), then an image only if the screen hash changed. `screenshot=false` suppresses the image.

## Key technical facts (verified against the ROM)

* PyBoy `tick(n, render=False)` runs ~30k fps; render once before reading the screen.
* Walking: 16 frames per tile, ~2 extra frames to turn; input is ignored ~70 frames after a warp.
* Pokémon text lives in the window tilemap (0x9C00) when LCDC bit 5 is set and WY = 0; tile IDs equal
  character codes. Decode only when the font is loaded (tile 0x80 == `FONT_A_TILE`), otherwise the title
  screen produces fake text.
* Play time: hours 0xDA41, minutes 0xDA43, seconds 0xDA44 (the old code was off by one).
* `started()` = sprite table 0xC100 non-zero **and** map width/height non-zero; the sprite check alone is
  true during the intro animation.
* Warp dest 0xFF means "back to the last outdoor map".
* Full maps come from the block grid at 0xC6E8 (3-block border) + 16-byte block definitions in the
  tileset ROM bank (0xD52B/0xD52C) + the walkable-tile list (0xD530); a metatile is walkable if its
  bottom-left tile is in that list. Grass = tile 0xD535. Edge connections: bits at 0xD370, map ids at
  0xD371/0xD37C/0xD387/0xD392.
* Every press is followed by `_settle()`: advance until the tilemaps stop changing (max 120 frames), so
  text finishes printing before the next input. Battle intros ignore input; `walk` checks for dialogue
  and battles before declaring "blocked".
* Text speed FAST + battle animations OFF + battle style SET (0xC1) are written to 0xD355 after every action unless `--no-fast-text`.
* The game ignores input while a jingle plays (item/Pokémon received); `profile.busy()` reads the SFX
  channels at 0xC02A-0xC02D and `_settle()` waits for them. Cutscenes can also freeze the player before
  their text box shows, so `walk` re-classifies "blocked" after settling.
* `busy()` is also true during battle animations: in battle with no menu/cursor/▼ on screen. After
  "Go! <mon>!" the throw animation is ~125 frames with an unchanged tilemap; the settle cap is 300.
* Scripts (Oak's lab) briefly scribble on the Pokédex owned flags: a capture ("obtained: X") is only
  reported when the species is also in the party or the current PC box (0xDA80). `after_load` seeds the
  already-owned set so resumed games don't re-report.
* `walk("to x,y")` = BFS on `full_map_cells()` with NPC tiles blocked (`find_path`), re-planned up to
  3 times when "blocked". Building doors are solid tiles you walk *into*, so a solid warp tile is
  allowed only as the BFS destination. Two-wide doorways (gates) often have one solid half: if the
  step onto the target is refused, `_goto` retries the twin warp (`alternate_warps`). Arriving on a
  walkable warp tile takes one extra step off the map edge (`edge_direction`) or in the last direction.
* One-way ledges: outdoor tileset (0xD367 == 0) tiles 0x36/0x37 (down), 0x27 (left), 0x0D/0x1D (right)
  from pokered `LedgeTiles`; drawn as `v < >` and traversed by BFS as a 2-cell move in that direction.
* `profile.hint()` adds a one-line tip to action results for known prompts; keep hints short.
* After `battle`/`talk`/`shop` the emulator settles and, if a battle just ended, waits 60 frames so a
  black-out teleport has loaded the new map's warps before the next call reads them.
* Brock strategy that worked with a Charmander start: catch a Caterpie in Viridian Forest, level it as
  lead (switching out when low) to Butterfree L12 for Confusion; Charmeleon's Ember does ¼ damage to
  Brock's Rock/Ground team. A local `saves/Pokemon-Red_Version/after-brock.state` (gitignored, not
  in the repo) is the resulting state if you have generated one.
* Map-edge connections: the coordinates leave the map a few frames before the map id changes;
  `_walk_segment` waits for the new map (`profile.off_map`) so callers never see out-of-map positions.
  Ledge jumps move 2 cells: `find_path` segments count cells and the executor counts distance.
* World graph: `snapshot()` records each visited map's warps, connections and `wLastMap` (0xD365, the
  outdoor map an "outside" warp returns to) in `profile.world`; `_resolve_far` BFSes it for
  `walk("to <map>")`, one hop per iteration in `Emulator.walk`. `on_battle` wraps `_walk_once`.
* Scripted scenes: `wJoyIgnore` (0xCD6B) is non-zero while a cutscene controls the player;
  `talk()` waits through the silent walking parts, `walk` refuses with a hint.
* `tests/test_playthrough.py` replays power-on → Viridian City through the real tool functions in ~2 s;
  run it after any change to input timing, walking, or the profile.
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
optionally `position` (enables smart walking and door/battle detection), `screen_text`, `after_load`,
`agent_hints`. Register a title regex in `games/__init__.py`. Generic games can also pass
`--charmap file.json` to decode text.

## Conventions

* Results are short. No JSON dumps with indentation, no marketing text in tool descriptions.
* Every emulator behavior change should have a test in `tests/test_gameplay.py`.
* `saves/`, `metrics/`, `screenshots/`, `bench/runs/`, ROMs and `.ram` files are runtime data, not source;
  `results/*.json` and the generated `RESULTS.md` are the published benchmark data.
* Commits: identity `Dst0rtr <135249234+Dst0rtr@users.noreply.github.com>`, no AI attribution lines.
