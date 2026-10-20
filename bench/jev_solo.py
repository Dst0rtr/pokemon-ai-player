"""
jev-solo: Jev plays the whole game with no LLM anywhere. Long-horizon structure comes from code:

  * GRAPH: an ordered objective graph for all of Pokémon Red. Each node has a code-side `done` test
    over Facts read from the server (badges, bag contents incl. key items and HMs, moves the party
    knows, maps visited, milestones) and walk targets (waypoints) for the candidate set.
  * Where code cannot see completion (story events with no verified RAM address in this repo, e.g.
    "delivered the parcel" is visible, "woke Snorlax" is not), the node is marked `jev_check` and Jev
    answers a Noul "is this objective done?" from the screen text and recent actions; three answers
    >= 0.8 in a row mark it done.
  * Code rules that override the objective: heal when the team is weak, train before a gym when the
    best Pokémon is under the level target (numbers stay in code: Jev is not a calculator), teach an HM
    as soon as it is in the bag, use Cut/Surf/Strength when the hint says an obstacle is in front.
  * Stuck recovery: no new map / milestone / item for a while, or the same position for many steps,
    raises a recovery level that adds frontier exploration (exits to unvisited maps, longer walks),
    presses B to close stray menus, and finally skips a jev_check node Jev believes is done.

Jev still picks every action from the candidates; code only decides which candidates exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from bench.jev import HEAL_ITEMS, Obs, Option

# Giovanni's line after losing on Silph Co. 11F (the dialogue box can break it across lines)
STORY_RE = {"silph": re.compile(r"ruined\s+our\s+plans\s+for\s+SILPH", re.I),
            "snorlax": re.compile(r"SNORLAX\s+woke\s+up", re.I)}

FIELD_MOVES = {"Cut": "HM01", "Fly": "HM02", "Surf": "HM03", "Strength": "HM04", "Flash": "HM05"}
E4_ORDER = ["Lorelei", "Bruno", "Agatha", "Lance", "Champion"]
E4_ROOM_OF = {"Lorelei": "Lorelei's Room", "Bruno": "Bruno's Room", "Agatha": "Agatha's Room", "Lance": "Lance's Room",
              "Champion": "Champion's Room"}
E4_ROOMS = set(E4_ROOM_OF.values())
# gym/E4 level targets for the best party member (code-side numbers)
LEVEL_TARGET = {0: 12, 1: 21, 2: 24, 3: 29, 4: 38, 5: 40, 6: 44, 7: 47, 8: 55}
POKE_CENTERS = {"Viridian City": "Viridian Poké Center", "Pewter City": "Pewter Poké Center",
                "Cerulean City": "Cerulean Poké Center", "Route 4": "Mt. Moon Poké Center",
                "Vermilion City": "Vermilion Poké Center", "Lavender Town": "Lavender Poké Center",
                "Celadon City": "Celadon Poké Center", "Fuchsia City": "Fuchsia Poké Center",
                "Saffron City": "Saffron Poké Center", "Cinnabar Island": "Cinnabar Poké Center",
                "Route 10": "Rock Tunnel Poké Center", "Indigo Plateau Lobby": "Indigo Plateau Lobby"}
# Lt. Surge's door: two switches hidden in the 5x3 grid of trash cans; the second is next to the first (pokered
# GymTrashScript). A wrong second can resets both locks (and moves the first switch).
TRASH_CANS = [(x, y) for y in (7, 9, 11) for x in (1, 3, 5, 7, 9)]
# the bag holds 20 kinds; a full bag picks nothing up, not even the Lift Key (full run 55 lost ~2,100 steps to it).
# Tossed first: TMs (solo never teaches them), then items it never uses.
# moves that do no damage: their PP does not count as fighting strength (full run 58 blacked out on Route 10 with
# only Leer left: Struggle against a Pidgey)
STATUS_MOVES = {"Growl", "Leer", "Tail Whip", "Sand-Attack", "SmokeScreen", "String Shot", "Harden", "Defense Curl",
                "Withdraw", "Sing", "Supersonic", "PoisonPowder", "Sleep Powder", "Stun Spore", "Thunder Wave",
                "Hypnosis", "Confuse Ray", "Disable", "Agility", "Focus Energy", "Screech", "Growth", "Swords Dance",
                "Rest", "Reflect", "Light Screen", "Recover", "Softboiled", "Teleport", "Whirlwind", "Roar",
                "Leech Seed", "Toxic", "Double Team", "Minimize", "Barrier", "Amnesia", "Haze", "Mist", "Substitute",
                "Transform", "Splash", "Kinesis", "Flash", "Glare", "Lovely Kiss", "Spore", "Poison Gas", "Meditate",
                "Sharpen", "Acid Armor", "Conversion", "Mimic", "Metronome", "Mirror Move"}
LOW_PP = 10
BAG_SLOTS = 20
JUNK = ("Moon Stone", "Fire Stone", "Water Stone", "Thunder Stone", "Leaf Stone", "Dome Fossil", "Helix Fossil",
        "Old Amber", "Nugget", "Poké Doll", "Antidote", "Burn Heal", "Ice Heal", "Awakening", "Paralyze Heal")
TOSS_RETRY_STEPS = 50                                # a toss whose menu failed waits this long
NURSE_SPOT = (3, 3)                                  # where the player talks to a Poké Center nurse (facing up)
NURSE_SPOTS = {"Indigo Plateau Lobby": (7, 7)}       # elsewhere: the Lobby's nurse stands at (7,5) (ROM object list)
GYM_NODES = ("brock", "misty", "surge", "erika", "koga", "sabrina", "blaine", "giovanni")


@dataclass
class Facts:
    badges: int = 0
    items: set = field(default_factory=set)
    ever_items: set = field(default_factory=set)
    moves: set = field(default_factory=set)
    visited: set = field(default_factory=set)
    milestones: list = field(default_factory=list)
    levels: list = field(default_factory=list)
    hp_ratio: float = 1.0
    carry_ratio: float = 1.0                         # HP share of the strongest Pokémon (the one carrying the run)
    carry_pp: Optional[int] = None                   # PP left on its damaging moves (None: moves unknown)
    attack_pp: Optional[int] = None      # PP left on damaging moves of the Pokémon that can still fight (None: unknown)
    manual_done: set = field(default_factory=set)
    explored: int = 0                    # learned atlas: warps and edges taken so far (exploring counts as progress)
    came_from: str = ""                  # the map before the current one
    elevator: str = ""                   # the floor last chosen on an elevator panel (until the elevator is left)
    events: set = field(default_factory=set)   # story events code saw happen (e.g. "fuji": warped home from Tower 7F)
    teachable: set = field(default_factory=set)  # HMs in the bag that a party member has not refused yet

    def has(self, item: str) -> bool:
        """Ever held (key items can be handed over later: Tea, Gold Teeth, the parcel)."""
        return item in self.ever_items or item in self.items

    def reached(self, m: str) -> bool:
        return m in self.visited or any(x == f"reached: {m}" for x in self.milestones)

    def milestone(self, prefix: str) -> bool:
        return any(x.startswith(prefix) for x in self.milestones)


@dataclass
class Node:
    id: str
    objective: str
    targets: tuple
    done: Optional[Callable[[Facts], bool]]          # None = only Jev can tell (jev_check)
    jev_check: str = ""                              # Noul question used when done is None (or as a backup)
    stages: tuple = ()                               # ((condition(facts, obs), targets), ...): later steps of the node


def _badge(n: int) -> Callable[[Facts], bool]:
    def done(f: Facts) -> bool:
        return f.badges >= n
    done.anchor = True                                 # a badge count implies everything before it is done
    return done


GRAPH: list[Node] = [
    Node("intro", "Start a new game: get through the title screen and Professor Oak's introduction.", (),
         lambda f: f.milestone("game started")),
    Node("starter", "Leave the house, walk north out of Pallet Town; Oak takes you to his lab: choose a starter Pokémon (talk to one of the Poké Balls on the table, answer YES).",
         ("Pallet Town", "Route 1", "Oak's Lab"), lambda f: f.milestone("starter:")),
    Node("viridian", "Leave Oak's lab and go north along Route 1 to Viridian City.", ("Route 1", "Viridian City"),
         lambda f: f.reached("Viridian City")),
    Node("parcel", "Talk to the clerk in the Viridian Mart to receive Oak's Parcel.", ("Viridian Mart",),
         lambda f: "Oak's Parcel" in f.ever_items),
    Node("deliver", "Bring Oak's Parcel back to Professor Oak in his lab in Pallet Town and talk to him.",
         ("Pallet Town", "Oak's Lab"), lambda f: "Oak's Parcel" in f.ever_items and "Oak's Parcel" not in f.items),
    Node("forest", "Go north from Viridian City along Route 2 into Viridian Forest.", ("Viridian City", "Route 2", "Viridian Forest"),
         lambda f: f.reached("Viridian Forest")),
    Node("pewter", "Find the way through Viridian Forest to Pewter City.", ("Route 2", "Pewter City"), lambda f: f.reached("Pewter City")),
    Node("brock", "Beat Brock in the Pewter Gym.", ("Pewter Gym",), _badge(1)),
    Node("mtmoon", "Go east along Route 3 to Mt. Moon (the 'follow the map route' option knows the way).",
         ("Route 3", "Route 4", "Mt. Moon 1F"), lambda f: f.reached("Mt. Moon 1F")),
    Node("cerulean", "Get through Mt. Moon to Cerulean City: on every floor take the 'follow the map route' option (it knows "
                     "which ladder leads on); beat trainers who block the way.",
         ("Mt. Moon B1F", "Mt. Moon B2F", "Route 4", "Cerulean City"), lambda f: f.reached("Cerulean City")),
    Node("misty", "Beat Misty in the Cerulean Gym.", ("Cerulean Gym",), _badge(2)),
    Node("ticket", "Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket: "
                   "talk to Bill (he looks like a Pokémon), then use the computer at the right end of the room (stand below it, "
                   "face up, talk), then talk to Bill again when he comes out.",
         ("Route 24", "Route 25", "Bill's House"), lambda f: f.has("S.S. Ticket") or f.reached("S.S. Anne 1F")),
    Node("vermilion", "Go south through Route 5, the Underground Path and Route 6 to Vermilion City.",
         ("Route 5", "Route 6", "Vermilion City"), lambda f: f.reached("Vermilion City")),
    Node("cut", "Board the S.S. Anne in Vermilion harbor and talk to the captain on the top deck to get HM01 (Cut).",
         ("Vermilion Dock", "S.S. Anne 1F", "S.S. Anne 2F", "S.S. Anne Captain's Room"), lambda f: f.has("HM01")),
    Node("surge", "Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.", ("Vermilion Gym",), _badge(3)),
    # (B1F is part of the way: full run 78 explored it as a side map, left it by "go to Route 10 (unexplored exits)"
    # and went round by Vermilion to Route 12's Snorlax, ~2,300 steps)
    Node("lavender", "Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel "
                     "(its ladders lead between 1F and B1F several times before the exit south).",
         ("Route 9", "Route 10", "Rock Tunnel 1F", "Rock Tunnel B1F", "Lavender Town"), lambda f: f.reached("Lavender Town")),
    Node("celadon", "Go west from Lavender via Route 8 and the Underground Path to Route 7 and Celadon City.",
         ("Route 8", "Route 7", "Celadon City"), lambda f: f.reached("Celadon City")),
    Node("erika", "Beat Erika in the Celadon Gym (cut the tree in front of it).", ("Celadon Gym",), _badge(4)),
    Node("scope", "Find the Rocket Hideout under the Celadon Game Corner (a switch behind a poster opens the stairs), "
                  "go down to B4F (a Rocket there drops the Lift Key for the elevator), beat Giovanni and take the Silph Scope. "
                  "Giovanni's side of B4F is reached only by the elevator: with the Lift Key, ride the Rocket Hideout "
                  "Elevator, examine the panel on its wall, choose B4F and walk out.",
         ("Game Corner", "Rocket Hideout B1F", "Rocket Hideout B2F", "Rocket Hideout B3F", "Rocket Hideout B4F"),
         lambda f: f.has("Silph Scope"),
         # full run 49: the Lift Key in hand on the stairs side of B4F, the objective's last map, and nothing to route to
         stages=((lambda f, o: f.has("Lift Key") and f.elevator != "B4F" and not (
             o.map == "Rocket Hideout B4F" and f.came_from == "Rocket Hideout Elevator"),
                  ("Rocket Hideout B4F", "Rocket Hideout Elevator")),)),            # the route ends at the elevator
    Node("flute", "Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.",
         ("Lavender Town",) + tuple(f"Pokémon Tower {n}F" for n in range(1, 8)), lambda f: f.has("Poké Flute"),
         # he takes you home after the rescue; the flute is given there (full run 57 walked out and climbed the Tower
         # again for ~6,500 steps)
         # (only after the rescue: full run 74 walked into the empty house first, staged there, and its people's
         # answers from then hid Mr. Fuji after the rescue, ~2,000 steps in and out of the house)
         stages=((lambda f, o: "fuji" in f.events, ("Lavender Town", "Mr. Fuji's House")),)),
    Node("fuchsia", "Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.",
         ("Route 12", "Route 13", "Fuchsia City"), lambda f: f.reached("Fuchsia City"),
         # with the flute, Route 12 (the Snorlax's map) is the place until it woke: the furthest-known-map route wants
         # something left to explore past it, and the Snorlax walls that off (full run 77: ~1,100 steps of blind walks
         # around Celadon and Route 8 with the flute in the bag)
         stages=((lambda f, o: f.has("Poké Flute") and "snorlax" not in f.events, ("Lavender Town", "Route 12")),)),
    Node("koga", "Beat Koga in the Fuchsia Gym.", ("Fuchsia Gym",), _badge(5)),
    Node("surf", "Enter the Safari Zone and find the Secret House in its west area to get HM03 (Surf).",
         ("Safari Zone Gate", "Safari Zone Center", "Safari Zone West", "Safari Zone Secret House"), lambda f: f.has("HM03")),
    Node("strength", "Find the Safari Zone's Gold Teeth and give them to the Warden in Fuchsia for HM04 (Strength).",
         ("Safari Zone Gate", "Safari Zone Center", "Safari Zone West"), lambda f: f.has("HM04"),
         stages=((lambda f, o: f.has("Gold Teeth"), ("Fuchsia City", "Warden's House")),)),
    # Red/Blue have no Tea (that is FireRed): the thirsty Saffron gate guards take any drink
    Node("drink", "Buy a drink (Fresh Water, Soda Pop or Lemonade) from a vending machine on the Celadon Mart roof, "
                  "then walk into a Saffron gate: the thirsty guard takes it and lets you through.",
         ("Celadon City", "Celadon Mart 1F", "Celadon Mart Roof"),
         lambda f: any(f.has(d) for d in ("Fresh Water", "Soda Pop", "Lemonade")) or f.reached("Saffron City")),
    # the Card Key (5F) opens the locked doors (L); Giovanni's room on 11F is reached only by the warp pads (3F -> 7F
    # -> 11F), the stairs and the elevator open onto a corridor walled off from it (SoloDirector.entry_rule)
    Node("silph", "Enter Saffron City and clear Silph Co.: find the Card Key on 5F, open the locked doors with it "
                  "(face one and talk), and beat Giovanni on 11F (his room is reached by the warp pads, not the stairs).",
         # Giovanni's defeat line is the event code can see (full run 72 beat him at step 9,567; Jev's answer to the
         # question never reached three yes votes and the run paced 11F and 7F for ~2,100 steps)
         ("Saffron City",) + tuple(f"Silph Co. {n}F" for n in range(1, 12)),
         lambda f: "silph" in f.events or f.has("Master Ball"), "Has the player beaten Giovanni in Silph Co. (the Silph Co. president thanked the player)?",
         stages=((lambda f, o: not f.has("Card Key"), ("Saffron City",) + tuple(f"Silph Co. {n}F" for n in range(1, 6))),)),
    Node("sabrina", "Beat Sabrina in the Saffron Gym.", ("Saffron Gym",), _badge(6)),
    # full run 75: none of Charizard, Nidoran♂/♀, Paras and Doduo can learn Surf, and Cinnabar is across the sea;
    # the Silph Co. 7F worker gives a Lapras (it learns Surf), once the game has refused HM03 to every team member
    Node("lapras", "Nobody in your team can learn Surf (HM03). Go back to Silph Co. in Saffron City and talk to the Silph "
                   "worker on 7F who gives away a Lapras (keep a party slot free), then teach it HM03.",
         ("Saffron City",) + tuple(f"Silph Co. {n}F" for n in range(1, 8)),
         lambda f: "Surf" in f.moves or "HM03" in f.teachable or not f.has("HM03")),
    # Pallet Town is a target: Route 21 is unknown on a blank atlas, and the furthest known map of the objective is
    # where the route goes (full run 75: no target known, ~1,500 steps of blind walks in Celadon City)
    Node("cinnabar", "Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.",
         ("Pallet Town", "Route 21", "Cinnabar Island"), lambda f: f.reached("Cinnabar Island")),
    Node("key", "Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key (in the basement).",
         ("Pokémon Mansion 1F", "Pokémon Mansion 2F", "Pokémon Mansion 3F", "Pokémon Mansion B1F"),
         lambda f: f.has("Secret Key")),
    Node("blaine", "Beat Blaine in the Cinnabar Gym.", ("Cinnabar Gym",), _badge(7)),
    Node("giovanni", "Beat Giovanni in the Viridian Gym.", ("Viridian City", "Viridian Gym"), _badge(8)),
    Node("plateau", "Go west from Viridian City on Route 22 and north on Route 23 through Victory Road to Indigo Plateau.",
         ("Route 22", "Route 23", "Victory Road 1F", "Victory Road 2F", "Victory Road 3F", "Indigo Plateau Lobby"),
         lambda f: f.reached("Indigo Plateau Lobby")),   # (all its floors: a side map is left, as in run 78: Codex 5)
    Node("champion", "Beat the Elite Four and the Champion.",
         ("Indigo Plateau Lobby", "Lorelei's Room", "Bruno's Room", "Agatha's Room", "Lance's Room", "Champion's Room"),
         lambda f: f.milestone("champion defeated")),
]


def current_node(f: Facts) -> Node:
    # Only anchors skip ahead: the badge count, nodes confirmed done (manual_done, incl. a segment's --progress) and the
    # starter once a party exists. From there the first unfinished node wins, so visiting a later map early (Vermilion
    # through the Underground Path before Misty) does not skip Misty and the S.S. Ticket (Codex review).
    start = 0
    for i, n in enumerate(GRAPH):
        if n.id == "starter" and bool(f.levels) or getattr(n.done, "anchor", False) and n.done(f) or n.id in f.manual_done:
            start = i + 1
    for n in GRAPH[start:]:
        if n.id in f.manual_done:
            continue
        if n.done is None or not n.done(f):
            return n
    return GRAPH[-1]


STUCK_Q = "Do `recent_actions` show the player repeating actions that fail or change nothing, without progress toward `objective`?"


def _move_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


_STATUS_KEYS = {_move_key(m) for m in STATUS_MOVES}


def is_status_move(name: str) -> bool:
    """Case and punctuation do not matter: the screen says SMOKESCREEN / SAND-ATTACK, the table SmokeScreen."""
    return _move_key(name) in _STATUS_KEYS


def attack_pp(party: list[dict]) -> Optional[int]:
    """PP left on damaging moves of the party Pokémon that are not fainted; None when no moves are known."""
    moves = [m for p in party if p.get("hp", 0) > 0 for m in p.get("moves", [])]
    if not any(p.get("moves") for p in party):
        return None
    return sum(m.get("pp", 0) for m in moves if not is_status_move(m["name"]))


class SoloDirector:
    """Objective, extra candidates and Jev check questions for jev-solo. Pure code + Jev answers."""

    def __init__(self, state: dict):
        self.s = state                                   # the agent's persisted dict
        for k, v in {"ever_items": [], "manual_done": [], "last_progress_step": 0, "pos_repeat": 0, "last_pos": None,
                     "recovery": 0, "done_votes": {}, "progress_sig": ""}.items():
            self.s.setdefault(k, v)

    # ------------------------------------------------------------- facts
    def facts(self, o: Obs, party: list[dict], items: list[tuple[str, int]]) -> Facts:
        names = {n for n, _ in items}
        self.s["ever_items"] = sorted(set(self.s["ever_items"]) | names)
        moves = {m["name"] for p in party for m in p.get("moves", [])}
        hp = sum(p["hp"] for p in party), sum(p["max_hp"] for p in party)
        carry = max(party, key=lambda p: p["level"]) if party else None
        return Facts(badges=o.badges if o.map else self.s.get("badges", 0), items=names, ever_items=set(self.s["ever_items"]),
                     moves=moves, visited=set(self.s["visited"]), milestones=list(self.s["milestones"]),
                     levels=[p["level"] for p in party], hp_ratio=(hp[0] / hp[1]) if hp[1] else 1.0,
                     carry_ratio=(carry["hp"] / carry["max_hp"]) if carry and carry["max_hp"] else 1.0,
                     carry_pp=attack_pp([carry]) if carry and carry["hp"] > 0 else None,
                     attack_pp=attack_pp(party),
                     manual_done=set(self.s["manual_done"]), came_from=self.s.get("came_from", ""),
                     elevator=self.s.get("elevator", ""), events=set(self.s.get("events", [])),
                     teachable={hm for hm in FIELD_MOVES.values() if hm in names and any(
                         f"{hm}:{p['species']}" not in self.s.get("hm_no", []) for p in party)})

    # ------------------------------------------------------------- objective
    def objective(self, f: Facts, o: Obs) -> tuple[str, list[str], str]:
        """(objective text, walk targets, why) after the code rules that override the graph."""
        node = current_node(f)
        no_pp = f.attack_pp is not None and f.attack_pp < LOW_PP
        # the strongest Pokémon counts on its own: five healthy weak ones hid a fainted Charizard L70 (Codex review 4;
        # plateau-leg-6 blacked out on Victory Road 3F)
        # (and its attacking PP: run 75's Charizard had Slash 0, Ember 0, Strength 0 with plenty in reserve: Codex 5)
        weak_carry = len(f.levels) > 1 and (f.carry_ratio < 0.35 or f.carry_pp is not None and f.carry_pp < LOW_PP)
        league = o.map in E4_ROOMS                         # its doors lock behind you: items, not a Poké Center
        if node.id == "champion" and o.map == "Indigo Plateau Lobby" and self.league_next(f) == "Lorelei" \
                and f.levels and min(f.hp_ratio, f.carry_ratio) < 1:
            return ("Heal fully at the Indigo Plateau Poké Center before the Elite Four (talk to the nurse, answer YES): "
                    "there is no way back between their rooms.", ["Indigo Plateau Lobby"], "heal")
        if f.levels and not league and (f.hp_ratio < 0.35 or no_pp or weak_carry or
                         self.s.get("healing") and min(f.hp_ratio, f.carry_ratio) < 0.9):   # hysteresis: heal fully
            self.s["healing"] = True
            here = [POKE_CENTERS[o.map]] if o.map in POKE_CENTERS else []
            pcs = here + [POKE_CENTERS[m] for m in reversed(self.s["visited"]) if m in POKE_CENTERS and m != o.map]
            if pcs:
                weak = f"{round(100 * f.hp_ratio)}% HP" + (f", {f.attack_pp} PP left on attacking moves" if no_pp else "") + \
                    (f", your strongest Pokémon at {round(100 * f.carry_ratio)}%" if weak_carry else "")
                return (f"Your team is weak ({weak}): heal at a Poké Center (walk in, talk to the nurse, answer YES).",
                        pcs[:2], "heal")
        self.s["healing"] = False
        town = o.map.endswith(("City", "Town", "Island"))  # route Poké Centers (Mt. Moon's, Rock Tunnel's) are not homes
        pc = (POKE_CENTERS.get(o.map) if town else None) or \
            (o.map if o.map.endswith("Poké Center") and o.map not in ("Mt. Moon Poké Center", "Rock Tunnel Poké Center") else None)
        if pc and pc not in self.s.get("healed_at", []) + self.s.get("pc_unreachable", []) and f.levels \
                and pc != "Indigo Plateau Lobby":
            # the last Poké Center used is where a black-out sends you: use each new town's once
            return (f"Heal at the {pc} once (walk in, talk to the nurse, answer YES): after a lost battle you wake up "
                    f"at the last Poké Center you used.", [pc], "heal")
        target = min(100, LEVEL_TARGET.get(f.badges, 55) + self.s.get("level_bonus", {}).get(node.id, 0))   # (L100 is the top)
        if node.id in ("brock", "misty", "surge", "erika", "koga", "sabrina", "blaine", "giovanni", "champion") and f.levels \
                and max(f.levels) < target:
            return (f"Train before the next gym: walk through tall grass and win wild battles until your best Pokémon "
                    f"reaches level {target} (now {max(f.levels)}).", [], "train")
        if node.id == "starter":
            # Oak's scene starts when you try to leave Pallet Town north; walking into the lab first does nothing.
            # In the lab (after the scene) the starter balls are the choice: no route out.
            return node.objective, (["Oak's Lab"] if o.map == "Oak's Lab" else ["Pallet Town", "Route 1"]), node.id
        targets = list(node.targets)
        for cond, later in node.stages:
            if cond(f, o):
                targets = list(later)
        if node.id == "champion":
            # one room at a time: the next member not beaten in this attempt is the objective's own map, so its trainer
            # is talked to before the (locked) exit (plateau-leg-7 walked into Lorelei's closed exit ~15 times)
            nxt = self.league_next(f)
            targets = targets[:targets.index(E4_ROOM_OF[nxt]) + 1]
            return f"Beat the Elite Four and the Champion: next, {nxt} in {E4_ROOM_OF[nxt]} (talk to them).", targets, node.id
        return node.objective, targets, node.id

    def league_next(self, f: Facts) -> str:
        """The next Elite Four member (or the Champion) not beaten in this attempt: the agent keeps `league_beaten` and
        clears it on a black-out (a loss resets them all). Milestones keep each text only once, so a second win over
        Lorelei after a loss never showed there (Codex review 5)."""
        beaten = set(self.s.get("league_beaten", []))
        return next((n for n in E4_ORDER if n not in beaten), "Champion")

    def check_questions(self, f: Facts) -> dict[str, str]:
        node = current_node(f)
        qs = {"stuck": STUCK_Q}
        # only a node code cannot check asks Jev: votes on a badge, an item or a map reached could skip a step the
        # facts say is missing (Codex review; no run since 60 marked a node this way)
        if node.done is None and node.jev_check:
            qs["objective_done"] = node.jev_check
        return qs

    def absorb(self, f: Facts, nouls: dict[str, float]) -> Optional[str]:
        """Count Jev's 'done' votes; three >= 0.8 in a row mark a node done. Returns the node id if marked."""
        node = current_node(f)
        if "objective_done" not in nouls:
            return None
        votes = self.s["done_votes"]
        votes[node.id] = votes.get(node.id, 0) + 1 if nouls["objective_done"] >= 0.8 else 0
        if votes[node.id] >= 3:
            self.s["manual_done"] = sorted(set(self.s["manual_done"]) | {node.id})
            self.s["recovery"] = 0
            return node.id
        return None

    # ------------------------------------------------------------- progress / stuck
    def lost(self, f: Facts) -> None:
        """A black-out. In the gym the objective names (leader or its trainers): train harder before the next try."""
        node = current_node(f)
        # (the league too: league-leg lost to Lorelei with Charizard L72 and walked straight back; the table asks L55)
        seen = self.s.get("gym_map_seen", "")
        if (node.id in GYM_NODES and seen.endswith("Gym")) or (node.id == "champion" and seen in E4_ROOMS):
            bonus = self.s.setdefault("level_bonus", {})
            # at least three levels above the team that just lost (iteration 38: Charmeleon L25 lost to Misty, and the
            # table's 21 + 3 asked for no training at all)
            above = max(f.levels) + 3 - LEVEL_TARGET.get(f.badges, 55) if f.levels else 0
            bonus[node.id] = max(bonus.get(node.id, 0) + 3, above)
            self.s["gym_map_seen"] = ""                  # one black-out, one bonus

    def track(self, step: int, o: Obs, f: Facts) -> None:
        if o.map and o.map != self.s.get("prev_map"):
            self.s["came_from"] = self.s.get("prev_map", "")
            if not o.map.endswith("Elevator"):
                self.s["elevator"] = ""                  # the chosen floor counts until the elevator is left
            if o.map == "Mr. Fuji's House" and self.s["came_from"] == "Pokémon Tower 7F":
                self.s["events"] = sorted(set(self.s.get("events", [])) | {"fuji"})   # rescued: the warp home
                for key in ("said", "talk_noroute", "npcs"):
                    self.s.get(key, {}).pop(o.map, None)   # he sits at the table now: hear the house anew
                f.events.add("fuji")
            # the facts were read before this step's map change: on the arrival step they still named the map before
            # the last one (full run 68: every arrival on B4F from the elevator read "came from B4F", the stage routed
            # back into the elevator, ~1,400 steps in and out of it, and Giovanni's Silph Scope lay there ~1,150 of them)
            f.came_from, f.elevator = self.s["came_from"], self.s.get("elevator", "")
        if o.map:
            self.s["prev_map"] = o.map
        if o.map.endswith("Gym") or o.map in E4_ROOMS:
            self.s["gym_map_seen"] = o.map
        elif o.map:
            self.s["gym_map_seen"] = ""
        # story events are progress: a checkpoint follows each one, so a reload does not go back before an event the
        # agent keeps (Codex review: "silph" survived a reload to before Giovanni's defeat)
        sig = f"{len(f.visited)}|{len(f.milestones)}|{len(f.ever_items)}|{f.badges}|{sorted(f.moves)}|{sum(f.levels)}|" \
              f"{f.explored}|{sorted(f.events)}"
        if sig != self.s["progress_sig"]:
            self.s["progress_sig"] = sig
            self.s["last_progress_step"] = step
            self.s["recovery"] = 0
        pos = [o.map, *(o.pos or ())]
        self.s["pos_repeat"] = self.s["pos_repeat"] + 1 if pos == self.s["last_pos"] and o.mode == "overworld" else 0
        self.s["last_pos"] = pos
        idle = step - self.s["last_progress_step"]
        level = 0
        if idle >= 60 or self.s["pos_repeat"] >= 6:
            level = 1
        if idle >= 150 or self.s["pos_repeat"] >= 10:
            level = 2
        if idle >= 300:
            level = 3
        self.s["recovery"] = max(level, 0)

    def entry_rule(self, f: Facts) -> dict[str, str]:
        """Maps the route may enter only from one other map: Giovanni's room on Silph Co. 11F is reached by the warp
        pad from 7F; the stairs and the elevator open onto a corridor walled off from it (full run 61 paced that
        corridor ~2,800 steps)."""
        return {"Silph Co. 11F": "Silph Co. 7F"} if current_node(f).id == "silph" and f.has("Card Key") else {}

    def bag_option(self, items: list[tuple[str, int]]) -> Optional[Option]:
        """With 19 of the 20 bag slots taken, code tosses a stack it has no use for, so the next pickup always fits (full
        run 59 tossed only at 20: the slot it freed was refilled before Jev came back to the Gold Teeth). A toss the
        game refuses is not retried."""
        if len(items) < BAG_SLOTS - 1 or self.s.get("step", 0) - self.s.get("toss_failed_step", -10**9) < TOSS_RETRY_STEPS:
            return None
        refused = set(self.s.get("no_toss", []))
        names = [n for n, _ in items if n not in refused]
        junk = [n for n in names if n.startswith("TM")] + [n for j in JUNK for n in names if n == j]
        if not junk:
            return None
        return Option(f"toss {junk[0]} (the bag is full)", "manage", {"action": "toss", "target": junk[0]},
                      "a full bag cannot pick up anything, not even key items")

    def flute_option(self, items: list[tuple[str, int]]) -> Optional[Option]:
        """Facing a sleeping Snorlax (the last reply said so) with the Poké Flute: code plays it (full run 56 talked to
        the Route 12 Snorlax ~700 times; talking never wakes it)."""
        last = (self.s.get("history") or [""])[-1]
        if "sleeping POKéMON" in last and any(n == "Poké Flute" for n, _ in items):
            return Option("play the Poké Flute to wake the sleeping Pokémon", "manage",
                          {"action": "use", "target": "Poké Flute"}, "only the Poké Flute wakes Snorlax")
        return None

    def forced_recovery(self, step: int) -> Optional[Option]:
        """Code-only recovery when the player has not moved for a long time (no Jev question)."""
        r = self.s["pos_repeat"]
        if r and r % 15 == 0 and r < 45:
            return Option("recovery: open and close the START menu", "press", {"buttons": "START W10 B W10 B B"})
        if r >= 45 and self.s.get("checkpoint_step") is not None and step - self.s.get("loaded_at", -999) > 100:
            self.s["loaded_at"] = step
            self.s["pos_repeat"] = 0
            return Option("recovery: reload the last progress checkpoint", "load_state", {"slot": "jev-progress"})
        return None

    def want_checkpoint(self, step: int) -> bool:
        """Save a named checkpoint after progress (at most every 25 steps). Progress made too soon after the last one, or
        off the overworld (in a dialogue), stays pending until the next allowed step (Codex review 2: an event right
        after a checkpoint never got one, so a reload could go back to before it)."""
        last = self.s.get("checkpoint_step")
        last = -999 if last is None else last
        if self.s["last_progress_step"] > last - (last == step) and step - last >= 25:
            self.s["checkpoint_step"] = step
            return True
        return False

    # ------------------------------------------------------------- Vermilion Gym trash cans
    def trash_options(self, o: Obs) -> list[Option]:
        """Search the cans from below (facing up): untried ones while no switch is found, then the found switch's
        neighbours. Code keeps the bookkeeping; Jev still picks which can."""
        t = self.s.setdefault("trash", {"first": None, "tried": [], "open": False})
        if t["open"]:
            return []
        if t["first"]:
            fx, fy = t["first"]
            cans = [c for c in TRASH_CANS if abs(c[0] - fx) + abs(c[1] - fy) == 2 and list(c) not in t["tried"]]
            why = f"the first switch was in the can at ({fx},{fy}); the second is in a can next to it"
        else:
            cans = [c for c in TRASH_CANS if list(c) not in t["tried"]] or TRASH_CANS
            why = "Lt. Surge hid the door switches inside trash cans: search them"
        px, py = o.pos
        people = {tuple(n) for n in o.npcs}
        opts = []
        for x, y in sorted(cans, key=lambda c: abs(c[0] - px) + abs(c[1] + 1 - py))[:6]:
            # from below if free, else another side: trainers stand below some cans (full run 45 tried two ~134 times)
            side = next(((sx, sy, d) for sx, sy, d in ((x, y + 1, "up"), (x, y - 1, "down"), (x - 1, y, "right"),
                                                         (x + 1, y, "left")) if (sx, sy) not in people and sx >= 0), None)
            if side is None:
                continue
            sx, sy, d = side
            here = (px, py) == (sx, sy)
            face = {"path": f"{d} 1", "on_battle": "stop"}
            opts.append(Option(f"search the trash can at ({x},{y})", "walk",
                               face if here else {"path": f"to {sx},{sy}", "on_battle": "stop"}, why,
                               then=([] if here else [("walk", face)]) + [("talk", {})]))
        return opts

    def heard(self, reply: str) -> None:
        """Story events the game says in words (no verified RAM flag in this repo)."""
        for ev, rx in STORY_RE.items():
            if rx.search(reply):
                self.s["events"] = sorted(set(self.s.get("events", [])) | {ev})

    def trash_result(self, label: str, reply: str, left: bool = False) -> None:
        t = self.s.setdefault("trash", {"first": None, "tried": [], "open": False})
        if left and not t["open"]:
            t["first"], t["tried"] = None, []       # leaving the gym resets the first lock
        m = re.match(r"search the trash can at \((\d+),(\d+)\)", label)
        if not m:
            return
        can, low = [int(m[1]), int(m[2])], reply.lower()
        if "motorized door" in low or "2nd electric lock" in low:
            t["open"] = True
        elif "reset" in low:
            t["first"], t["tried"] = None, []       # the first switch moved: every can is a candidate again
        elif "switch" in low:
            t["first"], t["tried"] = can, [can]
        elif "trash" in low:
            t["tried"].append(can)

    # ------------------------------------------------------------- extra candidates
    def extra_options(self, o: Obs, f: Facts, party: list[dict], exits: list[str], conns: list[tuple[str, str]],
                      why: str) -> list[Option]:
        opts: list[Option] = []
        visited = set(self.s["visited"])
        # teach an HM in the bag that nobody knows yet: to the first Pokémon the game has not refused ("not
        # compatible", remembered by the agent); with 4 moves known the server forgets the one with the least power
        for move, hm in FIELD_MOVES.items():
            if hm in f.items and move not in f.moves and move in ("Cut", "Surf", "Strength", "Flash"):
                mon = next((p["species"] for p in party if f"{hm}:{p['species']}" not in self.s.get("hm_no", [])), None)
                if mon:
                    opts.append(Option(f"teach {hm} ({move}) to {mon}", "manage",
                                       {"action": "use", "target": hm, "target2": f"{mon}: weakest"},
                                       f"{move} is needed to pass obstacles"))
        if why == "heal" and (o.map.endswith("Poké Center") or o.map in NURSE_SPOTS) and o.pos:
            # code knows where the nurse is: every Gen 1 Poké Center has her at (3,1) behind the counter, talked to
            # from (3,3) facing up; the generic talk-to options cannot reach her across the counter
            spot = NURSE_SPOTS.get(o.map, NURSE_SPOT)
            at = tuple(o.pos) == spot
            face = ("walk", {"path": "up 1", "on_battle": "stop"})
            first = face[1] if at else {"path": f"to {spot[0]},{spot[1]}", "on_battle": "stop"}
            opts.append(Option("talk to the nurse across the counter", "walk", first,
                               "the Poké Center nurse heals the whole team: this is what the objective asks for",
                               then=([] if at else [face]) + [("talk", {})]))
        if o.map == "Vermilion Gym" and f.badges < 3 and o.pos:
            opts += self.trash_options(o)
        hint = (o.hint or "").lower()
        for move, word in (("Cut", "tree"), ("Surf", "water"), ("Strength", "boulder")):
            if move in f.moves and word in hint:
                opts.append(Option(f"use {move} on the {word} in front", "manage", {"action": "field", "target": move},
                                   f"clear the {word} with {move}"))
        if why == "train":
            for d in ("up", "down", "left", "right"):
                opts.append(Option(f"walk {d} 6 tiles through grass", "walk", {"path": f"{d} 6", "on_battle": "stop"},
                                   "look for wild Pokémon to fight"))
        if self.s["recovery"] >= 1:
            for e in exits:
                if e not in visited and e != "outside":
                    opts.append(Option(f"explore unvisited {e}", "walk", {"path": f"to {e}", "on_battle": "stop"},
                                       "a place not visited yet"))
            for side, dest in conns:
                if dest not in visited:
                    opts.append(Option(f"explore unvisited {dest} ({side} edge)", "walk", {"path": f"to {side} edge", "on_battle": "stop"},
                                       "a map not visited yet"))
        if self.s["recovery"] >= 2:
            for d in ("up", "down", "left", "right"):
                opts.append(Option(f"walk {d} 10 tiles", "walk", {"path": f"{d} 10", "on_battle": "stop"}, "explore further"))
            opts.append(Option("press B to close menus", "press", {"buttons": "B B B"}, "clear a stuck menu or text box"))
            opts.append(Option("open and close the START menu", "press", {"buttons": "START W10 B W10 B"},
                               "resets a player who cannot move after a scripted scene"))
        if (f.hp_ratio < 0.5 or f.carry_ratio < 0.5) and party and o.mode == "overworld":
            heal = next((h for h in HEAL_ITEMS if h in f.items), None)
            # the strongest Pokémon first when it is hurt, never a fainted one (a potion cannot revive: Codex review 4)
            alive = [p for p in party if p["hp"] > 0]
            carry = max(party, key=lambda p: p["level"])
            weakest = carry if 0 < carry["hp"] < carry["max_hp"] / 2 else \
                min(alive, key=lambda p: p["hp"] / max(p["max_hp"], 1)) if alive else carry
            if heal and 0 < weakest["hp"] < weakest["max_hp"]:
                opts.append(Option(f"use a {heal} on {weakest['species']}", "manage",
                                   {"action": "use", "target": heal, "target2": weakest["species"]}, "heal a hurt Pokémon"))
        return opts
