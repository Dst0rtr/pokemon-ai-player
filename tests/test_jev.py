"""Jev provider track: HTTP client (mocked transport), parsers, candidates, policy, labels, calibration summary,
solo objective graph, agent loop (fake server and the real one over MCP), harness glue. No network."""

import asyncio
import dataclasses
import re
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
from bench import jev_agent as AG
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
    assert [x.label for x in sw] == ["switch to Charmeleon"] and sw[0].args == {"action": "switch", "target": "Charmeleon"}
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
    assert d.objective(train, o)[2] == "heal"                              # first visit to Pewter: use its Poké Center once
    inside = J.parse("walked\nf1 Pewter Poké Center (3,6) facing up | X L9 30/30 | ¥3000 | 0 badges")
    assert d.objective(train, inside)[2] == "heal"                         # inside it: no flip back to the graph
    d.s.setdefault("healed_at", []).append("Pewter Poké Center")
    assert d.objective(train, o)[2] == "train"
    hm = SOLO.Facts(items={"HM01"}, moves={"Tackle"})
    labels = [x.label for x in d.extra_options(o, hm, J.parse_party(PARTY), [], [], "cut")]
    assert "teach HM01 (Cut) to Butterfree" in labels
    teach = next(x for x in d.extra_options(o, hm, J.parse_party(PARTY), [], [], "cut") if x.label.startswith("teach"))
    assert teach.args["target2"] == "Butterfree: weakest"                  # iteration 40: no move to forget was named
    d.s["hm_no"] = ["HM01:Butterfree"]                                     # the game refused: try the next one
    labels = [x.label for x in d.extra_options(o, hm, J.parse_party(PARTY), [], [], "cut")]
    assert "teach HM01 (Cut) to Charmeleon" in labels and "teach HM01 (Cut) to Butterfree" not in labels


def test_solo_jev_done_votes_and_stuck_tracking():
    s = {"visited": [], "milestones": []}
    d = SOLO.SoloDirector(s)
    f = SOLO.Facts(badges=5, items={"HM03", "HM04", "Tea"}, visited={"Saffron City"},
                   milestones=["game started", "starter: X"], ever_items={"Oak's Parcel", "S.S. Ticket", "Silph Scope", "Poké Flute"})
    for m in ("Viridian City", "Viridian Forest", "Pewter City", "Mt. Moon 1F", "Cerulean City", "Vermilion City", "Lavender Town",
              "Celadon City", "Fuchsia City"):
        f.visited.add(m)
    f.items |= {"HM01", "Silph Scope", "Poké Flute"}
    assert SOLO.current_node(f).id == "silph" and "objective_done" not in d.check_questions(f)
    # full run 72 beat Giovanni at step 9,567 and paced 11F for ~2,100 steps: his defeat line marks Silph Co. done
    d.heard("dialogue ended: Blast it all! You ruined our\nplans for SILPH! | But, TEAM ROCKET will never fall!")
    assert SOLO.current_node(SOLO.Facts(**{**f.__dict__, "events": set(s["events"])})).id == "sabrina"
    s["recovery"] = 3                     # stuck: a node code checks (the badge here) is not put to Jev's votes
    f = SOLO.Facts(**{**f.__dict__, "events": set(s["events"])})
    assert SOLO.current_node(f).id == "sabrina" and "objective_done" not in d.check_questions(f)
    sabrina = SOLO.current_node(f)
    try:                                  # a node only Jev can tell: three yes votes mark it done
        SOLO.GRAPH[SOLO.GRAPH.index(sabrina)] = dataclasses.replace(sabrina, done=None, jev_check="Has Sabrina been beaten?")
        assert d.check_questions(f)["objective_done"] == "Has Sabrina been beaten?"
        for _ in range(2):
            assert d.absorb(f, {"objective_done": 0.9}) is None
        assert d.absorb(f, {"objective_done": 0.95}) == "sabrina"
    finally:
        SOLO.GRAPH[SOLO.GRAPH.index(next(n for n in SOLO.GRAPH if n.id == "sabrina"))] = sabrina
    f.manual_done = set(s["manual_done"])
    assert SOLO.current_node(f).id == "lapras"                             # HM03 in the bag, nobody can learn it
    o = J.parse(PEWTER)
    for step in range(12):
        d.track(step, o, f)
    assert s["recovery"] == 2 and s["pos_repeat"] >= 10
    d.track(12, o, SOLO.Facts(**{**f.__dict__, "events": f.events | {"fuji"}}))   # a story event is progress
    assert s["last_progress_step"] == 12 and d.want_checkpoint(12)
    s["pos_repeat"] = 15
    assert d.forced_recovery(100).args["buttons"].startswith("START")



def test_a_team_that_cannot_learn_surf_gets_the_silph_lapras():
    # full run 75: HM03 refused by all five (Charizard, Nidoran♂/♀, Paras, Doduo) and the Cinnabar objective needs Surf
    s = {"visited": [], "milestones": [], "hm_no": ["HM03:Charizard"]}
    d = SOLO.SoloDirector(s)
    party = [{"species": "Charizard", "level": 62, "hp": 100, "max_hp": 100, "moves": [{"name": "Strength", "pp": 15}]},
             {"species": "Doduo", "level": 26, "hp": 60, "max_hp": 60, "moves": [{"name": "Peck", "pp": 35}]}]
    o = J.parse(PEWTER)
    f = d.facts(o, party, [("HM03", 1), ("HM04", 1)])
    assert "HM03" in f.teachable                                          # Doduo has not been tried: teach it first
    f = SOLO.Facts(**{**f.__dict__, "badges": 6})
    assert SOLO.current_node(f).id == "cinnabar"
    s["hm_no"].append("HM03:Doduo")
    f = SOLO.Facts(**{**d.facts(o, party, [("HM03", 1)]).__dict__, "badges": 6})
    assert f.teachable == set()
    node = SOLO.current_node(f)
    assert node.id == "lapras" and node.targets[-1] == "Silph Co. 7F"
    f.moves.add("Surf")                                                   # Lapras taught
    node = SOLO.current_node(f)
    assert node.id == "cinnabar" and node.targets[0] == "Pallet Town"     # the known map the way to Route 21 starts

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


