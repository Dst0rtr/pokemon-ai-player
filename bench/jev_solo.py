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

from dataclasses import dataclass, field
from typing import Callable, Optional

from bench.jev import HEAL_ITEMS, Obs, Option

FIELD_MOVES = {"Cut": "HM01", "Fly": "HM02", "Surf": "HM03", "Strength": "HM04", "Flash": "HM05"}
# gym/E4 level targets for the best party member (code-side numbers)
LEVEL_TARGET = {0: 12, 1: 21, 2: 24, 3: 29, 4: 38, 5: 40, 6: 44, 7: 47, 8: 55}
POKE_CENTERS = {"Viridian City": "Viridian Poké Center", "Pewter City": "Pewter Poké Center",
                "Cerulean City": "Cerulean Poké Center", "Route 4": "Mt. Moon Poké Center",
                "Vermilion City": "Vermilion Poké Center", "Lavender Town": "Lavender Poké Center",
                "Celadon City": "Celadon Poké Center", "Fuchsia City": "Fuchsia Poké Center",
                "Saffron City": "Saffron Poké Center", "Cinnabar Island": "Cinnabar Poké Center",
                "Route 10": "Rock Tunnel Poké Center", "Indigo Plateau Lobby": "Indigo Plateau Lobby"}
NURSE_SPOT = (3, 3)                                  # where the player talks to a Poké Center nurse (facing up)
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
    manual_done: set = field(default_factory=set)

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


def _badge(n: int) -> Callable[[Facts], bool]:
    return lambda f: f.badges >= n


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
    Node("ticket", "Go north over Nugget Bridge (Route 24) and east on Route 25 to Bill's house; help Bill to get the S.S. Ticket.",
         ("Route 24", "Route 25", "Bill's House"), lambda f: f.has("S.S. Ticket") or f.reached("S.S. Anne 1F")),
    Node("vermilion", "Go south through Route 5, the Underground Path and Route 6 to Vermilion City.",
         ("Route 5", "Route 6", "Vermilion City"), lambda f: f.reached("Vermilion City")),
    Node("cut", "Board the S.S. Anne in Vermilion harbor and talk to the captain on the top deck to get HM01 (Cut).",
         ("Vermilion Dock", "S.S. Anne 1F", "S.S. Anne 2F"), lambda f: f.has("HM01")),
    Node("surge", "Cut the small tree in front of the Vermilion Gym and beat Lt. Surge.", ("Vermilion Gym",), _badge(3)),
    Node("lavender", "Go to Lavender Town: east of Cerulean via Route 9 and Route 10, through Rock Tunnel.",
         ("Route 9", "Route 10", "Rock Tunnel 1F", "Lavender Town"), lambda f: f.reached("Lavender Town")),
    Node("celadon", "Go west from Lavender via Route 8 and the Underground Path to Route 7 and Celadon City.",
         ("Route 8", "Route 7", "Celadon City"), lambda f: f.reached("Celadon City")),
    Node("erika", "Beat Erika in the Celadon Gym (cut the tree in front of it).", ("Celadon Gym",), _badge(4)),
    Node("scope", "Find the Rocket Hideout under the Celadon Game Corner, beat Giovanni and take the Silph Scope.",
         ("Game Corner", "Rocket Hideout B1F"), lambda f: f.has("Silph Scope")),
    Node("flute", "Climb Pokémon Tower in Lavender with the Silph Scope, rescue Mr. Fuji and get the Poké Flute.",
         ("Lavender Town", "Pokémon Tower 1F", "Mr. Fuji's House"), lambda f: f.has("Poké Flute")),
    Node("fuchsia", "Wake the sleeping Snorlax with the Poké Flute and travel south to Fuchsia City.",
         ("Route 12", "Route 13", "Fuchsia City"), lambda f: f.reached("Fuchsia City")),
    Node("koga", "Beat Koga in the Fuchsia Gym.", ("Fuchsia Gym",), _badge(5)),
    Node("surf", "Enter the Safari Zone and find the Secret House to get HM03 (Surf).", ("Safari Zone Gate", "Safari Zone Center"),
         lambda f: f.has("HM03")),
    Node("strength", "Find the Safari Zone's Gold Teeth and give them to the Warden in Fuchsia for HM04 (Strength).",
         ("Safari Zone Center", "Warden's House"), lambda f: f.has("HM04")),
    Node("tea", "Get the Tea from the old woman in Celadon Mansion so the Saffron gate guards let you in.",
         ("Celadon City", "Celadon Mansion 1F"), lambda f: f.has("Tea") or f.reached("Saffron City")),
    Node("silph", "Enter Saffron City and clear Silph Co. (find the Card Key, beat Giovanni).",
         ("Saffron City", "Silph Co. 1F"), None, "Has the player beaten Giovanni in Silph Co. (the Silph Co. president thanked the player)?"),
    Node("sabrina", "Beat Sabrina in the Saffron Gym.", ("Saffron Gym",), _badge(6)),
    Node("cinnabar", "Surf south from Pallet Town (or through the Seafoam Islands) to Cinnabar Island.",
         ("Route 21", "Cinnabar Island"), lambda f: f.reached("Cinnabar Island")),
    Node("key", "Explore the Pokémon Mansion on Cinnabar Island to find the Secret Key.", ("Pokémon Mansion 1F",),
         lambda f: f.has("Secret Key")),
    Node("blaine", "Beat Blaine in the Cinnabar Gym.", ("Cinnabar Gym",), _badge(7)),
    Node("giovanni", "Beat Giovanni in the Viridian Gym.", ("Viridian City", "Viridian Gym"), _badge(8)),
    Node("plateau", "Go west from Viridian City on Route 22 and north on Route 23 through Victory Road to Indigo Plateau.",
         ("Route 22", "Route 23", "Victory Road 1F", "Indigo Plateau Lobby"), lambda f: f.reached("Indigo Plateau Lobby")),
    Node("champion", "Beat the Elite Four and the Champion.", ("Indigo Plateau Lobby", "Lorelei's Room"),
         lambda f: f.milestone("champion defeated")),
]


