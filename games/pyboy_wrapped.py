"""
Profile for games that PyBoy ships a game wrapper for (Tetris, Super Mario Land,
Kirby's Dream Land, Pokémon Pinball). Exposes whatever numeric attributes the
wrapper tracks (score, lives, level progress...) as a compact status line.
"""

from __future__ import annotations

from typing import Any

from .base import GameProfile

_ATTRS = ["score", "lives_left", "world", "level", "level_progress", "coins", "time_left",
          "lines", "fitness", "balls_left", "game_over"]


class PyBoyWrappedProfile(GameProfile):
    name = "pyboy-wrapper"
    agent_hints = "state(summary) reports score/lives read by PyBoy's game wrapper."

    def __init__(self, pyboy, options=None):
        super().__init__(pyboy, options)
        self.wrapper = pyboy.game_wrapper
        self.name = f"pyboy-{type(self.wrapper).__name__.replace('GameWrapper', '').lower()}"

    def _values(self) -> dict[str, Any]:
        out = {}
        for a in _ATTRS:
            v = getattr(self.wrapper, a, None)
            if callable(v):
                try:
                    v = v()
                except Exception:
                    continue
            if isinstance(v, (int, float, bool)):
                out[a] = v
        return out

    def status_line(self) -> str:
        return " ".join(f"{k}={v}" for k, v in self._values().items())

    def snapshot(self) -> dict[str, Any]:
        return self._values()

    def milestones(self, prev, cur) -> list[str]:
        out = []
        for key in ("world", "level"):
            if key in cur and cur.get(key) != prev.get(key):
                out.append(f"{key} {cur[key]}")
        return out
