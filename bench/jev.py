"""
Jev (TypeSafe "System One") as a benchmark player.

Jev does not generate text or call tools: it answers typed questions about a `state` (a Choice over
options we define, with a probability per option and a confidence). So code does what an agent CLI
does for itself: it reads the server's replies, enumerates the legal actions as a closed set, asks Jev
to pick one, executes it, and labels the outcome. That scaffolding is why Jev runs are a separate track.

    JevClient       HTTP client for POST https://api.typesafe.ai/v1/systemone (key: TYPESAFE_API_KEY only)
    MockJev         offline stand-in with the same answer shape (tests, --mock smoke runs)
    parse()         server reply text -> Obs (mode, map, battle, screen, events)
    *_options()     the candidate actions for each mode
    JevPolicy       builds the request, asks Jev, logs one decision record per question
    label_outcome() did the chosen action do what it is for? (the "correct" bit of the calibration record)
    summarize()     calls, latency, cost and the confidence-vs-correctness bins for report.py
    ClaudePlanner   Claude Haiku via `claude -p`: sets the objective (jev-hybrid)
    ROUTE           code-side objective list (jev-scripted)
    BattleAdvisor   server-side: battle('auto') turns decided by Jev (jev-battles)

API facts used here come from docs.typesafe.ai (API reference, Models, Confidence, Jev 1.13 jaggedness):
answers carry `choice`, `probabilities`, `confidence` = (n*p_max - 1)/(n - 1); `usage.input_tokens` is
billed at $0.042/MTok and output is free; 429/529 are retried with backoff; Choice options are capped
at 255 and the first option is slightly favoured, so the option order is shuffled per question.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"
PRICE_PER_MTOK = 0.042                     # input; output tokens are free
PLANNER_MODEL = "claude-haiku-4-5-20251001"
MAX_OPTIONS = 255


# ====================================================================== client
class JevError(RuntimeError):
    pass


class JevRateLimited(JevError):
    pass


@dataclass
class JevResult:
    answers: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float                      # the successful HTTP round trip
    wall_ms: float                         # including retries and backoff


class JevClient:
    """Minimal synchronous client for the System One endpoint (httpx, already a dependency of mcp)."""

    def __init__(self, model: str = DEFAULT_MODEL, api_key: Optional[str] = None, timeout: float = 30.0,
                 max_retries: int = 6, transport=None, sleep: Callable[[float], None] = time.sleep):
        import httpx
        key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise JevError("TYPESAFE_API_KEY is not set")
        self.model = model
        self.max_retries = max_retries
        self._sleep = sleep
        self._httpx = httpx
        self.http = httpx.Client(timeout=timeout, transport=transport,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def ask(self, state: Any, questions: dict[str, dict]) -> JevResult:
        body = {"state": state, "model": self.model, "questions": questions}
        start = time.perf_counter()
        delay = 1.0
        last = ""
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                r = self.http.post(API_URL, json=body)
            except self._httpx.TransportError as e:          # connection reset, timeout: retry
                last = f"{type(e).__name__}: {e}"
                self._sleep(delay)
                delay = min(delay * 2, 30)
                continue
            latency = (time.perf_counter() - t0) * 1000
            if r.status_code in (429, 529):
                last = f"{r.status_code}: {r.text[:200]}"
                if attempt == self.max_retries:
                    break
                try:
                    wait = float(r.headers.get("retry-after", "")) if r.headers.get("retry-after") else delay
                except ValueError:
                    wait = delay
                self._sleep(min(wait, 60))
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 400:
                raise JevError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            usage = data.get("usage") or {}
            return JevResult(answers=data.get("answers") or {}, model=data.get("model") or self.model,
                             input_tokens=int(usage.get("input_tokens", 0) or 0),
                             output_tokens=int(usage.get("output_tokens", 0) or 0),
                             latency_ms=round(latency, 1), wall_ms=round((time.perf_counter() - start) * 1000, 1))
        if last.startswith(("429", "529")):
            raise JevRateLimited(f"rate limited after {self.max_retries} retries ({last})")
        raise JevError(f"request failed after {self.max_retries} retries ({last})")

    def close(self) -> None:
        self.http.close()


def choice_confidence(probs: dict[str, float]) -> float:
    """TypeSafe's Choice confidence: (n * p_max - 1) / (n - 1), clamped to 0..1."""
    n = len(probs)
    if n < 2:
        return 1.0
    return max(0.0, min(1.0, (n * max(probs.values()) - 1) / (n - 1)))


class MockJev:
    """Offline stand-in for JevClient: same answer shape, no network. `policy(state, labels)` returns the
    label to pick (default: heuristic_policy); the pick gets probability `p` and the rest share 1 - p."""

    def __init__(self, model: str = "mock-jev", policy: Optional[Callable] = None, p: float = 0.6, seed: int = 0):
        self.model = model
        self.policy = policy or heuristic_policy
        self.p = p
        self.rng = random.Random(seed)
        self.calls = 0

    def ask(self, state: Any, questions: dict[str, dict]) -> JevResult:
        self.calls += 1
        answers: dict[str, Any] = {}
        for qid, q in questions.items():
            if q["type"] == "choice":
                labels = list(q["criteria"])
                pick = self.policy(state, labels)
                pick = pick if pick in labels else labels[0]
                p = self.p if len(labels) > 1 else 1.0
                rest = (1 - p) / max(len(labels) - 1, 1)
                probs = {lab: (p if lab == pick else rest) for lab in labels}
                answers[qid] = {"type": "choice", "choice": pick, "probabilities": probs,
                                "confidence": round(choice_confidence(probs), 4)}
            elif q["type"] == "noul":
                answers[qid] = {"type": "noul", "noul": 0.1}
            elif q["type"] == "score":
                answers[qid] = {"type": "score", "score": 0.0, "probabilities": {"0": 1.0}, "confidence": 1.0}
        size = len(json.dumps({"state": state, "questions": questions}))
        return JevResult(answers=answers, model=self.model, input_tokens=size // 4, output_tokens=10 * len(questions),
                         latency_ms=0.0, wall_ms=0.0)

    def close(self) -> None:
        pass


