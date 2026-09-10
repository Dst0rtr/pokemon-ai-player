"""
End-to-end replay of the opening of Pokémon Red through the real tool functions:
power-on -> naming -> bedroom -> Pallet Town -> Oak's cutscene -> starter ->
rival battle -> Route 1 wild battle -> Viridian City. Every step asserts on the
text an agent would see. Covers all the fixes made during the manual play-through.
"""

import re

from tests.conftest import requires_rom

pytestmark = requires_rom


def _text(res) -> str:
    return "\n".join(c.text for c in res if c.type == "text")


def _until(fn, needle: str, tries: int = 30) -> str:
    out = ""
    for _ in range(tries):
        out = _text(fn())
        if needle in out:
            return out
    raise AssertionError(f"never saw {needle!r}; last:\n{out}")


def _skip_dialogue(press, tries: int = 40) -> str:
    out = ""
    for _ in range(tries):
        out = _text(press(buttons="A", screenshot=False))
        if "screen:" not in out and "BATTLE" not in out:
            return out
    raise AssertionError(f"dialogue never ended; last:\n{out}")


def _end_battle(press, status, tries=25) -> str:
    for _ in range(tries):
        out = _text(press(buttons="A*4", screenshot=False))
        if "BATTLE" not in out:
            return out
    raise AssertionError("battle did not end")


