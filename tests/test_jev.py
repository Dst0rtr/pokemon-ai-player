"""Jev provider track: HTTP client (mocked transport), parsers, candidates, policy, labels, calibration summary,
solo objective graph, agent loop (fake server and the real one over MCP), harness glue. No network."""

import asyncio
import json
import os
import shutil
import sys
import types

import httpx
import pytest

from bench import jev as J
from bench import jev_solo as SOLO
from bench.jev_agent import Agent
from bench.report import build_results_md, derive
from bench.stream import ChunkStats
from tests.conftest import ROOT, requires_rom

PEWTER = """'Route 3' → (39,17): arrived
f357 Pewter City (16,18) facing down | Butterfree L15 20/47 (+Charmeleon L20, Pidgey L10) | ¥1913 | 1 badges
EVENT: reached: Pewter City
Pewter City 6x4, you at (2,2) facing down. x→ right, y↓ down. P=you N=npc D=door/warp #=blocked .=walkable
   012345
 0 ##D###
 1 #..N.#
 2 #.P..#
 3 #....#
exits: (2,0)→Pewter Mart, (14,7)→Pewter Museum 1F
connections: south edge→Route 2, east edge→Route 3"""
BATTLE = ("turn done (enemy 30→2, you 20→20)\nf3080 BATTLE (trainer): enemy Caterpie L10 2/30 | you Butterfree L15 20/47 "
          "[Tackle 35pp, String Shot 0pp, Confusion 12pp DISABLED, PoisonPowder 35pp] | menu: FIGHT/PKMN/ITEM/RUN (cursor on FIGHT)")
PARTY = """party:
1. Butterfree L15 20/47 [Tackle 35pp, Confusion 13pp] Bug/Flying atk24 def25 spd28 spc34
2. Charmeleon L20 57/57 PSN [Scratch 35pp, Ember 25pp] Fire atk34 def32 spd47 spc37
3. Pidgey L10 0/30 [Gust 35pp] Normal/Flying atk15 def14 spd16 spc13"""


# ---------------------------------------------------------------- HTTP client
def _client(handler, **kw):
    return J.JevClient("jev-latest", api_key="test-key-123", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_client_sends_documented_request_and_parses_answer():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json={"model": "jev-1.13.0", "usage": {"input_tokens": 318, "output_tokens": 34},
                                         "answers": {"action": {"type": "choice", "choice": "b", "confidence": 0.81,
                                                                "probabilities": {"a": 0.12, "b": 0.88}}}})
    res = _client(handler).ask({"x": 1}, {"action": {"type": "choice", "instructions": "?", "criteria": {"a": None, "b": None}}})
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone" and seen["auth"] == "Bearer test-key-123"
    assert seen["body"] == {"state": {"x": 1}, "model": "jev-latest",
                            "questions": {"action": {"type": "choice", "instructions": "?", "criteria": {"a": None, "b": None}}}}
    assert res.model == "jev-1.13.0" and res.input_tokens == 318 and res.answers["action"]["choice"] == "b"


def test_client_retries_429_then_gives_up_without_leaking_the_key():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"retry-after": "1"}, text="slow down")
    with pytest.raises(J.JevRateLimited) as e:
        _client(handler, max_retries=2).ask("s", {})
    assert len(calls) == 3 and "test-key-123" not in str(e.value)

    n = []

    def flaky(req):
        n.append(1)
        if len(n) < 3:
            return httpx.Response(529)
        return httpx.Response(200, json={"model": "m", "answers": {}, "usage": {"input_tokens": 1}})
    assert _client(flaky).ask("s", {}).input_tokens == 1 and len(n) == 3
    with pytest.raises(J.JevError, match="HTTP 401"):
        _client(lambda r: httpx.Response(401, text="bad key")).ask("s", {})


def test_client_needs_the_env_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(J.JevError, match="TYPESAFE_API_KEY"):
        J.JevClient()


def test_choice_confidence_matches_the_docs():
    assert abs(J.choice_confidence({"a": 0.6, "b": 0.3, "c": 0.1}) - 0.4) < 1e-9
    assert J.choice_confidence({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}) == 0.0


# ---------------------------------------------------------------- parsing and candidates
def test_parse_overworld_map_exits_connections_npcs():
    o = J.parse(PEWTER)
    assert o.mode == "overworld" and o.map == "Pewter City" and o.pos == (16, 18) and o.badges == 1 and o.money == 1913
    assert o.exits == ["Pewter Mart", "Pewter Museum 1F"] and ("east", "Route 3") in o.connections
    assert o.npcs == [(3, 1)] and o.grid[(2, 0)] == "D" and o.events == ["reached: Pewter City"]
    w = J.parse("walked down 3/3\nf83 Pewter Gym (4,5) facing down | X L5 1/2 | ¥1 | 0 badges\n"
                "Pewter Gym (4,5) facing down, window x0..9 y1..9\n" + "\n".join(["#...N....#"] + [".........."] * 8))
    assert (4, 1) in w.npcs and w.grid[(0, 1)] == "#"


def test_parse_battle_party_items_and_prompts():
    o = J.parse(BATTLE)
    assert o.mode == "battle" and o.battle["kind"] == "trainer" and o.battle["enemy"]["hp"] == 2
    mv = {m["name"]: m for m in o.battle["mine"]["moves"]}
    assert mv["Confusion"]["disabled"] and mv["String Shot"]["pp"] == 0
    party = J.parse_party(PARTY)
    assert [p["slot"] for p in party] == [1, 2, 3] and party[1]["status"] == "PSN" and party[2]["hp"] == 0
    assert J.parse_items("bag: Poké Ball×4, TM34×1, Potion×2") == [("Poké Ball", 4), ("TM34", 1), ("Potion", 2)]
    assert J.parse("needs a decision: learn?\nf1 BATTLE (wild): enemy A L2 1/9 | you B L3 4/9 [Tackle 3pp] | menu: x").mode == "prompt"
    assert J.parse("talk\nf1 Red's House 2F (3,6) facing up | B L5 20/20 | ¥3000 | 0 badges\nscreen:\nHello!").mode == "dialogue"
    assert J.parse("x\nBUDGET EXHAUSTED: tool-call budget").mode == "over"
    assert J.parse("pressed A\nf9 intro/title (no map loaded yet)").mode == "intro"


