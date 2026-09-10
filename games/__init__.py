"""
Game profile registry. A profile is picked from the cartridge title in the ROM
header; unknown games get the generic profile (works for any Game Boy ROM).

To add a game: subclass GameProfile in a new module and register a matcher here.
"""

from __future__ import annotations

import re
from typing import Callable

from .base import GameProfile

# (regex on cartridge title, loader) — first match wins.
_REGISTRY: list[tuple[re.Pattern, Callable[[], type[GameProfile]]]] = []


def register(title_pattern: str, loader: Callable[[], type[GameProfile]]) -> None:
    _REGISTRY.append((re.compile(title_pattern, re.I), loader))


def _gen1():
    from .pokemon_gen1 import PokemonGen1Profile
    return PokemonGen1Profile


def _wrapped():
    from .pyboy_wrapped import PyBoyWrappedProfile
    return PyBoyWrappedProfile


register(r"^POKEMON (RED|BLUE|YELLOW)", _gen1)
register(r"^(TETRIS|SUPER MARIOLAND|KIRBY DREAM LAND|POKEMON PINBALL)", _wrapped)


def detect_profile(pyboy, options: dict | None = None, force: str | None = None) -> GameProfile:
    """Instantiate the best profile for the loaded ROM."""
    title = (pyboy.cartridge_title or "").strip()
    if force and force != "auto":
        cls = {"pokemon-gen1": _gen1, "pyboy-wrapper": _wrapped, "generic": lambda: GameProfile}[force]()
        return cls(pyboy, options)
    for pat, loader in _REGISTRY:
        if pat.search(title):
            return loader()(pyboy, options)
    return GameProfile(pyboy, options)


AVAILABLE_PROFILES = ["auto", "generic", "pokemon-gen1", "pyboy-wrapper"]