def heuristic_policy(state: Any, labels: list[str]) -> str:
    """What the mock picks: enough sense to get through the intro and keep moving in an offline smoke run."""
    screen = (state.get("screen") or "") if isinstance(state, dict) else ""
    prefer: list[str] = []
    if "NEW NAME" in screen:                                   # name lists: take the first preset name
        prefer.append("press DOWN then A")
    if "▶CONTINUE" in screen:
        prefer.append("press DOWN then A")
    prefer += ["auto-battle", "teach ", "follow the map route", "explore unvisited", "walk to ", "walk up to the person", "press A", "talk to"]
    recent = " ".join(state.get("recent_actions") or []) if isinstance(state, dict) else ""
    fresh = [lab for lab in labels if recent.count(lab + " ->") < 2] or labels
    for want in prefer:
        for lab in fresh:
            if lab.startswith(want):
                return lab
    return fresh[0]


# ====================================================================== parsing server replies
STATUS_RE = re.compile(r"^(?:f\d+ )?(?P<map>[^|\n]+?) \((?P<x>\d+),(?P<y>\d+)\) facing (?P<facing>\w+) \| (?P<party>[^|\n]+?) \| "
                       r"¥(?P<money>\d+) \| (?P<badges>\d+) badges", re.M)
BATTLE_RE = re.compile(r"^(?:f\d+ )?BATTLE \((?P<kind>[\w ]+)\): enemy (?P<enemy>.+?) \| you (?P<mine>.+?) \| (?P<menu>[^\n]+)$", re.M)
BATTLE_START_RE = re.compile(r"^(?:f\d+ )?BATTLE \((?P<kind>[\w ]+)\) starting", re.M)
MON_RE = re.compile(r"^(?P<name>.+?) L(?P<level>\d+) (?P<hp>\d+)/(?P<max_hp>\d+)(?P<rest>.*)$")
PARTY_RE = re.compile(r"^(?P<n>\d+)\. (?P<mon>.+?\d+/\d+[^\[\n]*(?:\[[^\]]*\])?)", re.M)
MOVE_RE = re.compile(r"^(?P<name>.+?) (?P<pp>\d+)pp(?P<dis> DISABLED)?$")
EXIT_RE = re.compile(r"\(\d+,\d+\)→([^,\n]+)")
MAP_ROW_RE = re.compile(r"^\s*(\d+) ([#.,NPDvT<>~^LoS:BXH]+)$")
WINDOW_RE = re.compile(r"window x(-?\d+)\.\.-?\d+ y(-?\d+)\.\.-?\d+")
CONN_RE = re.compile(r"(north|south|east|west) edge→([^,\n]+)")
HEAL_ITEMS = ("Potion", "Super Potion", "Hyper Potion", "Max Potion", "Full Restore", "Fresh Water", "Soda Pop", "Lemonade")
BALLS = ("Poké Ball", "Great Ball", "Ultra Ball")
REFUSALS = ("bad path", "no path", "cannot", "no walkable", "route to", "unknown", "nothing to talk", "no move", "no PP",
            "could not", "not in a battle", "already in", "bad token", "too many", "no buttons", "not reset")


def parse_mon(text: str) -> Optional[dict]:
    m = MON_RE.match(text.strip())
    if not m:
        return None
    name = m["name"].strip()
    species = name[name.index("(") + 1:-1] if name.endswith(")") and "(" in name else name
    rest = m["rest"]
    moves = []
    if "[" in rest and "]" in rest:
        for part in rest[rest.index("[") + 1:rest.rindex("]")].split(", "):
            mm = MOVE_RE.match(part.strip())
            if mm:
                moves.append({"name": mm["name"], "pp": int(mm["pp"]), "disabled": bool(mm["dis"])})
    status = rest.split("[", 1)[0].strip()
    return {"species": species, "name": name, "level": int(m["level"]), "hp": int(m["hp"]), "max_hp": int(m["max_hp"]),
            "status": status, "moves": moves}


def parse_party(text: str) -> list[dict]:
    out = []
    for m in PARTY_RE.finditer(text or ""):
        mon = parse_mon(m["mon"])
        if mon:
            mon["slot"] = int(m["n"])
            out.append(mon)
    return out


def parse_items(text: str) -> list[tuple[str, int]]:
    line = next((ln for ln in (text or "").splitlines() if ln.startswith("bag:")), "")
    out = []
    for part in line[4:].split(","):
        part = part.strip()
        if "×" in part:
            name, qty = part.rsplit("×", 1)
            out.append((name.strip(), int(qty) if qty.strip().isdigit() else 1))
    return out


@dataclass
class Obs:
    mode: str                                  # intro / battle_start / battle / faint_switch / prompt / dialogue / overworld / over / unknown
    text: str
    head: str = ""
    map: str = ""
    pos: Optional[tuple[int, int]] = None
    facing: str = ""
    badges: int = 0
    money: int = 0
    lead: str = ""
    battle: Optional[dict] = None
    screen: str = ""
    hint: str = ""
    events: list[str] = field(default_factory=list)
    exits: list[str] = field(default_factory=list)
    connections: list[tuple[str, str]] = field(default_factory=list)
    npcs: list[tuple[int, int]] = field(default_factory=list)
    balls: list[tuple[int, int]] = field(default_factory=list)    # item balls (also in npcs: talked to the same way)
    grid: dict = field(default_factory=dict)     # (x, y) -> map cell char, from a full map or a window view

    def key(self) -> tuple:
        """What counts as 'the game changed' for outcome labelling."""
        b = self.battle or {}
        return (self.mode, self.map, self.pos, self.facing, self.screen,
                json.dumps(b, sort_keys=True) if b else "")


