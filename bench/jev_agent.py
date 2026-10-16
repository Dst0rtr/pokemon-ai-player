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
import json
import re
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.jev import (BATTLE_RE, DEFAULT_MODEL, PLANNER_MODEL, STATUS_RE, ClaudePlanner, JevError, drop_repeats,  # noqa: E402
                       JevPolicy, JevRateLimited, MockPlanner, Obs, Option, battle_options, label_outcome, make_client,
                       overworld_options, parse, parse_items, parse_party, press_options, route_step)
from bench.jev_solo import STUCK_Q, SoloDirector  # noqa: E402
from bench import jev as J  # noqa: E402

AGENT_VERSION = "2"
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
    def __init__(self, a: argparse.Namespace, call_tool, policy: JevPolicy, planner=None, chooser=None):
        if a.variant == "solo" and (planner is not None or chooser is not None):
            raise ValueError("jev-solo must not have a planner or a fallback: no LLM may be called")
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
                     "last_fallback_step": -10**9}.items():
            self.s.setdefault(k, v)
        self.director = SoloDirector(self.s) if a.variant in ("solo", "assist") else None
        self.party: list[dict] = []
        self.items: list[tuple[str, int]] = []
        self.team_step = -10**9
        self.reply = ""
        self.stop = ""
        self.planner_cost = 0.0
        self.planner_calls = 0
        self.planner_tokens = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0}
        self.tool_calls = 0

    # ------------------------------------------------------------- plumbing
    def save(self) -> None:
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
            return battle_options(o.battle, self.party, self.items, allow_auto=True)
        if o.mode == "faint_switch":
            return battle_options(o.battle, self.party, self.items, only_switch=True) or press_options()
        return overworld_options(o, ex, cn, targets, self.party, self.items, self.s["step"] - self.s["last_save_step"],
                                 grid=self.grid(o.map), said=self.s["said"].get(o.map, {}),
                                 facing_said=self.s["said"].get(o.map, {}).get(f"facing {o.pos} {o.facing}", ""))

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
        return {"objective": objective, "location": f"{o.map} ({o.pos[0]},{o.pos[1]}) facing {o.facing}" if o.pos else "(no map yet)",
                "team": o.lead, "badges": o.badges, "money": o.money, "screen": o.screen, "hint": o.hint,
                "last_result": o.head[:200], "recent_actions": recent}

    async def step(self) -> None:
        o = parse(self.reply)
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
        if o.mode in ("battle", "faint_switch") and (self.team_step < self.s["battle_seen_step"] or self.team_step < 0):
            await self.refresh_team()
        if o.mode in ("battle", "battle_start", "faint_switch"):
            self.s["battle_seen_step"] = self.s["step"]
        elif o.mode == "overworld" and (self.team_step < 0 or self.s["step"] - self.team_step >= 30
                                        or self.team_step < self.s["battle_seen_step"] or self.s.get("refresh_items")):
            await self.refresh_team()
            self.s["refresh_items"] = False
        ex, cn = await self.map_info(o) if o.mode == "overworld" else ([], [])

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

        opts = self.options(o, ex, cn, targets)
        if self.director and kind == "overworld":
            opts = self.director.extra_options(o, facts, self.party, ex, cn, why) + opts
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
            kept = drop_repeats(opts, self.s["history"])
            loop_dropped = len(kept) < len(opts)
            opts = kept
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
            trigger = self.fallback_trigger(dec, loop_dropped and kind == "overworld", kind == "overworld")
            if trigger and self.s["step"] - self.s["last_fallback_step"] >= self.a.fallback_gap:
                await self.fallback(trigger, dec, o, objective, opts, facts, kind)
        opt = dec.option
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
        if o.map and (opt.label.startswith("talk to") or opt.tool == "talk"):
            m = re.search(r"\((\d+),(\d+)\)", opt.label) if opt.label.startswith("talk to the person") else None
            key = f"{m[1]},{m[2]}" if m else f"facing {o.pos} {o.facing}"
            self.s["said"].setdefault(o.map, {})[key] = after.head[:80]
        if opt.tool == "manage" and opt.args.get("action") == "save":
            self.s["last_save_step"] = self.s["step"]
        if opt.tool in ("manage", "shop") or GOT_RE.search(reply):
            self.s["refresh_items"] = True              # the bag, HMs or moves may have changed
        line = f"{opt.label} -> {after.head[:90]}"
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
        if self.a.variant == "solo" and self.a.stuck_fail_steps and \
                self.s["step"] - self.s.get("last_progress_step", 0) >= self.a.stuck_fail_steps:
            self.stop = "stuck"                            # final exam: no fallback, stuck = fail
        self.reply = reply if has_status(reply) or after.mode == "over" else reply + "\n" + await self.observe()

    # ------------------------------------------------------------- jev-assist fallbacks
    def fallback_trigger(self, dec, loop_dropped: bool, overworld: bool) -> str:
        """Low confidence anywhere; stuck/loop only on the map (repeating A through menus and text is normal)."""
        if dec.record["confidence"] < self.a.fallback_threshold:
            return f"low confidence {dec.record['confidence']:.2f}"
        if overworld and (self.s.get("recovery", 0) >= 2 or self.s.get("pos_repeat", 0) >= 10):
            return "stuck"
        if loop_dropped:
            return "loop"
        return ""

    async def fallback(self, trigger: str, dec, o: Obs, objective: str, opts: list[Option], facts, kind: str) -> None:
        """Ask Claude for this one decision and record a structured fallback event."""
        self.s["last_fallback_step"] = self.s["step"]
        probs = dec.record.get("probs") or {}
        state = self.jev_state(o, objective)
        fb = self.chooser.choose(trigger, objective, state, opts, probs)
        self.planner_calls += 1
        self.planner_cost += fb.cost_usd
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

            agent = Agent(a, call_tool, policy, planner, chooser)
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
    p.add_argument("--fallback-outcome-steps", type=int, default=10, help="assist: record the outcome this many steps later")
    p.add_argument("--stuck-fail-steps", type=int, default=2000,
                   help="solo (final exam): stop as 'stuck' after this many steps without progress (0 = never)")
    p.add_argument("--jev-model", default=DEFAULT_MODEL)
    p.add_argument("--planner-model", default=PLANNER_MODEL)
    p.add_argument("--replan-every", type=int, default=40, help="hybrid: ask the planner at least every N steps")
    p.add_argument("--confidence-threshold", type=float, default=0.3, help="hybrid: replan when Jev's confidence is below this")
    p.add_argument("--stuck-threshold", type=float, default=0.7, help="hybrid: replan when Jev's 'stuck' noul is at least this")
    p.add_argument("--min-replan-gap", type=int, default=5, help="hybrid: steps between confidence/stuck-triggered replans")
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
