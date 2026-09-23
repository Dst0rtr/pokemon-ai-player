"""Pure-Python tests: no ROM or emulator needed."""


from emulator import _TOKEN, _WAIT, _WALK, BUTTONS, Emulator
from games import gen1_data as D


def test_button_tokens():
    m = _TOKEN.match("A*5")
    assert m and m.group("btn") == "A" and m.group("rep") == "5"
    m = _TOKEN.match("up:16")
    assert m and BUTTONS[m.group("btn").upper()] == "up" and m.group("hold") == "16"
    m = _TOKEN.match("Right x3:10")
    assert m and m.group("rep") == "3" and m.group("hold") == "10"
    assert _TOKEN.match("bogus") and _TOKEN.match("bogus").group("btn").upper() not in BUTTONS


def test_wait_tokens():
    assert _WAIT.match("W60").group("n") == "60"
    assert _WAIT.match("wait:120").group("n") == "120"
    assert _WAIT.match("WAIT 30") is None or _WAIT.match("WAIT 30").group("n") == "30"


def test_walk_tokens():
    assert _WALK.match("up5").group("n") == "5"
    assert _WALK.match("R3").group("dir").upper() == "R"
    assert _WALK.match("down").group("n") is None
    assert _WALK.match("sideways") is None


def test_parse_walk_path():
    segs = Emulator._parse_walk(None, "up 5, right 3;  L2")
    assert segs == [("up", 5), ("right", 3), ("left", 2)]
    assert Emulator._parse_walk(None, "up 5 right 2") == [("up", 5), ("right", 2)]
    assert Emulator._parse_walk(None, "up5 right2 down") == [("up", 5), ("right", 2), ("down", 1)]
    assert Emulator._parse_walk(None, "U5 R3") == [("up", 5), ("right", 3)]
    assert isinstance(Emulator._parse_walk(None, "north 2"), str)
    assert isinstance(Emulator._parse_walk(None, "up 0"), str)
    assert isinstance(Emulator._parse_walk(None, ""), str)
    assert Emulator._parse_walk(None, "up 999")[0][1] == 60  # clamped


def test_parse_addr():
    import pytest
    with pytest.raises(ValueError):
        Emulator._parse_addr("ZZZZ")
    with pytest.raises(ValueError):
        Emulator._parse_addr("10000")
    assert Emulator._parse_addr("D163") == 0xD163
    assert Emulator._parse_addr("0xd163") == 0xD163
    assert Emulator._parse_addr("$C100") == 0xC100
    assert Emulator._parse_addr(0x10) == 0x10


def test_gen1_tables():
    assert D.species_name(0x99) == "Bulbasaur"
    assert D.species_name(0xB0) == "Charmander"
    assert D.species_name(0x54) == "Pikachu"
    assert D.species_name(0x15) == "Mew"
    assert D.move_name(33) == "Tackle" and D.move_name(165) == "Struggle"
    assert D.item_name(4) == "Poké Ball" and D.item_name(0xC4) == "HM01" and D.item_name(0xC9) == "TM01"
    assert D.map_name(0) == "Pallet Town" and D.map_name(40) == "Oak's Lab"
    assert D.decode_text([0x91, 0x84, 0x83, 0x50, 0x80]) == "RED"
    assert D.decode_text([0x8F, 0xE1, 0xE2, 0x7F, 0xF6]) == "PPKMN 0"


def test_instructions_are_compact():
    from server import GUIDE
    assert len(GUIDE) < 1500, "keep the agent guide short: it is sent with every request"


def test_safari_battle_menu_cursor():
    from games.pokemon_gen1 import PokemonGen1Profile
    cur = PokemonGen1Profile._main_menu_cursor
    assert cur(None, "▶BALL×      BAIT\n THROW ROCK  RUN") == (0, 0)
    assert cur(None, " BALL×     ▶BAIT\n THROW ROCK  RUN") == (1, 0)
    assert cur(None, " BALL×      BAIT\n▶THROW ROCK  RUN") == (0, 1)
    assert cur(None, " BALL×      BAIT\n THROW ROCK ▶RUN") == (1, 1)
    assert cur(None, "▶FIGHT  PKMN\n ITEM   RUN") == (0, 0)
    assert cur(None, " FIGHT  PKMN\n ITEM  ▶RUN") == (1, 1)
    assert cur(None, "some text ▼") is None
