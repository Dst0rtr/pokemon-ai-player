"""
Static data tables for Pokémon Red/Blue/Yellow (Generation 1).

Sources: pokered disassembly (constants/*.asm) and the Data Crystal RAM map.
Addresses verified empirically against a running Pokémon Red ROM (see tests/).
"""

# --------------------------------------------------------------------------- #
# WRAM addresses
# --------------------------------------------------------------------------- #
PLAYER_NAME = 0xD158        # 11 bytes, 0x50-terminated
RIVAL_NAME = 0xD34A
PARTY_COUNT = 0xD163
PARTY_SPECIES = 0xD164      # 7 bytes (6 + 0xFF terminator)
PARTY_MONS = 0xD16B         # 6 x 44-byte structs
PARTY_MON_SIZE = 44
PARTY_OT_NAMES = 0xD273     # 6 x 11 bytes
PARTY_NICKS = 0xD2B5        # 6 x 11 bytes
NAME_LEN = 11
POKEDEX_OWNED = 0xD2F7      # 19 bytes of bit flags
POKEDEX_SEEN = 0xD30A       # 19 bytes of bit flags
BAG_COUNT = 0xD31D
BAG_ITEMS = 0xD31E          # (item, qty) pairs, 0xFF terminated, max 20
MONEY = 0xD347              # 3 bytes BCD
OPTIONS = 0xD355            # bits 0-2 text speed (1 fast/3 mid/5 slow), bit6 battle style, bit7 anims off
BADGES = 0xD356             # bit flags
CUR_MAP = 0xD35E
LAST_MAP = 0xD365           # wLastMap: the outdoor map an "outside" (0xFF) warp returns to
PLAYER_Y = 0xD361
PLAYER_X = 0xD362
MAP_HEIGHT = 0xD368         # in 2x2 blocks
MAP_WIDTH = 0xD369
NUM_WARPS = 0xD3AE
WARPS = 0xD3AF              # 4 bytes each: y, x, dest warp id, dest map
MAP_CONNECTIONS = 0xD370     # bit3 north, bit2 south, bit1 west, bit0 east
CONNECTION_HEADERS = {"north": 0xD371, "south": 0xD37C, "west": 0xD387, "east": 0xD392}  # first byte = map id
TILESET_BANK = 0xD52B
TILESET_BLOCKS_PTR = 0xD52C  # ROM pointer (in TILESET_BANK) to 16-byte block definitions
OVERWORLD_MAP = 0xC6E8       # (width+3*2) x (height+3*2) block ids, 3-block border
TILESET_COLLISION_PTR = 0xD530
GRASS_TILE = 0xD535
JOY_IGNORE = 0xCD6B         # wJoyIgnore: bit set = that button is ignored; non-zero during scripted scenes
IS_IN_BATTLE = 0xD057       # 0 none, 1 wild, 2 trainer, 0xFF lost
BATTLE_TYPE = 0xD05A        # 0 normal, 1 old man, 2 safari
ENEMY_MON = 0xCFE5          # species, hp(2), lvl(box), status, type1, type2, catch, moves(4), dvs(2), level(@0xCFF3), maxhp(2)...
BATTLE_MON = 0xD014         # same layout as enemy: species, hp(2), ..., level @ +14 (0xD022), maxhp @ +15
BATTLE_MON_PP = 0xD02D      # 4 bytes
ENEMY_MON_PP = 0xCFFE
PLAY_TIME_HOURS = 0xDA41
PLAY_TIME_MINUTES = 0xDA43
PLAY_TIME_SECONDS = 0xDA44
PLAY_TIME_FRAMES = 0xDA45
BOX_COUNT = 0xDA80          # current PC box: count, then species list (0xFF terminated)
BOX_SPECIES = 0xDA81
NUM_HOF_TEAMS = 0xD5A0      # incremented each Hall of Fame entry (= Champion defeated)
SFX_CHANNELS = 0xC02A       # wChannelSoundIDs[4..7]: non-zero while a sound effect / jingle plays
SPRITE_STATE_1 = 0xC100     # 16 sprites x 16 bytes; +0 picture id, +9 facing (0 down,4 up,8 left,0xC right)
SPRITE_STATE_2 = 0xC200     # +4 map y + 4, +5 map x + 4

