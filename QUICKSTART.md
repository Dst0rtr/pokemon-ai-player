# Quick Start

## 1. Install

```bash
cd /path/to/pokemon-ai-player
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Use the venv's Python in your MCP config (`/path/to/pokemon-ai-player/venv/bin/python`).
If you prefer the system interpreter, install the requirements into the same `python3`
the client will run and use that path instead.

## 2. Test

```bash
python test_emulator.py "Pokemon-Red_Version.gb"                # boot, press, screenshot
python test_emulator.py "Pokemon-Red_Version.gb" --play-intro   # plays to the overworld and prints the map
python -m pytest tests -q                                         # 35 tests, about 5 s
python examples/reference_run.py "Pokemon-Red_Version.gb"        # scripted agent: power-on to Brock, ~35 s
```

Any `.gb`/`.gbc` works; only Pokémon Red/Blue/Yellow get the rich profile. The reference run
copies the ROM to a temp folder, so it never touches your battery save.

## 3. Configure your client

Use absolute paths everywhere.

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "gameboy": {
      "command": "/Users/you/code/pokemon-ai-player/venv/bin/python",
      "args": [
        "/Users/you/code/pokemon-ai-player/server.py",
        "--rom", "/Users/you/code/pokemon-ai-player/Pokemon-Red_Version.gb",
        "--ai-model", "claude-fable-5-1",
        "--resume"
      ]
    }
  }
}
```

### Claude Code

```bash
claude mcp add gameboy -- /Users/you/code/pokemon-ai-player/venv/bin/python \
  /Users/you/code/pokemon-ai-player/server.py --rom /Users/you/code/pokemon-ai-player/Pokemon-Red_Version.gb --ai-model claude-fable-5-1
```

### Goose Desktop

Settings → Extensions → Add Extension → type STDIO, command:

```
/Users/you/code/pokemon-ai-player/venv/bin/python /Users/you/code/pokemon-ai-player/server.py --rom /Users/you/code/pokemon-ai-player/Pokemon-Red_Version.gb --ai-model goose
```

Restart the client after editing its config.

## 4. Play

Tell the agent something like:

> Play Pokémon Red. Read the server instructions first. Use `walk("to ...")` for movement,
> `talk()` for people and signs, `battle("auto")` or `battle("fight", move)` for fights,
> `shop` and `manage` for shops and the party. Trust the returned text and hints; take a
> screenshot only when the text is ambiguous. Save a state before each gym. Call
> `metrics("finalize")` when you stop.

Screenshots are written to `screenshots/latest.png` (and numbered files unless
`--no-screenshot-files`). Save states live in `saves/<rom>/`; reports in `metrics/`.
Save states are not part of the repository; make your own with `save_state("name")`.

## Troubleshooting

* **`ModuleNotFoundError`**: the client is running a different Python than the one you installed
  into. Put the venv interpreter path in `command`.
* **ROM not found**: use an absolute path; check the file exists.
* **Agent seems slow**: the emulator is not the bottleneck (about 30k frames/s). Reduce round trips:
  goals instead of steps, `battle("auto")`, `talk()`, `screenshot=false` when text suffices.
* **Fake text on screen**: only screens with the game font loaded are decoded; the title screen
  returns no text by design.
* **Lost progress**: `load_state("autosave")`, or start the server with `--resume`. In-game saves
  (`manage("save")`) are written to `<rom>.ram` next to the ROM when the server stops.
* **Title menu shows CONTINUE**: a battery save exists next to the ROM; press DOWN before A to start
  a new game, or delete `<rom>.ram`.
