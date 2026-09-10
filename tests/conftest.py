import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Any Pokémon Red/Blue ROM in the project root, or POKEMON_ROM env var.
_candidates = [Path(os.environ["POKEMON_ROM"])] if os.environ.get("POKEMON_ROM") else []
_candidates += sorted(ROOT.glob("*.gb")) + sorted(ROOT.glob("*.gbc"))
ROM = next((p for p in _candidates if p.exists()), None)

requires_rom = pytest.mark.skipif(ROM is None, reason="no ROM found (set POKEMON_ROM or drop a .gb in the project root)")


@pytest.fixture(scope="session")
def rom_path() -> Path:
    if ROM is None:
        pytest.skip("no ROM")
    return ROM


@pytest.fixture(scope="session")
def scratch(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("gb")


def drive_intro(emu, max_actions: int = 200) -> int:
    """Mash through Pokémon Red's intro until the player can move. Returns actions used."""
    emu.press("W600")
    for i in range(max_actions):
        txt = emu.screen_text() or ""
        if "▶CONTINUE" in txt:                 # a battery save exists: pick NEW GAME instead
            emu.press("DOWN")
            continue
        if "NEW NAME" in txt:
            emu.press("DOWN A")
            continue
        if emu.profile.started() and not txt:
            emu.wait(60)
            if not (emu.screen_text() or ""):
                return i
        emu.press("A", settle=8)
    raise RuntimeError("intro did not finish")


@pytest.fixture(scope="session")
def in_game_state(rom_path, scratch) -> Path:
    """A save state with the player standing in their bedroom, cached per session."""
    from emulator import Emulator

    state = scratch / "bedroom.state"
    emu = Emulator(str(rom_path), base_dir=scratch, autosave_every=0)
    emu.boot()
    if emu.profile.name != "pokemon-gen1":
        pytest.skip("ROM is not Pokémon Gen 1")
    drive_intro(emu)
    with open(state, "wb") as f:
        emu.pyboy.save_state(f)
    emu.pyboy.stop(save=False)
    emu.pyboy = None
    return state


@pytest.fixture
def emu(rom_path, scratch, in_game_state):
    from emulator import Emulator

    e = Emulator(str(rom_path), base_dir=scratch, autosave_every=0, save_screenshots=False)
    e.boot()
    with open(in_game_state, "rb") as f:
        e.pyboy.load_state(f)
    e.tick(2)
    e.profile.after_load()
    yield e
    e.pyboy.stop(save=False)
    e.pyboy = None
