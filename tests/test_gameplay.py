"""Integration tests driving a real Pokémon Red ROM headlessly."""

import io
import time

from PIL import Image

from tests.conftest import requires_rom

pytestmark = requires_rom


def test_boot_detects_profile(rom_path, scratch):
    from emulator import Emulator

    e = Emulator(str(rom_path), base_dir=scratch, autosave_every=0)
    msg = e.boot()
    assert "profile=pokemon-gen1" in msg
    assert "intro" in e.status()
    e.pyboy.stop(save=False)


def test_intro_menu_text_decodes(rom_path, scratch):
    from emulator import Emulator

    e = Emulator(str(rom_path), base_dir=scratch, autosave_every=0)
    e.boot()
    e.press("W600")
    assert e.screen_text() == ""             # intro animation: font not loaded, no fake text
    for _ in range(12):                      # A through the intro and title until the menu shows
        e.press("A")
        txt = e.screen_text() or ""
        if "NEW GAME" in txt:
            break
    assert "NEW GAME" in txt and "OPTION" in txt
    e.pyboy.stop(save=False)


def test_in_game_status_and_state(emu):
    assert emu.profile.started()
    s = emu.status()
    assert "Red's House 2F" in s and "¥3000" in s and "0 badges" in s
    full = emu.state("full")
    assert "player RED" in full and "rival BLUE" in full
    assert "party: none" in full
    assert emu.state("battle") == "not in battle"
    assert emu.state("items").startswith("bag")
    assert "unknown section" in emu.state("nope")


def test_nearby_view_marks_player_and_exit(emu):
    m = emu.state("nearby")
    lines = m.split("\n")
    grid = lines[1:10]
    assert len(grid) == 9 and all(len(r) == 10 for r in grid)
    assert grid[4][4] == "P"
    assert "exits here:" in m and "Red's House 1F" in m


def test_full_map_decodes_room(emu):
    m = emu.state("map")
    lines = m.split("\n")
    assert lines[0].startswith("Red's House 2F 8x8")
    rows = [ln[3:] for ln in lines[2:10]]
    assert len(rows) == 8 and all(len(r) == 8 for r in rows)
    assert rows[6][3] == "P"                      # player at (3,6)
    assert rows[1][7] == "D"                      # stairs at (7,1)
    assert sum(r.count(".") for r in rows) > 20   # mostly walkable floor
    assert "exits: (7,1)→Red's House 1F" in m


def test_walk_counts_steps_and_stops_when_blocked(emu):
    _, x0, y0 = emu.profile.position()
    r = emu.walk("right 2")
    _, x1, y1 = emu.profile.position()
    assert r.startswith("walked right 2/2") and (x1 - x0, y1 - y0) == (2, 0)
    r = emu.walk("right 40")
    assert "blocked" in r and "right 0/40" in r
    r = emu.walk("up 5, right 2, down 40")
    assert "stopped: entered Red's House 1F" in r  # walking onto the stairs warps before the path ends


def test_walk_through_door_reports_map_change(emu):
    # Bedroom stairs are at (7,1); the player starts at (3,6).
    emu.walk("right 2, up 5")
    r = emu.walk("right 2")
    assert "entered Red's House 1F" in r
    assert emu.profile.position()[0] == 37


def test_walk_outside_and_back_in(emu):
    emu.walk("right 2, up 5, right 2")          # to 1F via the stairs
    emu.walk("down 6, left 4, down 1")           # out the front door
    assert emu.profile.position()[0] == 0        # Pallet Town
    m = emu.state("map")
    assert "Pallet Town" in m and "N" in m       # NPCs visible in town
    assert "Oak's Lab" in m                      # listed as an exit


def test_screenshot_dedupe_and_scale(emu):
    png = emu.screenshot()
    assert png and png[:4] == b"\x89PNG"
    im = Image.open(io.BytesIO(png))
    assert im.size == (320, 288)
    assert emu.screenshot() is None            # unchanged -> no image
    assert emu.screenshot(force=True) is not None
    assert Image.open(io.BytesIO(emu.screenshot(scale=9, force=True))).size == (640, 576)   # clamped to 4x
    emu.press("START")                          # opens the menu: screen changes
    assert emu.screenshot() is not None
    assert "POKéDEX" in (emu.screen_text() or "").replace("é", "é") or "ITEM" in emu.screen_text()