def test_battle_options_are_the_legal_set():
    o = J.parse(BATTLE)
    party = J.parse_party(PARTY)
    labels = [x.label for x in J.battle_options(o.battle, party, [("Potion", 1), ("Poké Ball", 3)])]
    assert labels[0] == "auto-battle" and "use Tackle" in labels and "use PoisonPowder" in labels
    assert "use String Shot" not in labels and "use Confusion" not in labels           # no PP / disabled
    assert "switch to Charmeleon" in labels and "switch to Pidgey" not in labels and "switch to Butterfree" not in labels
    assert "use Potion" in labels and "throw a Poké Ball" not in labels and "run away" not in labels   # trainer battle
    o.battle["kind"] = "wild"
    wild = [x.label for x in J.battle_options(o.battle, party, [("Poké Ball", 3)], allow_auto=False)]
    assert "throw a Poké Ball" in wild and "run away" in wild and "auto-battle" not in wild
    sw = J.battle_options(o.battle, party, [], only_switch=True)
    assert [x.label for x in sw] == ["switch to Charmeleon"] and sw[0].args == {"action": "switch", "target": "2"}
    safari = dict(o.battle, menu="menu: BALL/BAIT/ROCK/RUN (Safari: cursor on BALL)")
    assert [x.args["action"] for x in J.battle_options(safari, party, [])] == ["item", "bait", "rock", "run"]


def test_overworld_options_and_talk_to_objects_on_tables():
    o = J.parse(PEWTER)
    o.pos = (2, 2)
    opts = J.overworld_options(o, o.exits, o.connections, ["Route 3", "Pewter City"], J.parse_party(PARTY), [("Potion", 1)])
    labels = [x.label for x in opts]
    assert labels[0] == "walk to Route 3" and "walk to Pewter City" not in labels       # already there
    assert "walk to Route 2 (south edge)" in labels and "use a Potion on Butterfree" in labels
    talk = next(x for x in opts if x.label.startswith("talk to the person"))
    assert talk.args == {"path": "to 3,2", "on_battle": "stop"}                         # stand below the NPC at (3,1)...
    assert talk.then == [("walk", {"path": "up 1", "on_battle": "stop"}), ("talk", {})]    # ...face it, talk
    o.npcs, o.grid[(3, 2)] = [(3, 1)], "#"                                              # below is solid: stand left instead
    talk = next(x for x in J.talk_to_options(o, o.grid))
    assert talk.args["path"] == "to 2,1" and talk.then[0][1]["path"] == "right 1"


def test_drop_repeats_and_talk_memory():
    opts = [J.Option(x, "talk", {}) for x in ("talk to what you are facing", "walk to A")]
    hist = ["talk to what you are facing -> dialogue ended: BLUE: Heh"] * 3 + ["walk to A -> moved"]
    assert [o.label for o in J.drop_repeats(opts, hist)] == ["walk to A"]
    assert J.drop_repeats(opts[:1], hist) == opts[:1]                                 # never empties the set
    o = J.parse(PEWTER)
    o.pos, o.npcs = (1, 3), [(3, 1), (4, 3)]
    t = J.talk_to_options(o, o.grid, said={"3,1": "BLUE: Heh"})
    assert t[0].label.endswith("(4,3)") and "not talked to yet" in t[0].desc and "BLUE: Heh" in t[1].desc


# ---------------------------------------------------------------- policy, labels, summary
def test_policy_shuffles_logs_and_forces_single_options(tmp_path):
    log = tmp_path / "d.jsonl"
    pol = J.JevPolicy(J.MockJev(policy=lambda s, labels: "b"), log, variant="t", seed=1)
    opts = [J.Option(x, "press", {"buttons": "A"}) for x in "abcd"]
    dec = pol.decide("prompt", {"objective": "o"}, opts, step=3)
    r = dec.record
    assert dec.option.label == "b" and r["p"] == 0.6 and abs(r["confidence"] - (4 * 0.6 - 1) / 3) < 1e-3
    assert r["n_options"] == 4 and r["forced"] is False and pol.calls == 1 and r["input_tokens"] > 0
    one = pol.decide("dialogue", {}, opts[:1])
    assert one.record["forced"] and pol.calls == 1
    pol.log(r)
    assert json.loads(log.read_text())["choice"] == "b"
    positions = {J.JevPolicy(J.MockJev(policy=lambda s, labels: "b"), seed=s).decide("p", {}, opts).record["position"] for s in range(12)}
    assert len(positions) > 1                                                             # option order is shuffled


def test_label_outcome_cases():
    o = J.parse(BATTLE)
    fight = J.Option("use Tackle", "battle", {"action": "fight", "target": "Tackle"})
    hit = J.parse(BATTLE.replace("2/30", "0/30"))
    assert J.label_outcome("battle", fight, o, hit)[0]
    hurt = J.parse(BATTLE.replace("20/47", "1/47"))
    assert not J.label_outcome("battle", fight, o, hurt)[0]
    over = J.parse("Enemy fainted | battle over\nf9 Route 3 (11,6) facing up | B L15 14/47 | ¥2013 | 1 badges")
    assert J.label_outcome("battle", fight, o, over) == (True, "battle over")
    walk = J.Option("walk to Pewter Mart", "walk", {"path": "to Pewter Mart"})
    ow = J.parse(PEWTER)
    assert J.label_outcome("overworld", walk, ow, J.parse("no path to X\n" + PEWTER.split("\n", 1)[1]))[1] == "refused"
    moved = J.parse(PEWTER.replace("(16,18)", "(16,19)"))
    assert J.label_outcome("overworld", walk, ow, moved)[0]
    assert J.label_outcome("overworld", walk, ow, moved, repeat=True) == (False, "repeats a recent result")
    black = J.parse("x\nf9 Pewter City (1,1) facing up | B L1 1/2 | ¥1 | 0 badges\nEVENT: blacked out (lost a battle)")
    assert J.label_outcome("overworld", walk, ow, black) == (False, "blacked out")


