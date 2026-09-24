"""Benchmark harness: stream parsers, derived results and the report, without running any CLI."""

import json
from pathlib import Path

from bench.report import CHAMPION, build_results_md, derive, rank_key
from bench.stream import ChunkStats

FIX = Path(__file__).parent / "fixtures"


def test_claude_stream_parses_usage_and_session():
    st = ChunkStats("claude")
    for line in (FIX / "claude_stream.jsonl").read_text().splitlines():
        st.feed_line(line)
    assert st.session_id == "0750e85f-903a-41e3-8c3a-4ce533f74bcf"
    assert st.finished and st.tokens["input"] == 10 and st.tokens["cache_write"] == 6610 and st.tokens["output"] == 42
    assert st.tokens["reasoning"] == 34 and abs(st.cost_usd - 0.01344) < 1e-9
    assert st.tool_calls == 0 and not st.rate_limited and not st.errors and st.result_text == "pong"


def test_claude_tool_use_and_rate_limit_events():
    st = ChunkStats("claude")
    st.feed({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__gameboy__walk", "input": {}}]}})
    st.feed({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "rateLimitType": "five_hour", "resetsAt": 1}})
    st.feed({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "Rate limit reached", "usage": {}})
    assert st.tool_calls == 1 and st.rate_limited and st.errors


def test_codex_stream_parses_thread_and_usage():
    st = ChunkStats("codex")
    for line in (FIX / "codex_stream.jsonl").read_text().splitlines():
        st.feed_line(line)
    assert st.session_id == "01a0d1b6-508b-7370-bbaa-e53155a86f9e"
    assert st.tokens["input"] == 17566 and st.tokens["cached_input"] == 11136 and st.tokens["output"] == 5
    assert st.cost_usd is None and st.turns == 1 and st.result_text == "pong"
    st.feed({"type": "item.started", "item": {"type": "mcp_tool_call", "server": "gameboy", "tool": "walk"}})
    st.feed({"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "gameboy", "tool": "walk"}})
    assert st.tool_calls == 1
    st.feed({"type": "error", "message": "429 rate limit exceeded"})
    assert st.rate_limited


def _metrics(names, badges=1, team=True):
    ms = [{"name": n, "frame": i * 100, "elapsed_s": 60.0 * i, "tool_calls": 10 * i, "at": "t",
           "snapshot": {"playtime": f"0:{i:02d}:00"}} for i, n in enumerate(names, 1)]
    return {"session_id": "s", "real_seconds": 3600.0, "tool_calls_total": 500, "images_sent": 3, "loads": 1,
            "milestones": ms, "notes": ["remember Cut"],
            "final_state": {"badges": badges, "playtime": "1:00:00", "dex_owned": 5, "maps_visited": 9,
                            "team": [{"species": "Charmeleon", "nick": "CHARMELEON", "level": 23, "hp": 10, "max_hp": 65,
                                      "moves": [["Ember", 25]], "stats": [34, 32, 47, 37]}] if team else []}}


def _result(run_id, model, provider, names, badges, cost=None):
    m = _metrics(names, badges)
    h = {"provider": provider, "cli": provider, "cli_version": "1", "model": model, "started": "2026-09-24T00:00:00",
         "ended": "2026-09-24T01:00:00", "wall_seconds": 3600, "paused_seconds": 0, "exit_reason": "budget_time",
         "tokens": {"input": 1_000_000, "cached_input": 5_000_000, "output": 50_000}, "cost_usd": cost,
         "cost_estimated": False, "chunks": [{"n": 1, "started": "t", "seconds": 3600, "exit_reason": "budget_time",
                                              "tool_calls_seen": 500, "tokens": {"input": 1}, "cost_usd": cost}]}
    return {"schema": 1, "run_id": run_id, "harness": h, "metrics": m, "derived": derive(m, h)}


def test_derive_extracts_starter_badges_and_times():
    d = derive(_metrics(["game started", "starter: Charmander", "reached: Viridian City", "badge: Boulder",
                         "loaded state 'x'", "badge: Boulder", "defeated: Lorelei"]), {})
    assert d["starter"] == "Charmander" and d["badges"] == 1
    assert d["milestone_times"]["badge: Boulder"]["tool_calls"] == 40          # first occurrence wins
    assert d["milestone_times"]["defeated: Lorelei"]["elapsed_s"] == 420.0
    assert d["furthest"] == "defeated: Lorelei" and d["final_team"][0]["moves"] == ["Ember"]
    assert derive({}, {})["furthest"] == "nothing"


def test_ranking_and_results_md():
    a = _result("a", "model-a", "claude", ["starter: Squirtle", "badge: Boulder", "badge: Cascade"], 2, 1.5)
    b = _result("b", "model-b", "codex", ["starter: Bulbasaur", "badge: Boulder"], 1)
    c = _result("c", "model-c", "claude", ["starter: Charmander", "badge: Boulder", CHAMPION], 8, 9.0)
    order = [r["run_id"] for r in sorted([a, b, c], key=rank_key)]
    assert order == ["c", "a", "b"]
    md = build_results_md([a, b, c])
    assert md.startswith("# Benchmark results")
    rows = [ln for ln in md.splitlines() if ln.startswith("| 1 |") or ln.startswith("| 2 |") or ln.startswith("| 3 |")]
    assert "model-c" in rows[0] and "Charmander" in rows[0] and "model-b" in rows[2]
    assert "0:02 · 20" in rows[1]                                            # Boulder cell for run a
    assert "1.0M / 5.0M / 50k" in md and "$1.50" in md and "$9.00" in md
    assert "**Final team**" in md and "| 1 | Charmeleon | 23 |" in md and "remember Cut" in md
    assert build_results_md([]).endswith("_No runs yet._\n")
    json.dumps(a)                                                            # results stay JSON-serialisable
