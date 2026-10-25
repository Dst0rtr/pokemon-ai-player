"""Benchmark harness: stream parsers, derived results and the report, without running any CLI."""

import json
from pathlib import Path

from bench.report import CHAMPION, build_results_md, derive, dump_result, rank_key
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
    assert st.tokens["input"] == 17566 - 11136 and st.tokens["cached_input"] == 11136 and st.tokens["output"] == 5
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


def test_claude_tokens_accumulate_per_message_without_result():
    st = ChunkStats("claude")
    usage = {"input_tokens": 5, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 20}
    for block in ({"type": "thinking", "thinking": ""}, {"type": "tool_use", "name": "mcp__gameboy__walk", "input": {}}):
        st.feed({"type": "assistant", "message": {"id": "m1", "usage": usage, "content": [block]}})
    st.feed({"type": "assistant", "message": {"id": "m2", "usage": usage, "content": [{"type": "text", "text": "hi"}]}})
    assert st.tokens["input"] == 10 and st.tokens["cached_input"] == 2000 and st.tokens["output"] == 40   # m1 counted once
    st.feed({"type": "result", "usage": {"input_tokens": 11, "output_tokens": 41}, "total_cost_usd": 0.5, "session_id": "s"})
    assert st.tokens["input"] == 11 and st.tokens["output"] == 41 and st.cost_usd == 0.5


def test_dump_result_round_trips_and_keeps_chunks_on_single_lines():
    a = _result("a", "model-a", "claude", ["starter: Squirtle", "badge: Boulder"], 1, 1.5)
    text = dump_result(a)
    assert json.loads(text) == a
    assert sum(1 for ln in text.splitlines() if ln.startswith('  {"n": 1')) == 1          # the chunk is one line
    assert sum(1 for ln in text.splitlines() if ln.startswith('  {"name": "badge: Boulder"')) == 1


def test_metrics_active_time_caps_idle_gaps(tmp_path):
    import time
    from metrics import IDLE_CAP, MetricsTracker
    t = MetricsTracker("m", "rom", tmp_path)
    t._last_tick = time.time() - 4000                      # the client went quiet for over an hour
    assert t.elapsed() < IDLE_CAP + 1
    t.record_call("walk", 10, False)
    assert IDLE_CAP - 1 < t.active_seconds < IDLE_CAP + 1
    t._last_tick = time.time() - 10
    t.record_call("walk", 10, False)
    assert IDLE_CAP + 8 < t.active_seconds < IDLE_CAP + 12  # short gaps count in full


def test_claude_transcript_usage_counts_each_message_once(tmp_path):
    from bench.providers import claude_transcript_usage
    d = tmp_path / "-some-run-dir"
    d.mkdir()
    u1 = {"input_tokens": 3, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10, "output_tokens": 40,
          "output_tokens_details": {"thinking_tokens": 7}}
    u2 = {"input_tokens": 1, "cache_read_input_tokens": 200, "cache_creation_input_tokens": 0, "output_tokens": 5}
    lines = [{"type": "user", "message": {"role": "user"}},
             {"type": "assistant", "message": {"id": "m1", "usage": u1}},
             {"type": "assistant", "message": {"id": "m1", "usage": u1}},   # one entry per content block
             {"type": "assistant", "message": {"id": "m2", "usage": u2}}]
    (d / "sess.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    tok = claude_transcript_usage(["sess", None], root=str(tmp_path))
    assert tok == {"input": 4, "cached_input": 300, "cache_write": 10, "output": 45, "reasoning": 7}
    assert claude_transcript_usage(["missing"], root=str(tmp_path)) == {}


def test_run_cost_estimates_when_the_last_claude_chunk_reported_none():
    from bench.run import run_cost
    prices = {"input": 10.0, "cached_input": 0.25, "cache_write": 20.0, "output": 50.0}
    tok = {"input": 0, "cached_input": 4_000_000, "cache_write": 0, "output": 0}
    c = lambda cost, t=1, s="a": {"cost_usd": cost, "tokens": {"input": t}, "cli_session": s}  # noqa: E731
    assert run_cost("claude", [c(None), c(2.0), c(3.0)], tok, prices) == (3.0, False)
    assert run_cost("claude", [c(2.0), c(2.0, t=0)], tok, prices) == (2.0, False)   # idle rate-limit chunk
    assert run_cost("claude", [c(0.5), c(None)], tok, prices) == (1.0, True)
    assert run_cost("claude", [c(2.0), c(None)], tok, prices) == (2.0, False)  # estimate below the CLI figure
    assert run_cost("claude", [c(2.0), c(None)], tok, None) == (2.0, False)
    assert run_cost("claude", [c(2.0, s="a"), c(1.5, s="b")], tok, prices) == (3.5, False)  # fresh-session fallback
    assert run_cost("codex", [c(None)], tok, None) == (None, False)


def test_jev_benchmark_entries_carry_their_label():
    """A Jev full-game run recorded as a benchmark entry is listed with its label (assisted or not, atlas, seeds, cap),
    and an entry outside the standard call cap is not shown as an experiment nor ranked as a standard run."""
    def jev(run_id, names, badges, entry, experiment=None, budget=(12.0, 20000)):
        r = _result(run_id, "jev-latest", "jev", names, badges, 0.3)
        r["harness"].update({"track": "jev", "variant": "solo", "mode": "jev-solo", "experiment": experiment,
                             "map_source": {"source": "learned", "atlas_seed": None}, "jev": {"steps": 100},
                             "benchmark_entry": entry, "budget": {"hours": budget[0], "max_calls": budget[1]}})
        return r
    std = jev("std", ["badge: Boulder"], 5, {"label": "standard limits (12 h / 20,000 calls)"})
    unc = jev("unc", ["badge: Boulder", CHAMPION], 8,
              {"label": "unassisted, blank atlas, one seed, outside the standard 20,000-call cap"},
              experiment="uncapped-2", budget=(48.0, 1000000))
    other = jev("exp", ["badge: Boulder"], 1, None, experiment="a segment check")
    it = jev("it91", ["badge: Boulder", CHAMPION], 8, None, budget=(6.0, 100000))   # an iteration on a bigger budget
    it["harness"]["iteration"] = 91
    md = build_results_md([std, unc, other, it])
    sec = md.split("### Jev full-game benchmark entries", 1)[1].split("### All Jev runs", 1)[0]
    rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and not ln.startswith("| Entry")]
    assert len(rows) == 2 and "standard limits" in rows[0] and "outside the standard 20,000-call cap" in rows[1]
    assert "0:02 · 20" in rows[1] and "| — |" in rows[0]                      # Hall of Fame cells
    unc_row = next(ln for ln in md.splitlines() if "outside the 20k cap" in ln)   # its row in the full Jev table
    assert "experiment" not in unc_row and "learned (blank)" in unc_row
    assert "learned (blank) — experiment" in md                                     # a plain experiment still says so
    # whether a run kept the standard limits comes from its recorded budget, not from a hand-written flag
    board = md.split("### All Jev runs", 1)[1].splitlines()
    row = lambda key: next(ln for ln in board if key in ln)                          # noqa: E731
    assert "outside the 20k cap" in row("full game · it91") and "outside the 20k cap" not in row("| 5 |")