def test_summarize_bins_ece_latency_and_kinds():
    recs = [{"kind": "battle", "confidence": 0.95, "p": 0.9, "correct": True, "latency_ms": 100, "input_tokens": 1000, "cost_usd": 4.2e-5, "model": "jev-1.13.0"},
            {"kind": "battle", "confidence": 0.91, "p": 0.9, "correct": False, "latency_ms": 300, "input_tokens": 1000, "cost_usd": 4.2e-5, "model": "jev-1.13.0"},
            {"kind": "overworld", "confidence": 0.1, "p": 0.3, "correct": False, "latency_ms": 200, "input_tokens": 500, "cost_usd": 2.1e-5},
            {"kind": "overworld", "confidence": 0.12, "p": 0.3, "correct": True, "superseded": True, "latency_ms": 90},
            {"kind": "dialogue", "forced": True}]
    s = J.summarize(recs, [{"cost_usd": 0.01}, {"cost_usd": 0.02, "error": "x"}])
    assert s["jev_calls"] == 4 and s["forced"] == 1 and s["scored"] == 3 and s["input_tokens"] == 2500
    assert [b["n"] for b in s["calibration"]] == [1, 2] and s["calibration"][1]["accuracy"] == 0.5
    assert abs(s["ece"] - (1 / 3 * 0.3 + 2 / 3 * 0.4)) < 1e-3
    assert s["by_kind"]["battle"] == {"n": 2, "accuracy": 0.5, "mean_conf": 0.93} and s["models"] == ["jev-1.13.0"]
    assert s["latency_ms"]["p50"] == 200 and s["planner_calls"] == 2 and s["planner_errors"] == 1


# ---------------------------------------------------------------- solo graph
def test_solo_graph_waypoints_are_real_map_names():
    from games import gen1_data as D
    names = {D.map_name(i) for i in range(256)}
    for node in SOLO.GRAPH:
        assert set(node.targets) <= names, node.id
    assert set(SOLO.POKE_CENTERS) <= names and set(SOLO.POKE_CENTERS.values()) <= names
    for step in J.ROUTE:
        assert set(step[1]) <= names


def test_solo_objective_progression_and_rules():
    f = SOLO.Facts(milestones=["game started", "starter: Bulbasaur"], visited={"Viridian City"})
    assert SOLO.current_node(f).id == "parcel"
    f.ever_items, f.items = {"Oak's Parcel"}, {"Oak's Parcel"}
    assert SOLO.current_node(f).id == "deliver"
    f.items = set()
    assert SOLO.current_node(f).id == "forest"
    d = SOLO.SoloDirector({"visited": ["Pewter City", "Viridian City"], "milestones": []})
    o = J.parse(PEWTER)
    weak = SOLO.Facts(badges=0, levels=[10], hp_ratio=0.2, visited={"Pewter City"}, milestones=["badge: x"])
    assert d.objective(weak, o)[2] == "heal" and d.objective(weak, o)[1][0] == "Pewter Poké Center"
    train = SOLO.Facts(badges=0, levels=[9], hp_ratio=1.0, visited={"Pewter City", "Viridian Forest", "Viridian City"},
                       milestones=["game started", "starter: X"], ever_items={"Oak's Parcel"})
    assert d.objective(train, o)[2] == "train"
    hm = SOLO.Facts(items={"HM01"}, moves={"Tackle"})
    labels = [x.label for x in d.extra_options(o, hm, J.parse_party(PARTY), [], [], "cut")]
    assert "teach HM01 (Cut) to Butterfree" in labels


def test_solo_jev_done_votes_and_stuck_tracking():
    s = {"visited": [], "milestones": []}
    d = SOLO.SoloDirector(s)
    f = SOLO.Facts(badges=5, items={"HM03", "HM04", "Tea"}, visited={"Saffron City"},
                   milestones=["game started", "starter: X"], ever_items={"Oak's Parcel", "S.S. Ticket", "Silph Scope", "Poké Flute"})
    for m in ("Viridian City", "Viridian Forest", "Pewter City", "Mt. Moon 1F", "Cerulean City", "Vermilion City", "Lavender Town",
              "Celadon City", "Fuchsia City"):
        f.visited.add(m)
    f.items |= {"HM01", "Silph Scope", "Poké Flute"}
    assert SOLO.current_node(f).id == "silph" and "objective_done" in d.check_questions(f)
    for _ in range(2):
        assert d.absorb(f, {"objective_done": 0.9}) is None
    assert d.absorb(f, {"objective_done": 0.95}) == "silph"
    f.manual_done = set(s["manual_done"])
    assert SOLO.current_node(f).id == "sabrina"
    o = J.parse(PEWTER)
    for step in range(12):
        d.track(step, o, f)
    assert s["recovery"] == 2 and s["pos_repeat"] >= 10
    s["pos_repeat"] = 15
    assert d.forced_recovery(100).args["buttons"].startswith("START")


