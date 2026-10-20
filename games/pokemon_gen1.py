"""
Profile for Pokémon Red / Blue / Yellow.

Everything here is read straight from WRAM/VRAM, so the agent can get party,
battle, map and dialogue information as a few lines of text instead of images.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from . import gen1_data as D
from .base import GameProfile, decode_visible_tilemap

# Pokédex order (bit index + 1) -> name; used to name new captures.
_DEX = ("Bulbasaur Ivysaur Venusaur Charmander Charmeleon Charizard Squirtle Wartortle Blastoise "
        "Caterpie Metapod Butterfree Weedle Kakuna Beedrill Pidgey Pidgeotto Pidgeot Rattata Raticate "
        "Spearow Fearow Ekans Arbok Pikachu Raichu Sandshrew Sandslash Nidoran♀ Nidorina Nidoqueen "
        "Nidoran♂ Nidorino Nidoking Clefairy Clefable Vulpix Ninetales Jigglypuff Wigglytuff Zubat "
        "Golbat Oddish Gloom Vileplume Paras Parasect Venonat Venomoth Diglett Dugtrio Meowth Persian "
        "Psyduck Golduck Mankey Primeape Growlithe Arcanine Poliwag Poliwhirl Poliwrath Abra Kadabra "
        "Alakazam Machop Machoke Machamp Bellsprout Weepinbell Victreebel Tentacool Tentacruel Geodude "
        "Graveler Golem Ponyta Rapidash Slowpoke Slowbro Magnemite Magneton Farfetch'd Doduo Dodrio "
        "Seel Dewgong Grimer Muk Shellder Cloyster Gastly Haunter Gengar Onix Drowzee Hypno Krabby "
        "Kingler Voltorb Electrode Exeggcute Exeggutor Cubone Marowak Hitmonlee Hitmonchan Lickitung "
        "Koffing Weezing Rhyhorn Rhydon Chansey Tangela Kangaskhan Horsea Seadra Goldeen Seaking "
        "Staryu Starmie Mr.Mime Scyther Jynx Electabuzz Magmar Pinsir Tauros Magikarp Gyarados Lapras "
        "Ditto Eevee Vaporeon Jolteon Flareon Porygon Omanyte Omastar Kabuto Kabutops Aerodactyl "
        "Snorlax Articuno Zapdos Moltres Dratini Dragonair Dragonite Mewtwo Mew").split()
assert len(_DEX) == 151
_DEX_BY_NAME = {n: i + 1 for i, n in enumerate(_DEX)}
_DEX_BY_NAME["Mr. Mime"] = _DEX_BY_NAME["Mr.Mime"]

# Maps worth reporting as "reached" milestones (towns, routes, dungeons).
_LANDMARKS = set(range(0, 37)) | {59, 82, 83, 94, 108, 113, 118, 120, 142, 156, 159, 165, 174, 181, 192, 194, 198,
                                  199, 217, 218, 219, 220, 228, 232, 245, 246, 247}

_BATTLE_KIND = {1: "wild", 2: "trainer"}
_STATUS_MOVES = {"Growl", "Tail Whip", "String Shot", "Leer", "Sand-Attack", "Harden", "Withdraw", "Defense Curl",
                 "PoisonPowder", "Stun Spore", "Sleep Powder", "Supersonic", "Sing", "Smokescreen", "Screech",
                 "Focus Energy", "Meditate", "Sharpen", "Agility", "Double Team", "Minimize", "Swords Dance",
                 "Thunder Wave", "Toxic", "Leech Seed", "Hypnosis", "Confuse Ray", "Glare", "Poison Gas",
                 "Lovely Kiss", "Spore", "Mist", "Haze", "Reflect", "Light Screen", "Recover", "Rest",
                 "Softboiled", "Amnesia", "Barrier", "Acid Armor", "Transform", "Substitute", "Roar", "Whirlwind",
                 "Teleport", "Splash", "Disable", "Mimic", "Kinesis", "Flash", "Growth", "Conversion", "Metronome",
                 "Mirror Move", "Bide", "Counter", "Rage"}   # Rage locks the user in for the whole battle (Gen 1)



# Gen 1 high-critical moves (Karate Chop, Razor Leaf, Crabhammer, Slash): 8x the critical rate, near-certain for a fast
# attacker, and a critical hit roughly doubles the damage; valued at 1.7x (Codex review 15: Strength 80 was preferred to
# Charizard's Slash, and Slash was the move forgotten for Earthquake)
HIGH_CRIT = {2: 1.7, 75: 1.7, 152: 1.7, 163: 1.7}

class PokemonGen1Profile(GameProfile):
    name = "pokemon-gen1"
    agent_hints = (
        "Pokémon Gen 1: dialogue and menus are returned as text after every action, so you rarely "
        "need images. Use walk() for movement (it stops when blocked and reports the map, exits and "
        "NPCs). Use state('party'|'battle'|'items'|'map') for decisions. In battle, FIGHT is the "
        "top-left option; the party/battle sections list moves with PP. Coordinates are (x,y) with y "
        "increasing downward."
    )

    def __init__(self, pyboy, options=None):
        super().__init__(pyboy, options)
        self.charmap = D.CHARMAP
        self.fast_text = self.options.get("fast_text", True)
        self.visited: set[int] = set()
        self._reported_maps: set[int] = set()
        self._battles = 0
        self._was_in_battle = False
        self._reported_owned: set[int] = set()  # dex numbers whose capture was already reported
        self._block_cache: dict[tuple[int, int, int], bytes] = {}
        self._coll_cache: dict[int, frozenset] = {}
        self._move_table: Optional[dict] = None   # move id -> (effect, power, type, accuracy); {} = not this ROM
        self._type_chart: dict[tuple[int, int], float] = {}
        self.world: dict[int, dict] = {}        # visited map id -> {"warps": [(x,y,dest)], "conns": [(side,dest)]}
        self.spinners: dict[int, dict] = {}     # map id -> {spinner cell: cell the slide ends on}, learned by walking
        self._starter_reported = False

    # ------------------------------------------------------------------ #
    # memory helpers
    # ------------------------------------------------------------------ #
    def _u8(self, a: int) -> int:
        return self.mem[a]

    def _u16(self, a: int) -> int:
        return (self.mem[a] << 8) | self.mem[a + 1]

    def _bytes(self, a: int, n: int) -> list[int]:
        return list(self.mem[a:a + n])

    def _str(self, a: int, n: int = D.NAME_LEN) -> str:
        return D.decode_text(self._bytes(a, n)).strip()

    def _bcd(self, a: int, n: int) -> int:
        v = 0
        for b in self._bytes(a, n):
            v = v * 100 + (b >> 4) * 10 + (b & 0xF)
        return v

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def after_load(self) -> None:
        self._enforce_options()
        self.visited.add(self._u8(D.CUR_MAP))
        if self.started():   # resumed/loaded game: what is already owned is not a new capture
            self._reported_owned |= self.dex_owned_set() & self.have_dex_numbers()
            if self.party():
                self._starter_reported = True

    def after_action(self) -> None:
        self._enforce_options()

    def scripted(self) -> bool:
        """True while a cutscene controls the player (directional input ignored)."""
        return self.started() and not self.in_battle() and (self._u8(D.JOY_IGNORE) & 0xF0) != 0

    def sliding(self) -> bool:
        return self.started() and bool(self._u8(D.MOVEMENT_FLAGS) & 0x80)

    def busy(self) -> bool:
        # The game blocks on jingles (item/Pokémon received, level up...) before polling input again,
        # and battle animations (slide-in, throws, attacks) ignore input until a menu or prompt shows.
        if any(self.mem[D.SFX_CHANNELS:D.SFX_CHANNELS + 4]):
            return True
        if self.in_battle():
            return self.battle_menu().startswith("animating")
        # a cutscene that ignores every button is moving things around: wait for it
        return self.started() and self._u8(D.JOY_IGNORE) == 0xFF

    def _enforce_options(self) -> None:
        # Text speed FAST, battle animations OFF, battle style SET (no "change POKéMON?" prompts):
        # all identical to the in-game OPTION menu.
        if self.fast_text:
            cur = self._u8(D.OPTIONS)
            want = 0x80 | 0x40 | 0x01
            if cur != want and self.started():  # only once the game has started
                self.mem[D.OPTIONS] = want

    # ------------------------------------------------------------------ #
    # basic readers
    # ------------------------------------------------------------------ #
    def started(self) -> bool:
        """True once a map is loaded (i.e. past the title screen / intro)."""
        return self.mem[0xC100] != 0 and self._u8(D.MAP_WIDTH) != 0 and self._u8(D.MAP_HEIGHT) != 0

    def map_label(self, map_id: int) -> str:
        return "outside" if map_id == 0xFF else D.map_name(map_id)

    def position(self) -> Optional[tuple]:
        return (self._u8(D.CUR_MAP), self._u8(D.PLAYER_X), self._u8(D.PLAYER_Y))

    def in_battle(self) -> int:
        return self._u8(D.IS_IN_BATTLE)

    def badges(self) -> int:
        return bin(self._u8(D.BADGES)).count("1")

    def money(self) -> int:
        return self._bcd(D.MONEY, 3)

    def playtime(self) -> str:
        return f"{self._u8(D.PLAY_TIME_HOURS)}:{self._u8(D.PLAY_TIME_MINUTES):02d}:{self._u8(D.PLAY_TIME_SECONDS):02d}"

    def dex_counts(self) -> tuple[int, int]:
        owned = sum(bin(b).count("1") for b in self._bytes(D.POKEDEX_OWNED, 19))
        seen = sum(bin(b).count("1") for b in self._bytes(D.POKEDEX_SEEN, 19))
        return owned, seen

    def dex_owned_set(self) -> set[int]:
        out = set()
        for i, b in enumerate(self._bytes(D.POKEDEX_OWNED, 19)):
            for bit in range(8):
                if b & (1 << bit):
                    n = i * 8 + bit + 1
                    if n <= 151:
                        out.add(n)
        return out

    def party(self) -> list[dict[str, Any]]:
        count = min(self._u8(D.PARTY_COUNT), 6)
        mons = []
        for i in range(count):
            base = D.PARTY_MONS + i * D.PARTY_MON_SIZE
            if self._u8(base + D.MON_SPECIES) == 0:   # slot reserved but not filled in yet
                continue
            moves = self._bytes(base + D.MON_MOVES, 4)
            pp = self._bytes(base + D.MON_PP, 4)
            t1, t2 = self._u8(base + D.MON_TYPE1), self._u8(base + D.MON_TYPE2)
            types = [D.TYPES.get(t1, "?")] + ([D.TYPES.get(t2, "?")] if t2 != t1 else [])
            mons.append({
                "species": D.species_name(self._u8(base + D.MON_SPECIES)),
                "nick": self._str(D.PARTY_NICKS + i * D.NAME_LEN),
                "level": self._u8(base + D.MON_LEVEL),
                "hp": self._u16(base + D.MON_HP),
                "max_hp": self._u16(base + D.MON_MAX_HP),
                "status": D.status_name(self._u8(base + D.MON_STATUS), self._u16(base + D.MON_HP)),
                "types": types,
                "moves": [(D.move_name(m), (pp[j] & 0x3F)) for j, m in enumerate(moves) if m],
                "stats": (self._u16(base + D.MON_ATTACK), self._u16(base + D.MON_DEFENSE),
                          self._u16(base + D.MON_SPEED), self._u16(base + D.MON_SPECIAL)),
            })
        return mons

    def box_species(self) -> list[str]:
        """Species names in the active PC box."""
        count = self._u8(D.BOX_COUNT)
        if count > 20:      # box not initialised yet
            return []
        names = []
        for i in range(count):
            sp = self._u8(D.BOX_SPECIES + i)
            if sp == 0xFF:
                break
            names.append(D.species_name(sp))
        return names

    def have_dex_numbers(self) -> set[int]:
        """Pokédex numbers of every species currently in the party or the active PC box."""
        names = [p["species"] for p in self.party()] + self.box_species()
        return {_DEX_BY_NAME[n] for n in names if n in _DEX_BY_NAME}

    def items(self) -> list[tuple[str, int]]:
        count = min(self._u8(D.BAG_COUNT), 20)
        out = []
        for i in range(count):
            item, qty = self._u8(D.BAG_ITEMS + 2 * i), self._u8(D.BAG_ITEMS + 2 * i + 1)
            if item == 0xFF:
                break
            out.append((D.item_name(item), qty))
        return out

    def _battle_mon(self, base: int, pp_addr: int, disabled_addr: int = 0) -> dict[str, Any]:
        moves = self._bytes(base + 8, 4)
        pp = self._bytes(pp_addr, 4)
        disabled = ""
        if disabled_addr:
            slot = self._u8(disabled_addr) >> 4            # high nibble: disabled move slot 1-4 (0 = none)
            if 1 <= slot <= 4 and moves[slot - 1]:
                disabled = D.move_name(moves[slot - 1])
        return {
            "disabled": disabled,
            "species": D.species_name(self._u8(base)),
            "hp": self._u16(base + 1), "max_hp": self._u16(base + 15),
            "level": self._u8(base + 14), "status": D.status_name(self._u8(base + 4), self._u16(base + 1)),
            "types": [D.TYPES.get(self._u8(base + 5), "?")] +
                     ([D.TYPES.get(self._u8(base + 6), "?")] if self._u8(base + 6) != self._u8(base + 5) else []),
            "moves": [(D.move_name(m), pp[j] & 0x3F) for j, m in enumerate(moves) if m],
        }

    def battle(self) -> Optional[dict[str, Any]]:
        kind = self.in_battle()
        if kind == 0:
            return None
        return {
            "kind": _BATTLE_KIND.get(kind, "battle"),
            "safari": self._u8(D.BATTLE_TYPE) == 2,
            "enemy": self._battle_mon(D.ENEMY_MON, D.ENEMY_MON_PP, D.ENEMY_DISABLED_MOVE),
            "mine": self._battle_mon(D.BATTLE_MON, D.BATTLE_MON_PP, D.PLAYER_DISABLED_MOVE),
        }

    def warps(self) -> list[tuple[int, int, int]]:
        n = min(self._u8(D.NUM_WARPS), 32)
        out = []
        for i in range(n):
            y, x, _, dest = self._bytes(D.WARPS + 4 * i, 4)
            out.append((x, y, dest))
        return out

    def npcs(self, balls: Optional[bool] = None) -> list[tuple[int, int]]:
        """Map cells of the sprites; balls=True only item balls still lying there, balls=False only the others (people,
        boulders; hidden ones included, as for walking)."""
        out, hidden = [], self.hidden_slots() if balls else set()     # walking keeps every slot (+40 per sprite)
        for i in range(1, 16):
            pic = self._u8(D.SPRITE_STATE_1 + 16 * i)
            if pic and i not in hidden and (balls is None or (pic == D.SPRITE_POKE_BALL) == balls):
                out.append((self._u8(D.SPRITE_STATE_2 + 16 * i + 5) - 4, self._u8(D.SPRITE_STATE_2 + 16 * i + 4) - 4))
        return out

    def hidden_slots(self) -> set[int]:
        """Sprite slots of this map's missable objects that are hidden: they keep their slot (and position) after a
        ball is taken or a person leaves (full run 63 walked to taken balls: "nothing to talk to here")."""
        out = set()
        for k in range(16):
            slot, idx = self._u8(D.MISSABLE_LIST + 2 * k), self._u8(D.MISSABLE_LIST + 2 * k + 1)
            if slot == 0xFF:
                break
            if self._u8(D.MISSABLE_FLAGS + idx // 8) >> (idx % 8) & 1:
                out.add(slot)
        return out

    def _draw_sprites(self, cells: list[list[str]]) -> None:
        """People as N, item balls as o, boulders as B (all on screen; each has its own sprite picture)."""
        h, w = len(cells), len(cells[0]) if cells else 0
        for mark, spots in (("N", self.npcs(False)), ("o", self.npcs(True)), ("B", self.boulders())):
            for nx, ny in spots:
                if 0 <= nx < w and 0 <= ny < h:
                    cells[ny][nx] = mark

    def boulders(self) -> list[tuple[int, int]]:
        """Map cells of the boulders (Strength pushes them)."""
        hidden = self.hidden_slots()
        return [(self._u8(D.SPRITE_STATE_2 + 16 * i + 5) - 4, self._u8(D.SPRITE_STATE_2 + 16 * i + 4) - 4)
                for i in range(1, 16) if self._u8(D.SPRITE_STATE_1 + 16 * i) == D.SPRITE_BOULDER and i not in hidden]

    def facing(self) -> str:
        return D.FACING.get(self._u8(D.SPRITE_STATE_1 + 9), "?")

    # ------------------------------------------------------------------ #
    # text / formatting
    # ------------------------------------------------------------------ #
    def font_loaded(self) -> bool:
        return bytes(self.mem[D.FONT_A_ADDR:D.FONT_A_ADDR + 16]) == D.FONT_A_TILE

    def screen_text(self) -> Optional[str]:
        if not self.font_loaded():
            return ""
        raw = decode_visible_tilemap(self.pyboy, self.charmap)
        lines = [ln for ln in raw.split("\n") if ln.strip()]
        return "\n".join(lines)

    def dialog_text(self) -> str:
        """Text in the bottom message box only (screen rows 12-17)."""
        if not self.font_loaded():
            return ""
        raw = decode_visible_tilemap(self.pyboy, self.charmap).split("\n")
        return " ".join(ln.strip() for ln in raw[12:18] if ln.strip()).replace("▼", "").strip()

    @staticmethod
    def _norm(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    @staticmethod
    def _mon_line(m: dict[str, Any], with_moves: bool = False) -> str:
        name = m["species"] if not m.get("nick") or m.get("nick") == m["species"].upper() else f"{m['nick']}({m['species']})"
        st = f" {m['status']}" if m["status"] else ""
        s = f"{name} L{m['level']} {m['hp']}/{m['max_hp']}{st}"
        if with_moves:
            dis = m.get("disabled", "")
            s += " [" + ", ".join(f"{n} {p}pp" + (" DISABLED" if n == dis else "") for n, p in m["moves"]) + "]"
        return s

    def status_line(self) -> str:
        if not self.started():
            return "intro/title (no map loaded yet)"
        b = self.battle()
        if b:
            if self.in_safari_battle() and b["enemy"]["max_hp"] and "Safari" in (menu := self.battle_menu()):
                # no Pokémon of yours is sent out in the Safari Zone: its menu is the whole battle (Codex review 10: the
                # "starting" line hid it, and Jev pressed A through runs 75/76's Safari battles, 100+ decisions)
                return f"BATTLE ({b['kind']}): enemy {self._mon_line(b['enemy'])} | you (none in the Safari Zone) | {menu}"
            if b["enemy"]["max_hp"] == 0 or b["mine"]["max_hp"] == 0 or b["mine"]["species"].startswith("MissingNo(0"):
                who = f"wild {b['enemy']['species']} appeared" if b["kind"] == "wild" and b["enemy"]["max_hp"] else "trainer challenge"
                return f"BATTLE ({b['kind']}) starting: {who} (press A / wait)"
            return (f"BATTLE ({b['kind']}): enemy {self._mon_line(b['enemy'])} | "
                    f"you {self._mon_line(b['mine'], True)} | {self.battle_menu()}")
        m, x, y = self.position()
        party = self.party()
        lead = self._mon_line(party[0]) if party else "no party"
        if len(party) > 1:
            rest = ", ".join(f"{p['species']} L{p['level']}" + (" FNT" if p["hp"] == 0 else "") for p in party[1:])
            lead += f" (+{rest})"
        return f"{D.map_name(m)} ({x},{y}) facing {self.facing()} | {lead} | ¥{self.money()} | {self.badges()} badges"

    def battle_menu(self) -> str:
        """Which battle prompt is active, judged from the on-screen text."""
        txt = self.screen_text() or ""
        if "FIGHT" in txt and "RUN" in txt:
            return "menu: FIGHT/PKMN/ITEM/RUN (cursor on " + ("FIGHT" if "▶FIGHT" in txt else "PKMN" if "▶PKMN" in txt else "ITEM" if "▶ITEM" in txt else "RUN") + ")"
        if "BAIT" in txt and "RUN" in txt:
            return "menu: BALL/BAIT/ROCK/RUN (Safari: cursor on " + ("BALL" if "▶BALL" in txt else "BAIT" if "▶BAIT" in txt else "ROCK" if ("▶THROW" in txt or "▶ROCK" in txt) else "RUN") + ")"
        if "TYPE/" in txt:
            return "menu: choose a move (UP/DOWN then A, B to go back)"
        if "▶" in txt:
            return "menu: list open (UP/DOWN then A, B to go back)"
        if "▼" in txt:
            return "text: press A"
        return "animating: press A or wait"

    def sections(self) -> list[str]:
        return ["summary", "map", "nearby", "party", "battle", "items", "full"]

    def state(self, section: str = "summary") -> str:
        section = (section or "summary").lower()
        if section == "summary" or not self.started():
            return self.status_line()
        if section == "party":
            return self.party_text()
        if section == "battle":
            b = self.battle()
            if not b:
                return "not in battle"
            if b["enemy"]["max_hp"] == 0 or b["mine"]["max_hp"] == 0 or b["mine"]["species"].startswith("MissingNo(0"):
                return f"{b['kind']} battle starting (press A / wait)"
            return (f"{b['kind']} battle{' (safari)' if b['safari'] else ''}\n"
                    f"enemy: {self._mon_line(b['enemy'], True)} types {'/'.join(b['enemy']['types'])}\n"
                    f"you:   {self._mon_line(b['mine'], True)} types {'/'.join(b['mine']['types'])}")
        if section == "items":
            its = self.items()
            return ("bag: " + ", ".join(f"{n}×{q}" for n, q in its)) if its else "bag: empty"
        if section == "map":
            return self.full_map_text()
        if section == "nearby":
            return self.map_text()
        if section == "full":
            owned, seen = self.dex_counts()
            badges = [D.BADGE_NAMES[i] for i in range(8) if self._u8(D.BADGES) & (1 << i)]
            parts = [
                self.status_line(),
                f"player {self._str(D.PLAYER_NAME)} rival {self._str(D.RIVAL_NAME)} | playtime {self.playtime()} | "
                f"dex {owned} owned/{seen} seen | badges: {', '.join(badges) or 'none'}",
                self.party_text(),
                self.state("items"),
            ]
            if self.in_battle():
                parts.append(self.state("battle"))
            else:
                parts.append(self.full_map_text())
            return "\n".join(parts)
        return f"unknown section '{section}'; use one of {', '.join(self.sections())}"

    def party_text(self) -> str:
        party = self.party()
        if not party:
            return "party: none"
        lines = []
        for i, m in enumerate(party, 1):
            a, d, s, sp = m["stats"]
            lines.append(f"{i}. {self._mon_line(m, True)} {'/'.join(m['types'])} atk{a} def{d} spd{s} spc{sp}")
        box = self.box_species()
        if box:
            lines.append("PC box: " + ", ".join(box))
        return "party:\n" + "\n".join(lines)

    # ------------------------------------------------------------------ #
    # map view (10x9 walkability grid around the player)
    # ------------------------------------------------------------------ #
    def map_text(self) -> str:
        """10x9 window of the full map centred on the player."""
        if self.in_battle() or not self.started():
            return "(no map: not in overworld)"
        m, px, py = self.position()
        try:
            cells = self.full_map_cells()
        except Exception:
            return f"{D.map_name(m)} ({px},{py})"
        h, w = len(cells), len(cells[0]) if cells else 0
        for wx, wy, _ in self.warps():
            if 0 <= wx < w and 0 <= wy < h:
                cells[wy][wx] = "D"
        self._draw_sprites(cells)
        rows = []
        for r in range(9):
            y = py + r - 4
            row = ""
            for c in range(10):
                x = px + c - 4
                row += "P" if (x, y) == (px, py) else (cells[y][x] if 0 <= x < w and 0 <= y < h else "#")
            rows.append(row)
        near = [f"({wx},{wy})→{self.map_label(d)}" for wx, wy, d in self.warps() if abs(wx - px) <= 6 and abs(wy - py) <= 6]
        head = f"{D.map_name(m)} ({px},{py}) facing {self.facing()}, window x{px - 4}..{px + 5} y{py - 4}..{py + 4}"
        tail = ("\nexits here: " + ", ".join(near[:6])) if near else ""
        return head + "\n" + "\n".join(rows) + tail

    # ------------------------------------------------------------------ #
    # battle automation (used by the `battle` tool)
    # ------------------------------------------------------------------ #
    def _main_menu_cursor(self, txt: str) -> Optional[tuple[int, int]]:
        """(col, row) of the ▶ cursor in the battle menu: FIGHT/PKMN/ITEM/RUN or Safari BALL/BAIT/ROCK/RUN."""
        for ln in txt.split("\n"):
            if "FIGHT" in ln and "PKMN" in ln:
                if "▶FIGHT" in ln:
                    return (0, 0)
                if "▶PKMN" in ln:
                    return (1, 0)
            if "ITEM" in ln and "RUN" in ln:
                if "▶ITEM" in ln:
                    return (0, 1)
                if "▶RUN" in ln:
                    return (1, 1)
            if "BALL" in ln and "BAIT" in ln:
                if "▶BALL" in ln:
                    return (0, 0)
                if "▶BAIT" in ln:
                    return (1, 0)
            if "ROCK" in ln and "RUN" in ln:
                if "▶THROW" in ln or "▶ROCK" in ln:
                    return (0, 1)
                if "▶RUN" in ln:
                    return (1, 1)
        return None

    def in_safari_battle(self) -> bool:
        return self.in_battle() != 0 and self._u8(D.BATTLE_TYPE) == 2

    def _list_cursor(self, txt: str, entries: list[str]) -> Optional[int]:
        """Index of the entry marked with ▶ among `entries` (normalised names)."""
        for ln in txt.split("\n"):
            if "▶" in ln:
                label = self._norm(ln.split("▶", 1)[1])
                for i, e in enumerate(entries):
                    if e and label.startswith(e[:6]):
                        return i
        return None

    def _collect(self, seen: list[str]) -> None:
        """Record the message box text; a box that is still printing replaces its own prefix."""
        d = self.dialog_text()
        if not d or d in seen[-3:] or ("FIGHT" in d and "RUN" in d) or d.startswith(("▶", "▷")):
            return
        while seen and (d.startswith(seen[-1]) or seen[-1].startswith(d)):
            seen.pop()
        seen.append(d)

    def _classify(self, txt: str) -> Optional[str]:
        if not self.in_battle():
            return "over"
        if self._main_menu_cursor(txt) is not None:
            return "main"
        if "Bring out which" in txt or ("Use next" in txt and "▶" in txt):
            return "choose"
        if "▶YES" in txt or "▶NO" in txt:
            return "prompt"
        if "▶" in txt and ("forgotten" in txt or "Abandon" in txt or "Which move" in txt):
            return "prompt"
        return None

    def _move_value(self, name: str) -> float:
        """Rough worth of a move: power x accuracy, two-turn/recharge/self-KO moves at half or less; status moves 0."""
        table = self._load_move_data()
        ids = {self._norm(D.move_name(i)): i for i in range(1, 166)}
        eff, power, _, acc = table.get(ids.get(self._norm(name), 0), (0, 0, 0, 255))
        v = power * (acc / 255 if acc else 1) * HIGH_CRIT.get(ids.get(self._norm(name), 0), 1.0)
        if eff in (D.EFFECT_CHARGE, D.EFFECT_FLY, D.EFFECT_HYPER_BEAM):
            v /= 2
        elif eff == D.EFFECT_SELF_KO:
            v /= 4
        return v

    def _move_type(self, name: str) -> int:
        table = self._load_move_data()
        ids = {self._norm(D.move_name(i)): i for i in range(1, 166)}
        return table.get(ids.get(self._norm(name), 0), (0, 0, -1, 0))[2]

    def _forget_choice(self, moves: list[str], new: str = "") -> Optional[int]:
        """Which known move to forget for `new` (index into `moves`), or None to keep the old moves: the set kept is the
        one with the best attack per type (sum over types of the strongest move of each), HMs never go; on a tie a move
        of the new move's type goes first, then the weaker one (Codex 7: raw power deleted Slash for Fire Blast with
        Flamethrower kept, and Fire Spin was learned over Slash). Without `new`, the weakest move by that measure."""
        keep = {self._norm(m) for m in D.FIELD_MOVES}

        def score(ms: list[str]) -> float:
            best: dict[int, float] = {}
            for m in ms:
                v = self._move_value(m)
                if v > 0:
                    t = self._move_type(m)
                    best[t] = max(best.get(t, 0), v)
            return sum(best.values())
        cands = [j for j, m in enumerate(moves) if self._norm(m) not in keep]
        if not cands:
            return None
        if not new or self._norm(new) in keep:            # an HM is taught for the field: the weakest move goes
            return min(cands, key=lambda j: (self._move_value(moves[j]), j))
        now = score(moves)
        nt = self._move_type(new)
        ranked = sorted(cands, key=lambda j: (-score([m for k, m in enumerate(moves) if k != j] + [new]),
                                              self._move_type(moves[j]) != nt, self._move_value(moves[j])))
        j = ranked[0]
        return j if score([m for k, m in enumerate(moves) if k != j] + [new]) > now else None

    _LEARN_WORDS = ("learn", "forgot", "forget", "poof", "1, 2", "make room", "abandon", "trying to", "older move")

    def _learner(self, txt: str) -> Optional[dict[str, Any]]:
        """The party Pokémon learning the move: wWhichPokemon, checked against the move list on screen (Codex 6: the
        Pokémon in battle is not always the learner); else the member whose moves the list shows."""
        party = self.party()
        listed = {self._norm(ln.replace("▶", "")) for ln in txt.split("\n") if ln.strip()}
        fits = lambda m: bool(m["moves"]) and all(self._norm(n) in listed for n, _ in m["moves"])  # noqa: E731
        idx = self._u8(D.WHICH_POKEMON)
        if idx < len(party) and fits(party[idx]):
            return party[idx]
        return next((m for m in party if fits(m)), party[idx] if idx < len(party) else None)

    def _learn_prompt(self, emu, learn: bool) -> str:
        """battle('learn') / battle('skip') on a level-up move prompt: learn it and forget the weakest move (status
        moves first, then the least power; HM moves stay), or keep the old moves (run 75: Charizard L36+ never learned
        Flamethrower; generic cursor presses tried to delete Cut, an HM, and gave up). It stops at the battle menu or
        any text that is not about the move (Codex 6: pressing A through the menu attacked three times)."""
        seen: list[str] = []
        new_move = ""
        for _ in range(16):
            txt, d = self.screen_text() or "", (self.dialog_text() or "").lower()
            if self.in_battle() and self._classify(txt) in ("main", "choose"):
                break
            nm = re.search(r"(?:make\s+room\s+for|learn)\s+([A-Z][A-Z0-9\- ]+?)[?!.]", " ".join(txt.split()))
            if nm and not new_move:
                new_move = nm[1].strip()
            if "▶YES" in txt or "▶NO" in txt:
                self._collect(seen)
                if "abandon" in d:
                    emu.press("DOWN A" if learn else "A", settle=1)   # learn: do not abandon; skip: abandon
                else:                                     # "Delete an older move to make room for X?"
                    emu.press("A" if learn else "DOWN A", settle=1)
                continue
            if "▶" in txt and ("forgotten" in d or "which move" in d):
                if not learn:
                    emu.press("B", settle=1)
                    continue
                mon = self._learner(txt)
                if not mon:
                    emu.press("B", settle=1)
                    continue
                names = [self._norm(n) for n, _ in mon["moves"]]
                k = self._forget_choice([n for n, _ in mon["moves"]], new_move)
                if k is None:
                    emu.press("B", settle=1)              # only HMs, or nothing better: keep the old moves
                    learn = False
                    continue
                seen.append(f"forgot {mon['moves'][k][0]}")
                cur = self._list_cursor(txt, names) or 0
                if k != cur:
                    emu.press(("DOWN " if k > cur else "UP ") * abs(k - cur), settle=1)
                emu.press("A", settle=1)
                continue
            if self.is_text_visible() and d.strip() and ("▼" in txt or any(w in d for w in self._LEARN_WORDS)):
                self._collect(seen)
                emu.press("A", settle=1)
                continue
            break
        return " | ".join(x for x in seen if x) or "no move prompt on screen"

    def _watch(self, emu, seen: list[str], max_frames: int = 420) -> Optional[str]:
        """Advance in small steps collecting message text until a menu/prompt shows or things go quiet."""
        quiet = 0
        for _ in range(max_frames // 6):
            emu.tick(6)
            self._collect(seen)
            kind = self._classify(self.screen_text() or "")
            if kind:
                return kind
            if any(self.mem[D.SFX_CHANNELS:D.SFX_CHANNELS + 4]):
                quiet = 0
                continue
            quiet += 1
            if quiet >= 8 and "▼" in (self.screen_text() or ""):
                return None                      # text waiting for A
            if quiet >= 30:
                return None
        return None

    def _wait_menu(self, emu, max_presses: int = 14) -> tuple[str, str]:
        """Press A through text until a menu/prompt shows or the battle ends. Returns (kind, text)."""
        seen: list[str] = []
        self._collect(seen)
        for _ in range(max_presses):
            kind = self._classify(self.screen_text() or "")
            if kind == "prompt":
                return kind, " | ".join(seen + [self.dialog_text()])
            if kind:
                return kind, " | ".join(seen)
            txt = self.screen_text() or ""
            if "▶" in txt:               # some other list is open: back out of it
                emu.press("B", settle=1)
                continue
            emu.pyboy.button_press("a"); emu.tick(8); emu.pyboy.button_release("a")
            kind = self._watch(emu, seen)
            if kind == "prompt":
                return kind, " | ".join(seen + [self.dialog_text()])
            if kind:
                return kind, " | ".join(seen)
        return "stuck", " | ".join(seen)

    def _select_main(self, emu, target: tuple[int, int]) -> bool:
        for _ in range(4):
            cur = self._main_menu_cursor(self.screen_text() or "")
            if cur is None:
                return False
            if cur == target:
                return True
            dx, dy = target[0] - cur[0], target[1] - cur[1]
            script = " ".join(([("RIGHT" if dx > 0 else "LEFT")] if dx else []) + ([("DOWN" if dy > 0 else "UP")] if dy else []))
            emu.press(script, settle=1)
        return self._main_menu_cursor(self.screen_text() or "") == target

    def _load_move_data(self) -> dict:
        if self._move_table is None:
            self._move_table = {}
            bank, a = D.MOVES_TABLE
            raw = bytes(self.mem[bank, a:a + 6 * 165])
            tb, ta = D.TYPE_EFFECTS_TABLE
            chart = bytes(self.mem[tb, ta:ta + 3 * 90])
            if raw.startswith(D.MOVES_SIGNATURE) and chart.startswith(D.TYPE_EFFECTS_SIGNATURE):
                for i in range(165):
                    mid, eff, power, typ, acc, _ = raw[6 * i:6 * i + 6]
                    self._move_table[mid] = (eff, power, typ, acc)
                for i in range(0, len(chart) - 2, 3):
                    if chart[i] == 0xFF:
                        break
                    self._type_chart[(chart[i], chart[i + 1])] = chart[i + 2] / 10
        return self._move_table

    def _auto_move(self, target: str = "") -> Optional[str]:
        """The move battle('auto') uses: `target` if named, else the damaging move with the best expected
        damage this turn (Gen 1 formula from the battle structs' stats, STAB, type chart, accuracy, capped
        at the enemy's HP), skipping moves the enemy is immune to, two-turn moves at half value and
        Self-Destruct/Explosion unless nothing else works; among equally good moves, the one with most PP.
        None when no move with PP left can hurt the enemy (Normal moves against a Ghost)."""
        b = self.battle()
        if not b or not b["mine"]["moves"]:
            return ""
        mine, foe = b["mine"], b["enemy"]
        ids = self._bytes(D.BATTLE_MON + 8, 4)
        usable = [(n, pp, ids[j]) for j, (n, pp) in enumerate(mine["moves"]) if pp > 0 and n != mine.get("disabled")]
        wanted = next((n for n, _, _ in usable if target and self._norm(target) in self._norm(n)), None)
        dmg = [(n, mid, pp) for n, pp, mid in usable if n not in _STATUS_MOVES]
        fallback = wanted or (dmg[0][0] if dmg else (usable[0][0] if usable else ""))
        table = self._load_move_data()
        if wanted or not dmg or not table:
            return fallback
        st = lambda base, k: self._u16(base + 17 + 2 * k)          # noqa: E731  attack, defense, speed, special
        lvl, foe_hp = mine["level"], max(foe["hp"], 1)
        my_types = {self._u8(D.BATTLE_MON + 5), self._u8(D.BATTLE_MON + 6)}
        foe_types = {self._u8(D.ENEMY_MON + 5), self._u8(D.ENEMY_MON + 6)}
        asleep = self._u8(D.ENEMY_MON + 4) & 0x07

        def score(mid: int) -> float:
            eff, power, typ, acc = table.get(mid, (0, 0, 0, 255))
            mult = 1.0
            for t in foe_types:
                mult *= self._type_chart.get((typ, t), 1.0)
            if mult == 0 or (eff == D.EFFECT_DREAM_EATER and not asleep):
                return 0.0
            if eff == D.EFFECT_FIXED:
                dmg_ = {82: 40, 49: 20}.get(mid, lvl)              # Dragon Rage, SonicBoom; else = level
            elif eff == D.EFFECT_SUPER_FANG:
                dmg_ = foe_hp / 2
            elif eff == D.EFFECT_OHKO:
                dmg_ = foe_hp if st(D.BATTLE_MON, 2) >= st(D.ENEMY_MON, 2) else 0   # fails on a faster foe
            else:
                special = typ >= D.SPECIAL_TYPES_FROM
                atk = st(D.BATTLE_MON, 3 if special else 0)
                dfn = max(st(D.ENEMY_MON, 3 if special else 1), 1)
                dmg_ = ((2 * lvl // 5 + 2) * power * atk / dfn / 50 + 2) * (1.5 if typ in my_types else 1) * mult
                dmg_ *= HIGH_CRIT.get(mid, 1.0)
            value = min(dmg_, foe_hp) * acc / 255
            if eff in (D.EFFECT_CHARGE, D.EFFECT_FLY) or (eff == D.EFFECT_HYPER_BEAM and dmg_ < foe_hp):
                value /= 2
            if eff == D.EFFECT_SELF_KO:
                value *= 0.01
            return value

        # equal value (typically: several moves knock out) -> the one with the most PP left
        best = max(dmg, key=lambda m: (round(score(m[1]), 1), m[2]))
        return best[0] if score(best[1]) > 0 else None

    def battle_auto(self, emu, target: str = "") -> str:
        """Fight with damaging moves until the battle ends, a prompt appears, or HP gets low."""
        logs: list[str] = []
        if self.in_safari_battle():
            return "Safari Zone battle: there is no FIGHT. battle('item') throws a Safari Ball, battle('bait') / battle('rock') change catch odds, battle('run') leaves"
        first_foe = None
        for turn in range(25):
            if not self.in_battle():
                break
            b = self.battle()
            if b and b["mine"]["max_hp"] and b["mine"]["hp"] <= b["mine"]["max_hp"] // 4 and turn:
                return " | ".join(logs) + f" — stopped: {b['mine']['species']} is low on HP ({b['mine']['hp']}/{b['mine']['max_hp']}); switch, use an item, run, or battle('auto') again to keep going"
            # a trainer's next Pokémon is a new matchup: hand it back (switch, item, or auto again) before attacking it
            # (Codex review 15: in league-leg-6 one auto call ran from Lorelei's Dewgong into her Cloyster and on)
            foe = (b["enemy"]["species"], b["enemy"]["max_hp"]) if b and b["enemy"]["max_hp"] else None
            if b and b.get("kind") == "trainer" and foe:
                if first_foe is None:
                    first_foe = foe
                elif foe != first_foe and turn:
                    return " | ".join(logs) + f" — stopped: the trainer sent out {b['enemy']['species']} (L{b['enemy']['level']}); switch, use an item, or battle('auto') again"
            move = self._auto_move(target) if b else ""
            if move is None:
                # (Codex review 18: Flamethrower out of PP, Strength and Slash on Tower 6F's Gastly and Haunter, turn after turn)
                return " | ".join(logs + [f"stopped: no move with PP left can affect {b['enemy']['species']}; switch, use an item, or run"])
            r = self.battle_action(emu, "fight", move)
            logs.append(r)
            if b and b.get("kind") == "trainer" and re.search(r"Enemy [^|]*fainted", r) and self.in_battle() \
                    and "battle over" not in r:
                # its next Pokémon may be the same species (Lance's two Dragonair: Codex review 16): hand back now
                return " | ".join(logs) + " — stopped: the trainer is sending out its next Pokémon; switch, use an item, or battle('auto') again"
            if ("needs a decision" in r or "prompt" in r or "battle('switch'" in r or "battle over" in r
                    or "battle is over" in r or r.startswith(("cannot", "could not", "no move", "no PP"))):
                break
        out = " | ".join(logs)
        return out if out else ("not in a battle" if not self.in_battle() else "nothing happened")

    def battle_action(self, emu, action: str, target: str = "") -> str:
        action = (action or "fight").lower().strip()
        if action == "auto":
            return self.battle_auto(emu, target)
        if action in ("learn", "skip"):                   # the "Delete an older move to make room for X?" prompt
            return self._learn_prompt(emu, action == "learn")
        if not self.in_battle():
            return "not in a battle"
        kind, prelog = self._wait_menu(emu)
        log = prelog
        if kind == "over":
            return "battle is over" + (f": {log}" if log else "")
        if kind == "prompt":
            return f"needs a decision: {log} — answer with press (A = YES / first option, DOWN A = NO)"
        if kind == "stuck":
            return f"could not reach a menu: {log}"
        if kind == "choose" and action != "switch":
            emu.press("B", settle=1)                      # optional list (e.g. after "change POKéMON?"): back out
            kind, extra = self._wait_menu(emu)
            log = (log + " | " + extra) if extra else log
            if kind == "choose":
                return "a Pokémon must be chosen (yours fainted): use battle('switch', n)"
            if kind == "over":
                return "battle is over" + (f": {log}" if log else "")
        b = self.battle()
        before = (b["enemy"]["hp"], b["mine"]["hp"], b["mine"]["species"]) if b else None

        safari = self.in_safari_battle()
        if action in ("bait", "rock") and not safari:
            return "bait/rock only exist in Safari Zone battles"
        if action == "fight" and safari:
            return "Safari Zone battle: no FIGHT here. battle('item') throws a Safari Ball, 'bait', 'rock' or 'run'"
        if action == "run":
            if kind != "main" or not self._select_main(emu, (1, 1)):
                return "cannot run now"
            emu.press("A", settle=1)
        elif action in ("bait", "rock"):
            if kind != "main" or not self._select_main(emu, (1, 0) if action == "bait" else (0, 1)):
                return f"cannot {action} now"
            emu.press("A", settle=1)
        elif action == "item" and safari:
            if kind != "main" or not self._select_main(emu, (0, 0)):
                return "cannot throw a ball now"
            emu.press("A", settle=1)
        elif action == "fight":
            if kind != "main" or not self._select_main(emu, (0, 0)):
                return "cannot fight now"
            emu.press("A", settle=1)
            moves = [self._norm(n) for n, _ in b["mine"]["moves"]] if b else []
            pps = [pp for _, pp in b["mine"]["moves"]] if b else []
            if pps and all(pp == 0 for pp in pps):
                # no PP anywhere: the game skips the move list and uses Struggle
                kind, log2 = self._wait_menu(emu)
                b2 = self.battle()
                note = "no PP left on any move: used Struggle"
                if kind == "over" or b2 is None:
                    return note + " | " + (log2 + " | " if log2 else "") + "battle over — " + self.status_line()
                return note + (" | " + log2 if log2 else "")
            idx = next((i for i, pp in enumerate(pps) if pp > 0), 0)      # default: first move with PP
            if target:
                t = self._norm(target)
                if t.isdigit():
                    idx = max(1, min(int(t), 4)) - 1
                else:
                    matches = [i for i, m in enumerate(moves) if m.startswith(t) or t in m]
                    if not matches:
                        emu.press("B", settle=1)
                        return f"no move '{target}'; moves: " + ", ".join(n for n, _ in b["mine"]["moves"])
                    idx = matches[0]
            if idx >= len(moves):
                emu.press("B", settle=1)
                return f"no move #{idx + 1}; moves: " + ", ".join(n for n, _ in b["mine"]["moves"])
            if pps[idx] == 0:
                emu.press("B", settle=1)
                usable = [n for n, pp in b["mine"]["moves"] if pp > 0]
                return (f"no PP left for {b['mine']['moves'][idx][0]}; usable: " + (", ".join(usable) or "none (only Struggle)")
                        + " — pick another move, switch, or heal at a Poké Center")
            if b["mine"]["moves"][idx][0] == b["mine"].get("disabled"):
                emu.press("B", settle=1)
                usable = [n for n, pp in b["mine"]["moves"] if pp > 0 and n != b["mine"]["disabled"]]
                return (f"{b['mine']['disabled']} is DISABLED by the enemy for a few turns; usable: "
                        + (", ".join(usable) or "none") + " — pick another move or switch")
            cur = self._list_cursor(self.screen_text() or "", moves) or 0
            steps = idx - cur
            if steps:
                emu.press(("DOWN " if steps > 0 else "UP ") * abs(steps), settle=1)
            emu.press("A", settle=1)
        elif action == "switch":
            if "Use next" in (self.screen_text() or ""):     # YES/NO question first
                emu.press("A", settle=1)
                self._watch(emu, [])
            party = self.party()
            t = self._norm(target)
            if t.isdigit():
                idx = max(1, min(int(t), len(party))) - 1
            else:
                found = self._party_match(target, party)
                if found is None:
                    return "which Pokémon? give its party number or name: " + ", ".join(f"{i + 1}={p['species']}" for i, p in enumerate(party))
                idx = found
            cur_idx = self._u8(D.PLAYER_MON_NUMBER)
            cur_hp = b["mine"]["hp"] if b else None
            if party[idx]["hp"] == 0 or (idx == cur_idx and cur_hp == 0):   # the party struct lags behind a faint
                return f"{party[idx]['species']} has fainted; pick another"
            if kind == "main":
                if not self._select_main(emu, (1, 0)):
                    return "cannot open the party menu now"
                emu.press("A", settle=1)
            # the party menu remembers its cursor and draws ▶ on each entry's HP line, not the name: read the row from WRAM
            cur = self._u8(D.CURRENT_MENU_ITEM)
            if not 0 <= cur < len(party):
                cur = self._list_cursor(self.screen_text() or "", [self._norm(p["species"]) for p in party]) or 0
            steps = idx - cur
            if steps:
                emu.press(("DOWN " if steps > 0 else "UP ") * abs(steps), settle=1)
            emu.press("A", settle=1)
            if "▶SWITCH" in (self.screen_text() or ""):
                emu.press("A", settle=1)
        elif action == "item":
            if kind != "main" or not self._select_main(emu, (0, 1)):
                return "cannot use an item now"
            bag = self.items()
            if not bag:
                return "bag is empty"
            item_name, _, mon_target = target.partition(":")           # "Potion" or "Potion: Pidgey"
            t = self._norm(item_name)
            idx = 0
            if t:
                matches = [i for i, (n, _) in enumerate(bag) if t in self._norm(n)]
                if not matches:
                    return f"no item '{item_name.strip()}'; bag: " + ", ".join(f"{n}×{q}" for n, q in bag)
                idx = matches[0]
            emu.press("A", settle=1)                                    # open the bag
            names = [self._norm(n) for n, _ in bag]
            for _ in range(len(bag) + 2):                               # the bag remembers its cursor: look, don't assume
                cur = self._list_cursor(self.screen_text() or "", names)
                if cur is None or cur == idx:
                    break
                emu.press("DOWN" if idx > cur else "UP", settle=1)
            emu.press("A", settle=1)
            txt = self.screen_text() or ""
            d = self.dialog_text()
            if "▶" in txt and ("which POK" in d or "Use item" in d):     # item wants a target Pokémon
                party = self.party()
                k = self._pick_party(emu, mon_target) if mon_target.strip() else None
                if k is None:                                           # default: the Pokémon that is fighting
                    k = min(self._u8(D.PLAYER_MON_NUMBER), max(len(party) - 1, 0))
                if not self._party_cursor_to(emu, k):
                    emu.press("DOWN " * k if k else "W1", settle=1)
                emu.press("A", settle=1)
        else:
            return "unknown action; use fight, run, switch, item, bait or rock"

        kind, log = self._wait_menu(emu)
        if action == "fight" and kind == "main" and "move is disabled" in log.lower():
            chosen = b["mine"]["moves"][idx][0] if b and idx < len(b["mine"]["moves"]) else target
            usable = [n for n, pp in b["mine"]["moves"] if pp > 0 and n != chosen] if b else []
            return f"{chosen} is DISABLED by the enemy for a few turns; usable: " + (", ".join(usable) or "none") + " — pick another move or switch"
        if prelog:
            log = prelog + " | " + log if log else prelog
        b2 = self.battle()
        if kind == "over" or b2 is None:
            return (log + " | " if log else "") + "battle over — " + self.status_line()
        after = (b2["enemy"]["hp"], b2["mine"]["hp"], b2["mine"]["species"])
        summary = ""
        if before and after[2] == before[2]:
            summary = f" (enemy {before[0]}→{after[0]}, you {before[1]}→{after[1]})"
        if kind == "prompt":
            return (log or "prompt") + summary + " — answer with press (A = YES / first option, DOWN A = NO)"
        if kind == "choose":
            return (log or "") + summary + " — your Pokémon fainted: battle('switch', n)"
        return (log or "turn done") + summary

    def hint(self) -> str:
        txt = self.screen_text() or ""
        if not txt:
            return self.obstacle_hint() or self.health_hint()
        if "Bring out which" in txt or "Use next" in txt:
            return "hint: choose a Pokémon with battle('switch', n)"
        if "▶YES" in txt or "▶NO" in txt:
            what = "learn the move" if "learn" in txt.lower() or "forget" in txt.lower() else "confirm"
            return f"hint: YES/NO prompt ({what}): press('A') = YES, press('DOWN A') = NO"
        if "▶HEAL" in txt:
            return "hint: press('A') to heal, then talk() to finish"
        if "▶BUY" in txt or "▷BUY" in txt:
            return "hint: shop('<item>', qty) buys; press('B') leaves"
        if self.in_battle():
            m = self.battle_menu()
            if m.startswith("menu: FIGHT"):
                return "hint: battle('fight', '<move>') / battle('run') / battle('item', 'Poké Ball') / battle('switch', n)"
            if m.startswith("menu: BALL"):
                return "hint: Safari Zone: battle('item') throws a Safari Ball, battle('bait') / battle('rock') / battle('run')"
            return ""
        if "▶" in txt and "NEW GAME" not in txt:
            return "hint: a menu is open: UP/DOWN then A, or B to close"
        if "▼" in txt:
            return "hint: text is waiting: talk() reads it all, or press('A')"
        if self.scripted():
            return "hint: a cutscene is running (you cannot walk yet): talk() advances it"
        return self.obstacle_hint() or self.health_hint()

    def obstacle_hint(self) -> str:
        """After a blocked walk: what is in front of the player and which field move deals with it."""
        if self.last_stop != "blocked" or not self.started():
            return ""
        tile, tileset = self._u8(D.TILE_IN_FRONT), self._u8(D.CUR_TILESET)
        if tile == D.WATER_TILE and tileset in D.WATER_TILESETS and not self.surfing():
            return "hint: water ahead: manage('field', 'Surf') while facing it (a party Pokémon must know Surf; needs the Soul Badge)"
        if tile == D.CUT_TREE_TILES.get(tileset, -1):
            return ("hint: a small tree blocks this tile. Early in the game there is another way (gates, forests, other exits: "
                    "see state('map')); later, manage('field', 'Cut') removes it (HM01 from the S.S. Anne, Cascade Badge)")
        if tileset == 17:                                   # caves: a sprite in the way is often a boulder
            m, px, py = self.position()
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}.get(self.facing(), (0, 0))
            if (px + dx, py + dy) in set(self.npcs()):
                return "hint: if that is a boulder, manage('field', 'Strength') once, then walk into it to push it"
        return ""

    def health_hint(self) -> str:
        if self.in_battle() or not self.started():
            return ""
        party = self.party()
        psn = [p["species"] for p in party if p["status"] == "PSN"]
        if psn:
            return f"hint: {', '.join(psn)} is poisoned and loses HP every few steps: use an Antidote or heal at a Poké Center soon"
        alive = [p for p in party if p["hp"] > 0]
        if party and len(alive) == 1 and alive[0]["hp"] <= alive[0]["max_hp"] // 4:
            return "hint: your last healthy Pokémon is low on HP: heal before the next battle or you will black out (money halves)"
        if party and all(pp == 0 for n, pp in party[0]["moves"] if n not in _STATUS_MOVES) and any(n not in _STATUS_MOVES for n, _ in party[0]["moves"]):
            return f"hint: {party[0]['species']} has no PP left on its attacking moves: heal at a Poké Center or switch the lead"
        return ""

    # ------------------------------------------------------------------ #
    # dialogue helpers (used by the `talk` and `shop` tools)
    # ------------------------------------------------------------------ #
    def talk(self, emu, max_boxes: int = 40) -> str:
        """Interact (A) if nothing is open, then advance text until a choice appears or it ends."""
        if self.in_battle():
            return "in a battle: use battle()"
        seen: list[str] = []
        if not self.is_text_visible():
            emu.press("A", settle=1)
            if not self.is_text_visible():
                return "nothing to talk to here (face an NPC, sign or object and try again)"
        waited = 0
        for _ in range(max_boxes * 4):
            txt = self.screen_text() or ""
            if not txt.strip():
                if self.scripted() and waited < 1800:      # cutscene walking someone around: wait
                    emu.tick(12)
                    waited += 12
                    continue
                if self.in_battle():
                    return ("said: " + " | ".join(seen) + " — " if seen else "") + "a battle started: use battle()"
                return ("dialogue ended: " + " | ".join(seen)) if seen else "dialogue ended"
            if "▶" in txt:
                return ("said: " + " | ".join(seen) + "\n" if seen else "") + "choice:\n" + txt
            self._collect(seen)
            emu.press("A", settle=1)
        return "still talking: " + " | ".join(seen)

    def shop(self, emu, item: str, qty: int = 1) -> str:
        """Buy `qty` of `item` from the clerk you are facing. Returns the result and the bag."""
        if self.in_battle():
            return "in a battle"
        qty = max(1, min(int(qty), 99))
        txt = self.screen_text() or ""
        if "BUY" not in txt or "▶" not in txt:
            r = self.talk(emu)
            txt = self.screen_text() or ""
            if "BUY" not in txt:
                return "no shop menu: face the clerk (usually left of you behind the counter) first. " + r
        # cursor to BUY (it is the first entry) and open the list
        for _ in range(3):
            if "▶BUY" in (self.screen_text() or ""):
                break
            emu.press("UP", settle=1)
        emu.press("A", settle=1)
        want = self._norm(item)
        # scroll until the wanted item is under the cursor
        for _ in range(16):
            txt = self.screen_text() or ""
            lines = txt.split("\n")
            cur = next((i for i, ln in enumerate(lines) if "▶" in ln), None)
            hit = next((i for i, ln in enumerate(lines) if want and want in self._norm(ln.replace("▶", "").replace("▷", ""))), None)
            if cur is None:
                emu.press("B", settle=1)
                return "lost the shop list"
            if hit is None:
                emu.press("DOWN", settle=1)      # list scrolls; item may appear
                continue
            if hit == cur:
                break
            # item rows are 2 lines apart (name / price)
            steps = (hit - cur) // 2 if abs(hit - cur) >= 2 else (1 if hit > cur else -1)
            emu.press(("DOWN " if steps > 0 else "UP ") * abs(steps), settle=1)
        else:
            emu.press("B*2", settle=1)
            return f"'{item}' is not sold here. Screen:\n{txt}"
        money0, bag0 = self.money(), dict(self.items())
        emu.press("A", settle=1)                              # quantity box
        if qty > 1:
            emu.press("UP " * (qty - 1), settle=1)
        emu.press("A", settle=1)                              # "That will be ¥x. OK?"
        for _ in range(3):
            if "▶YES" in (self.screen_text() or ""):
                break
            emu.press("A", settle=1)
        emu.press("A", settle=1)                              # YES
        msg = self.dialog_text()
        emu.press("A", settle=1)                              # Here you are! Thank you!
        bag = self.items()
        bought = {n: q for n, q in bag}.get(next((n for n, _ in bag if want in self._norm(n)), ""), 0) - bag0.get(next((n for n in bag0 if want in self._norm(n)), ""), 0)
        return (f"bought {bought} × {item} for ¥{money0 - self.money()}" if bought > 0 else f"purchase failed: {msg}") + \
               f" | ¥{self.money()} left | bag: " + (", ".join(f"{n}×{q}" for n, q in bag) or "empty") + " (shop menu still open: press B to leave)"

    # ------------------------------------------------------------------ #
    # START-menu helpers (used by the `manage` tool)
    # ------------------------------------------------------------------ #
    def _cursor_line(self) -> str:
        for ln in (self.screen_text() or "").split("\n"):
            if "▶" in ln:
                return ln.split("▶", 1)[1].strip()
        return ""

    def _menu_select(self, emu, label: str, max_moves: int = 8) -> bool:
        """Move the ▶ cursor to the entry starting with `label` and press A."""
        want = self._norm(label)
        for _ in range(max_moves):
            cur = self._norm(self._cursor_line())
            if cur.startswith(want):
                emu.press("A", settle=1)
                return True
            emu.press("DOWN", settle=1)
        return False

    def _open_start_menu(self, emu) -> bool:
        if self.in_battle():
            return False
        txt = self.screen_text() or ""
        if "▶" in txt and ("ITEM" in txt or "SAVE" in txt) and "EXIT" in txt:
            return True
        if txt.strip():
            return False                      # some other text/menu is open
        emu.press("START", settle=1)
        txt = self.screen_text() or ""
        return "▶" in txt and "EXIT" in txt

    def _party_match(self, target: str, party: list[dict]) -> Optional[int]:
        """The party slot a name means: the exact species first (Nidoran♀ and Nidoran♂ normalize alike), then one that
        can still fight (volcano-leg-25: battle('switch', 'Nidoran♀') picked the fainted Nidoran♂ ~10 times running)."""
        t, exact = self._norm(target), target.strip().lower()
        matches = [i for i, p in enumerate(party) if t and (t in self._norm(p["species"]) or t in self._norm(p["nick"]))]
        matches.sort(key=lambda i: (party[i]["species"].lower() != exact, party[i]["hp"] == 0))
        return matches[0] if matches else None

    def _pick_party(self, emu, target: str) -> Optional[int]:
        party = self.party()
        t = self._norm(target)
        if t.isdigit():
            idx = int(t) - 1
            return idx if 0 <= idx < len(party) else None
        return self._party_match(target, party)

    def manage(self, emu, action: str, target: str = "", target2: str = "") -> str:
        action = (action or "").lower().strip()
        if self.in_battle():
            return "in a battle: use battle()"
        if action in ("lead", "swap"):
            party = self.party()
            i = self._pick_party(emu, target)
            j = 0 if action == "lead" else self._pick_party(emu, target2)
            if i is None or j is None:
                return "which Pokémon? " + ", ".join(f"{k + 1}={p['species']}" for k, p in enumerate(party))
            if i == j:
                return f"{party[i]['species']} is already in that slot"
            if not self._open_start_menu(emu):
                return "cannot open the START menu now (close any text first)"
            if not self._menu_select(emu, "POKéMON") and not self._menu_select(emu, "POK"):
                emu.press("B", settle=1)
                return "no POKéMON entry in the menu"
            if not self._party_cursor_to(emu, i):
                emu.press("DOWN " * i if i else "W1", settle=1)  # unreadable list: assume it starts at the top
            emu.press("A", settle=1)                              # STATS / SWITCH / CANCEL
            if not self._menu_select(emu, "SWITCH"):
                emu.press("B*3", settle=1)
                return "no SWITCH option"
            cur = i                                               # cursor stays on the chosen mon
            steps = j - cur
            emu.press(("DOWN " if steps > 0 else "UP ") * abs(steps), settle=1)
            emu.press("A", settle=1)
            emu.press("B*2", settle=1)
            new = self.party()
            return "party: " + ", ".join(f"{k + 1}={p['species']} L{p['level']}" for k, p in enumerate(new))
        if action == "use":
            return self._use_item(emu, target, target2)
        if action == "toss":
            return self._toss_item(emu, target)
        if action == "field":
            return self._field_move(emu, target, target2)
        if action == "save":
            if not self._open_start_menu(emu):
                return "cannot open the START menu now (close any text first)"
            if not self._menu_select(emu, "SAVE"):
                emu.press("B", settle=1)
                return "no SAVE entry in the menu"
            for _ in range(3):
                if "▶YES" in (self.screen_text() or ""):
                    break
                emu.press("A", settle=1)
            emu.press("A", settle=1)                              # YES
            for _ in range(20):
                d = self.dialog_text()
                if "saved the game" in d:
                    emu.press("A", settle=1)
                    return "game saved (battery save; survives restarts)"
                emu.tick(30)
            return "save may not have completed: " + self.dialog_text()
        return "unknown action; use lead, swap, use, toss, field or save"

    def _party_cursor_index(self, txt: str) -> Optional[int]:
        """Party slot under the ▶ cursor. The cursor sits on an entry's name row, or (TM/HM lists) on its
        second row, in which case the name is on the line above."""
        names = [self._norm(p["nick"] or p["species"]) for p in self.party()]
        lines = [ln for ln in txt.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            if "▶" not in ln:
                continue
            for cand in (ln.split("▶", 1)[1], lines[i - 1] if i else ""):
                label = self._norm(cand)
                for j, e in enumerate(names):
                    if e and label.startswith(e[:6]):
                        return j
        return None

    def _party_cursor_to(self, emu, k: int) -> bool:
        """Move the ▶ cursor of the open party list to slot k (the menu remembers its last position). The slot is
        read from WRAM: names cannot tell apart Pokémon with the same nickname (full runs 71-75: all AAAAAAAAAA)."""
        n = len(self.party())
        for _ in range(8):
            cur = self._u8(D.CURRENT_MENU_ITEM)
            if not 0 <= cur < n:
                cur = self._party_cursor_index(self.screen_text() or "")
            if cur is None:
                return False
            if cur == k:
                return True
            emu.press("DOWN" if k > cur else "UP", settle=1)
        return False

    def _party_list_open(self, txt: str) -> bool:
        """True when the START-menu party list (nicknames with ▶) is on screen."""
        if "▶" not in txt:
            return False
        return any((p["nick"] or p["species"].upper())[:5] in txt for p in self.party())

    def _bag_text(self) -> str:
        return "bag: " + (", ".join(f"{n}×{q}" for n, q in self.items()) or "empty")

    def _bag_seek(self, emu, bag: list[tuple[str, int]], hit: int) -> bool:
        """Move the bag cursor onto entry `hit`. The bag remembers its cursor and scroll between visits, so read where
        it is and go up or down (full run 63: left on CANCEL, DOWN-only never reached an item and every toss failed).
        Entries are told apart by their whole name (six letters made SUPER REPEL and SUPER ROD the same entry)."""
        keys = [self._norm(n) for n, _ in bag]

        def at(line: str) -> Optional[int]:
            if line.startswith(self._norm("CANCEL")):
                return len(bag)
            k = max((k for k, key in enumerate(keys) if key and line.startswith(key)), key=lambda k: len(keys[k]),
                    default=None)
            if k is None:                                     # the screen spells it differently: a unique prefix
                hits = {key for key in keys if key[:6] and line.startswith(key[:6])}
                k = next((k for k, key in enumerate(keys) if key in hits), None) if len(hits) == 1 else None
            return k

        names, pos = keys + [self._norm("CANCEL")], None
        for _ in range(2 * len(bag) + 4):
            cur = at(self._norm(self._cursor_line()))
            if cur is not None and pos is not None and 0 <= pos < len(names) and names[pos] == names[cur]:
                cur = pos                                     # an item listed twice: where the moves so far put it
            if cur is not None and cur < len(bag) and keys[cur] == keys[hit]:      # (a twin entry is the same item)
                return True
            up = cur is None or cur > hit
            emu.press("UP" if up else "DOWN", settle=1)
            pos = None if cur is None else cur - 1 if up else cur + 1
        return False

    def _toss_item(self, emu, target: str) -> str:
        """START → ITEM → item → TOSS, the whole stack (DOWN from ×1 wraps to the most), YES. A full bag (20 kinds)
        cannot pick anything up, not even a key item ("No more room for items!")."""
        bag = self.items()
        want = self._norm(target)
        hit = next((k for k, (n, _) in enumerate(bag) if want and want in self._norm(n)), None)
        if hit is None:
            return f"no '{target}' in the bag: " + (", ".join(f"{n}×{q}" for n, q in bag) or "empty")
        item_name, qty = bag[hit]
        if not self._open_start_menu(emu):
            return "cannot open the START menu now (close any text first)"
        if not self._menu_select(emu, "ITEM"):
            emu.press("B", settle=1)
            return "no ITEM entry in the menu"
        if not self._bag_seek(emu, bag, hit):
            emu.press("B*4", settle=1)
            return f"could not find {item_name} in the bag menu"
        emu.press("A", settle=1)                              # USE / TOSS
        if not self._menu_select(emu, "TOSS", 2):
            emu.press("B*3", settle=1)
            return "could not select TOSS"
        if qty > 1:
            emu.press("DOWN", settle=1)                       # quantity box: ×1 wraps to the whole stack
        said = ""
        for _ in range(8):
            txt = self.screen_text() or ""
            d = self.dialog_text()
            if "too impor" in d.replace("\n", "").replace("-", ""):
                said = f"{item_name} is too important to toss"
                break
            if "▶YES" in txt:                                 # "Is it OK to toss X?"
                emu.press("A", settle=1)
                continue
            if "Threw away" in d or "threw away" in d:
                said = f"threw away {item_name}×{qty}"
                break
            emu.press("A", settle=1)
        emu.press("B*4", settle=1)
        return (said or "toss may not have completed") + "; " + self._bag_text()

    def _use_item(self, emu, target: str, target2: str) -> str:
        """START → ITEM → item → USE, answering the prompts: a Pokémon to use it on (target2), and for
        TMs/HMs the move to forget ("Charmander: Growl", or "Charmander: weakest" for the move with the least power)."""
        bag = self.items()
        want = self._norm(target)
        hit = next((k for k, (n, _) in enumerate(bag) if want and want in self._norm(n)), None)
        if hit is None:
            return f"no '{target}' in the bag: " + (", ".join(f"{n}×{q}" for n, q in bag) or "empty")
        item_name = bag[hit][0]
        mon_target, _, forget = target2.partition(":")
        mon_target, forget = mon_target.strip(), forget.strip()
        if not self._open_start_menu(emu):
            return "cannot open the START menu now (close any text first)"
        if not self._menu_select(emu, "ITEM"):
            emu.press("B", settle=1)
            return "no ITEM entry in the menu"
        if not self._bag_seek(emu, bag, hit):
            emu.press("B*4", settle=1)
            return f"could not find {item_name} in the bag menu"
        emu.press("A", settle=1)                              # USE / TOSS
        if not self._menu_select(emu, "USE", 2):
            emu.press("B*3", settle=1)
            return "could not select USE"
        seen: list[str] = []
        picked: Optional[int] = None
        outcome = ""
        for _ in range(16):
            txt = self.screen_text() or ""
            d = self.dialog_text()
            if not txt.strip():
                break                                         # back in the overworld
            if "▶YES" in txt or "▶NO" in txt:
                self._collect(seen)
                low = d.lower()
                if "delete" in low or "make room" in low:     # "Delete an older move to make room for X?"
                    if forget:
                        emu.press("A", settle=1)
                    else:
                        emu.press("DOWN A", settle=1)         # NO: keep the moves, ask the agent
                        outcome = "needs a decision"
                elif "abandon" in low:
                    emu.press("A", settle=1)                  # YES, abandon (we declined to forget a move)
                else:
                    emu.press("A", settle=1)                  # "Teach X to a POKéMON?" and other confirmations
                continue
            if "▶" in txt and picked is None and self._party_list_open(txt):
                k = self._pick_party(emu, mon_target) if mon_target else 0
                if k is None:
                    emu.press("B*3", settle=1)
                    return "use it on which Pokémon? give a name or number as the second target"
                if not self._party_cursor_to(emu, k):
                    emu.press("DOWN " * k if k else "W1", settle=1)
                emu.press("A", settle=1)
                picked = k
                continue
            if "▶" in txt and ("forgotten" in d or "Which move" in d) and picked is not None:
                mon = self.party()[picked] if picked < len(self.party()) else None
                names = [self._norm(n) for n, _ in mon["moves"]] if mon else []
                fk = self._norm(forget)
                if fk == "weakest" and mon:                   # the move whose loss costs least (see _forget_choice); HMs stay
                    nm = re.search(r"make\s+room\s+for\s+([A-Z][A-Z0-9\- ]+?)[?!.]", " ".join(" ".join(seen + [txt]).split()))
                    k = self._forget_choice([n for n, _ in mon["moves"]], nm[1].strip() if nm else "")
                    fk = names[k] if k is not None else ""
                idx = next((i for i, n in enumerate(names) if fk and (n.startswith(fk) or fk in n)), None)
                if idx is None:
                    emu.press("B", settle=1)                  # → "Abandon learning X?"
                    outcome = "needs a decision"
                    continue
                cur = self._list_cursor(txt, names) or 0
                steps = idx - cur
                if steps:
                    emu.press(("DOWN " if steps > 0 else "UP ") * abs(steps), settle=1)
                emu.press("A", settle=1)
                continue
            if "▶" in txt:
                break                                         # back in the bag / party list: done
            self._collect(seen)
            emu.press("A", settle=1)
        emu.press("B*3", settle=1)
        result = " | ".join(seen) or f"used {item_name}"
        if outcome == "needs a decision":
            mon = self.party()[picked] if picked is not None and picked < len(self.party()) else None
            moves = ", ".join(n for n, _ in mon["moves"]) if mon else "?"
            result += (f" — {mon['species'] if mon else 'it'} already knows 4 moves ({moves}): repeat with "
                       f"manage('use', '{item_name}', '{mon['species'] if mon else mon_target}: <move to forget or weakest>')")
        return result + " | " + self._bag_text()

    def _field_move(self, emu, move: str, where: str = "") -> str:
        """Use Cut / Surf / Strength / Flash / Fly / Dig / Teleport / Softboiled from the party menu."""
        key = self._norm(move)
        if not key:
            return "which field move? " + ", ".join(D.FIELD_MOVES)
        party = self.party()
        k = next((i for i, p in enumerate(party) if any(self._norm(n).startswith(key) for n, _ in p["moves"])), None)
        if k is None:
            known = {n for p in party for n, _ in p["moves"] if n in D.FIELD_MOVES}
            return f"no Pokémon in the party knows {move}" + (f"; field moves available: {', '.join(sorted(known))}" if known else "")
        label = next(n for n, _ in party[k]["moves"] if self._norm(n).startswith(key))
        if not self._open_start_menu(emu):
            return "cannot open the START menu now (close any text first)"
        if not self._menu_select(emu, "POKéMON") and not self._menu_select(emu, "POK"):
            emu.press("B", settle=1)
            return "no POKéMON entry in the menu"
        if not self._party_cursor_to(emu, k):
            emu.press("DOWN " * k if k else "W1", settle=1)
        emu.press("A", settle=1)                              # <field moves> / STATS / SWITCH / CANCEL
        if not self._menu_select(emu, label, 6):
            emu.press("B*3", settle=1)
            return f"{party[k]['species']} shows no {label} option here"
        seen: list[str] = []
        before = self.position()
        for _ in range(16):
            txt = self.screen_text() or ""
            if not txt.strip():
                break
            if self._norm(label) == "fly" and "▶" not in txt and not self.dialog_text():
                # Town map: UP/DOWN cycles the visited towns, the name shows at the top.
                if where and self._norm(where)[:6] in self._norm(txt):
                    emu.press("A", settle=1)
                    seen.append(f"flying to {where}")
                    break
                if not where:
                    emu.press("B*2", settle=1)
                    return "Fly: give the town as the second target, e.g. manage('field', 'Fly', 'Pewter City')"
                emu.press("DOWN", settle=1)
                continue
            if "▶YES" in txt or "▶NO" in txt:
                self._collect(seen)
                emu.press("A", settle=1)
                continue
            if "▶" in txt:
                emu.press("B", settle=1)                      # a menu is still open: close it
                continue
            self._collect(seen)
            emu.press("A", settle=1)
        emu.tick(30)
        emu._settle()
        after = self.position()
        note = " | ".join(seen) or f"used {label}"
        if self.surfing() and self._norm(label) == "surf":
            note += " — now surfing: walk onto the water (~)"
        if after != before:
            note += f" — now at {D.map_name(after[0])} ({after[1]},{after[2]})"
        return note

    # ------------------------------------------------------------------ #
    # full map (decoded from the block grid in RAM + tileset data in ROM)
    # ------------------------------------------------------------------ #
    def _walkable_tiles(self) -> frozenset:
        ptr = self._u8(D.TILESET_COLLISION_PTR) | (self._u8(D.TILESET_COLLISION_PTR + 1) << 8)
        if ptr not in self._coll_cache:
            tiles = []
            for i in range(0x180):
                t = self.mem[ptr + i]
                if t == 0xFF:
                    break
                tiles.append(t)
            self._coll_cache[ptr] = frozenset(tiles)
        return self._coll_cache[ptr]

    def _block(self, block_id: int) -> bytes:
        bank = self._u8(D.TILESET_BANK)
        ptr = self._u8(D.TILESET_BLOCKS_PTR) | (self._u8(D.TILESET_BLOCKS_PTR + 1) << 8)
        key = (bank, ptr, block_id)
        if key not in self._block_cache:
            a = ptr + block_id * 16
            self._block_cache[key] = bytes(self.mem[bank, a:a + 16])
        return self._block_cache[key]

    def full_map_tiles(self) -> list[list[int]]:
        """Collision tile (bottom-left 8x8 tile) of every 2x2-tile metatile of the current map."""
        w, h = self._u8(D.MAP_WIDTH) * 2, self._u8(D.MAP_HEIGHT) * 2
        bw = self._u8(D.MAP_WIDTH) + 6
        blocks = self.mem[D.OVERWORLD_MAP:D.OVERWORLD_MAP + bw * (self._u8(D.MAP_HEIGHT) + 6)]
        tiles = []
        for y in range(h):
            row = []
            for x in range(w):
                blk = self._block(blocks[(y // 2 + 3) * bw + (x // 2 + 3)])
                row.append(blk[((y % 2) * 2 + 1) * 4 + (x % 2) * 2])
            tiles.append(row)
        return tiles

    def switch_cells(self, quad: tuple = D.MANSION_SWITCH_QUAD, where: str = "Pokémon Mansion",
                     tileset: int = 22) -> set[tuple[int, int]]:
        """The Pokémon Mansion's secret switches: the statue drawn with its own four tiles (examine it from below); with
        `quad`, the cells drawn with another four tiles (its broken floor, Victory Road's floor switches)."""
        if not D.map_name(self._u8(D.CUR_MAP)).startswith(where) or (tileset is not None and self._u8(D.CUR_TILESET) != tileset):
            return set()
        bw = self._u8(D.MAP_WIDTH) + 6
        blocks = self.mem[D.OVERWORLD_MAP:D.OVERWORLD_MAP + bw * (self._u8(D.MAP_HEIGHT) + 6)]
        out = set()
        for y in range(self._u8(D.MAP_HEIGHT) * 2):
            for x in range(self._u8(D.MAP_WIDTH) * 2):
                blk = self._block(blocks[(y // 2 + 3) * bw + (x // 2 + 3)])
                if tuple(blk[((y % 2) * 2 + r) * 4 + (x % 2) * 2 + c] for r in (0, 1) for c in (0, 1)) == quad:
                    out.add((x, y))
        return out

    def full_map_cells(self) -> list[list[str]]:
        """Walkability of every 2x2-tile metatile of the current map."""
        walkable = self._walkable_tiles()
        grass = self._u8(D.GRASS_TILE)
        tileset = self._u8(D.CUR_TILESET)
        ledges = D.LEDGE_TILES if tileset == 0 else {}
        water = D.WATER_TILE if tileset in D.WATER_TILESETS else -1
        tree = D.CUT_TREE_TILES.get(tileset, -1)
        doors = D.CARD_KEY_DOOR_TILES if D.map_name(self._u8(D.CUR_MAP)).startswith("Silph Co.") else ()
        switches = self.switch_cells()
        broken = self.switch_cells(D.MANSION_BROKEN_QUAD) if switches else set()
        plates = self.switch_cells(D.VICTORY_SWITCH_QUAD, "Victory Road", None)
        puzzle = D.VICTORY_ROAD_PUZZLE.get(D.map_name(self._u8(D.CUR_MAP)), {})
        done = {c for c, (addr, bit, _) in puzzle.items() if self._u8(addr) >> bit & 1}   # activated: plain floor
        plates = (plates | {c for c, (_, _, k) in puzzle.items() if k == "X"}) - done
        holes = {c for c, (_, _, k) in puzzle.items() if k == "H"} - done
        cells = []
        for y, trow in enumerate(self.full_map_tiles()):
            row = []
            for x, tile in enumerate(trow):
                if (x, y) in switches:
                    row.append("S")
                elif tile == grass:
                    row.append(",")
                elif tile in ledges:
                    row.append(D.LEDGE_CHAR[ledges[tile]])
                elif (x, y) in plates:
                    row.append("X")                         # a floor switch (walkable; a boulder on it opens a way)
                elif (x, y) in holes:
                    row.append("H")                         # a hole a boulder can be pushed into (it lands below)
                elif tile in walkable:
                    row.append(":" if (x, y) in broken else ".")
                elif tile == water:
                    row.append("~")
                elif tile == tree:
                    row.append("T")
                elif tile in doors:
                    row.append("L")
                else:
                    row.append("#")
            cells.append(row)
        return cells

    def push_plan(self, b: tuple[int, int], t: tuple[int, int]) -> Optional[list[tuple[tuple[int, int], str]]]:
        """Pushes that bring the boulder at b to t: [(cell to stand on, direction to push), ...], or None. A push moves
        the boulder one cell; it needs the player behind it and the cell ahead walkable, free of other sprites and not
        across a cave elevation step (the same tile-pair rule as walking)."""
        cells = self.full_map_cells()
        h, w = len(cells), len(cells[0]) if cells else 0
        solid = {"#", "T", "L", "S", "~"} | set(D.LEDGE_DIR)
        pairs = set(D.TILE_PAIR_COLLISIONS_LAND.get(self._u8(D.CUR_TILESET), ()))
        tiles = self.full_map_tiles() if pairs else None
        # a warp on the map's border (a cave exit) only takes you away when you step off the edge: standing on it is
        # fine (Victory Road 1F's boulder goes up past the entrance, pushed from it)
        warps = {(wx, wy) for wx, wy, _ in self.warps() if 0 < wx < w - 1 and 0 < wy < h - 1}
        others = (set(self.boulders()) | set(self.npcs(False)) | set(self.npcs(True))) - {b}
        moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}

        def ok(a, c) -> bool:                                # (H, a hole, takes a boulder: only as the target)
            if 0 <= c[0] < w and 0 <= c[1] < h and cells[c[1]][c[0]] == "H" and c != t:
                return False
            return (0 <= c[0] < w and 0 <= c[1] < h and cells[c[1]][c[0]] not in solid and c not in others
                    and not (tiles is not None and frozenset((tiles[a[1]][a[0]], tiles[c[1]][c[0]])) in pairs))

        def region(start, boulder) -> set:
            seen, todo = {start}, [start]
            while todo:
                x, y = todo.pop()
                for dx, dy in moves.values():
                    c = (x + dx, y + dy)
                    if c not in seen and c != boulder and c not in warps and ok((x, y), c) and cells[c[1]][c[0]] != "H":
                        seen.add(c)
                        todo.append(c)
            return seen

        _, px, py = self.position()
        start = (b, (px, py))
        parent: dict = {(b, min(region((px, py), b))): None}
        todo = [start]
        while todo:
            nxt = []
            for bpos, ppos in todo:
                reach = region(ppos, bpos)
                for d, (dx, dy) in moves.items():
                    stand, dest = (bpos[0] - dx, bpos[1] - dy), (bpos[0] + dx, bpos[1] + dy)
                    if stand not in reach or dest in warps or not ok(bpos, dest):
                        continue
                    key = (dest, min(region(bpos, dest)))
                    if key in parent:
                        continue
                    parent[key] = ((bpos, min(reach)), stand, d)
                    if dest == t:
                        plan, k = [], key
                        while parent[k] is not None:
                            prev, s_, d_ = parent[k]
                            plan.append((s_, d_))
                            k = prev
                        return plan[::-1]
                    nxt.append((dest, bpos))
            todo = nxt
            if len(parent) > 20000:
                break
        return None

    def push_boulder(self, emu, b: tuple[int, int], t: tuple[int, int]) -> str:
        """walk('push bx,by to tx,ty'): plan the pushes, walk behind the boulder and push, one cell at a time, checking
        that it moved and re-planning when something got in the way (Victory Road's floor switches)."""
        if self._u8(0xD728) & 1 == 0:                       # wd728 bit 0: Strength is active on this map
            r = self.manage(emu, "field", "Strength")       # (turned on here: one tool call for the whole push)
            if self._u8(0xD728) & 1 == 0:
                return f"Strength is not active: {r}"
        notes = []
        for _ in range(60):
            if b == t:
                return f"the boulder is at ({t[0]},{t[1]}) — " + ", ".join(notes[-6:])
            if b not in self.boulders():
                return f"no boulder at ({b[0]},{b[1]})"
            plan = self.push_plan(b, t)
            if not plan:
                return f"no way to push the boulder at ({b[0]},{b[1]}) to ({t[0]},{t[1]})" + (" — " + ", ".join(notes[-6:]) if notes else "")
            (sx, sy), d = plan[0]
            r = emu._goto(sx, sy, through=False)          # (behind the boulder may be a cave exit: stay on it)
            if self.position()[1:] != (sx, sy):
                return f"could not get behind the boulder at ({b[0]},{b[1]}): {r}"
            dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[d]
            moved = False
            for _try in range(3):                           # the first press may only turn the player
                emu._walk_segment(d, 1)
                for _ in range(8):                          # the boulder slides for a while: wait until it stands
                    emu.tick(8)
                    if (b[0] + dx, b[1] + dy) in self.boulders() or b not in self.boulders():
                        break
                emu._settle()
                if (b[0] + dx, b[1] + dy) in self.boulders():
                    moved = True
                    break
                if b not in self.boulders():                # it went somewhere else (two cells?): re-plan from there
                    if (b[0] + dx, b[1] + dy) == t:
                        return f"the boulder fell into the hole at ({t[0]},{t[1]})"   # (Victory Road 3F: it lands on 2F)
                    return f"the boulder at ({b[0]},{b[1]}) moved unexpectedly: now at {self.boulders()}"
                if self.in_battle() or self.is_text_visible():
                    return f"pushing stopped: {self.status_line()}"
            if not moved:
                return f"the boulder at ({b[0]},{b[1]}) did not move {d}"
            if self.in_battle() or self.is_text_visible():  # (pushed, then a wild battle)
                return f"pushed {d} to ({b[0] + dx},{b[1] + dy}), then stopped: {self.status_line()}"
            b = (b[0] + dx, b[1] + dy)
            notes.append(f"pushed {d} to ({b[0]},{b[1]})")
        return "too many pushes; stopped"

    def find_path(self, tx: int, ty: int, avoid=frozenset(), allow: str = "") -> Optional[list[tuple[str, int]]]:
        """Dijkstra over the decoded map. NPC sprites are expensive rather than solid (some are hidden
        by events, others wander off); cells in `avoid` were found solid by walking and are walls. A spinner tile
        found by walking is a one-way jump to where it carried the player: the path ends with the step onto it
        (the slide stops the walk) and the caller plans again from where it lands."""
        if self.in_battle() or not self.started():
            return None
        _, px, py = self.position()
        cells = self.full_map_cells()
        h, w = len(cells), len(cells[0]) if cells else 0
        if not (0 <= tx < w and 0 <= ty < h):
            return None
        npc_cells = {(nx, ny) for nx, ny in self.npcs()}
        blocked = set(avoid) | ((set(self.boulders()) - {(tx, ty)}) if "B" not in allow else set())   # (never moves by walking past)
        # Never cross another warp on the way (stairs, ladders, teleport pads would whisk the player away).
        blocked |= {(wx, wy) for wx, wy, _ in self.warps() if (wx, wy) != (tx, ty)}
        if 0 <= tx < w and 0 <= ty < h and cells[ty][tx] in ("#",) and any((wx, wy) == (tx, ty) for wx, wy, _ in self.warps()):
            cells[ty][tx] = "."                 # a solid door tile can still be walked into as the destination
        if (tx, ty) == (px, py):
            return []
        solid = ("#", "T", "L", "S", "H") if self.surfing() else ("#", "T", "L", "S", "H", "~")
        solid = tuple(c for c in solid if c not in allow)           # (route_hint asks "what if water/trees were not")
        tileset = self._u8(D.CUR_TILESET)
        pairs = set(D.TILE_PAIR_COLLISIONS_LAND.get(tileset, ()))
        if self.surfing():
            pairs |= set(D.TILE_PAIR_COLLISIONS_WATER.get(tileset, ()))
        tiles = self.full_map_tiles() if pairs else None       # cave/forest elevation steps you cannot cross
        moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        spin = self.spinners.get(self._u8(D.CUR_MAP), {})
        prev: dict[tuple[int, int], tuple[tuple[int, int], str, int]] = {}
        # Dijkstra: tall grass costs extra so routes avoid needless wild encounters.
        import heapq
        dist = {(px, py): 0}
        heap = [(0, px, py)]
        while heap:
            cost, x, y = heapq.heappop(heap)
            if cost > dist.get((x, y), 1 << 30):
                continue
            if (x, y) == (tx, ty):
                break
            for d, (dx, dy) in moves.items():
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                c = cells[ny][nx]
                if c in D.LEDGE_DIR:                     # one-way ledge: jump over it in its direction
                    if D.LEDGE_DIR[c] != d:
                        continue
                    nx, ny = nx + dx, ny + dy
                    if not (0 <= nx < w and 0 <= ny < h) or cells[ny][nx] in solid or cells[ny][nx] in D.LEDGE_DIR:
                        continue
                    c = cells[ny][nx]
                elif c in solid:
                    continue
                elif tiles is not None and frozenset((tiles[y][x], tiles[ny][nx])) in pairs:
                    continue
                if (nx, ny) in blocked and (nx, ny) != (tx, ty):
                    continue
                step = 4 if c == "," else 1
                if (nx, ny) in npc_cells and (nx, ny) != (tx, ty):
                    step += 40
                moved = abs(nx - x) + abs(ny - y)
                if (nx, ny) in spin:                     # carried on: ~3 steps' time per tile slid
                    (sx, sy), moved = spin[(nx, ny)], -1
                    step += 3 * (abs(sx - nx) + abs(sy - ny))
                    nx, ny = sx, sy
                nc = cost + step
                if nc < dist.get((nx, ny), 1 << 30):
                    dist[(nx, ny)] = nc
                    prev[(nx, ny)] = ((x, y), d, moved)
                    heapq.heappush(heap, (nc, nx, ny))
        if (tx, ty) not in prev:
            return None
        dirs = []                                    # (direction, cells moved) per move; ledge jumps span 2 cells
        cur = (tx, ty)
        while cur != (px, py):
            (bx, by), d, moved = prev[cur]
            dirs.append((d, moved))
            cur = (bx, by)
        dirs.reverse()
        for i, (d, moved) in enumerate(dirs):
            if moved < 0:                            # the step onto a spinner ends this walk
                dirs = dirs[:i] + [(d, 1)]
                break
        segs: list[tuple[str, int]] = []
        for d, cells in dirs:
            if segs and segs[-1][0] == d:
                segs[-1] = (d, segs[-1][1] + cells)
            else:
                segs.append((d, cells))
        return segs

    def resolve_target(self, name: str) -> Optional[tuple[int, int, Optional[str]]]:
        """
        Turn a place name into (x, y, edge_direction). Matches exit destinations
        ("Oak's Lab", "outside"), connection sides ("north edge") or connected map
        names ("Route 1"). Returns None when nothing matches.
        """
        key = self._norm(name)
        if not key or not self.started():
            return None
        _, px, py = self.position()
        # 1. warps by destination name: nearest reachable one
        best = None
        for wx, wy, d in self.warps():
            label = self._norm(self.map_label(d))
            if key in label or label in key:
                path = self.find_path(wx, wy)
                if path is not None:
                    dist = sum(n for _, n in path)
                    if best is None or dist < best[0]:
                        best = (dist, wx, wy)
        if best:
            return best[1], best[2], None
        # 2. map edges by side or by connected map name
        sides = {"north": "up", "south": "down", "west": "left", "east": "right"}
        want = None
        for side, mid in self.connections():
            if key.startswith(side) or key in self._norm(D.map_name(mid)):
                want = side
                break
        if want is None:
            return self._resolve_far(key)
        self._last_unreachable = None
        cells = self.full_map_cells()
        h, w = len(cells), len(cells[0]) if cells else 0
        if want == "north":
            edge = [(x, 0) for x in range(w)]
        elif want == "south":
            edge = [(x, h - 1) for x in range(w)]
        elif want == "west":
            edge = [(0, y) for y in range(h)]
        else:
            edge = [(w - 1, y) for y in range(h)]
        best = None
        for ex, ey in edge:
            if cells[ey][ex] == "#":
                continue
            path = self.find_path(ex, ey)
            if path is None:
                continue
            dist = sum(n for _, n in path)
            if best is None or dist < best[0]:
                best = (dist, ex, ey)
        if best is None:
            # The map connects that way, but this part of the map does not reach that edge (trees, ledges,
            # a split map like Route 2): remember why, so walk() can explain instead of "unknown place".
            self._last_unreachable = (name, want)
            return None
        return best[1], best[2], sides[want]

    _last_unreachable = None

    def unreachable_note(self, name: str) -> str:
        if not self._last_unreachable or self._norm(self._last_unreachable[0]) != self._norm(name):
            return ""
        side = self._last_unreachable[1]
        exits = ", ".join(self.map_label(d) for _, _, d in self.warps()[:8]) or "none"
        return (f"{name} lies past this map's {side} edge, but no walkable route from here reaches that edge "
                f"(trees, ledges or a split map). Use one of this map's exits instead ({exits}) and come back "
                f"into the other part of the map, or walk the roads through the next town.")

    def surfing(self) -> bool:
        return self._u8(D.WALK_BIKE_SURF) == 2

    def route_hint(self, tx: int, ty: int) -> str:
        try:
            cells = self.full_map_cells()
        except Exception:  # pragma: no cover
            return ""
        h, w = len(cells), len(cells[0]) if cells else 0
        c = cells[ty][tx] if 0 <= tx < w and 0 <= ty < h else "#"
        if c == "~":
            return "the target is water: stand at the shore facing it and manage('field', 'Surf') first"
        if c == "T":
            return "the target is a small tree: look for another way around (state('map') exits/connections); Cut removes it later"
        flat = {ch for row in cells for ch in row}
        notes = []
        # name what blocks this route, not whatever the map has (full run 87: a forest elevation step in the Safari Zone
        # was reported as "water needs Surf" and the agent took it for Surf's job)
        try:
            by_tree = "T" in flat and self.find_path(tx, ty, allow="T") is not None
            by_water = "~" in flat and not self.surfing() and self.find_path(tx, ty, allow="~") is not None
            by_both = not (by_tree or by_water) and self.find_path(tx, ty, allow="T~") is not None
        except Exception:  # pragma: no cover
            by_tree = by_water = by_both = False
        if by_tree or by_both and "T" in flat:
            notes.append("a small tree (T) blocks part of this map: use another exit or route around it; Cut removes it later")
        if by_water or by_both and "~" in flat and not self.surfing():
            notes.append("water (~) needs Surf: face it and manage('field', 'Surf')")
        if not notes and self.boulders():
            if self.find_path(tx, ty, allow="B") is not None:   # (what if the boulders were not there)
                notes.append("a boulder (B) is in the way: push it aside with Strength or go round it")
        if not notes and D.TILE_PAIR_COLLISIONS_LAND.get(self._u8(D.CUR_TILESET)):
            notes.append("an elevation step (a raised ledge in a cave or forest) walls it off from this part of the map: "
                         "go round through another part or another floor")
        if "L" in flat:
            notes.append("a locked door (L) blocks part of this map: with the Card Key, face it and talk")
        return "; ".join(notes)

    def place_names(self) -> list[str]:
        if not self.started():
            return []
        names = []
        for wx, wy, d in self.warps():
            label = self.map_label(d)
            if label not in names:
                names.append(label)
        for side, mid in self.connections():
            names.append(f"{D.map_name(mid)} ({side} edge)")
        return names

    def _resolve_far(self, key: str):
        """Route toward a map that is not adjacent, through maps already visited."""
        here = self._u8(D.CUR_MAP)
        dests = [mid for mid, name in D.MAPS.items() if key == self._norm(name)] or \
                [mid for mid, name in D.MAPS.items() if key in self._norm(name)]
        if not dests:
            return None
        if here in dests:
            return "here"
        # BFS over the explored world graph
        from collections import deque
        prev: dict[int, tuple[int, tuple]] = {}
        q = deque([here])
        seen = {here}
        found = None
        while q:
            m = q.popleft()
            if m in dests and m != here:
                found = m
                break
            info = self.world.get(m)
            if not info:
                continue
            for wx, wy, d in info["warps"]:
                d2 = info.get("outside") if d == 0xFF else d      # 0xFF = back to the outdoor map
                if d2 is None or d2 in seen:
                    continue
                seen.add(d2)
                prev[d2] = (m, ("warp", wx, wy, d))
                q.append(d2)
            for side, d in info["conns"]:
                if d in seen:
                    continue
                seen.add(d)
                prev[d] = (m, ("edge", side))
                q.append(d)
        if found is None:
            return None
        # walk back to find the first hop from here
        cur = found
        hop = None
        while cur in prev:
            pm, hop = prev[cur]
            if pm == here:
                break
            cur = pm
        if hop is None:
            return None
        if hop[0] == "warp":
            _, wx, wy, d = hop
            return (wx, wy, None)
        side = hop[1]
        r = self.resolve_target(side + " edge")
        return r

    def far_destination_note(self, name: str) -> str:
        key = self._norm(name)
        here = self._u8(D.CUR_MAP)
        dests = [mid for mid, n in D.MAPS.items() if key == self._norm(n)] or [mid for mid, n in D.MAPS.items() if key in self._norm(n)]
        if dests and here not in dests:
            return f"{D.map_name(dests[0])} is not adjacent; heading there through explored maps"
        return ""

    def alternate_warps(self, x: int, y: int) -> list[tuple[int, int]]:
        """Other warp tiles next to (x, y) leading to the same map (two-wide doorways)."""
        warps = self.warps()
        dest = next((d for wx, wy, d in warps if (wx, wy) == (x, y)), None)
        if dest is None:
            return []
        return [(wx, wy) for wx, wy, d in warps if d == dest and (wx, wy) != (x, y) and abs(wx - x) + abs(wy - y) <= 2]

    def off_map(self, pos) -> bool:
        """True when a position lies outside the current map (mid edge-transition)."""
        w, h = self._u8(D.MAP_WIDTH) * 2, self._u8(D.MAP_HEIGHT) * 2
        _, x, y = pos
        return not (0 <= x < w and 0 <= y < h)

    def edge_direction(self, x: int, y: int) -> Optional[str]:
        """Direction that leaves the map from an edge tile (building exits are on the bottom row)."""
        w, h = self._u8(D.MAP_WIDTH) * 2, self._u8(D.MAP_HEIGHT) * 2
        if y == h - 1:
            return "down"
        if y == 0:
            return "up"
        if x == w - 1:
            return "right"
        if x == 0:
            return "left"
        return None

    def connections(self) -> list[tuple[str, int]]:
        bits = self._u8(D.MAP_CONNECTIONS)
        out = []
        for name, bit in (("north", 3), ("south", 2), ("west", 1), ("east", 0)):
            if bits & (1 << bit):
                out.append((name, self._u8(D.CONNECTION_HEADERS[name])))
        return out

    def full_map_text(self) -> str:
        if self.in_battle() or not self.started():
            return "(no map: not in overworld)"
        m, px, py = self.position()
        try:
            cells = self.full_map_cells()
        except Exception as e:  # pragma: no cover
            return f"{D.map_name(m)} ({px},{py}) map decode failed: {e}"
        h, w = len(cells), len(cells[0]) if cells else 0
        for wx, wy, _ in self.warps():
            if 0 <= wx < w and 0 <= wy < h:
                cells[wy][wx] = "D"
        self._draw_sprites(cells)
        if 0 <= px < w and 0 <= py < h:
            cells[py][px] = "P"
        head = (f"{D.map_name(m)} {w}x{h}, you at ({px},{py}) facing {self.facing()}. "
                "x→ right, y↓ down. P=you N=npc D=door/warp #=blocked .=walkable ,=tall grass v<>=one-way ledge "
                "~=water (Surf) T=small tree (Cut)" + (" L=locked door (Card Key)" if any("L" in r for r in cells) else "") + \
                (" S=secret switch (examine it from below)" if any("S" in r for r in cells) else "") + \
                (" :=broken floor (a hole can drop you a floor)" if any(":" in r for r in cells) else "") + \
                (" B=boulder (Strength pushes it)" if any("B" in r for r in cells) else "") + \
                (" X=floor switch (push a boulder onto it)" if any("X" in r for r in cells) else "") + \
                (" H=hole (push a boulder into it)" if any("H" in r for r in cells) else "")
                + (" o=item ball" if any("o" in r for r in cells) else ""))
        ruler = "   " + "".join(str(x % 10) for x in range(w))
        body = "\n".join(f"{y:2d} " + "".join(row) for y, row in enumerate(cells))
        exits = ", ".join(f"({wx},{wy})→{self.map_label(d)}" for wx, wy, d in self.warps()[:12])
        conns = ", ".join(f"{side} edge→{D.map_name(mid)}" for side, mid in self.connections())
        tail = "\n".join(t for t in (f"exits: {exits}" if exits else "", f"connections: {conns}" if conns else "",
                                     self.elevation_text(cells)) if t)
        return head + "\n" + ruler + "\n" + body + ("\n" + tail if tail else "")

    def elevation_text(self, cells) -> str:
        """Cave/forest elevation steps between neighbouring floor cells (pokered TilePairCollisionsLand): "x,yr" = no
        walking between (x,y) and (x+1,y), "x,yd" = (x,y) and (x,y+1). The character grid cannot show them; a map built
        from it took walled-off parts for reachable (Codex review 14: run 87's Safari Zone West)."""
        pairs = set(D.TILE_PAIR_COLLISIONS_LAND.get(self._u8(D.CUR_TILESET), ()))
        if not pairs:
            return ""
        try:
            tiles = self.full_map_tiles()
        except Exception:  # pragma: no cover
            return ""
        h, w = len(cells), len(cells[0]) if cells else 0
        out = []
        for y in range(h):
            for x in range(w):
                for d, (dx, dy) in (("r", (1, 0)), ("d", (0, 1))):
                    nx, ny = x + dx, y + dy
                    if nx < w and ny < h and cells[y][x] != "#" and cells[ny][nx] != "#" \
                            and frozenset((tiles[y][x], tiles[ny][nx])) in pairs:
                        out.append(f"{x},{y}{d}")
        return ("elevation steps (no walking across): " + " ".join(out)) if out else ""

    def seed_milestones(self, names) -> None:
        by_name = {self._norm(n): m for m, n in D.MAPS.items()}
        for name in names:
            if name.startswith("reached: "):
                m = by_name.get(self._norm(name[9:]))
                if m is not None:
                    self._reported_maps.add(m)
            elif name.startswith("starter: "):
                self._starter_reported = True
            elif name.startswith("obtained: ") or name.startswith("evolved: "):
                species = name.split("→")[-1].split(":", 1)[-1].strip()
                if species in _DEX_BY_NAME:
                    self._reported_owned.add(_DEX_BY_NAME[species])

    # ------------------------------------------------------------------ #
    # world graph persistence (survives load_state / --resume / restarts)
    # ------------------------------------------------------------------ #
    def world_data(self) -> Optional[dict]:
        if not self.world:
            return None
        data = {str(m): {"warps": [list(w) for w in info["warps"]], "conns": [list(c) for c in info["conns"]],
                         "outside": info.get("outside")} for m, info in self.world.items()}
        if self.spinners:
            data["spinners"] = {str(m): [[*a, *b] for a, b in cells.items()] for m, cells in self.spinners.items()}
        return data

    def note_spinner(self, mid: int, cell: tuple[int, int], end: tuple[int, int]) -> None:
        """A spinner tile at `cell` carried the player to `end`; find_path uses it as a one-way jump from now on."""
        if cell != end:
            self.spinners.setdefault(mid, {})[cell] = end

    def load_world(self, data: dict) -> None:
        for key, cells in ((data or {}).get("spinners") or {}).items():
            for c in cells if isinstance(cells, list) else []:
                if len(c) == 4:
                    self.note_spinner(int(key), (c[0], c[1]), (c[2], c[3]))
        for key, info in (data or {}).items():
            try:
                m = int(key)
            except (TypeError, ValueError):
                continue
            if m in self.world or not isinstance(info, dict):
                continue
            self.world[m] = {"warps": [tuple(w) for w in info.get("warps", [])],
                             "conns": [tuple(c) for c in info.get("conns", [])], "outside": info.get("outside")}
            self.visited.add(m)

    # ------------------------------------------------------------------ #
    # metrics
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict[str, Any]:
        if not self.started():
            return {"started": False}
        owned, seen = self.dex_counts()
        party = self.party()
        m = self._u8(D.CUR_MAP)
        self.visited.add(m)
        fighting = self.in_battle() != 0
        if not fighting and not self.off_map((m, self._u8(D.PLAYER_X), self._u8(D.PLAYER_Y))):
            self.world[m] = {"warps": self.warps(), "conns": self.connections(), "outside": self._u8(D.LAST_MAP)}
        if fighting and not self._was_in_battle:
            self._battles += 1
        self._was_in_battle = fighting
        return {
            "started": True,
            "playtime": self.playtime(),
            "badges": self.badges(),
            "badge_bits": self._u8(D.BADGES),
            "dex_owned": owned,
            "dex_seen": seen,
            "owned_set": sorted(self.dex_owned_set()),
            "have_dex": sorted(self.have_dex_numbers()),
            "party_count": len(party),
            "max_level": max((p["level"] for p in party), default=0),
            "party": [f"{p['species']} L{p['level']}" for p in party],
            "team": [{"species": p["species"], "nick": p["nick"], "level": p["level"], "hp": p["hp"],
                      "max_hp": p["max_hp"], "status": p["status"], "types": p["types"],
                      "moves": [[n, pp] for n, pp in p["moves"]], "stats": list(p["stats"])} for p in party],
            "surfing": self._u8(D.WALK_BIKE_SURF) == 2,
            "money": self.money(),
            "map": m,
            "map_name": D.map_name(m),
            "maps_visited": len(self.visited),
            "hall_of_fame": self._u8(D.NUM_HOF_TEAMS),
            "battles": self._battles,
            "in_battle": self.in_battle(),
        }

    def milestones(self, prev: dict[str, Any], cur: dict[str, Any]) -> list[str]:
        out = []
        if not cur.get("started"):
            return out
        if not prev.get("started"):
            out.append("game started")
            prev = {"badge_bits": 0, "owned_set": [], "hall_of_fame": 0, "map": -1, "party_count": 0}
        pb, cb = prev.get("badge_bits", 0), cur.get("badge_bits", 0)
        for i in range(8):
            if cb & (1 << i) and not pb & (1 << i):
                out.append(f"badge: {D.BADGE_NAMES[i]}")
        # Scripts (e.g. Oak's lab) briefly scribble on the Pokédex flags, so a new "owned" bit only
        # counts when that species is really in the party or the PC box.
        owned_now = set(cur.get("owned_set", []))
        have = set(cur.get("have_dex", []))
        confirmed = (owned_now & have) - self._reported_owned
        # evolution: same party size, a slot's species changed into the newly owned species
        evolved = {}
        prev_party, cur_party = prev.get("party", []), cur.get("party", [])
        if len(prev_party) == len(cur_party):
            for a, b in zip(prev_party, cur_party):
                sa, sb = a.rsplit(" L", 1)[0], b.rsplit(" L", 1)[0]
                if sa != sb and _DEX_BY_NAME.get(sb) in confirmed:
                    evolved[_DEX_BY_NAME[sb]] = f"evolved: {sa} → {sb}"
        for n in sorted(confirmed):
            out.append(evolved.get(n, f"obtained: {_DEX[n - 1]}"))
        self._reported_owned |= confirmed
        # The starter: the only time a party grows from empty (you can never deposit your last Pokémon).
        if not self._starter_reported and prev.get("party_count", 0) == 0 and cur.get("party_count", 0) >= 1 and cur_party:
            self._starter_reported = True
            out.append(f"starter: {cur_party[0].rsplit(' L', 1)[0]}")
        # Elite Four / Champion rooms hold one trainer each: a trainer battle ending normally (not with
        # the 0xFF loss flag) while still in that room means that member was defeated.
        m = cur.get("map")
        if prev.get("in_battle") == 2 and cur.get("in_battle") == 0 and prev.get("map") == m and m in D.E4_ROOMS:
            out.append(f"defeated: {D.E4_ROOMS[m]}")
        if cur.get("hall_of_fame", 0) > prev.get("hall_of_fame", 0):
            out.append("champion defeated (Hall of Fame)")
        if cur.get("in_battle") == 0xFF and prev.get("in_battle") != 0xFF:
            out.append("blacked out (lost a battle)")
        if m != prev.get("map") and m in _LANDMARKS and m not in self._reported_maps:
            self._reported_maps.add(m)
            out.append(f"reached: {D.map_name(m)}")
        return out