# Party mon struct offsets (44 bytes)
MON_SPECIES = 0
MON_HP = 1          # 2 bytes big-endian
MON_STATUS = 4
MON_TYPE1 = 5
MON_TYPE2 = 6
MON_MOVES = 8       # 4 bytes
MON_EXP = 14        # 3 bytes
MON_PP = 29         # 4 bytes
MON_LEVEL = 33
MON_MAX_HP = 34
MON_ATTACK = 36
MON_DEFENSE = 38
MON_SPEED = 40
MON_SPECIAL = 42

FACING = {0: "down", 4: "up", 8: "left", 0xC: "right"}
CUR_TILESET = 0xD367
# One-way ledge tiles of the outdoor tileset (tileset 0), from pokered LedgeTiles: tile -> jump direction
LEDGE_TILES = {0x36: "down", 0x37: "down", 0x27: "left", 0x0D: "right", 0x1D: "right"}
LEDGE_CHAR = {"down": "v", "left": "<", "right": ">"}
LEDGE_DIR = {"v": "down", "<": "left", ">": "right"}
BADGE_NAMES = ["Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth"]

TYPES = {0: "Normal", 1: "Fighting", 2: "Flying", 3: "Poison", 4: "Ground", 5: "Rock", 7: "Bug",
         8: "Ghost", 20: "Fire", 21: "Water", 22: "Grass", 23: "Electric", 24: "Psychic",
         25: "Ice", 26: "Dragon"}


def status_name(b: int, hp: int = 1) -> str:
    if hp == 0:
        return "FNT"
    if b & 0x40:
        return "PAR"
    if b & 0x20:
        return "FRZ"
    if b & 0x10:
        return "BRN"
    if b & 0x08:
        return "PSN"
    if b & 0x07:
        return "SLP"
    return ""


# --------------------------------------------------------------------------- #
# Text encoding (also used for tile IDs in VRAM: the font lives at the same
# indices, so decoding the tilemap gives the on-screen text).
# --------------------------------------------------------------------------- #
CHARMAP: dict[int, str] = {
    0x50: "", 0x7F: " ",
    0x79: "", 0x7A: "", 0x7B: "", 0x7C: "", 0x7D: "", 0x7E: "",   # text box borders
    0x9A: "(", 0x9B: ")", 0x9C: ":", 0x9D: ";", 0x9E: "[", 0x9F: "]",
    0xBA: "é", 0xBB: "'d", 0xBC: "'l", 0xBD: "'s", 0xBE: "'t", 0xBF: "'v",
    0xE0: "'", 0xE1: "PK", 0xE2: "MN", 0xE3: "-", 0xE4: "'r", 0xE5: "'m",
    0xE6: "?", 0xE7: "!", 0xE8: ".", 0xEC: "▷", 0xED: "▶", 0xEE: "▼",
    0xEF: "♂", 0xF0: "¥", 0xF1: "×", 0xF3: "/", 0xF4: ",", 0xF5: "♀",
}
for _i in range(26):
    CHARMAP[0x80 + _i] = chr(65 + _i)
    CHARMAP[0xA0 + _i] = chr(97 + _i)
for _i in range(10):
    CHARMAP[0xF6 + _i] = str(_i)
TEXT_BORDER_TILES = {0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E}
# VRAM bytes of the 'A' glyph (tile 0x80 at 0x8800) whenever the font is loaded.
# The title screen and some overworld screens keep other graphics there, so the
# tilemap can only be decoded as text when this signature is present.
FONT_A_TILE = bytes.fromhex("10102828282844447c7c828282820000")
FONT_A_ADDR = 0x8800


