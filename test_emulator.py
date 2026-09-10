#!/usr/bin/env python3
"""
Smoke test: verify PyBoy + the ROM work and show what the agent will see.

  python test_emulator.py path/to/game.gb              boot, press START, screenshot, status
  python test_emulator.py path/to/pokemon.gb --play-intro   also play through the intro and print the map
"""

import logging
import sys
import time
from pathlib import Path

from emulator import Emulator


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    rom = sys.argv[1]
    play_intro = "--play-intro" in sys.argv
    logging.basicConfig(level="INFO", stream=sys.stderr, format="%(message)s")

    emu = Emulator(rom, autosave_every=0, save_screenshots=False)
    print(emu.boot())
    t = time.time()
    print(emu.press("W600 START W60 A W60"))
    print(f"  ({emu.frame} frames in {time.time() - t:.2f}s)")
    print("status:", emu.status())
    txt = emu.screen_text()
    print("screen text:", repr(txt[:80]) if txt else "(none)")
    png = emu.screenshot()
    out = Path(emu.screenshots_dir) / "latest.png"
    print(f"screenshot: {len(png) if png else 0} bytes -> {out}")

    if play_intro and emu.profile.name == "pokemon-gen1":
        from tests.conftest import drive_intro
        n = drive_intro(emu)
        print(f"\nplayed through the intro in {n} actions")
        print(emu.state("full"))
        print(emu.walk("right 2, up 5"))
        print(emu.state("map"))
        emu.screenshot()
    elif play_intro:
        print("--play-intro only knows Pokémon Red/Blue/Yellow")

    print("\n" + emu.metrics.summary())
    emu.pyboy.stop(save=False)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