def parse(text: str) -> Obs:
    text = text or ""
    lines = text.splitlines()
    head = lines[0] if lines else ""
    o = Obs(mode="unknown", text=text, head=head)
    for ln in lines:
        if ln.startswith("EVENT: "):
            o.events += [e.strip() for e in ln[7:].split(";") if e.strip()]
        elif ln.startswith("hint:"):
            o.hint = ln
        elif ln.startswith(("exits:", "exits here:")):
            o.exits = [e.strip() for e in EXIT_RE.findall(ln)]
        elif ln.startswith("connections:"):
            o.connections = [(d, m.strip()) for d, m in CONN_RE.findall(ln)]
    win = None
    for i, ln in enumerate(lines):
        m = MAP_ROW_RE.match(ln)
        if m:
            o.npcs += [(x, int(m[1])) for x, c in enumerate(m[2]) if c in "No"]
            o.balls += [(x, int(m[1])) for x, c in enumerate(m[2]) if c == "o"]
            o.grid.update({(x, int(m[1])): c for x, c in enumerate(m[2])})
        w = WINDOW_RE.search(ln)
        if w:
            win = (int(w[1]), int(w[2]), i)
    if win and not o.npcs:
        x0, y0, i0 = win
        for r, ln in enumerate(lines[i0 + 1:i0 + 10]):
            if not re.fullmatch(r"[#.,NPDvT<>~^LoS:BXH]{10}", ln):
                break
            o.npcs += [(x0 + x, y0 + r) for x, c in enumerate(ln) if c in "No"]
            o.balls += [(x0 + x, y0 + r) for x, c in enumerate(ln) if c == "o"]
            o.grid.update({(x0 + x, y0 + r): c for x, c in enumerate(ln)})
    if "screen:\n" in text:
        tail = text.split("screen:\n", 1)[1]
        o.screen = "\n".join(ln for ln in tail.splitlines() if not ln.startswith("hint:")).strip("\n")
    if "BUDGET EXHAUSTED" in text:
        o.mode = "over"
        return o
    if "intro/title" in text:
        o.mode = "prompt" if "▶" in o.screen else "intro"
        return o
    s = STATUS_RE.search(text)
    if s:
        o.map, o.pos, o.facing = s["map"].strip(), (int(s["x"]), int(s["y"])), s["facing"]
        o.badges, o.money, o.lead = int(s["badges"]), int(s["money"]), s["party"].strip()
    b = BATTLE_RE.search(text)
    if b:
        o.battle = {"kind": b["kind"], "enemy": parse_mon(b["enemy"]), "mine": parse_mon(b["mine"]), "menu": b["menu"]}
        low = text.lower()
        if "needs a decision" in head or "learn" in o.screen.lower() and "▶" in o.screen:
            o.mode = "prompt"
        elif "battle('switch'" in head or "bring out which" in low:
            o.mode = "faint_switch"
        elif "menu: FIGHT" in b["menu"] or "choose a move" in b["menu"]:
            o.mode = "battle"
        elif "Safari" in b["menu"]:
            o.mode = "battle"
        elif "▶" in o.screen:
            o.mode = "prompt"
        else:
            o.mode = "battle_start"                  # text or animation between turns: press A
        return o
    if BATTLE_START_RE.search(text):
        o.mode = "battle_start"
        return o
    if head.startswith("choice") or "needs a decision" in head or "▶" in o.screen:
        o.mode = "prompt"
    elif o.screen:
        o.mode = "dialogue"
    elif s:
        o.mode = "overworld"
    return o


# ====================================================================== candidate actions
@dataclass
class Option:
    label: str                       # what Jev sees as the option name (unique)
    tool: str                        # server tool
    args: dict
    desc: Optional[str] = None       # criteria text for the option (None = self-explanatory)
    then: list = field(default_factory=list)    # follow-up (tool, args) calls run only if the previous one did not stop early


AUTO = "(auto) "                               # history prefix of code-forced actions (never counted as a Jev repeat)


def drop_repeats(opts: list[Option], history: list[str], times: int = 3, keep: tuple[str, ...] = ()) -> list[Option]:
    """Code-side loop breaker: drop an option whose identical result already appeared `times` times in the recent
    history ("label -> result" lines). Forced actions (AUTO prefix) do not count; labels in `keep` are never dropped
    ("press A" on a YES/NO prompt is often the only way out). Never empties the set."""
    counts: dict[str, int] = {}
    for h in history:
        if not h.startswith(AUTO):
            counts[h] = counts.get(h, 0) + 1
    tired = {h.split(" -> ", 1)[0] for h, n in counts.items() if n >= times} - set(keep)
    kept = [o for o in opts if o.label not in tired]
    return kept or opts


def _dedupe(opts: list[Option]) -> list[Option]:
    seen, out = set(), []
    for o in opts:
        k = o.label.lower()
        if k not in seen:
            seen.add(k)
            out.append(o)
    return out[:MAX_OPTIONS]


def press_options(intro: bool = False) -> list[Option]:
    opts = [Option("press A", "press", {"buttons": "A"}, "confirm / YES / select the highlighted entry / advance text"),
            Option("press DOWN then A", "press", {"buttons": "DOWN A"}, "select the second entry / answer NO"),
            Option("press DOWN twice then A", "press", {"buttons": "DOWN DOWN A"}, "select the third entry"),
            Option("press DOWN three times then A", "press", {"buttons": "DOWN DOWN DOWN A"}, "select the fourth entry"),
            Option("press B", "press", {"buttons": "B"}, "back / cancel / close the menu")]
    if intro:
        opts += [Option("press START", "press", {"buttons": "START"}, "start the game from the title screen"),
                 Option("wait one second", "wait", {"frames": 60}, "let an animation or scene play")]
    return opts


CHOICE_RE = re.compile(r"^ {2,}(▶)?\s*(\S.*?)\s*$")


def choice_options(o: Obs) -> list[Option]:
    """A menu list on screen (an elevator's floors, a vendor's drinks): one 'choose <entry>' option per entry, with the
    presses from the ▶ cursor computed in code instead of Jev counting rows ("press DOWN twice then A")."""
    lines = (o.screen or o.text).splitlines()
    best: list = []
    run: list = []
    for ln in lines + [""]:
        m = CHOICE_RE.match(ln)
        if m and "  " not in m[2]:                  # one entry per row (not a two-column menu)
            run.append((bool(m[1]), m[2]))
            continue
        if len(run) >= 2 and any(c for c, _ in run) and not best:
            best = run
        run = []
    if not best:
        return []
    cur = next(i for i, (c, _) in enumerate(best) if c)
    out = []
    for i, (_, name) in enumerate(best):
        keys = ["DOWN"] * (i - cur) + ["UP"] * (cur - i) + ["A"]
        out.append(Option(f"choose {name}", "press", {"buttons": " ".join(keys)}, f"select '{name}' in the list on screen"))
    return out


BATTLE_CURES = {"PSN": ("Antidote",), "BRN": ("Burn Heal",), "PAR": ("Paralyze Heal",), "FRZ": ("Ice Heal",),
                "SLP": ("Awakening",)}