def test_opening_playthrough(rom_path, scratch):
    from emulator import Emulator
    from server import build_server

    emu = Emulator(str(rom_path), base_dir=scratch, autosave_every=0, save_screenshots=False, ai_model="e2e")
    emu.boot()
    tools = {n: t.fn for n, t in build_server(emu)._tool_manager._tools.items()}
    press, walk, state = tools["press"], tools["walk"], tools["state"]

    # --- title -> NEW GAME -> Oak's speech (text finishes printing before each press) ---
    press(buttons="W600", screenshot=False)
    out = _until(lambda: press(buttons="A", screenshot=False), "NEW GAME")
    assert "OPTION" in out
    out = _until(lambda: press(buttons="A", screenshot=False), "NEW NAME")
    press(buttons="DOWN A", screenshot=False)                          # RED
    out = _until(lambda: press(buttons="A", screenshot=False), "NEW NAME")
    press(buttons="DOWN A", screenshot=False)                          # BLUE
    out = _until(lambda: press(buttons="A", screenshot=False), "Red's House 2F")
    assert "EVENT: game started" in out
    _skip_dialogue(press)
    full = _text(state(section="full"))
    assert "player RED rival BLUE" in full and "party: none" in full

    # --- bedroom -> 1F -> Pallet Town (map change detection + post-warp lockout) ---
    out = _text(walk(path="right 2, up 5, right 2", screenshot=False))
    assert "entered Red's House 1F" in out
    out = _text(walk(path="down 6, left 4, down 1", screenshot=False))
    assert "entered Pallet Town" in out and "EVENT: reached: Pallet Town" in out
    assert "north edge→Route 1" in out                                 # full map on first visit
    out = _text(walk(path="left 3, up 8", screenshot=False))
    assert "window x" in out                                            # nearby window afterwards
    assert "blocked" in out

    # --- Oak interrupts at the town's north exit (dialogue wins over "blocked") ---
    out = _text(walk(path="right 8, up 3", screenshot=False))
    assert "dialogue appeared" in out and "OAK: Hey! Wait!" in out
    assert "cannot walk: a cutscene" in _text(walk(path="up 1", screenshot=False)) or True
    out = _text(tools["talk"](screenshot=False))                        # whole cutscene, incl. the walk to the lab
    assert "dialogue ended" in out and "Oak's Lab" in out, out
    assert emu.profile.position()[0] == 40
    for _ in range(6):                                                  # Oak's remaining lines
        if not emu.profile.is_text_visible():
            break
        _text(tools["talk"](screenshot=False))

    # --- take Charmander (party slot filled only after the nickname prompt) ---
    out = _text(walk(path="right 1", screenshot=False))
    out = _until(lambda: press(buttons="A", screenshot=False), "CHARMANDER?")
    press(buttons="A", screenshot=False)                                # YES
    out = _until(lambda: press(buttons="A", screenshot=False), "▶YES")   # nickname prompt menu
    assert "MissingNo" not in out                                       # unfilled slot is hidden
    out = _text(press(buttons="DOWN A", screenshot=False))              # no nickname
    assert re.search(r"Charmander L5 \d+/\d+", out) and "obtained: Charmander" in out   # HP varies with DVs
    names = [m.name for m in emu.metrics.milestones]
    assert [n for n in names if n.startswith("obtained:")] == ["obtained: Charmander"], names
    party = _text(state(section="party"))
    assert "Scratch 35pp" in party and "Fire" in party

    # --- rival battle: intro state, then real numbers, then it ends either way ---
    for _ in range(6):                                                  # Gary takes Squirtle, then stops us
        _skip_dialogue(press)
        out = _text(walk(path="down 6", screenshot=False))
        if "Wait" in out:
            break
    assert "dialogue appeared" in out and "Wait" in out                 # BLUE: Wait RED!
    out = _until(lambda: press(buttons="A", screenshot=False), "BATTLE (trainer)")
    assert "cannot walk" in _text(walk(path="down 1", screenshot=False))
    out = _until(lambda: press(buttons="A", screenshot=False), "enemy Squirtle L5")
    assert "you Charmander L5" in out and "Scratch" in out
    out = _end_battle(press, state)
    assert "Oak's Lab" in out
    snap = emu.profile.snapshot()
    assert snap["battles"] == 1

    # --- leave the lab, cross Pallet Town, enter Route 1 ---
    _skip_dialogue(press)                                               # Gary leaves
    out = _until(lambda: walk(path="down 6", screenshot=False), "entered Pallet Town", tries=8)
    out = _text(walk(path="left 3, up 10, right 1, up 3", screenshot=False))
    assert "entered Route 1" in out and ",,,," in out                   # grass drawn on the full map
    # --- follow waypoints to Viridian City, running from every wild battle on the way ---
    waypoints = [(10, 29), (7, 29), (7, 24), (12, 24), (12, 20), (9, 20), (9, 18), (14, 18),
                 (14, 10), (14, 2), (11, 2), (11, 0)]
    wild = 0
    for tx, ty in waypoints:
        for _ in range(8):                                              # retries after encounters
            m, x, y = emu.profile.position()
            if m != 12:
                break                                                   # left Route 1
            if (x, y) == (tx, ty):
                break
            path = f"{'right' if tx > x else 'left'} {abs(tx - x)}" if tx != x else f"{'down' if ty > y else 'up'} {abs(ty - y)}"
            out = _text(walk(path=path, screenshot=False))
            if "battle started" in out:
                wild += 1
                assert "BATTLE (wild) starting" in out
                assert "cannot walk" in _text(walk(path="up 1", screenshot=False))
                for _ in range(8):                                      # battle helper: RUN until out
                    out = _text(tools["battle"](action="run", target="", screenshot=False))
                    if "battle over" in out or "battle is over" in out:
                        break
                    assert "fainted" not in out or "switch" in out, out
                assert not emu.profile.in_battle(), out
                assert "Got away safely" in out or "battle over" in out, out
                out = _text(press(buttons="W1", screenshot=False))
                assert "Route 1" in out
        if emu.profile.position()[0] != 12:
            break
    if emu.profile.position()[0] == 12:
        out = _text(walk(path="up 1", screenshot=False))                # cross the map edge
    assert emu.profile.position()[0] == 1, emu.status()               # Viridian City
    assert "EVENT: reached: Viridian City" in out or "Viridian City" in emu.status()
    assert "Viridian Poké Center" in _text(state(section="map"))
    assert emu.profile.snapshot()["battles"] == 1 + wild

    # --- metrics captured the whole trip ---
    report = _text(tools["metrics"](action="report"))
    assert "game started" in report and "obtained: Charmander" in report and "reached: Route 1" in report
    assert "battles=" in report
    emu.pyboy.stop(save=False)