def test_improve_apply_only_touches_the_scaffolding(tmp_path, monkeypatch):
    """Codex review: the prompt limits the patch to four files; apply must enforce that, and fail loudly."""
    from bench import improve
    import argparse
    import subprocess
    monkeypatch.setattr(improve, "ROOT", tmp_path)
    subprocess.run(["git", "init", "-q", "-b", "work", str(tmp_path)], check=True)
    (tmp_path / "bench").mkdir()
    for f in ("bench/jev.py", "server.py"):
        (tmp_path / f).write_text("x = 1\n")
    g = ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(g + ["add", "."], check=True)
    subprocess.run(g + ["commit", "-q", "-m", "init"], check=True)
    it = tmp_path / "bench" / "iterations" / "it1"
    it.mkdir(parents=True)
    hunk = "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    (it / "proposal.patch").write_text(f"--- a/server.py\n+++ b/server.py\n{hunk}")
    with pytest.raises(SystemExit, match="outside the scaffolding.*server.py"):
        improve.apply(argparse.Namespace(iteration=1, branch=None))
    (it / "proposal.patch").write_text(f"--- a/bench/jev.py\n+++ b/bench/jev.py\n{hunk}"
                                       f"diff --git a/server.py b/bench/jev_nav.py\nsimilarity index 100%\n"
                                       f"rename from server.py\nrename to bench/jev_nav.py\n")
    with pytest.raises(SystemExit, match="server.py"):                    # a rename out of a protected file
        improve.apply(argparse.Namespace(iteration=1, branch=None))
    assert (tmp_path / "server.py").exists() and not (tmp_path / "bench" / "jev_nav.py").exists()
    assert subprocess.run(g + ["branch", "--show-current"], capture_output=True, text=True).stdout.strip() == "work"
    (it / "proposal.patch").write_text(f"--- a/bench/jev.py\n+++ b/bench/jev.py\n{hunk}")
    improve.apply(argparse.Namespace(iteration=1, branch=None))
    assert (tmp_path / "bench" / "jev.py").read_text() == "x = 2\n"


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
    assert tbl.index("| 1 | assist | rom | 1000 | 40 |") < tbl.index("| 2 | assist | rom | 1000 | 12 |") and "$2.00" in tbl and "✓ badge: Boulder" in tbl


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
    from bench.jev_nav import map_id
    SOLO_MAP_ID = map_id("Mt. Moon 1F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=nav)
    o = J.parse("walked\nf1 Mt. Moon 1F (14,35) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    facts = SOLO.Facts(badges=1)
    opts, key = agent.nav_options(o, ["Mt. Moon B1F", "Mt. Moon B2F", "Route 4", "Cerulean City"], facts)
    assert opts[0].label.startswith("follow the map route to Cerulean City") and opts[0].args["path"] == "to 5,5"
    assert key.endswith(":5,5") and "B2F" in opts[0].desc
    assert not any(NAME_WALK_RE.match(x.args["path"]) for x in opts)
    pocket = J.parse("walked\nf1 Mt. Moon B2F (25,9) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    here = agent.nav_options(pocket, [], facts)[0]                       # other B2F sections: unlisted
    assert [x.label for x in here] == ["walk to the warp at (25,9) → Mt. Moon B1F (not visited yet) (you stand on it: step off and back on)"]
    assert here[0].args["path"] == "up 1" and here[0].then == [("walk", {"path": "down 1", "on_battle": "stop"})]
    assert NAME_WALK_RE.match("to Mt. Moon B1F") and not NAME_WALK_RE.match("to east edge") and not NAME_WALK_RE.match("to 5,5")
    after = J.parse("walked\nf1 Mt. Moon B1F (5,5) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    agent.nav_feedback(o, opts[0], after, key)
    assert agent.s["nav_taken"] == {key: 1}
    # the server finds no way although the map data has one: offer to clear whatever stands on the route
    stuck = J.parse("no walkable route from (14,35) to (5,5) on this map\nf1 Mt. Moon 1F (14,35) facing up | Charmeleon L20 50/60 | ¥3000 | 1 badges")
    agent.nav_feedback(o, opts[0], stuck, key)
    assert agent.s["nav_noroute"][key] == agent.s["step"] and key not in agent.s["nav_blocked"]
    path = nav.path_cells(SOLO_MAP_ID, (14, 35), (5, 5))
    assert path[0] == (14, 35) and path[-1] == (5, 5) and len(path) > 10
    o.npcs = [path[len(path) // 2]]
    opts2, _ = agent.nav_options(o, ["Cerulean City"], facts)
    assert opts2[0].label.startswith("follow the map route to Cerulean City: first clear the way at")   # the route clears it
    assert "blocked by" in opts2[0].desc and opts2[0].then[-1] == ("talk", {})
    assert not any(x.label.startswith("walk to the warp at (5,5)") for x in opts2)
    agent.s["step"] += 5                                                 # failed again later: avoid that hop
    agent.nav_feedback(o, opts[0], stuck, key)
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


def test_heal_offers_the_nurse():
    d = SOLO.SoloDirector({"visited": ["Pewter City", "Pewter Poké Center"]})
    o = J.parse("walked\nf1 Pewter Poké Center (5,6) facing up | Charmeleon L20 10/60 | ¥3000 | 1 badges")
    nurse = [x for x in d.extra_options(o, SOLO.Facts(badges=1, levels=[20], hp_ratio=0.2), [], [], [], "heal")
             if x.label == "talk to the nurse across the counter"]
    assert nurse and nurse[0].args["path"] == "to 3,3" and nurse[0].then[-1] == ("talk", {})
    o.pos = (3, 3)
    nurse = [x for x in d.extra_options(o, SOLO.Facts(badges=1, levels=[20], hp_ratio=0.2), [], [], [], "heal")
             if x.label.startswith("talk to the nurse")]
    assert nurse[0].args["path"] == "up 1" and nurse[0].then == [("talk", {})]
    # the Indigo Plateau Lobby's nurse (7,5) is not where a Poké Center's is, and its name has no "Poké Center"
    o = J.parse("walked\nf1 Indigo Plateau Lobby (7,10) facing up | Charizard L60 10/160 | ¥3000 | 8 badges")
    nurse = [x for x in d.extra_options(o, SOLO.Facts(badges=8, levels=[60], hp_ratio=0.1), [], [], [], "heal")
             if x.label.startswith("talk to the nurse")]
    assert nurse and nurse[0].args["path"] == "to 7,7" and nurse[0].then[-1] == ("talk", {})


# ---------------------------------------------------------------- --map-source learned (bench/jev_atlas.py)
def _view(name, rows, exits=""):
    body = "\n".join(f"{y:2d} {r}" for y, r in enumerate(rows))
    return f"{name} {len(rows[0])}x{len(rows)}, you at (1,1) facing up.\n   0123456\n{body}\nexits: {exits}"


def _warps_hex(warps):
    data = [len(warps)] + [b for (x, y, dw, dm) in warps for b in (y, x, dw, dm)]
    return "\n".join(f"{0xD3AE + i:04X}: " + " ".join(f"{b:02X}" for b in data[i:i + 16]) for i in range(0, len(data), 16))


def test_learned_atlas_builds_routes_from_what_it_saw(tmp_path):
    from bench.jev_atlas import LearnedAtlas, parse_view, parse_warps
    from bench.jev_nav import map_id
    a, b, c = map_id("Mt. Moon 1F"), map_id("Mt. Moon B1F"), map_id("Mt. Moon B2F")
    assert parse_warps(_warps_hex([(5, 1, 0, b), (1, 3, 1, 0xFF)])) == [(5, 1, 0, b), (1, 3, 1, 0xFF)]
    assert parse_view(_view("x", ["#######", "#P..D.#", "#######"]))[1] == list("#...D.#")
    atlas = LearnedAtlas(tmp_path / "atlas.json")
    # a blind start: 1F seen, its ladder (5,1) goes to B1F per WRAM, nothing known about B1F yet
    atlas.observe(a, _view("Mt. Moon 1F", ["#######", "#P...D#", "#######"]), _warps_hex([(5, 1, 0, b)]), [])
    r = atlas.route(a, (1, 1), b)
    assert r and r[0].kind == "warp" and (r[0].x, r[0].y) == (5, 1)          # WRAM names the destination map
    assert atlas.route(a, (1, 1), c) is None                                 # B2F: not reachable through the atlas yet
    assert [(h.x, h.y) for h in atlas.frontier(a, (1, 1), {"Mt. Moon 1F"})] == [(5, 1)]
    # take the ladder: arrive at B1F (2,1); B1F has a ladder back at (2,1) and one to B2F at (5,1)
    atlas.observe(b, _view("Mt. Moon B1F", ["#######", "#.D..D#", "#######"]), _warps_hex([(2, 1, 0, a), (5, 1, 0, c)]), [])
    atlas.record_warp(a, 5, 1, b, 2, 1)
    assert atlas.map(b)["arrivals"]["2,1"] == {"map": a, "x": 5, "y": 1, "seen": False}   # assumed way back
    r = atlas.route(a, (1, 1), c)
    assert [(h.map, h.x, h.y) for h in r] == [(a, 5, 1), (b, 5, 1)]         # B2F through the known B1F ladder
    assert atlas.frontier(a, (1, 1), {"Mt. Moon 1F", "Mt. Moon B1F"}) == []  # the 1F ladder was taken
    atlas.save()
    again = LearnedAtlas(tmp_path / "other.json", seed=tmp_path / "atlas.json")   # carried into a later run
    assert again.route(a, (1, 1), c) is not None and again.stats()["warps_taken"] == 1


def test_learned_atlas_edges(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    r3, r4 = map_id("Route 3"), map_id("Route 4")
    atlas = LearnedAtlas(tmp_path / "atlas.json")
    atlas.observe(r3, _view("Route 3", ["#...#", "#...#"]), _warps_hex([]), [("north", "Route 4")])
    hops = atlas.frontier(r3, (2, 1), {"Route 3"})
    assert hops and hops[0].kind == "edge" and hops[0].side == "north" and hops[0].y == 0
    atlas.record_edge(r3, "north", 2, 0, r4, 7, 9)
    e = atlas.data["edges"]
    assert e[f"{r3}:north"]["offset"] == 5 and e[f"{r4}:south"] == {"map": r3, "offset": -5, "fixed": 0, "seen": False}
    _, trans = atlas.reach(r3, (2, 1))
    assert any(arr == (r4, 6, 9) for _, h, arr in trans if (h.x, h.y) == (1, 0))   # the offset applies along the edge


def test_results_record_how_maps_were_known():
    from bench.report import map_cell
    assert map_cell({"variant": "solo"}) == "rom"                                    # runs before --map-source
    assert map_cell({"variant": "solo", "map_source": {"source": "learned", "atlas_seed": None}}) == "learned (blank)"
    assert map_cell({"variant": "solo", "map_source": {"source": "learned", "atlas_seed": "a.json"}}) == "learned (carried atlas)"
    from bench.run import build_parser
    assert build_parser().parse_args(["--mode", "jev-solo"]).map_source == "learned"


def test_learned_atlas_remembers_unreachable_targets(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b2 = map_id("Mt. Moon B2F")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(b2, _view("Mt. Moon B2F", ["#######", "#D...D#", "#######"]), _warps_hex([(1, 1, 0, 60), (5, 1, 1, 60)]), [])
    assert {(h.x, h.y) for h in atlas.frontier(b2, (4, 1), set())} == {(1, 1), (5, 1)}
    atlas.record_noroute(b2, (4, 1), (1, 1))            # the map view hid an elevation step
    assert {(h.x, h.y) for h in atlas.frontier(b2, (4, 1), set())} == {(5, 1)}
    atlas.record_walk(b2, (4, 1), (3, 1))
    assert {(h.x, h.y) for h in atlas.frontier(b2, (4, 1), set(), blocked=frozenset({f"{b2}:5,1"}))} == set()
    atlas.save()
    assert LearnedAtlas(tmp_path / "b.json", seed=tmp_path / "a.json").unreachable(b2, (3, 1), (1, 1))


def test_unreachable_record_only_counts_in_its_own_section(tmp_path):
    # Rock Tunnel B1F (full run 51): "no route to (3,3)" from (23,16) hid the way from (23,11), behind a wall 5 cells off
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b1 = map_id("Rock Tunnel B1F")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(b1, _view("Rock Tunnel B1F", ["#######", "#D...D#", "##.#.##", "#....D#", "#######"]),
                  _warps_hex([(1, 1, 0, 82), (5, 1, 1, 82), (5, 3, 2, 82)]), [])   # the map view shows no elevation step
    atlas.record_walk(b1, (4, 3), (2, 3))
    atlas.record_noroute(b1, (2, 3), (1, 1))           # learned below, where (1,1) really is out of reach
    assert atlas.unreachable(b1, (4, 3), (1, 1))       # walked from there: it counts
    assert {(h.x, h.y) for h in atlas.frontier(b1, (2, 1), set())} == {(1, 1), (5, 1), (5, 3)}   # came by ladder: try
    atlas.record_noroute(b1, (2, 1), (1, 1))           # refused from there too: now it counts there as well
    assert {(h.x, h.y) for h in atlas.frontier(b1, (2, 1), set())} == {(5, 1), (5, 3)}
    atlas.save()
    assert LearnedAtlas(tmp_path / "b.json", seed=tmp_path / "a.json").unreachable(b1, (4, 3), (1, 1))   # walks persist


def test_agent_links_consecutive_positions_on_a_map(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    b1 = map_id("Rock Tunnel B1F")
    agent.learn_walked(J.parse("walked\nf1 Rock Tunnel B1F (33,25) facing up | C L24 38/68 | ¥2543 | 3 badges"))
    agent.s["step"] += 4                                 # a battle cut the walk short
    agent.learn_walked(J.parse("walked\nf1 Rock Tunnel B1F (23,16) facing up | C L24 38/68 | ¥2543 | 3 badges"))
    agent.s["step"] += 1
    agent.learn_walked(J.parse("walked\nf1 Rock Tunnel 1F (17,11) facing up | C L24 38/68 | ¥2543 | 3 badges"))
    agent.s["step"] += 1
    agent.learn_walked(J.parse("walked\nf1 Rock Tunnel B1F (23,11) facing up | C L24 38/68 | ¥2543 | 3 badges"))
    assert agent.nav.linked(b1, (33, 25), (23, 16)) and not agent.nav.linked(b1, (23, 16), (23, 11))


@requires_rom
def test_refusals_without_a_status_line_still_count(nav, tmp_path):
    """The server's 'no walkable route' reply has no status line; iteration 7 never recorded it (no clear option)."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=nav)
    o = J.parse("walked\nf1 Mt. Moon B2F (13,7) facing up | Charmeleon L24 38/68 | ¥2543 | 1 badges")
    opt = J.Option("follow the map route to Cerulean City: walk to the warp at (5,7) → Mt. Moon B1F", "walk", {"path": "to 5,7"})
    agent.nav_feedback(o, opt, J.parse("no walkable route from (13,7) to (5,7) on this map"), "61:5,7")
    assert "61:5,7" in agent.s["nav_noroute"]
    o.npcs = [(12, 6), (13, 6), (12, 8)]                  # the two fossils and the Super Nerd
    opts, _ = agent.nav_options(o, ["Mt. Moon B1F", "Mt. Moon B2F", "Route 4", "Cerulean City"], SOLO.Facts(badges=1))
    assert opts[0].label.startswith("follow the map route to Cerulean City: first clear the way at (1")
    agent.nav_feedback(o, opts[0], J.parse("dialogue ended\nf1 Mt. Moon B2F (12,7) facing up | C L24 38/68 | ¥2543 | 1 badges"), "")
    agent.nav_feedback(o, opts[0], J.parse("dialogue ended\nf1 Mt. Moon B2F (12,7) facing up | C L24 38/68 | ¥2543 | 1 badges"), "")
    again, _ = agent.nav_options(o, ["Cerulean City"], SOLO.Facts(badges=1))
    assert again[0].label != opts[0].label                # tried twice and still there: no longer a blocker


def test_learned_frontier_prefers_the_objectives_maps(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b1 = map_id("Mt. Moon B1F")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(b1, _view("Mt. Moon B1F", ["#######", "#D.D.D#", "#######"]),
                  _warps_hex([(1, 1, 0, 61), (3, 1, 0, 0xFF), (5, 1, 1, 61)]), [], last_map_text="D365: 0F")
    hops = atlas.frontier(b1, (2, 1), {"Mt. Moon B2F", "Route 4"}, prefer=("Route 4", "Cerulean City"))
    assert (hops[0].x, hops[0].dest_name) == (3, "Route 4")     # the exit: wLastMap names it, the objective lists it


def test_learned_refusal_with_a_blocker_on_the_path_is_not_a_wall(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b2 = map_id("Mt. Moon B2F")
    (tmp_path / "data").mkdir()
    a = _agent_args(tmp_path, "solo")
    agent = Agent(a, FakeServer(), J.JevPolicy(J.MockJev()), nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(b2, _view("Mt. Moon B2F", ["#######", "#D..P.#", "#######"]), _warps_hex([(1, 1, 0, 60)]), [])
    o = J.parse("walked\nf1 Mt. Moon B2F (4,1) facing left | C L24 38/68 | ¥2543 | 1 badges")
    opt = J.Option("walk to the warp at (1,1) → Mt. Moon B1F", "walk", {"path": "to 1,1"})
    agent.nav_feedback(o, opt, J.parse("no walkable route from (4,1) to (1,1) on this map"), "")
    o.npcs = [(2, 1)]                                   # someone stands in the corridor
    agent.learn_noroute(o)
    assert not agent.nav.unreachable(b2, (4, 1), (1, 1))
    agent.nav_feedback(o, opt, J.parse("no walkable route from (4,1) to (1,1) on this map"), "")
    o.npcs = []                                         # nobody: a wall the map view did not show
    agent.learn_noroute(o)
    assert agent.nav.unreachable(b2, (4, 1), (1, 1))


def test_unreachable_blocker_means_a_wall_not_a_try(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b2 = map_id("Mt. Moon B2F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(b2, _view("Mt. Moon B2F", ["#######", "#D..P.#", "#######"]), _warps_hex([(1, 1, 0, 60)]), [])
    o = J.parse("walked\nf1 Mt. Moon B2F (4,1) facing left | C L24 38/68 | ¥2543 | 1 badges")
    o.npcs = [(2, 1)]
    agent.s["nav_noroute"][f"{b2}:1,1"] = agent.s["step"]
    opts, _ = agent.nav_options(o, ["Cerulean City"], SOLO.Facts(badges=1))
    clear = next(x for x in opts if "first clear the way" in x.label)
    agent.nav_feedback(o, clear, J.parse("no walkable route from (4,1) to (3,1) on this map"), "")
    assert agent.nav.unreachable(b2, (4, 1), (1, 1)) and not agent.s.get("clear_tries")


def test_route_through_a_small_tree_offers_cut(tmp_path):
    """Full run 41: Cut learned, but the server's walk never crosses a tree (the Vermilion Gym is behind one)."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b2 = map_id("Mt. Moon B2F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(b2, _view("Mt. Moon B2F", ["########", "#D.T.P.#", "########"]), _warps_hex([(1, 1, 0, 60)]), [])
    o = J.parse("walked\nf1 Mt. Moon B2F (5,1) facing left | C L24 38/68 | ¥2543 | 2 badges")
    opt = J.Option("walk to the warp at (1,1) → Mt. Moon B1F", "walk", {"path": "to 1,1"})
    agent.nav_feedback(o, opt, J.parse("no walkable route from (5,1) to (1,1) on this map"), "")
    agent.learn_noroute(o)
    assert not agent.nav.unreachable(b2, (5, 1), (1, 1))                   # the tree is not a hidden wall
    opts, _ = agent.nav_options(o, ["Cerulean City"], SOLO.Facts(badges=2, moves={"Cut"}))
    cut = next(x for x in opts if "first cut the tree at (3,1)" in x.label)
    assert cut.args["path"] == "to 4,1" and cut.then == [("walk", {"path": "left 1", "on_battle": "stop"}),
                                                          ("manage", {"action": "field", "target": "Cut"})]
    opts, _ = agent.nav_options(o, ["Cerulean City"], SOLO.Facts(badges=2, moves={"Tackle"}))
    assert not any("cut the tree" in x.label for x in opts)                # no Cut: no such option


def test_route_across_water_offers_surf_from_the_shore(tmp_path):
    """Pallet Town's south edge to Route 21 is water: the server's walk refuses a water cell until the player surfs.
    The refusal is not a wall, and the route's hop becomes 'walk to the shore, face the water, use Surf'."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    pal = map_id("Pallet Town")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(pal, _view("Pallet Town", ["#########", "#P..~~.D#", "#########"]), _warps_hex([(7, 1, 0, 60)]), [])
    o = J.parse("walked\nf1 Pallet Town (1,1) facing right | C L50 138/168 | ¥2543 | 6 badges")
    opt = J.Option("walk to the warp at (7,1) → Route 21", "walk", {"path": "to 7,1"})
    agent.nav_feedback(o, opt, J.parse("no walkable route from (1,1) to (7,1) on this map"), "")
    agent.learn_noroute(o)
    assert not agent.nav.unreachable(pal, (1, 1), (7, 1))                  # water is not a hidden wall
    opts, _ = agent.nav_options(o, ["Route 21"], SOLO.Facts(badges=6, moves={"Surf"}))
    surf = next(x for x in opts if "first surf from the shore onto the water at (4,1)" in x.label)
    assert surf.args["path"] == "to 3,1" and surf.then == [("walk", {"path": "right 1", "on_battle": "stop"}),
                                                           ("manage", {"action": "field", "target": "Surf"})]
    o2 = J.parse("walked\nf1 Pallet Town (4,1) facing right | C L50 138/168 | ¥2543 | 6 badges")   # surfing already
    opts, _ = agent.nav_options(o2, ["Route 21"], SOLO.Facts(badges=6, moves={"Surf"}))
    assert not any("first surf" in x.label for x in opts)
    opts, _ = agent.nav_options(o, ["Route 21"], SOLO.Facts(badges=6, moves={"Cut"}))
    assert not any("first surf" in x.label for x in opts)                  # no Surf: no such option


def test_tree_behind_a_ledge_is_still_found(tmp_path):
    """Full run 43: Route 9's tree lies before a maze of ledges; the path traced back through distances broke at
    the first jump, so no Cut option, and the refusal was learned as a wall."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    r9 = map_id("Route 9")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(r9, _view("Route 9", ["########", "#P.T..##", "####v###", "#.....D#", "########"]),
                      _warps_hex([(6, 3, 0, 60)]), [])
    assert (3, 1) in agent.nav.path_cells(r9, (1, 1), (6, 3), cut=True)   # tree, then the jump at (4,2)
    o = J.parse("walked\nf1 Route 9 (1,1) facing right | C L42 38/68 | ¥2543 | 3 badges")
    opt = J.Option("walk to the warp at (6,3) → Mt. Moon B1F", "walk", {"path": "to 6,3"})
    agent.nav_feedback(o, opt, J.parse("no walkable route from (1,1) to (6,3) on this map"), "")
    agent.learn_noroute(o)
    assert not agent.nav.unreachable(r9, (1, 1), (6, 3))
    opts, _ = agent.nav_options(o, ["Cerulean City"], SOLO.Facts(badges=3, moves={"Cut"}))
    assert any("first cut the tree at (3,1)" in x.label for x in opts)


def test_talk_refused_by_a_tree_offers_cut(tmp_path):
    """Full run 44: Erika sits behind the Celadon Gym's trees; the talk option was refused ~240 times."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    gym = map_id("Celadon Gym")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(gym, _view("Celadon Gym", ["#######", "#..N..#", "#.....#", "##T####", "#.....#", "###D###"]),
                      _warps_hex([(3, 5, 0, 0xFF)]), [])
    o = J.parse("walked\nf1 Celadon Gym (3,4) facing up | C L49 138/168 | ¥2543 | 3 badges")
    talk = J.Option("talk to the person or object at (3,1)", "walk", {"path": "to 3,2"})
    agent.s["tree_target"] = None
    after = J.parse("no walkable route from (3,4) to (3,2) on this map — a small tree (T) blocks part of this map")
    agent.nav_feedback(o, talk, after, "")
    tr = re.match(r"no walkable route from \(\d+,\d+\) to \((\d+),(\d+)\).*small tree", after.head)
    assert tr                                                              # what the agent stores after the action
    agent.s["tree_target"] = [gym, int(tr[1]), int(tr[2]), agent.s["step"]]
    opts, _ = agent.nav_options(o, ["Celadon Gym"], SOLO.Facts(badges=3, moves={"Cut"}))
    cut = next(x for x in opts if "first cut the tree at (2,3)" in x.label)
    assert cut.args["path"] == "to 2,4" and cut.then[0] == ("walk", {"path": "up 1", "on_battle": "stop"})
    # full run 60: the "no way there" stamp from before the cut hid Erika right after it
    agent.remember_talk(o, talk, after)
    agent.remember_tree(o, after, after.head)
    assert agent.s["tree_target"][1:3] == [3, 2] and "3,1" in agent.s["talk_noroute"]["Celadon Gym"]
    agent.remember_tree(o, J.parse("walked\nf1 Celadon Gym (2,4) facing up | C L49 138/168 | ¥2543 | 3 badges"),
                        "AAAAAAAAAA hacked away with CUT!")
    assert "tree_target" not in agent.s and not agent.s["talk_noroute"].get("Celadon Gym")


def test_four_moves_prompt_is_not_an_hm_refusal(tmp_path):
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    teach = J.Option("teach HM01 (Cut) to Charizard", "manage", {"action": "use", "target": "HM01", "target2": "Charizard: weakest"})
    agent.remember_refusal(teach, "Booted up an HM! | AAAAAAAAAA is trying to learn | trying to learn CUT! | But, AAAAAAAAAA "
                                  "can't learn more | can't learn more than 4 moves! | AAAAAAAAAA learned CUT!")
    assert not agent.s.get("hm_no")                                        # full run 45: Charizard never got Cut
    agent.remember_refusal(dataclasses.replace(teach, args=dict(teach.args, target2="Magikarp: weakest")),
                           "MAGIKARP is not compatible with | compatible with CUT. | It can't learn CUT.")
    assert agent.s["hm_no"] == ["HM01:Magikarp"]


def test_a_full_bag_is_made_room_in_by_code(tmp_path):
    """Full run 55: 20 kinds in the bag, "No more room for items!" for the Lift Key, ~2,100 steps on B4F."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    bag = [("Antidote", 1), ("S.S. Ticket", 1), ("HM01", 1), ("Moon Stone", 1), ("Potion", 3), ("TM34", 1)]
    bag += [(f"Item{i}", 1) for i in range(20 - len(bag))]
    d = agent.director
    assert d.bag_option(bag[:18]) is None                                 # two free slots: nothing to do
    assert d.bag_option(bag[:19]).args["target"] == "TM34"                 # one: keep it free for the next pickup
    toss = d.bag_option(bag)
    assert toss.tool == "manage" and toss.args == {"action": "toss", "target": "TM34"}, toss
    agent.remember_refusal(toss, "TM34 is too important to toss; bag: ...")
    assert d.bag_option(bag).args["target"] == "Moon Stone"                # a refused toss is not offered again
    agent.remember_refusal(d.bag_option(bag), "threw away Moon Stone×1; bag: ...")
    assert d.bag_option(bag).args["target"] == "Moon Stone"                # (a real toss leaves the bag at 19)
    keep = [("S.S. Ticket", 1), ("HM01", 1), ("Potion", 3)] + [(f"Item{i}", 1) for i in range(16)]
    assert d.bag_option(keep) is None                                      # nothing it may throw away
    # full run 63: "could not select TOSS" (the bag menu's cursor) is not a refusal: retried after a pause
    agent.s["step"] = 100
    agent.remember_refusal(d.bag_option(bag), "could not select TOSS")
    assert d.bag_option(bag) is None
    agent.s["step"] = 100 + SOLO.TOSS_RETRY_STEPS
    assert d.bag_option(bag).args["target"] == "Moon Stone"


def test_a_team_out_of_attack_pp_goes_to_heal():
    """Full run 58: Charizard left Rock Tunnel at full-ish HP with only Leer, Struggled against a Pidgey, blacked out."""
    from games import gen1_data as D
    assert SOLO.STATUS_MOVES <= set(D.MOVES.values())
    d = SOLO.SoloDirector({"visited": ["Route 10", "Lavender Town"], "milestones": [], "healed_at": ["Lavender Poké Center"]})
    route = J.parse("walked\nf1 Route 10 (8,54) facing down | C L52 120/157 | ¥3000 | 3 badges")
    tired = [{"species": "Charizard", "level": 52, "hp": 120, "max_hp": 157,
              "moves": [{"name": "Slash", "pp": 0}, {"name": "Leer", "pp": 30}, {"name": "Ember", "pp": 3}]}]
    f = d.facts(route, tired, [])
    assert f.attack_pp == 3
    text, targets, why = d.objective(f, route)
    assert why == "heal" and targets[0] == "Rock Tunnel Poké Center" and "PP" in text, text
    rested = [dict(tired[0], moves=[{"name": "Slash", "pp": 20}, {"name": "Leer", "pp": 30}, {"name": "Ember", "pp": 25}])]
    rested[0]["hp"] = 157
    assert d.objective(d.facts(route, rested, []), route)[2] != "heal"
    assert SOLO.attack_pp([dict(tired[0], hp=0)]) == 0 and SOLO.attack_pp([{"hp": 5}]) is None


def test_the_poke_flute_is_played_at_a_sleeping_snorlax(tmp_path):
    """Full run 56: ~700 talks to the Route 12 Snorlax with the Poké Flute in the bag."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    d, bag = agent.director, [("Poké Flute", 1), ("HM01", 1)]
    agent.s["history"] = ["talk to what you are facing -> dialogue ended: A sleeping POKéMON blocks the way!"]
    flute = d.flute_option(bag)
    assert flute.tool == "manage" and flute.args == {"action": "use", "target": "Poké Flute"}
    assert d.flute_option([("HM01", 1)]) is None                           # no flute yet: nothing to play
    agent.s["history"].append("play the Poké Flute to wake the sleeping Pokémon -> BATTLE (wild) starting")
    assert d.flute_option(bag) is None


def test_vermilion_gym_trash_cans_are_searched_in_order():
    """Full run 42: in the Vermilion Gym with every person talked to, Jev walked out and back in ~600 times."""
    d = SOLO.SoloDirector({"visited": ["Vermilion Gym"], "milestones": []})
    o = J.parse("walked\nf1 Vermilion Gym (3,8) facing up | Charizard L37 100/120 | ¥3000 | 2 badges")
    f = SOLO.Facts(badges=2, moves={"Cut"})
    cans = [x for x in d.extra_options(o, f, [], [], [], "surge") if x.label.startswith("search the trash can")]
    assert cans[0].label == "search the trash can at (3,7)" and cans[0].args["path"] == "up 1"   # it stands below it
    assert cans[0].then == [("talk", {})] and cans[1].then[0] == ("walk", {"path": "up 1", "on_battle": "stop"})
    o.npcs = [(3, 8)]                                                       # full run 45: a trainer stands below it
    blocked = next(x for x in d.extra_options(o, f, [], [], [], "surge") if x.label == "search the trash can at (3,7)")
    assert blocked.args["path"] == "to 3,6" and blocked.then[0][1]["path"] == "down 1"
    o.npcs = []
    d.trash_result("search the trash can at (3,7)", "dialogue ended: Nope, there's only trash here.")
    labels = [x.label for x in d.extra_options(o, f, [], [], [], "surge")]
    assert "search the trash can at (3,7)" not in labels
    d.trash_result("search the trash can at (5,9)", "dialogue ended: Hey! There's a switch under the trash! | Turn it on!")
    labels = {x.label for x in d.extra_options(o, f, [], [], [], "surge") if x.label.startswith("search")}
    assert labels == {f"search the trash can at ({x},{y})" for x, y in ((3, 9), (7, 9), (5, 7), (5, 11))}
    d.trash_result("search the trash can at (3,9)", "Nope! There's only trash here. | Hey! The electric locks were reset!")
    assert d.s["trash"]["first"] is None and not d.s["trash"]["tried"]
    d.trash_result("search the trash can at (1,7)", "Hey! There's a switch under the trash!")
    d.trash_result("search the trash can at (1,9)", "The 2nd electric lock opened! | The motorized door opened!")
    assert not [x for x in d.extra_options(o, f, [], [], [], "surge") if x.label.startswith("search")]


def test_a_checkpoint_follows_progress_made_too_soon_or_off_the_overworld():
    """Codex review 2: progress one step after a checkpoint was throttled, and at the next allowed step it was no longer
    'this step', so no checkpoint followed it (and a reload could go back to before an event the agent keeps)."""
    d = SOLO.SoloDirector({"last_progress_step": 0, "checkpoint_step": None})
    assert d.want_checkpoint(0)
    d.s["last_progress_step"] = 3                       # an event right after the checkpoint
    assert not d.want_checkpoint(3) and not d.want_checkpoint(20)
    assert d.want_checkpoint(25)                         # still pending: saved at the first allowed step
    assert not d.want_checkpoint(60)                     # nothing new since
    d.s["last_progress_step"] = 70                       # progress in a dialogue; the next overworld step is 74
    assert d.want_checkpoint(74)


def test_ordinary_warp_options_skip_a_blocked_warp(tmp_path):
    """Codex review 2 / volcano experiment: the locked Cinnabar Gym door ("dialogue appeared") was blocked for the
    route and the frontier, but the plain 'walk to the warp' option offered it ~40 times."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    isl = map_id("Cinnabar Island")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(isl, _view("Cinnabar Island", ["#######", "#D.P.D#", "#######"]),
                      _warps_hex([(1, 1, 0, map_id("Cinnabar Gym")), (5, 1, 0, map_id("Cinnabar Lab"))]), [])
    o = J.parse("walked\nf1 Cinnabar Island (3,1) facing up | C L60 200/207 | ¥3000 | 6 badges")
    opts, _ = agent.nav_options(o, ["Pokémon Mansion 1F"], SOLO.Facts(badges=6))
    assert any("(1,1)" in x.label for x in opts)
    agent.s["nav_blocked"][f"{isl}:1,1"] = agent.s["step"] + 300
    opts, _ = agent.nav_options(o, ["Pokémon Mansion 1F"], SOLO.Facts(badges=6))
    assert not any("(1,1)" in x.label for x in opts), [x.label for x in opts]   # the frontier dropped it; so does the plain option
    assert any("(5,1)" in x.label for x in opts)


def test_mansion_switches_are_offered_and_a_press_forgets_every_floor(tmp_path):
    """Volcano-leg experiment: the Mansion's switches were walls in the map view and never pressed. S cells this part
    of the floor reaches are offered (stand below, face up, talk); "Who wouldn't?" (the YES answer) changes doors on
    every floor, so refusals and walks learned on all Mansion floors are forgotten."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    f1, f2 = map_id("Pokémon Mansion 1F"), map_id("Pokémon Mansion 2F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(f1, _view("Pokémon Mansion 1F", ["#######", "#.S##.#", "#.P.D##", "#######"]), _warps_hex([(4, 2, 0, f2)]), [])
    agent.nav.observe(f2, _view("Pokémon Mansion 2F", ["#####", "#P.D#", "#####"]), _warps_hex([(3, 1, 0, f1)]), [])
    agent.nav.record_noroute(f2, (1, 1), (3, 1))
    agent.nav.record_walk(f2, (1, 1), (2, 1))
    o = J.parse("walked\nf1 Pokémon Mansion 1F (2,2) facing up | C L60 200/207 | ¥3000 | 6 badges")
    rest = [J.Option("walk down 4 tiles", "walk", {"path": "down 4"})]
    opts = agent.switch_options(o, rest)
    assert opts[0].label == "press the secret switch at (2,1) (from below)" and "not pressed yet" in opts[0].desc
    assert opts[0].args == {"path": "up 1", "on_battle": "stop"} and opts[0].then == [("talk", {})]
    onward = [J.Option("explore the frontier: walk to the untaken warp at (4,2) → Pokémon Mansion 2F", "walk", {"path": "to 4,2"})]
    assert agent.switch_options(o, onward)[-1].label.startswith("press the secret switch")   # last while there is a way on
    agent.nav.data["maps"][str(f1)]["warps"].append([5, 1, 0, map_id("Pokémon Mansion B1F")])     # stairs behind a wall
    agent.nav._maps.pop(f1, None)
    shut = agent.switch_options(o, onward + rest)
    assert shut[0].label.startswith("press the secret switch") and "walk down 4 tiles" not in [x.label for x in shut]
    agent.nav.data["maps"][str(f1)]["warps"].pop()
    agent.nav._maps.pop(f1, None)
    agent.s["nav_noroute"][f"{f2}:3,1"] = agent.s["nav_blocked"][f"{f2}:3,1"] = agent.s["step"]
    agent.remember_door(o, opts[0], "said: A secret switch! | Press it?")
    agent.s["prev_map"] = "Pokémon Mansion 1F"
    agent.remember_door(J.parse("choice:\n▶YES\nNO"), J.Option("continue the conversation", "talk", {}),
                        "dialogue ended: Who wouldn't?")     # a dialogue: no map in the observation
    assert agent.s["reobserve"] == "Pokémon Mansion 1F"
    assert f"{f2}:3,1" not in agent.s["nav_noroute"] and f"{f2}:3,1" not in agent.s["nav_blocked"]
    m2 = agent.nav.data["maps"][str(f2)]
    assert not m2.get("noroute") and not m2.get("walked")
    facing = [J.Option("talk to what you are facing", "talk", {})] + rest
    assert [x.label for x in agent.switch_options(o, facing)] == ["walk down 4 tiles"]   # just pressed: no press back
    agent.s["step"] += 41
    assert "pressed 1 time(s)" in agent.switch_options(o, rest)[0].desc
    prompt = J.parse("said: A secret switch!\nscreen:\nA secret switch!\n              ▶YES\n               NO\nPress it?")
    assert prompt.mode == "prompt"
    assert [x.label for x in agent.options(prompt, [], [], [])] == ["choose YES"]   # the switch was chosen on purpose
    assert agent.switch_options(J.parse("walked\nf1 Cinnabar Island (2,2) facing up | C L60 200/207 | ¥3000 | 6 badges"), rest) == rest


def test_a_trainer_beaten_in_the_cinnabar_gym_reopens_its_floor(tmp_path):
    """Codex review 2: in Blaine's gym each trainer beaten opens a gate; the floor is read again and the ways refused
    while it was shut are forgotten. Elsewhere a win changes nothing."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    gym = map_id("Cinnabar Gym")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.s["prev_map"] = "Cinnabar Gym"
    agent.s["nav_noroute"][f"{gym}:5,5"] = agent.s["step"]
    win = "Enemy PONYTA fainted! | AAAAAAA defeated SUPER NERD! | SUPER NERD: Ahh! | AAAAAAA got ¥1000 for winning!"
    agent.remember_door(J.parse("BATTLE (trainer): enemy PONYTA L36 0/90 | you CHARIZARD L62 150/205 | FIGHT"),
                        J.Option("auto-battle", "battle", {"action": "auto"}), win)
    assert agent.s["reobserve"] == "Cinnabar Gym" and f"{gym}:5,5" not in agent.s["nav_noroute"]
    agent.s.pop("reobserve")
    agent.s["prev_map"] = "Route 21"
    agent.remember_door(J.parse("BATTLE (trainer): enemy STARYU L30 0/90 | you CHARIZARD L62 150/205 | FIGHT"),
                        J.Option("auto-battle", "battle", {"action": "auto"}), win.replace("SUPER NERD", "SWIMMER"))
    assert "reobserve" not in agent.s


def test_floor_never_walked_on_is_offered_while_the_last_target_is_unknown(tmp_path):
    """Volcano-leg experiments: Mansion 3F's holes (plain-looking collapsed floor) are the only way to 1F's stairs to
    B1F; the run walked the floors' known parts ~450 steps without falling. Reachable floor far from every cell stood
    on is offered while the objective's last map is unknown; a fall on such a walk is not recorded as a warp."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    f3 = map_id("Pokémon Mansion 3F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(f3, _view("Pokémon Mansion 3F", ["##############", "#P...........#", "##############"]), _warps_hex([]), [])
    targets = ["Pokémon Mansion 1F", "Pokémon Mansion 3F", "Pokémon Mansion B1F"]
    o = J.parse("walked\nf1 Pokémon Mansion 3F (1,1) facing up | C L60 200/207 | ¥3000 | 6 badges")
    agent.learn_trod(o)
    opts = agent.floor_options(o, [], targets)
    assert [x.label for x in opts] == ["explore the unvisited floor at (5,1)", "explore the unvisited floor at (12,1)"]
    agent.s["trod"]["Pokémon Mansion 3F"] += [[6, 1], [10, 1]]
    assert [x.label for x in agent.floor_options(o, [], targets)] == []      # all walked (within 3 cells)
    agent.s["trod"]["Pokémon Mansion 3F"] = [[1, 1]]
    agent.nav.observe(map_id("Pokémon Mansion B1F"), _view("Pokémon Mansion B1F", ["###", "#P#", "###"]), _warps_hex([]), [])
    assert agent.floor_options(o, [], targets) == []                         # the last target is known: routes do it
    fall = J.parse("went toward (12,1): right 6/11 — stopped: entered Pokémon Mansion 1F\n"
                   "f1 Pokémon Mansion 1F (16,14) facing right | C L60 200/207 | ¥3000 | 6 badges")
    agent.nav_feedback(o, J.Option("explore the unvisited floor at (12,1)", "walk", {"path": "to 12,1"}), fall, "")
    assert "12,1" not in agent.nav.data["maps"][str(f3)].get("arrivals", {})


def test_a_carried_atlas_counts_its_maps_as_visited(tmp_path):
    """it75 end-state experiment: with a carried atlas but fresh agent memory, every map looked first reached during
    the objective, so the frontier beat the route to Pallet Town. A blank atlas (goal runs) leaves visited empty."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    old = LearnedAtlas(tmp_path / "old.json")
    old.observe(map_id("Pallet Town"), _view("Pallet Town", ["#####", "#P..#", "#####"]), _warps_hex([]), [])
    old.data["maps"][str(map_id("Pallet Town"))]["visits"] = 3
    old.save()
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json", seed=tmp_path / "old.json"))
    assert agent.s["visited"] == ["Pallet Town"]
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "data").mkdir()
    blank = Agent(_agent_args(tmp_path / "b", "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "b" / "data" / "jev_atlas.json"))
    assert blank.s["visited"] == []


def test_rom_maps_and_carried_atlases_are_experiments_only(monkeypatch):
    from bench import run
    from bench.report import map_cell
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    for extra in (["--map-source", "rom"], ["--atlas", "a.json"]):
        with pytest.raises(SystemExit, match="experiment"):
            run.main(["--mode", "jev-solo"] + extra)
    h = {"variant": "solo", "experiment": "carry", "map_source": {"source": "learned", "atlas_seed": "a.json"}}
    assert map_cell(h) == "learned (carried atlas) — experiment"


def test_resume_rejects_other_settings(tmp_path, monkeypatch):
    """Codex review: --resume-run kept the old metadata but ran the new CLI settings."""
    from bench import run
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    r = run.Run(run.parse_args(["--mode", "jev-solo", "--mock"]))
    r.dir.mkdir(parents=True)
    r.state_path.write_text(json.dumps(r.state))
    again = run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--smoke", "--resume-run", str(r.dir)]))
    assert again.state["config"] == r.state["config"]
    with pytest.raises(SystemExit, match="stuck-fail-steps"):
        run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--smoke", "--resume-run", str(r.dir), "--stuck-fail-steps", "50"]))
    with pytest.raises(SystemExit, match="map_source"):
        run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--smoke", "--resume-run", str(r.dir), "--map-source", "rom",
                                "--experiment", "x"]))


def test_resume_rejects_another_hybrid_planner(tmp_path, monkeypatch):
    """Codex review: jev-hybrid's --model is the Claude planner (provider.planner_model), not the recorded model."""
    from bench import run
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    base = ["--mode", "jev-hybrid", "--mock"]
    r = run.Run(run.parse_args(base + ["--model", "claude-haiku-4-5-20251001"]))
    assert r.state["config"]["planner_model"] == "claude-haiku-4-5-20251001"
    r.dir.mkdir(parents=True)
    r.state_path.write_text(json.dumps(r.state))
    resume = base + ["--smoke", "--resume-run", str(r.dir)]
    run.Run(run.parse_args(resume + ["--model", "claude-haiku-4-5-20251001"]))
    with pytest.raises(SystemExit, match="planner_model"):
        run.Run(run.parse_args(resume + ["--model", "claude-sonnet-4-5"]))
    # Codex review (21:00): a config written before planner_model existed resumes with the planner it recorded
    pre = dict(r.state, config={k: v for k, v in r.state["config"].items() if k != "planner_model"})
    r.state_path.write_text(json.dumps(pre))
    run.Run(run.parse_args(resume + ["--model", "claude-haiku-4-5-20251001"]))      # from the display model
    with pytest.raises(SystemExit, match="planner_model"):
        run.Run(run.parse_args(resume + ["--model", "claude-sonnet-4-5"]))
    (r.dir / "chunks").mkdir()
    r.provider.prepare(r.dir, ["python", "server.py"])
    (r.dir / "chunks" / "001.cmd").write_text(" ".join(r.provider.command(r.dir, None, r.run_id, True)) + "\n")
    r.state_path.write_text(json.dumps(dict(pre, display_model="")))
    run.Run(run.parse_args(resume + ["--model", "claude-haiku-4-5-20251001"]))      # from the agent command
    (r.dir / "chunks" / "001.cmd").unlink()
    with pytest.raises(SystemExit, match="cannot be established"):
        run.Run(run.parse_args(resume + ["--model", "claude-haiku-4-5-20251001"]))
    solo = run.Run(run.parse_args(["--mode", "jev-solo", "--mock"]))
    solo.dir.mkdir(parents=True)
    solo.state_path.write_text(json.dumps(dict(solo.state, config={k: v for k, v in solo.state["config"].items()
                                                                   if k != "planner_model"})))
    run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--smoke", "--resume-run", str(solo.dir)]))


def test_resume_checks_a_checkpoint_without_config(tmp_path, monkeypatch):
    """Codex review: checkpoints from before `config` skipped the check and adopted whatever was passed. They are now
    compared on their metadata and the first chunk's agent command; without provider/model the resume is refused."""
    from bench import run
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    r = run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--smoke"]))
    legacy = {k: v for k, v in r.state.items() if k != "config"}
    legacy.update(mode="jev-solo", map_source={"source": "learned", "atlas_seed": None, "start": "blank"},
                  track="jev", variant="solo", display_model=r.provider.display_model, mock=True, jev_model=r.model)
    (r.dir / "chunks").mkdir(parents=True)
    r.state_path.write_text(json.dumps(legacy))
    resume = ["--mock", "--smoke", "--resume-run", str(r.dir)]
    ok = run.Run(run.parse_args(["--mode", "jev-solo"] + resume))
    assert ok.state["config"]["mode"] == "jev-solo"
    with pytest.raises(SystemExit, match="mode: 'jev-solo' -> 'jev-assist'"):
        run.Run(run.parse_args(["--mode", "jev-assist"] + resume))
    r.provider.prepare(r.dir, ["python", "server.py"])
    (r.dir / "chunks" / "001.cmd").write_text(" ".join(r.provider.command(r.dir, None, r.run_id, True)) + "\n")
    run.Run(run.parse_args(["--mode", "jev-solo"] + resume))
    with pytest.raises(SystemExit, match="agent command.*stuck-fail-steps=50"):
        run.Run(run.parse_args(["--mode", "jev-solo", "--stuck-fail-steps", "50"] + resume))
    r.state_path.write_text(json.dumps({k: v for k, v in legacy.items() if k not in ("provider", "model")}))
    with pytest.raises(SystemExit, match="cannot be established"):
        run.Run(run.parse_args(["--mode", "jev-solo"] + resume))


def test_a_later_map_visited_early_does_not_skip_objectives():
    """Codex review: with Vermilion visited (Route 5, Underground Path) before Misty, the furthest-done rule returned
    'cut' and skipped Misty and the S.S. Ticket. Only badges and confirmed nodes skip ahead now."""
    f = SOLO.Facts(badges=1, levels=[24], visited={"Mt. Moon 1F", "Cerulean City", "Vermilion City"},
                   milestones=["game started", "starter: X"])
    assert SOLO.current_node(f).id == "misty"
    f.badges = 2
    assert SOLO.current_node(f).id == "ticket"
    f.badges = 0                                                            # no badge yet: Brock comes first
    f.visited |= {"Viridian City", "Viridian Forest", "Pewter City"}
    f.ever_items = {"Oak's Parcel"}
    assert SOLO.current_node(f).id == "brock"
    seg = SOLO.Facts(badges=1, levels=[24], visited={"Cerulean City"}, manual_done={"intro", "starter", "viridian",
                     "parcel", "deliver", "forest", "pewter", "brock", "mtmoon", "cerulean"})   # cerulean segment
    assert SOLO.current_node(seg).id == "misty"



def test_segment_progress_reaches_the_agent(tmp_path, monkeypatch):
    from bench import run
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    monkeypatch.setattr(run, "load_segment", lambda name: {"name": name, "state": None, "goal": "badge: Cascade",
                                                           "progress": "cerulean"})
    r = run.Run(run.parse_args(["--mode", "jev-solo", "--mock", "--segment", "cerulean"]))
    assert "--progress=cerulean" in r.provider.agent_args
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo", progress="cerulean"), FakeServer(), J.JevPolicy(J.MockJev()))
    assert agent.s["manual_done"][-1] == "cerulean" and "misty" not in agent.s["manual_done"]


def test_losing_at_a_gym_raises_its_level_target():
    d = SOLO.SoloDirector({"visited": ["Cerulean City", "Cerulean Gym"]})
    f = SOLO.Facts(badges=1, levels=[23, 15], hp_ratio=1.0, visited={"Mt. Moon 1F", "Cerulean City", "Cerulean Gym"},
                   milestones=["reached: Cerulean City"])
    o = J.parse("walked\nf1 Cerulean Gym (4,3) facing up | Charmeleon L24 60/68 | ¥3000 | 1 badges")
    d.track(1, o, f)
    assert d.objective(f, o)[2] == "misty"                                 # L23 >= 21: no training yet
    d.lost(f)                                                              # the agent calls it on "RED blacked out!"
    d.lost(f)                                                              # (once per black-out: the gym is not re-seen)
    assert d.s["level_bonus"] == {"misty": 5} and d.objective(f, o)[2] == "train"   # L23 + 3 = 26 (table 21 + 5)
    d.s["level_bonus"] = {}                            # iteration 38: L25 lost to Misty; 21 + 3 asked for no training
    f.levels = [25]
    d.s["gym_map_seen"] = "Cerulean Gym"
    d.lost(f)
    assert d.objective(f, o)[0].endswith("reaches level 28 (now 25).")


@requires_rom
def test_training_paces_in_real_tall_grass(nav, tmp_path):
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=nav)
    agent.s["visited"] = ["Pallet Town", "Route 1", "Viridian City"]
    o = J.parse("walked\nf1 Route 1 (10,30) facing up | Charmander L6 20/22 | ¥3000 | 0 badges")
    opt = agent.train_options(o, None)[0]
    gx, gy = map(int, opt.label.split("(")[1].rstrip(")").split(","))
    assert opt.label.startswith("train in the tall grass") and nav.map(nav_id("Route 1"))["cells"][gy][gx] == ","
    assert len(opt.then) >= 7 and opt.then[0][1]["path"].endswith(" 1")
    town = J.parse("walked\nf1 Viridian City (21,26) facing up | Charmander L6 20/22 | ¥3000 | 0 badges")
    assert agent.train_options(town, None)[0].label.startswith("follow the map route to the tall grass on Route 1")


def nav_id(name):
    from bench.jev_nav import map_id
    return map_id(name)


def test_learned_twin_doors_and_global_frontier(tmp_path):
    from bench.jev_atlas import LearnedAtlas, frontier_maps
    from bench.jev_nav import map_id
    city, house = map_id("Cerulean City"), map_id("Cerulean Trashed House")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(city, _view("Cerulean City", ["#######", "#..D..#", "#.....#"]), _warps_hex([(3, 1, 0, house)]), [])
    atlas.observe(house, _view("Cerulean Trashed House", ["###D###", "#.....#", "#..DD.#"]),
                  _warps_hex([(3, 2, 0, 0xFF), (4, 2, 0, 0xFF), (3, 0, 2, 0xFF)]), [], last_map_text="D365: 03")
    atlas.record_warp(city, 3, 1, house, 3, 2)
    atlas.record_warp(house, 3, 2, city, 3, 2)
    assert atlas.warp_dest(house, 1) == [(city, 3, 2)]                 # (4,2) is the other half of the front door
    assert [(h.x, h.y) for h in atlas.frontier(house, (3, 1), {"Cerulean City"})] == [(3, 0)]   # only the back door
    assert house in frontier_maps(atlas, {"Cerulean City", "Cerulean Trashed House"})
    # the agent outside, nothing left to explore in the city: offered the way back to the house (iteration 31 crashed here)
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=atlas)
    agent.s["visited"] = ["Cerulean City", "Cerulean Trashed House"]
    o = J.parse("walked\nf1 Cerulean City (3,2) facing down | C L24 38/68 | ¥2543 | 2 badges")
    opts, _ = agent.nav_options(o, ["Vermilion City"], SOLO.Facts(badges=2))
    assert any(x.label.startswith("explore the frontier: go to Cerulean Trashed House") for x in opts)
    # the same from a map whose way there starts with an edge crossing (iteration 31 crashed on that hop)
    r24 = map_id("Route 24")
    atlas.observe(r24, _view("Route 24", ["#######", "#.....#", "#.....#"]), _warps_hex([]), [("south", "Cerulean City")])
    atlas.observe(city, _view("Cerulean City", ["#.....#", "#..D..#", "#.....#"]), _warps_hex([(3, 1, 0, house)]),
                  [("north", "Route 24")])
    atlas.record_edge(r24, "south", 2, 2, city, 2, 0)
    agent.s["visited"].append("Route 24")
    o = J.parse("walked\nf1 Route 24 (2,1) facing down | C L24 38/68 | ¥2543 | 2 badges")
    opts, _ = agent.nav_options(o, ["Vermilion City"], SOLO.Facts(badges=2))
    go = next(x for x in opts if x.label.startswith("explore the frontier: go to "))
    assert go.label.endswith("(south edge)") and agent.edge_opts[go.label][0] == "south"
    # back in the city with a west neighbour whose only unexplored exit lies beyond a one-way ledge: not that one
    # (bills-house iteration 32 crossed to Route 4 and back ~400 times)
    r4 = map_id("Route 4")
    atlas.observe(city, _view("Cerulean City", ["#.....#", "...D..#", "#.....#"]), _warps_hex([(3, 1, 0, house)]),
                  [("north", "Route 24"), ("west", "Route 4")])
    atlas.record_edge(city, "north", 2, 0, r24, 2, 2)
    atlas.observe(r4, _view("Route 4", ["#######", "#D.>...", "#######"]), _warps_hex([(1, 1, 0, map_id("Mt. Moon 1F"))]),
                  [("east", "Cerulean City")])
    atlas.record_edge(city, "west", 0, 1, r4, 6, 1)
    atlas.record_edge(r4, "east", 6, 1, city, 0, 1)
    atlas.data["maps"] = {str(r4): atlas.data["maps"].pop(str(r4)), **atlas.data["maps"]}   # listed first, nearest
    agent.s["visited"].append("Route 4")
    o = J.parse("walked\nf1 Cerulean City (1,1) facing left | C L24 38/68 | ¥2543 | 2 badges")
    opts, _ = agent.nav_options(o, ["Vermilion City"], SOLO.Facts(badges=2))
    go = next(x for x in opts if x.label.startswith("explore the frontier: go to "))
    assert go.label.startswith("explore the frontier: go to Cerulean Trashed House"), go.label
    labels = [x.label for x in opts]                   # plain ways back to explored maps would drown it (iteration 33)
    assert "walk to Route 4 (west edge)" not in labels and "walk to Route 24 (north edge)" not in labels
    assert not any(x.startswith("walk to the warp at (3,1)") for x in labels)
    # taking new warps and edges counts as progress: exploring does not escalate the stuck recovery
    d = SOLO.SoloDirector({})
    f = SOLO.Facts(badges=2, explored=5)
    d.track(0, o, f)
    d.track(400, o, SOLO.Facts(badges=2, explored=6))
    assert d.s["recovery"] == 0 and d.s["last_progress_step"] == 400


def test_harness_stops_an_agent_that_keeps_crashing(monkeypatch):
    from bench import run
    r = run.Run.__new__(run.Run)
    r.stop_requested, r.state = False, {"paused_seconds": 0}
    monkeypatch.setattr(r, "stop_reason", lambda: None, raising=False)
    monkeypatch.setattr(r, "log", lambda *a: None, raising=False)
    monkeypatch.setattr(run.time, "sleep", lambda s: None)
    calls = []
    def chunk():                                       # bills-house iteration 31: a traceback after 3 setup calls, every time
        calls.append(1)
        return {"exit_reason": "exited", "exit_code": 1, "seconds": 5.0, "tool_calls_seen": 3}
    monkeypatch.setattr(r, "run_chunk", chunk, raising=False)
    assert r.loop() == "crashed" and len(calls) == 3


def test_a_guard_who_stops_the_walk_every_time_blocks_the_hop(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    gate, r5 = map_id("Route 5 Gate"), map_id("Route 5")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(gate, _view("Route 5 Gate", ["###D###", "#.....#", "#.....#", "###D###"]),
                      _warps_hex([(3, 0, 0, 0xFF), (3, 3, 1, 0xFF)]), [])
    agent.nav.record_warp(gate, 3, 0, r5, 10, 29)
    agent.s["visited"] = ["Route 5", "Route 5 Gate"]
    o = J.parse("walked\nf1 Route 5 Gate (3,1) facing down | C L24 38/68 | ¥2543 | 2 badges")
    opt = J.Option("explore the frontier: walk to the untaken warp at (3,3) → Route 5", "walk", {"path": "to 3,3"})
    stopped = J.parse("went toward (3,3): down 1/2 — stopped: dialogue appeared\n"
                      "f1 Route 5 Gate (3,2) facing down | C L24 38/68 | ¥2543 | 2 badges")
    for _ in range(2):                                 # iteration 34: "Gee, I'm thirsty… the road's closed", every time
        agent.nav_feedback(o, opt, stopped, "")
        agent.s["step"] += 2
    assert f"{gate}:3,3" in agent.s["nav_blocked"]
    opts, _ = agent.nav_options(o, ["Vermilion City"], SOLO.Facts(badges=2))
    assert not any("(3,3)" in x.label and x.label.startswith("explore") for x in opts)


def test_first_visit_records_the_way_back_before_the_map_is_observed(tmp_path):
    from bench.jev_atlas import LearnedAtlas, UNKNOWN
    from bench.jev_nav import map_id
    r4, m1 = map_id("Route 4"), map_id("Mt. Moon 1F")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(r4, _view("Route 4", ["###D###", "#.....#", "#.....#"]), _warps_hex([(3, 0, 0, m1)]), [("east", "Cerulean City")])
    atlas.record_warp(r4, 3, 0, m1, 3, 2)              # walked in; Mt. Moon 1F is observed only on the next step
    atlas.observe(m1, _view("Mt. Moon 1F", ["#######", "#.....#", "#..DD.#"]),
                  _warps_hex([(3, 2, 0, 0xFF), (4, 2, 0, 0xFF)]), [], last_map_text="D365: 0F")
    assert atlas.warp_dest(m1, 0) == [(r4, 3, 0)] and atlas.warp_dest(m1, 1) == [(r4, 3, 0)]   # not (r4, *UNKNOWN)
    assert (r4, *UNKNOWN) not in atlas.warp_dest(m1, 1)
    assert atlas.route(m1, (3, 1), map_id("Cerulean City")) is None   # no optimistic shortcut back out


def test_a_failed_edge_crossing_is_blocked_by_its_cell(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    pallet = map_id("Pallet Town")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(pallet, _view("Pallet Town", ["#######", "#.....#", "#.~~~~#"]), _warps_hex([]), [("south", "Route 21")])
    agent.s["visited"] = ["Pallet Town"]
    o = J.parse("walked\nf1 Pallet Town (1,2) facing down | C L6 20/20 | ¥3000 | 0 badges")
    for _ in range(2):                                 # iteration 36: "walked down 0/1 — stopped: blocked", ~2,800 times
        opts, _ = agent.nav_options(o, ["Pewter City"], SOLO.Facts())
        opt = next(x for x in opts if "south edge" in x.label)
        agent.edge_hop = agent.edge_opts.get(opt.label)
        agent.nav_feedback(o, opt, J.parse("walked down 0/1 — stopped: blocked\n"
                                           "f1 Pallet Town (1,2) facing down | C L6 20/20 | ¥3000 | 0 badges"), "")
        agent.s["step"] += 2
    assert f"{pallet}:1,2" in agent.s["nav_blocked"]
    opts, _ = agent.nav_options(o, ["Pewter City"], SOLO.Facts())
    assert not any("south edge" in x.label for x in opts)


def test_an_edge_cell_that_walks_up_and_bumps_is_dropped(tmp_path):
    """Full run 53: Lavender Town's west edge crosses to Route 8 only on row 8. Each try walked to another edge cell
    and bumped, the position changed, so no cell was ever blocked; the agent went exploring the Pokémon Tower."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    lav = map_id("Lavender Town")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(lav, _view("Lavender Town", ["######", ".....#", ".....#", ".....#", "######"]), _warps_hex([]),
                      [("west", "Route 8")])
    agent.s["visited"] = ["Lavender Town"]
    tried = []
    for k in range(6):
        o = J.parse("walked\nf1 Lavender Town (4,1) facing left | C L40 99/99 | ¥3000 | 3 badges")
        opts, _ = agent.nav_options(o, ["Celadon City"], SOLO.Facts(badges=3))
        opt = next((x for x in opts if "west edge" in x.label), None)
        if opt is None:
            break
        agent.edge_hop = agent.edge_opts.get(opt.label)
        _, ex, ey = agent.edge_hop
        tried.append((ex, ey))
        if (ex, ey) == (0, 3):
            break                                      # the real crossing is offered
        agent.nav_feedback(o, opt, J.parse(f"walked left 0/1 — stopped: blocked\n"
                                           f"f1 Lavender Town ({ex},{ey}) facing left | C L40 99/99 | ¥3000 | 3 badges"), "")
        agent.s["step"] += 400                         # long after any short-term block expired
    assert tried == [(0, 1), (0, 1), (0, 2), (0, 2), (0, 3)]   # twice each (a person may stand across once)
    agent.nav.save()
    again = LearnedAtlas(tmp_path / "x.json", seed=tmp_path / "data" / "jev_atlas.json")
    _, trans = again.reach(lav, (4, 1))
    assert {(h.x, h.y) for _, h, _ in trans if h.kind == "edge"} == {(0, 3)}   # remembered across runs of the atlas


def test_the_tower_top_is_not_explored_without_the_silph_scope(tmp_path):
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    t6 = map_id("Pokémon Tower 6F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(t6, _view("Pokémon Tower 6F", ["#######", "#D...D#", "#######"]),
                      _warps_hex([(1, 1, 0, map_id("Pokémon Tower 5F")), (5, 1, 0, map_id("Pokémon Tower 7F"))]), [])
    agent.s["visited"] = ["Pokémon Tower 6F"]
    o = J.parse("walked\nf1 Pokémon Tower 6F (3,1) facing left | C L48 99/99 | ¥3000 | 4 badges")
    opts, _ = agent.nav_options(o, ["Celadon City"], SOLO.Facts(badges=4))
    assert not any("7F" in x.label for x in opts) and any("5F" in x.label for x in opts)
    agent.s["nav_noroute"][f"{t6}:5,1"] = agent.s["step"]   # a recently refused 7F hop is not "pending" either (Codex)
    opts, _ = agent.nav_options(o, ["Celadon City"], SOLO.Facts(badges=4))
    assert not any("7F" in x.label for x in opts)
    opts, _ = agent.nav_options(o, ["Celadon City"], SOLO.Facts(badges=4, items={"Silph Scope"}))
    assert any("7F" in x.label for x in opts)


def test_talk_option_avoids_cells_other_people_stand_on():
    rows = ["..........", ".~~~..~~~.", ".~......~."]           # Cerulean Gym rows 1-3: Misty at (4,2)
    grid = {(x, y + 1): c for y, r in enumerate(rows) for x, c in enumerate(r)}
    o = J.parse("walked\nf1 Cerulean Gym (7,3) facing left | C L27 70/80 | ¥3000 | 1 badges")
    o.npcs = [(4, 2), (4, 3)]                          # iteration 37: the beaten trainer stood right below Misty
    misty = next(x for x in J.talk_to_options(o, grid) if x.label.endswith("(4,2)"))
    assert misty.args["path"] == "to 5,2" and misty.then[0][1]["path"] == "left 1"


def test_a_walk_that_failed_is_not_what_the_person_said(tmp_path):
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    o = J.parse("walked\nf1 Cerulean Gym (5,3) facing left | C L27 70/80 | ¥3000 | 1 badges")
    opt = J.Option("talk to the person or object at (4,2)", "walk", {"path": "to 4,3"}, then=[("talk", {})])
    agent.s["said"]["Cerulean Gym"] = {}
    said = agent.s["said"]["Cerulean Gym"]
    for head, kept in (("went toward (4,3): left 0/1, left 0/1 — could not get closer", False),
                       ("went toward (4,3): up 1/3 — stopped: dialogue appeared", False),
                       ("no walkable route from (5,3) to (4,3) on this map", False),
                       ("dialogue ended: No more room for items!", False),     # run 59: the Gold Teeth, bag full
                       ("dialogue ended: Hi, you're a new face!", True)):
        said.clear()
        agent.remember_talk(o, opt, J.parse(head + "\nf1 Cerulean Gym (5,3) facing left | C L27 70/80 | ¥3000 | 1 badges"))
        assert ("4,2" in said) is kept, head


def test_a_person_with_no_way_there_is_not_offered_for_a_while(tmp_path):
    """Full run 48: Rocket Hideout B4F's guard stands behind a wall; 'no walkable route' was (rightly) not stored as
    what he said, but he stayed on offer and Jev chose him ~1,000 times over the Rocket with the Lift Key."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    status = "\nf1 Rocket Hideout B4F (20,12) facing down | C L51 160/170 | ¥3000 | 4 badges"
    view = "Rocket Hideout B4F (20,12) facing down, window x16..25 y8..16\n" + "\n".join(
        ["....#....."] * 4 + ["....P#.N.."] + ["....#....."] * 4)
    o = J.parse("walked" + status + "\n" + view)
    o.npcs.append((11, 2))                                          # remembered from the full map view
    o.grid[(11, 3)] = "."
    guard = J.Option("talk to the person or object at (23,12)", "walk", {"path": "to 22,12"}, then=[("talk", {})])
    agent.s["step"] = 100
    labels = lambda: [x.label for x in agent.options(o, [], [], [])]   # noqa: E731
    assert "talk to the person or object at (23,12)" in labels()
    agent.remember_talk(o, guard, J.parse("no walkable route from (20,12) to (22,12) on this map" + status))
    assert "23,12" not in agent.s["said"].get("Rocket Hideout B4F", {})
    assert "talk to the person or object at (23,12)" not in labels()
    assert "talk to the person or object at (11,2)" in labels()
    agent.s["step"] = 100 + AG.NAV_BLOCK_STEPS + 1                  # the door may have opened since
    assert "talk to the person or object at (23,12)" in labels()


def test_a_window_view_keeps_the_people_seen_outside_it(tmp_path):
    """Full run 48: a 10x9 window view replaced B4F's nine remembered people with the one inside it."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    agent.s["npcs"] = {"Rocket Hideout B4F": [[11, 2], [23, 12], [10, 12], [18, 9]]}
    status = "walked\nf1 Rocket Hideout B4F (14,15) facing down | C L51 160/170 | ¥3000 | 4 badges\n"
    o = J.parse(status + "Rocket Hideout B4F (14,15) facing down, window x9..18 y11..19\n"
                + "\n".join([".N........"] + [".........."] * 3 + [".....P...."] + [".........."] * 4))
    assert agent.remember_people(o)
    assert sorted(o.npcs) == [(10, 11), (11, 2), (18, 9), (23, 12)]  # (10,12) was inside the window: gone
    assert sorted(map(tuple, agent.s["npcs"]["Rocket Hideout B4F"])) == sorted(o.npcs)
    bare = J.parse(status)                                           # no map rows at all: the remembered list
    assert agent.remember_people(bare) and sorted(bare.npcs) == sorted(o.npcs)


def test_a_floor_list_offers_each_floor_by_name():
    """The Rocket Hideout Elevator's panel answers with a list; the presses from the cursor are computed in code."""
    o = J.parse("choice:\n    ▶B1F\n     B2F\n     B4F\n     CANCEL\nWhich floor do\nyou want?")
    assert o.mode == "prompt"
    opts = {x.label: x.args["buttons"] for x in J.choice_options(o)}
    assert opts == {"choose B1F": "A", "choose B2F": "DOWN A", "choose B4F": "DOWN DOWN A", "choose CANCEL": "DOWN DOWN DOWN A"}
    up = J.parse("choice:\n     B1F\n     B2F\n    ▶B4F\n     CANCEL\nWhich floor do\nyou want?")
    assert {x.label: x.args["buttons"] for x in J.choice_options(up)}["choose B1F"] == "UP UP A"
    assert J.choice_options(J.parse("said: Hello!\nf1 Pallet Town (5,5) facing up | C L5 20/20 | ¥3000 | 0 badges")) == []


def test_with_the_lift_key_the_objective_is_the_elevator(tmp_path):
    """Full run 49: the Lift Key in hand on B4F's stairs side, the scope objective's last map: nothing to route to.
    With the key the target is the elevator until B4F is chosen on its panel; arriving from it, B4F is the target."""
    d = SOLO.SoloDirector({})
    order = [n.id for n in SOLO.GRAPH]
    f = SOLO.Facts(badges=4, levels=[51], visited={"Celadon City", "Rocket Hideout B4F"},
                   manual_done=set(order[:order.index("scope")]))
    at = lambda m: J.parse(f"walked\nf1 {m} (9,6) facing up | C L51 160/170 | ¥3000 | 4 badges")   # noqa: E731
    b4f = at("Rocket Hideout B4F")
    assert d.objective(f, b4f)[1][-1] == "Rocket Hideout B4F"            # no key yet: the Rocket on B4F drops it
    f.ever_items = {"Lift Key"}
    assert d.objective(f, b4f)[1] == ["Rocket Hideout B4F", "Rocket Hideout Elevator"]
    f.elevator = "B4F"                                                     # chosen on the panel: walk out
    assert d.objective(f, at("Rocket Hideout Elevator"))[1][-1] == "Rocket Hideout B4F"
    f.elevator, f.came_from = "", "Rocket Hideout Elevator"                 # arrived on Giovanni's side
    assert d.objective(f, b4f)[1][-1] == "Rocket Hideout B4F"
    st = {}
    d2 = SOLO.SoloDirector(st)
    for m in ("Rocket Hideout B2F", "Rocket Hideout Elevator"):
        d2.track(1, at(m), f)
    st["elevator"] = "B4F"
    d2.track(2, at("Rocket Hideout B4F"), f)
    assert st["came_from"] == "Rocket Hideout Elevator" and st["elevator"] == ""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    agent.s["prev_map"] = "Rocket Hideout Elevator"
    menu = J.parse("choice:\n    ▶B1F\n     B2F\n     B4F\n     CANCEL\nWhich floor do\nyou want?")
    assert [x.label for x in J.choice_options(menu)] == ["choose B1F", "choose B2F", "choose B4F", "choose CANCEL"]
    stage = ["Rocket Hideout B4F", "Rocket Hideout Elevator"]
    assert [x.label for x in agent.options(menu, [], [], stage) if x.label.startswith("choose")] == ["choose B4F"]
    agent.remember_choice(menu, next(x for x in agent.options(menu, [], [], stage) if x.label == "choose B4F"))
    assert agent.s["elevator"] == "B4F"
    # full run 54: Silph Scope taken, the objective is the Pokémon Tower: the way out of the building is the top entry
    tower = ["Lavender Town", "Pokémon Tower 1F", "Pokémon Tower 7F"]
    assert [x.label for x in agent.options(menu, [], [], tower) if x.label.startswith("choose")] == ["choose B1F"]


def test_the_elevator_panel_is_offered(tmp_path):
    """Full run 52: the Rocket Hideout Elevator's view has side and bottom walls; with them 14 wall cells touched the
    floor, over the cap, and the panel at (1,1) was never offered (~3,000 steps between B2F and the elevator)."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    el = map_id("Rocket Hideout Elevator")
    agent.nav.observe(el, _view("Rocket Hideout Elevator", ["######", "##DD##", "#....#", "#....#", "#....#", "#....#",
                                                            "#....#", "######"]),
                      _warps_hex([(2, 1, 4, 200), (3, 1, 4, 200)]), [])
    o = J.parse("walked\nf1 Rocket Hideout Elevator (2,2) facing up | C L49 160/165 | ¥3000 | 4 badges")
    labels = [x.label for x in agent.object_options(o)]
    assert "examine the object at (1,1) from below" in labels
    assert not any(re.search(r"\((0|5),\d\)|,7\)", x) for x in labels)          # borders are not objects
    first = next(x for x in agent.object_options(o) if x.label == "examine the object at (1,1) from below")
    assert first.args["path"] == "to 1,2" and first.then == [("walk", {"path": "up 1", "on_battle": "stop"}), ("talk", {})]
    # full run 54: whatever the objective, a floor must be chosen first; the doors only lead back where it came from
    door = J.Option("walk to the warp at (2,1) → Rocket Hideout B4F", "walk", {"path": "to 2,1"})
    labels = [x.label for x in agent.panel_first(o, [door, J.Option("save the game", "manage", {"action": "save"})])]
    assert labels[0] == "examine the object at (1,1) from below" and door.label not in labels and "save the game" in labels


def test_a_black_out_is_seen_without_the_words(tmp_path):
    """Full run 50: the last turns of a loss to Misty were plain 'pressed A' replies; the black-out went unnoticed, so
    Misty stayed 'already talked to' (Jev 0.02) and no training bonus followed. Out of a battle onto another map with
    the money halved is a black-out too."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    gym = J.parse("walked\nf1 Cerulean Gym (4,3) facing up | C L33 90/90 | ¥3000 | 1 badges")
    fight = J.parse("pressed A\nbattle: trainer | enemy STARYU L18 40/40 | you CHARMELEON L33 10/90 | menu: text")
    assert fight.mode != "overworld"
    assert not agent.blacked_out(gym, fight, "dialogue ended: Hi, you're a new face!")
    won = J.parse("pressed A\nf1 Cerulean Gym (4,3) facing up | C L33 50/90 | ¥4980 | 2 badges")
    assert not agent.blacked_out(fight, won, "pressed A")                 # same map, more money: a win
    town = J.parse("pressed A\nf1 Cerulean City (19,18) facing down | C L33 90/90 | ¥2490 | 2 badges")
    assert not agent.blacked_out(won, town, "walked down 1/1 — entered Cerulean City")   # a walk, not a battle
    agent.blacked_out(town, gym, "went toward (30,19) — entered Cerulean Gym")
    lost = J.parse("pressed A\nf1 Cerulean City (19,18) facing down | C L33 90/90 | ¥1500 | 1 badges")
    assert agent.blacked_out(fight, lost, "pressed A")
    assert agent.blacked_out(fight, lost, "AAAAAAA blacked out!")


def test_node_targets_reach_the_room_that_matters():
    from games import gen1_data as D
    nodes = {n.id: n for n in SOLO.GRAPH} if hasattr(SOLO, "GRAPH") else None
    nodes = nodes or {n.id: n for v in vars(SOLO).values() if isinstance(v, list) and v and isinstance(v[0], SOLO.Node) for n in v}
    names = set(D.MAPS.values())
    assert all(t in names for n in nodes.values() for t in n.targets)
    # iteration 39: the targets ended at S.S. Anne 2F, so the map route took Jev out of the captain's room each time
    assert nodes["cut"].targets[-1] == "S.S. Anne Captain's Room"
    assert nodes["scope"].targets[-1] == "Rocket Hideout B4F" and nodes["silph"].targets[-1] == "Silph Co. 11F"
    assert nodes["champion"].targets[-1] == "Champion's Room" and "tea" not in nodes   # Red/Blue: any drink, no Tea
    d = SOLO.SoloDirector({"visited": ["Lavender Town"], "milestones": []})
    f = SOLO.Facts(badges=4, levels=[60], visited={"Lavender Town"}, ever_items={"Silph Scope"})
    tower = J.parse("walked\nf1 Pokémon Tower 7F (10,4) facing up | C L60 100/100 | ¥3000 | 4 badges")
    home = J.parse("walked\nf1 Mr. Fuji's House (3,5) facing up | C L60 100/100 | ¥3000 | 4 badges")
    order = list(nodes)
    f.manual_done = set(order[:order.index("flute")])
    assert SOLO.current_node(f).id == "flute"
    assert d.objective(f, tower)[1][-1] == "Pokémon Tower 7F"
    # full run 74: walking into the empty house before the rescue is not the stage (its people's answers then hid him)
    assert d.objective(f, home)[1][-1] == "Pokémon Tower 7F"
    # full run 57: out of the house again, the objective sent Jev back up the Tower for ~6,500 steps
    lavender = J.parse("walked\nf1 Lavender Town (7,10) facing down | C L60 100/100 | ¥3000 | 4 badges")
    d.s["prev_map"] = "Pokémon Tower 7F"
    d.s["said"] = {"Mr. Fuji's House": {"3,3": "dialogue ended: POKéMON Monthly Grand Prize"}}
    d.track(1, home, f)                                            # arrived from 7F: the rescue warp
    assert "Mr. Fuji's House" not in d.s["said"]                   # he sits at the table now: heard anew
    assert d.objective(d.facts(home, [], [("Silph Scope", 1)]), home)[1][-1] == "Mr. Fuji's House"
    d.track(2, lavender, f)
    f2 = d.facts(lavender, [], [("Silph Scope", 1)])
    f2.manual_done = f.manual_done
    assert d.objective(f2, lavender)[1][-1] == "Mr. Fuji's House"
    d2 = SOLO.SoloDirector({"visited": ["Lavender Town", "Mr. Fuji's House"], "milestones": []})
    d2.s["prev_map"] = "Lavender Town"
    d2.track(1, home, f)                                            # walking in from town before the rescue: no event
    f3 = d2.facts(lavender, [], [("Silph Scope", 1)])
    f3.manual_done = f.manual_done
    assert d2.objective(f3, tower)[1][-1] == "Pokémon Tower 7F"


@requires_rom
def test_silph_11f_is_entered_only_from_the_7f_warp_pad(nav):
    """Full run 61: Silph Co.'s stairs reach 11F's corridor, walled off from Giovanni's room; Jev paced it ~2,800
    steps. With the entry rule the route goes through the warp pads (3F -> 7F -> 11F), also from that corridor."""
    rule = {nav_id("Silph Co. 11F"): nav_id("Silph Co. 7F")}
    plain = _route(nav, "Silph Co. 10F", (10, 1), "Silph Co. 11F")
    assert plain == [("warp", 10, 0, "Silph Co. 11F")]
    ruled = _route(nav, "Silph Co. 10F", (10, 1), "Silph Co. 11F", entry=rule)
    assert ruled[-2:] == [("warp", 11, 11, "Silph Co. 7F"), ("warp", 5, 7, "Silph Co. 11F")], ruled
    assert _route(nav, "Silph Co. 11F", (9, 1), "Silph Co. 11F") == []
    assert _route(nav, "Silph Co. 11F", (9, 1), "Silph Co. 11F", entry=rule)[-1] == ("warp", 5, 7, "Silph Co. 11F")



def test_silph_card_key_first_then_doors_and_the_pad_route(tmp_path):
    d = SOLO.SoloDirector({"visited": [], "milestones": []})
    order = [n.id for n in SOLO.GRAPH]
    f = SOLO.Facts(badges=5, levels=[60], visited={"Saffron City"}, manual_done=set(order[:order.index("silph")]))
    o = J.parse("walked\nf1 Silph Co. 1F (10,17) facing up | C L60 200/207 | ¥3000 | 5 badges")
    text, targets, why = d.objective(f, o)
    assert why == "silph" and targets[-1] == "Silph Co. 5F" and d.entry_rule(f) == {}   # no Card Key: 5F
    f.ever_items = {"Card Key"}
    assert d.objective(f, o)[1][-1] == "Silph Co. 11F" and d.entry_rule(f) == {"Silph Co. 11F": "Silph Co. 7F"}
    # the doors: L cells in the map view, offered only with the Card Key, left alone after a try that failed
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    rows = ["#######", "#.....#", "###LL##", "#.....#", "#######"]
    agent.s["grids"]["Silph Co. 10F"] = {f"{x},{y}": c for y, r in enumerate(rows) for x, c in enumerate(r)}
    here = J.parse("walked\nf1 Silph Co. 10F (1,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    agent.items = [("Potion", 1)]
    assert agent.card_door_options(here) == []
    agent.items = [("Card Key", 1)]
    door, = agent.card_door_options(here)
    assert door.label == "open the locked door at (3,2) with the Card Key", door
    assert door.args["path"] == "to 3,1" and door.then == [("walk", {"path": "down 1", "on_battle": "stop"}), ("talk", {})]
    agent.remember_door(here, door, "dialogue ended: Bingo! The CARD KEY | The CARD KEY opened the door!")
    assert agent.card_door_options(here)                                   # (opened: the next view has no L)
    agent.remember_door(here, door, "walked down 0/1 — stopped: blocked")
    assert agent.card_door_options(here) == []
    # the elevator panel does not pick 11F: it opens onto the corridor
    agent.s["entry_rule"] = d.entry_rule(f)
    panel = J.parse("choice:\n    ▶1F\n     5F\n     10F\n     11F\n     CANCEL\nWhich floor do\nyou want?")
    agent.s["prev_map"] = "Silph Co. Elevator"
    assert [x.label for x in agent.floor_choice(panel, J.choice_options(panel), d.objective(f, o)[1])] == ["choose 10F"]


def test_locked_doors_and_item_balls_keep_every_map_row(tmp_path):
    """3d45c25 drew Silph's card-key doors 'L', but the map-row patterns did not know the letter: the learned atlas
    stopped at the first row with a door (Silph Co. 5F kept rows 0-3) and the agent's grid lost those rows (full run
    62). Item balls are drawn 'o': a talk target like a person, offered first and named as an item."""
    from bench.jev_atlas import parse_view
    rows = ["#########", "#P..N..o#", "#..L....#", "#..L..o.#", "#########"]
    assert len(parse_view(_view("Silph Co. 5F", rows))) == 5
    assert parse_view(_view("Silph Co. 5F", rows))[2][3] == "L" and parse_view(_view("Silph Co. 5F", rows))[1][7] == "."
    o = J.parse("walked up 1/1\nf1 Silph Co. 5F (1,1) facing up | X L5 20/20 | ¥0 | 5 badges\n"
                + _view("Silph Co. 5F", rows))
    assert (3, 3) in o.grid and o.grid[(3, 3)] == "L"
    assert set(o.balls) == {(7, 1), (6, 3)} and {(4, 1), (7, 1), (6, 3)} <= set(o.npcs)
    opts = J.talk_to_options(o, o.grid)
    assert opts[0].label == "talk to the person or object at (7,1) (an item ball: pick it up)" and "(6,3) (an item" in opts[1].label
    assert "not taken yet" in opts[0].desc and opts[2].label == "talk to the person or object at (4,1)"
    win = ("walked up 1/1\nf1 Silph Co. 5F (5,5) facing up | X L5 20/20 | ¥0 | 5 badges\n"
           "Silph Co. 5F (5,5) facing up, window x1..10 y1..9\n" + "\n".join(["..L.o.N...", "#" * 10] + ["." * 10] * 7))
    o = J.parse(win)
    assert o.balls == [(5, 1)] and (7, 1) in o.npcs and o.grid[(3, 1)] == "L"


def test_an_item_ball_out_of_reach_is_sought_from_another_arrival(tmp_path, nav):
    """Full run 63's map: Silph Co. 5F's Card Key lies in a corridor whose two ends are held by beaten Rockets who never
    move; the server finds no way. The ball becomes a spot goal: the route looks for an arrival on 5F from which it can
    be reached with people as walls (9F's warp pad), and once the player stands there the ball is offered again."""
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    agent.nav = nav
    f5, f9 = map_id("Silph Co. 5F"), map_id("Silph Co. 9F")
    o = J.parse("walked\nf1 Silph Co. 5F (27,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    o.npcs, o.balls = [(28, 4), (8, 16), (21, 16)], [(21, 16)]
    agent.s["step"] = 10
    talk = J.Option("talk to the person or object at (21,16) (an item ball: pick it up)", "walk", {"path": "to 20,16"})
    agent.remember_talk(o, talk, J.parse("no walkable route from (27,1) to (20,16) on this map"))
    assert agent.s["spot_goal"] == ["Silph Co. 5F", 21, 16, 10, "ball"]
    cells = agent.spot_cells(o, f5, f5)
    assert (21, 16) in cells and (9, 16) in cells and (27, 1) not in cells and (28, 5) in cells
    hops = agent.nav.route(f5, (27, 1), f5, goal_cells=cells)
    assert hops and hops[-1].dest == f5 and any(h.dest == f9 for h in hops), hops
    assert agent.nav.route(f5, (27, 1), f5) == []                         # without it: "already there"
    there = dataclasses.replace(o, pos=(9, 16))
    assert agent.spot_cells(there, f5, f5) is None and "21,16" not in agent.s["talk_noroute"]["Silph Co. 5F"]
    gone = dataclasses.replace(o, balls=[], grid={(21, 16): ".", (20, 16): "."})   # a view of its cell without it
    assert agent.spot_cells(gone, f5, f5) is None and "spot_goal" not in agent.s


def test_a_gym_leader_behind_warp_pads_is_sought_through_them(tmp_path, nav):
    """Full run 73: Sabrina's room in the Saffron Gym is joined to the others only by warp pads; the walk to her never
    crosses a warp ("no walkable route"), and ~4,500 steps went on the same pads. An unreachable person in a gym becomes
    a spot goal like an item ball: the route crosses the pads (their landings are in the map's own warp list)."""
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    agent.nav = nav
    gym = map_id("Saffron Gym")
    o = J.parse("walked\nf1 Saffron Gym (9,16) facing up | C L50 200/207 | ¥3000 | 5 badges")
    o.npcs = [(9, 8), (10, 15)]
    agent.s["step"] = 10
    talk = J.Option("talk to the person or object at (9,8)", "walk", {"path": "to 9,9"})
    agent.remember_talk(o, talk, J.parse("no walkable route from (9,16) to (9,9) on this map"))
    assert agent.s["spot_goal"] == ["Saffron Gym", 9, 8, 10, "person"]
    cells = agent.spot_cells(o, gym, gym)
    assert (9, 9) in cells and (9, 16) not in cells
    hops = agent.nav.route(gym, (9, 16), gym, goal_cells=cells)
    assert hops and all(h.kind == "warp" and h.dest == gym for h in hops), hops
    gone = dataclasses.replace(o, npcs=[(10, 15)], grid={(9, 8): "."})      # nobody on her cell any more
    assert agent.spot_cells(gone, gym, gym) is None and "spot_goal" not in agent.s



def test_a_warp_pad_on_the_same_map_is_recorded_as_taken(tmp_path):
    """Full run 75: walking onto a Saffron Gym pad ends "could not get closer" on another pad of the same map; only a
    map change recorded a warp, so the pads stayed frontier and the Cinnabar objective came back to them (~1,400 steps)."""
    from bench.jev_atlas import LearnedAtlas, frontier_maps
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    gym = map_id("Saffron Gym")
    agent.nav = atlas = LearnedAtlas(tmp_path / "atlas.json")
    atlas.observe(gym, _view("Saffron Gym", ["#######", "#.D#D.#", "#######"]), _warps_hex([(2, 1, 1, gym), (4, 1, 0, gym)]), [])
    assert gym in frontier_maps(atlas, {"Saffron Gym"})
    o = J.parse("walked\nf1 Saffron Gym (1,1) facing up | C L50 200/207 | ¥3000 | 6 badges")
    opt = J.Option("explore the frontier: walk to the untaken warp at (2,1) → Saffron Gym", "walk", {"path": "to 2,1"})
    after = J.parse("went toward (2,1): right 1/1 — could not get closer\nf1 Saffron Gym (4,1) facing right | C L50 200/207 | ¥3000 | 6 badges")
    agent.nav_feedback(o, opt, after, "")
    assert atlas.data["maps"][str(gym)]["arrivals"]["2,1"] == {"map": gym, "x": 4, "y": 1, "seen": True}
    assert [(h.x, h.y) for h in atlas.frontier(gym, (1, 1), {"Saffron Gym"})] == []
    stuck = J.parse("went toward (2,1): right 0/1 — could not get closer\nf1 Saffron Gym (1,1) facing right | C L50 200/207 | ¥3000 | 6 badges")
    agent.nav_feedback(o, J.Option("walk to the warp at (4,1) → Saffron Gym", "walk", {"path": "to 4,1"}), stuck, "")
    assert "4,1" not in atlas.data["maps"][str(gym)]["arrivals"] or not atlas.data["maps"][str(gym)]["arrivals"]["4,1"]["seen"]
    # Codex review 2: standing on one pad, a refused walk to another leaves the player where they were (on a pad)
    on_pad = J.parse("walked\nf1 Saffron Gym (4,1) facing up | C L50 200/207 | ¥3000 | 6 badges")
    for reply in ("no walkable route from (4,1) to (2,1) on this map",
                  "went toward (2,1): left 0/1 — could not get closer\nf1 Saffron Gym (4,1) facing left | C L50 200/207 | ¥3000 | 6 badges"):
        atlas.data["maps"][str(gym)]["arrivals"].pop("2,1", None)
        agent.nav_feedback(on_pad, J.Option("walk to the warp at (2,1) → Saffron Gym", "walk", {"path": "to 2,1"}),
                           J.parse(reply), "")
        assert not atlas.data["maps"][str(gym)]["arrivals"].get("2,1", {}).get("seen"), reply

def test_a_status_only_reply_keeps_the_item_balls_and_the_spot_goal(tmp_path, nav):
    """The refusal that makes the Card Key a spot goal carries no map rows, and the next reply may show only the status
    line: no balls in it is not a taken ball (the goal was dropped right away). Balls are remembered per map like
    people; only a view that shows the ball's cell without it ends the goal."""
    from bench.jev_nav import map_id
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    agent.nav = nav
    f5 = map_id("Silph Co. 5F")
    seen = J.parse("walked\nf1 Silph Co. 5F (27,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    seen.npcs, seen.balls, seen.grid = [(28, 4), (8, 16), (21, 16)], [(21, 16)], {(21, 16): ".", (27, 1): "."}
    agent.remember_people(seen)
    agent.remember_balls(seen)
    agent.s["step"] = 10
    talk = J.Option("talk to the person or object at (21,16) (an item ball: pick it up)", "walk", {"path": "to 20,16"})
    refusal = J.parse("no walkable route from (27,1) to (20,16) on this map")
    agent.remember_talk(seen, talk, refusal)
    status = J.parse("walked\nf1 Silph Co. 5F (27,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    agent.remember_people(status)                              # as step() does: the people and the balls seen last
    agent.remember_balls(status)
    assert status.balls == [(21, 16)]
    assert agent.spot_cells(status, f5, f5) and agent.s["spot_goal"][:3] == ["Silph Co. 5F", 21, 16]
    window = J.parse("walked\nf1 Silph Co. 5F (27,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    window.grid = {(27, 1): ".", (26, 1): "."}                 # a view that does not cover the ball: still there
    agent.remember_balls(window)
    assert window.balls == [(21, 16)]
    taken = J.parse("walked\nf1 Silph Co. 5F (27,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    taken.grid = {(21, 16): ".", (27, 1): "."}
    agent.remember_balls(taken)
    assert taken.balls == [] and agent.spot_cells(taken, f5, f5) is None and "spot_goal" not in agent.s


def test_a_warp_the_walk_could_not_get_closer_to_leaves_the_frontier(tmp_path):
    """Silph Co. 1F lists a warp at (16,10) to 3F that the player walks over without warping; full run 64 explored
    towards it ~1,800 steps ("could not get closer", the player a step away each time, so nothing was blocked)."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    f1 = map_id("Silph Co. 1F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(f1, _view("Silph Co. 1F", ["#######", "#P....#", "#..D..#", "#.....#", "#######"]),
                      _warps_hex([(3, 2, 6, map_id("Silph Co. 3F"))]), [])
    o = J.parse("walked\nf1 Silph Co. 1F (1,1) facing up | C L60 200/207 | ¥3000 | 5 badges")
    assert [(h.x, h.y) for h in agent.nav.frontier(f1, (1, 1), set())] == [(3, 2)]
    opt = J.Option("explore the frontier: walk to the untaken warp at (3,2) → Silph Co. 3F", "walk", {"path": "to 3,2"})
    after = J.parse("went toward (3,2): right 2/2, down 2/2 — could not get closer\n"
                    "f1 Silph Co. 1F (3,3) facing down | C L60 200/207 | ¥3000 | 5 badges")
    agent.nav_feedback(o, opt, after, "")
    agent.learn_noroute(after)
    assert agent.nav.frontier(f1, (3, 3), set()) == [] and agent.nav.frontier(f1, (1, 1), set()) == []


def test_a_person_in_the_way_of_a_warp_walk_does_not_block_the_warp(tmp_path):
    """"could not get closer" because someone stood in the corridor is not a wall: nothing is learned while the view
    shows a person on the way, and the warp stays on the frontier; with nobody there it is learned as unreachable."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    f1 = map_id("Silph Co. 1F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(f1, _view("Silph Co. 1F", ["#######", "#P...D#", "#######"]),
                      _warps_hex([(5, 1, 6, map_id("Silph Co. 3F"))]), [])
    o = J.parse("walked\nf1 Silph Co. 1F (1,1) facing right | C L60 200/207 | ¥3000 | 5 badges")
    opt = J.Option("explore the frontier: walk to the untaken warp at (5,1) → Silph Co. 3F", "walk", {"path": "to 5,1"})
    after = J.parse("went toward (5,1): right 3/4 — could not get closer\n"
                    "f1 Silph Co. 1F (4,1) facing right | C L60 200/207 | ¥3000 | 5 badges")
    agent.nav_feedback(o, opt, after, "")
    after.npcs = [(5, 1)]                                   # a Rocket standing on the stairs
    agent.learn_noroute(after)
    assert [(h.x, h.y) for h in agent.nav.frontier(f1, (4, 1), set())] == [(5, 1)]
    assert [(h.x, h.y) for h in agent.nav.frontier(f1, (1, 1), set())] == [(5, 1)]
    agent.nav_feedback(o, opt, after, "")
    after.npcs = []                                         # gone, and the walk still stops short: a wall
    agent.learn_noroute(after)
    assert agent.nav.frontier(f1, (4, 1), set()) == [] and agent.nav.frontier(f1, (1, 1), set()) == []


def test_an_opened_card_key_door_is_read_again_and_routed_through(tmp_path):
    """Opening a Card Key door changes the floor without a map change: the atlas kept the L as a wall (and the refusal
    learned while it was shut) until the player left and came back. After "CARD KEY opened" the map is read again
    on the next step and the refusals on that floor are forgotten."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    f8, f9 = map_id("Silph Co. 8F"), map_id("Silph Co. 9F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    warps = _warps_hex([(5, 1, 0, f9)])
    agent.nav.observe(f8, _view("Silph Co. 8F", ["#######", "#P.L.D#", "#######"]), warps, [])
    agent.nav.record_warp(f8, 5, 1, f9, 1, 1)
    agent.nav.observe(f9, _view("Silph Co. 9F", ["####", "#P.#", "####"]), _warps_hex([]), [])
    o = J.parse("walked\nf1 Silph Co. 8F (2,1) facing right | C L60 200/207 | ¥3000 | 5 badges")
    agent.s["atlas_map"] = "Silph Co. 8F"
    agent.nav.record_noroute(f8, (2, 1), (5, 1))
    agent.s["nav_noroute"][f"{f8}:5,1"] = agent.s["step"]
    assert agent.nav.route(f8, (2, 1), f9) is None and not agent.atlas_due(o)
    door = J.Option("open the locked door at (3,1) with the Card Key", "walk", {"path": "right 1"})
    agent.remember_door(o, door, "Bingo! The CARD KEY opened the door!")
    assert agent.atlas_due(o) and f"{f8}:5,1" not in agent.s["nav_noroute"]
    agent.nav.observe(f8, _view("Silph Co. 8F", ["#######", "#P...D#", "#######"]), warps, [])   # what step() reads
    hops = agent.nav.route(f8, (2, 1), f9)
    assert hops and hops[-1].dest == f9


def test_a_guarded_poster_is_examined_from_where_the_guard_stood(tmp_path):
    """The Game Corner's stairs stay shut until the switch behind the poster is pressed. Full run 64 found it only by a
    lucky talk from the guard's spot; run 65 never did and, once the stairs were learned as unreachable, never came
    back. The guard's words name the poster: the walls beside his spot are offered, and the switch re-reads the floor
    and forgets its refusals."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    gc, b1 = map_id("Game Corner"), map_id("Rocket Hideout B1F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    rows = ["####################", "#################.##", "########............", "............########"]
    agent.nav.observe(gc, _view("Game Corner", rows), _warps_hex([(17, 1, 0, b1)]), [])
    o = J.parse("walked\nf1 Game Corner (12,2) facing left | C L40 120/130 | ¥3000 | 4 badges")
    assert agent.clue_options(o) == []
    talk = J.Option("talk to the person or object at (9,2)", "walk", {"path": "to 10,2"})
    agent.remember_talk(o, talk, J.parse("dialogue ended: I'm guarding this poster! | Go away, or else!\n"
                                         "f1 Game Corner (10,2) facing left | C L40 120/130 | ¥3000 | 4 badges"))
    agent.nav.record_noroute(gc, (12, 2), (17, 1))
    opts = agent.clue_options(o)
    assert [x.label.split(" (beside")[0] for x in opts] == ["examine the object at (9,1) from below"]
    assert opts[0].args["path"] == "to 9,2" and opts[0].then == [("walk", {"path": "up 1", "on_battle": "stop"}), ("talk", {})]
    at = J.parse("walked\nf1 Game Corner (9,2) facing up | C L40 120/130 | ¥3000 | 4 badges")
    assert agent.clue_options(at)[0].args == {"path": "up 1", "on_battle": "stop"} and agent.clue_options(at)[0].then == [("talk", {})]
    agent.remember_door(at, opts[0], "dialogue ended: Hey! | A switch behind the poster!?")
    assert "clues" in agent.s and agent.clue_options(at) == [] and agent.atlas_due(at) and not agent.nav.unreachable(gc, (12, 2), (17, 1))


def test_a_walk_that_ends_far_from_a_warp_or_slides_does_not_learn_it_unreachable(tmp_path):
    """Full run 66: across the Rocket Hideout's spinners "could not get closer" ended far from the stairs (or after a
    slide); those stairs were learned as unreachable and the frontier left the hideout for Celadon. Only a walk that
    stopped right next to the warp (Silph Co. 1F's dead warp) counts."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    b2 = map_id("Rocket Hideout B2F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(b2, _view("Rocket Hideout B2F", ["########", "#P.....#", "#......#", "#.....D#", "########"]),
                      _warps_hex([(6, 3, 0, map_id("Rocket Hideout B3F"))]), [])
    o = J.parse("walked\nf1 Rocket Hideout B2F (1,1) facing up | C L40 120/130 | ¥3000 | 4 badges")
    opt = J.Option("explore the frontier: walk to the untaken warp at (6,3) → Rocket Hideout B3F", "walk", {"path": "to 6,3"})
    for head in ("went toward (6,3): right 2/2 — could not get closer\nf1 Rocket Hideout B2F (3,1) facing right | C L40 120/130 | ¥3000 | 4 badges",
                 "went toward (6,3): right 4/5, slid to (5,3) — could not get closer\nf1 Rocket Hideout B2F (5,3) facing right | C L40 120/130 | ¥3000 | 4 badges"):
        after = J.parse(head)
        agent.nav_feedback(o, opt, after, "")
        agent.learn_noroute(after)
        assert [(h.x, h.y) for h in agent.nav.frontier(b2, (1, 1), set())] == [(6, 3)], head


def test_a_warp_that_did_not_open_puts_the_people_on_its_map_first(tmp_path):
    """Full run 67 reached the Game Corner's shut stairs before talking to the poster guard, learned them as
    unreachable, left and never came back. A warp the map shows a way to that does not open means something on this
    map opens it: the people not talked to yet come first (and leaving waits) for a while."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    gc, b1 = map_id("Game Corner"), map_id("Rocket Hideout B1F")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    rows = ["####################", "#################.##", "########............", "............########"]
    agent.nav.observe(gc, _view("Game Corner", rows), _warps_hex([(17, 1, 0, b1)]), [])
    o = J.parse("walked\nf1 Game Corner (12,3) facing up | C L40 120/130 | ¥3000 | 4 badges")
    guard = J.Option("talk to the person or object at (9,2)", "walk", {"path": "to 10,2"})
    gambler = J.Option("talk to the person or object at (3,3)", "walk", {"path": "to 4,3"})
    leave = J.Option("explore the frontier: go to Celadon City (unexplored exits): walk to the warp at (0,3) → Celadon City",
                     "walk", {"path": "to 0,3"})
    agent.s["said"]["Game Corner"] = {"3,3": "dialogue ended: Games are scary!"}
    assert agent.sealed_talks(o, [guard, gambler, leave]) == []
    stairs = J.Option("explore the frontier: walk to the untaken warp at (17,1) → Rocket Hideout B1F", "walk", {"path": "to 17,1"})
    agent.nav_feedback(o, stairs, J.parse("went toward (17,1): right 5/5, up 0/1 — could not get closer\n"
                                          "f1 Game Corner (17,2) facing up | C L40 120/130 | ¥3000 | 4 badges"), "")
    assert agent.sealed_talks(o, [guard, gambler, leave]) == [guard]
    pads = J.Option("follow the map route to Game Corner: walk to the warp at (5,1) → Game Corner", "walk", {"path": "to 5,1"})
    agent.entry_pending = False
    assert agent.sealed_first(o, [guard, gambler, leave, pads], "scope") == [guard, gambler]
    agent.entry_pending = True             # a spot goal across this map's own pads (Saffron Gym): its route stays
    assert agent.sealed_first(o, [guard, gambler, leave, pads], "scope") == [guard, gambler, pads]
    assert agent.sealed_first(o, [guard, gambler, leave], "heal") == [guard, gambler, leave]   # healing comes first
    agent.s["step"] += 601
    assert agent.sealed_talks(o, [guard, gambler, leave]) == []


def test_the_arrival_step_reads_the_map_it_came_from(tmp_path):
    """Full run 68: the facts were read before the step's map change, so on arriving on B4F from the elevator they
    said "came from B4F", the elevator stage routed straight back in (~1,400 steps in and out of the elevator)."""
    d = SOLO.SoloDirector({})
    order = [n.id for n in SOLO.GRAPH]
    at = lambda m: J.parse(f"walked\nf1 {m} (24,15) facing down | C L51 160/170 | ¥3000 | 4 badges")   # noqa: E731
    fact = lambda: SOLO.Facts(badges=4, levels=[51], visited={"Celadon City", "Rocket Hideout B4F"},   # noqa: E731
                              ever_items={"Lift Key"}, manual_done=set(order[:order.index("scope")]),
                              came_from=d.s.get("came_from", ""), elevator=d.s.get("elevator", ""))
    for m in ("Rocket Hideout B4F", "Rocket Hideout Elevator"):
        d.track(1, at(m), fact())
    d.s["elevator"] = "B4F"
    b4f = at("Rocket Hideout B4F")
    f = fact()                                                             # read before the step's map change
    assert f.came_from == "Rocket Hideout B4F"
    d.track(2, b4f, f)
    assert f.came_from == "Rocket Hideout Elevator" and f.elevator == ""
    assert d.objective(f, b4f)[1][-1] == "Rocket Hideout B4F"           # Giovanni's side: not back to the elevator


def test_an_item_ball_on_the_objectives_map_comes_before_leaving_it(tmp_path):
    """Full run 68 beat Giovanni next to the Silph Scope's ball and chose 'walk to Rocket Hideout Elevator' (0.40 over
    the ball's 0.05): an untaken ball on the objective's own map keeps every way out off the list, by name too."""
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()))
    o = J.parse("walked\nf1 Rocket Hideout B4F (26,3) facing left | C L51 160/170 | ¥3000 | 4 badges")
    ball = J.Option("talk to the person or object at (25,2) (an item ball: pick it up)", "walk", {"path": "to 25,3"},
                    "1 tiles away; an item lying here, not taken yet")
    giovanni = J.Option("talk to the person or object at (25,3)", "walk", {"path": "left 1"},
                        "1 tiles away; already talked to it, it said: I see that you raise")
    by_name = J.Option("walk to Rocket Hideout Elevator", "walk", {"path": "to Rocket Hideout Elevator"})
    warp = J.Option("walk to the warp at (24,15) → Rocket Hideout Elevator", "walk", {"path": "to 24,15"})
    up = J.Option("walk up 4 tiles", "walk", {"path": "up 4"})
    # (blind walks too: full run 74 paced Pokémon Tower 7F ~490 steps with the Rockets and Mr. Fuji offered)
    assert agent.objective_map_options(o, [ball, giovanni, by_name, warp, up]) == [ball, giovanni]
    taken = J.Option(ball.label, "walk", ball.args, "1 tiles away; already talked to it, it said: nothing to talk to")
    assert by_name in agent.objective_map_options(o, [taken, giovanni, by_name, warp, up])


def test_an_unknown_last_map_routes_to_the_furthest_known_map_of_the_objective(tmp_path):
    """Full run 68 blacked out in the Pokémon Tower, woke in Celadon and explored Celadon's and Route 16's exits for
    ~8,500 steps: 7F was not in the atlas, but the way to the objective's known maps was. The route goes to the
    furthest of them past this map, and explores from there."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    city, r7, mart = map_id("Celadon City"), map_id("Route 7"), map_id("Celadon Mart 1F")
    atlas = LearnedAtlas(tmp_path / "a.json")
    atlas.observe(city, _view("Celadon City", ["###D###", "#......", "#######"]), _warps_hex([(3, 0, 0, mart)]),
                  [("east", "Route 7")])
    gate = map_id("Underground Path (Route 7)")
    atlas.observe(r7, _view("Route 7", ["#######", "......#", "####D##"]), _warps_hex([(4, 2, 0, gate)]),
                  [("west", "Celadon City")])
    atlas.record_edge(city, "east", 6, 1, r7, 0, 1)
    atlas.record_edge(r7, "west", 0, 1, city, 6, 1)
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()), nav=atlas)
    agent.s["visited"] = ["Celadon City", "Route 7"]
    o = J.parse("walked\nf1 Celadon City (2,1) facing down | C L40 120/130 | ¥3000 | 4 badges")
    targets = ["Lavender Town", "Route 7", "Pokémon Tower 7F"]
    opts, key = agent.nav_options(o, targets, SOLO.Facts(badges=4), "flute")
    assert opts[0].label == "follow the map route to Route 7: walk to Route 7 (east edge)" and key
    assert not any(x.label.startswith("explore the frontier") for x in opts)
    assert agent.s["node_mark"]["flute"] == 2
    # full run 70: from a map first reached during this objective (Route 14), exploring is the way on, not back
    agent.s["node_mark"]["flute"] = 0
    opts, key = agent.nav_options(o, targets, SOLO.Facts(badges=4), "flute")
    assert not key and opts[0].label.startswith("explore the frontier"), opts[0].label
    # full run 71: a map new to the objective that the objective names (Saffron City after a black-out) still routes on
    named = ["Celadon City", "Route 7", "Pokémon Tower 7F"]
    opts, key = agent.nav_options(o, named, SOLO.Facts(badges=4), "flute")
    assert opts[0].label == "follow the map route to Route 7: walk to Route 7 (east edge)" and key
    agent.s["node_mark"]["flute"] = 2
    # on the furthest known map itself: nothing known lies past it, so explore
    o = J.parse("walked\nf1 Route 7 (2,1) facing down | C L40 120/130 | ¥3000 | 4 badges")
    opts, key = agent.nav_options(o, targets, SOLO.Facts(badges=4), "flute")
    assert not key and not any(x.label.startswith("follow the map route") for x in opts)
    # full run 69: a known map of the objective with nothing left to explore from the arrival (Route 2's south part)
    # is not a goal: its frontier sends the player back, and this rule would send them there again
    atlas.record_warp(r7, 4, 2, gate, 3, 7)                                # its one warp taken
    agent.s["visited"].append("Underground Path (Route 7)")
    o = J.parse("walked\nf1 Celadon City (2,1) facing down | C L40 120/130 | ¥3000 | 4 badges")
    opts, key = agent.nav_options(o, targets, SOLO.Facts(badges=4), "flute")
    assert not key and opts[0].label.startswith("explore the frontier: walk to the untaken warp at (3,0)"), opts[0].label


def test_waking_snorlax_forgets_the_refusals_on_its_route(tmp_path):
    """Full run 70: Route 12's atlas kept the 'no walkable route' records learned while Snorlax slept across it; after
    the flute (and a trip to heal) the route to Route 13 took a detour that ends at Saffron's guarded gates, and the run
    never came back to Route 14's tree (~3,500 steps). Playing the flute changes the map like a switch or a door."""
    from bench.jev_atlas import LearnedAtlas
    from bench.jev_nav import map_id
    r12 = map_id("Route 12")
    (tmp_path / "data").mkdir()
    agent = Agent(_agent_args(tmp_path, "solo"), FakeServer(), J.JevPolicy(J.MockJev()),
                  nav=LearnedAtlas(tmp_path / "data" / "jev_atlas.json"))
    agent.nav.observe(r12, _view("Route 12", ["#.#", "#.#", "#.#"]), _warps_hex([]), [])
    agent.nav.record_noroute(r12, (1, 0), (1, 2))
    agent.s["nav_noroute"][f"{r12}:1,2"] = agent.s["step"]
    o = J.parse("walked\nf1 Route 12 (1,0) facing down | C L45 120/130 | ¥3000 | 4 badges")
    flute = J.Option("play the Poké Flute to wake the sleeping Pokémon", "manage", {"action": "use", "target": "Poké Flute"})
    agent.remember_door(o, flute, "AAAAAAA played the POKé FLUTE.\nbag: Poké Flute×1")
    assert not agent.nav.data["maps"][str(r12)].get("noroute")
    assert not agent.s["nav_noroute"] and agent.s["reobserve"] == "Route 12"
