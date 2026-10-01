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


def _load_bedroom(e, in_game_state):
    with open(in_game_state, "rb") as f:
        e.pyboy.load_state(f)
    e.tick(2)
    e.profile.after_load()


def test_metrics_session_resumes_across_restarts(rom_path, scratch, in_game_state):
    from emulator import Emulator

    base = scratch / "resume"
    e = Emulator(str(rom_path), base_dir=base, autosave_every=2, save_screenshots=False, ai_model="m", session_id="run-abc")
    e.boot()
    _load_bedroom(e, in_game_state)
    e.press("A")
    e.walk("right 1")
    e.metrics.note("remember the SNES")
    frames = e.frame
    e.metrics.record_call("press", 10, False)
    e.metrics.record_call("walk", 10, False)
    e.stop()
    assert (base / "metrics" / "run-abc_checkpoint.json").exists()

    e2 = Emulator(str(rom_path), base_dir=base, autosave_every=2, save_screenshots=False, ai_model="m", session_id="run-abc")
    e2.boot(resume=True)
    assert e2.metrics.session_id == "run-abc" and e2.metrics.chunks == 2
    assert sum(e2.metrics.tool_calls.values()) == 2 and e2.frame >= frames
    assert e2.metrics.notes == ["remember the SNES"]
    e2.wait(1)
    d = e2.metrics.to_dict()
    assert d["frames"] > frames and d["chunks"] == 2 and "remember the SNES" in e2.metrics.summary()
    e2.pyboy.stop(save=False)
    e2.pyboy = None


def test_budget_exhausted_refuses_actions_and_finalizes(rom_path, scratch, in_game_state):
    from emulator import Emulator
    from server import build_server

    e = Emulator(str(rom_path), base_dir=scratch / "budget", autosave_every=0, save_screenshots=False,
                 ai_model="b", session_id="budget-1", max_tool_calls=3)
    e.boot()
    _load_bedroom(e, in_game_state)
    tools = {n: t.fn for n, t in build_server(e)._tool_manager._tools.items()}
    txt = lambda res: "\n".join(c.text for c in res if c.type == "text")  # noqa: E731
    assert txt(tools["press"](buttons="A", screenshot=False)).startswith("pressed")
    assert txt(tools["state"](section="summary"))
    assert txt(tools["wait"](frames=1, screenshot=False)).startswith("waited")
    out = txt(tools["walk"](path="right 1", screenshot=False))
    assert out.startswith("BUDGET EXHAUSTED"), out
    assert e.metrics.finalized and (e.metrics_dir / "budget-1.json").exists()
    assert txt(tools["metrics"](action="report")).startswith("session budget-1")     # reporting still works
    assert txt(tools["press"](buttons="A", screenshot=False)).startswith("BUDGET EXHAUSTED")
    e.pyboy.stop(save=False)
    e.pyboy = None


def test_frames_never_rewind_on_load_state(emu):
    emu.metrics.restart("frames")
    emu.save_state("t1")
    emu.walk("right 2")
    f = emu.frame
    emu.load_state("t1")
    assert emu.frame >= f
    assert emu.metrics.loads == 1 and "loaded state 't1'" in [m.name for m in emu.metrics.milestones]
    emu.wait(1)
    assert emu.metrics.to_dict()["frames"] > f


def test_world_graph_survives_restart(rom_path, scratch, in_game_state):
    from emulator import Emulator

    base = scratch / "world"
    e = Emulator(str(rom_path), base_dir=base, autosave_every=1, save_screenshots=False)
    e.boot()
    _load_bedroom(e, in_game_state)
    e.wait(1)                                              # snapshot the bedroom (map 38) into the graph
    assert "entered Red's House 1F" in e.walk("to Red's House 1F")
    assert "entered Pallet Town" in e.walk("to Pallet Town")
    e.stop()
    assert (base / "saves" / rom_path.stem / "world.json").exists()

    e2 = Emulator(str(rom_path), base_dir=base, autosave_every=1, save_screenshots=False)
    e2.boot(resume=True)
    assert e2.profile.position()[0] == 0 and {37, 38} <= set(e2.profile.world)
    r = e2.walk("to Red's House 2F")                       # two hops, known only from the saved graph
    assert "entered Red's House 2F" in r, r
    assert e2.profile.position()[0] == 38
    e2.pyboy.stop(save=False)
    e2.pyboy = None


def _encode(text: str) -> list[int]:
    from games import gen1_data as D
    rev = {v: k for k, v in D.CHARMAP.items() if len(v) == 1}
    return [rev[c] for c in text] + [0x50]