def battle_options(b: dict, party: list[dict], items: list[tuple[str, int]], allow_auto: bool = True,
                   only_switch: bool = False, run_note: str = "") -> list[Option]:
    """The legal battle actions. Switches name the species: Gen 1 reorders the party in battle, so slot numbers go
    stale ("PIDGEY is already out!"). The server's auto-battle scores moves with the damage formula (code, not Jev)."""
    mine, kind = b.get("mine") or {}, b.get("kind", "")
    active = (mine.get("species") or "").lower()
    opts: list[Option] = []
    if "Safari" in b.get("menu", ""):
        return [Option("throw a Safari Ball", "battle", {"action": "item"}, "try to catch it"),
                Option("throw bait", "battle", {"action": "bait"}, "it flees less but is harder to catch"),
                Option("throw a rock", "battle", {"action": "rock"}, "easier to catch but more likely to flee"),
                Option("run away", "battle", {"action": "run"}, "leave the encounter")]
    if not only_switch:
        if allow_auto:
            opts.append(Option("auto-battle", "battle", {"action": "auto"},
                               "the server picks the strongest move for this matchup each turn (Gen 1 damage formula, type "
                               "chart, accuracy) until the battle ends or HP is low; the usual choice when attacking"))
        for mv in mine.get("moves", []):
            if mv["pp"] > 0 and not mv.get("disabled"):
                opts.append(Option(f"use {mv['name']}", "battle", {"action": "fight", "target": mv["name"]},
                                   f"attack with {mv['name']} ({mv['pp']} PP left)"))
    for p in party:
        if p["hp"] <= 0 or p["species"].lower() == active:
            continue
        opts.append(Option(f"switch to {p['species']}", "battle", {"action": "switch", "target": p["species"]},
                           f"L{p['level']}, {p['hp']}/{p['max_hp']} HP, moves: " + ", ".join(m["name"] for m in p["moves"])))
    if only_switch:
        return _dedupe(opts)
    names = {n for n, _ in items}
    if _frac(mine) < 0.5:
        for h in HEAL_ITEMS:
            if h in names:
                opts.append(Option(f"use {h}", "battle", {"action": "item", "target": h}, "heal the Pokémon in battle"))
    # a fainted teammate revived and a status cured in battle (Codex review 16: bought Revives were only usable between
    # rooms, and a frozen or paralysed fighter at full HP had no option)
    revive = next((r for r in ("Max Revive", "Revive") if r in names), None)
    for p in party:
        if revive and p["hp"] <= 0:
            opts.append(Option(f"revive {p['species']} with a {revive}", "battle",
                               {"action": "item", "target": f"{revive}: {p['species']}"}, "back in the fight"))
    st = (mine.get("status") or "").split(" ")[0]
    cure = next((c for c in BATTLE_CURES.get(st, ()) + ("Full Heal", "Full Restore") if c in names), None) if st else None
    if cure:
        opts.append(Option(f"cure {mine.get('species', 'it')} ({st}) with {cure}", "battle",
                           {"action": "item", "target": cure}, "it cannot fight well like this"))
    if kind == "wild":
        ball = next((x for x in BALLS if x in names), None)
        if ball and len(party) < 4:                    # a small team: catching is worth an option
            opts.append(Option(f"throw a {ball}", "battle", {"action": "item", "target": ball}, "try to catch the wild Pokémon"))
        opts.append(Option("run away", "battle", {"action": "run"}, run_note or "flee from the wild Pokémon (no experience gained)"))
    return _dedupe(opts)


WALKABLE = set(".,:X")
STEP_TOWARD = {(0, -1): "down", (0, 1): "up", (-1, 0): "right", (1, 0): "left"}   # offset of the stand cell -> facing


def talk_to_options(o: Obs, grid: dict, limit: int = 10, said: Optional[dict] = None) -> list[Option]:
    """'talk to the person or object at (x,y)': stand on a free neighbouring cell, face it, talk. Objects on
    tables (Oak's Poké Balls) or behind counters are solid targets, so the walk goes to the neighbour."""
    out = []
    px, py = o.pos
    said = said or {}
    # untaken item balls first: a key item lies in one (Silph Co. 5F's Card Key, full run 62: offered as a plain
    # "person or object" among ten, Jev took the 4-tile walks ~1,400 times instead)
    balls = set(o.balls)
    for nx, ny in sorted(set(o.npcs), key=lambda n: (f"{n[0]},{n[1]}" in said, n not in balls,
                                                     abs(n[0] - px) + abs(n[1] - py)))[:limit]:
        # not a cell another person stands on (Cerulean Gym, iteration 37: a beaten trainer stood right below Misty)
        stands = [((nx + dx, ny + dy), face) for (dx, dy), face in STEP_TOWARD.items()
                  if (grid.get((nx + dx, ny + dy)) in WALKABLE and (nx + dx, ny + dy) not in o.npcs)
                  or (nx + dx, ny + dy) == (px, py)]
        if not stands:
            continue
        (sx, sy), face = min(stands, key=lambda s: abs(s[0][0] - px) + abs(s[0][1] - py))
        first = (Option("", "walk", {"path": f"{face} 1", "on_battle": "stop"}) if (sx, sy) == (px, py)
                 else Option("", "walk", {"path": f"to {sx},{sy}", "on_battle": "stop"}))
        then = [("walk", {"path": f"{face} 1", "on_battle": "stop"})] if (sx, sy) != (px, py) else []
        before = said.get(f"{nx},{ny}")
        ball = (nx, ny) in balls
        out.append(Option(f"talk to the person or object at ({nx},{ny})" + (" (an item ball: pick it up)" if ball else ""),
                          first.tool, first.args,
                          f"{abs(nx - px) + abs(ny - py)} tiles away; " + (f"already talked to it, it said: {before}" if before
                                                                            else "an item lying here, not taken yet" if ball
                                                                            else "not talked to yet"),
                          then=then + [("talk", {})]))
    return out


def overworld_options(o: Obs, exits: list[str], conns: list[tuple[str, str]], targets: list[str],
                      party: list[dict], items: list[tuple[str, int]], steps_since_save: int = 0,
                      grid: Optional[dict] = None, said: Optional[dict] = None, facing_said: str = "") -> list[Option]:
    opts: list[Option] = []
    for t in targets:
        if t and t != o.map:
            opts.append(Option(f"walk to {t}", "walk", {"path": f"to {t}", "on_battle": "stop"},
                               "a destination the current objective names (pathfinds across visited maps)"))
    for e in exits:
        opts.append(Option(f"walk to {e}", "walk", {"path": f"to {e}", "on_battle": "stop"}, "a door, stairway or exit on this map"))
    for side, dest in conns:
        opts.append(Option(f"walk to {dest} ({side} edge)", "walk", {"path": f"to {side} edge", "on_battle": "stop"},
                           f"leave this map by its {side} edge"))
    if o.pos:
        opts += talk_to_options(o, grid or o.grid, said=said)
    for d in ("up", "down", "left", "right"):
        opts.append(Option(f"walk {d} 4 tiles", "walk", {"path": f"{d} 4", "on_battle": "stop"}, "explore nearby"))
    opts.append(Option("talk to what you are facing", "talk", {}, "an NPC, sign, item ball, PC or nurse right in front of you"
                       + (f"; last time it said: {facing_said}" if facing_said else "")))
    names = {n for n, _ in items}
    lead = party[0] if party else None
    if lead and 0 < lead["hp"] < lead["max_hp"] // 2:   # (a potion cannot revive: Codex review 5)
        heal = next((h for h in HEAL_ITEMS if h in names), None)
        if heal:
            opts.append(Option(f"use a {heal} on {lead['species']}", "manage",
                               {"action": "use", "target": heal, "target2": lead["species"]}, "heal the lead Pokémon"))
    if steps_since_save >= 50:
        opts.append(Option("save the game", "manage", {"action": "save"}, "write an in-game save"))
    return _dedupe(opts)