def test_press_script_and_errors(emu):
    assert emu.press("START W10 B").startswith("pressed START W10 B")
    assert emu.press("A*3").startswith("pressed A*3")
    assert emu.press("FOO").startswith("bad token")
    assert emu.press("A*0").startswith("bad token")
    assert emu.press("UP:0").startswith("bad token")
    f = emu.frame
    emu.press("UP:99999")                        # hold is clamped
    assert emu.frame - f < 1500
    assert emu.press("A*200").startswith("too many")
    assert emu.press("   ") == "no buttons given"


def test_save_and_load_state_roundtrip(emu):
    pos0 = emu.profile.position()
    assert emu.save_state("t1").startswith("saved state 't1'")
    assert "t1" in emu.list_states()
    emu.walk("right 2")
    assert emu.profile.position() != pos0
    assert emu.load_state("t1").startswith("loaded state")
    assert emu.profile.position() == pos0
    assert emu.load_state("nope").startswith("no state")
    assert not list(emu.saves_dir.glob("*.tmp"))       # atomic write leaves no temp file


def test_memory_read_and_write_gate(emu):
    dump = emu.read_memory("D35E", 4)
    assert dump.startswith("D35E: 26")            # map 38 = 0x26
    assert len(emu.read_memory("FFF0", 9999).split()) == 17   # clamped to the end of the address space
    assert emu.read_memory("D163", 0).startswith("D163: ")
    assert "disabled" in emu.write_memory("D35E", "00")
    emu.allow_memory_write = True
    assert emu.write_memory("D347", "01 23 45").startswith("wrote 3")
    assert emu.profile.money() == 12345


def test_fast_text_option_enforced(emu):
    emu.press("A", settle=1)
    assert emu.pyboy.memory[0xD355] & 0x07 == 1        # fast text
    assert emu.pyboy.memory[0xD355] & 0x80             # animations off
    assert emu.pyboy.memory[0xD355] & 0x40             # battle style SET


def test_metrics_capture_milestones(emu):
    emu.metrics.restart("pytest-model")
    emu.pyboy.memory[0xD356] = 0b00000001              # fake BoulderBadge
    emu.wait(1)
    names = [m.name for m in emu.metrics.milestones]
    assert "badge: Boulder" in names
    emu.pyboy.memory[0xD2F7] = 0b00000001              # fake Bulbasaur owned bit only
    emu.wait(1)
    assert "obtained: Bulbasaur" not in [m.name for m in emu.metrics.milestones]   # not in party: ignored
    emu.pyboy.memory[0xD163] = 1                       # now put a Bulbasaur in the party
    emu.pyboy.memory[0xD164] = 0x99
    emu.pyboy.memory[0xD16B] = 0x99
    emu.wait(1)
    assert "obtained: Bulbasaur" in [m.name for m in emu.metrics.milestones]
    out = emu.metrics.finalize()
    assert "milestones:" in out
    assert (emu.metrics_dir / f"{emu.metrics.session_id}.json").exists()


def test_speed_budget(emu):
    t = time.time()
    emu.press("A*20")                                  # ~700 frames
    emu.walk("up 3")
    emu.wait(600)
    assert time.time() - t < 2.0, "actions should take well under a second each"


def test_walk_refuses_during_battle(emu):
    emu.pyboy.memory[0xD057] = 1                     # pretend a wild battle is running
    assert emu.walk("up 2").startswith("cannot walk")
    assert "starting" in emu.status()
    emu.pyboy.memory[0xD057] = 0


def test_wall_on_first_step_reports_blocked(emu):
    emu.walk("right 2")                              # now at (5,6) with a wall to the right
    r = emu.walk("right 1")
    assert r == "walked right 0/1 — stopped: blocked"


def test_press_settles_text_before_next_press(emu):
    # Talking to nothing changes nothing; opening START then pressing DOWN twice must land on RED.
    emu.press("START DOWN DOWN")
    txt = emu.screen_text() or ""
    assert "▶RED" in txt.replace("▶ ", "▶") or "▶" in txt
    emu.press("B")