# ---------------------------------------------------------------- agent loop
class FakeServer:
    """Replies like server.py for a tiny scripted world: one map, a talkable NPC, a prompt."""

    def __init__(self):
        self.calls = []
        self.pos = 2

    async def __call__(self, name, args):
        self.calls.append((name, args))
        status = f"f1 Pallet Town ({self.pos},5) facing up | Bulbasaur L5 20/20 | ¥3000 | 0 badges"
        if name == "screen":
            return status + "\n(no readable text on screen)"
        if name == "state":
            if args["section"] == "party":
                return "party:\n1. Bulbasaur L5 20/20 [Tackle 35pp, Growl 40pp] Grass"
            if args["section"] == "items":
                return "bag: Potion×1"
            return PEWTER.split("\n", 3)[3].replace("Pewter City 6x4", "Pallet Town 6x4")
        if name == "walk":
            self.pos += 1
            return f"walked right 1/1\n{status.replace(f'({self.pos - 1},5)', f'({self.pos},5)')}"
        if name == "talk":
            return f"dialogue ended: hi\n{status}"
        return f"ok\n{status}"


def _agent_args(tmp_path, variant="solo", **kw):
    from bench.jev_agent import build_parser
    a = build_parser().parse_args(["--run-dir", str(tmp_path), "--session-id", "t", "--variant", variant, "--max-steps", "8", "--mock"])
    for k, val in kw.items():
        setattr(a, k, val)
    return a


def test_solo_agent_never_calls_an_llm(tmp_path, monkeypatch, capsys):
    import subprocess

    def boom(*a, **k):
        raise AssertionError("jev-solo must not start any process (no LLM)")
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path)
    with pytest.raises(ValueError):
        Agent(a, FakeServer(), J.JevPolicy(J.MockJev()), planner=J.MockPlanner())
    srv = FakeServer()
    pol = J.JevPolicy(J.MockJev(), tmp_path / "data" / "jev_decisions.jsonl", variant="solo")
    agent = Agent(a, srv, pol)
    assert asyncio.run(agent.run()) == "max_steps"
    recs = J.read_jsonl(tmp_path / "data" / "jev_decisions.jsonl")
    assert len(recs) == 8 and all(r["variant"] == "solo" for r in recs) and pol.calls >= 1
    assert all("correct" in r for r in recs if not r["forced"]) and recs[0]["why"] == "viridian"   # party exists: intro/starter done
    events = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert events[0]["type"] == "start" and any(e["type"] == "usage" for e in events)
    assert json.loads((tmp_path / "jev_agent.json").read_text())["step"] == 8
    agent2 = Agent(a, srv, pol)                                    # a new chunk continues the saved progress
    assert agent2.resumed and agent2.s["step"] == 8


def test_assist_agent_records_fallback_events_with_outcomes(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "assist", fallback_threshold=0.99, fallback_gap=1, fallback_outcome_steps=2, max_steps=6)
    pol = J.JevPolicy(J.MockJev(), tmp_path / "data" / "jev_decisions.jsonl", variant="assist")
    agent = Agent(a, FakeServer(), pol, chooser=J.MockChooser())
    assert asyncio.run(agent.run()) == "max_steps"
    evs = J.read_jsonl(tmp_path / "fallbacks.jsonl")
    assert evs and agent.s["fallbacks"] == len(evs) and all(e["trigger"] == "low" for e in evs)
    e = evs[0]
    assert e["fallback_choice"] != e["jev_choice"] and not e["agreed"] and e["options"] and e["summary"]["party"]
    assert e["outcome_after"]["complete"] and "progress" in e["outcome_after"] and e["map"] == "Pallet Town"
    recs = J.read_jsonl(tmp_path / "data" / "jev_decisions.jsonl")
    sup = [r for r in recs if r.get("fallback")]
    assert sup and all(r["superseded"] and r["executed"] != r["choice"] for r in sup)     # excluded from Jev's calibration
    s = J.summarize_fallbacks(evs, 6)
    assert s["fallbacks"] == len(evs) and s["fallbacks_per_1k_steps"] == round(1000 * len(evs) / 6, 2)


def test_solo_exam_stops_as_stuck(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "solo", stuck_fail_steps=3, max_steps=50)
    agent = Agent(a, FakeServer(), J.JevPolicy(J.MockJev()))
    assert asyncio.run(agent.run()) == "stuck" and agent.s["step"] < 50


def test_claude_chooser_picks_from_the_closed_set():
    class Out:
        stdout, stderr = json.dumps({"result": '{"choice": 2, "why": "go"}', "total_cost_usd": 0.003}), ""
    opts = [J.Option("a", "press", {}), J.Option("b", "press", {})]
    fb = J.ClaudeChooser(runner=lambda cmd, **kw: Out()).choose("stuck", "o", {}, opts, {"a": 0.6, "b": 0.4})
    assert fb.label == "b" and fb.cost_usd == 0.003 and not fb.error

    class Bad:
        stdout, stderr = json.dumps({"result": '{"choice": 9}'}), ""
    assert J.ClaudeChooser(runner=lambda cmd, **kw: Bad()).choose("x", "o", {}, opts, {}).error


def test_segments_resolve_and_iteration_cost(tmp_path, monkeypatch):
    from bench import run
    segs = json.loads((ROOT / "bench" / "segments.json").read_text())
    assert {"power-on", "after-brock", "cerulean", "viridian-gym"} <= set(segs)
    assert run.load_segment("power-on")["goal"] == "badge: Boulder"
    with pytest.raises(SystemExit):
        run.load_segment("nope")
    it = tmp_path / "bench" / "iterations" / "it2"
    it.mkdir(parents=True)
    (it / "analysis.json").write_text(json.dumps({"cost_usd": 1.25}))
    monkeypatch.setattr(run, "ROOT", tmp_path)
    assert run.analysis_cost(3) == 1.25 and run.analysis_cost(5) is None