# ====================================================================== outcome labelling
def _frac(m: Optional[dict]) -> float:
    return (m["hp"] / m["max_hp"]) if m and m.get("max_hp") else 0.0


def label_outcome(kind: str, opt: Option, before: Obs, after: Obs, repeat: bool = False) -> tuple[bool, str]:
    """Proxy for "was this the right call": the action was accepted and did what it is for. Battle moves must
    hurt the foe at least as much (as a share of max HP) as the turn hurt us; walks must move the player or
    start something (battle, dialogue); presses and talks must change the screen. Losing a battle is wrong, and an
    outside-battle action whose exact result already appeared twice in the recent history is not progress."""
    head = after.head.strip()
    low = head.lower()
    if any(low.startswith(r) for r in REFUSALS) or "is not on this map" in low or "is disabled" in low:
        return False, "refused"
    if any("blacked out" in e for e in after.events):
        return False, "blacked out"
    if kind in ("battle", "faint_switch"):
        if not after.battle:
            if opt.args.get("action") == "run" or "battle over" in low or after.mode == "overworld":
                return True, "battle over"
            return True, "battle ended"
        bm, am = (before.battle or {}).get("mine"), after.battle.get("mine")
        be, ae = (before.battle or {}).get("enemy"), after.battle.get("enemy")
        action = opt.args.get("action")
        if action == "switch":
            ok = bool(am and bm and am["species"] != bm["species"]) or kind == "faint_switch" and bool(am and am["hp"] > 0)
            return ok, "switched" if ok else "switch failed"
        if action == "run":
            return False, "could not escape"
        if action == "item":
            if opt.args.get("target") in BALLS:
                return False, "not caught"
            ok = bool(am and bm and am["hp"] > bm["hp"])
            return ok, "healed" if ok else "item had no effect"
        if after.mode == "faint_switch" or "fainted" in after.text and am and am["hp"] == 0:
            return False, "our Pokémon fainted"
        e_drop = 1.0 if (be and ae and ae["species"] != be["species"]) else _frac(be) - _frac(ae)
        m_drop = _frac(bm) - _frac(am) if (bm and am and am["species"] == bm["species"]) else 0.0
        ok = e_drop > 0 and e_drop >= m_drop
        return ok, f"foe -{e_drop:.0%} vs us -{m_drop:.0%}"
    if repeat:
        return False, "repeats a recent result"
    if opt.tool == "walk":
        if after.mode in ("battle", "battle_start", "dialogue", "prompt"):
            return True, "something started"
        moved = after.map != before.map or after.pos != before.pos
        return moved, "moved" if moved else "did not move"
    if "(screen image unchanged)" in after.text:
        return False, "no change"
    changed = after.key() != before.key() or opt.tool in ("press", "wait") and "(screen image unchanged)" not in after.text
    return changed, "changed" if changed else "no change"


# ====================================================================== the policy
@dataclass
class Decision:
    option: Option
    record: dict
    noul: dict[str, float] = field(default_factory=dict)


class JevPolicy:
    """Asks Jev to pick one Option and logs one JSON line per decision (outcome added after execution)."""

    INSTRUCTIONS = ("You are playing Pokémon Red. Which action should the player take next to make progress toward "
                    "`objective`? Read `location`, `map_route`, `hint` and `last_result`. An option starting with 'follow the "
                    "map route' is the next step of the shortest path in the game's map data toward the objective: take it "
                    "unless `recent_actions` show it just failed. Avoid repeating actions from `recent_actions` that failed "
                    "or changed nothing.")
    BATTLE_INSTRUCTIONS = ("You are playing a Pokémon Red battle. Which action gives the best chance to win this battle "
                           "(or, against a wild Pokémon you do not need, to end it safely)? auto-battle attacks with the "
                           "move code rates strongest for the matchup; switch out a Pokémon that is about to faint if a "
                           "healthier one is available; follow what the 'run away' option says about fleeing.")

    def __init__(self, client, log_path: Optional[Path] = None, variant: str = "", seed: int = 0,
                 price_per_mtok: float = PRICE_PER_MTOK):
        self.client = client
        self.log_path = Path(log_path) if log_path else None
        self.variant = variant
        self.rng = random.Random(seed)
        self.price = price_per_mtok
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.latencies: list[float] = []

    def decide(self, kind: str, state: dict, options: list[Option], step: int = 0, nouls: Optional[dict[str, str]] = None,
               battle: bool = False) -> Decision:
        rec: dict[str, Any] = {"t": round(time.time(), 1), "step": step, "variant": self.variant, "kind": kind,
                               "n_options": len(options), "objective": state.get("objective", "")}
        if len(options) == 1:
            rec.update(choice=options[0].label, forced=True)
            return Decision(options[0], rec)
        order = options[:]
        self.rng.shuffle(order)                     # Jev 1.13 leans toward the first option: never favour one systematically
        by_label = {o.label: o for o in order}
        questions: dict[str, dict] = {"action": {"type": "choice",
                                                 "instructions": self.BATTLE_INSTRUCTIONS if battle else self.INSTRUCTIONS,
                                                 "criteria": {o.label: o.desc for o in order}}}
        for qid, text in (nouls or {}).items():
            questions[qid] = {"type": "noul", "instructions": text}
        res = self.client.ask(state, questions)
        self.calls += 1
        self.input_tokens += res.input_tokens
        self.output_tokens += res.output_tokens
        cost = res.input_tokens * self.price / 1e6
        self.cost_usd += cost
        self.latencies.append(res.latency_ms)
        a = res.answers.get("action") or {}
        probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
        choice = a.get("choice") if a.get("choice") in by_label else (max(probs, key=probs.get) if probs else order[0].label)
        if choice not in by_label:
            choice = order[0].label
        ranked = sorted(probs.values(), reverse=True)
        p = probs.get(choice, ranked[0] if ranked else 0.0)
        conf = float(a["confidence"]) if a.get("confidence") is not None else choice_confidence(probs or {choice: 1.0})
        rec.update(choice=choice, p=round(p, 4), confidence=round(conf, 4), probs={k: round(v, 4) for k, v in probs.items()},
                   ratio=round(p / ranked[1], 3) if len(ranked) > 1 and ranked[1] > 0 else None,
                   position=[o.label for o in order].index(choice), latency_ms=res.latency_ms, wall_ms=res.wall_ms,
                   input_tokens=res.input_tokens, cost_usd=round(cost, 8), model=res.model, forced=False)
        noul = {qid: float((res.answers.get(qid) or {}).get("noul", 0.0)) for qid in (nouls or {})}
        if noul:
            rec["nouls"] = {k: round(v, 3) for k, v in noul.items()}
        return Decision(by_label[choice], rec, noul)

    def log(self, rec: dict) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ====================================================================== summary for report.py