def test_walk_refuses_while_menu_open(emu):
    emu.press("START")
    assert "▶" in (emu.screen_text() or "")
    assert emu.walk("up 1").startswith("cannot walk: a text box or menu is open")
    emu.press("B")
    assert emu.walk("right 1").startswith("walked right")


def test_goto_pathfinds_around_furniture(emu):
    segs = emu.profile.find_path(7, 1)                 # bedroom stairs
    assert segs and segs[0][0] in ("right", "up")
    r = emu.walk("to 7,1")
    assert "entered Red's House 1F" in r, r
    assert emu.walk("to 99,99").startswith("no walkable route")
    r = emu.walk("to 7,7")                             # 1F: bottom-right corner, reachable
    assert r.startswith("arrived at (7,7)"), r
    assert emu.profile.position()[1:] == (7, 7)


def test_finalize_then_stop_leaves_no_checkpoint(rom_path, scratch):
    from emulator import Emulator

    e = Emulator(str(rom_path), base_dir=scratch, autosave_every=2, save_screenshots=False, ai_model="fin")
    e.boot()
    e.press("W60")
    e.metrics.finalize()
    e.stop()
    files = sorted(p.name for p in (scratch / "metrics").glob("fin_*"))
    assert any(f.endswith("_summary.txt") for f in files)
    assert not any(f.endswith("_checkpoint.json") for f in files), files


def test_fainted_status_shown(emu):
    emu.pyboy.memory[0xD163] = 1                       # one Bulbasaur in the party with 0 HP
    emu.pyboy.memory[0xD164] = 0x99
    base = 0xD16B
    emu.pyboy.memory[base] = 0x99
    emu.pyboy.memory[base + 1] = 0
    emu.pyboy.memory[base + 2] = 0
    emu.pyboy.memory[base + 33] = 5
    emu.pyboy.memory[base + 34] = 0
    emu.pyboy.memory[base + 35] = 20
    assert "Bulbasaur L5 0/20 FNT" in emu.state("party")


def test_blackout_milestone(emu):
    emu.metrics.restart("blackout")
    emu.pyboy.memory[0xD057] = 0xFF                    # battle lost flag
    emu.wait(1)
    emu.pyboy.memory[0xD057] = 0
    emu.wait(1)
    names = [m.name for m in emu.metrics.milestones]
    assert names.count("blacked out (lost a battle)") == 1


def test_talk_reads_a_whole_conversation(emu):
    # The bedroom: facing up at the start, the SNES is in front of the player.
    r = emu.talk()
    assert r.startswith("dialogue ended:") and "SNES" in r, r
    assert emu.walk("right 1").startswith("walked right 1/1")   # nothing left open
    emu.press("START")
    r = emu.talk()
    assert r.startswith("choice:") and "▶" in r                # START menu is a choice
    emu.press("B")
    emu.walk("up 1")
    assert emu.talk().startswith("nothing to talk to")


def test_cross_map_routing_through_explored_maps(emu):
    assert "no explored route" in emu.walk("to Pallet Town")            # 1F not visited yet
    r = emu.walk("to Red's House 1F")
    assert "entered Red's House 1F" in r
    r = emu.walk("to Pallet Town")                                       # 1F's door leads outside
    assert "entered Pallet Town" in r, r
    assert emu.profile.position()[0] == 0
    assert emu.walk("to Pallet Town").startswith("already in")
    r = emu.walk("to Red's House 2F")                                    # two hops back through 1F
    assert "entered Red's House 2F" in r, r
    assert emu.profile.position()[0] == 38


