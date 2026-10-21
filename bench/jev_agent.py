#!/usr/bin/env python3
"""
The Jev player: an MCP client of server.py that asks Jev (bench/jev.py) to pick every action.

run.py launches it like an agent CLI, one process per chunk, and reads its stdout: one JSON event per
line (`start`, `tool_call`, `objective`, `usage`, `error`, `result`; parsed by bench/stream.py). Its own
progress (objective, facts, recent actions) lives in <run-dir>/jev_agent.json so the next chunk continues
where this one stopped; the game itself resumes from the server's autosave.

    python bench/jev_agent.py --run-dir bench/runs/<id> --variant solo [--mock] -- <server command...>

Variants (who sets the objective; Jev always picks the action):
    solo      code only: the objective graph, rules and stuck recovery in bench/jev_solo.py. No LLM is ever called.
    hybrid    Claude Haiku (`claude -p`) every N steps, when Jev's confidence is low, when Jev says "stuck", or after a badge.
    scripted  the short code-side ROUTE in bench/jev.py (no rules, no recovery).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import hashlib
import json
import re
import signal
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.jev import (BATTLE_RE, DEFAULT_MODEL, PLANNER_MODEL, STATUS_RE, ClaudePlanner, JevError, drop_repeats,  # noqa: E402
                       JevPolicy, JevRateLimited, MockPlanner, Obs, Option, battle_options, label_outcome, make_client,
                       overworld_options, parse, parse_items, parse_party, press_options, route_step)
from bench.jev_solo import GRAPH, GYM_NODES, NURSE_SPOTS, STUCK_Q, is_status_move, SoloDirector, E4_ROOMS as SOLO_E4_ROOMS, STORY_RE as SOLO_STORY_RE  # noqa: E402
from bench.jev_nav import ScopedBlocks, MOVES, Hop, WorldNav, map_id  # noqa: E402
from bench.jev_atlas import HEX_RE, LearnedAtlas, explored_count, frontier_maps  # noqa: E402
from games import gen1_data as D  # noqa: E402
from bench import jev as J  # noqa: E402

AGENT_VERSION = "2"
NAME_WALK_RE = re.compile(r"^to (?!.*\bedge$)(?!\d+,\d+$).+")   # walk("to <map name>"): the server picks the nearest warp
TROD_RADIUS = 3                                 # floor within this many steps of a cell stood on counts as walked
SWITCH_REST_STEPS = 15                          # a Mansion switch just pressed is not offered again this long
SEALED_STEPS = 600                              # after a warp did not open, the people on its map come first this long
NAV_BLOCK_STEPS = 300                           # a route hop that failed is avoided this long
TALK_STOPS = 8                 # dialogue stops further on, per hop, before they count as failures
SHORT_BLOCK_STEPS = 30                          # ...or this long when something on the way stopped the walk
FACING_STEP = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
MAP_CHANGE_RE = re.compile(r"CARD KEY opened|switch behind the poster|played the POK.{1,2} FLUTE|Who wouldn't\?|"
                           r"the boulder is at \(|fell into the hole|pushed \w+ to \(\d+,\d+\), then stopped",
                           re.I)   # (a boulder on Victory Road's floor switch or in its hole opens a barrier)   # the floor changed in place ("Who wouldn't?": a Pokémon Mansion switch was pressed)
GATE_MAPS = {"Cinnabar Gym", "Lorelei's Room", "Bruno's Room", "Agatha's Room", "Lance's Room"}   # a trainer beaten there
# opens a gate (pokered CinnabarGym.asm) or the room's exit (LoreleisRoom.asm and the others)
CLUE_RE = re.compile(r"\bposter\b", re.I)                    # a person guarding something on the wall
SPOT_STEPS = 1500                               # an item ball with no way to it from here is sought this long
SCREEN_LOOP = 3                                 # a non-map screen seen this often without progress is a loop
IDLE_RELOAD = 500                               # steps without progress before the checkpoint is reloaded
FROZEN_RE = re.compile(r"no walkable route from|^walked \w+ 0/\d+ — stopped: blocked")
GOT_RE = re.compile(r"\b(got|received|obtained|learned|put .* in|delivered|handed over|traded)\b", re.I)
NO_SHOT = ("press", "walk", "battle", "talk", "wait")
STOP = {"flag": False}


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def has_status(text: str) -> bool:
    return bool(STATUS_RE.search(text) or BATTLE_RE.search(text) or "intro/title" in text or "BATTLE (" in text)


class Agent:
    def __init__(self, a: argparse.Namespace, call_tool, policy: JevPolicy, planner=None, chooser=None,
                 nav: Optional[WorldNav] = None):
        if a.variant == "solo" and (planner is not None or chooser is not None):
            raise ValueError("jev-solo must not have a planner or a fallback: no LLM may be called")
        self.nav = nav if a.variant in ("solo", "assist") else None   # static warp/edge graph from the ROM
        self.chooser = chooser                         # jev-assist: per-decision fallback (Claude Haiku)
        self.fallback_log = Path(a.run_dir) / "fallbacks.jsonl"
        self.a = a
        self.call_tool = call_tool                     # async (name, args) -> text
        self.policy = policy
        self.planner = planner
        self.path = Path(a.run_dir) / "jev_agent.json"
        self.objective_log = Path(a.run_dir) / "data" / "jev_objectives.jsonl"
        try:
            self.s = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.s = {}
        self.resumed = bool(self.s)
        for k, v in {"step": 0, "objective": "", "targets": [], "last_plan_step": -10**9, "milestones": [], "visited": [],
                     "maps": {}, "history": [], "last_save_step": 0, "plan_badges": 0, "battle_seen_step": -1,
                     "last_objective": "", "grids": {}, "said": {}, "pending_fallbacks": [], "fallbacks": 0,
                     "last_fallback_step": -10**9, "screens": {}, "screens_at": -1, "reloads": 0,
                     "last_reload_step": -10**9, "nav_taken": {}, "nav_blocked": {}, "nav_at": -1, "nav_noroute": {},
                     "fallback_cost": 0.0, "fallback_capped": False}.items():
            self.s.setdefault(k, v)
        self.director = SoloDirector(self.s) if a.variant in ("solo", "assist") else None
        if self.director and getattr(a, "progress", "") and not self.resumed:
            ids = [n.id for n in GRAPH]                 # a segment start state: nodes up to this one are finished
            self.s["manual_done"] = ids[:ids.index(a.progress) + 1]
        if isinstance(self.nav, LearnedAtlas) and not self.resumed and not self.s["visited"]:
            # a carried atlas (--atlas, experiments only) was walked in an earlier run: its maps count as visited, or
            # every map looks first reached during the current objective and its frontier wins over the route
            # (it75 end-state experiment: after the Lapras, Saffron and Vermilion were explored instead of routing to
            # Pallet Town). A blank atlas has no maps here, so goal runs are unchanged.
            self.s["visited"] = [D.map_name(int(k)) for k, m in self.nav.data["maps"].items() if m.get("visits")]
        self.party: list[dict] = []
        self.items: list[tuple[str, int]] = []
        self.team_step = -10**9
        self.reply = ""
        self.stop = ""
        self.route_hint = ""
        self.why = ""                                  # the director's reason for the objective (heal, train, node id)
        self.exploring = False
        self.entry_pending = False                      # on the objective's map, but not entered the way that counts
        self.clear_for: dict = {}                       # clear-the-way option label -> the hop it unblocks
        self.edge_hop: Optional[tuple] = None           # (side, x, y) of the chosen edge-crossing option (learned atlas)
        self.edge_opts: dict = {}
        self.planner_cost = 0.0
        self.planner_calls = 0
        self.planner_tokens = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0}
        self.tool_calls = 0

    # ------------------------------------------------------------- plumbing
    def save(self) -> None:
        if isinstance(self.nav, LearnedAtlas):
            self.nav.save()
            self.s["atlas"] = self.nav.stats()
        self.path.write_text(json.dumps(self.s, ensure_ascii=False))

    async def tool(self, name: str, **kw) -> str:
        if name in NO_SHOT:
            # press/wait ask for an image only to get the server's "(screen image unchanged)" signal (the image is dropped)
            kw.setdefault("screenshot", name in ("press", "wait"))
        self.tool_calls += 1
        emit({"type": "tool_call", "tool": name})
        return await self.call_tool(name, kw)

    def usage(self) -> None:
        emit({"type": "usage", "step": self.s["step"], "jev_calls": self.policy.calls, "planner_calls": self.planner_calls,
              "tokens": {"input": self.policy.input_tokens, "output": self.policy.output_tokens},
              "planner_tokens": self.planner_tokens, "cost_usd": round(self.policy.cost_usd + self.planner_cost, 6)})

    async def observe(self) -> str:
        """Status + on-screen text in the same shape as an action reply."""
        r = await self.tool("screen", mode="text")
        status, _, rest = r.partition("\n")
        return status + ("\nscreen:\n" + rest if rest and not rest.startswith("(no readable text") else "")

    async def refresh_team(self) -> None:
        self.party = parse_party(await self.tool("state", section="party"))
        self.items = parse_items(await self.tool("state", section="items"))
        self.team_step = self.s["step"]

    async def map_info(self, o: Obs) -> tuple[list[str], list[tuple[str, str]]]:
        maps, grids = self.s["maps"], self.s["grids"]
        if o.exits or o.connections:
            maps[o.map] = [o.exits, o.connections]
        elif o.map and o.map not in maps:
            m = parse(await self.tool("state", section="map"))
            maps[o.map] = [m.exits, m.connections]
            o.grid.update(m.grid)
            if not o.npcs:
                o.npcs, o.balls = m.npcs, m.balls
        if o.grid:                                     # keep the terrain (NPC cells are refreshed by every view)
            g = {f"{x},{y}": c for (x, y), c in o.grid.items()}
            grids.setdefault(o.map, {}).update(g)
        ex, cn = maps.get(o.map, [[], []])
        return list(ex), [tuple(c) for c in cn]

    def atlas_due(self, o: Obs) -> bool:
        """Learned atlas: read the map view on entering a map, on a map it has no grid for, and after a door opened."""
        return isinstance(self.nav, LearnedAtlas) and o.mode == "overworld" and bool(o.map) and \
            map_id(o.map) is not None and (not self.nav.known(map_id(o.map)) or o.map != self.s.get("atlas_map")
                                           or self.s.get("reobserve") == o.map)

    def free_neighbour(self, o: Obs) -> bool:
        g = self.grid(o.map)
        x, y = o.pos
        return any(g.get((x + dx, y + dy)) in (".", ",", ":", "X") for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)))

    def grid(self, name: str) -> dict:
        return {tuple(int(v) for v in k.split(",")): c for k, c in self.s["grids"].get(name, {}).items()}

    def log_objective(self, source: str, reason: str, objective: str, targets: list[str], **extra) -> None:
        rec = {"t": round(time.time(), 1), "step": self.s["step"], "source": source, "reason": reason,
               "objective": objective, "targets": targets, **extra}
        self.objective_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.objective_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        emit({"type": "objective", "step": self.s["step"], "source": source, "reason": reason, "objective": objective,
              "error": extra.get("error")})

    # ------------------------------------------------------------- hybrid planner
    def situation_text(self, o: Obs) -> str:
        ex, cn = self.s["maps"].get(o.map, [[], []])
        status = next((ln for ln in o.text.splitlines() if has_status(ln)), "")
        party = "; ".join(f"{p['species']} L{p['level']} {p['hp']}/{p['max_hp']}" for p in self.party) or o.lead
        hist = "\n".join(f"  {h}" for h in self.s["history"][-12:])
        return (f"Status: {status}\n"
                f"Map: {o.map} at {o.pos}; exits: {', '.join(ex) or 'none'}; "
                f"connections: {', '.join(f'{d} edge→{m}' for d, m in cn) or 'none'}\n"
                f"Party: {party}\nBag: {', '.join(f'{n}×{q}' for n, q in self.items) or 'empty'}\n"
                f"Visited maps: {', '.join(self.s['visited'][-40:])}\nMilestones: {', '.join(self.s['milestones'][-12:])}\n"
                f"Screen: {o.screen or '(none)'}\nRecent actions:\n{hist}")

    async def replan(self, reason: str, o: Obs) -> None:
        assert self.a.variant == "hybrid" and self.planner is not None
        self.s["last_plan_step"] = self.s["step"]
        self.s["plan_badges"] = o.badges
        if isinstance(self.planner, MockPlanner):
            plan = self.planner.plan(reason, self.s["objective"], "", self.s["milestones"])
        else:
            if not self.party:
                await self.refresh_team()
            plan = self.planner.plan(reason, self.s["objective"], self.situation_text(o))
        self.planner_calls += 1
        self.planner_cost += plan.cost_usd
        for k in self.planner_tokens:
            self.planner_tokens[k] += int(plan.tokens.get(k, 0))
        if not plan.error:
            self.s["objective"], self.s["targets"] = plan.objective, plan.targets
        self.log_objective("planner", reason, plan.objective, plan.targets, cost_usd=plan.cost_usd, tokens=plan.tokens,
                           latency_ms=plan.latency_ms, error=plan.error or None, model=getattr(self.planner, "model", ""))

    # ------------------------------------------------------------- one step
    def options(self, o: Obs, ex, cn, targets) -> list[Option]:
        if o.mode in ("intro", "unknown"):
            return press_options(intro=True)
        learn = re.search(r"make\s+room\s+for\s+([A-Z][A-Z\- ]+?)[?!.]", o.text) if o.mode == "prompt" else None
        if learn or (o.mode == "prompt" and re.search(r"Which move should be forgotten|Abandon learning", o.text, re.I)):
            # a level-up move: code decides (run 75's Charizard never learned Flamethrower: cursor presses tried to delete
            # Cut, an HM). A damaging move is learned over the weakest one; a status move is not
            new = (learn[1].strip().title() if learn else "")
            if new and is_status_move(new):
                return [Option(f"keep the old moves (do not learn {new})", "battle", {"action": "skip"}, "a status move")]
            return [Option(f"learn {new or 'the new move'} and forget the weakest move (never an HM)", "battle",
                           {"action": "learn"}, "a new damaging move replaces the weakest one")]
        if o.mode == "prompt":
            choices = J.choice_options(o)
            if "secret switch" in o.text.lower() and any(x.label == "choose YES" for x in choices):
                # the switch was chosen on purpose: answering NO only wastes the walk there (volcano-leg-2: about half
                # the answers among the cursor presses were NO, "Not quite yet!")
                return [x for x in choices if x.label == "choose YES"]
            return self.floor_choice(o, choices, targets) + press_options()
        if o.mode == "battle_start":
            return [Option("press A", "press", {"buttons": "A"})]
        if o.mode == "dialogue":
            return [Option("continue the conversation", "talk", {})]
        if o.mode == "battle":
            return battle_options(o.battle, self.party, self.items, allow_auto=True, run_note=self.run_note(o),
                                  no_effect=self.s.get("no_effect_moves"))
        if o.mode == "faint_switch":
            return battle_options(o.battle, self.party, self.items, only_switch=True) or press_options()
        opts = overworld_options(o, ex, cn, targets, self.party, self.items, self.s["step"] - self.s["last_save_step"],
                                 grid=self.grid(o.map), said=self.s["said"].get(o.map, {}),
                                 facing_said=self.s["said"].get(o.map, {}).get(f"facing {o.pos} {o.facing}", ""))
        # a person the server just found no way to (a guard behind a wall) is not offered again for a while: full run
        # 48 picked Rocket Hideout B4F's walled-off guard ~1,000 times over the reachable Rocket with the Lift Key
        noroute = self.s.get("talk_noroute", {}).get(o.map, {})
        def refused(x: Option) -> bool:
            m = re.match(r"talk to the person or object at \((\d+),(\d+)\)", x.label)
            return bool(m) and self.s["step"] - noroute.get(f"{m[1]},{m[2]}", -10**9) <= NAV_BLOCK_STEPS
        return [x for x in opts if not refused(x)]

    def run_note(self, o: Obs) -> str:
        """Whether fleeing a wild battle fits the objective is decided in code; Jev reads it as the option's criterion."""
        mine = (o.battle or {}).get("mine") or {}
        if self.why == "train":
            return "flee: gives no experience, and the objective is to train, so fighting is better"
        if self.why == "heal" or mine.get("hp", 0) < 0.35 * max(mine.get("max_hp", 1), 1):
            return "flee: recommended now, the team needs healing before more fights"
        return "flee from the wild Pokémon (no experience gained)"

    def jev_state(self, o: Obs, objective: str) -> dict:
        recent = self.s["history"][-8:]
        if o.mode in ("battle", "faint_switch") and o.battle:
            e, m = o.battle["enemy"] or {}, o.battle["mine"] or {}
            return {"objective": objective,
                    "battle": {"kind": o.battle["kind"],
                               "enemy": f"{e.get('species')} L{e.get('level')} {round(100 * e.get('hp', 0) / max(e.get('max_hp', 1), 1))}% HP {e.get('status', '')}".strip(),
                               "your_pokemon": f"{m.get('species')} L{m.get('level')} {m.get('hp')}/{m.get('max_hp')} HP {m.get('status', '')}".strip(),
                               "your_moves": [f"{mv['name']} {mv['pp']}pp" for mv in m.get("moves", [])]},
                    "party": [f"{p['slot']}. {p['species']} L{p['level']} {p['hp']}/{p['max_hp']} HP" for p in self.party],
                    "screen": o.screen, "recent_actions": recent}
        st = {"objective": objective, "location": f"{o.map} ({o.pos[0]},{o.pos[1]}) facing {o.facing}" if o.pos else "(no map yet)",
              "team": o.lead, "badges": o.badges, "money": o.money, "screen": o.screen, "hint": o.hint,
              "last_result": o.head[:200], "recent_actions": recent}
        if self.route_hint and o.mode == "overworld":
            st["map_route"] = self.route_hint             # from the game's map data (bench/jev_nav.py)
        return st

    async def step(self) -> None:
        if isinstance(self.nav, LearnedAtlas):
            self.nav.reach_cache = None                   # (never left on by a step that ended early)
        o = parse(self.reply)
        self.route_hint = ""
        self.s["milestones"] += [e for e in o.events if e not in self.s["milestones"]]
        for e in o.events:                               # the league, per attempt (milestones keep each text once: a
            if e.startswith("defeated: "):               # second win over Lorelei after a loss was lost; Codex review 5)
                beaten = self.s.setdefault("league_beaten", [])
                if e[len("defeated: "):] not in beaten:
                    beaten.append(e[len("defeated: "):])
        if any(e.startswith("champion defeated") for e in o.events):
            self.stop = "champion"
            return
        if o.mode == "over":
            self.stop = "budget"
            return
        if o.map and o.map not in self.s["visited"]:
            self.s["visited"].append(o.map)
        if o.map:
            self.s["badges"] = o.badges
        if o.mode in ("battle", "faint_switch") and (self.team_step < self.s["battle_seen_step"] or self.team_step < 0
                                                     or self.s.get("refresh_party")):
            await self.refresh_team()
            self.s["refresh_party"] = False
        if o.mode in ("battle", "battle_start", "faint_switch"):
            self.s["battle_seen_step"] = self.s["step"]
            enemy = (o.battle or {}).get("enemy") or {}
            where = self.s.get("prev_map", "")
            if (o.battle or {}).get("kind", "").startswith("wild") and enemy.get("level") and where:
                lv = self.s.setdefault("wild_levels", {})       # the strongest wild Pokémon met on each map (training)
                lv[where] = max(lv.get(where, 0), enemy["level"])
        elif o.mode == "overworld" and (self.team_step < 0 or self.s["step"] - self.team_step >= 30
                                        or self.team_step < self.s["battle_seen_step"] or self.s.get("refresh_items")):
            await self.refresh_team()
            self.s["refresh_items"] = False
            if isinstance(self.nav, LearnedAtlas):
                self.nav.set_card_key(any(n == "Card Key" for n, _ in self.items))
        ex, cn = await self.map_info(o) if o.mode == "overworld" else ([], [])
        if o.mode == "overworld" and o.map:
            # replies after a warp often carry no map rows: keep the last people seen on this map
            known = self.s.setdefault("npcs", {})
            if self.remember_people(o):
                pass
            elif o.map not in known:
                m = parse(await self.tool("state", section="map"))
                o.npcs, o.balls = m.npcs, m.balls
                known[o.map] = [list(n) for n in o.npcs]
            self.remember_balls(o)
            if map_id(o.map) is not None:
                self.boulders(map_id(o.map), o)           # every view keeps the atlas's boulders current (Codex review 15)
            # hidden objects keep their sprite slot: a spot that answered "nothing to talk to here" is nobody
            said = self.s["said"].get(o.map, {})
            o.npcs = [n for n in o.npcs if not said.get(f"{n[0]},{n[1]}", "").startswith("nothing to talk to")]
        again = o.mode == "overworld" and bool(o.map) and self.s.get("reobserve") == o.map
        if self.atlas_due(o):
            # learned atlas: record what the player can see on entering a map (full map view + wWarpEntries in WRAM),
            # and again after a door opened on it
            view = await self.tool("state", section="map")
            if again:
                self.s["grids"].setdefault(o.map, {}).update({f"{x},{y}": c for (x, y), c in parse(view).grid.items()})
            warps = await self.tool("memory", address="D3AE", length=129)
            last = await self.tool("memory", address="D365", length=1)        # wLastMap: where "outside" warps lead
            self.nav.observe(map_id(o.map), view, warps, cn, last_map_text=last)
            full = parse(view).grid
            if full and map_id(o.map) is not None:
                # the whole map's boulders, as they are now: they reset when a floor is entered again, and the reply's
                # 10x9 window kept the old cells out of view as walls (Codex review 17)
                shown, o.grid = o.grid, full
                self.boulders(map_id(o.map), o)
                o.grid = shown
        if o.mode == "overworld" and o.map.startswith("Pokémon Mansion"):
            # the doors' real state (EVENT_MANSION_SWITCH_ON, 0xD796 bit 0), not a count of presses: full run 85 had
            # 21 counted flips and floor "walked" in both states at cells that are walls in one of them, so the floors
            # that open in the other state were never explored (3F's way to the collapsed floor, 2F's east stairs)
            flag = HEX_RE.search(await self.tool("memory", address="D796", length=1) or "")
            if flag:
                self.s["mansion_doors"] = int(flag[2].split()[0], 16) & 1
        if o.mode == "overworld" and o.map:
            if self.s.get("atlas_map") != o.map:
                self.s.get("push_tried", {}).pop(o.map, None)   # a push refused from one side may work from another
            self.s["atlas_map"] = o.map
            if again:
                self.s.pop("reobserve", None)

        kind = o.mode
        battle = kind in ("battle", "faint_switch")
        nouls = None
        facts = None
        if self.director:
            facts = self.director.facts(o, self.party, self.items)
            if isinstance(self.nav, LearnedAtlas):
                facts.explored = explored_count(self.nav)
            self.director.track(self.s["step"], o, facts)
            objective, targets, why = self.director.objective(facts, o)
            if kind == "overworld":
                nouls = self.director.check_questions(facts)
        elif self.a.variant == "scripted":
            objective, targets, why = *route_step(self.s["milestones"])[:2], "route"
            targets = list(targets)
        else:
            since = self.s["step"] - self.s["last_plan_step"]
            if kind in ("overworld", "battle", "prompt", "intro"):
                if not self.s["objective"]:
                    await self.replan("start", o)
                elif since >= self.a.replan_every:
                    await self.replan(f"routine ({self.a.replan_every} steps)", o)
                elif o.badges > self.s["plan_badges"]:
                    await self.replan("new badge", o)
            objective, targets, why = self.s["objective"] or "Make progress in the game.", list(self.s["targets"]), "planner"
            nouls = {"stuck": STUCK_Q} if kind == "overworld" else None
        if self.a.variant != "hybrid" and objective != self.s["last_objective"] and kind in ("overworld", "intro"):
            self.log_objective("graph" if self.director else "route", why, objective, targets)
            self.s["last_objective"] = objective

        self.why = why
        opts = self.options(o, ex, cn, targets)
        route_key = ""
        if self.director and kind == "overworld":
            opts = self.director.extra_options(o, facts, self.party, ex, cn, why) + opts
            if self.nav and not o.npcs and any(self.s["step"] - v <= 3 for v in self.s["nav_noroute"].values()):
                m = parse(await self.tool("state", section="map"))   # who stands in the way (no view in a refusal)
                o.npcs, o.balls = m.npcs, m.balls
            if "X" in self.grid(o.map).values() and facts and "Strength" in facts.moves:
                # a floor switch here: where the boulders stand now (a push cut short moved one: plateau-leg-5 offered
                # the boulder where it had been)
                m = parse(await self.tool("state", section="map"))
                o.grid.update(m.grid)
            self.learn_walked(o)
            self.learn_trod(o)
            self.learn_noroute(o)
            if isinstance(self.nav, LearnedAtlas):
                self.nav.reach_cache = {}                 # until this step's options are built (cleared below)
            nav_opts, route_key = self.nav_options(o, targets, facts, why)
            if nav_opts:                                 # concrete warps replace "walk to <map>" (nearest-warp guesses)
                quiet = (bool(route_key) or self.exploring) and self.s.get("recovery", 0) < 3   # blind walks dilute the choice
                opts = nav_opts + [x for x in opts if not (x.tool == "walk" and NAME_WALK_RE.match(x.args.get("path", "")))
                                   and not (x.tool == "walk" and x.args.get("path", "").endswith(" edge"))   # nav lists reachable edges
                                   and not (quiet and x.label.startswith("walk ") and x.label.endswith(" 4 tiles"))]
            if why in GYM_NODES and o.map.endswith("Gym") and any(x.label.startswith("talk to the person") for x in opts):
                # in the gym the objective names: the trainers and the leader are the options (blind walks only pace)
                opts = [x for x in opts if not (x.label.startswith("walk ") and x.label.endswith(" tiles"))
                        and x.label != "talk to what you are facing"]
            if o.map.endswith(" Elevator") and not self.s.get("elevator"):
                opts = self.panel_first(o, opts)
            elif targets and o.map == targets[-1] and why not in ("heal", "train") and not self.entry_pending:
                opts = self.objective_map_options(o, opts)
            doors = self.card_door_options(o)
            if doors:                                     # Silph Co.: a locked door is the way on until it is open
                opts = doors + opts
            opts = self.clue_options(o) + opts            # the Game Corner: the switch behind the guarded poster
            opts = self.switch_options(o, opts)           # the Pokémon Mansion: secret switches open and shut doors
            opts = self.mansion_trapped(o, opts)
            if why not in ("heal", "train"):              # (healing first: Codex review 4)
                opts = self.boulder_options(o, facts, opts)   # Victory Road: a boulder onto each floor switch (Strength)
            if o.map in targets and why not in ("heal", "train"):
                before = opts
                opts = self.floor_options(o, opts, targets)   # floor never walked on (a hole drops to the floor below)
                opts = self.puzzle_stay(o, opts, targets)     # and the other floors, not the way out
                opts = self.puzzle_order(opts, targets, o)    # one kind of move at a time while a puzzle is pending
                opts = opts or before                         # (never nothing: volcano-leg-17 sent Jev an empty choice)
            elif why not in ("heal", "train"):
                opts = self.puzzle_return(o, opts, targets)   # the way on is a switch back there, not a new map
            opts = self.sealed_first(o, opts, why)
            if any(x.label.startswith("search the trash can") for x in opts):
                # Lt. Surge's locked door: the cans are the way on, leaving the gym is not (full run 42 left ~600 times)
                opts = [x for x in opts if not (x.tool == "walk" and ("warp at" in x.label or x.label.endswith("edge)")))]
            if why not in ("train", "heal"):
                self.s.pop("train_spot", None)            # kept for one training spell, healing trips included
            if why == "train" and self.nav:
                train = self.train_options(o, facts)
                if train:                                 # pace in real tall grass instead of blind walks
                    opts = train + [x for x in opts if not x.label.endswith("through grass")
                                    and not (x.label.startswith("walk ") and x.label.endswith(" tiles"))]
            if why == "heal" and o.map.endswith("Poké Center"):
                opts = [x for x in opts if not x.label.startswith("talk to the person")]   # the nurse option replaces them
            seen, uniq = set(), []
            for x in opts:
                if x.label.lower() not in seen:
                    seen.add(x.label.lower())
                    uniq.append(x)
            opts = uniq
        if isinstance(self.nav, LearnedAtlas):
            self.nav.reach_cache = None                   # the action and what it teaches change the atlas
        forced = self.director.forced_recovery(self.s["step"]) if self.director and kind == "overworld" else None
        if not forced and self.director and kind == "overworld":
            forced = self.director.bag_option(self.items, self.party) or self.director.flute_option(self.items) or \
                self.director.league_recover_option(o, self.party, self.items) or \
                self.director.league_prep_option(o, self.party, self.items)
        if self.director and kind == "overworld" and self.director.want_checkpoint(self.s["step"]):
            await self.tool("save_state", slot="jev-progress")
        if kind == "overworld" and (o.map.endswith("Poké Center") or o.map in NURSE_SPOTS) and \
                self.s.pop("want_safe", False):
            # (the Indigo Plateau Lobby too: full run 90's safe checkpoint stayed in Cinnabar at six badges; Codex 17)
            await self.tool("save_state", slot="jev-safe")   # healed here: a place a reload can always leave
            self.s["safe_step"] = self.s["step"]
        if forced:
            opts = [forced]                              # code decides: logged as a forced decision
        loop_dropped = False
        if kind in ("overworld", "prompt", "intro"):
            kept = drop_repeats(opts, self.s["history"], keep=("press A",) if kind == "prompt" else ())
            loop_dropped = len(kept) < len(opts)
            opts = kept
        if kind in ("battle", "faint_switch"):
            # a switch the game refused ("is already out", "no will to fight") is not offered again right away
            failed = {h.removeprefix(J.AUTO).split(" -> ", 1)[0] for h in self.s["history"][-4:]
                      if "is already out" in h or "no will to fight" in h}
            kept = [x for x in opts if x.label not in failed]
            opts = kept or (press_options() if kind == "faint_switch" else opts)   # every switch refused: use the menu
        screen, screen_stuck = self.screen_entry(o), False
        if kind != "overworld" and screen["n"] >= SCREEN_LOOP and len(opts) > 1:
            # the same menu/dialog/prompt screen keeps coming back without progress: try what was not tried here yet;
            # when everything was tried, start over and report it as stuck (assist asks the fallback model)
            untried = [x for x in opts if x.label not in screen["tried"]]
            if untried:
                opts, loop_dropped = untried, True
            else:
                screen["tried"], screen_stuck = [], True
        if not forced and self.director and kind != "over":
            reload = self.idle_reload()
            if reload:
                opts, forced = [reload], reload
        if not opts:                                     # a Jev choice needs at least one option (HTTP 422 otherwise)
            opts = [Option(f"walk {d} 4 tiles", "walk", {"path": f"{d} 4", "on_battle": "stop"}) for d in
                    ("up", "down", "left", "right")] if kind == "overworld" else press_options()
        dec = self.policy.decide(kind, self.jev_state(o, objective), opts, step=self.s["step"], nouls=nouls, battle=battle)
        if self.director and dec.noul:
            marked = self.director.absorb(facts, dec.noul)
            if marked:
                self.log_objective("jev", "Jev judged the objective done (3 votes >= 0.8)", f"done: {marked}", [])
        if self.a.variant == "hybrid" and not dec.record.get("forced") \
                and self.s["step"] - self.s["last_plan_step"] >= self.a.min_replan_gap:
            low = dec.record["confidence"] < self.a.confidence_threshold
            stuck = dec.noul.get("stuck", 0.0) >= self.a.stuck_threshold
            if low or stuck:
                dec.record["superseded"] = True
                self.policy.log(dec.record)
                await self.replan(f"low Jev confidence {dec.record['confidence']:.2f}" if low else
                                  f"Jev thinks the player is stuck ({dec.noul['stuck']:.2f})", o)
                objective, targets = self.s["objective"] or objective, list(self.s["targets"])
                opts = self.options(o, ex, cn, targets)
                dec = self.policy.decide(kind, self.jev_state(o, objective), opts, step=self.s["step"], battle=battle)
                dec.record["after_replan"] = True
        if facts is not None:
            dec.record["recovery"] = self.s.get("recovery", 0)
            dec.record["why"] = why
        if self.chooser is not None and not dec.record.get("forced"):
            trigger = self.fallback_trigger(dec, loop_dropped, kind == "overworld", screen_stuck)
            if trigger and self.s["step"] - self.s["last_fallback_step"] >= self.a.fallback_gap:
                if self.fallback_allowed():
                    await self.fallback(trigger, dec, o, objective, opts, facts, kind)
                else:
                    dec.record["fallback_capped"] = trigger
        opt = dec.option
        self.edge_hop = self.edge_opts.get(opt.label)
        screen["tried"] = (screen["tried"] + [opt.label])[-20:]
        reply = await self.tool(opt.tool, **opt.args)
        if opt.tool == "walk" and o.pos and FROZEN_RE.search(reply.split("\n", 1)[0]) and self.free_neighbour(o):
            # After some scripted push-backs (Oak's "Don't go away yet!") the game ignores directions until a menu
            # opens and closes. Code fix, not a Jev decision: unstick once and retry the same walk.
            await self.tool("press", buttons="START W10 B W10 B")
            reply = await self.tool(opt.tool, **opt.args)
            dec.record["unstuck"] = True
        for i, (tool, args) in enumerate(opt.then):      # composite options (walk next to it, face it, talk)
            head = reply.split("\n", 1)[0]
            if parse(reply).mode != "overworld" or (i == 0 and opt.args.get("path", "").startswith("to ") and "arrived" not in head):
                break                                    # did not get there, or something else started
            reply = await self.tool(tool, **args)
        after = parse(reply)
        if self.nav and o.map and opt.tool == "walk":
            self.nav_feedback(o, opt, after, route_key)
        self.sleeper_gone(o, after)
        if o.map and (opt.label.startswith(("talk to", "examine")) or opt.tool == "talk" or any(t == "talk" for t, _ in opt.then)):
            self.s.setdefault("npcs", {}).pop(o.map, None)   # people move after talking (Bill into his machine)
        self.remember_talk(o, opt, after)
        self.remember_tree(o, after, reply)
        self.remember_door(o, opt, reply)
        self.remember_push(o, opt, reply)
        if self.director:
            self.director.trash_result(opt.label, reply, left=o.map == "Vermilion Gym" and after.map not in ("", o.map))
            self.director.heard(reply)
        self.remember_refusal(opt, reply)
        self.remember_outmatched(reply)
        self.remember_choice(o, opt)
        if opt.tool == "manage" and opt.args.get("action") == "save":
            self.s["last_save_step"] = self.s["step"]
        if opt.tool in ("manage", "shop") or any(t == "shop" for t, _ in opt.then) or GOT_RE.search(reply):
            self.s["refresh_items"] = True              # the bag, HMs or moves may have changed
        if self.director and facts is not None and self.blacked_out(o, after, reply) and \
                self.s["step"] - self.s.get("blackout_step", -10**9) > 5:
            self.s["blackout_step"] = self.s["step"]
            gym = self.director.s.get("gym_map_seen", "")
            if gym.endswith("Gym") or gym in SOLO_E4_ROOMS:
                self.s["said"].pop(gym, None)            # lost in a gym: its leader and trainers are to be faced again
            if self.s.pop("league_beaten", None):        # a loss resets the league: every member again
                for room in SOLO_E4_ROOMS:
                    self.s["said"].pop(room, None)
            self.director.lost(facts)                    # the milestone event is not reliable; the battle text is
        if "fighting fit" in reply and o.map == "Indigo Plateau Lobby":
            self.s["lobby_fresh"] = True                 # healed for this league attempt (see SoloDirector.objective)
        if "fighting fit" in reply and o.map:
            self.s.setdefault("healed_at", [])
            if o.map not in self.s["healed_at"]:
                self.s["healed_at"].append(o.map)        # the black-out respawn point
        if "fighting fit" in reply:
            self.team_step = -10**9                      # healed at a Poké Center: re-read the party (heal rule)
            self.s["want_safe"] = True                   # (a safe checkpoint: see reload_option)
        if opt.tool == "battle" and (opt.args.get("action") == "switch" or "fainted" in reply.lower()):
            self.s["refresh_party"] = True              # Gen 1 reorders the party on a switch; faints change the switch set
        line = (J.AUTO if dec.record.get("forced") else "") + f"{opt.label} -> {after.head[:90]}"
        if not dec.record.get("forced"):
            repeat = kind not in ("battle", "faint_switch") and self.s["history"].count(line) >= 2
            ok, how = label_outcome(kind, opt, o, after, repeat=repeat)
            dec.record.update(correct=ok, outcome=how)
        dec.record["result"] = after.head[:120]
        dec.record["at"] = f"{o.map} {o.pos}" if o.map else o.mode
        self.policy.log(dec.record)
        self.s["history"] = (self.s["history"] + [line])[-12:]
        self.s["step"] += 1
        self.settle_fallbacks(after)
        if self.director and self.a.stuck_fail_steps and \
                self.s["step"] - self.s.get("last_progress_step", 0) >= self.a.stuck_fail_steps:
            self.stop = "stuck"           # solo (final exam): stuck = fail; assist: the fallbacks did not help either
        self.reply = reply if has_status(reply) or after.mode == "over" else reply + "\n" + await self.observe()

    # ------------------------------------------------------------- jev-assist fallbacks
    def fallback_trigger(self, dec, loop_dropped: bool, overworld: bool, screen_stuck: bool = False) -> str:
        """Low confidence anywhere; stuck when the map position or a menu/dialog/prompt screen keeps repeating
        without progress (every option there was tried); loop when the code dropped repeated options."""
        if dec.record["confidence"] < self.a.fallback_threshold:
            return f"low confidence {dec.record['confidence']:.2f}"
        if screen_stuck or overworld and (self.s.get("recovery", 0) >= 2 or self.s.get("pos_repeat", 0) >= 10):
            return "stuck"
        if loop_dropped:
            return "loop"
        return ""

    # ------------------------------------------------------------- navigation (static warp graph, no LLM)
    def remember_outmatched(self, reply: str) -> None:
        """Battles auto gave up on because no move with PP left can hit, since the last heal (SoloDirector.objective:
        lavender-train-2 ran from Tower 6F's Gastly ~25 times with Flamethrower at 0 PP)."""
        if "no move with PP left can affect" in reply:
            self.s["outmatched"] = self.s.get("outmatched", 0) + 1
        elif "fighting fit" in reply or "fully healed" in reply or re.search(r"Enemy [^|]* fainted!", reply):
            self.s["outmatched"] = 0                     # healed, or a fight won since: what it has still works
        fail = self.s.get("talk_fail")
        if not fail or fail[1] == self.s["step"]:        # (the stop's own reply: what was said comes next)
            return
        self.s.pop("talk_fail")
        if "fully healed" in reply and self.s["step"] - fail[1] <= 2:
            # the walk stopped for Pokémon Tower 5F's purified zone, not for a person (lavender-train-3: its stairs were
            # blocked that way, healing found no route and training went on with Flamethrower empty)
            key = fail[0]
            fails = self.s.get("nav_fail_from", {}).get(key) or []
            if fails and len(fails[-1]) > 2 and fails[-1][2] == fail[1]:
                fails.pop()
            if not fail[2]:
                self.s["nav_blocked"].pop(key, None)
            if self.s["nav_noroute"].get(key) == fail[1]:
                self.s["nav_noroute"].pop(key)

    def remember_refusal(self, opt: Option, reply: str) -> None:
        """'X is not compatible with CUT': this Pokémon cannot learn that HM, teach another one. Only that line counts:
        "can't learn more than 4 moves!" is the forget-a-move prompt (full run 45 marked Charizard refused on it)."""
        hit = re.search(r"doesn't affect Enemy ([^!|]+)!", reply)
        if opt.tool == "battle" and opt.args.get("action") == "fight" and opt.args.get("target") and hit:
            key = f"{opt.args['target'].lower()}:{hit[1].strip().lower()}"
            if key not in self.s.setdefault("no_effect_moves", []):
                self.s["no_effect_moves"].append(key)
        if opt.tool == "manage" and opt.args.get("action") == "toss" and "threw away" not in reply:
            # only "too important to toss" is for good; a menu that did not work out is tried again later (full run 63:
            # seven "could not select TOSS" in a row marked every spare item, and the bag stayed full for good)
            if "too important" in reply:
                self.s.setdefault("no_toss", []).append(opt.args["target"])
            else:
                self.s["toss_failed_step"] = self.s["step"]
        if opt.tool == "manage" and opt.args.get("action") == "use" and "won't have any effect" in reply.lower():
            # a vitamin at its cap, a candy on a L100 Pokémon: not offered again for it (Codex review 16: HP Up and Iron
            # stayed in run 88's bag and league preparation chose them again and again)
            self.s.setdefault("no_effect", []).append(
                f"{opt.args['target']}:{opt.args.get('target2', '').partition(':')[0].strip()}")
        if opt.tool == "manage" and opt.args.get("action") == "use" and "not compatible" in reply:
            refused = f"{opt.args['target']}:{opt.args.get('target2', '').partition(':')[0].strip()}"
            self.s.setdefault("hm_no", []).append(refused)
        elif opt.tool == "manage" and opt.args.get("action") == "use" and opt.args.get("target", "").startswith("TM") \
                and "learned" not in reply.lower():
            # a TM not learned for another reason (nothing worth forgetting, a menu that went wrong): twice and that
            # Pokémon is passed over, so the same teach is not offered forever (Codex review 7)
            key = f"{opt.args['target']}:{opt.args.get('target2', '').partition(':')[0].strip()}"
            tries = self.s.setdefault("teach_tries", {})
            tries[key] = tries.get(key, 0) + 1
            if tries[key] >= 2:
                self.s.setdefault("hm_no", []).append(key)

    def blacked_out(self, o: Obs, after: Obs, reply: str) -> bool:
        """A lost battle: the text says so, or (full run 50: the last turns of a loss to Misty were plain "pressed A"
        replies) the game state does: out of a battle onto another map with the money halved."""
        prev = self.s.get("ow") or ["", 0]
        if after.mode == "overworld" and after.map:
            self.s["ow"] = [after.map, after.money]
        elif o.mode == "overworld" and o.map:
            self.s["ow"] = [o.map, o.money]
        if "blacked out" in reply:
            return True
        return (o.mode != "overworld" and after.mode == "overworld" and bool(after.map) and bool(prev[0])
                and after.map != prev[0] and prev[1] > 0 and after.money < prev[1] and after.money * 2 <= prev[1] + 1)

    def panel_first(self, o: Obs, opts: list[Option]) -> list[Option]:
        """In an elevator with no floor chosen since stepping in, the doors lead back where it came from: the panel
        first, the doors left out (after the Silph Scope the elevator is the only way off Giovanni's side of B4F, and
        full run 54 rode it ~1,900 times without examining the panel)."""
        objects = self.object_options(o)
        if not objects:
            return opts
        return objects + [x for x in opts if not (x.tool == "walk" and ("warp at" in x.label or x.label.endswith("edge)")))]

    def floor_choice(self, o: Obs, choices: list[Option], targets: list[str]) -> list[Option]:
        """An elevator's floor list: the floor of the building the objective names (latest target first); with none
        named, the way out (1F, or the top entry: the Rocket Hideout's B1F). Full run 54 took the Silph Scope on B4F
        and rode the elevator ~1,900 times without ever choosing a floor."""
        elev = o.map or self.s.get("prev_map", "")
        floors = {x.label[len("choose "):]: x for x in choices if x.label.startswith("choose ")}
        if not elev.endswith(" Elevator") or not floors:
            return choices
        building = elev[:-len(" Elevator")]
        rule = self.s.get("entry_rule", {})
        want = next((t[len(building) + 1:] for t in reversed(targets)    # not a floor the elevator cannot really reach
                     if t.startswith(building + " ") and t[len(building) + 1:] in floors and t not in rule), None)
        if want is None:
            want = "1F" if "1F" in floors else next((f for f in floors if f != "CANCEL"), None)
        return [floors[want]] if want else choices

    def objective_map_options(self, o: Obs, opts: list[Option]) -> list[Option]:
        """On the objective's own map: talk to everyone there, and pick up what lies there, before leaving it again
        (full run 68 beat Giovanni next to the Silph Scope and took "walk to Rocket Hideout Elevator"); then the
        machines, PCs and furniture of a small room."""
        def leaving(x: Option) -> bool:
            return x.tool == "walk" and ("warp at" in x.label or x.label.endswith("edge)")
                                         or bool(NAME_WALK_RE.match(x.args.get("path", ""))))
        if any(x.label.startswith("talk to the person") and ("not talked to yet" in (x.desc or "") or
                                                             "not taken yet" in (x.desc or "")) for x in opts):
            # blind walks only pace while someone here is still unheard (full run 74: ~490 steps of them on Pokémon
            # Tower 7F with the Rockets and Mr. Fuji offered)
            return [x for x in opts if not leaving(x) and not (x.label.startswith("walk ") and x.label.endswith(" tiles"))
                    and x.label != "talk to what you are facing"]
        objects = self.object_options(o)
        if any("not tried yet" in (x.desc or "") for x in objects):
            opts = [x for x in opts if not (x.tool == "walk" and ("warp at" in x.label or x.label.endswith("edge)")))]
        return objects + opts

    def remember_choice(self, o: Obs, opt: Option) -> None:
        """The floor chosen on an elevator panel (a prompt carries no status line: the map is the last one seen)."""
        if opt.label.startswith("choose ") and (o.map or self.s.get("prev_map", "")).endswith("Elevator"):
            self.s["elevator"] = opt.label[len("choose "):]       # the director's elevator stage reads it

    def remember_people(self, o: Obs) -> bool:
        """Keep the last people seen on this map (replies after a warp often carry no map rows). False: none known."""
        known = self.s.setdefault("npcs", {})
        if o.grid and known.get(o.map):
            # a window view shows only the people near the player: keep the ones remembered outside it (full run
            # 48: a 10x9 window replaced Rocket Hideout B4F's nine people with one, the Lift Key Rocket was gone)
            o.npcs = [tuple(n) for n in known[o.map] if tuple(n) not in o.grid] + list(o.npcs)
        elif not o.npcs and known.get(o.map):
            o.npcs = [tuple(n) for n in known[o.map]]
        elif not o.npcs:
            return False
        known[o.map] = [list(n) for n in o.npcs]
        return True

    def remember_balls(self, o: Obs) -> None:
        """Keep the item balls seen on this map like the people: a refusal or a status-only reply shows none, and that
        is not a taken ball (the Card Key's spot goal was dropped on the next step). A view covering a ball's cell
        without it means it was taken."""
        known = self.s.setdefault("balls", {})
        balls = [tuple(b) for b in known.get(o.map, []) if tuple(b) not in o.grid] + list(o.balls)
        o.balls = list(dict.fromkeys(balls))
        known[o.map] = [list(b) for b in o.balls]

    def sealed_first(self, o: Obs, opts: list[Option], why: str) -> list[Option]:
        """A warp the map shows a way to did not open: something on this map opens it, so the people here come before
        leaving (full run 67 hit the Game Corner's shut stairs before talking to the poster guard, learned them
        unreachable, left, and paced Celadon ~3,800 steps). Not while healing, and the route to a spot goal or an entry
        rule's warp stays: it crosses this map's own pads (Saffron Gym; Codex review)."""
        sealed = self.sealed_talks(o, opts)
        if not sealed or why == "heal":
            return opts
        return sealed + [x for x in opts if x not in sealed and not (
            x.tool == "walk" and ("warp at" in x.label or x.label.endswith("edge)"))
            and not (self.entry_pending and x.label.startswith("follow the map route")))]

    def sealed_talks(self, o: Obs, opts: list[Option]) -> list[Option]:
        """After a warp on this map could not be reached (no one in the way): the talk options to people here not
        talked to yet (and not known to be out of reach), for a while."""
        sealed = self.s.get("sealed", {}).get(o.map)
        if not sealed or self.s["step"] - sealed[2] > SEALED_STEPS:
            return []
        said, nr = self.s["said"].get(o.map, {}), self.s.get("talk_noroute", {}).get(o.map, {})
        out = []
        for x in opts:
            m = re.match(r"talk to the person or object at \((\d+),(\d+)\)", x.label)
            if m and f"{m[1]},{m[2]}" not in said and f"{m[1]},{m[2]}" not in nr:
                out.append(x)
        return out

    def clue_options(self, o: Obs) -> list[Option]:
        """Someone said they guard a poster: the walls next to where they stood, examined from that cell (facing each
        one), until one answers. Sides already tried are not offered again."""
        clue = self.s.get("clues", {}).get(o.map)
        cur = map_id(o.map) if o.map else None
        if not clue or cur is None or not o.pos or self.nav is None:
            return []
        try:
            cells = self.nav.map(cur)["cells"]
        except (KeyError, IndexError):
            return []
        x, y = clue
        said = self.s["said"].get(o.map, {})
        out = []
        for side, (dx, dy), face in (("below", (0, -1), "up"), ("right", (-1, 0), "left"), ("left", (1, 0), "right"),
                                     ("above", (0, 1), "down")):
            wx, wy = x + dx, y + dy
            if not (0 <= wy < len(cells) and 0 <= wx < len(cells[wy])) or cells[wy][wx] != "#":
                continue
            label = f"examine the object at ({wx},{wy}) from {side} (beside where someone guarded a poster)"
            if f"{wx},{wy} " + label.rsplit(" from ", 1)[-1] in said:
                continue
            at = tuple(o.pos) == (x, y)
            first = {"path": f"{face} 1", "on_battle": "stop"} if at else {"path": f"to {x},{y}", "on_battle": "stop"}
            then = ([] if at else [("walk", {"path": f"{face} 1", "on_battle": "stop"})]) + [("talk", {})]
            out.append(Option(label, "walk", first, "a guard stood here watching a poster on the wall: face the wall and "
                              "press A (not tried yet)", then=then))
        return out

    def card_door_options(self, o: Obs) -> list[Option]:
        """With the Card Key: each locked door (L in the map view, two cells wide) this part of the map reaches, as
        'stand next to it, face it, talk'. A door that did not open is left alone for a while (full run 61 reached
        Silph Co. 11F with no Card Key and no idea of the doors)."""
        if not any(n == "Card Key" for n, _ in self.items) or not o.pos:
            return []
        grid = self.grid(o.map)
        locked = {c for c, ch in grid.items() if ch == "L"}
        if not locked:
            return []
        reach = None
        if self.nav is not None and map_id(o.map) is not None:
            held = getattr(self.nav, "card_key", False)
            try:
                if held:
                    self.nav.set_card_key(False)         # (the doors as they are: walls until opened)
                reach, _ = self.nav.reach(map_id(o.map), tuple(o.pos))
            except (KeyError, IndexError, ValueError):
                reach = None
            finally:
                if held:
                    self.nav.set_card_key(True)
        tried = self.s.get("card_tried", {}).get(o.map, {})
        out, done = [], set()
        px, py = o.pos
        for door in sorted(locked, key=lambda c: abs(c[0] - px) + abs(c[1] - py)):
            if door in done:
                continue
            pair = {door} | {(door[0] + dx, door[1] + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                             if (door[0] + dx, door[1] + dy) in locked}
            done |= pair
            if any(self.s["step"] - tried.get(f"{x},{y}", -10**9) <= NAV_BLOCK_STEPS for x, y in pair):
                continue
            stands = [((x + dx, y + dy), face, (x, y)) for x, y in pair for (dx, dy), face in J.STEP_TOWARD.items()
                      if grid.get((x + dx, y + dy)) in (".", ",", ":", "X") and (x + dx, y + dy) not in o.npcs
                      and (reach is None or (x + dx, y + dy) in reach or (x + dx, y + dy) == (px, py))]
            if not stands:
                continue
            (sx, sy), face, (dx_, dy_) = min(stands, key=lambda t: abs(t[0][0] - px) + abs(t[0][1] - py))
            first = {"path": f"{face} 1" if (sx, sy) == (px, py) else f"to {sx},{sy}", "on_battle": "stop"}
            then = ([("walk", {"path": f"{face} 1", "on_battle": "stop"})] if (sx, sy) != (px, py) else []) + [("talk", {})]
            out.append(Option(f"open the locked door at ({dx_},{dy_}) with the Card Key", "walk", first,
                              "a locked door (L): face it and talk with the Card Key in the bag; beyond it is part of "
                              "the floor this side cannot reach", then=then))
        return out[:3]

    def blocked_now(self, o: Optional[Obs] = None) -> frozenset:
        """Route hops that keep failing (the same set the objective's route leaves out), each only in the parts of the
        map it failed from: full run 81 was refused Rock Tunnel B1F's far ladder from the east part, and the block then
        hid it from (23,11), whose part does reach it (~1,700 steps). Every active key is kept; whoever asks about a
        concrete cell asks `at(key, (map, x, y))`, and a route search asks per arrival (Codex reviews 8, 9)."""
        frm = self.s.get("nav_block_from", {})
        # each origin holds until its own step + NAV_BLOCK_STEPS (an expired part does not come back when another part
        # renews the hop: Codex review 10); origins without a step (older state) last as long as the hop
        frm = {k: [f[:2] for f in (v if isinstance(v[0], list) else [v])
                   if len(f) < 3 or self.s["step"] - f[2] <= NAV_BLOCK_STEPS] for k, v in frm.items() if v}
        frm = {k: v for k, v in frm.items() if v}
        linked = self.nav.linked if isinstance(self.nav, LearnedAtlas) else None
        return ScopedBlocks({k for k, until in self.s["nav_blocked"].items() if until > self.s["step"]}, frm, linked)

    def blocked_here(self, o: Obs, cur: int, x: int, y: int) -> bool:
        """Whether the hop at (x,y) on this map is blocked for the player where they stand."""
        b, key = self.blocked_now(o), f"{cur}:{x},{y}"
        return b.at(key, (cur, *o.pos)) if o.pos and isinstance(b, ScopedBlocks) else key in b

    def mansion_trapped(self, o: Obs, opts: list[Option]) -> list[Option]:
        """In the Pokémon Mansion with no route to the objective (healing, or Blaine after the Secret Key): the doors are
        the problem, so a switch not pressed yet in this door state comes first, then any switch, and blind walks go.
        The stairs stay (B1F's switches are reached from 1F). 1F's part with the stairs to B1F is shut off from the back
        door unless EVENT_MANSION_SWITCH_ON (pokered PokemonMansion1F.asm swaps block (12,9)): full run 86 and
        volcano-leg-26 went up and down those stairs ~500 steps, the experiment only got out by fainting."""
        if not o.map.startswith("Pokémon Mansion") or any(x.label.startswith("follow the map route") for x in opts):
            return opts
        # a floor whose doors changed since it was last seen is looked at again before another press: its route may be
        # open now (Codex review 13: with the exit's door state already set, an untried switch would undo it)
        stale = set(self.s.get("floor_changed", [])) - {o.map}
        look = [x for x in opts if x.tool == "walk" and "warp at" in x.label
                and any(x.label.split("→ ", 1)[-1].startswith(f) for f in stale)]
        if look:
            return look
        sw = [x for x in opts if x.label.startswith("press the secret switch")]
        if not sw:
            return opts
        doors = self.s.get("mansion_doors", self.s.get("flips", 0) % 2)
        tried = set(self.s.get("switch_tried", []))
        fresh = [x for x in sw if (w := re.match(r"press the secret switch at \((\d+),(\d+)\)", x.label))
                 and f"{o.map}:{w[1]},{w[2]}#{doors}" not in tried]
        if fresh:
            return fresh                                  # (Jev picked the stairs among them: one kind at a time)
        return sw + [x for x in opts if x not in sw and not (x.label.startswith("walk ") and x.label.endswith(" tiles"))]

    def puzzle_pending(self, targets: list[str]) -> bool:
        """One of the objective's maps has secret switches (S) and a warp not taken yet."""
        for name in targets:
            mid = map_id(name)
            m = self.nav.data["maps"].get(str(mid)) if mid is not None and isinstance(self.nav, LearnedAtlas) else None
            if m and any("S" in row for row in m.get("cells", [])) and any(
                    not m.get("arrivals", {}).get(f"{w[0]},{w[1]}", {}).get("seen") for w in m.get("warps", [])):
                return True
        return False

    def puzzle_stay(self, o: Obs, opts: list[Option], targets: list[str]) -> list[Option]:
        """On one of the objective's maps while a puzzle is pending there: the stairs to its other floors are offered
        and exploring the way out is not (volcano-leg-7 went in and out of the Mansion's front door ~16 times: with
        1F walked, the untaken door twin outside was the only 'explore' left and the stairs were hidden as revisits)."""
        if not o.pos or not self.puzzle_pending(targets) or o.map == targets[-1]:
            return opts                                   # (the last floor is where the goal is: volcano-leg-10 left B1F)
        cur = map_id(o.map)
        try:
            warps = self.nav.map(cur)["warps"]
            _, trans = self.nav.reach(cur, tuple(o.pos))
        except (KeyError, IndexError, ValueError):
            return opts
        near = {(h.x, h.y) for _, h, _ in trans if h.kind == "warp"}
        arr = self.nav.data["maps"].get(str(cur), {}).get("arrivals", {})
        stairs = []
        changed = set(self.s.get("floor_changed", []))
        for i, (x, y, _, _) in enumerate(warps):
            dests = {D.map_name(d[0]) for d in self.nav.warp_dest(cur, i)}
            # stairs already taken only to a floor a press changed since it was seen (uncapped-1: every stair taken and
            # the way out dropped left "talk to what you are facing", forced ~140 times, while 2F and 3F had changed)
            taken = arr.get(f"{x},{y}", {}).get("seen") and not dests & changed
            if (x, y) not in near or not dests & set(targets) or dests == {o.map} or taken \
                    or self.blocked_here(o, cur, x, y):   # (Codex review 3: puzzle helpers bypassed blocked hops)
                continue                                  # (stairs already taken: volcano-leg-12 went 2F <-> 3F ~70 times)
            walk = self.hop_walk(cur, tuple(o.pos), x, y)
            label = f"take the stairs: walk to the warp at ({x},{y}) → {sorted(dests & set(targets))[0]}"   # (nav_feedback learns it)
            if walk and not any(f"({x},{y})" in z.label and "warp" in z.label for z in opts):
                stairs.append(Option(label, "walk", walk[0], "another floor of the objective's building", then=walk[1]))
        keep = [x for x in opts if not (x.label.startswith("explore the frontier") and not any(t in x.label for t in targets))]
        return (keep + stairs) or opts                    # (never nothing: volcano-leg-17 sent Jev an empty choice)

    def puzzle_order(self, opts: list[Option], targets: list[str], o: Optional[Obs] = None) -> list[Option]:
        """Inside a building whose switches still hide a warp: the first kind of move that exists, in this order:
        untaken warps and item balls here, floor never walked on, a switch, another floor (changed by a switch, or
        stairs not taken yet); Jev picks within it. Volcano-leg experiments 5-13 offered all of them at once and Jev's
        picks among them (stairs just taken at ~0.5, the unwalked floor at ~0.1) broke the sequence the Mansion needs
        (3F's switch, then its collapsed floor, then the hole to 1F's stairs to B1F) for hundreds of steps."""
        if not self.puzzle_pending(targets):
            return opts
        # stairs where a known staircase lands on this floor lead back the way it came, not anywhere new (volcano-leg-20
        # came up 2F's (6,1) into 3F's top left for the first time and went straight back down by 3F's untaken (6,1))
        lands = set()
        if o is not None and isinstance(self.nav, LearnedAtlas) and map_id(o.map) is not None:
            for m in self.nav.data["maps"].values():
                lands |= {(a["x"], a["y"]) for a in m.get("arrivals", {}).values()
                          if a.get("seen") and a.get("map") == map_id(o.map)}
        def back(x: Option) -> bool:
            w = re.search(r"warp at \((\d+),(\d+)\)", x.label)
            return bool(w) and any(abs(int(w[1]) - a) + abs(int(w[2]) - b) <= 1 for a, b in lands)
        here = lambda x: x.label.startswith("explore the frontier") and "(unexplored exits)" not in x.label and not back(x)
        dist = None
        if o is not None and o.pos and map_id(o.map) is not None:
            try:
                dist, _ = self.nav.reach(map_id(o.map), tuple(o.pos))
            except (KeyError, IndexError, ValueError):
                dist = None
        def ball(x: Option) -> bool:                      # one this part of the floor reaches (volcano-leg-15 tried 3F's
            m = re.search(r"at \((\d+),(\d+)\) \(an item ball", x.label)     # ball at (25,5) from the far side ~5 times)
            return bool(m) and (dist is None or any((int(m[1]) + dx, int(m[2]) + dy) in dist for dx, dy in MOVES.values()))
        # a switch only once nothing is left to see in this door state (floor walked is kept per state: trod_key);
        # every switch flips the same doors, so pressing early only undoes the last press (volcano-leg-14 and -19)
        rv = self.s.get("revisit")
        # the cell-by-cell pass waits until both door states had the quick pass (two presses): volcano-leg-23 walked
        # Mansion 1F one cell at a time for ~400 steps with one press made
        early = self.s.get("flips", 0) < 2
        doors = self.s.get("mansion_doors", self.s.get("flips", 0) % 2)
        tried = set(self.s.get("switch_tried", []))
        def fresh_switch(x: Option) -> bool:              # this floor's switch, not pressed yet in this door state
            w = re.match(r"press the secret switch at \((\d+),(\d+)\)", x.label)
            return bool(w) and o is not None and f"{o.map}:{w[1]},{w[2]}#{doors}" not in tried
        # ...unless this floor has floor never walked (uncapped-1: "go back to 2F" was forced on every arrival on 3F's main
        # part, so its collapsed floor, the way to 1F's stairs to B1F, was never walked again)
        unwalked = any(x.label.startswith("explore the unvisited floor") for x in opts)
        # broken floor (":", where holes are) this door state does not reach and no state has walked: this floor's switch
        # before leaving it (uncapped-1: 3F's collapsed floor opens in one state only; its switch was tried in both, so
        # "go back to 2F" came first on every visit in the other state and the doors were never flipped from 3F)
        hidden = False
        if o is not None and dist is not None and map_id(o.map) is not None and o.map.startswith("Pokémon Mansion"):
            try:
                cells = self.nav.map(map_id(o.map))["cells"]
            except (KeyError, IndexError):
                cells = []
            walked = {tuple(c) for k in (f"{o.map}#0", f"{o.map}#1") for c in self.s.get("trod", {}).get(k, [])}
            hidden = any(c == ":" and (x, y) not in dist and (x, y) not in walked
                         for y, row in enumerate(cells) for x, c in enumerate(row))
        kinds = (lambda x: bool(rv) and not unwalked and x.label.startswith(f"go back to {rv}"),   # a revisit begun is finished first
                 # (Codex review 3: "go back to 2F" from B1F went by 1F, where the route to B1F turned it round)
                 lambda x: x.label.startswith("follow the map route"),   # the objective's own route first
                 # (volcano-leg-21 fell through 3F's hole next to 1F's stairs to B1F, and the order had no place for
                 # "follow the map route to Pokémon Mansion B1F": ~150 steps of floor walks around them instead)
                 lambda x: here(x) or ball(x),
                 lambda x: x.label.startswith("explore the unvisited floor"),
                 # once both door states had their quick pass, this floor's own work before going back elsewhere: its
                 # holes, then its switch once per door state (full run 85 left 3F by "go back to 2F" on every arrival
                 # and never pressed 3F's switch: Codex review 12)
                 lambda x: not early and x.label.startswith("explore the untested floor"),
                 lambda x: not early and fresh_switch(x),
                 lambda x: hidden and x.label.startswith("press the secret switch"),
                 lambda x: x.label.startswith(("go back to", "take the stairs")),
                 lambda x: early and x.label.startswith("press the secret switch"),
                 lambda x: x.label.startswith("explore the untested floor"),
                 lambda x: x.label.startswith("press the secret switch"),
                 back,
                 # another floor's exits last: volcano-leg-14 went 1F <-> 2F ~20 times between "go to 1F (unexplored
                 # exits)" on 2F and "go back to 3F" (through 2F) on 1F
                 lambda x: x.label.startswith("explore the frontier"))
        for k in kinds:
            first = [x for x in opts if k(x)]
            if first:
                return first
        return opts

    def puzzle_return(self, o: Obs, opts: list[Option], targets: list[str]) -> list[Option]:
        """Off the objective's maps while one of them has secret switches (S) and an untaken warp: the route back to the
        nearest such map replaces exploring elsewhere (volcano-leg-6 left the Pokémon Mansion for Route 22 with the
        stairs to B1F, 2F's (6,1) stairs and 3F's east stairs all still untaken behind the switch doors)."""
        if not o.pos or not isinstance(self.nav, LearnedAtlas):
            return opts
        cur, best = map_id(o.map), None
        if not self.puzzle_pending(targets):
            return opts
        for name in targets:
            mid = map_id(name)
            m = self.nav.data["maps"].get(str(mid)) if mid is not None else None
            if not m or not any("S" in row for row in m.get("cells", [])):
                continue
            r = self.nav.route(cur, tuple(o.pos), mid, blocked=self.blocked_now(o))
            if r and (best is None or len(r) < len(best[1])):
                best = (name, r)
        if not best:
            return opts
        name, r = best
        walk = self.hop_walk(cur, tuple(o.pos), r[0].x, r[0].y, r[0].side if r[0].kind == "edge" else "")
        if not walk:
            return opts
        back = Option(f"go back to {name}: {r[0].label()}", "walk", walk[0],
                      "its switches open and shut doors; stairs there are still untaken: the way on is there", then=walk[1])
        return [back] + [x for x in opts if not x.label.startswith("explore ")
                         and not (x.label.startswith("walk ") and x.label.endswith(" tiles"))]

    def trod_key(self, name: str) -> str:
        """The floor walked is kept per door state in the Pokémon Mansion: all its switches flip one setting, so the
        parity of the presses tells which doors are open (volcano-leg-19 pressed 1F's and 2F's switches by turns, each
        undoing the other, with every floor "walked" in the other state)."""
        doors = self.s.get("mansion_doors", self.s.get("flips", 0) % 2)
        return f"{name}#{doors}" if name.startswith("Pokémon Mansion") else name

    def learn_trod(self, o: Obs) -> None:
        """Cells the player has stood on, per map (for floor_options)."""
        if o.mode == "overworld" and o.map and o.pos and isinstance(self.nav, LearnedAtlas) and map_id(o.map) is not None:
            here = [o.map, *o.pos]
            if self.s.get("stood") == here:
                self.nav.drop_fall(map_id(o.map), *o.pos)    # on a "hole" a whole step without falling: none there
            self.s["stood"] = here                       # (once is not enough: the reply that steps on one shows it)
        if o.mode == "overworld" and o.map and o.pos:
            if o.map in self.s.get("floor_changed", []):
                self.s["floor_changed"].remove(o.map)     # seen again (the atlas re-reads it on entry)
            if self.s.get("revisit") == o.map:
                self.s.pop("revisit")
            t = self.s.setdefault("trod", {}).setdefault(self.trod_key(o.map), [])
            if list(o.pos) not in t and len(t) < 600:
                t.append(list(o.pos))

    def floor_options(self, o: Obs, opts: list[Option], targets: list[str]) -> list[Option]:
        """On a map the objective names whose last target is still unknown: the nearest reachable floor far (more than
        TROD_RADIUS) from every cell stood on. Some ways on are not warps: Pokémon Mansion 3F's collapsed floor has
        holes that drop to 1F's part with the stairs to B1F, the only way there (pokered PokemonMansion3F.asm); the
        volcano-leg experiments walked the floors' known parts and the stairs for ~450 steps without falling."""
        if not o.pos or not isinstance(self.nav, LearnedAtlas) or not targets:
            return opts
        if any(x.label.startswith("push the boulder") for x in opts):
            # a boulder puzzle on this floor: the pushes first (Codex review 17: full run 90's first steps on Victory
            # Road 3F walked unwalked floor over eight push options, then left); a filled hole is floor to walk after
            return opts
        last = map_id(targets[-1])
        cur = map_id(o.map)
        if last is None or self.nav.known(last) and o.map != targets[-1] and (
                cur is None or self.nav.route(cur, tuple(o.pos), last) is not None):
            # (on the last map itself the goal lies somewhere on its floor; a known last map with no route from here counts
            # as unknown: uncapped-1 left B1F to heal and, B1F known, never searched 3F's collapsed floor again)
            return opts
        try:
            cells = self.nav.map(cur)["cells"]
            dist, _ = self.nav.reach(cur, tuple(o.pos))
        except (KeyError, IndexError, ValueError):
            return opts
        trod = [tuple(t) for t in self.s.get("trod", {}).get(self.trod_key(o.map), [])] + [tuple(o.pos)]
        refused = {tuple(t) for t in self.s.get("floor_refused", {}).get(self.trod_key(o.map), [])}
        floor = [(d, c) for c, d in dist.items() if 0 <= c[1] < len(cells) and 0 <= c[0] < len(cells[c[1]])
                 and cells[c[1]][c[0]] in (".", ",", ":", "X") and c not in refused]
        far = sorted((d, c) for d, c in floor if all(abs(c[0] - t[0]) + abs(c[1] - t[1]) > TROD_RADIUS for t in trod))
        exact = not far
        if exact:
            # then every cell never stepped on: a hole is one cell, and near walked floor is not tested floor (Codex
            # review 3: Mansion 3F's holes to 1F lay two and three cells from cells walked; stepping on one drops you,
            # so a hole is never among the cells walked)
            seen = set(trod)                              # (only broken floor ":": a cell-by-cell walk of whole floors
            far = sorted((d, c) for d, c in floor if c not in seen and cells[c[1]][c[0]] == ":")   # cost ~800 steps)
        out: list = []
        for _, (x, y) in far:
            if all(abs(x - a) + abs(y - b) > 2 * TROD_RADIUS for a, b in out):
                out.append((x, y))
            if len(out) == 2:
                break
        word = "untested" if exact else "unvisited"      # (the cell-by-cell pass is slow: see puzzle_order)
        new = [Option(f"explore the {word} floor at ({x},{y})", "walk", {"path": f"to {x},{y}", "on_battle": "stop"},
                      "part of this floor never walked on: some ways on are not doors (a hole in the floor)") for x, y in out]
        goal_floor = o.map == targets[-1]                 # (B1F works on its own floor: Codex review 3)
        if not new and not goal_floor:
            near = {(h.x, h.y) for _, h, _ in self.nav.reach(cur, tuple(o.pos))[1] if h.kind == "warp"}
            for key in self.s.get("stairs_changed", []):
                k, w = key.split(":")
                x, y = (int(v) for v in w.split(","))
                if int(k) != cur or (x, y) not in near or self.blocked_here(o, cur, x, y):
                    continue
                arr = self.nav.data["maps"][k]["arrivals"][w]
                walk = self.hop_walk(cur, tuple(o.pos), x, y)
                if walk:
                    new.append(Option(f"go back to {D.map_name(arr['map'])} by the warp at ({x},{y})", "walk", walk[0],
                                      "a switch pressed since you last went this way changed the doors over there",
                                      then=walk[1]))
        for name in ([] if new or goal_floor else self.s.get("floor_changed", [])):   # this floor first (volcano-leg-9
            mid = map_id(name)                                       # pressed 3F's switch and left by "go back to 2F")
            if name not in targets or mid is None or mid == cur:
                continue
            r = self.nav.route(cur, tuple(o.pos), mid, blocked=self.blocked_now(o))
            walk = self.hop_walk(cur, tuple(o.pos), r[0].x, r[0].y, r[0].side if r[0].kind == "edge" else "") if r else None
            if walk:
                new.append(Option(f"go back to {name}: {r[0].label()}", "walk", walk[0],
                                  "a switch pressed since you were there changed its doors: parts may be open now",
                                  then=walk[1]))
        if new:                                           # (blind walks only dilute them: ~60 of them on 3F in volcano-leg-5)
            opts = [x for x in opts if not (x.label.startswith("walk ") and x.label.endswith(" tiles"))]
        if any(x.label.startswith(("explore the unvisited floor", "explore the untested floor")) for x in new):
            # warps already taken lead to floors already seen: volcano-leg-8 took the stairs it had just come up by
            # (Jev ~0.5 for them, ~0.1 for the unwalked floor) ~150 times between Mansion 2F and 3F
            arr = self.nav.data["maps"].get(str(cur), {}).get("arrivals", {})
            taken = {k for k, a in arr.items() if a.get("seen")}
            opts = [x for x in opts if not (x.label.startswith(("walk to the warp", "take the stairs")) and any(
                f"({k})" in x.label for k in taken))]
        onward = any(x.label.startswith("explore the frontier") and any(t in x.label for t in targets) for x in opts)
        return opts + new if onward else new + opts

    def boulder_options(self, o: Obs, facts, opts: list[Option]) -> list[Option]:
        """A floor switch (X) with no boulder on it, boulders (B) and Strength: 'push the boulder at .. onto the switch
        at ..' for each pair not refused lately (use Strength, then the server plans and makes the pushes). First: the
        barrier it opens is the way on (plateau-leg experiment: Victory Road 1F's switch, walks back and forth to
        Route 23 for ~700 steps)."""
        if not o.pos or not facts or "Strength" not in facts.moves:
            return opts
        grid = o.grid or {}
        plates = [c for c, ch in grid.items() if ch in ("X", "H")]   # an activated switch is drawn as floor
        stones = [c for c, ch in grid.items() if ch == "B"]
        if not plates or not stones:
            return opts
        tried = self.s.setdefault("push_tried", {}).setdefault(o.map, {})
        out = []
        for sx, sy in plates:
            for bx, by in stones:
                key = f"{bx},{by}>{sx},{sy}"
                if self.s["step"] - tried.get(key, -10**9) <= NAV_BLOCK_STEPS:
                    continue
                where = "into the hole" if grid.get((sx, sy)) == "H" else "onto the switch"
                out.append(Option(f"push the boulder at ({bx},{by}) {where} at ({sx},{sy})", "walk",
                                  {"path": f"push {bx},{by} to {sx},{sy}", "on_battle": "stop"},
                                  "a boulder on the floor switch opens the way on (the push uses Strength)"))
        if not out:
            return opts
        # blind walks, staring at walls and stairs back the way you came only dilute them (plateau-leg-3: ~0.1 for the
        # pushes against walks and Route 23's stairs)
        # the pushes, the objective's own route and people (trainers) only (plateau-leg-5: "walk to outside", named
        # walks and a frontier to another map at 0.2-0.6, the pushes at 0.06)
        keep = [x for x in opts if x.label.startswith(("follow the map route", "talk to the person"))]
        return out + keep

    def puzzle_left(self, mid: int, facts) -> bool:
        """A known map with a floor switch (X) or a hole (H) and a boulder not pushed there lately (boulder_options would
        offer the push on arrival)."""
        if not facts or "Strength" not in facts.moves or not isinstance(self.nav, LearnedAtlas):
            return False
        m = self.nav.data["maps"].get(str(mid)) or {}
        plates = [(x, y) for y, row in enumerate(m.get("cells") or []) for x, ch in enumerate(row) if ch in ("X", "H")]
        tried = self.s.get("push_tried", {}).get(D.map_name(mid), {})
        return any(self.s["step"] - tried.get(f"{b[0]},{b[1]}>{x},{y}", -10**9) > NAV_BLOCK_STEPS
                   for x, y in plates for b in m.get("boulders") or [])

    def remember_push(self, o: Obs, opt: Option, reply: str) -> None:
        """A boulder that cannot go onto that switch (no way, did not move) is not offered for it again for a while."""
        m = re.match(r"push the boulder at \((\d+),(\d+)\) (?:onto the switch|into the hole) at \((\d+),(\d+)\)", opt.label)
        if m and o.map and re.search(r"no way to push|did not move|no boulder at|could not get behind", reply) \
                and not re.search(r"battle started|dialogue appeared|stopped: BATTLE", reply):   # (an interruption is not a no)
            self.s.setdefault("push_tried", {}).setdefault(o.map, {})[f"{m[1]},{m[2]}>{m[3]},{m[4]}"] = self.s["step"]

    def switch_options(self, o: Obs, opts: list[Option]) -> list[Option]:
        """The Pokémon Mansion's secret switches (S in the map view) this part of the floor reaches: stand below, face
        up, examine, answer YES. A press opens some doors and shuts others on every floor (the volcano-leg experiment
        explored the Mansion's open part, never pressed one, and left for Route 23). First when nothing on this floor
        is left to explore or route through, otherwise last."""
        if not o.pos or not o.map.startswith("Pokémon Mansion") or not isinstance(self.nav, LearnedAtlas):
            return opts
        cur = map_id(o.map)
        try:
            cells = self.nav.map(cur)["cells"]
            dist, _ = self.nav.reach(cur, tuple(o.pos))
        except (KeyError, IndexError, ValueError):
            return opts
        out, recent = [], set()
        for y, row in enumerate(cells):
            for x, c in enumerate(row):
                if c != "S" or (x, y + 1) not in dist:
                    continue
                pressed = self.s.get("switches", {}).get(f"{o.map}:{x},{y}", [])
                if pressed and self.s["step"] - pressed[-1] <= SWITCH_REST_STEPS:
                    recent.add((x, y + 1))                 # just pressed: the changed floor first, not a press back
                    continue
                face = ("walk", {"path": "up 1", "on_battle": "stop"})
                at = tuple(o.pos) == (x, y + 1)
                first = face[1] if at else {"path": f"to {x},{y + 1}", "on_battle": "stop"}
                desc = "a statue with a secret switch: pressing it opens some doors and shuts others on every floor; " + \
                    (f"pressed {len(pressed)} time(s), last at step {pressed[-1]}" if pressed else "not pressed yet")
                out.append(Option(f"press the secret switch at ({x},{y}) (from below)", "walk", first, desc,
                                  then=([] if at else [face]) + [("talk", {})]))
        if tuple(o.pos) in recent:                         # "talk to what you are facing" would press it back
            opts = [x for x in opts if x.label != "talk to what you are facing"]
        if not out:
            return opts
        # an untaken warp of this floor the player's part of it cannot reach (Mansion 1F's stairs to B1F after the first
        # press shut them off; volcano-leg-3 went up and down the stairs ~300 steps with the switch offered last)
        m = self.nav.data["maps"].get(str(cur), {})
        shut = [(wx, wy) for wx, wy, *_ in m.get("warps", []) if not m.get("arrivals", {}).get(f"{wx},{wy}", {}).get("seen")
                and not any((wx + dx, wy + dy) in dist for dx, dy in ((0, 0), *MOVES.values()))]
        onward = any(x.label.startswith(("explore the frontier", "follow the map route")) for x in opts)
        if shut:
            return out + [x for x in opts if not (x.label.startswith("walk ") and x.label.endswith(" tiles"))]
        return opts + out if onward else out + opts

    def remember_door(self, o: Obs, opt: Option, reply: str) -> None:
        """A door that did not open (blocked on the way, wrong side) is not offered again for a while."""
        m = re.match(r"open the locked door at \((\d+),(\d+)\)", opt.label)
        # (a walk there cut short by a trainer or a battle is no try: full run 90's approach to Silph Co. 11F's door was
        # stopped by a Rocket, the door was skipped 300 steps and the player shuttled between the 7F and 11F pads)
        interrupted = bool(re.search(r"stopped: (?:dialogue appeared|battle started)", reply))
        if m and o.map and not MAP_CHANGE_RE.search(reply) and not interrupted:
            self.s.setdefault("card_tried", {}).setdefault(o.map, {})[f"{m[1]},{m[2]}"] = self.s["step"]
        elif (o.map or self.s.get("prev_map")) and (MAP_CHANGE_RE.search(reply) or (
                (o.map or self.s.get("prev_map")) in GATE_MAPS and re.search(r"\bdefeated [A-Z]", reply))):
            # the floor changed without a map change: read it again next step (the atlas kept the door as a wall until
            # the player left and came back) and forget the ways that were refused while it was shut (the Game Corner's
            # stairs open with the switch behind the poster: full run 65 had learned them as unreachable)
            name = o.map or self.s.get("prev_map", "")    # (the switch's last line is a dialogue: no status line)
            self.s["reobserve"] = name
            # a Pokémon Mansion switch opens and shuts doors on every floor: all of them are forgotten, walks included
            names = [D.map_name(int(k)) for k in self.nav.data["maps"]] if isinstance(self.nav, LearnedAtlas) else []
            mansion = name.startswith("Pokémon Mansion")
            # one press, once: "Who wouldn't?" is both on the YES reply's screen and in the next talk's summary
            # (Codex review 3: every press flipped the parity twice, so it never changed)
            pressed = mansion and bool(re.search(r"Who wouldn't\?", reply)) and self.s.pop("switch_pending", False)
            if pressed:
                # which switch was pressed in which door state (each is pressed once per state: puzzle_order)
                sa = self.s.pop("switch_at", None)
                if sa:
                    doors = self.s.get("mansion_doors", self.s.get("flips", 0) % 2)
                    self.s.setdefault("switch_tried", [])
                    if f"{sa}#{doors}" not in self.s["switch_tried"]:
                        self.s["switch_tried"].append(f"{sa}#{doors}")
                self.s["flips"] = self.s.get("flips", 0) + 1   # the doors' state (see trod_key)
            if pressed:                                   # the other floors' doors changed too: worth seeing again
                self.s["floor_changed"] = sorted({x for x in names if x.startswith("Pokémon Mansion")} - {name})
                # ...each part of them: every staircase between the floors leads to its own part of the next floor
                # (volcano-leg-16 went to 3F by the nearest stairs, into its small west part, ~15 times, and almost
                # never by 2F's (6,1) to 3F's top left, the part with 3F's own switch)
                stairs = []
                for k, m in self.nav.data["maps"].items():
                    if not D.map_name(int(k)).startswith("Pokémon Mansion"):
                        continue
                    for w, a in m.get("arrivals", {}).items():
                        dest = D.map_name(a.get("map", -1)) if a.get("seen") else ""
                        if dest.startswith("Pokémon Mansion") and dest not in (name, D.map_name(int(k))):
                            stairs.append(f"{k}:{w}")
                self.s["stairs_changed"] = sorted(set(stairs))
            for n in {name} | ({x for x in names if x.startswith("Pokémon Mansion")} if mansion else set()):
                self.s.get("clues", {}).pop(n, None)
                self.s.get("sealed", {}).pop(n, None)
                cur = map_id(n)
                for k in ("nav_noroute", "nav_blocked", "terrain_noroute", "nav_fail_from", "nav_block_from"):
                    for key in [key for key in self.s.get(k, {}) if key.startswith(f"{cur}:")]:
                        del self.s[k][key]
                self.s.get("talk_noroute", {}).pop(n, None)
                if isinstance(self.nav, LearnedAtlas) and cur is not None:
                    self.nav.forget_noroute(cur, walked=mansion)
        if "A secret switch" in reply:
            self.s["switch_pending"] = True               # the YES that follows is one press (see above)
        gb = re.match(r"go back to (Pokémon Mansion \w+)", opt.label)
        if gb:
            self.s["revisit"] = gb[1]                     # kept until reached (see puzzle_order)
        if opt.label.startswith(("train in the tall grass", "train here")) and o.map:
            tp = self.s.setdefault("train_paces", {})
            tp[o.map] = tp.get(o.map, 0) + 1              # (see train_options: no wild Pokémon after 8 is no grass)
        sw = re.match(r"press the secret switch at \((\d+),(\d+)\)", opt.label)
        if sw and o.map:
            self.s.setdefault("switches", {}).setdefault(f"{o.map}:{sw[1]},{sw[2]}", []).append(self.s["step"])
            if "A secret switch" in reply:
                self.s["switch_at"] = f"{o.map}:{sw[1]},{sw[2]}"   # (the YES that follows records it: see above)

    def remember_tree(self, o: Obs, after: Obs, reply: str) -> None:
        """A walk refused by a small tree makes cutting it an option; once a tree is cut, the people this map had no way
        to are offered again (full run 60: Celadon's trees grow back on every visit, so "no way to Erika" was stamped
        each time and still hid her right after the cut; ~2,300 steps in and out of the gym)."""
        tr = re.match(r"no walkable route from \(\d+,\d+\) to \((\d+),(\d+)\).*small tree", after.head)
        if tr and map_id(o.map) is not None:
            self.s["tree_target"] = [map_id(o.map), int(tr[1]), int(tr[2]), self.s["step"]]
        elif "hacked away with CUT" in reply:
            self.s.pop("tree_target", None)
            self.s.get("talk_noroute", {}).pop(o.map, None)

    def remember_talk(self, o: Obs, opt: Option, after: Obs) -> None:
        """What a person or object answered, per map (shown in the next talk options; empty spots are dropped)."""
        clear = re.search(r"first clear the way at \((\d+),(\d+)\)", opt.label)
        if not (o.map and (opt.label.startswith(("talk to", "examine")) or opt.tool == "talk" or clear)):
            return
        # (clearing the way is talking to whoever stands there: full run 84 heard "I'm guarding this poster!" through
        # it, recorded no clue, and left the Game Corner with the poster switch untried)
        person = opt.label.startswith("talk to the person") or bool(clear)
        m = clear or (re.search(r"\((\d+),(\d+)\)", opt.label) if opt.label.startswith(("talk to the person", "examine the object")) else None)
        key = f"{m[1]},{m[2]}" if m else f"facing {o.pos} {o.facing}"
        if m and opt.label.startswith("examine the object"):
            key += " " + opt.label.rsplit(" from ", 1)[-1]     # each side is a different try
        if m and person and \
                re.search(r"could not get closer|— stopped: (?!entered)|^no walkable route", after.head):
            # a walk that did not get there is not what the person said: it read "already talked to it, it said:
            # … could not get closer" and Jev left Misty alone (iteration 37, ~1,900 steps in and out of the gym);
            # "no walkable route" to Lt. Surge behind his locked door did the same after the door opened (run 46)
            if after.head.startswith("no walkable route"):
                self.s.setdefault("talk_noroute", {}).setdefault(o.map, {})[key] = self.s["step"]
                if "item ball" in opt.label or o.map.endswith("Gym"):
                    # an item no way leads to from here: another arrival on this floor may reach it (Silph Co. 5F's
                    # Card Key: beaten Rockets stand in both ends of its corridor, the way in is 9F's warp pad).
                    # Same for a gym's people: Sabrina's rooms are joined only by warp pads (full run 73 stepped on
                    # the same pads ~4,500 steps; the walk to a person never crosses a warp)
                    self.s["spot_goal"] = [o.map, int(m[1]), int(m[2]), self.s["step"],
                                           "ball" if "item ball" in opt.label else "person"]
            return
        if m and person and CLUE_RE.search(after.text) and \
                not MAP_CHANGE_RE.search(after.text):
            # "I'm guarding this poster!": the walls beside where they stand hide something (full run 64 found the
            # Game Corner's switch only by a lucky talk from the guard's spot; run 65 never did)
            self.s.setdefault("clues", {})[o.map] = [int(m[1]), int(m[2])]
        if "No more room for items" in after.head:
            return                                   # the item is still there once the bag has room (run 59: Gold Teeth)
        said = self.s["said"].setdefault(o.map, {})
        if not after.head.startswith("nothing to talk to"):
            # a real conversation: the room may have changed (Bill came out), retry the empty spots
            for k in [k for k, v in said.items() if v.startswith("nothing to talk to") and re.fullmatch(r"\d+,\d+", k)]:
                del said[k]                          # people only: objects do not move
        said[key] = after.head[:80]

    def spot_cells(self, o: Obs, cur: Optional[int], goal: Optional[int]) -> Optional[frozenset]:
        """The cells an item ball the server found no way to can be reached from (people in the way count as walls), while
        the player is on that map, it is still there, and the player is not among those cells: the route then looks for
        an arrival among them, or explores. Reaching them gives the ball back to the talk options."""
        sg = self.s.get("spot_goal")
        if not sg or sg[0] != o.map or cur is None or cur != goal or self.s["step"] - sg[3] > SPOT_STEPS:
            return None
        ball = (sg[1], sg[2])
        here = o.npcs if sg[4:] == ["person"] else o.balls
        if ball not in here and ball in o.grid:
            self.s.pop("spot_goal", None)                 # the view shows its cell without it: taken (or moved away)
            return None
        try:
            dist, _ = self.nav.reach(cur, ball, avoid=frozenset(n for n in o.npcs if n != ball))
        except (KeyError, IndexError, ValueError):
            return None
        cells = frozenset(dist)
        if any((o.pos[0] + dx, o.pos[1] + dy) in cells for dx, dy in ((0, 0), *MOVES.values())):
            self.s.get("talk_noroute", {}).get(o.map, {}).pop(f"{ball[0]},{ball[1]}", None)
            return None
        return cells

    def nav_options(self, o: Obs, targets: list[str], facts, why: str = "") -> tuple[list[Option], str]:
        """The next hop of the shortest route to the objective's last target map, plus one option per warp on this
        map (by coordinates, so a ladder is never confused with another ladder to the same floor)."""
        cur = map_id(o.map) if o.map else None
        if self.nav is None or cur is None or not o.pos:
            return [], ""
        if self.s["nav_at"] != self.s.get("last_progress_step", 0):
            self.s["nav_taken"], self.s["nav_at"] = {}, self.s.get("last_progress_step", 0)
        opts, route_key, skip = [], "", None
        self.route_hint = ""
        self.edge_opts = {}
        self.clear_for = {}
        self.exploring = False
        moves = set(facts.moves) if facts else set()
        surf = "Surf" in moves and (facts.badges if facts else 0) >= 5
        cut = "Cut" in moves and (facts.badges if facts else 0) >= 2
        # healing: the targets list the nearest Poké Center first; otherwise the route ends at the last target
        order = targets if why == "heal" else list(reversed(targets))
        goal = next((map_id(t) for t in order if map_id(t) is not None), None)
        if why == "heal":
            # the nearest Poké Center the map knowledge can reach (the town's own can be behind a ledge), searched like
            # the walk there: Surf and Cut (full run 90: every way back from Victory Road crosses Route 23's water) and
            # the hops blocked lately (Codex review 17: a blocked nearest one was chosen and no route came of it)
            blocked_heal, best = self.blocked_now(o), None
            for t in targets:
                mid = map_id(t)
                r = self.route_ok(cur, tuple(o.pos), mid, surf=surf, cut=cut, taken=self.s["nav_taken"],
                                  blocked=blocked_heal) if mid is not None else None
                if r is not None and (best is None or len(r) < best[0]):
                    best = (len(r), mid)
            goal = best[1] if best else goal
            # no Poké Center the map knowledge reaches from here: the director may carry on when the team can (full run 88
            # went up and down Victory Road's ladders at 57-66% HP with the heal objective and no way out from there)
            if best is None:
                self.s["heal_noroute_step"] = self.s["step"]
        if why == "heal" and len(targets) == 1 and goal != cur and goal is not None and \
                self.nav.route(cur, tuple(o.pos), goal, surf=surf, cut=cut) is None and "once" in (self.s.get("last_objective") or ""):
            # the one-off "use this town's Poké Center" visit has no known way there (Route 4's is behind a ledge)
            self.s.setdefault("pc_unreachable", []).append(targets[0])
        # a map that counts only when entered from one other map (Silph Co. 11F from 7F's warp pad): standing on it
        # after arriving some other way is not being there
        rule = self.director.entry_rule(facts) if self.director and facts else {}
        self.s["entry_rule"] = rule                      # the elevator panel reads it (no facts on a prompt)
        entry = {map_id(m): map_id(src) for m, src in rule.items() if map_id(m) is not None and map_id(src) is not None}
        if goal == cur and goal in entry and self.s.get("came_from") == D.map_name(entry[goal]):
            entry = {}
        self.entry_pending = goal in entry
        sl = self.s.get("sleeper", {}).get(o.map)
        if sl and facts and facts.has("Poké Flute"):
            self.s["spot_goal"] = [o.map, sl[0], sl[1], self.s["step"], "person"]   # the route goes to its side
        cells = self.spot_cells(o, cur, goal)
        if cells is not None:
            self.entry_pending = True
        # the Pokémon Tower's top floor is walled off by the ghost Marowak until the Silph Scope: exploring towards it
        # only replays an unwinnable battle (full run 53, ~2,000 steps on 6F)
        closed = {"Pokémon Tower 7F"} if not (facts and facts.has("Silph Scope")) else set()
        tt = self.s.get("tree_target")
        if cut and tt and tt[0] == cur and self.s["step"] - tt[3] <= NAV_BLOCK_STEPS:
            # a walk on this map (to a person, a warp, a cell) was refused because of a small tree: cut it first
            # (full run 44: Erika sits behind the Celadon Gym's trees; 1,250 steps in and out of the gym)
            c = self.cut_option(cur, o, Hop(cur, "cell", tt[1], tt[2], cur), f"to reach ({tt[1]},{tt[2]})",
                                "the server found no way there", surf)
            if c:
                opts.append(c)
        if goal is not None and (goal != cur or self.entry_pending):
            blocked = self.blocked_now(o)
            route = self.route_ok(cur, tuple(o.pos), goal, surf=surf, cut=cut, taken=self.s["nav_taken"], blocked=blocked,
                                  entry=entry, goal_cells=cells)
            if route and self.loops_back(cur, route):
                # the route leaves this map and comes back to "somewhere on it" through arrivals not known yet: it only
                # says this part of the map does not reach the goal (full run 81: from Route 15's east part to Fuchsia
                # round by Route 14, 13, 12, Lavender and Route 8, while Route 15's own gate was the way on)
                route = []
            mark = self.s.setdefault("node_mark", {})
            if why not in ("heal", "train") and why not in mark:
                mark[why] = len(self.s["visited"])           # the maps visited before this objective began
            # a map first reached during this objective that the objective does not name (Route 14 on the way to
            # Fuchsia): nothing tells what lies past it, so the frontier works there
            new_here = o.map in self.s["visited"][mark.get(why, len(self.s["visited"])):] and o.map not in targets
            if not route and isinstance(self.nav, LearnedAtlas) and why not in ("heal", "train") and cells is None \
                    and not new_here:
                # the last map is not known yet: the route goes to the furthest map of the objective the atlas knows,
                # past this one, and explores from there (full run 68 blacked out on Pokémon Tower 3F, woke in Celadon,
                # and explored Celadon's and Route 16's exits for ~8,500 steps with the way to Lavender in the atlas).
                # Not from a map first reached during this objective outside its targets: that is the frontier at
                # work (full run 70 was sent from the new Route 14 back to Route 13). On one of its targets it is
                # (full run 71: with the Card Key, 11F needs 7F's warp pad; after a black-out Saffron City and Silph
                # Co. 1F, both new to the objective, had no route and no exit left, ~2,500 steps in Saffron)
                here = targets.index(o.map) if o.map in targets else -1
                for t in reversed(targets[here + 1:]):
                    mid = map_id(t)
                    if mid is None or mid == goal or mid == cur or mid in entry:
                        continue
                    found = self.route_ok(cur, tuple(o.pos), mid, surf=surf, cut=cut, taken=self.s["nav_taken"],
                                           blocked=blocked, entry=entry, arrival=True)
                    # only where something is left to explore from the arrival (full run 69: Route 2's south part has
                    # no untaken exit, its frontier sent the player back to Viridian City, this rule back to Route 2,
                    # ~11,000 steps)
                    try:
                        # (a target map with a clue not followed yet is somewhere to go too: the Game Corner's poster)
                        # (and one with a boulder puzzle left: full run 90, back on Route 23 after a black-out, had all
                        # of Victory Road explored but 3F's hole and 2F's second switch, and explored towards the Mansion)
                        open_ = bool(found and found[0]) and (found[1][1] < 0 or t in self.s.get("clues", {}) or
                                                              self.puzzle_left(mid, facts) or bool([
                            h for h in self.nav.frontier(mid, (found[1][1], found[1][2]), set(self.s["visited"]),
                                                         surf=surf, cut=cut, blocked=blocked) if h.dest_name not in closed]))
                    except (KeyError, IndexError, ValueError):
                        open_ = False
                    if open_ and not self.loops_back(cur, found[0]):
                        route, goal = found[0], mid
                        break
            if route:
                h = route[0]
                args, then = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side if h.kind == "edge" else "") or \
                    ({"path": f"to {h.x},{h.y}", "on_battle": "stop"}, [])
                via = " → ".join(x.dest_name for x in route)
                route_key = f"{h.map}:{h.x},{h.y}"       # the key format WorldNav.route checks in `blocked`
                desc = f"next hop of the shortest route in the game's map data: {via} ({len(route)} hops)"
                self.route_hint = f"to reach {D.map_name(goal)}: {h.label()} on this map, then {via}"
                clear = self.clear_option(cur, o, h, f"follow the map route to {D.map_name(goal)}", desc, surf, cut)
                if clear:
                    opts.insert(0, clear)
                    skip = (h.x, h.y)                      # walking straight there fails until the way is clear
                if skip is None:
                    opts.insert(0, Option(f"follow the map route to {D.map_name(goal)}: {h.label()}", "walk", args, desc, then=then))
                if h.kind == "edge" and skip is None:
                    self.edge_opts[opts[0].label] = (h.side, h.x, h.y)
        if isinstance(self.nav, LearnedAtlas) and not route_key and (goal != cur or self.entry_pending):
            # (on the objective's map, entered the right way: nothing to explore)
            # the objective's map is not in the atlas (or not reachable through it yet): explore frontier-first
            blocked = self.blocked_now(o)
            front = [h for h in self.nav.frontier(cur, tuple(o.pos), set(self.s["visited"]), surf=surf, cut=cut,
                                                  blocked=blocked, prefer=tuple(targets)) if h.dest_name not in closed]
            pending = [h for h in front if self.s["step"] - self.s["nav_noroute"].get(f"{h.map}:{h.x},{h.y}", -10**9)
                       <= NAV_BLOCK_STEPS]          # a hop waiting for its way to be cleared goes first
            for h in (pending[:1] + [x for x in front if x not in pending[:1]])[:3]:
                walk = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side if h.kind == "edge" else "")
                if not walk:
                    continue
                what = (f"cross the {h.side} edge → {h.dest_name} (never crossed)" if h.kind == "edge"
                        else f"walk to the untaken warp at ({h.x},{h.y}) → {h.dest_name}")
                label = f"explore the frontier: {what}"
                desc = "the atlas does not know the way to the objective yet: unexplored warps and edges (never-visited maps first) find it"
                clear = self.clear_option(cur, o, h, "explore the frontier", desc, surf, cut)
                if clear:
                    opts.insert(0, clear)
                    skip = (h.x, h.y)
                    self.exploring = True
                    continue
                opts.insert(0, Option(label, "walk", walk[0], desc, then=walk[1]))
                self.exploring = True
                if h.kind == "edge":
                    self.edge_opts[label] = (h.side, h.x, h.y)
            if not front:
                # nothing unexplored here: the map route to the nearest known map that still has unexplored exits
                best, visited = None, set(self.s["visited"])
                for mid in frontier_maps(self.nav, visited):
                    if mid == cur:
                        continue
                    found = self.route_ok(cur, tuple(o.pos), mid, surf=surf, cut=cut, blocked=blocked, arrival=True)
                    if not found or not found[0]:
                        continue
                    r, arr = found
                    if self.loops_back(cur, r):                   # (the same rule as the objective's route: Codex 9)
                        continue
                    # only where the unexplored exits can be reached from the arrival point (bills-house iteration 32:
                    # Route 4's exits lie beyond its one-way ledge, and Jev crossed to it and back ~400 times)
                    try:
                        if arr[1] >= 0 and not [h for h in self.nav.frontier(mid, (arr[1], arr[2]), visited, surf=surf,
                                                                             cut=cut, blocked=blocked)
                                                if h.dest_name not in closed]:
                            continue
                    except (KeyError, IndexError, ValueError):
                        continue
                    key = (len(r), sum(h.steps for h in r))
                    if best is None or key < best[2]:
                        best = (mid, r, key)
                if best:
                    h = best[1][0]
                    walk = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side if h.kind == "edge" else "")
                    if walk:
                        opts.insert(0, Option(f"explore the frontier: go to {D.map_name(best[0])} (unexplored exits): {h.label()}",
                                              "walk", walk[0], "nothing is left to explore on this map; that map still has "
                                              "exits never taken", then=walk[1]))
                        self.exploring = True
                        if h.kind == "edge":
                            self.edge_opts[opts[0].label] = (h.side, h.x, h.y)
        visited = set(self.s["visited"])
        _, trans = self.nav.reach(cur, tuple(o.pos), surf=surf, cut=cut)
        near = {(h.x, h.y) for _, h, _ in trans if h.kind == "warp"}   # warps this section of the map can reach
        sides: dict = {}
        for steps, h, _ in trans:                         # edges this section reaches: the nearest cell per side
            if h.kind == "edge" and h.x >= 0 and not self.blocked_here(o, cur, h.x, h.y) and \
                    (h.side not in sides or steps < sides[h.side][0]):
                sides[h.side] = (steps, h)
        for _, h in sides.values():
            walk = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side)
            label = f"walk to {h.dest_name} ({h.side} edge)"
            if walk and not any(x.label == label for x in opts):
                opts.append(Option(label, "walk", walk[0], f"leave this map by its {h.side} edge", then=walk[1]))
                self.edge_opts[label] = (h.side, h.x, h.y)
        for i, (x, y, _, _) in enumerate(self.nav.map(cur)["warps"]):
            if (x, y) not in near or (x, y) == skip or self.blocked_here(o, cur, x, y):
                continue                                  # (a blocked warp too, like the edges: the locked Cinnabar Gym)
            dests = {D.map_name(d[0]) for d in self.nav.warp_dest(cur, i)}
            if dests & closed:
                continue
            name = dests.pop() if len(dests) == 1 else "outside"
            new = "" if name in visited else " (not visited yet)"
            walk = self.hop_walk(cur, tuple(o.pos), x, y)
            if not walk:
                continue
            if self.exploring and self.s.get("recovery", 0) < 3 and isinstance(self.nav, LearnedAtlas) and \
                    self.nav.map(cur)["arrivals"].get(f"{x},{y}", {}).get("seen"):
                continue                                  # exploring: warps already taken only dilute the frontier
            here = " (you stand on it: step off and back on)" if (x, y) == tuple(o.pos) else ""
            opts.append(Option(f"walk to the warp at ({x},{y}) → {name}{new}{here}", "walk", walk[0],
                               "this particular door, ladder or stairway", then=walk[1]))
        if self.exploring and isinstance(self.nav, LearnedAtlas):
            # exploring is all that is left: plain ways back to maps already explored, and plain copies of explore
            # options, only dilute the choice (bills-house iterations 32-33: Jev took Route 4 / Route 24 crossings at
            # 0.36 and 0.14 over the robbed house's frontier at 0.03, ~440 times each way)
            spots = {(int(m[1]), int(m[2])) for x in opts if x.label.startswith("explore the frontier")
                      for m in [re.search(r"warp at \((\d+),(\d+)\)", x.label)] if m}
            def revisit(x: Option) -> bool:
                if x.label.startswith(("explore the frontier", "follow the map route", "first clear the way")):
                    return False
                m = re.search(r"warp at \((\d+),(\d+)\)", x.label)
                if m and x.label.startswith("walk to the warp"):
                    return (int(m[1]), int(m[2])) in spots or "(not visited yet)" not in x.label
                e = self.edge_opts.get(x.label)
                return bool(e) and x.label.startswith("walk to ") and x.label.split(" (")[0][8:] in visited
            if any(x.label.startswith("explore the frontier") for x in opts):
                opts = [x for x in opts if not revisit(x)]
        return opts, route_key

    def object_options(self, o: Obs) -> list[Option]:
        """Small indoor room: the solid cells below the top wall that touch the floor are furniture, machines or a
        PC (the map view shows them as walls). Offer to examine them, untried first."""
        cur = map_id(o.map) if o.map else None
        if self.nav is None or cur is None or not o.pos:
            return []
        try:
            cells = self.nav.map(cur)["cells"]
        except (KeyError, IndexError):
            return []
        h, w = len(cells), len(cells[0]) if cells else 0
        if h > 20 or w > 20:
            return []
        top = 0
        while top < h and all(c == "#" for c in cells[top]):
            top += 1
        # the side and bottom borders are walls, not objects (the Rocket Hideout Elevator's view has them: 14 wall cells
        # touched the floor, over the cap, and its panel at (1,1) was never offered; full run 52, ~3,000 steps)
        objs = [(x, y) for y in range(top, h - 1) for x in range(1, w - 1) if cells[y][x] == "#" and any(
            0 <= x + dx < w and 0 <= y + dy < h and cells[y + dy][x + dx] in (".", ",", ":", "X") for dx, dy in MOVES.values())]
        # (a roof's vending machines sit among many solid cells: Celadon Mart Roof has 26, over the cap, and no option
        # was offered; full run 71 spent 274 decisions on it: Codex review 10)
        if not objs or len(objs) > (40 if o.map.endswith(" Roof") else 12):
            return []
        said = self.s["said"].get(o.map, {})
        px, py = o.pos
        sides = (("below", (0, 1), "up"), ("left", (-1, 0), "right"), ("right", (1, 0), "left"), ("above", (0, -1), "down"))
        cands = []
        for x, y in objs:                                  # machines and PCs are used from below first
            for rank, (side, (dx, dy), face) in enumerate(sides):
                sx, sy = x + dx, y + dy
                if not (0 <= sx < w and 0 <= sy < h) or cells[sy][sx] not in (".", ",", ":", "X"):
                    continue
                key = f"{x},{y} {side}"
                first = ({"path": f"{face} 1", "on_battle": "stop"} if (sx, sy) == (px, py)
                         else {"path": f"to {sx},{sy}", "on_battle": "stop"})
                then = ([("walk", {"path": f"{face} 1", "on_battle": "stop"})] if (sx, sy) != (px, py) else []) + [("talk", {})]
                before = said.get(key)
                cands.append(((key in said, rank, abs(sx - px) + abs(sy - py)), Option(
                    f"examine the object at ({x},{y}) from {side}", "walk", first,
                    f"stand {side} it, face it and press A; " + (f"tried before: {before}" if before else "not tried yet"),
                    then=then)))
        return [o_ for _, o_ in sorted(cands, key=lambda c: c[0])[:8]]

    def train_options(self, o: Obs, facts) -> list[Option]:
        """Training: walk into the nearest reachable tall grass and pace there (wild battles come from grass); with no
        grass here, the map route to the nearest visited map that has some."""
        cur = map_id(o.map) if o.map else None
        if cur is None or not o.pos:
            return []
        # walking only: training walks are plain hops that never surf or cut, so grass across water is out of reach
        # (b39ac2c planned with Surf; league-leg-6 then walked at Route 23's water again and again: Codex review 7)
        caps: dict = {}
        try:
            m = self.nav.map(cur)
            dist, _ = self.nav.reach(cur, tuple(o.pos), **caps)
        except (KeyError, IndexError):
            return []
        cells = m["cells"]
        # the Safari Zone's battles give no experience (balls and bait only): full run 76 trained there ~2,000 steps
        safari = lambda name: name.startswith("Safari Zone")
        # in reach and with a cell pair to pace on, whatever its wild Pokémon: out of reach means only that (Codex review
        # 18: weak grass was marked out of reach, then left out of the last-resort strongest-wilds fallback as well; a lone
        # grass cell in reach was never marked, and two maps could take turns as the target)
        spot = None
        for d, (gx, gy) in sorted((d, c) for c, d in dist.items() if cells[c[1]][c[0]] == ",")[:40]:
            for name, (dx, dy) in MOVES.items():
                nb = (gx + dx, gy + dy)
                if nb in dist and cells[nb[1]][nb[0]] == "," and self.pace_ok(cur, cells, (gx, gy)) and \
                        self.pace_ok(cur, cells, nb):
                    spot = (gx, gy, name)
                    break
            if spot:
                break
        no_grass = self.s.setdefault("no_grass", [])
        if not spot and any("," in "".join(r) for r in cells) and o.map not in no_grass:
            no_grass.append(o.map)                       # its grass is out of reach from where you arrive
        elif spot and o.map in no_grass:
            no_grass.remove(o.map)                       # arrived on the grass's side (Route 12 by its south gate)
        best = self.strong_wilds(o, cur, safari, caps)
        if best:
            return best
        top = max((p["level"] for p in self.party), default=0)
        lv = self.s.get("wild_levels", {})
        paced = self.s.get("train_paces", {})
        # met there and not worth it, or paced there with no wild Pokémon at all (Pallet Town's two cells of Route 1's
        # grass: league-leg-4 paced there and back to Route 1): try grass not met yet
        weak = lambda name: (name in lv and lv[name] * 2 < top) or (name not in lv and paced.get(name, 0) >= 8)
        if spot and not safari(o.map) and not weak(o.map):
            gx, gy, name = spot
            back = {"up": "down", "down": "up", "left": "right", "right": "left"}[name]
            pace = [("walk", {"path": f"{name} 1", "on_battle": "stop"}), ("walk", {"path": f"{back} 1", "on_battle": "stop"})] * 4
            first = {"path": f"to {gx},{gy}", "on_battle": "stop"} if (gx, gy) != tuple(o.pos) else pace[0][1]
            return [Option(f"train in the tall grass at ({gx},{gy})", "walk", first,
                           "pace back and forth in tall grass until a wild Pokémon appears, then fight it",
                           then=pace if (gx, gy) != tuple(o.pos) else pace[1:])]
        best = None
        # hops that keep failing are left out, as for the objective's route (full run 76 trained by walking to Route 9's
        # grass through Rock Tunnel: B1F's far ladder had no walkable route from the arrival, ~400 steps up and down)
        blocked = self.blocked_now(o)
        for name in self.s["visited"]:
            mid = map_id(name)
            if mid is None or mid == cur or name in no_grass or safari(name) or weak(name):
                continue
            try:
                if not any("," in "".join(r) for r in self.nav.map(mid)["cells"]):
                    continue
            except (KeyError, IndexError):
                continue
            r = self.route_ok(cur, tuple(o.pos), mid, blocked=blocked, **caps)
            if r and self.loops_back(cur, r):
                r = None
            if r and (best is None or len(r) < len(best[1])):
                best = (name, r)
        if best:
            h = best[1][0]
            walk = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side if h.kind == "edge" else "")
            if walk:
                return [Option(f"follow the map route to the tall grass on {best[0]}: {h.label()}", "walk", walk[0],
                               "no tall grass on this map: the nearest visited map with grass to train in", then=walk[1])]
        # every grass known is below half the best level: the strongest met so far still beats wandering (Codex review 5)
        return self.strong_wilds(o, cur, safari, caps, ratio=0)

    def pace_ok(self, cur: int, cells, c: tuple[int, int]) -> bool:
        """A pacing cell is not on a warp, next to one or on the map's border: pacing there leaves the map (league-leg-6
        "trained" at the Power Plant's entrance (4,35) and walked out to Route 10 each time: Codex review 7)."""
        x, y = c
        if y <= 0 or x <= 0 or y >= len(cells) - 1 or x >= len(cells[y]) - 1:
            return False
        try:
            warps = self.nav.map(cur).get("warps", [])
        except (KeyError, IndexError):
            warps = []
        return not any(abs(w[0] - x) + abs(w[1] - y) <= 1 for w in warps)

    def strong_wilds(self, o: Obs, cur: int, safari, caps: Optional[dict] = None, ratio: float = 0.5) -> list[Option]:
        """Train where the wild Pokémon are strongest of those met (league-leg-2 trained Charizard L73 on Route 1's L3
        Rattata after losing to Lorelei): pace there, in grass if it has any (caves have encounters anywhere), or the
        map route there. Only once a map's wild Pokémon are worth it (at least half the strongest party level)."""
        # nor where the grass is out of reach from where you arrive (the full benchmark: Lavender routed to Route 12's L30
        # wilds beyond its gate, Route 12 then to Route 10's grass through Lavender, ~1,000 steps to the call cap)
        no_grass = self.s.setdefault("no_grass", [])
        lv = {n: v for n, v in self.s.get("wild_levels", {}).items()
              if not safari(n) and map_id(n) is not None and n not in no_grass}
        top = max((p["level"] for p in self.party), default=0)
        caps = caps or {}
        # the spot chosen stays good past the cut while training goes on (Codex review 18: Tower 6F's L30 fell under it at
        # L61 while the director wanted L62, and the search for grass started over)
        # (unless a stronger one is known: Codex review 19, a L25 kept Viridian Forest's L6 while Mt. Moon's L11 was known)
        kept = self.s.get("train_spot")
        if kept not in lv or lv[kept] < max(lv.values(), default=0):
            kept = None
        good = sorted((v, n) for n, v in lv.items() if (v >= top * ratio or n == kept) and v > 0)
        if not good:
            return []
        blocked = self.blocked_now(o)
        for v, name in reversed(good):
            mid = map_id(name)
            if mid == cur:
                try:
                    cells = self.nav.map(cur)["cells"]
                    dist, _ = self.nav.reach(cur, tuple(o.pos), **caps)
                except (KeyError, IndexError):
                    return []
                grassy = any("," in row for row in cells)     # (cells are rows of characters: Codex review 5's crash)
                ok = (",",) if grassy else (".", ",", ":")
                spot = sorted((d, c) for c, d in dist.items() if cells[c[1]][c[0]] in ok)
                if grassy and not spot:
                    if o.map not in no_grass:
                        no_grass.append(o.map)
                    continue                                  # out of reach from here: the next strongest
                for _, (gx, gy) in spot[:40]:
                    for d, (dx, dy) in MOVES.items():
                        nb = (gx + dx, gy + dy)
                        if nb in dist and cells[nb[1]][nb[0]] in ok and self.pace_ok(cur, cells, (gx, gy)) and \
                                self.pace_ok(cur, cells, nb):            # both ends of the pacing in grass, off exits
                            back = {"up": "down", "down": "up", "left": "right", "right": "left"}[d]
                            pace = [("walk", {"path": f"{d} 1", "on_battle": "stop"}), ("walk", {"path": f"{back} 1", "on_battle": "stop"})] * 4
                            first = {"path": f"to {gx},{gy}", "on_battle": "stop"} if (gx, gy) != tuple(o.pos) else pace[0][1]
                            self.s["train_spot"] = name
                            return [Option(f"train here at ({gx},{gy}) (wild Pokémon up to L{v})", "walk", first,
                                           "pace back and forth until a wild Pokémon appears, then fight it",
                                           then=pace if (gx, gy) != tuple(o.pos) else pace[1:])]
                continue
            r = self.route_ok(cur, tuple(o.pos), mid, blocked=blocked, **caps)
            r = None if r and self.loops_back(cur, r) else r
            walk = self.hop_walk(cur, tuple(o.pos), r[0].x, r[0].y, r[0].side if r[0].kind == "edge" else "") if r else None
            if walk:
                self.s["train_spot"] = name
                return [Option(f"follow the map route to train on {name} (wild Pokémon up to L{v}): {r[0].label()}", "walk",
                               walk[0], "the strongest wild Pokémon met so far", then=walk[1])]
        return []

    def learn_walked(self, o: Obs) -> None:
        """Learned atlas: consecutive overworld positions on the same map (a walk, or one cut short by a battle) are in
        the same walkable section; "no walkable route" records only apply within a section (LearnedAtlas.unreachable)."""
        if not isinstance(self.nav, LearnedAtlas) or not o.map or not o.pos or map_id(o.map) is None:
            return
        last, self.s["last_ow"] = self.s.get("last_ow"), [o.map, o.pos[0], o.pos[1], self.s["step"]]
        if last and last[0] != o.map and str(last[0]).startswith("Pokémon Mansion") and o.map.startswith("Pokémon Mansion") \
                and not re.search(r"\b(?:up|down|left|right) \d+/\d+|loaded state|blacked out", o.head) \
                and self.s["step"] - last[3] <= 12:
            # dropped to another floor with no walk in this reply: a hole stepped on before a battle (volcano-leg-26 fell
            # from 3F's (17,14) after the battle that cell started)
            self.record_fall(map_id(last[0]), (last[1], last[2]), o)
        # not across a warp pad on the same map, a spinner, a reload or a black-out: those do not join the parts of a
        # map (Codex review 8: two of the Saffron Gym's rooms became linked after a pad trip)
        report = re.findall(r"\b(?:up|down|left|right) (\d+)/\d+", o.head)   # (a reply after a chain of walks has none)
        steps = sum(int(n) for n in report)
        jumped = bool(report) and last and abs(o.pos[0] - last[1]) + abs(o.pos[1] - last[2]) > 2 * steps + 1   # (ledges: 2)
        moved = jumped or re.search(r"\bentered\b|\bslid\b|loaded state|blacked out", o.head, re.I) or \
            self.pad_landing(map_id(o.map), tuple(o.pos))
        if last and last[0] == o.map and self.s["step"] - last[3] <= 40 and not moved:
            self.nav.record_walk(map_id(o.map), (last[1], last[2]), tuple(o.pos))

    def record_fall(self, mid: Optional[int], cell: tuple, after: Obs) -> None:
        """A drop from `cell` of map mid to where `after` stands, learned as a one-way hop (not a warp: none is there)."""
        if mid is None or not isinstance(self.nav, LearnedAtlas) or map_id(after.map) is None:
            return
        try:
            if any(abs(w[0] - cell[0]) + abs(w[1] - cell[1]) <= 1 for w in self.nav.map(mid)["warps"]):
                return                                    # stairs, not a hole
        except (KeyError, IndexError):
            return
        self.nav.record_fall(mid, cell[0], cell[1], map_id(after.map), *after.pos)

    def pad_landing(self, mid: int, pos: tuple) -> bool:
        """Whether `pos` is where (or next to where) a warp pad of this map lands on this same map: a walk ending there
        may have been teleported, however few cells apart (Codex review 9: run 75's step 9,655, right 4/4 and six cells
        between the Saffron Gym's rooms)."""
        try:
            m = self.nav.map(mid)
            for i, (_, _, _, dm) in enumerate(m["warps"]):
                if dm != mid:
                    continue
                for d in self.nav.warp_dest(mid, i):
                    if d[0] == mid and d[1] >= 0 and abs(d[1] - pos[0]) + abs(d[2] - pos[1]) <= 1:
                        return True
        except (KeyError, IndexError, ValueError):
            pass
        return False

    def can_clear(self, move: str, hm: str) -> bool:
        """The party knows `move`, or holds its HM and has a member that has not refused it yet (a teach is still to
        come). Holding the HM with every member refused is no way through (Codex review 14: run 87 carried HM03, Charizard
        refused Surf at 6,288, and the refusals across water went on being excused)."""
        if any(m["name"] == move for p in self.party for m in p.get("moves", [])):
            return True
        if not any(n == hm for n, _ in self.items):
            return False
        refused = set(self.s.get("hm_no", []))
        return any(f"{hm}:{p['species']}" not in refused for p in self.party) if self.party else True

    def sleeper_gone(self, o: Obs, after: Obs) -> None:
        """A Snorlax woken (or beaten, or caught; the reply comes from a battle or its dialogue) on the map the player is
        on: its goal ends; another map's Snorlax keeps its own (Codex review 7)."""
        here = after.map or o.map or (self.s.get("last_ow") or [""])[0]
        if here in self.s.get("sleeper", {}) and SOLO_STORY_RE["snorlax"].search(after.head + "\n" + after.text):
            self.s["sleeper"].pop(here)
            self.atlas_sleepers(here)
            if (self.s.get("spot_goal") or [""])[0] == here:
                self.s.pop("spot_goal")

    def route_ok(self, cur: int, pos: tuple, goal: int, **kw):
        """`nav.route`, but a route that loops back through an unknown arrival is searched again without the hop that
        makes the loop (full run 86: from Route 12's south part to Lavender the cheapest route went by Route 11 and back
        to "somewhere on Route 12", and was dropped; the real one, north through Route 12's gate, was never looked at)."""
        blocked = kw.pop("blocked", frozenset())
        for _ in range(4):
            r = self.nav.route(cur, pos, goal, blocked=blocked, **kw)
            hops = r[0] if kw.get("arrival") and r else r
            if not hops or not self.loops_back(cur, hops):
                return r
            seen, bad = {cur}, None
            for i, h in enumerate(hops):
                if i and h.map in seen and (h.x < 0 or not self.nav.arrival_known(hops[i - 1])):
                    bad = hops[i - 1]
                    break
                seen.add(h.map)
            if bad is None:
                return None
            key = f"{bad.map}:{bad.x},{bad.y}"
            blocked = ScopedBlocks(set(blocked) | {key}, getattr(blocked, "origins", {}), getattr(blocked, "linked", None))
        return None

    def loops_back(self, cur: int, route: list) -> bool:
        """A route that comes back to this map at a point the atlas does not know (then a warp or an edge from there):
        it only says this part of the map does not reach the goal (a601d76; Codex review 8: a warp after the unknown
        arrival was missed)."""
        if not isinstance(self.nav, LearnedAtlas):
            return False
        seen = {cur}                                      # any map the route was already on, not only this one (full
        for i, h in enumerate(route):                     # run 82: from the Underground Path's building out to Route 5,
            if i and h.map in seen and (h.x < 0 or not self.nav.arrival_known(route[i - 1])):   # through Route 5's gate
                return True                               # and back to "somewhere on Route 5"; the building and Route 5
            seen.add(h.map)                               # sent the player to each other ~600 steps)
        return False

    def atlas_sleepers(self, name: str) -> None:
        """The atlas keeps where a sleeping Snorlax lies on this map as a wall (see LearnedAtlas.reach)."""
        mid = map_id(name)
        if isinstance(self.nav, LearnedAtlas) and mid is not None and str(mid) in self.nav.data["maps"]:
            sl = self.s.get("sleeper", {}).get(name)
            self.nav.data["maps"][str(mid)]["sleepers"] = [sl] if sl else []
            self.nav._maps.pop(mid, None)
            self.nav.dirty = True

    def boulders(self, cur: int, o: Obs) -> set:
        """Boulders on this map: in the current view, else where the last view of it showed them (a status-only reply
        has no view, and the atlas keeps boulders as floor: Codex review 7 had a refusal there learned as a lasting wall)."""
        seen = self.s.setdefault("boulders", {})
        if o.grid and o.map:
            # like the item balls: a view replaces only the boulders in the cells it covers (an action reply's window is
            # 10x9; Codex review 8: a window without the boulder dropped one remembered elsewhere)
            kept = [c for c in seen.get(o.map, []) if tuple(c) not in o.grid]
            seen[o.map] = sorted(kept + [[c[0], c[1]] for c, ch in o.grid.items() if ch == "B"])
            m = self.nav.data["maps"].get(str(cur)) if isinstance(self.nav, LearnedAtlas) and cur is not None else None
            if m is not None and m.get("boulders") != seen[o.map]:
                m["boulders"] = seen[o.map]               # (the atlas routes around them: see LearnedAtlas.reach)
                self.nav.dirty = True
        return {tuple(c) for c in seen.get(o.map or "", [])}

    def learn_noroute(self, o: Obs) -> None:
        """Learned atlas: a refusal with nobody on the path is a wall the map view does not show (cave elevation);
        with someone or something on it, it is a blocker to clear, not a wall."""
        pend = self.s.pop("pending_noroute", None)
        if not pend or not isinstance(self.nav, LearnedAtlas):
            return
        for p in pend if isinstance(pend[0], list) else [pend]:
            if map_id(o.map) != p[0]:
                continue
            cur, frm, to = p[0], (p[1], p[2]), (p[3], p[4])
            try:
                stones = self.boulders(cur, o)                   # a boulder is moved, not a wall
                on_path = set(self.nav.path_cells(cur, frm, to)) & (set(o.npcs) | stones)
                cells = self.nav.map(cur)["cells"]
                # (only what the party can clear: without Surf, water is a wall; full run 87 was refused ~100 times in a
                # Safari Zone pocket walled off by an elevation step, each refusal excused as "Surf's job")
                clear = ({"T"} if self.can_clear("Cut", "HM01") else set()) | ({"~"} if self.can_clear("Surf", "HM03") else set())
                tree = bool(clear) and any(0 <= y < len(cells) and 0 <= x < len(cells[y]) and cells[y][x] in clear
                                           for x, y in self.nav.path_cells(cur, frm, to, cut=True, surf=True))
            except KeyError:
                on_path, tree = set(), False
            # a small tree on the way is Cut's job, not a wall (full run 41); water is Surf's (Pallet Town's south
            # edge: the walk to the water cell is refused until the player surfs); a refusal before any step is the
            # terrain whoever stands on the agent's path (see nav_feedback)
            terrain = len(p) > 5 and bool(p[5])
            # (with boulders on the map the atlas routes round them, and no path may simply mean a boulder is in the way:
            # a boulder is moved, not a wall)
            boulder_bound = False
            try:
                if self.boulders(cur, o):
                    dist, _ = self.nav.reach(cur, frm)
                    boulder_bound = not any((to[0] + dx, to[1] + dy) in dist for dx, dy in ((0, 0), *MOVES.values()))
            except KeyError:
                pass
            if (terrain or not on_path) and not tree and not boulder_bound:
                self.nav.record_noroute(cur, frm, to)

    def clear_option(self, cur: int, o: Obs, h, prefix: str, desc: str, surf: bool, cut: bool) -> Optional[Option]:
        """After the server found no way to this hop although the map data has one: if a person or object (an item
        ball, a guard) stands on the map path, the hop's option becomes 'first clear the way': walk up to it and talk
        (take the item / start the battle). Jev still has to pick it."""
        key = f"{h.map}:{h.x},{h.y}"
        if self.s["step"] - self.s["nav_noroute"].get(key, -10**9) > NAV_BLOCK_STEPS:
            return None
        path = set(self.nav.path_cells(cur, tuple(o.pos), (h.x, h.y), surf=surf, cut=cut))
        tried = self.s.setdefault("clear_tries", {})
        blockers = [n for n in o.npcs if n in path and tried.get(f"{h.map}:{n[0]},{n[1]}", 0) < 2]   # 2 tries: it stays
        tn = self.s.get("terrain_noroute", {}).get(key)
        if isinstance(tn, list) and self.s["step"] - tn[0] <= NAV_BLOCK_STEPS and \
                self.nav.linked(cur, (tn[1], tn[2]), tuple(o.pos)):
            blockers = []                                 # refused for the terrain: no one to talk out of the way
        if surf and blockers:
            # the first obstacle along the way decides: water before anyone standing further on is Surf's job (plateau-
            # leg experiment: Route 23's guards stand past its water, and "talk to the guard" was offered, not Surf)
            seq = self.nav.path_cells(cur, tuple(o.pos), (h.x, h.y), surf=surf, cut=cut)
            cells = self.nav.map(cur)["cells"]
            at_ = lambda x, y: cells[y][x] if 0 <= y < len(cells) and 0 <= x < len(cells[y]) else "#"
            water = next((k for k in range(1, len(seq)) if at_(*seq[k]) == "~" and at_(*seq[k - 1]) != "~"), None)
            first = next((k for k, c in enumerate(seq) if c in blockers), None)
            if water is not None and (first is None or water < first):
                blockers = []
        if not blockers and (cut or surf):
            return self.cut_option(cur, o, h, prefix, desc, surf, cut)
        if not blockers:
            return None
        grid = self.grid(o.map) or o.grid or {(x, y): c for y, row in enumerate(self.nav.map(cur)["cells"]) for x, c in enumerate(row)}
        clear = J.talk_to_options(dataclasses.replace(o, npcs=blockers), grid)
        if not clear:
            return None
        c = clear[0]
        bx, by = re.search(r"\((\d+),(\d+)\)", c.label).groups()
        label = f"{prefix}: first clear the way at ({bx},{by}) (talk to it / take it)"
        self.clear_for[label] = (h.x, h.y)
        return Option(label, c.tool, c.args, desc + f"; the only way on is blocked by someone or something at ({bx},{by})",
                      then=c.then)

    def cut_option(self, cur: int, o: Obs, h, prefix: str, desc: str, surf: bool, cut: bool = True) -> Optional[Option]:
        """The map path to this hop goes through a small tree that the server's walk refuses to cross: walk up to it,
        face it and use Cut (full run 41 had Cut and walked around Vermilion for 9,000 steps: the gym is behind a tree).
        Water from the shore the same way with Surf (the server's walk crosses water only while surfing)."""
        cells = self.nav.map(cur)["cells"]
        seq = self.nav.path_cells(cur, tuple(o.pos), (h.x, h.y), surf=surf, cut=cut)
        at_ = lambda x, y: cells[y][x] if 0 <= y < len(cells) and 0 <= x < len(cells[y]) else "#"
        at = next((k for k, (x, y) in enumerate(seq) if k and (cut and at_(x, y) == "T" or
                                                               surf and at_(x, y) == "~" and at_(*seq[k - 1]) != "~")), None)
        if not at:
            return None
        (sx, sy), (tx, ty) = seq[at - 1], seq[at]
        d = {(0, -1): "up", (0, 1): "down", (-1, 0): "left", (1, 0): "right"}.get((tx - sx, ty - sy))
        if not d:
            return None
        move = "Cut" if at_(tx, ty) == "T" else "Surf"
        label = f"{prefix}: first cut the tree at ({tx},{ty})" if move == "Cut" else \
            f"{prefix}: first surf from the shore onto the water at ({tx},{ty})"
        self.clear_for[label] = (h.x, h.y)
        face, use = ("walk", {"path": f"{d} 1", "on_battle": "stop"}), ("manage", {"action": "field", "target": move})
        desc += f"; a small tree at ({tx},{ty}) blocks the only way on: face it and use Cut" if move == "Cut" else \
            f"; the only way on is across the water at ({tx},{ty}): face it from the shore and use Surf"
        if tuple(o.pos) == (sx, sy):
            return Option(label, "walk", face[1], desc, then=[use])
        return Option(label, "walk", {"path": f"to {sx},{sy}", "on_battle": "stop"}, desc, then=[face, use])

    def nav_feedback(self, o: Obs, opt: Option, after: Obs, route_key: str) -> None:
        """Per-dungeon memory: count warps taken since the last progress; block a route hop that failed."""
        # warp options carry their coordinates in the label (a warp you stand on is taken by stepping off and back)
        m = re.search(r"warp at \((\d+),(\d+)\)", opt.label) or re.fullmatch(r"to (\d+),(\d+)", opt.args.get("path", ""))
        if "sleeping POK" in after.head + "\n" + after.text and after.map and after.pos and after.facing in FACING_STEP:
            # where the sleeping Snorlax lies: with the flute, that cell is the goal (full run 80 met it before the flute,
            # then went back and forth across Lavender's south edge: Route 12's north part is walled off from it)
            dx, dy = FACING_STEP[after.facing]
            self.s.setdefault("sleeper", {})[after.map] = [after.pos[0] + dx, after.pos[1] + dy]
            self.atlas_sleepers(after.map)

        if o.map and o.pos and after.map == o.map and o.mode == "overworld":
            # every cell a walk stepped on counts as walked, not only where it ended ("left 3/3, up 2/2")
            x, y = o.pos
            t = self.s.setdefault("trod", {}).setdefault(self.trod_key(o.map), [])
            for d, n in re.findall(r"\b(up|down|left|right) (\d+)/\d+", after.head):
                dx, dy = MOVES[d]
                for _ in range(int(n)):
                    x, y = x + dx, y + dy
                    if [x, y] not in t and len(t) < 900:
                        t.append([x, y])
        if opt.label.startswith(("explore the unvisited floor", "explore the untested floor")):
            m = None                                     # a fall on the way is not a warp at the walk's target cell
            fx = re.search(r"\((\d+),(\d+)\)", opt.label)
            if fx and o.map and ("no walkable route" in after.head or "could not get closer" in after.head):
                # (not a walk cut short by a trainer or a battle: Codex review 3)
                # not reached (a wall the view does not show, someone in the way): it counts as walked, or the strict
                # puzzle order would offer it again and again
                # (kept apart from the cells walked: as "walked" its radius hid the floor around it: Codex review 12)
                self.s.setdefault("floor_refused", {}).setdefault(self.trod_key(o.map), []).append([int(fx[1]), int(fx[2])])
        cur = map_id(o.map)
        if m and cur is not None and isinstance(self.nav, LearnedAtlas) and after.map and after.map != o.map \
                and o.map.startswith("Pokémon Mansion") and after.map.startswith("Pokémon Mansion") and o.pos and after.pos:
            # the target is a hole, not a warp (a known fall is offered as an "untaken warp"), and the moves stopped short
            # of it: the floor gave way on the way there (uncapped-1: aiming for 3F's (19,14), a 2F drop, the player fell
            # through (16,14) into 1F's part with the stairs to B1F; recorded as (19,14)'s arrival, that hole was never
            # learned and after a heal no route led back)
            x, y = o.pos
            for d, n in re.findall(r"\b(up|down|left|right) (\d+)/\d+", after.head):
                dx, dy = MOVES[d]
                x, y = x + dx * int(n), y + dy * int(n)
            warps = {(w[0], w[1]) for w in self.nav.data["maps"].get(str(cur), {}).get("warps", [])}
            if (int(m[1]), int(m[2])) not in warps and (x, y) != (int(m[1]), int(m[2])):
                m = None                                  # (so no warp is recorded at the target: the fall below is)
        if after.map and after.map != o.map and o.map.startswith("Pokémon Mansion") and \
                after.map.startswith("Pokémon Mansion") and o.pos and after.pos and not m and cur is not None \
                and re.search(r"\b(?:up|down|left|right) \d+/\d+", after.head) \
                and not NAME_WALK_RE.match(opt.args.get("path", "")):
            # (only a walk that itself ended on the other floor: "walk to <map>" crosses maps by their stairs inside the
            # server, and uncapped-1 learned 2F's (15,7) as a hole from one that stopped on 1F with no moves at all)
            # a fall through the floor during a walk (no warp was the target): the cell the moves reached is the hole
            x, y = o.pos
            for d, n in re.findall(r"\b(up|down|left|right) (\d+)/\d+", after.head):
                dx, dy = MOVES[d]
                x, y = x + dx * int(n), y + dy * int(n)
            self.record_fall(cur, (x, y), after)
        if m and after.map and after.map != o.map and cur is not None:
            key = f"{cur}:{m[1]},{m[2]}"
            self.s["nav_taken"][key] = self.s["nav_taken"].get(key, 0) + 1
            if key in self.s.get("stairs_changed", []):
                self.s["stairs_changed"].remove(key)       # seen again by these stairs
            if isinstance(self.nav, LearnedAtlas) and after.pos and map_id(after.map) is not None and "edge" not in opt.label:
                self.nav.record_warp(cur, int(m[1]), int(m[2]), map_id(after.map), *after.pos)
        if m and isinstance(self.nav, LearnedAtlas) and cur is not None and after.map == o.map and after.pos \
                and o.pos and tuple(after.pos) != tuple(o.pos) and "no walkable route" not in after.head:
            # (not when the walk was refused or left the player where they were, on another pad: Codex review 2)
            # a pad on the same map (Saffron Gym): the walk "could not get closer" and the player stands on another
            # pad. Recorded as taken, or the gym stays frontier for good (full run 75: the Cinnabar objective
            # explored Saffron Gym's pads again and again, ~1,400 steps)
            x, y, (ax, ay) = int(m[1]), int(m[2]), after.pos
            pads = {(w[0], w[1]) for w in self.nav.data["maps"].get(str(cur), {}).get("warps", [])}
            if (x, y) in pads and (ax, ay) in pads and abs(ax - x) + abs(ay - y) > 1:
                self.nav.record_warp(cur, x, y, cur, ax, ay)
        if isinstance(self.nav, LearnedAtlas) and self.edge_hop and after.map and after.map != o.map and after.pos \
                and cur is not None and map_id(after.map) is not None:
            side, ex_, ey_ = self.edge_hop
            self.nav.record_edge(cur, side, ex_, ey_, map_id(after.map), *after.pos)
        if isinstance(self.nav, LearnedAtlas) and self.edge_hop and cur is not None and after.map == o.map and \
                after.pos and tuple(after.pos) == tuple(self.edge_hop[1:]) and "blocked" in after.head:
            self.nav.record_nocross(cur, self.edge_hop[1], self.edge_hop[2], self.edge_hop[0])   # at the cell, not across
        if "first cut the tree" in opt.label or "first surf from the shore" in opt.label:
            return                                       # standing still while cutting/surfing is not a failed hop
        cl = re.search(r"first clear the way at \((\d+),(\d+)\)", opt.label)
        if cl and cur is not None:
            if "no walkable route" in after.head:
                # the blocker cannot even be reached from here: the hop is behind a wall (elevation), not a person
                hop = self.clear_for.get(opt.label)
                if hop and isinstance(self.nav, LearnedAtlas) and o.pos:
                    self.nav.record_noroute(cur, tuple(o.pos), hop)
                self.s["nav_noroute"].pop(f"{cur}:{hop[0]},{hop[1]}" if hop else "", None)
                return
            k = f"{cur}:{cl[1]},{cl[2]}"
            self.s.setdefault("clear_tries", {})[k] = self.s["clear_tries"].get(k, 0) + 1
        nr = re.match(r"no walkable route from \((\d+),(\d+)\) to \((\d+),(\d+)\)", after.head)
        if nr and isinstance(self.nav, LearnedAtlas) and cur is not None:
            # decided next step, once the map view (with the people in it) has been read: see learn_noroute(). Refused
            # before any step (no "— up 0/2" report) is the terrain itself: the server's pathfinder walks past people
            # (they only cost more), so no one standing there is the reason (full runs 78-79: Rock Tunnel B1F's far
            # ladder, refused again and again while trainers on the agent's path made it "a blocker to clear")
            # Boulders are the exception: the server routes around them, so a map with one may refuse for where they
            # stand now, not for the terrain (Codex 6)
            terrain = not re.search(r"on this map — (?:up|down|left|right) \d+/\d+", after.head) and \
                not self.boulders(cur, o)
            self.s["pending_noroute"] = [[cur, int(nr[1]), int(nr[2]), int(nr[3]), int(nr[4]), int(terrain)]]
            if terrain:     # with where it was refused from: elsewhere on the map the way may be someone to clear
                self.s.setdefault("terrain_noroute", {})[f"{cur}:{nr[3]},{nr[4]}"] = \
                    [self.s["step"], int(nr[1]), int(nr[2])]
        elif m and "could not get closer" in after.head and "slid" not in after.head and after.map == o.map and \
                after.pos and abs(after.pos[0] - int(m[1])) + abs(after.pos[1] - int(m[2])) <= 1 and \
                isinstance(self.nav, LearnedAtlas) and cur is not None:
            # only when it stopped right next to the warp: across the Rocket Hideout's spinners a walk ends far away
            # and the stairs are still there (full run 66 learned B2F/B3F's stairs as unreachable and left the hideout)
            # the walk went as near as it could and stopped: a warp behind a counter (Silph Co. 1F's (16,10) to 3F; full
            # run 64 explored towards it ~1,800 steps) is learned like a "no walkable route" from where it stopped
            # (from both, once the map view shows nobody on the way: a person who stood in the way moves on)
            to = [int(m[1]), int(m[2])]
            self.s.setdefault("sealed", {})[o.map] = to + [self.s["step"]]
            self.s["pending_noroute"] = [[cur, *after.pos, *to]] + ([[cur, *o.pos, *to]] if o.pos else [])
        if after.map and after.map != o.map:
            pass
        elif "no walkable route" in after.head or (after.mode == "overworld" and after.map == o.map and after.pos == o.pos
                                                    and "already at" not in after.head) \
                or (m and after.mode == "overworld" and after.map == o.map and after.pos
                    and re.search(r" 0/1(?: — could not get closer| — stopped: blocked)?$", after.head)
                    and abs(after.pos[0] - int(m[1])) + abs(after.pos[1] - int(m[2])) <= 2) \
                or ("stopped: dialogue appeared" in after.head and after.map in ("", o.map)):
            # (a person who stops the walk every time, e.g. Saffron's thirsty gate guards, blocks the hop like a wall;
            # bills-house iteration 34 walked into the Route 5 gate guard ~430 times. A trainer stops it only once.)
            # (a refusal carries no status line: no map in `after`)
            key = f"{cur}:{m[1]},{m[2]}" if m else (route_key if opt.label.startswith("follow the map route") else "")
            if not key and self.edge_hop:
                # an edge crossing that fails (Pallet Town's south edge is water: full-run iteration 36 tried it ~2,800
                # times) is blocked by its cell like a warp; the next cell on that side is offered instead
                key = f"{cur}:{self.edge_hop[1]},{self.edge_hop[2]}"
            # a refusal for a small tree or water the party can clear is Cut's or Surf's job (their options follow), not
            # a failed hop (full run 88: the tree refusal on Route 8 plus a gambler's interruption later blocked the
            # Underground Path's entrance 300 steps, and the frontier tried Route 8's gate to Saffron instead)
            clearable = ("small tree" in after.head and self.can_clear("Cut", "HM01")) or \
                ("water (~)" in after.head and self.can_clear("Surf", "HM03"))
            talk_stop = "stopped: dialogue appeared" in after.head and after.pos and after.pos != o.pos
            if key and talk_stop:
                # stopped by someone further on each time (Route 23's badge guards, one per gate: full run 90 was
                # stopped by the Marsh and Volcano guards on the way to Victory Road and blocked its entrance 300 steps
                # from one cell below it) is progress; stopped at the same cell again is a person in the way
                # (at most TALK_STOPS such stops per hop in NAV_BLOCK_STEPS: two cells in turn is no progress; Codex 17)
                stops = self.s.setdefault("nav_talk_stop", {})
                last = stops.get(key)
                if not last or len(last) < 4 or self.s["step"] - last[3] > NAV_BLOCK_STEPS:
                    last = None
                moved_on = bool(last) and last[:2] != list(after.pos) and last[2] < TALK_STOPS
                stops[key] = [after.pos[0], after.pos[1], (last[2] + 1) if last else 1,
                              last[3] if last else self.s["step"]]
                if moved_on:                        # the earlier stop was someone else further back: not "again"
                    self.s.setdefault("nav_fail_from", {}).pop(key, None)
            else:
                moved_on = False
            if key and not clearable and not moved_on and "stopped: dialogue appeared" in after.head:
                # what it says decides (remember_outmatched): a floor message that heals is no one in the way
                self.s["talk_fail"] = [key, self.s["step"], key in self.s["nav_blocked"]]
            if key and not clearable and not moved_on:
                # failed again from the same part of the map, lately (full run 82: refusals from B1F's east part, then
                # a trainer stopping the walk from (23,11) once, blocked the far ladder in the part that reaches it;
                # each failure keeps its own step: Codex review 9)
                fails = [f for f in self.s.setdefault("nav_fail_from", {}).get(key) or []
                         if len(f) > 2 and self.s["step"] - f[2] <= NAV_BLOCK_STEPS]
                same_part = bool(fails) and (not o.pos or not isinstance(self.nav, LearnedAtlas) or ScopedBlocks(
                    (key,), {key: [f[:2] for f in fails]}, self.nav.linked).applies(key, (cur, o.pos[0], o.pos[1])))
                if same_part:
                    # failed again: try another way; stopped by something on the way before the first step ("— down
                    # 0/7": someone standing in a one-cell corridor) only for a short while (full run 87: Pokémon Tower
                    # 6F's corridor to the 7F stairs, blocked 300 steps after two such stops, and the player left for
                    # Route 8; run 85 had walked through on the next try)
                    held = SHORT_BLOCK_STEPS if re.search(r"on this map — (?:up|down|left|right) 0/\d+", after.head) \
                        else NAV_BLOCK_STEPS
                    self.s["nav_blocked"][key] = self.s["step"] + held
                    if o.pos:                             # the parts of the map it is blocked in (Codex review 8)
                        fs = self.s.setdefault("nav_block_from", {}).get(key) or []
                        fs = [f for f in (fs if not fs or isinstance(fs[0], list) else [fs])
                              if len(f) > 2 and self.s["step"] - f[2] <= NAV_BLOCK_STEPS and f[:2] != list(o.pos)]
                        self.s["nav_block_from"][key] = (fs + [[o.pos[0], o.pos[1], self.s["step"]]])[-8:]
                if o.pos:
                    self.s["nav_fail_from"][key] = ([f for f in fails if f[:2] != list(o.pos)]
                                                    + [[o.pos[0], o.pos[1], self.s["step"]]])[-8:]
            if key:
                self.s["nav_noroute"][key] = self.s["step"]   # (the cut/surf options read it)

    def hop_walk(self, cur: int, pos: tuple, x: int, y: int, side: str = "") -> Optional[tuple[dict, list]]:
        """Walk args and follow-up walks for one hop: to a warp tile, or to the route's own edge cell and one step
        across (the server's "to <side> edge" picks its own cell, which can be solid on the other side). A warp the
        player stands on (just arrived by it) is taken by stepping off and back on; None if no neighbour is free."""
        if side:
            across = {"north": "up", "south": "down", "west": "left", "east": "right"}[side]
            if (x, y) == pos:
                return {"path": f"{across} 1", "on_battle": "stop"}, []
            return {"path": f"to {x},{y}", "on_battle": "stop"}, [("walk", {"path": f"{across} 1", "on_battle": "stop"})]
        if (x, y) != pos:
            return {"path": f"to {x},{y}", "on_battle": "stop"}, []
        m = self.nav.map(cur)
        cells, warps = m["cells"], {(wx, wy) for wx, wy, _, _ in m["warps"]}
        back = {"up": "down", "down": "up", "left": "right", "right": "left"}
        for d, (dx, dy) in MOVES.items():
            nx, ny = x + dx, y + dy
            if 0 <= ny < len(cells) and 0 <= nx < len(cells[0]) and cells[ny][nx] in (".", ",", ":", "X") and (nx, ny) not in warps:
                return {"path": f"{d} 1", "on_battle": "stop"}, [("walk", {"path": f"{back[d]} 1", "on_battle": "stop"})]
        return None

    def screen_entry(self, o: Obs) -> dict:
        """Per-screen visit counter and options tried there, reset whenever the director sees progress."""
        if self.director and self.s["screens_at"] != self.s.get("last_progress_step", 0):
            self.s["screens"], self.s["screens_at"] = {}, self.s.get("last_progress_step", 0)
        if o.mode == "overworld":
            sig = f"ow|{o.map}|{o.pos}|{o.facing}"
        else:
            sig = o.mode + "|" + hashlib.md5(o.screen.encode()).hexdigest()[:12]
        screens = self.s["screens"]
        if sig not in screens and len(screens) >= 400:
            screens.pop(next(iter(screens)))
        e = screens.setdefault(sig, {"n": 0, "tried": []})
        e["n"] += 1
        return e

    def idle_reload(self):
        """Any screen: after IDLE_RELOAD steps without progress reload the last progress checkpoint (code, no Jev)."""
        idle = self.s["step"] - self.s.get("last_progress_step", 0)
        if idle >= IDLE_RELOAD and self.s.get("checkpoint_step") is not None \
                and self.s["step"] - self.s["last_reload_step"] >= IDLE_RELOAD:
            self.s["last_reload_step"] = self.s["step"]
            self.s["reloads"] += 1
            if self.director:
                return self.director.reload_option(self.s["step"])
            return Option("recovery: reload the last progress checkpoint", "load_state", {"slot": "jev-progress"})
        return None

    def fallback_allowed(self) -> bool:
        """The fallback budget cap (cost and/or count): once used up, Jev plays on alone (logged once)."""
        over = (self.a.fallback_budget_usd and self.s["fallback_cost"] >= self.a.fallback_budget_usd) or \
            (self.a.max_fallbacks and self.s["fallbacks"] >= self.a.max_fallbacks)
        if over and not self.s["fallback_capped"]:
            self.s["fallback_capped"] = True
            emit({"type": "fallback_cap", "step": self.s["step"], "fallbacks": self.s["fallbacks"],
                  "cost_usd": round(self.s["fallback_cost"], 4)})
        return not over

    async def fallback(self, trigger: str, dec, o: Obs, objective: str, opts: list[Option], facts, kind: str) -> None:
        """Ask Claude for this one decision and record a structured fallback event."""
        self.s["last_fallback_step"] = self.s["step"]
        probs = dec.record.get("probs") or {}
        state = self.jev_state(o, objective)
        fb = self.chooser.choose(trigger, objective, state, opts, probs)
        self.planner_calls += 1
        self.planner_cost += fb.cost_usd
        self.s["fallback_cost"] += fb.cost_usd
        for k in self.planner_tokens:
            self.planner_tokens[k] += int(fb.tokens.get(k, 0))
        chosen = next((x for x in opts if x.label == fb.label), None)
        ev = {"id": f"{self.a.session_id}:{self.s['step']}", "run": self.a.session_id, "step": self.s["step"],
              "t": round(time.time(), 1), "trigger": trigger.split(" ")[0] if trigger.startswith("low") else trigger,
              "trigger_detail": trigger, "mode": kind, "map": o.map, "pos": list(o.pos) if o.pos else None,
              "objective": objective, "node": dec.record.get("why"), "recovery": self.s.get("recovery", 0),
              "summary": {"badges": o.badges, "money": o.money, "lead": o.lead,
                          "party": [f"{p['species']} L{p['level']} {p['hp']}/{p['max_hp']}" for p in self.party],
                          "bag": [f"{n}×{q}" for n, q in self.items], "moves": sorted(facts.moves) if facts else [],
                          "milestones": self.s["milestones"][-8:], "visited": len(self.s["visited"])},
              "screen": o.screen, "recent_actions": self.s["history"][-8:],
              "options": [{"label": x.label, "p": round(probs.get(x.label, 0), 4)} for x in opts],
              "jev_choice": dec.record["choice"], "jev_confidence": dec.record["confidence"],
              "fallback_model": fb.model, "fallback_choice": fb.label or None, "fallback_why": fb.why,
              "agreed": fb.label == dec.record["choice"], "cost_usd": fb.cost_usd, "latency_ms": fb.latency_ms,
              "error": fb.error or None, "sig_before": self.progress_sig(o)}
        dec.record["fallback"] = ev["trigger"]
        if chosen is not None and chosen.label != dec.record["choice"]:
            dec.option = chosen
            dec.record.update(superseded=True, executed=chosen.label)   # not Jev's call: out of Jev's calibration
        self.s["pending_fallbacks"].append(ev)
        self.s["fallbacks"] += 1
        emit({"type": "fallback", "step": ev["step"], "trigger": trigger, "jev": ev["jev_choice"], "chosen": fb.label,
              "error": fb.error or None})

    def progress_sig(self, o: Obs) -> dict:
        return {"map": o.map, "pos": list(o.pos) if o.pos else None, "milestones": len(self.s["milestones"]),
                "visited": len(self.s["visited"]), "items": len(self.s.get("ever_items", []))}

    def settle_fallbacks(self, after: Obs, force: bool = False) -> None:
        """Fill in each fallback's outcome N steps later and append it to fallbacks.jsonl."""
        keep = []
        for ev in self.s["pending_fallbacks"]:
            if not ev.get("immediate"):
                ev["immediate"] = (self.s["history"][-1] if self.s["history"] else "")[:160]
            if self.s["step"] - ev["step"] >= self.a.fallback_outcome_steps or force:
                now, before = self.progress_sig(after), ev.pop("sig_before")
                ev["outcome_after"] = {"steps": self.s["step"] - ev["step"], "complete": not force or
                                       self.s["step"] - ev["step"] >= self.a.fallback_outcome_steps,
                                       "map": now["map"], "pos": now["pos"],
                                       "new_milestones": self.s["milestones"][before["milestones"]:],
                                       "new_maps": now["visited"] - before["visited"],
                                       "moved": now["map"] != before["map"] or now["pos"] != before["pos"],
                                       "progress": (now["milestones"], now["visited"], now["items"]) !=
                                                   (before["milestones"], before["visited"], before["items"])}
                with open(self.fallback_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            else:
                keep.append(ev)
        self.s["pending_fallbacks"] = keep

    async def run(self) -> str:
        emit({"type": "start", "session_id": self.a.session_id, "variant": self.a.variant, "resumed": self.resumed,
              "step": self.s["step"], "jev_model": self.a.jev_model, "agent_version": AGENT_VERSION})
        self.reply = await self.observe()
        while not self.stop and not STOP["flag"]:
            if self.a.max_steps and self.s["step"] >= self.a.max_steps:
                self.stop = "max_steps"
                break
            await self.step()
            self.save()
            self.usage()
        if self.stop in ("champion", "budget", "stuck", "max_steps", "segment_goal"):
            self.settle_fallbacks(parse(self.reply), force=True)
        self.save()
        return self.stop or "terminated"


def load_nav(a: argparse.Namespace, server_cmd: list[str]) -> Optional[WorldNav]:
    """--map-source rom: the static world graph from the ROM the server plays (its --rom argument); learned: the
    atlas Jev builds while playing (<run>/data/jev_atlas.json, seeded from --atlas)."""
    if a.map_source == "learned":
        return LearnedAtlas(Path(a.run_dir) / "data" / "jev_atlas.json", seed=Path(a.atlas) if a.atlas else None)
    rom = a.rom or (server_cmd[server_cmd.index("--rom") + 1] if "--rom" in server_cmd[:-1] else "")
    path = Path(rom) if Path(rom).is_absolute() else Path(a.run_dir) / rom
    try:
        return WorldNav(path.read_bytes()) if rom else None
    except OSError:
        return None


async def amain(a: argparse.Namespace, server_cmd: list[str]) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    try:
        client = make_client(a.jev_model, a.mock, seed=a.seed)
    except JevError as e:
        emit({"type": "error", "message": str(e)})
        return 2
    planner = chooser = None
    if a.variant == "assist":
        chooser = J.MockChooser() if a.mock else J.ClaudeChooser(a.fallback_model)
        if not chooser.available():
            emit({"type": "error", "message": "the assist fallback needs the claude CLI on PATH"})
            return 2
    if a.variant == "hybrid":
        planner = MockPlanner() if a.mock else ClaudePlanner(a.planner_model)
        if not planner.available():
            emit({"type": "error", "message": "the hybrid planner needs the claude CLI on PATH"})
            return 2
    policy = JevPolicy(client, Path(a.run_dir) / "data" / "jev_decisions.jsonl", variant=a.variant,
                       seed=a.seed * 100003 + (0 if a.mock else int(time.time()) % 100003))   # mock runs are reproducible
    params = StdioServerParameters(command=server_cmd[0], args=server_cmd[1:], cwd=a.run_dir)
    code = 0
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            async def call_tool(name, args):
                res = await session.call_tool(name, args)
                return "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")

            agent = Agent(a, call_tool, policy, planner, chooser, nav=load_nav(a, server_cmd))
            reason = "error"
            try:
                reason = await agent.run()
            except JevRateLimited as e:
                emit({"type": "error", "message": str(e), "rate_limited": True})
                code = 3
            except JevError as e:
                emit({"type": "error", "message": str(e)})
                code = 2
            finally:
                agent.save()
                agent.usage()
            emit({"type": "result", "reason": reason, "steps": agent.s["step"], "tool_calls": agent.tool_calls,
                  "jev_calls": policy.calls, "planner_calls": agent.planner_calls,
                  "cost_usd": round(policy.cost_usd + agent.planner_cost, 6)})
    client.close()
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Jev player (MCP client of server.py)")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--session-id", default="")
    p.add_argument("--variant", default="solo", choices=["solo", "assist", "hybrid", "scripted"])
    p.add_argument("--fallback-model", default=PLANNER_MODEL, help="assist: the model asked when Jev is unsure or stuck")
    p.add_argument("--fallback-threshold", type=float, default=0.3, help="assist: fall back below this Jev confidence")
    p.add_argument("--fallback-gap", type=int, default=3, help="assist: minimum steps between fallbacks")
    p.add_argument("--fallback-budget-usd", type=float, default=0.0,
                   help="assist: stop asking the fallback model once its cost reaches this (0 = no cap); Jev plays on alone")
    p.add_argument("--max-fallbacks", type=int, default=0, help="assist: at most this many fallbacks per run (0 = no cap)")
    p.add_argument("--fallback-outcome-steps", type=int, default=10, help="assist: record the outcome this many steps later")
    p.add_argument("--stuck-fail-steps", type=int, default=2000,
                   help="solo (final exam): stop as 'stuck' after this many steps without progress (0 = never)")
    p.add_argument("--jev-model", default=DEFAULT_MODEL)
    p.add_argument("--planner-model", default=PLANNER_MODEL)
    p.add_argument("--replan-every", type=int, default=40, help="hybrid: ask the planner at least every N steps")
    p.add_argument("--confidence-threshold", type=float, default=0.3, help="hybrid: replan when Jev's confidence is below this")
    p.add_argument("--stuck-threshold", type=float, default=0.7, help="hybrid: replan when Jev's 'stuck' noul is at least this")
    p.add_argument("--min-replan-gap", type=int, default=5, help="hybrid: steps between confidence/stuck-triggered replans")
    p.add_argument("--rom", default="", help="ROM for the static map graph (default: the server's --rom)")
    p.add_argument("--map-source", choices=["rom", "learned"], default="learned",
                   help="learned (default): Jev builds its own atlas while playing; rom: world graph from the ROM map tables")
    p.add_argument("--atlas", default="", help="learned: start from this atlas (an earlier run's data/jev_atlas.json)")
    p.add_argument("--max-steps", type=int, default=0)
    p.add_argument("--progress", default="", help="segment start: the last objective-graph node the state has finished")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mock", action="store_true", help="offline: MockJev (and MockPlanner for hybrid), no network")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        raise SystemExit("usage: jev_agent.py [options] -- <server command...>")
    i = argv.index("--")
    a = build_parser().parse_args(argv[:i])
    a.session_id = a.session_id or Path(a.run_dir).name

    def _stop(*_):
        STOP["flag"] = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return asyncio.run(amain(a, argv[i + 1:]))


if __name__ == "__main__":
    sys.exit(main())