def _pct(xs: list[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 1)


def read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def summarize(decisions: list[dict], planner: Optional[list[dict]] = None, bins: int = 10) -> dict:
    """Totals plus calibration bins (by Jev's own confidence) of the decisions whose outcome was labelled."""
    asked = [r for r in decisions if not r.get("forced")]
    scored = [r for r in asked if r.get("correct") is not None and not r.get("superseded")]
    lat = [r["latency_ms"] for r in asked if r.get("latency_ms") is not None]
    cal = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        xs = [r for r in scored if lo <= r["confidence"] < hi or (i == bins - 1 and r["confidence"] >= 1.0)]
        if xs:
            cal.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": len(xs),
                        "mean_conf": round(sum(r["confidence"] for r in xs) / len(xs), 3),
                        "mean_p": round(sum(r["p"] for r in xs) / len(xs), 3),
                        "accuracy": round(sum(1 for r in xs if r["correct"]) / len(xs), 3)})
    n = len(scored)
    ece = round(sum(b["n"] / n * abs(b["accuracy"] - b["mean_p"]) for b in cal), 4) if n else None
    kinds: dict[str, dict] = {}
    for r in scored:
        k = kinds.setdefault(r["kind"], {"n": 0, "correct": 0, "conf": 0.0})
        k["n"] += 1
        k["correct"] += 1 if r["correct"] else 0
        k["conf"] += r["confidence"]
    by_kind = {k: {"n": v["n"], "accuracy": round(v["correct"] / v["n"], 3), "mean_conf": round(v["conf"] / v["n"], 3)}
               for k, v in sorted(kinds.items())}
    pl = planner or []
    return {"decisions": len(decisions), "jev_calls": len(asked), "forced": len(decisions) - len(asked), "scored": n,
            "accuracy": round(sum(1 for r in scored if r["correct"]) / n, 3) if n else None,
            "input_tokens": sum(int(r.get("input_tokens", 0) or 0) for r in asked),
            "jev_cost_usd": round(sum(float(r.get("cost_usd", 0) or 0) for r in asked), 6),
            "latency_ms": {"mean": round(sum(lat) / len(lat), 1) if lat else None, "p50": _pct(lat, 0.5),
                           "p95": _pct(lat, 0.95), "max": round(max(lat), 1) if lat else None},
            "calibration": cal, "ece": ece, "by_kind": by_kind,
            "models": sorted({r["model"] for r in asked if r.get("model")}),
            "planner_calls": len(pl), "planner_cost_usd": round(sum(float(p.get("cost_usd") or 0) for p in pl), 6),
            "planner_errors": sum(1 for p in pl if p.get("error"))}


# ====================================================================== planner (jev-hybrid)
PLANNER_PROMPT = """You are the planner for an automated Pokémon Red player. A fast decision model picks every button/walk action; you only set the current objective. Reply with ONLY a JSON object:
{{"objective": "<one sentence: what to do next and why>", "targets": ["<up to 5 place names to walk to, best first>"]}}
Targets must be map or building names written exactly as they appear below (exits, connections, visited maps), e.g. "Viridian Mart", "Route 2", "Pewter Poké Center". Heal at a Poké Center when the team is weak; train before gyms.

Why you are asked now: {reason}
Current objective: {objective}

{situation}"""


@dataclass
class Plan:
    objective: str
    targets: list[str]
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str = ""


def parse_plan(text: str) -> Optional[tuple[str, list[str]]]:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    obj = str(d.get("objective") or "").strip()
    targets = [str(t).strip() for t in (d.get("targets") or []) if str(t).strip()][:5]
    return (obj[:400], targets) if obj else None