def test_hybrid_agent_replans_with_the_planner(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "hybrid")
    pol = J.JevPolicy(J.MockJev(), tmp_path / "data" / "jev_decisions.jsonl", variant="hybrid")
    agent = Agent(a, FakeServer(), pol, planner=J.MockPlanner())
    asyncio.run(agent.run())
    objs = J.read_jsonl(tmp_path / "data" / "jev_objectives.jsonl")
    assert objs and objs[0]["source"] == "planner" and objs[0]["reason"] == "start" and agent.planner_calls >= 1


def test_claude_planner_parses_cli_json_and_errors():
    class Out:
        def __init__(self, stdout, stderr=""):
            self.stdout, self.stderr = stdout, stderr
    reply = {"type": "result", "is_error": False, "total_cost_usd": 0.0021, "usage": {"input_tokens": 900, "output_tokens": 40},
             "result": 'Here: {"objective": "Go to Pewter Gym", "targets": ["Pewter Gym", "Pewter Poké Center"]}'}
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["input"]
        return Out(json.dumps(reply))
    p = J.ClaudePlanner(runner=runner).plan("start", "", "Status: x")
    assert p.objective == "Go to Pewter Gym" and p.targets[0] == "Pewter Gym" and p.cost_usd == 0.0021 and not p.error
    assert "--tools" in seen["cmd"] and "claude-haiku-4-5-20251001" in seen["cmd"] and "Status: x" in seen["input"]
    bad = J.ClaudePlanner(runner=lambda cmd, **kw: Out(json.dumps({"result": "no json", "total_cost_usd": 0.001}))).plan("r", "old", "")
    assert bad.error and bad.objective == "old" and bad.cost_usd == 0.001


# ---------------------------------------------------------------- harness glue
def test_stream_parser_for_the_jev_agent():
    st = ChunkStats("jev")
    for e in [{"type": "start", "session_id": "run1"}, {"type": "tool_call", "tool": "walk"}, {"type": "tool_call", "tool": "talk"},
              {"type": "usage", "step": 2, "tokens": {"input": 1500, "output": 20}, "cost_usd": 0.0001},
              {"type": "objective", "error": "planner timed out"},
              {"type": "error", "message": "rate limited", "rate_limited": True}, {"type": "result", "reason": "budget"}]:
        st.feed(e)
    assert st.session_id == "run1" and st.tool_calls == 2 and st.tokens["input"] == 1500 and st.cost_usd == 0.0001
    assert st.rate_limited and st.finished and len(st.errors) == 2


def test_providers_build_agent_and_battle_commands(tmp_path):
    from bench.providers import JevBattlesProvider, JevProvider, make_provider
    p = make_provider("jev", variant="solo", mock=True)
    assert isinstance(p, JevProvider) and p.label == "jev-solo" and p.parser == "jev" and p.track == "jev"
    p.prepare(tmp_path, ["/py", "server.py", "--rom", "r.gb"])
    cmd = p.command(tmp_path, tmp_path / "prompt.md", None, True)
    assert cmd[1].endswith("jev_agent.py") and "--mock" in cmd and cmd[cmd.index("--variant") + 1] == "solo"
    assert cmd[cmd.index("--") + 1:] == ["/py", "server.py", "--rom", "r.gb"]
    if shutil.which("claude"):
        b = make_provider("jev", variant="battles", mock=True)
        assert isinstance(b, JevBattlesProvider) and b.parser == "claude" and b.model == "claude-haiku-4-5-20251001"
        assert b.server_args(tmp_path)[:2] == ["--battle-advisor", "mock-jev"] and "battle('auto')" in b.prompt_suffix()


def test_run_refuses_a_real_jev_run_without_the_key(monkeypatch):
    from bench import run
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="TYPESAFE_API_KEY"):
        run.main(["--provider", "jev", "--variant", "solo"])


def test_results_md_puts_jev_in_a_separate_track():
    from tests.test_bench import _result
    cli = _result("a", "model-a", "claude", ["starter: Squirtle", "badge: Boulder"], 1, 1.5)
    j = _result("j", "jev-latest", "jev", ["starter: Bulbasaur"], 0, 0.2)
    j["harness"].update(track="jev", variant="solo", display_model="jev-latest",
                        jev=J.summarize([{"kind": "battle", "confidence": 0.9, "p": 0.9, "correct": True, "latency_ms": 120,
                                          "input_tokens": 100, "cost_usd": 0.1, "model": "jev-1.13.0"}]))
    j["derived"] = derive(j["metrics"], j["harness"])
    md = build_results_md([cli, j])
    lead, jev_part = md.split("## Jev track", 1)
    assert "model-a" in lead and "jev-latest" not in lead
    assert "heavy code scaffolding" in jev_part and "jev-solo" in jev_part and "no LLM" in jev_part
    assert "Confidence vs. correctness" in jev_part and "| 0.9–1.0 | 1 |" in jev_part