def current_node(f: Facts) -> Node:
    # A run that starts from a segment save state has no milestone history: everything before the furthest node
    # whose code-side test passes (badges, bag, maps incl. the current one; the starter once a party exists) is done.
    start = 0
    for i, n in enumerate(GRAPH):
        if n.id == "starter" and bool(f.levels) or n.done is not None and n.done(f) or n.id in f.manual_done:
            start = i + 1
    for n in GRAPH[start:]:
        if n.id in f.manual_done:
            continue
        if n.done is None or not n.done(f):
            return n
    return GRAPH[-1]


STUCK_Q = "Do `recent_actions` show the player repeating actions that fail or change nothing, without progress toward `objective`?"


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
        return Facts(badges=o.badges if o.map else self.s.get("badges", 0), items=names, ever_items=set(self.s["ever_items"]),
                     moves=moves, visited=set(self.s["visited"]), milestones=list(self.s["milestones"]),
                     levels=[p["level"] for p in party], hp_ratio=(hp[0] / hp[1]) if hp[1] else 1.0,
                     manual_done=set(self.s["manual_done"]))

    # ------------------------------------------------------------- objective
    def objective(self, f: Facts, o: Obs) -> tuple[str, list[str], str]:
        """(objective text, walk targets, why) after the code rules that override the graph."""
        node = current_node(f)
        if f.levels and (f.hp_ratio < 0.35 or self.s.get("healing") and f.hp_ratio < 0.9):   # hysteresis: heal fully
            self.s["healing"] = True
            here = [POKE_CENTERS[o.map]] if o.map in POKE_CENTERS else []
            pcs = here + [POKE_CENTERS[m] for m in reversed(self.s["visited"]) if m in POKE_CENTERS and m != o.map]
            if pcs:
                return (f"Your team is weak ({round(100 * f.hp_ratio)}% HP): heal at a Poké Center (walk in, talk to the nurse, answer YES).",
                        pcs[:2], "heal")
        self.s["healing"] = False
        target = LEVEL_TARGET.get(f.badges, 55) + self.s.get("level_bonus", {}).get(node.id, 0)
        if node.id in ("brock", "misty", "surge", "erika", "koga", "sabrina", "blaine", "giovanni", "champion") and f.levels \
                and max(f.levels) < target:
            return (f"Train before the next gym: walk through tall grass and win wild battles until your best Pokémon "
                    f"reaches level {target} (now {max(f.levels)}).", [], "train")
        return node.objective, list(node.targets), node.id

    def check_questions(self, f: Facts) -> dict[str, str]:
        node = current_node(f)
        qs = {"stuck": STUCK_Q}
        if node.done is None and node.jev_check:
            qs["objective_done"] = node.jev_check
        elif self.s["recovery"] >= 3:
            qs["objective_done"] = f"Is this objective already complete: {node.objective}"
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
        if node.id in GYM_NODES and self.s.get("gym_map_seen", "").endswith("Gym"):
            bonus = self.s.setdefault("level_bonus", {})
            bonus[node.id] = bonus.get(node.id, 0) + 3
            self.s["gym_map_seen"] = ""                  # one black-out, one bonus

    def track(self, step: int, o: Obs, f: Facts) -> None:
        if o.map:
            self.s["prev_map"] = o.map
        if any("blacked out" in e for e in o.events):
            self.lost(f)
        if o.map.endswith("Gym"):
            self.s["gym_map_seen"] = o.map
        elif o.map:
            self.s["gym_map_seen"] = ""
        sig = f"{len(f.visited)}|{len(f.milestones)}|{len(f.ever_items)}|{f.badges}|{sorted(f.moves)}|{sum(f.levels)}"
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
        """Save a named checkpoint after progress (at most every 25 steps)."""
        if self.s["last_progress_step"] == step and step - (self.s.get("checkpoint_step") or -999) >= 25:
            self.s["checkpoint_step"] = step
            return True
        return False

    # ------------------------------------------------------------- extra candidates
    def extra_options(self, o: Obs, f: Facts, party: list[dict], exits: list[str], conns: list[tuple[str, str]],
                      why: str) -> list[Option]:
        opts: list[Option] = []
        visited = set(self.s["visited"])
        # teach an HM in the bag that nobody knows yet (to the first Pokémon; the server picks the move to forget)
        for move, hm in FIELD_MOVES.items():
            if hm in f.items and move not in f.moves and party and move in ("Cut", "Surf", "Strength", "Flash"):
                opts.append(Option(f"teach {hm} ({move}) to {party[0]['species']}", "manage",
                                   {"action": "use", "target": hm, "target2": party[0]["species"]},
                                   f"{move} is needed to pass obstacles"))
        if why == "heal" and o.map.endswith("Poké Center") and o.pos:
            # code knows where the nurse is: every Gen 1 Poké Center has her at (3,1) behind the counter, talked to
            # from (3,3) facing up; the generic talk-to options cannot reach her across the counter
            at = tuple(o.pos) == NURSE_SPOT
            face = ("walk", {"path": "up 1", "on_battle": "stop"})
            first = face[1] if at else {"path": f"to {NURSE_SPOT[0]},{NURSE_SPOT[1]}", "on_battle": "stop"}
            opts.append(Option("talk to the nurse across the counter", "walk", first,
                               "the Poké Center nurse heals the whole team: this is what the objective asks for",
                               then=([] if at else [face]) + [("talk", {})]))
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
        if f.hp_ratio < 0.5 and party and o.mode == "overworld":
            heal = next((h for h in HEAL_ITEMS if h in f.items), None)
            weakest = min(party, key=lambda p: p["hp"] / max(p["max_hp"], 1))
            if heal and weakest["hp"] < weakest["max_hp"]:
                opts.append(Option(f"use a {heal} on {weakest['species']}", "manage",
                                   {"action": "use", "target": heal, "target2": weakest["species"]}, "heal a hurt Pokémon"))
        return opts
