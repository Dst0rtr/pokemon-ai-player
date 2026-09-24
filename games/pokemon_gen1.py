"""
Profile for Pokémon Red / Blue / Yellow.

Everything here is read straight from WRAM/VRAM, so the agent can get party,
battle, map and dialogue information as a few lines of text instead of images.
"""

from __future__ import annotations

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
                 "Mirror Move", "Bide", "Counter"}


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
        self.world: dict[int, dict] = {}        # visited map id -> {"warps": [(x,y,dest)], "conns": [(side,dest)]}
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

    def npcs(self) -> list[tuple[int, int]]:
        out = []
        for i in range(1, 16):
            if self._u8(D.SPRITE_STATE_1 + 16 * i):
                out.append((self._u8(D.SPRITE_STATE_2 + 16 * i + 5) - 4, self._u8(D.SPRITE_STATE_2 + 16 * i + 4) - 4))
        return out

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
        for nx, ny in self.npcs():
            if 0 <= nx < w and 0 <= ny < h:
                cells[ny][nx] = "N"
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

    def battle_auto(self, emu, target: str = "") -> str:
        """Fight with damaging moves until the battle ends, a prompt appears, or HP gets low."""
        logs: list[str] = []
        if self.in_safari_battle():
            return "Safari Zone battle: there is no FIGHT. battle('item') throws a Safari Ball, battle('bait') / battle('rock') change catch odds, battle('run') leaves"
        for turn in range(25):
            if not self.in_battle():
                break
            b = self.battle()
            if b and b["mine"]["max_hp"] and b["mine"]["hp"] <= b["mine"]["max_hp"] // 4 and turn:
                return " | ".join(logs) + f" — stopped: {b['mine']['species']} is low on HP ({b['mine']['hp']}/{b['mine']['max_hp']}); switch, use an item, run, or battle('auto') again to keep going"
            move = ""
            if b and b["mine"]["moves"]:
                usable = [(n, pp) for n, pp in b["mine"]["moves"] if pp > 0 and n != b["mine"].get("disabled")]
                wanted = next((n for n, _ in usable if target and self._norm(target) in self._norm(n)), None)
                dmg = [n for n, _ in usable if n not in _STATUS_MOVES]
                move = wanted or (dmg[0] if dmg else (usable[0][0] if usable else ""))
            r = self.battle_action(emu, "fight", move)
            logs.append(r)
            if ("needs a decision" in r or "prompt" in r or "battle('switch'" in r or "battle over" in r
                    or "battle is over" in r or r.startswith(("cannot", "could not", "no move", "no PP"))):
                break
        out = " | ".join(logs)
        return out if out else ("not in a battle" if not self.in_battle() else "nothing happened")

    def battle_action(self, emu, action: str, target: str = "") -> str:
        action = (action or "fight").lower().strip()
        if action == "auto":
            return self.battle_auto(emu, target)
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
                matches = [i for i, p in enumerate(party) if t and (t in self._norm(p["species"]) or t in self._norm(p["nick"]))]
                if not matches:
                    return "which Pokémon? give its party number or name: " + ", ".join(f"{i + 1}={p['species']}" for i, p in enumerate(party))
                idx = matches[0]
            if party[idx]["hp"] == 0:
                return f"{party[idx]['species']} has fainted; pick another"
            if kind == "main":
                if not self._select_main(emu, (1, 0)):
                    return "cannot open the party menu now"
                emu.press("A", settle=1)
            names = [self._norm(p["species"]) for p in party]
            cur = self._list_cursor(self.screen_text() or "", names) or 0
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
            return "hint: a small tree blocks the way: manage('field', 'Cut') while facing it (teach HM01 first; needs the Cascade Badge)"
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

    def _pick_party(self, emu, target: str) -> Optional[int]:
        party = self.party()
        t = self._norm(target)
        if t.isdigit():
            idx = int(t) - 1
            return idx if 0 <= idx < len(party) else None
        for i, p in enumerate(party):
            if t and (t in self._norm(p["species"]) or t in self._norm(p["nick"])):
                return i
        return None

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
        return "unknown action; use lead, swap, use, field or save"

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
        """Move the ▶ cursor of the open party list to slot k (the menu remembers its last position)."""
        for _ in range(8):
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

    def _use_item(self, emu, target: str, target2: str) -> str:
        """START → ITEM → item → USE, answering the prompts: a Pokémon to use it on (target2), and for
        TMs/HMs the move to forget ("Charmander: Growl")."""
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
        for _ in range(len(bag) + 2):                          # the bag list scrolls: move until the item is under the cursor
            if self._norm(self._cursor_line()).startswith(self._norm(item_name)[:6]):
                break
            emu.press("DOWN", settle=1)
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
                       f"manage('use', '{item_name}', '{mon['species'] if mon else mon_target}: <move to forget>')")
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

    def full_map_cells(self) -> list[list[str]]:
        """Walkability of every 2x2-tile metatile of the current map."""
        walkable = self._walkable_tiles()
        grass = self._u8(D.GRASS_TILE)
        tileset = self._u8(D.CUR_TILESET)
        ledges = D.LEDGE_TILES if tileset == 0 else {}
        water = D.WATER_TILE if tileset in D.WATER_TILESETS else -1
        tree = D.CUT_TREE_TILES.get(tileset, -1)
        cells = []
        for trow in self.full_map_tiles():
            row = []
            for tile in trow:
                if tile == grass:
                    row.append(",")
                elif tile in ledges:
                    row.append(D.LEDGE_CHAR[ledges[tile]])
                elif tile in walkable:
                    row.append(".")
                elif tile == water:
                    row.append("~")
                elif tile == tree:
                    row.append("T")
                else:
                    row.append("#")
            cells.append(row)
        return cells

    def find_path(self, tx: int, ty: int, avoid=frozenset()) -> Optional[list[tuple[str, int]]]:
        """Dijkstra over the decoded map. NPC sprites are expensive rather than solid (some are hidden
        by events, others wander off); cells in `avoid` were found solid by walking and are walls."""
        if self.in_battle() or not self.started():
            return None
        _, px, py = self.position()
        cells = self.full_map_cells()
        h, w = len(cells), len(cells[0]) if cells else 0
        if not (0 <= tx < w and 0 <= ty < h):
            return None
        npc_cells = {(nx, ny) for nx, ny in self.npcs()}
        blocked = set(avoid)
        # Never cross another warp on the way (stairs, ladders, teleport pads would whisk the player away).
        blocked |= {(wx, wy) for wx, wy, _ in self.warps() if (wx, wy) != (tx, ty)}
        if 0 <= tx < w and 0 <= ty < h and cells[ty][tx] in ("#",) and any((wx, wy) == (tx, ty) for wx, wy, _ in self.warps()):
            cells[ty][tx] = "."                 # a solid door tile can still be walked into as the destination
        if (tx, ty) == (px, py):
            return []
        solid = ("#", "T") if self.surfing() else ("#", "T", "~")
        tileset = self._u8(D.CUR_TILESET)
        pairs = set(D.TILE_PAIR_COLLISIONS_LAND.get(tileset, ()))
        if self.surfing():
            pairs |= set(D.TILE_PAIR_COLLISIONS_WATER.get(tileset, ()))
        tiles = self.full_map_tiles() if pairs else None       # cave/forest elevation steps you cannot cross
        moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        prev: dict[tuple[int, int], tuple[tuple[int, int], str]] = {}
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
                nc = cost + step
                if nc < dist.get((nx, ny), 1 << 30):
                    dist[(nx, ny)] = nc
                    prev[(nx, ny)] = ((x, y), d)
                    heapq.heappush(heap, (nc, nx, ny))
        if (tx, ty) not in prev:
            return None
        dirs = []                                    # (direction, cells moved) per move; ledge jumps span 2 cells
        cur = (tx, ty)
        while cur != (px, py):
            (bx, by), d = prev[cur]
            dirs.append((d, abs(cur[0] - bx) + abs(cur[1] - by)))
            cur = (bx, by)
        dirs.reverse()
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
            return None
        return best[1], best[2], sides[want]

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
            return "the target is a small tree: stand next to it facing it and manage('field', 'Cut') removes it"
        flat = {ch for row in cells for ch in row}
        notes = []
        if "T" in flat:
            notes.append("a small tree (T) may block the way: face it and manage('field', 'Cut')")
        if "~" in flat and not self.surfing():
            notes.append("water (~) needs Surf: face it and manage('field', 'Surf')")
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
        for nx, ny in self.npcs():
            if 0 <= nx < w and 0 <= ny < h:
                cells[ny][nx] = "N"
        if 0 <= px < w and 0 <= py < h:
            cells[py][px] = "P"
        head = (f"{D.map_name(m)} {w}x{h}, you at ({px},{py}) facing {self.facing()}. "
                "x→ right, y↓ down. P=you N=npc D=door/warp #=blocked .=walkable ,=tall grass v<>=one-way ledge "
                "~=water (Surf) T=small tree (Cut)")
        ruler = "   " + "".join(str(x % 10) for x in range(w))
        body = "\n".join(f"{y:2d} " + "".join(row) for y, row in enumerate(cells))
        exits = ", ".join(f"({wx},{wy})→{self.map_label(d)}" for wx, wy, d in self.warps()[:12])
        conns = ", ".join(f"{side} edge→{D.map_name(mid)}" for side, mid in self.connections())
        tail = "\n".join(t for t in (f"exits: {exits}" if exits else "", f"connections: {conns}" if conns else "") if t)
        return head + "\n" + ruler + "\n" + body + ("\n" + tail if tail else "")

    # ------------------------------------------------------------------ #
    # world graph persistence (survives load_state / --resume / restarts)
    # ------------------------------------------------------------------ #
    def world_data(self) -> Optional[dict]:
        if not self.world:
            return None
        return {str(m): {"warps": [list(w) for w in info["warps"]], "conns": [list(c) for c in info["conns"]],
                         "outside": info.get("outside")} for m, info in self.world.items()}

    def load_world(self, data: dict) -> None:
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