# ---------------------------------------------------------------- against the real server
@requires_rom
def test_solo_agent_plays_the_real_server_over_mcp(rom_path, tmp_path):
    """Spawn server.py over stdio and let the mock-Jev solo agent play its first steps from power-on."""
    import subprocess
    rom = tmp_path / "rom.gb"
    shutil.copy(rom_path, rom)
    (tmp_path / "data").mkdir()
    server = [sys.executable, str(ROOT / "server.py"), "--rom", str(rom), "--data-dir", str(tmp_path / "data"),
              "--session-id", "t", "--autosave-every", "0", "--no-screenshot-files", "--log-level", "WARNING"]
    out = subprocess.run([sys.executable, str(ROOT / "bench" / "jev_agent.py"), "--run-dir", str(tmp_path), "--variant", "solo",
                          "--mock", "--max-steps", "90", "--"] + server, capture_output=True, text=True, timeout=300,
                         env={k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"})
    events = [json.loads(x) for x in out.stdout.splitlines() if x.startswith("{")]
    assert events[-1]["type"] == "result" and events[-1]["reason"] == "max_steps", out.stderr[-2000:]
    state = json.loads((tmp_path / "jev_agent.json").read_text())
    assert "game started" in state["milestones"]
    recs = J.read_jsonl(tmp_path / "data" / "jev_decisions.jsonl")
    assert len(recs) == 90 and any(r["kind"] == "overworld" for r in recs)


@requires_rom
def test_battle_advisor_decides_trainer_turns(rom_path, tmp_path):
    """In-process: battle('auto') with the advisor plays a Route 3 trainer battle turn by turn (local state needed)."""
    st = ROOT / "saves" / rom_path.stem / "after-brock.state"
    if not st.exists():
        pytest.skip("needs a local saves/<rom>/after-brock.state")
    from emulator import Emulator
    from server import build_server
    rom = tmp_path / "rom.gb"
    shutil.copy(rom_path, rom)
    (tmp_path / "saves" / "rom").mkdir(parents=True)
    shutil.copy(st, tmp_path / "saves" / "rom" / "after-brock.state")
    emu = Emulator(str(rom), base_dir=tmp_path, autosave_every=0, save_screenshots=False)
    emu.boot()
    log = tmp_path / "jev.jsonl"
    T = {n: t.fn for n, t in build_server(emu, J.BattleAdvisor(J.MockJev(policy=lambda s, labels: next(
        (x for x in labels if x.startswith("use ")), labels[0])), log))._tool_manager._tools.items()}
    txt = lambda r: "\n".join(c.text for c in r if c.type == "text")  # noqa: E731
    T["load_state"](slot="after-brock")
    T["walk"](path="to outside", screenshot=False)
    T["walk"](path="to Route 3", screenshot=False)
    for _ in range(6):
        r = txt(T["walk"](path="to 30,9", screenshot=False))
        if emu.profile.is_text_visible() and not emu.profile.in_battle():
            T["talk"]()
        if emu.profile.in_battle():
            break
    assert emu.profile.in_battle(), r
    out = txt(T["battle"](action="auto"))
    recs = J.read_jsonl(log)
    assert "[Jev: use " in out and recs and all(r["variant"] == "battles" for r in recs)
    assert all(r["kind"] in ("battle", "faint_switch") and "correct" in r for r in recs if not r.get("forced"))
    emu.pyboy.stop(save=False)


# ---------------------------------------------------------------- self-improvement loop
def _event(i, trigger="low", node="parcel", where="Viridian Mart", progress=True):
    return {"id": f"r:{i}", "run": "r", "step": i, "trigger": trigger, "trigger_detail": trigger, "node": node, "map": where,
            "mode": "overworld", "objective": "get the parcel", "options": [{"label": "a", "p": 0.4}], "jev_choice": "a",
            "jev_confidence": 0.2, "fallback_choice": "b", "agreed": False, "cost_usd": 0.01,
            "outcome_after": {"complete": True, "progress": progress}}


def test_improve_clusters_and_dry_run(tmp_path, monkeypatch, capsys):
    from bench import improve
    run = tmp_path / "run1"
    run.mkdir()
    evs = [_event(i) for i in range(5)] + [_event(9, "stuck", "brock", "Pewter Gym", False)]
    (run / "fallbacks.jsonl").write_text("\n".join(json.dumps(e) for e in evs))
    cl = improve.build_clusters(evs)
    assert [c["count"] for c in cl] == [5, 1] and cl[0]["progress_after"] == 1.0 and cl[1]["progress_after"] == 0.0
    assert cl[0]["top_swaps"][0] == ("jev: a -> fallback: b", 5)
    monkeypatch.setattr(improve, "ROOT", tmp_path)
    for f in improve.SCAFFOLDING:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text(f"# {f}\n")
    import argparse
    ns = argparse.Namespace(runs=[str(run)], iteration=1, model="claude-opus-5-5", call=False, per_cluster=2, max_clusters=12)
    out = improve.analyze(ns, runner=lambda *x, **k: (_ for _ in ()).throw(AssertionError("dry run must not call")))
    prompt = (out / "prompt.md").read_text()
    assert "fallback events of 1 run(s)" in prompt and "# bench/jev_solo.py" in prompt and '"count": 5' in prompt
    assert json.loads((out / "analysis.json").read_text())["called"] is False

    class Out:
        stdout = json.dumps({"result": "## Summary\nAdd a Mart option.\n## Patch\n```diff\n--- a/bench/jev.py\n+++ b/bench/jev.py\n@@ -1 +1 @@\n-x\n+y\n```",
                             "total_cost_usd": 3.5, "usage": {"input_tokens": 50000}})
        stderr = ""
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"] = cmd
        return Out()
    ns.call = True
    out = improve.analyze(ns, runner=runner)
    assert "claude-opus-5-5" in seen["cmd"] and "--tools" in seen["cmd"]
    assert (out / "proposal.patch").read_text().startswith("--- a/bench/jev.py") and "Add a Mart option" in (out / "summary.md").read_text()
    assert json.loads((out / "analysis.json").read_text())["cost_usd"] == 3.5


def test_improve_apply_refuses_main(tmp_path, monkeypatch):
    from bench import improve
    import argparse
    import subprocess
    monkeypatch.setattr(improve, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    g = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "init"], check=True)
    it = tmp_path / "bench" / "iterations" / "it1"
    it.mkdir(parents=True)
    (it / "proposal.patch").write_text("--- a/x\n+++ b/x\n")
    with pytest.raises(SystemExit, match="main"):
        improve.apply(argparse.Namespace(iteration=1, branch=None))


def test_results_md_iteration_trend():
    from tests.test_bench import _result
    rows = []
    for it, fb in ((1, 40), (2, 12)):
        r = _result(f"j{it}", "jev-latest", "jev", ["badge: Boulder"], 1, 0.5)
        r["harness"].update(track="jev", variant="assist", iteration=it, analysis_cost_usd=2.0 if it == 2 else None,
                            segment={"name": "after-brock", "state_sha256": "abc", "goal": "badge: Boulder"},
                            jev=dict(J.summarize([]), steps=1000, fallbacks=fb, fallbacks_per_1k_steps=float(fb),
                                     jev_cost_usd=0.1, planner_cost_usd=0.4))
        rows.append(r)
    md = build_results_md(rows)
    assert "### Self-improvement iterations" in md
    tbl = md.split("### Self-improvement iterations", 1)[1]
    assert tbl.index("| 1 | assist | 1000 | 40 |") < tbl.index("| 2 | assist | 1000 | 12 |") and "$2.00" in tbl and "✓ badge: Boulder" in tbl


class LearnMoveServer(FakeServer):
    """Replays iteration 1's bug: Butterfree's learn-move prompts inside a battle. NO on "Abandon learning?" goes back
    through two text screens to the first prompt; only YES (press A) there ends it."""

    BAT = "f1 BATTLE (trainer): enemy Sandshrew L11 0/30 | you Butterfree L12 30/40 [Confusion 20pp] | menu: (text)"

    def __init__(self):
        super().__init__()
        self.at = "teach"

    async def __call__(self, name, args):
        self.calls.append((name, args))
        if self.at == "done":
            return await super().__call__(name, args) if name != "press" else "pressed\n" + \
                "f1 Pallet Town (2,5) facing up | Butterfree L12 30/40 | ¥3000 | 0 badges"
        if name == "press":
            b = args["buttons"]
            if self.at == "teach":
                self.at = "text1" if b == "A" else "abandon"
            elif self.at == "abandon":
                self.at = "done" if b == "A" else "text1"
            elif self.at == "text1":
                self.at = "text2"
            elif self.at == "text2":
                self.at = "teach"
            if self.at == "done":
                return await self(name, args)
        screen = {"teach": "BUTTERFREE is trying to\nlearn STUN SPORE!\nDelete an older move?\n ▶YES\n  NO",
                  "abandon": "Abandon learning\nSTUN SPORE?\n ▶YES\n  NO",
                  "text1": "BUTTERFREE can't learn\nmore than 4 moves!", "text2": "But, BUTTERFREE can't\nlearn more than 4!"}
        return f"pressed {args.get('buttons', '')}\n{self.BAT}\nscreen:\n{screen.get(self.at, screen['text1'])}"


def test_learn_move_prompt_loop_is_broken(tmp_path):
    """Iteration 1 burned 19,800 steps here: forced A presses on the text screens filled the history, so the repeat
    filter dropped "press A" (the only way out). Forced presses no longer count and repeated screens try new options."""
    assert J.drop_repeats([J.Option("press A", "press", {}), J.Option("press B", "press", {})],
                          [J.AUTO + "press A -> pressed A"] * 5) [0].label == "press A"
    assert [o.label for o in J.drop_repeats([J.Option("press A", "press", {}), J.Option("press B", "press", {})],
                                            ["press A -> x"] * 3, keep=("press A",))] == ["press A", "press B"]
    (tmp_path / "data").mkdir()

    def stubborn(state, labels):                   # never picks YES on its own
        for want in ("press B", "press DOWN then A"):
            if want in labels:
                return want
        return labels[0]
    srv = LearnMoveServer()
    a = _agent_args(tmp_path, "solo", max_steps=60, stuck_fail_steps=0)
    agent = Agent(a, srv, J.JevPolicy(J.MockJev(policy=stubborn)))
    asyncio.run(agent.run())
    assert srv.at == "done"
    assert sum(1 for n, x in srv.calls if n == "press") < 30


def test_assist_reports_a_repeated_prompt_as_stuck(tmp_path):
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "assist", max_steps=1)
    agent = Agent(a, FakeServer(), J.JevPolicy(J.MockJev()), chooser=J.MockChooser())
    dec = types.SimpleNamespace(record={"confidence": 0.9})
    assert agent.fallback_trigger(dec, False, False, screen_stuck=True) == "stuck"
    assert agent.fallback_trigger(dec, True, False) == "loop"
    assert agent.fallback_trigger(dec, False, False) == ""