def decode_text(codes) -> str:
    out = []
    for c in codes:
        if c == 0x50:
            break
        out.append(CHARMAP.get(c, "?" if c >= 0x60 else ""))
    return "".join(out)


# --------------------------------------------------------------------------- #
# Species by internal index (1-190). MISSINGNO. slots are None.
# --------------------------------------------------------------------------- #
_SPECIES_LIST = [
    None, "Rhydon", "Kangaskhan", "Nidoran♂", "Clefairy", "Spearow", "Voltorb", "Nidoking",
    "Slowbro", "Ivysaur", "Exeggutor", "Lickitung", "Exeggcute", "Grimer", "Gengar",
    "Nidoran♀", "Nidoqueen", "Cubone", "Rhyhorn", "Lapras", "Arcanine", "Mew", "Gyarados",
    "Shellder", "Tentacool", "Gastly", "Scyther", "Staryu", "Blastoise", "Pinsir", "Tangela",
    None, None, "Growlithe", "Onix", "Fearow", "Pidgey", "Slowpoke", "Kadabra", "Graveler",
    "Chansey", "Machoke", "Mr. Mime", "Hitmonlee", "Hitmonchan", "Arbok", "Parasect",
    "Psyduck", "Drowzee", "Golem", None, "Magmar", None, "Electabuzz", "Magneton", "Koffing",
    None, "Mankey", "Seel", "Diglett", "Tauros", None, None, None, "Farfetch'd", "Venonat",
    "Dragonite", None, None, None, "Doduo", "Poliwag", "Jynx", "Moltres", "Articuno", "Zapdos",
    "Ditto", "Meowth", "Krabby", None, None, None, "Vulpix", "Ninetales", "Pikachu", "Raichu",
    None, None, "Dratini", "Dragonair", "Kabuto", "Kabutops", "Horsea", "Seadra", None, None,
    "Sandshrew", "Sandslash", "Omanyte", "Omastar", "Jigglypuff", "Wigglytuff", "Eevee",
    "Flareon", "Jolteon", "Vaporeon", "Machop", "Zubat", "Ekans", "Paras", "Poliwhirl",
    "Poliwrath", "Weedle", "Kakuna", "Beedrill", None, "Dodrio", "Primeape", "Dugtrio",
    "Venomoth", "Dewgong", None, None, "Caterpie", "Metapod", "Butterfree", "Machamp", None,
    "Golduck", "Hypno", "Golbat", "Mewtwo", "Snorlax", "Magikarp", None, None, "Muk", None,
    "Kingler", "Cloyster", None, "Electrode", "Clefable", "Weezing", "Persian", "Marowak",
    None, "Haunter", "Abra", "Alakazam", "Pidgeotto", "Pidgeot", "Starmie", "Bulbasaur",
    "Venusaur", "Tentacruel", None, "Goldeen", "Seaking", None, None, None, None, "Ponyta",
    "Rapidash", "Rattata", "Raticate", "Nidorino", "Nidorina", "Geodude", "Porygon",
    "Aerodactyl", None, "Magnemite", None, None, "Charmander", "Squirtle", "Charmeleon",
    "Wartortle", "Charizard", None, None, None, None, "Oddish", "Gloom", "Vileplume",
    "Bellsprout", "Weepinbell", "Victreebel",
]
assert len(_SPECIES_LIST) == 191
SPECIES = {i: n for i, n in enumerate(_SPECIES_LIST) if n}


def species_name(idx: int) -> str:
    return SPECIES.get(idx, f"MissingNo({idx})")