def _inject_mon(emu, slot: int, species: int, level: int, moves: list[int], hp: int = 30, nick: str = "MON"):
    """Write a party member straight into RAM (species is the internal index)."""
    from games import gen1_data as D
    mem = emu.pyboy.memory
    mem[D.PARTY_COUNT] = max(mem[D.PARTY_COUNT], slot + 1)
    mem[D.PARTY_COUNT + 1 + slot] = species
    mem[D.PARTY_COUNT + 2 + slot] = 0xFF
    base = D.PARTY_MONS + slot * D.PARTY_MON_SIZE
    for i in range(D.PARTY_MON_SIZE):
        mem[base + i] = 0
    mem[base + D.MON_SPECIES] = species
    mem[base + D.MON_HP], mem[base + D.MON_HP + 1] = hp >> 8, hp & 0xFF
    mem[base + D.MON_LEVEL] = level
    mem[base + 3] = level                                 # box level byte
    mem[base + D.MON_MAX_HP], mem[base + D.MON_MAX_HP + 1] = hp >> 8, hp & 0xFF
    for j in range(4):
        mem[base + D.MON_MOVES + j] = moves[j] if j < len(moves) else 0
        mem[base + D.MON_PP + j] = 20 if j < len(moves) else 0
    for j, stat in enumerate((20, 20, 20, 20)):
        mem[base + D.MON_ATTACK + 2 * j], mem[base + D.MON_ATTACK + 2 * j + 1] = 0, stat
    enc = _encode(nick.upper())
    for i, b in enumerate(enc):
        mem[D.PARTY_NICKS + slot * D.NAME_LEN + i] = b
    for i, b in enumerate(_encode("RED")):                # OT name
        mem[0xD273 + slot * D.NAME_LEN + i] = b


def _give_item(emu, item: int, qty: int = 1):
    from games import gen1_data as D
    mem = emu.pyboy.memory
    n = mem[D.BAG_COUNT] if mem[D.BAG_COUNT] <= 20 else 0
    mem[D.BAG_ITEMS + 2 * n], mem[D.BAG_ITEMS + 2 * n + 1] = item, qty
    mem[D.BAG_ITEMS + 2 * n + 2] = 0xFF
    mem[D.BAG_COUNT] = n + 1


def _to_pallet(emu):
    emu.walk("right 2, up 5, right 2")
    emu.walk("down 6, left 4, down 1")
    assert emu.profile.position()[0] == 0


def test_pathfinder_never_crosses_a_warp_en_route(emu):
    emu.walk("right 2, up 5, right 2")                     # Red's House 1F, arriving on the stairs
    prof = emu.profile
    warps = {(x, y) for x, y, _ in prof.warps()}
    cells = prof.full_map_cells()
    _, px, py = prof.position()
    row = len(cells) - 1                                   # bottom row holds the exit door tiles
    targets = [x for x in range(len(cells[0])) if cells[row][x] == "." and (x, row) not in warps]
    assert targets
    for tx in targets:
        segs = prof.find_path(tx, row)
        assert segs is not None
        x, y = px, py
        for d, n in segs:
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            for _ in range(n):
                x, y = x + dx, y + dy
                assert (x, y) not in warps or (x, y) == (tx, row), (tx, segs)
        assert (x, y) == (tx, row)
    r = emu.walk(f"to {targets[0]},{row}")
    assert r.startswith("arrived") and "entered" not in r, r


def test_water_marked_and_surf_field_move(emu):
    from games import gen1_data as D

    _to_pallet(emu)
    m = emu.state("map")
    rows = [ln[3:] for ln in m.split("\n")[2:20]]
    assert rows[15][5] == "~" and rows[15][6] == "~", m     # the pond south of town
    r = emu.walk("to 5,15")
    assert r.startswith("no walkable route") and "Surf" in r, r
    assert emu.walk("to 5,13").startswith("arrived")
    r = emu.walk("down 1")                                 # bump into the water
    assert "blocked" in r
    assert "Surf" in emu.profile.hint(), emu.profile.hint()
    assert "no Pokémon in the party knows Surf" in emu.manage("field", "Surf")
    _inject_mon(emu, 0, 0xB1, 30, [57, 33], nick="SQUIRTLE")   # Squirtle with Surf + Tackle
    emu.pyboy.memory[D.BADGES] |= 0x10                      # Soul Badge
    r = emu.manage("field", "Surf")
    assert emu.profile.surfing(), r
    assert "surfing" in r and emu.profile.position()[1:] == (5, 14)   # Surf steps onto the first water tile
    r = emu.walk("down 2")
    assert r.startswith("walked down 2/2"), r
    assert emu.profile.position()[1:] == (5, 16)
    assert emu.profile.find_path(6, 16) is not None         # water is walkable while surfing


