"""
Game profile interface.

A profile teaches the generic emulator about one specific game: how to
summarize its state in a few tokens, how to read on-screen text from VRAM,
how to walk reliably, and which events count as progress milestones.

The generic profile works for any ROM. Game-specific profiles override
whatever they can improve. See pokemon_gen1.py for a full example.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from pyboy import PyBoy


class GameProfile:
    """Base profile: works with any Game Boy ROM."""

    #: Human-readable profile name.
    name = "generic"
    #: Extra guidance appended to the MCP server instructions for the agent.
    agent_hints = ""
    #: Why the last walk stopped ("blocked", "entered X", ...), set by the emulator; None after other actions.
    last_stop: Optional[str] = None

    def __init__(self, pyboy: "PyBoy", options: dict[str, Any] | None = None):
        self.pyboy = pyboy
        self.mem = pyboy.memory
        self.options = options or {}
        self.charmap: dict[int, str] = self.options.get("charmap") or {}

    # -- lifecycle ---------------------------------------------------------- #
    def after_load(self) -> None:
        """Called after boot / reset / load_state. Apply quality-of-life tweaks here."""

    def after_action(self) -> None:
        """Called after every tool action (cheap hook, e.g. keep options enforced)."""

    def busy(self) -> bool:
        """True while the game is known to ignore input (e.g. a jingle is playing)."""
        return False

    def scripted(self) -> bool:
        """True while a cutscene controls the player."""
        return False

    # -- state -------------------------------------------------------------- #
    def status_line(self) -> str:
        """One short line describing where the player is / what is happening."""
        return ""

    def state(self, section: str = "summary") -> str:
        """Longer text for the `state` tool. Sections vary per profile."""
        if section in ("summary", "full"):
            return self.status_line() or "(no game-specific state for this ROM)"
        return f"Unknown section '{section}'. Available: {', '.join(self.sections())}"

    def sections(self) -> list[str]:
        return ["summary"]

    def snapshot(self) -> dict[str, Any]:
        """Machine-readable progress snapshot used by the metrics tracker."""
        return {}

    def milestones(self, prev: dict[str, Any], cur: dict[str, Any]) -> list[str]:
        """Return names of milestones reached between two snapshots."""
        return []

    def world_data(self) -> Optional[dict]:
        """JSON-serialisable navigation knowledge worth keeping across restarts (None if there is none)."""
        return None

    def load_world(self, data: dict) -> None:
        """Restore what an earlier world_data() returned."""

    # -- screen ------------------------------------------------------------- #
    def screen_text(self) -> Optional[str]:
        """Decode on-screen text from VRAM. None if unsupported for this game."""
        if not self.charmap:
            return None
        return decode_visible_tilemap(self.pyboy, self.charmap)

    def hint(self) -> str:
        """One-line tip for the prompt currently on screen (empty when there is none)."""
        return ""

    def is_text_visible(self) -> bool:
        txt = self.screen_text()
        return bool(txt and txt.strip())

    # -- movement ----------------------------------------------------------- #
    def position(self) -> Optional[tuple]:
        """Return a hashable position (map, x, y) if the game exposes one."""
        return None

    def map_label(self, map_id: int) -> str:
        return f"map {map_id}"

    def find_path(self, tx: int, ty: int):
        """Return [(direction, steps), ...] to reach (tx, ty) on the current map, or None."""
        return None

    def resolve_target(self, name: str):
        """Turn a place name into (x, y, edge_direction) for walk('to <name>'), or None."""
        return None

    def route_hint(self, tx: int, ty: int) -> str:
        """Why a route to (tx, ty) may be impossible (water, obstacles...); empty if unknown."""
        return ""

    def battle_action(self, emu, action: str, target: str = "") -> str:
        return "this game profile has no battle helper; use press()"

    def talk(self, emu) -> str:
        """Generic: press A and return whatever text is on screen."""
        emu.press("A", settle=1)
        return self.screen_text() or "(no readable text)"

    def shop(self, emu, item: str, qty: int = 1) -> str:
        return "this game profile has no shop helper; use press()"

    def manage(self, emu, action: str, target: str = "", target2: str = "") -> str:
        return "this game profile has no menu helper; use press()"

    frames_per_step = 16


def decode_visible_tilemap(pyboy: "PyBoy", charmap: dict[int, str], width: int = 20, height: int = 18) -> str:
    """
    Decode the visible 20x18 tile grid to text using a tile-id -> char map.
    Reads the window map when the window covers the screen, else the scrolled BG map.
    """
    mem = pyboy.memory
    lcdc = mem[0xFF40]
    wy = mem[0xFF4A]
    if lcdc & 0x20 and wy == 0:
        base = 0x9C00 if lcdc & 0x40 else 0x9800
        scx = scy = 0
    else:
        base = 0x9C00 if lcdc & 0x08 else 0x9800
        scx, scy = mem[0xFF43], mem[0xFF42]
    col0, row0 = scx // 8, scy // 8
    rows = []
    for r in range(height):
        y = (row0 + r) % 32
        line = "".join(charmap.get(mem[base + y * 32 + ((col0 + c) % 32)], " ") for c in range(width))
        rows.append(line.rstrip())
    return "\n".join(rows)