# --------------------------------------------------------------------------- #
# Moves by index (1-165)
# --------------------------------------------------------------------------- #
_MOVES = """Pound,Karate Chop,DoubleSlap,Comet Punch,Mega Punch,Pay Day,Fire Punch,Ice Punch,
ThunderPunch,Scratch,ViceGrip,Guillotine,Razor Wind,Swords Dance,Cut,Gust,Wing Attack,
Whirlwind,Fly,Bind,Slam,Vine Whip,Stomp,Double Kick,Mega Kick,Jump Kick,Rolling Kick,
Sand-Attack,Headbutt,Horn Attack,Fury Attack,Horn Drill,Tackle,Body Slam,Wrap,Take Down,
Thrash,Double-Edge,Tail Whip,Poison Sting,Twineedle,Pin Missile,Leer,Bite,Growl,Roar,Sing,
Supersonic,SonicBoom,Disable,Acid,Ember,Flamethrower,Mist,Water Gun,Hydro Pump,Surf,
Ice Beam,Blizzard,Psybeam,BubbleBeam,Aurora Beam,Hyper Beam,Peck,Drill Peck,Submission,
Low Kick,Counter,Seismic Toss,Strength,Absorb,Mega Drain,Leech Seed,Growth,Razor Leaf,
SolarBeam,PoisonPowder,Stun Spore,Sleep Powder,Petal Dance,String Shot,Dragon Rage,
Fire Spin,ThunderShock,Thunderbolt,Thunder Wave,Thunder,Rock Throw,Earthquake,Fissure,Dig,
Toxic,Confusion,Psychic,Hypnosis,Meditate,Agility,Quick Attack,Rage,Teleport,Night Shade,
Mimic,Screech,Double Team,Recover,Harden,Minimize,SmokeScreen,Confuse Ray,Withdraw,
Defense Curl,Barrier,Light Screen,Haze,Reflect,Focus Energy,Bide,Metronome,Mirror Move,
Selfdestruct,Egg Bomb,Lick,Smog,Sludge,Bone Club,Fire Blast,Waterfall,Clamp,Swift,
Skull Bash,Spike Cannon,Constrict,Amnesia,Kinesis,Softboiled,Hi Jump Kick,Glare,Dream Eater,
Poison Gas,Barrage,Leech Life,Lovely Kiss,Sky Attack,Transform,Bubble,Dizzy Punch,Spore,
Flash,Psywave,Splash,Acid Armor,Crabhammer,Explosion,Fury Swipes,Bonemerang,Rest,Rock Slide,
Hyper Fang,Sharpen,Conversion,Tri Attack,Super Fang,Slash,Substitute,Struggle"""
MOVES = {i + 1: n for i, n in enumerate(_MOVES.replace("\n", "").split(","))}
assert len(MOVES) == 165


def move_name(idx: int) -> str:
    return MOVES.get(idx, f"move{idx}")


# --------------------------------------------------------------------------- #
# Items by index
# --------------------------------------------------------------------------- #
_ITEMS = """Master Ball,Ultra Ball,Great Ball,Poké Ball,Town Map,Bicycle,?????,Safari Ball,
Pokédex,Moon Stone,Antidote,Burn Heal,Ice Heal,Awakening,Parlyz Heal,Full Restore,
Max Potion,Hyper Potion,Super Potion,Potion,BoulderBadge,CascadeBadge,ThunderBadge,
RainbowBadge,SoulBadge,MarshBadge,VolcanoBadge,EarthBadge,Escape Rope,Repel,Old Amber,
Fire Stone,Thunderstone,Water Stone,HP Up,Protein,Iron,Carbos,Calcium,Rare Candy,
Dome Fossil,Helix Fossil,Secret Key,?????,Bike Voucher,X Accuracy,Leaf Stone,Card Key,
Nugget,PP Up,Poké Doll,Full Heal,Revive,Max Revive,Guard Spec.,Super Repel,Max Repel,
Dire Hit,Coin,Fresh Water,Soda Pop,Lemonade,S.S. Ticket,Gold Teeth,X Attack,X Defend,
X Speed,X Special,Coin Case,Oak's Parcel,Itemfinder,Silph Scope,Poké Flute,Lift Key,
Exp. All,Old Rod,Good Rod,Super Rod,PP Up,Ether,Max Ether,Elixer,Max Elixer"""
ITEMS = {i + 1: n for i, n in enumerate(_ITEMS.replace("\n", "").split(","))}
for _i in range(5):
    ITEMS[0xC4 + _i] = f"HM0{_i + 1}"