def test_map_table_matches_rom_headers(rom_path):
    from games import gen1_data as D

    rom = rom_path.read_bytes()
    # (tileset, height, width) straight from the ROM; tilesets: 2 mart, 5 dojo, 6 poké center, 7 gym,
    # 14 ship port, 15 cemetery, 17 cavern, 18 lobby, 22 facility.
    expect = {40: (5, 6, 5), 41: (6, 4, 7), 59: (17, 18, 20), 81: (6, 4, 7), 82: (17, 18, 20), 83: (22, 18, 20),
              91: (2, 4, 4), 92: (7, 9, 5), 94: (14, 6, 14), 113: (5, 13, 13), 118: (7, 4, 5), 120: (7, 4, 4),
              174: (2, 6, 8), 232: (17, 18, 20), 236: (18, 2, 2), 245: (7, 6, 5), 246: (7, 6, 5), 247: (15, 6, 5)}
    for mid, want in expect.items():
        assert D.map_header(rom, mid)[1:] == want, (mid, D.map_name(mid), D.map_header(rom, mid))
    for mid in D.MAPS:                                   # every named map has a sane header (no unused slots)
        bank, tileset, h, w = D.map_header(rom, mid)
        assert bank <= 0x2D and tileset <= 23 and 1 <= w <= 80 and 1 <= h <= 80, (mid, D.map_name(mid))
    assert D.map_name(82) == "Rock Tunnel 1F" and D.map_name(92) == "Vermilion Gym"
    assert D.map_name(245) == "Lorelei's Room" and D.map_name(120) == "Champion's Room"


def test_hall_of_fame_milestone_uses_the_counter_not_the_box_number(emu):
    emu.metrics.restart("hof")
    emu.pyboy.memory[0xD5A0] = 1                       # switching PC box must not count
    emu.wait(1)
    assert "champion defeated (Hall of Fame)" not in [m.name for m in emu.metrics.milestones]
    emu.pyboy.memory[0xD5A2] = 1                       # wNumHoFTeams
    emu.wait(1)
    assert "champion defeated (Hall of Fame)" in [m.name for m in emu.metrics.milestones]


def test_starter_milestone(emu):
    emu.metrics.restart("starter")
    mem = emu.pyboy.memory
    mem[0xD163] = 1                                    # a Charmander appears in the (empty) party
    mem[0xD164] = 0xB0
    mem[0xD16B] = 0xB0
    emu.wait(1)
    names = [m.name for m in emu.metrics.milestones]
    assert names.count("starter: Charmander") == 1, names
    mem[0xD163] = 0
    emu.wait(1)
    mem[0xD163] = 1
    emu.wait(1)
    assert [m.name for m in emu.metrics.milestones].count("starter: Charmander") == 1   # never twice


def test_elite_four_defeat_milestone(emu):
    # Pure snapshot logic: the room ids and battle flags are fed in directly.
    prof = emu.profile
    base = emu.profile.snapshot()
    prev = {**base, "map": 174, "in_battle": 0}
    cur = {**base, "map": 245, "in_battle": 2}
    assert "reached: Lorelei's Room" in prof.milestones(prev, cur)
    won = {**cur, "in_battle": 0}
    assert "defeated: Lorelei" in prof.milestones(cur, won)
    lost = {**cur, "in_battle": 0xFF}
    out = prof.milestones(cur, lost)
    assert "blacked out (lost a battle)" in out and not any(n.startswith("defeated") for n in out)
    teleported = {**cur, "map": 174, "in_battle": 0}
    assert not any(n.startswith("defeated") for n in prof.milestones(cur, teleported))
    champ = {**base, "map": 120, "in_battle": 2}
    assert "defeated: Champion" in prof.milestones(champ, {**champ, "in_battle": 0})
    hof = {**champ, "in_battle": 0, "hall_of_fame": 1}
    assert "champion defeated (Hall of Fame)" in prof.milestones({**champ, "in_battle": 0}, hof)


def test_milestone_snapshot_includes_team(emu):
    emu.metrics.restart("team")
    mem = emu.pyboy.memory
    mem[0xD163] = 1                                    # one Bulbasaur L5 20/20
    mem[0xD164] = 0x99
    base = 0xD16B
    mem[base] = 0x99
    mem[base + 1], mem[base + 2] = 0, 20
    mem[base + 33] = 5
    mem[base + 34], mem[base + 35] = 0, 20
    mem[0xD356] = 0b00000001                           # Boulder badge
    emu.wait(1)
    m = next(m for m in emu.metrics.milestones if m.name == "badge: Boulder")
    team = m.snapshot["team"]
    assert team[0]["species"] == "Bulbasaur" and team[0]["level"] == 5 and len(team[0]["stats"]) == 4
    assert "owned_set" not in m.snapshot                # other lists are still dropped
    assert m.snapshot["party"] == ["Bulbasaur L5"]