# ---------------------------------------------------------------- static warp graph (bench/jev_nav.py)
@requires_rom
def test_rom_world_data_matches_wram(emu):
    """map_warps / map_cells / map_connections read from the ROM equal what the game loads into WRAM."""
    from games import gen1_data as D
    rom = emu.rom_path.read_bytes()
    m, p = emu.pyboy.memory, emu.profile
    mid = m[D.CUR_MAP]
    wram = [(m[D.WARPS + 4 * i + 1], m[D.WARPS + 4 * i], m[D.WARPS + 4 * i + 2], m[D.WARPS + 4 * i + 3])
            for i in range(m[D.NUM_WARPS])]
    assert D.map_warps(rom, mid) == wram and wram
    assert D.map_cells(rom, mid) == p.full_map_cells()
    assert [(s, d) for s, d, _, _ in D.map_connections(rom, mid)] == list(p.connections())
    ts = m[D.CUR_TILESET]
    assert bytes(rom[D.TILESET_HEADERS + 12 * ts: D.TILESET_HEADERS + 12 * ts + 11]) == bytes(m[0xD52B + i] for i in range(11))


@pytest.fixture(scope="module")
def nav(rom_path):
    from bench.jev_nav import WorldNav
    return WorldNav(rom_path.read_bytes())


def _route(nav, src, pos, goal, **kw):
    from bench.jev_nav import map_id
    r = nav.route(map_id(src), pos, map_id(goal), **kw)
    return None if r is None else [(h.kind, h.x, h.y, h.dest_name) for h in r]


