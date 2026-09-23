#!/usr/bin/env python3
"""
Game Boy MCP server: lets an AI agent play any Game Boy ROM through a small,
token-efficient tool set. Game-specific smarts (Pokémon Red/Blue/Yellow today)
come from profiles in games/ and are picked automatically from the ROM header.

Run:  python3 server.py --rom path/to/game.gb [--ai-model name] [--resume]
"""

from __future__ import annotations

import argparse
import atexit
import logging
import signal
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
import base64

from emulator import Emulator
from games import AVAILABLE_PROFILES

log = logging.getLogger("gameboy.server")

GUIDE = """You control a Game Boy through this server. Every action returns a status line, on-screen text, a hint when the game is asking something, and (by default) a screenshot only if the screen changed.

Prefer goals over button presses: walk("to Viridian Mart" / "to Pewter City" / "to 12,4" / "up 5, right 3", on_battle="run" to flee wild battles on the way), talk() to read a whole conversation or cutscene, battle("auto") for a routine fight or battle("fight", "Ember") / "run" / "item", "Poké Ball" / "switch", 2 for one turn, shop("Potion", 3), manage("lead"|"use"|"save", ...). They stop at every question (YES/NO, learn move, nickname) - answer with press("A") or press("DOWN A").

press() script: A B START SELECT UP DOWN LEFT RIGHT; "A*5" repeats, "UP:16" holds, "W60" waits 1s. Pass screenshot=false when text is enough; use state("map"/"party"/"items"/"battle") for details. Keep your Pokémon healthy (heal when low or poisoned).

Progress is auto-saved; save_state/load_state give checkpoints. Metrics are recorded automatically; metrics("note", text) keeps a reminder for yourself (shown by metrics("report")); call metrics("finalize") when you stop."""


