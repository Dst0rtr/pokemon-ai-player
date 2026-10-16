"""Jev provider track: HTTP client (mocked transport), parsers, candidates, policy, labels, calibration summary,
solo objective graph, agent loop (fake server and the real one over MCP), harness glue. No network."""

import asyncio
import json
import os
import shutil
import sys
from argparse import Namespace

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
    f = SOLO.Facts(badges=5, items={"HM03", "HM04", "Tea"}, visited={"Saffron City", "Cinnabar Island"},
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


def _agent_args(tmp_path, variant="solo"):
    return Namespace(run_dir=str(tmp_path), session_id="t", variant=variant, jev_model="mock", planner_model="x",
                     replan_every=40, confidence_threshold=0.3, stuck_threshold=0.7, min_replan_gap=5, max_steps=8, seed=0, mock=True)


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
    assert all("correct" in r for r in recs if not r["forced"]) and recs[0]["why"] == "intro"
    events = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert events[0]["type"] == "start" and any(e["type"] == "usage" for e in events)
    assert json.loads((tmp_path / "jev_agent.json").read_text())["step"] == 8
    agent2 = Agent(a, srv, pol)                                    # a new chunk continues the saved progress
    assert agent2.resumed and agent2.s["step"] == 8


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