for _i in range(50):
    ITEMS[0xC9 + _i] = f"TM{_i + 1:02d}"


def item_name(idx: int) -> str:
    return ITEMS.get(idx, f"item{idx}")


# --------------------------------------------------------------------------- #
# Map names by ID (pokered map_constants order)
# --------------------------------------------------------------------------- #
MAPS: dict[int, str] = {
    0: "Pallet Town", 1: "Viridian City", 2: "Pewter City", 3: "Cerulean City",
    4: "Lavender Town", 5: "Vermilion City", 6: "Celadon City", 7: "Fuchsia City",
    8: "Cinnabar Island", 9: "Indigo Plateau", 10: "Saffron City",
}
for _i in range(1, 26):
    MAPS[11 + _i] = f"Route {_i}"
MAPS.update({
    37: "Red's House 1F", 38: "Red's House 2F", 39: "Blue's House", 40: "Oak's Lab",
    41: "Viridian Poké Center", 42: "Viridian Mart", 43: "Viridian School",
    44: "Viridian House", 45: "Viridian Gym", 46: "Diglett's Cave (Route 2 side)",
    47: "Viridian Forest North Gate", 48: "Route 2 Trade House", 49: "Route 2 Gate",
    50: "Viridian Forest South Gate", 51: "Viridian Forest", 52: "Pewter Museum 1F",
    53: "Pewter Museum 2F", 54: "Pewter Gym", 55: "Pewter Nidoran House", 56: "Pewter Mart",
    57: "Pewter Speech House", 58: "Pewter Poké Center", 59: "Mt. Moon 1F",
    60: "Mt. Moon B1F", 61: "Mt. Moon B2F", 62: "Cerulean Trashed House",
    63: "Cerulean Trade House", 64: "Cerulean Poké Center", 65: "Cerulean Gym",
    66: "Bike Shop", 67: "Cerulean Mart", 68: "Mt. Moon Poké Center",
    70: "Route 5 Gate", 71: "Underground Path (Route 5)", 72: "Daycare", 73: "Route 6 Gate",
    74: "Underground Path (Route 6)", 75: "Route 7 Gate", 76: "Underground Path (Route 7)",
    78: "Route 8 Gate", 79: "Underground Path (Route 8)", 80: "Rock Tunnel Poké Center",
    81: "Rock Tunnel 1F", 82: "Power Plant", 83: "Route 11 Gate 1F",
    84: "Diglett's Cave (Route 11 side)", 85: "Route 11 Gate 2F", 86: "Route 12 Gate 1F",
    87: "Bill's House", 88: "Vermilion Poké Center", 89: "Pokémon Fan Club",
    90: "Vermilion Mart", 91: "Vermilion Gym", 92: "Vermilion Pidgey House",
    93: "Vermilion Dock", 94: "S.S. Anne 1F", 95: "S.S. Anne 2F", 96: "S.S. Anne 3F",
    97: "S.S. Anne B1F", 98: "S.S. Anne Bow", 99: "S.S. Anne Kitchen",
    100: "S.S. Anne Captain's Room", 101: "S.S. Anne 1F Rooms", 102: "S.S. Anne 2F Rooms",
    103: "S.S. Anne B1F Rooms", 108: "Victory Road 1F", 113: "Lance's Room",
    118: "Hall of Fame", 119: "Underground Path N-S", 120: "Champion's Room",
    121: "Underground Path W-E", 122: "Celadon Mart 1F", 123: "Celadon Mart 2F",
    124: "Celadon Mart 3F", 125: "Celadon Mart 4F", 126: "Celadon Mart Roof",
    127: "Celadon Mart Elevator", 128: "Celadon Mansion 1F", 129: "Celadon Mansion 2F",
    130: "Celadon Mansion 3F", 131: "Celadon Mansion Roof", 132: "Celadon Mansion Roof House",
    133: "Celadon Poké Center", 134: "Celadon Gym", 135: "Game Corner", 136: "Celadon Mart 5F",
    137: "Game Corner Prize Room", 138: "Celadon Diner", 139: "Celadon Chief House",
    140: "Celadon Hotel", 141: "Lavender Poké Center", 142: "Pokémon Tower 1F",
    143: "Pokémon Tower 2F", 144: "Pokémon Tower 3F", 145: "Pokémon Tower 4F",
    146: "Pokémon Tower 5F", 147: "Pokémon Tower 6F", 148: "Pokémon Tower 7F",
    149: "Mr. Fuji's House", 150: "Lavender Mart", 151: "Lavender Cubone House",
    152: "Fuchsia Mart", 153: "Bill's Grandpa's House", 154: "Fuchsia Poké Center",
    155: "Warden's House", 156: "Safari Zone Gate", 157: "Fuchsia Gym",
    158: "Fuchsia Meeting Room", 159: "Seafoam Islands B1F", 160: "Seafoam Islands B2F",
    161: "Seafoam Islands B3F", 162: "Seafoam Islands B4F", 163: "Vermilion Old Rod House",
    164: "Fuchsia Good Rod House", 165: "Pokémon Mansion 1F", 166: "Cinnabar Gym",
    167: "Cinnabar Lab", 168: "Cinnabar Lab Trade Room", 169: "Cinnabar Lab Metronome Room",
    170: "Cinnabar Lab Fossil Room", 171: "Cinnabar Poké Center", 172: "Cinnabar Mart",
    174: "Indigo Plateau Lobby", 175: "Copycat's House 1F", 176: "Copycat's House 2F",
    177: "Fighting Dojo", 178: "Saffron Gym", 179: "Saffron Pidgey House", 180: "Saffron Mart",
    181: "Silph Co. 1F", 182: "Saffron Poké Center", 183: "Mr. Psychic's House",
    184: "Route 15 Gate 1F", 185: "Route 15 Gate 2F", 186: "Route 16 Gate 1F",
    187: "Route 16 Gate 2F", 188: "Route 16 Fly House", 189: "Route 12 Super Rod House",
    190: "Route 18 Gate 1F", 191: "Route 18 Gate 2F", 192: "Seafoam Islands 1F",
    193: "Route 22 Gate", 194: "Victory Road 2F", 195: "Route 12 Gate 2F",
    196: "Vermilion Trade House", 197: "Diglett's Cave", 198: "Victory Road 3F",
    199: "Rocket Hideout B1F", 200: "Rocket Hideout B2F", 201: "Rocket Hideout B3F",
    202: "Rocket Hideout B4F", 203: "Rocket Hideout Elevator", 207: "Silph Co. 2F",
    208: "Silph Co. 3F", 209: "Silph Co. 4F", 210: "Silph Co. 5F", 211: "Silph Co. 6F",
    212: "Silph Co. 7F", 213: "Silph Co. 8F", 214: "Pokémon Mansion 2F",
    215: "Pokémon Mansion 3F", 216: "Pokémon Mansion B1F", 217: "Safari Zone East",
    218: "Safari Zone North", 219: "Safari Zone West", 220: "Safari Zone Center",
    221: "Safari Zone Center Rest House", 222: "Safari Zone Secret House",
    223: "Safari Zone West Rest House", 224: "Safari Zone East Rest House",
    225: "Safari Zone North Rest House", 226: "Cerulean Cave 2F", 227: "Cerulean Cave B1F",
    228: "Cerulean Cave 1F", 229: "Name Rater's House", 230: "Cerulean Badge House",
    234: "Rock Tunnel B1F", 235: "Silph Co. 9F", 236: "Silph Co. 10F", 237: "Silph Co. 11F",
    238: "Silph Co. Elevator", 245: "Trade Center", 246: "Colosseum", 248: "Lorelei's Room",
    249: "Bruno's Room", 250: "Agatha's Room",
})


def map_name(idx: int) -> str:
    return MAPS.get(idx, f"Map#{idx}")
