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
from bench.jev_solo import GYM_NODES, STUCK_Q, SoloDirector  # noqa: E402
from bench.jev_nav import MOVES, WorldNav, map_id  # noqa: E402
from bench.jev_atlas import LearnedAtlas  # noqa: E402
from games import gen1_data as D  # noqa: E402
from bench import jev as J  # noqa: E402

AGENT_VERSION = "2"
NAME_WALK_RE = re.compile(r"^to (?!.*\bedge$)(?!\d+,\d+$).+")   # walk("to <map name>"): the server picks the nearest warp
NAV_BLOCK_STEPS = 300                           # a route hop that failed is avoided this long
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
        self.party: list[dict] = []
        self.items: list[tuple[str, int]] = []
        self.team_step = -10**9
        self.reply = ""
        self.stop = ""
        self.route_hint = ""
        self.why = ""                                  # the director's reason for the objective (heal, train, node id)
        self.exploring = False
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
            o.npcs = o.npcs or m.npcs
        if o.grid:                                     # keep the terrain (NPC cells are refreshed by every view)
            g = {f"{x},{y}": c for (x, y), c in o.grid.items()}
            grids.setdefault(o.map, {}).update(g)
        ex, cn = maps.get(o.map, [[], []])
        return list(ex), [tuple(c) for c in cn]

    def free_neighbour(self, o: Obs) -> bool:
        g = self.grid(o.map)
        x, y = o.pos
        return any(g.get((x + dx, y + dy)) in (".", ",") for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)))

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
        if o.mode == "prompt":
            return press_options()
        if o.mode == "battle_start":
            return [Option("press A", "press", {"buttons": "A"})]
        if o.mode == "dialogue":
            return [Option("continue the conversation", "talk", {})]
        if o.mode == "battle":
            return battle_options(o.battle, self.party, self.items, allow_auto=True, run_note=self.run_note(o))
        if o.mode == "faint_switch":
            return battle_options(o.battle, self.party, self.items, only_switch=True) or press_options()
        return overworld_options(o, ex, cn, targets, self.party, self.items, self.s["step"] - self.s["last_save_step"],
                                 grid=self.grid(o.map), said=self.s["said"].get(o.map, {}),
                                 facing_said=self.s["said"].get(o.map, {}).get(f"facing {o.pos} {o.facing}", ""))

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
        o = parse(self.reply)
        self.route_hint = ""
        self.s["milestones"] += [e for e in o.events if e not in self.s["milestones"]]
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
        elif o.mode == "overworld" and (self.team_step < 0 or self.s["step"] - self.team_step >= 30
                                        or self.team_step < self.s["battle_seen_step"] or self.s.get("refresh_items")):
            await self.refresh_team()
            self.s["refresh_items"] = False
        ex, cn = await self.map_info(o) if o.mode == "overworld" else ([], [])
        if o.mode == "overworld" and o.map:
            # replies after a warp often carry no map rows: keep the last people seen on this map
            known = self.s.setdefault("npcs", {})
            if o.npcs:
                known[o.map] = [list(n) for n in o.npcs]
            elif known.get(o.map):
                o.npcs = [tuple(n) for n in known[o.map]]
            elif o.map not in known:
                o.npcs = parse(await self.tool("state", section="map")).npcs
                known[o.map] = [list(n) for n in o.npcs]
        if isinstance(self.nav, LearnedAtlas) and o.mode == "overworld" and o.map and map_id(o.map) is not None \
                and (not self.nav.known(map_id(o.map)) or o.map != self.s.get("atlas_map")):
            # learned atlas: record what the player can see on entering a map (full map view + wWarpEntries in WRAM)
            view = await self.tool("state", section="map")
            warps = await self.tool("memory", address="D3AE", length=129)
            last = await self.tool("memory", address="D365", length=1)        # wLastMap: where "outside" warps lead
            self.nav.observe(map_id(o.map), view, warps, cn, last_map_text=last)
        if o.mode == "overworld" and o.map:
            self.s["atlas_map"] = o.map

        kind = o.mode
        battle = kind in ("battle", "faint_switch")
        nouls = None
        facts = None
        if self.director:
            facts = self.director.facts(o, self.party, self.items)
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
                o.npcs = parse(await self.tool("state", section="map")).npcs   # who stands in the way (no view in a refusal)
            self.learn_noroute(o)
            nav_opts, route_key = self.nav_options(o, targets, facts, why)
            if nav_opts:                                 # concrete warps replace "walk to <map>" (nearest-warp guesses)
                quiet = (bool(route_key) or self.exploring) and self.s.get("recovery", 0) == 0   # blind walks dilute the choice
                opts = nav_opts + [x for x in opts if not (x.tool == "walk" and NAME_WALK_RE.match(x.args.get("path", "")))
                                   and not (x.tool == "walk" and x.args.get("path", "").endswith(" edge"))   # nav lists reachable edges
                                   and not (quiet and x.label.startswith("walk ") and x.label.endswith(" 4 tiles"))]
            if why in GYM_NODES and o.map.endswith("Gym") and any(x.label.startswith("talk to the person") for x in opts) \
                    and self.s.get("recovery", 0) < 2:
                # in the gym the objective names: the trainers and the leader are the options (blind walks only pace)
                opts = [x for x in opts if not (x.label.startswith("walk ") and x.label.endswith(" tiles"))
                        and x.label != "talk to what you are facing"]
            if why == "heal" and o.map.endswith("Poké Center"):
                opts = [x for x in opts if not x.label.startswith("talk to the person")]   # the nurse option replaces them
            seen, uniq = set(), []
            for x in opts:
                if x.label.lower() not in seen:
                    seen.add(x.label.lower())
                    uniq.append(x)
            opts = uniq
        forced = self.director.forced_recovery(self.s["step"]) if self.director and kind == "overworld" else None
        if self.director and kind == "overworld" and self.director.want_checkpoint(self.s["step"]):
            await self.tool("save_state", slot="jev-progress")
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
            opts = [x for x in opts if x.label not in failed] or opts
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
        if o.map and (opt.label.startswith("talk to") or opt.tool == "talk"):
            m = re.search(r"\((\d+),(\d+)\)", opt.label) if opt.label.startswith("talk to the person") else None
            key = f"{m[1]},{m[2]}" if m else f"facing {o.pos} {o.facing}"
            self.s["said"].setdefault(o.map, {})[key] = after.head[:80]
        if opt.tool == "manage" and opt.args.get("action") == "save":
            self.s["last_save_step"] = self.s["step"]
        if opt.tool in ("manage", "shop") or GOT_RE.search(reply):
            self.s["refresh_items"] = True              # the bag, HMs or moves may have changed
        if "fighting fit" in reply:
            self.team_step = -10**9                      # healed at a Poké Center: re-read the party (heal rule)
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
        # healing: the targets list the nearest Poké Center first; otherwise the route ends at the last target
        order = targets if why == "heal" else list(reversed(targets))
        goal = next((map_id(t) for t in order if map_id(t) is not None), None)
        moves = set(facts.moves) if facts else set()
        surf = "Surf" in moves and (facts.badges if facts else 0) >= 5
        cut = "Cut" in moves and (facts.badges if facts else 0) >= 2
        if goal is not None and goal != cur:
            blocked = frozenset(k for k, until in self.s["nav_blocked"].items() if until > self.s["step"])
            route = self.nav.route(cur, tuple(o.pos), goal, surf=surf, cut=cut, taken=self.s["nav_taken"], blocked=blocked)
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
        if isinstance(self.nav, LearnedAtlas) and not route_key and goal != cur:   # on the objective's map: nothing to explore
            # the objective's map is not in the atlas (or not reachable through it yet): explore frontier-first
            blocked = frozenset(k for k, until in self.s["nav_blocked"].items() if until > self.s["step"])
            front = self.nav.frontier(cur, tuple(o.pos), set(self.s["visited"]), surf=surf, cut=cut, blocked=blocked,
                                      prefer=tuple(targets))
            pending = [h for h in front if self.s["step"] - self.s["nav_noroute"].get(f"{h.map}:{h.x},{h.y}", -10**9)
                       <= NAV_BLOCK_STEPS]          # a hop waiting for its way to be cleared goes first
            for h in (pending[:1] + [x for x in front if x not in pending[:1]])[:2]:
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
        visited = set(self.s["visited"])
        _, trans = self.nav.reach(cur, tuple(o.pos), surf=surf, cut=cut)
        near = {(h.x, h.y) for _, h, _ in trans if h.kind == "warp"}   # warps this section of the map can reach
        sides: dict = {}
        for steps, h, _ in trans:                         # edges this section reaches: the nearest cell per side
            if h.kind == "edge" and h.x >= 0 and (h.side not in sides or steps < sides[h.side][0]):
                sides[h.side] = (steps, h)
        for _, h in sides.values():
            walk = self.hop_walk(cur, tuple(o.pos), h.x, h.y, h.side)
            label = f"walk to {h.dest_name} ({h.side} edge)"
            if walk and not any(x.label == label for x in opts):
                opts.append(Option(label, "walk", walk[0], f"leave this map by its {h.side} edge", then=walk[1]))
                self.edge_opts[label] = (h.side, h.x, h.y)
        for i, (x, y, _, _) in enumerate(self.nav.map(cur)["warps"]):
            if (x, y) not in near or (x, y) == skip:
                continue
            dests = {D.map_name(d[0]) for d in self.nav.warp_dest(cur, i)}
            name = dests.pop() if len(dests) == 1 else "outside"
            new = "" if name in visited else " (not visited yet)"
            walk = self.hop_walk(cur, tuple(o.pos), x, y)
            if not walk:
                continue
            here = " (you stand on it: step off and back on)" if (x, y) == tuple(o.pos) else ""
            opts.append(Option(f"walk to the warp at ({x},{y}) → {name}{new}{here}", "walk", walk[0],
                               "this particular door, ladder or stairway", then=walk[1]))
        return opts, route_key

    def learn_noroute(self, o: Obs) -> None:
        """Learned atlas: a refusal with nobody on the path is a wall the map view does not show (cave elevation);
        with someone or something on it, it is a blocker to clear, not a wall."""
        pend = self.s.pop("pending_noroute", None)
        if not pend or not isinstance(self.nav, LearnedAtlas) or map_id(o.map) != pend[0]:
            return
        cur, frm, to = pend[0], (pend[1], pend[2]), (pend[3], pend[4])
        try:
            on_path = set(self.nav.path_cells(cur, frm, to)) & set(o.npcs)
        except KeyError:
            on_path = set()
        if not on_path:
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

    def nav_feedback(self, o: Obs, opt: Option, after: Obs, route_key: str) -> None:
        """Per-dungeon memory: count warps taken since the last progress; block a route hop that failed."""
        # warp options carry their coordinates in the label (a warp you stand on is taken by stepping off and back)
        m = re.search(r"warp at \((\d+),(\d+)\)", opt.label) or re.fullmatch(r"to (\d+),(\d+)", opt.args.get("path", ""))
        cur = map_id(o.map)
        if m and after.map and after.map != o.map and cur is not None:
            key = f"{cur}:{m[1]},{m[2]}"
            self.s["nav_taken"][key] = self.s["nav_taken"].get(key, 0) + 1
            if isinstance(self.nav, LearnedAtlas) and after.pos and map_id(after.map) is not None and "edge" not in opt.label:
                self.nav.record_warp(cur, int(m[1]), int(m[2]), map_id(after.map), *after.pos)
        if isinstance(self.nav, LearnedAtlas) and self.edge_hop and after.map and after.map != o.map and after.pos \
                and cur is not None and map_id(after.map) is not None:
            side, ex_, ey_ = self.edge_hop
            self.nav.record_edge(cur, side, ex_, ey_, map_id(after.map), *after.pos)
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
            # decided next step, once the map view (with the people in it) has been read: see learn_noroute()
            self.s["pending_noroute"] = [cur, int(nr[1]), int(nr[2]), int(nr[3]), int(nr[4])]
        if after.map and after.map != o.map:
            pass
        elif "no walkable route" in after.head or (after.mode == "overworld" and after.map == o.map and after.pos == o.pos
                                                    and "already at" not in after.head):
            # (a refusal carries no status line: no map in `after`)
            key = f"{cur}:{m[1]},{m[2]}" if m else (route_key if opt.label.startswith("follow the map route") else "")
            if key:
                if self.s["step"] - self.s["nav_noroute"].get(key, -10**9) <= NAV_BLOCK_STEPS:
                    self.s["nav_blocked"][key] = self.s["step"] + NAV_BLOCK_STEPS   # failed again: try another way
                self.s["nav_noroute"][key] = self.s["step"]

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
            if 0 <= ny < len(cells) and 0 <= nx < len(cells[0]) and cells[ny][nx] in (".", ",") and (nx, ny) not in warps:
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