class ClaudePlanner:
    """One-shot `claude -p` calls with no tools and no MCP servers; the CLI reports its own cost."""

    def __init__(self, model: str = PLANNER_MODEL, timeout: float = 180.0, runner: Callable = subprocess.run):
        self.model = model
        self.timeout = timeout
        self.runner = runner

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def plan(self, reason: str, objective: str, situation: str) -> Plan:
        prompt = PLANNER_PROMPT.format(reason=reason, objective=objective or "(none yet)", situation=situation)
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "json", "--tools", "",
               "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}']
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        t0 = time.perf_counter()
        try:
            out = self.runner(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, env=env)
        except (subprocess.TimeoutExpired, OSError) as e:
            return Plan(objective, [], error=f"{type(e).__name__}: {e}"[:300])
        ms = round((time.perf_counter() - t0) * 1000, 1)
        try:
            d = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {}
        except ValueError:
            d = {}
        u = d.get("usage") or {}
        tokens = {"input": int(u.get("input_tokens", 0) or 0), "cached_input": int(u.get("cache_read_input_tokens", 0) or 0),
                  "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0), "output": int(u.get("output_tokens", 0) or 0)}
        cost = float(d.get("total_cost_usd") or 0.0)
        parsed = parse_plan(str(d.get("result") or "")) if not d.get("is_error") else None
        if not parsed:
            err = str(d.get("result") or out.stderr or "no JSON plan in reply")[:300]
            return Plan(objective, [], cost, tokens, ms, error=err)
        return Plan(parsed[0], parsed[1], cost, tokens, ms)


class MockPlanner:
    """Offline planner: walks the scripted ROUTE (so --mock smoke runs exercise the replanning path)."""

    model = "mock-planner"

    def available(self) -> bool:
        return True

    def plan(self, reason: str, objective: str, situation: str, milestones: Optional[list[str]] = None) -> Plan:
        step = route_step(milestones or [])
        return Plan(step[0], list(step[1]), 0.0, {}, 0.0)


# ====================================================================== scripted route (jev-scripted)
# (objective, walk targets, done when a milestone starting with this text has been seen)
ROUTE: list[tuple[str, tuple[str, ...], str]] = [
    ("Start a new game: get through the title screen and Professor Oak's introduction.", (), "game started"),
    ("Leave your house and walk north out of Pallet Town; Professor Oak stops you and takes you to his lab to choose a starter.",
     ("Pallet Town", "Route 1", "Oak's Lab"), "starter:"),
    ("Leave Oak's lab and go north along Route 1 to Viridian City.", ("Route 1", "Viridian City"), "reached: Viridian City"),
    ("Pick up Oak's Parcel at the Viridian Mart, bring it to Oak in Pallet Town, then go north via Route 2 into Viridian Forest.",
     ("Viridian Mart", "Pallet Town", "Oak's Lab", "Route 2", "Viridian Forest"), "reached: Viridian Forest"),
    ("Get through Viridian Forest to Pewter City.", ("Route 2", "Pewter City"), "reached: Pewter City"),
    ("Level up your team, heal, and beat Brock at the Pewter Gym.", ("Pewter Poké Center", "Pewter Gym"), "badge: Boulder"),
    ("Travel east along Route 3 to Mt. Moon.", ("Route 3", "Route 4", "Mt. Moon 1F"), "reached: Mt. Moon 1F"),
    ("Get through Mt. Moon and continue to Cerulean City.", ("Route 4", "Cerulean City"), "reached: Cerulean City"),
    ("Heal, then beat Misty at the Cerulean Gym.", ("Cerulean Poké Center", "Cerulean Gym"), "badge: Cascade"),
    ("Visit Bill on Route 25 for the S.S. Ticket, then go south via Route 5, the Underground Path and Route 6 to Vermilion City.",
     ("Route 24", "Route 25", "Route 5", "Route 6", "Vermilion City"), "reached: Vermilion City"),
    ("Board the S.S. Anne at Vermilion harbor and get HM01 (Cut) from the captain.", ("S.S. Anne 1F",), "reached: S.S. Anne 1F"),
    ("Teach Cut, cut the tree in front of the Vermilion Gym and beat Lt. Surge.", ("Vermilion Gym",), "badge: Thunder"),
    ("Go east via Route 11/Diglett's Cave or Route 9 to Rock Tunnel and through it to Lavender Town.",
     ("Route 9", "Route 10", "Rock Tunnel 1F", "Lavender Town"), "reached: Lavender Town"),
    ("Go west via Route 8, the Underground Path and Route 7 to Celadon City.", ("Route 8", "Route 7", "Celadon City"),
     "reached: Celadon City"),
    ("Beat Erika at the Celadon Gym.", ("Celadon Gym",), "badge: Rainbow"),
    ("Clear the Rocket Hideout under the Celadon Game Corner and get the Silph Scope.", ("Rocket Hideout B1F",),
     "reached: Rocket Hideout B1F"),
    ("Climb Pokémon Tower in Lavender Town with the Silph Scope and rescue Mr. Fuji.", ("Pokémon Tower 1F",),
     "reached: Pokémon Tower 1F"),
    ("Get the Poké Flute, wake Snorlax and travel to Fuchsia City.", ("Fuchsia City",), "reached: Fuchsia City"),
    ("Beat Koga at the Fuchsia Gym.", ("Fuchsia Gym",), "badge: Soul"),
    ("Get HM03 Surf in the Safari Zone and the HM04 Strength from the warden.", ("Safari Zone Gate",), "reached: Safari Zone Gate"),
    ("Clear Silph Co. in Saffron City.", ("Saffron City", "Silph Co. 1F"), "reached: Silph Co. 1F"),
    ("Beat Sabrina at the Saffron Gym.", ("Saffron Gym",), "badge: Marsh"),
    ("Surf south to Cinnabar Island.", ("Seafoam Islands 1F", "Cinnabar Island"), "reached: Cinnabar Island"),
    ("Find the Secret Key in the Pokémon Mansion and beat Blaine at the Cinnabar Gym.", ("Pokémon Mansion 1F", "Cinnabar Gym"),
     "badge: Volcano"),
    ("Beat Giovanni at the Viridian Gym.", ("Viridian Gym",), "badge: Earth"),
    ("Go west from Viridian City along Route 22 and north on Route 23 through Victory Road to Indigo Plateau.",
     ("Route 22", "Route 23", "Victory Road 1F", "Indigo Plateau Lobby"), "reached: Indigo Plateau Lobby"),
    ("Beat the Elite Four and the Champion.", ("Indigo Plateau Lobby",), "champion defeated"),
]


def route_step(milestones: list[str]) -> tuple[str, tuple[str, ...], str]:
    for step in ROUTE:
        if not any(m.startswith(step[2]) for m in milestones):
            return step
    return ROUTE[-1]


# ====================================================================== battle advisor (jev-battles, in the server)
class BattleAdvisor:
    """Replaces battle('auto') in the server: Jev picks every turn (move, switch, item, run) from the legal set.
    Explicit battle('fight'/'switch'/...) calls from the CLI agent pass through unchanged."""

    def __init__(self, client, log_path: Path, seed: int = 0):
        self.policy = JevPolicy(client, log_path, variant="battles", seed=seed)
        self.step = 0

    @staticmethod
    def _norm(b: Optional[dict]) -> Optional[dict]:
        if not b:
            return None
        def mon(m):
            return {"species": m["species"], "level": m["level"], "hp": m["hp"], "max_hp": m["max_hp"], "status": m.get("status", ""),
                    "types": m.get("types", []), "moves": [{"name": n, "pp": pp, "disabled": n == m.get("disabled")} for n, pp in m["moves"]]}
        return {"kind": b["kind"], "enemy": mon(b["enemy"]), "mine": mon(b["mine"])}

    def _state(self, b: dict, party: list[dict], log: list[str]) -> dict:
        e, m = b["enemy"], b["mine"]
        return {"battle": {"kind": b["kind"],
                           "enemy": f"{e['species']} L{e['level']} ({'/'.join(e['types'])}) {round(100 * _frac(e))}% HP {e['status']}".strip(),
                           "your_pokemon": f"{m['species']} L{m['level']} ({'/'.join(m['types'])}) {m['hp']}/{m['max_hp']} HP {m['status']}".strip(),
                           "your_moves": [f"{mv['name']} {mv['pp']}pp" + (" DISABLED" if mv["disabled"] else "") for mv in m["moves"]]},
                "party": [f"{p['slot']}. {p['species']} L{p['level']} {p['hp']}/{p['max_hp']} HP" for p in party],
                "this_battle_so_far": log[-6:]}

    def auto(self, emu, target: str = "") -> str:
        prof = emu.profile
        logs: list[str] = []
        if prof.in_battle() and prof.in_safari_battle():
            return prof.battle_action(emu, "auto", target)
        for _ in range(40):
            if not prof.in_battle():
                break
            kind, pre = prof._wait_menu(emu)
            if pre:
                logs.append(pre)
            if kind in ("over", "prompt", "stuck") or not prof.in_battle():
                if kind == "prompt":
                    logs.append("needs a decision — answer with press (A = YES / first option, DOWN A = NO)")
                break
            raw = prof.battle()
            b = self._norm(raw)
            if not b or b["mine"]["max_hp"] == 0:
                break
            party = [{"slot": i + 1, "species": p["species"], "level": p["level"], "hp": p["hp"], "max_hp": p["max_hp"],
                      "moves": [{"name": n, "pp": pp} for n, pp in p["moves"]]} for i, p in enumerate(prof.party())]
            items = prof.items()
            only_switch = kind == "choose"
            opts = battle_options(b, party, items, allow_auto=False, only_switch=only_switch)
            if not opts:
                break
            self.step += 1
            kind_label = "faint_switch" if only_switch else "battle"
            dec = self.policy.decide(kind_label, self._state(b, party, logs), opts, step=self.step, battle=True)
            before = Obs(mode=kind_label, text="", battle=b)
            head = emu.battle(dec.option.args["action"], dec.option.args.get("target", ""))
            logs.append(f"[Jev: {dec.option.label}] {head}")
            after = Obs(mode="battle" if prof.in_battle() else "overworld", text=head, head=head.split("\n", 1)[0],
                        battle=self._norm(prof.battle()) if prof.in_battle() else None)
            if "battle('switch'" in head:
                after.mode = "faint_switch"
            if not dec.record.get("forced"):
                ok, why = label_outcome(kind_label, dec.option, before, after)
                dec.record.update(correct=ok, outcome=why)
            self.policy.log(dec.record)
            if "needs a decision" in head:
                break
        return " | ".join(x for x in logs if x) or "not in a battle"


def make_client(model: str, mock: bool, seed: int = 0):
    return MockJev(seed=seed) if mock else JevClient(model)


# ====================================================================== fallback chooser (jev-assist)
CHOOSER_PROMPT = """You are the safety net for an automated Pokémon Red player. A fast decision model usually picks every action; this time it was unsure or the player looks stuck ({trigger}). Pick the best action from the numbered list. Reply with ONLY a JSON object: {{"choice": <number>, "why": "<one short sentence>"}}

Objective: {objective}

Situation (JSON):
{state}

The fast model's probabilities are shown after each option.
Options:
{options}"""


@dataclass
class Fallback:
    label: str
    why: str = ""
    cost_usd: float = 0.0
    tokens: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str = ""
    model: str = ""


class ClaudeChooser:
    """One `claude -p` call (no tools, no MCP) that picks one option of the same closed set Jev saw."""

    def __init__(self, model: str = PLANNER_MODEL, timeout: float = 120.0, runner: Callable = subprocess.run):
        self.model = model
        self.timeout = timeout
        self.runner = runner

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def choose(self, trigger: str, objective: str, state: dict, options: list[Option], probs: dict[str, float]) -> Fallback:
        lines = "\n".join(f"{i + 1}. {o.label}" + (f" — {o.desc}" if o.desc else "") + f" [p={probs.get(o.label, 0):.2f}]"
                          for i, o in enumerate(options))
        prompt = CHOOSER_PROMPT.format(trigger=trigger, objective=objective,
                                       state=json.dumps(state, ensure_ascii=False)[:6000], options=lines)
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "json", "--tools", "",
               "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}']
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
        t0 = time.perf_counter()
        try:
            out = self.runner(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, env=env)
        except (subprocess.TimeoutExpired, OSError) as e:
            return Fallback("", error=f"{type(e).__name__}: {e}"[:300], model=self.model)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        try:
            d = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {}
        except ValueError:
            d = {}
        u = d.get("usage") or {}
        tokens = {"input": int(u.get("input_tokens", 0) or 0), "cached_input": int(u.get("cache_read_input_tokens", 0) or 0),
                  "cache_write": int(u.get("cache_creation_input_tokens", 0) or 0), "output": int(u.get("output_tokens", 0) or 0)}
        cost = float(d.get("total_cost_usd") or 0.0)
        m = re.search(r"\{.*\}", str(d.get("result") or ""), re.S)
        try:
            pick = json.loads(m.group(0)) if m else {}
            n = int(pick.get("choice"))
            label = options[n - 1].label if 1 <= n <= len(options) else ""
        except (ValueError, TypeError):
            pick, label = {}, ""
        err = "" if label else f"no valid choice in reply: {str(d.get('result') or out.stderr)[:200]}"
        return Fallback(label, str(pick.get("why") or "")[:300], cost, tokens, ms, err, self.model)


class MockChooser:
    """Offline chooser: Jev's runner-up (so tests and --mock runs see the fallback change the action)."""
    model = "mock-chooser"

    def available(self) -> bool:
        return True

    def choose(self, trigger, objective, state, options, probs) -> Fallback:
        ranked = sorted(options, key=lambda o: -probs.get(o.label, 0))
        pick = ranked[1] if len(ranked) > 1 else ranked[0]
        return Fallback(pick.label, "mock: runner-up", 0.0, {}, 0.0, "", self.model)


def summarize_fallbacks(events: list[dict], steps: Optional[int]) -> dict:
    n = len(events)
    trig: dict[str, int] = {}
    for e in events:
        trig[e.get("trigger", "?")] = trig.get(e.get("trigger", "?"), 0) + 1
    done = [e for e in events if (e.get("outcome_after") or {}).get("complete")]
    return {"fallbacks": n, "fallbacks_per_1k_steps": round(1000 * n / steps, 2) if steps else None, "by_trigger": trig,
            "fallback_cost_usd": round(sum(float(e.get("cost_usd") or 0) for e in events), 6),
            "fallback_agreed_with_jev": sum(1 for e in events if e.get("agreed")),
            "fallback_errors": sum(1 for e in events if e.get("error")),
            "fallback_progress_rate": round(sum(1 for e in done if e["outcome_after"].get("progress")) / len(done), 3) if done else None}