@requires_rom
def test_nav_routes_through_multi_floor_dungeons(nav):
    from bench.jev_nav import map_id
    mm = _route(nav, "Mt. Moon 1F", (14, 35), "Cerulean City")       # iteration 2 bounced between B1F and B2F here
    assert [d for *_, d in mm] == ["Mt. Moon B1F", "Mt. Moon B2F", "Mt. Moon B1F", "Route 4", "Cerulean City"]
    assert mm[0][:3] == ("warp", 5, 5) and mm[1][:3] == ("warp", 21, 17)   # not the nearest ladder to B1F
    # warps are reciprocal: B1F's ladder (21,17) goes to B2F and B2F's arrival ladder leads back to it
    b1, b2 = map_id("Mt. Moon B1F"), map_id("Mt. Moon B2F")
    i = next(i for i, w in enumerate(nav.map(b1)["warps"]) if w[:2] == (21, 17))
    (dm, x, y), = nav.warp_dest(b1, i)
    j = next(j for j, w in enumerate(nav.map(b2)["warps"]) if w[:2] == (x, y))
    assert dm == b2 and nav.warp_dest(b2, j)[0][0] == b1
    assert _route(nav, "Route 4", (18, 5), "Cerulean City")[0][:3] == ("warp", 18, 5)   # standing on the entrance
    for src, pos, goal, kw in [("Route 10", (8, 17), "Lavender Town", {}),
                               ("Celadon City", (10, 20), "Rocket Hideout B4F", {}),
                               ("Silph Co. 1F", (10, 17), "Silph Co. 11F", {}),
                               ("Pokémon Tower 1F", (10, 17), "Pokémon Tower 7F", {}),
                               ("Route 23", (7, 140), "Indigo Plateau Lobby", {"surf": True})]:
        r = _route(nav, src, pos, goal, **kw)
        assert r and r[-1][3] == goal, (src, goal, r)
    assert _route(nav, "Pallet Town", (5, 6), "Pallet Town") == []


@requires_rom
def test_nav_memory_penalizes_taken_warps_and_skips_blocked_hops(nav):
    from bench.jev_nav import map_id
    mid = map_id("Mt. Moon 1F")
    first = _route(nav, "Mt. Moon 1F", (14, 35), "Route 4")                 # two-wide cave mouth: (14,35) and (15,35)
    assert first == [("warp", 15, 35, "Route 4")]                            # one step beats stepping off and on
    assert _route(nav, "Mt. Moon 1F", (14, 35), "Route 4", blocked=frozenset({f"{mid}:15,35"}))[0][:3] == ("warp", 14, 35)
    assert _route(nav, "Mt. Moon 1F", (14, 35), "Route 4", taken={f"{mid}:15,35": 3})[0][:3] == ("warp", 14, 35)
    assert _route(nav, "Mt. Moon 1F", (14, 35), "Cerulean City", blocked=frozenset({f"{mid}:5,5"})) is None


@requires_rom
def test_agent_offers_route_and_concrete_warps_instead_of_nearest_ladder(nav, tmp_path):
    from bench.jev_agent import NAME_WALK_RE
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=nav)
    o = J.parse("walked\nf1 Mt. Moon 1F (14,35) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    facts = SOLO.Facts(badges=1)
    opts, key = agent.nav_options(o, ["Mt. Moon B1F", "Mt. Moon B2F", "Route 4", "Cerulean City"], facts)
    assert opts[0].label.startswith("follow the map route to Cerulean City") and opts[0].args["path"] == "to 5,5"
    assert key.endswith(":5,5") and "B2F" in opts[0].desc
    assert any(x.args["path"] == "to 17,11" for x in opts) and not any(NAME_WALK_RE.match(x.args["path"]) for x in opts)
    assert NAME_WALK_RE.match("to Mt. Moon B1F") and not NAME_WALK_RE.match("to east edge") and not NAME_WALK_RE.match("to 5,5")
    after = J.parse("walked\nf1 Mt. Moon B1F (5,5) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    agent.nav_feedback(o, opts[0], after, key)
    assert agent.s["nav_taken"] == {key: 1}
    stuck = J.parse("walked\nf1 Mt. Moon 1F (14,35) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    agent.nav_feedback(o, J.Option(opts[0].label, "walk", {"path": "up 1"}), stuck, key)
    assert agent.s["nav_blocked"][key] > agent.s["step"]


def test_assist_fallback_budget_cap(tmp_path, capsys):
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "assist", fallback_threshold=0.99, fallback_gap=1, max_steps=6, max_fallbacks=1)
    agent = Agent(a, FakeServer(), J.JevPolicy(J.MockJev()), chooser=J.MockChooser())
    asyncio.run(agent.run())
    assert agent.s["fallbacks"] == 1 and agent.s["fallback_capped"]
    events = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert sum(e["type"] == "fallback_cap" for e in events) == 1


def test_play_modes_and_model_aliases():
    from bench.providers import MODES, resolve_mode, resolve_model
    assert set(MODES) == {"jev-solo", "jev-assist", "jev-hybrid", "jev-scripted", "jev-battles", "llm"}
    assert resolve_mode("jev-assist", "", "solo") == ("jev", "assist", "jev-assist")
    assert resolve_mode("llm", "codex", "solo")[::2] == ("codex", "llm")
    assert resolve_mode("", "jev", "hybrid")[2] == "jev-hybrid" and resolve_mode("", "claude", "solo")[2] == "llm"
    for bad in [("llm", "jev"), ("jev-solo", "claude"), ("", "")]:
        with pytest.raises(SystemExit):
            resolve_mode(bad[0], bad[1], "solo")
    assert resolve_model("opus") == "claude-opus-5-5" and resolve_model("Sonnet") == "claude-sonnet-5-5"
    assert resolve_model("haiku") == "claude-haiku-4-5-20251001" and resolve_model("gpt-5.6-sol") == "gpt-5.6-sol"