def test_manage_use_teaches_hm_and_asks_which_move_to_forget(emu):
    from games import gen1_data as D

    _inject_mon(emu, 0, 0xB0, 12, [10, 45, 52, 43], nick="CHARMANDER")   # Scratch Growl Ember Leer
    _give_item(emu, 0xC4)                                                 # HM01 Cut
    r = emu.manage("use", "HM01", "Charmander")
    assert "Growl" in r and "move to forget" in r, r
    assert [n for n, _ in emu.profile.party()[0]["moves"]] == ["Scratch", "Growl", "Ember", "Leer"]
    assert not (emu.screen_text() or "").strip()                          # menus closed again
    r = emu.manage("use", "HM01", "Charmander: Growl")
    moves = [n for n, _ in emu.profile.party()[0]["moves"]]
    assert "Cut" in moves and "Growl" not in moves, (r, moves)
    assert "learned" in r.lower(), r
    assert D.item_name(emu.pyboy.memory[D.BAG_ITEMS]) == "HM01"           # HMs are not consumed
    assert not (emu.screen_text() or "").strip()
    _inject_mon(emu, 1, 0xB1, 12, [33], nick="SQUIRTLE")
    r = emu.manage("use", "HM01", "Squirtle")                              # Squirtle cannot learn Cut in Gen 1
    assert "can't learn" in r and [n for n, _ in emu.profile.party()[1]["moves"]] == ["Tackle"], r
    _inject_mon(emu, 2, 0x99, 12, [33], nick="BULBASAUR")
    r = emu.manage("use", "HM01", "Bulbasaur")                             # room for a 2nd move: no question asked
    assert "Cut" in [n for n, _ in emu.profile.party()[2]["moves"]], r


def test_manage_use_potion_on_named_pokemon(emu):
    _inject_mon(emu, 0, 0xB0, 12, [10], hp=30, nick="CHARMANDER")
    _inject_mon(emu, 1, 0xB1, 12, [33], hp=30, nick="SQUIRTLE")
    emu.pyboy.memory[0xD16B + 44 + 2] = 5                                  # Squirtle at 5/30
    _give_item(emu, 0x14, 2)                                               # Potion x2
    r = emu.manage("use", "Potion", "Squirtle")
    assert emu.profile.party()[1]["hp"] == 25, r
    assert "Potion×1" in r, r


def test_battle_reports_disabled_move(emu):
    from games import gen1_data as D
    mem = emu.pyboy.memory
    mem[D.IS_IN_BATTLE] = 1
    mem[D.BATTLE_MON] = 0xB0                                   # Charmeleon-ish: species + moves + pp
    for j, mv in enumerate((10, 45, 52, 43)):
        mem[D.BATTLE_MON + 8 + j] = mv
        mem[D.BATTLE_MON_PP + j] = 20
    mem[D.BATTLE_MON + 1], mem[D.BATTLE_MON + 2] = 0, 30
    mem[D.BATTLE_MON + 15], mem[D.BATTLE_MON + 16] = 0, 60
    mem[D.PLAYER_DISABLED_MOVE] = 0x34                          # slot 3 (Ember), 4 turns
    b = emu.profile.battle()
    assert b["mine"]["disabled"] == "Ember"
    assert "Ember 20pp DISABLED" in emu.profile._mon_line(b["mine"], True)
    mem[D.PLAYER_DISABLED_MOVE] = 0
    assert emu.profile.battle()["mine"]["disabled"] == ""
    mem[D.IS_IN_BATTLE] = 0


def test_find_path_avoid_cells_are_walls(emu):
    prof = emu.profile
    _, px, py = prof.position()
    segs = prof.find_path(7, 1)
    d, n = segs[0]
    dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
    first = (px + dx, py + dy)
    alt = prof.find_path(7, 1, avoid={first})
    assert alt is None or alt != segs
    if alt:
        x, y = px, py
        for d2, n2 in alt:
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d2]
            for _ in range(n2):
                x, y = x + dx, y + dy
                assert (x, y) != first


def test_resumed_session_does_not_repeat_landmarks(rom_path, scratch, in_game_state):
    from emulator import Emulator

    base = scratch / "seed"
    e = Emulator(str(rom_path), base_dir=base, autosave_every=1, save_screenshots=False, session_id="seed-1")
    e.boot()
    _load_bedroom(e, in_game_state)
    e.wait(1)
    assert "entered Red's House 1F" in e.walk("to Red's House 1F")
    assert "entered Pallet Town" in e.walk("to Pallet Town")
    names = [m.name for m in e.metrics.milestones]
    assert names.count("reached: Pallet Town") == 1
    e.stop()
    e2 = Emulator(str(rom_path), base_dir=base, autosave_every=1, save_screenshots=False, session_id="seed-1")
    e2.boot(resume=True)
    assert 0 in e2.profile._reported_maps
    e2.walk("to Red's House 1F")
    e2.walk("to Pallet Town")
    assert [m.name for m in e2.metrics.milestones].count("reached: Pallet Town") == 1
    e2.pyboy.stop(save=False)
    e2.pyboy = None


def test_unreachable_connection_is_explained(emu):
    _to_pallet(emu)
    prof = emu.profile
    real = prof.find_path
    prof.find_path = lambda *a, **k: None                  # pretend nothing on this map is reachable (trees, ledges)
    try:
        r = emu.walk("to Route 1")
    finally:
        prof.find_path = real
    assert "north edge" in r and "no walkable route" in r and "exits" in r, r
    r = emu.walk("to Route 1")                             # and the real route still works (Oak interrupts it)
    assert "entered" in r or "dialogue appeared" in r, r