def build_server(emu: Emulator) -> FastMCP:
    name = "gameboy"
    instructions = GUIDE
    server = FastMCP(name, instructions=instructions)

    def _respond(tool: str, text: str, image: Optional[bytes]) -> list:
        emu.metrics.record_call(tool, len(text), image is not None)
        out: list = [TextContent(type="text", text=text)]
        if image is not None:
            out.append(ImageContent(type="image", data=base64.b64encode(image).decode(), mimeType="image/png"))
        return out

    def _guard(tool: str) -> Optional[list]:
        """When a run budget is used up, refuse further game actions (finalizing the metrics once)."""
        reason = emu.metrics.budget_exhausted()
        if not reason:
            return None
        if not emu.metrics.finalized:
            log.info("budget exhausted: %s", reason)
            emu.metrics.finalize()
        return _respond(tool, f"BUDGET EXHAUSTED: {reason}. The run is over and its metrics are finalized. "
                              "Stop playing and report your progress.", None)

    def _observe(tool: str, head: str, want_image: bool, with_map: bool = False, scale: Optional[int] = None) -> list:
        """Standard action result: status + events + screen text + optional screenshot."""
        parts = [head, emu.status()]
        events = emu.pop_events()
        if events:
            parts.append("EVENT: " + "; ".join(events))
        txt = emu.screen_text()
        if txt:
            parts.append("screen:\n" + txt)
        elif with_map:
            parts.append(emu.map_view())
        hint = emu.profile.hint() if emu.profile else ""
        if hint:
            parts.append(hint)
        img = emu.screenshot(scale) if want_image else None
        if want_image and img is None:
            parts.append("(screen image unchanged)")
        return _respond(tool, "\n".join(p for p in parts if p), img)

    tool = lambda **kw: server.tool(structured_output=False, **kw)  # noqa: E731

    @tool(description="Press buttons. Script tokens: A B START SELECT UP DOWN LEFT RIGHT; 'A*3' repeats, 'UP:16' holds 16 frames, 'W60' waits 60 frames. Example: 'A*4 DOWN A W30'. Returns status, on-screen text and a screenshot if the screen changed.")
    def press(buttons: str, screenshot: bool = True) -> list:
        if (blocked := _guard("press")) is not None:
            return blocked
        head = emu.press(buttons)
        if head.startswith(("bad token", "too many", "no buttons")):
            return _respond("press", head, None)
        return _observe("press", head, screenshot)

    @tool(description="Walk. A path of tile steps ('up 5, right 3'), or pathfind with 'to X,Y' (map coordinates), 'to <exit name>' ('to Viridian Mart', 'to outside'), 'to north edge', or 'to <map name>' (routes through maps you have visited). Stops early when blocked, on entering a new map, or when a battle/dialogue starts, and says why. on_battle='run' flees wild battles and keeps going, 'auto' fights them.")
    def walk(path: str, screenshot: bool = True, on_battle: str = "stop") -> list:
        if (blocked := _guard("walk")) is not None:
            return blocked
        head = emu.walk(path, on_battle)
        if head.startswith(("bad path", "no path", "cannot walk", "no walkable", "route to", "unknown place")):
            return _respond("walk", head, None)
        return _observe("walk", head, screenshot, with_map=True)

    @tool(description="Battle helper (Pokémon): action 'fight' (target = move name or 1-4), 'auto' (keep attacking with damaging moves until the battle ends, a question appears, or HP is low; target = preferred move), 'run', 'switch' (target = party number or name; also answers 'Bring out which POKéMON?'), 'item' (target = item name, optionally 'Potion: Pidgey' to pick who gets it; in the Safari Zone it throws a Safari Ball), 'bait' / 'rock' (Safari Zone). Returns what happened plus HP changes; stops on YES/NO or learn-move prompts so you can answer with press().")
    def battle(action: str = "fight", target: str = "", screenshot: bool = False) -> list:
        if (blocked := _guard("battle")) is not None:
            return blocked
        head = emu.battle(action, target)
        return _observe("battle", head, screenshot)

    @tool(description="Talk / interact: presses A at whatever you face (NPC, sign, PC, nurse, clerk) and reads the whole conversation, stopping when a choice (YES/NO, shop menu, list) appears or the text ends. Also use it to finish a conversation that is already open.")
    def talk(screenshot: bool = False) -> list:
        if (blocked := _guard("talk")) is not None:
            return blocked
        return _observe("talk", emu.talk(), screenshot)

    @tool(description="Buy from a Poké Mart clerk you are facing (Pokémon): item name (e.g. 'Poké Ball', 'Potion') and quantity. Opens the shop if needed and reports money and bag afterwards; press B to leave the shop menu.")
    def shop(item: str, qty: int = 1) -> list:
        if (blocked := _guard("shop")) is not None:
            return blocked
        return _respond("shop", emu.shop(item, qty), None)

    @tool(description="Menu helper (Pokémon, outside battle): action 'lead' (target = Pokémon name/number to put first), 'swap' (two party slots), 'use' (target = item name, target2 = Pokémon for Potions/TMs/HMs; 'Charmander: Growl' names the move to forget when it already knows 4), 'field' (target = Cut/Surf/Strength/Flash/Fly/Dig/Teleport while facing the tree/water/boulder; target2 = town for Fly), 'save' (in-game save). Handles the START menu for you.")
    def manage(action: str, target: str = "", target2: str = "") -> list:
        if (blocked := _guard("manage")) is not None:
            return blocked
        return _respond("manage", emu.manage(action, target, target2), None)

    @tool(description="Let the game run for N frames (60 = 1 second) without input, e.g. to let text or animations finish.")
    def wait(frames: int = 60, screenshot: bool = True) -> list:
        if (blocked := _guard("wait")) is not None:
            return blocked
        return _observe("wait", emu.wait(frames), screenshot)

    @tool(description="Look at the screen. mode='image' (screenshot), 'text' (decoded on-screen text, cheapest), or 'both'. scale 1-4 enlarges the image for reading small text (default from server config).")
    def screen(mode: str = "image", scale: int = 0) -> list:
        mode = (mode or "image").lower()
        if mode not in ("image", "text", "both"):
            return _respond("screen", f"unknown mode '{mode}': use image, text or both", None)
        parts = [emu.status()]
        if mode in ("text", "both"):
            parts.append(emu.screen_text() or "(no readable text on screen)")
        img = emu.screenshot(scale or None, force=True) if mode in ("image", "both") else None
        return _respond("screen", "\n".join(parts), img)

    @tool(description="Read game state as text. section: 'summary' (one line), 'map' (walkability grid, exits, NPCs), 'party', 'battle', 'items', 'full'. Sections depend on the game profile.")
    def state(section: str = "summary") -> list:
        return _respond("state", emu.state(section), None)

    @tool(description="Save the emulator state to a named slot (e.g. before a gym or a risky fight).")
    def save_state(slot: str = "1") -> list:
        return _respond("save_state", emu.save_state(slot), None)

    @tool(description="Load a previously saved slot. slot='list' shows available slots. 'autosave' is written automatically every few actions.")
    def load_state(slot: str = "1") -> list:
        if (blocked := _guard("load_state")) is not None:
            return blocked
        if slot.lower() == "list":
            slots = emu.list_states()
            return _respond("load_state", "slots: " + (", ".join(slots) or "none"), None)
        head = emu.load_state(slot)
        if head.startswith("no state"):
            return _respond("load_state", head, None)
        return _observe("load_state", head, True)

    @tool(description="Power-cycle the game (back to the title screen). Requires confirm=true. In-game saves survive; unsaved progress is lost.")
    def reset_game(confirm: bool = False) -> list:
        if (blocked := _guard("reset_game")) is not None:
            return blocked
        if not confirm:
            return _respond("reset_game", "not reset: pass confirm=true to power-cycle the game", None)
        return _observe("reset_game", emu.reset(), True)

    @tool(description="Raw memory access for games without a profile. action='read' returns a hex dump of `length` bytes at hex `address` (e.g. 'D163'); action='write' writes hex `values` (requires --allow-memory-write).")
    def memory(action: str = "read", address: str = "C000", length: int = 16, values: str = "") -> list:
        try:
            if action == "write":
                return _respond("memory", emu.write_memory(address, values), None)
            return _respond("memory", emu.read_memory(address, length), None)
        except Exception as e:  # bad address, out of bounds, bad hex
            return _respond("memory", f"error: {e}", None)

    @tool(description="Benchmark metrics. action: 'report' (current summary incl. your notes), 'milestone' (record a named milestone, e.g. name='beat Brock'), 'note' (name = a reminder to yourself, e.g. 'Cut tree blocks Vermilion Gym'), 'start' (new session, optional name=model), 'checkpoint', 'finalize' (write the report files; call when done).")
    def metrics(action: str = "report", name: str = "") -> list:
        a = (action or "report").lower()
        if a == "start":
            txt = emu.metrics.restart(name or None)
        elif a == "milestone":
            txt = emu.metrics.mark(name) if name else "milestone needs a name"
        elif a == "note":
            txt = emu.metrics.note(name)
        elif a == "checkpoint":
            txt = f"checkpoint written: {emu.metrics.checkpoint().name}"
        elif a == "finalize":
            txt = emu.metrics.finalize()
        else:
            txt = emu.metrics.summary()
        return _respond("metrics", txt, None)

    return server


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Game Boy MCP server")
    p.add_argument("--rom", required=True, help="path to a .gb/.gbc ROM")
    p.add_argument("--ai-model", default="unknown", help="model name recorded in metrics")
    p.add_argument("--profile", default="auto", choices=AVAILABLE_PROFILES, help="game profile (default: auto-detect)")
    p.add_argument("--scale", type=int, default=2, help="screenshot upscale factor 1-4 (default 2)")
    p.add_argument("--resume", action="store_true", help="load saves/<rom>/autosave.state on start")
    p.add_argument("--autosave-every", type=int, default=20, help="actions between autosaves (0 disables)")
    p.add_argument("--no-fast-text", action="store_true", help="Pokémon: don't force fast text / no battle animations")
    p.add_argument("--no-screenshot-files", action="store_true", help="don't write numbered PNGs to screenshots/")
    p.add_argument("--allow-memory-write", action="store_true", help="enable the memory write tool")
    p.add_argument("--charmap", help="JSON {tile_id: char} for reading text in games without a profile")
    p.add_argument("--data-dir", help="where screenshots/, saves/ and metrics/ go (default: next to server.py)")
    p.add_argument("--session-id", help="metrics session id; reuse it across launches to continue one benchmark run")
    p.add_argument("--max-tool-calls", type=int, default=0, help="refuse game actions after this many tool calls (0 = unlimited)")
    p.add_argument("--max-real-seconds", type=float, default=0, help="refuse game actions after this much real time (0 = unlimited)")
    p.add_argument("--finalize-on-exit", action="store_true", help="write the final metrics report when the server exits")
    p.add_argument("--log-file", help="also append the log to this file")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file))
    logging.basicConfig(level=args.log_level.upper(), handlers=handlers, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    emu = Emulator(
        args.rom, profile=args.profile, scale=args.scale, fast_text=not args.no_fast_text,
        save_screenshots=not args.no_screenshot_files, autosave_every=args.autosave_every,
        allow_memory_write=args.allow_memory_write, charmap_file=args.charmap, ai_model=args.ai_model,
        base_dir=args.data_dir, session_id=args.session_id, max_tool_calls=args.max_tool_calls,
        max_real_seconds=args.max_real_seconds, finalize_on_exit=args.finalize_on_exit,
    )
    log.info(emu.boot(resume=args.resume))
    server = build_server(emu)
    if emu.profile.agent_hints:
        server._mcp_server.instructions = GUIDE + "\n\n" + emu.profile.agent_hints
    atexit.register(emu.stop)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # a client killing us still gets autosave + metrics
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
