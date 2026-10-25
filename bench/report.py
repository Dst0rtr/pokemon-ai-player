#!/usr/bin/env python3
"""
Turn results/*.json (one file per benchmark run) into RESULTS.md: a leaderboard plus a section
per run with the final team, the milestone timeline and the chunk table. Also derives the
per-run summary fields (starter, badge times, Elite Four times, final team) stored in each result.

    venv/bin/python bench/report.py            # rewrites RESULTS.md from results/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

BADGES = ["Boulder", "Cascade", "Thunder", "Rainbow", "Soul", "Marsh", "Volcano", "Earth"]
E4 = ["Lorelei", "Bruno", "Agatha", "Lance", "Champion"]
CHAMPION = "champion defeated (Hall of Fame)"
# Story order used to rank "furthest point reached"; later entries rank higher.
PROGRESS = (["starter", "reached: Viridian City", "reached: Viridian Forest", "reached: Pewter City", "badge: Boulder",
             "reached: Mt. Moon 1F", "reached: Cerulean City", "badge: Cascade", "reached: Vermilion City",
             "reached: S.S. Anne 1F", "badge: Thunder", "reached: Rock Tunnel 1F", "reached: Lavender Town",
             "reached: Celadon City", "reached: Rocket Hideout B1F", "badge: Rainbow", "reached: Pokémon Tower 1F",
             "reached: Fuchsia City", "reached: Safari Zone Gate", "badge: Soul", "reached: Silph Co. 1F",
             "badge: Marsh", "reached: Seafoam Islands 1F", "reached: Cinnabar Island", "reached: Pokémon Mansion 1F",
             "badge: Volcano", "badge: Earth", "reached: Victory Road 1F", "reached: Indigo Plateau Lobby"]
            + [f"defeated: {m}" for m in E4] + [CHAMPION])
RANK = {name: i for i, name in enumerate(PROGRESS)}


def _first(milestones: list[dict], name: str) -> dict | None:
    for m in milestones:
        if m.get("name") == name:
            return m
    return None


def derive(metrics: dict[str, Any], harness: dict[str, Any]) -> dict[str, Any]:
    ms = metrics.get("milestones") or []
    fs = metrics.get("final_state") or {}
    starter = next((m["name"].split(":", 1)[1].strip() for m in ms if m.get("name", "").startswith("starter:")), None)
    times: dict[str, dict] = {}
    for name in [f"badge: {b}" for b in BADGES] + [f"defeated: {m}" for m in E4] + [CHAMPION]:
        m = _first(ms, name)
        if m:
            times[name] = {"elapsed_s": m.get("elapsed_s"), "tool_calls": m.get("tool_calls"),
                           "playtime": (m.get("snapshot") or {}).get("playtime")}
    best = -1
    for m in ms:
        n = m.get("name", "")
        key = "starter" if n.startswith("starter:") else n
        if key in RANK and RANK[key] > best:
            best = RANK[key]
    furthest = PROGRESS[best] if best >= 0 else ("game started" if ms else "nothing")
    team = [{"species": t.get("species"), "nick": t.get("nick"), "level": t.get("level"), "hp": t.get("hp"),
             "max_hp": t.get("max_hp"), "moves": [mv[0] for mv in t.get("moves", [])], "stats": t.get("stats")}
            for t in fs.get("team") or []]
    return {"starter": starter, "badges": fs.get("badges", 0), "furthest": furthest, "furthest_rank": best,
            "milestone_times": times, "final_team": team, "playtime": fs.get("playtime"),
            "dex_owned": fs.get("dex_owned"), "maps_visited": fs.get("maps_visited"), "blackouts":
            sum(1 for m in ms if m.get("name") == "blacked out (lost a battle)"),
            "tool_calls": metrics.get("tool_calls_total", 0), "real_seconds": metrics.get("real_seconds", 0)}


# ---------------------------------------------------------------- formatting
def _hm(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}"


def _cell(t: dict | None) -> str:
    return f"{_hm(t['elapsed_s'])} · {t['tool_calls']}" if t else "—"


def _tokens(tok: dict | None) -> str:
    if not tok:
        return "—"
    return f"{tok.get('input', 0) / 1e6:.1f}M / {tok.get('cached_input', 0) / 1e6:.1f}M / {tok.get('output', 0) / 1e3:.0f}k"


def _cost(h: dict) -> str:
    c = h.get("cost_usd")
    if c is None:
        return "—"
    return f"${c:,.2f}" + (" (est.)" if h.get("cost_estimated") else "")


def rank_key(r: dict) -> tuple:
    d = r["derived"]
    champ = d["milestone_times"].get(CHAMPION)
    return (0 if champ else 1, champ["elapsed_s"] if champ else 0, -d["badges"], -d["furthest_rank"], d["tool_calls"])


def leaderboard(results: list[dict]) -> str:
    head = (["#", "Model", "Provider", "Starter", "Badges", "Furthest"] + BADGES + E4[:-1]
            + ["Rival (Champion)", "Hall of Fame", "Active h", "Tool calls", "Tokens uncached in / cache reads / out", "Cost", "Exit"])
    rows = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for i, r in enumerate(sorted(results, key=rank_key), 1):
        d, h, m = r["derived"], r["harness"], r["metrics"]
        t = d["milestone_times"]
        cells = [str(i), f"`{h.get('model')}`", h.get("provider", ""), d.get("starter") or "—", str(d["badges"]), d["furthest"]]
        cells += [_cell(t.get(f"badge: {b}")) for b in BADGES]
        cells += [_cell(t.get(f"defeated: {e}")) for e in E4]
        cells += [_cell(t.get(CHAMPION)), f"{(m.get('real_seconds') or 0) / 3600:.1f}", str(d["tool_calls"]),
                  _tokens(h.get("tokens")), _cost(h), h.get("exit_reason") or "—"]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def run_section(r: dict) -> str:
    d, h, m = r["derived"], r["harness"], r["metrics"]
    title = f"jev-{h['variant']}: {h.get('display_model') or h.get('model')}" if h.get("track") == "jev" else f"{h.get('model')} via {h.get('provider')}"
    out = [f"### {title} ({r['run_id']})", "",
           f"- CLI: `{h.get('cli')}` {h.get('cli_version')} · server commit `{h.get('server_commit')}` · prompt `{h.get('prompt_sha256')}`",
           f"- Started {h.get('started')} · ended {h.get('ended')} · active {_hm(m.get('real_seconds'))} h · wall {_hm(h.get('wall_seconds'))} h · paused {_hm(h.get('paused_seconds'))} h · exit: **{h.get('exit_reason')}**",
           f"- Tool calls {d['tool_calls']} · images {m.get('images_sent')} · reloads {m.get('loads', 0)} · black-outs {d['blackouts']} · in-game playtime {d.get('playtime')} · Pokédex {d.get('dex_owned')} owned · maps visited {d.get('maps_visited')}",
           f"- Tokens uncached in / cache reads / out: {_tokens(h.get('tokens'))}"
           + (f" (from {h['tokens_source']})" if h.get("tokens_source") else "") + f" · cost {_cost(h)} · chunks {len(h.get('chunks', []))}"
           + (f" · save/load scumming: {m.get('tool_calls', {}).get('load_state', 0)} reloads" if m.get("tool_calls", {}).get("load_state", 0) > 100 else ""), ""]
    if h.get("corrections"):
        out += ["**Corrections:** " + " ".join(h["corrections"]), ""]
    if d["final_team"]:
        out += ["**Final team**", "", "| # | Pokémon | Lv | HP | Atk | Def | Spd | Spc | Moves |", "|---|---|---|---|---|---|---|---|---|"]
        for i, t in enumerate(d["final_team"], 1):
            st = t.get("stats") or [None] * 4
            name = t["species"] if not t.get("nick") or t["nick"] == (t["species"] or "").upper() else f"{t['nick']} ({t['species']})"
            out.append(f"| {i} | {name} | {t.get('level')} | {t.get('hp')}/{t.get('max_hp')} | {st[0]} | {st[1]} | {st[2]} | {st[3]} | {', '.join(t.get('moves') or [])} |")
        out.append("")
    else:
        out += ["**Final team**: none", ""]
    ms = m.get("milestones") or []
    if ms:
        out += ["**Milestones** (first occurrence; time is active server time)", "", "| Time | Calls | Playtime | Milestone |", "|---|---|---|---|"]
        seen = set()
        for x in ms:
            if x["name"] in seen or x["name"].startswith("loaded state"):
                continue
            seen.add(x["name"])
            out.append(f"| {_hm(x.get('elapsed_s'))} | {x.get('tool_calls')} | {(x.get('snapshot') or {}).get('playtime', '')} | {x['name']} |")
        out.append("")
    notes = m.get("notes") or []
    if notes:
        out += ["**Agent notes**", ""] + [f"- {n}" for n in notes[-15:]] + [""]
    chunks = h.get("chunks") or []
    if chunks:
        reasons: dict[str, int] = {}
        for c in chunks:
            reasons[c["exit_reason"]] = reasons.get(c["exit_reason"], 0) + 1
        secs = sorted(c["seconds"] for c in chunks)
        why = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]))
        out += [f"**CLI chunks:** {len(chunks)} (the CLI is restarted whenever the model ends its turn, a chunk rotates, "
                f"stalls or is rate-limited): {why}; median {secs[len(secs) // 2] / 60:.1f} min, longest {secs[-1] / 60:.0f} min.", ""]
        if len(chunks) <= 30:
            out += ["<details><summary>Chunks</summary>", "", "| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out |", "|---|---|---|---|---|---|"]
            for c in chunks:
                out.append(f"| {c['n']} | {c['started']} | {c['seconds'] / 60:.0f} | {c['exit_reason']} | {c['tool_calls_seen']} | {_tokens(c.get('tokens'))} |")
            out += ["", "</details>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- Jev track
JEV_SCAFFOLDING = {
    "solo": "The final exam: Jev + code only, no LLM anywhere, stuck = fail. Code enumerates the legal actions every step, reads progress (badges, bag, "
            "moves, maps, milestones) and walks a whole-game objective graph; it also heals, trains to level targets, teaches "
            "HMs, clears obstacles and runs stuck recovery. Jev picks every action and answers yes/no checks "
            "(\"stuck?\", \"objective done?\" where code cannot see a story event).",
    "assist": "jev-solo's scaffolding plus a safety net: when Jev's confidence is low or code detects stuck/looping, Claude "
              "Haiku picks that one action and a fallback event is logged; fallbacks per 1k steps should trend to 0 across "
              "self-improvement iterations (bench/improve.py).",
    "hybrid": "Claude Haiku sets the objective (every N steps, on low Jev confidence, when Jev says stuck, after a badge); "
              "code enumerates the actions; Jev picks every action.",
    "scripted": "A short code-side objective list (no rules, no recovery); code enumerates the actions; Jev picks every action.",
    "battles": "The normal Claude Code run (same tools and prompt plus one line), except battle('auto') turns are picked by Jev "
               "from the legal moves/switches/items.",
}


def is_jev(r: dict) -> bool:
    return (r.get("harness") or {}).get("track") == "jev"


def _ms(x) -> str:
    return "—" if x is None else f"{x:.0f}"


def over_cap(h: dict) -> bool:
    """Whether a run had more than the standard benchmark limits (12 h of active play, 20,000 tool calls), from the
    budget it recorded (older results without one count as standard)."""
    b = h.get("budget") or {}
    return (b.get("max_calls") or 0) > 20000 or (b.get("hours") or 0) > 12


def map_cell(h: dict) -> str:
    """How the Jev player knew the maps: rom, learned (blank) or learned (carried atlas). Older runs: rom."""
    ms = h.get("map_source") or {}
    if h.get("variant") == "battles":
        return "—"
    tags = [t for t in ("experiment" if h.get("experiment") and not h.get("benchmark_entry") else "",
                        "outside the 20k cap" if over_cap(h) else "") if t]
    exp = "".join(f" — {t}" for t in tags)
    if ms.get("source") == "learned":
        return ("learned (carried atlas)" if ms.get("atlas_seed") else "learned (blank)") + exp
    return "rom" + exp


def jev_leaderboard(results: list[dict]) -> str:
    head = ["#", "Variant", "Model", "Maps", "Segment", "Badges", "Furthest", "Hall of Fame", "Active h", "Tool calls", "Jev calls",
            "Fallbacks (/1k steps)",
            "Jev latency p50 / p95 ms", "Jev cost", "LLM cost", "Total cost", "Correct", "ECE", "Exit"]
    rows = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for i, r in enumerate(sorted(results, key=rank_key), 1):
        d, h, m = r["derived"], r["harness"], r["metrics"]
        j = h.get("jev") or {}
        lat = j.get("latency_ms") or {}
        jc = j.get("jev_cost_usd")
        total = h.get("cost_usd")
        llm = None if total is None or jc is None else max(total - jc, 0.0)
        acc = j.get("accuracy")
        fb = "—" if j.get("fallbacks") is None else f"{j['fallbacks']} ({j.get('fallbacks_per_1k_steps')})"
        seg = (h.get("segment") or {}).get("name", "full game") + (f" · it{h['iteration']}" if h.get("iteration") is not None else "")
        cells = [str(i), f"jev-{h.get('variant')}" + (" (mock)" if h.get("mock") else ""), f"`{h.get('display_model') or h.get('model')}`",
                 map_cell(h), seg, str(d["badges"]), d["furthest"], _cell(d["milestone_times"].get(CHAMPION)),
                 f"{(m.get('real_seconds') or 0) / 3600:.1f}", str(d["tool_calls"]), str(j.get("jev_calls", "—")), fb,
                 f"{_ms(lat.get('p50'))} / {_ms(lat.get('p95'))}", "—" if jc is None else f"${jc:,.2f}",
                 "—" if llm is None else f"${llm:,.2f}", _cost(h), "—" if acc is None else f"{acc:.0%}",
                 "—" if j.get("ece") is None else f"{j['ece']:.3f}", h.get("exit_reason") or "—"]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def jev_entries(results: list[dict]) -> str:
    """The Jev full-game runs recorded as benchmark entries (`harness.benchmark_entry`: a label saying how each was run:
    assisted or not, map knowledge, seeds); standard limits first, then runs over them (`over_cap`, from the budget)."""
    rows = [r for r in results if r["harness"].get("benchmark_entry")]
    if not rows:
        return ""
    head = ["Entry", "Variant", "Badges", "Furthest", "Hall of Fame", "Tool calls", "Steps", "Active h", "Total cost", "Exit"]
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for r in sorted(rows, key=lambda r: (over_cap(r["harness"]), r["run_id"])):
        h, d, m = r["harness"], r["derived"], r["metrics"]
        out.append("| " + " | ".join([
            h["benchmark_entry"].get("label", ""), f"jev-{h.get('variant')}", str(d["badges"]), d["furthest"],
            _cell(d["milestone_times"].get(CHAMPION)), str(d["tool_calls"]), str((h.get("jev") or {}).get("steps", "—")),
            f"{(m.get('real_seconds') or 0) / 3600:.1f}", _cost(h), h.get("exit_reason") or "—"]) + " |")
    return "\n".join(out)


def iteration_table(results: list[dict]) -> str:
    """Self-improvement trend: one row per iteration run, grouped by segment, oldest first."""
    rows = [r for r in results if r["harness"].get("iteration") is not None]
    if not rows:
        return ""
    head = ["Segment (state)", "Iter", "Variant", "Maps", "Steps", "Fallbacks", "Per 1k steps", "Goal", "Badges", "Active h",
            "Jev $", "Haiku $", "Opus $", "Total $", "Exit"]
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    key = lambda r: ((r["harness"].get("segment") or {}).get("name", ""), r["harness"]["iteration"], r["run_id"])  # noqa: E731
    for r in sorted(rows, key=key):
        h, d, m = r["harness"], r["derived"], r["metrics"]
        j, seg = h.get("jev") or {}, h.get("segment") or {}
        jc, llm, opus = j.get("jev_cost_usd") or 0.0, j.get("planner_cost_usd") or 0.0, h.get("analysis_cost_usd") or 0.0
        goal = seg.get("goal")
        reached = goal and any(str(x.get("name", "")).startswith(goal) for x in m.get("milestones") or [])
        out.append("| " + " | ".join([
            f"{seg.get('name', 'full game')}" + (f" (`{seg['state_sha256']}`)" if seg.get("state_sha256") else ""),
            str(h["iteration"]), h.get("variant", ""), map_cell(h), str(j.get("steps", "—")), str(j.get("fallbacks", "—")),
            str(j.get("fallbacks_per_1k_steps", "—")), ("✓ " if reached else "✗ ") + (goal or "—"), str(d["badges"]),
            f"{(m.get('real_seconds') or 0) / 3600:.2f}", f"${jc:,.2f}", f"${llm:,.2f}", f"${opus:,.2f}",
            f"${jc + llm + opus:,.2f}", h.get("exit_reason") or "—"]) + " |")
    return "\n".join(out)


def calibration_table(j: dict) -> str:
    cal = j.get("calibration") or []
    if not cal:
        return "_No labelled Jev decisions._"
    out = ["| Jev confidence | Decisions | Mean confidence | Mean p(choice) | Correct | |", "|---|---|---|---|---|---|"]
    for b in cal:
        bar = "█" * round(b["accuracy"] * 20)
        out.append(f"| {b['lo']:.1f}–{b['hi']:.1f} | {b['n']} | {b['mean_conf']:.2f} | {b['mean_p']:.2f} | {b['accuracy']:.0%} | `{bar:<20}` |")
    return "\n".join(out)


def jev_section(r: dict) -> str:
    h = r["harness"]
    j = h.get("jev") or {}
    lat = j.get("latency_ms") or {}
    out = [run_section(r), f"**Jev ({h.get('variant')})** — {JEV_SCAFFOLDING.get(h.get('variant'), '')}", "",
           f"- Decisions {j.get('decisions')} (asked Jev {j.get('jev_calls')}, forced by code {j.get('forced')}, labelled {j.get('scored')}) · "
           f"models {', '.join(j.get('models') or []) or '—'} · input tokens {j.get('input_tokens')} · Jev ${j.get('jev_cost_usd', 0):.4f}",
           f"- Jev latency mean {_ms(lat.get('mean'))} ms · p50 {_ms(lat.get('p50'))} · p95 {_ms(lat.get('p95'))} · max {_ms(lat.get('max'))}",
           (f"- Fallbacks {j.get('fallbacks')} ({j.get('fallbacks_per_1k_steps')} per 1k steps; by trigger {j.get('by_trigger')}; "
            f"agreed with Jev {j.get('fallback_agreed_with_jev')}; progress within 10 steps {j.get('fallback_progress_rate')}; "
            f"${j.get('fallback_cost_usd', 0):.4f})" if j.get("fallbacks") is not None else "- Fallbacks: none (variant without a safety net)"),
           (f"- Segment {h['segment'].get('name')} from state `{h['segment'].get('state_sha256')}` to `{h['segment'].get('goal')}`"
            + (f" · iteration {h.get('iteration')}" + (f" (analysis cost ${h['analysis_cost_usd']:.2f})" if h.get("analysis_cost_usd") else "")
               if h.get("iteration") is not None else "") if h.get("segment") else
            (f"- Iteration {h.get('iteration')}" if h.get("iteration") is not None else "- Full game from power-on")),
           f"- Planner calls {j.get('planner_calls', 0)} (${j.get('planner_cost_usd', 0):.4f}, errors {j.get('planner_errors', 0)}) · "
           f"objective changes {j.get('objective_changes', 0)} · objectives Jev marked done {j.get('jev_marked_done', 0)}"
           + (f" · final objective: {j['final_objective']}" if j.get("final_objective") else ""), ""]
    if j.get("by_kind"):
        out += ["| Decision kind | Labelled | Correct | Mean confidence |", "|---|---|---|---|"]
        out += [f"| {k} | {v['n']} | {v['accuracy']:.0%} | {v['mean_conf']:.2f} |" for k, v in j["by_kind"].items()]
        out.append("")
    out += ["**Confidence vs. correctness** (\"correct\" = the chosen action was accepted and did what it is for: a move that "
            "hurt the foe at least as much as the turn hurt us, a walk that moved or started something new, a press that changed "
            f"the screen; ECE against p(choice) = {j.get('ece')})", "", calibration_table(j), ""]
    return "\n".join(out)


def dump_result(result: dict) -> str:
    """Indented JSON, but one line per chunk and per milestone so long runs stay reviewable and small."""
    def lines(items):
        return "[\n" + ",\n".join("  " + json.dumps(x, ensure_ascii=False) for x in items) + "\n ]" if items else "[]"
    r = json.loads(json.dumps(result))
    chunks = r.get("harness", {}).pop("chunks", [])
    miles = r.get("metrics", {}).pop("milestones", [])
    text = json.dumps(r, indent=1, ensure_ascii=False)
    text = text.replace('"harness": {', '"harness": {\n  "chunks": ' + lines(chunks) + ",", 1)
    text = text.replace('"metrics": {', '"metrics": {\n  "milestones": ' + lines(miles) + ",", 1)
    return text + "\n"


def load_results(results_dir: Path) -> list[dict]:
    out = []
    for p in sorted(results_dir.glob("*.json")):
        try:
            r = json.loads(p.read_text())
        except ValueError:
            continue
        if r.get("schema") != 1:
            continue
        r.setdefault("derived", derive(r.get("metrics", {}), r.get("harness", {})))
        out.append(r)
    return out


def build_results_md(results: list[dict]) -> str:
    parts = ["# Benchmark results", "",
             "Each row is one autonomous playthrough of Pokémon Red from power-on by an agent CLI driving the "
             "[Game Boy MCP server](README.md), with the same prompt, the same server flags and a budget of "
             "12 hours of active play or 20,000 tool calls. Time cells are `active hours:minutes · tool calls` "
             "when the milestone was reached; `—` means never. Ranking: Champion first (by time), then badges, "
             "then the furthest story point, then fewer tool calls. Cost is the CLI's own API-equivalent figure "
             "(runs on a subscription are not billed per token); `(est.)` marks an estimate from list prices. "
             "Raw data: `results/*.json`; regenerate with `python bench/report.py`. Each result records the server commit "
             "it ran on (`harness.server_commit`): the server has gained features since round one (October 2026), so "
             "compare runs made on the same server version.", ""]
    cli = [r for r in results if not is_jev(r)]
    jev = [r for r in results if is_jev(r)]
    if not results:
        return "\n".join(parts + ["_No runs yet._", ""])
    parts += [leaderboard(cli) if cli else "_No agent CLI runs yet._", ""]
    if jev:
        parts += ["## Jev track (code-scaffolded, not comparable with the table above)", "",
                  "Jev (TypeSafe's System One model) answers typed questions; it cannot write text or call tools. In these runs "
                  "code does what an agent CLI does for itself: it reads the server's replies, lists the legal actions as a "
                  "closed set every step and executes the one Jev picks. **jev-solo uses heavy code scaffolding**: a "
                  "whole-game objective graph, progress checks, healing/training/HM rules and stuck recovery are written in "
                  "code, and no LLM is called. Cost is Jev's input tokens ($0.042/MTok, output free) plus any LLM the "
                  "variant uses.", "", "Variants: " + " ".join(f"**{k}**: {v}" for k, v in JEV_SCAFFOLDING.items()), ""]
        entries = jev_entries(jev)
        if entries:
            parts += ["### Jev full-game benchmark entries", "",
                      "Jev full-game runs from power-on (jev-solo: no LLM). The label says how each was run. "
                      "An entry outside the standard limits is not comparable with a capped run.", "", entries, "",
                      "### All Jev runs (iterations, segments and labelled experiments included)", ""]
        parts += [jev_leaderboard(jev), ""]
        it = iteration_table(jev)
        if it:
            parts += ["### Self-improvement iterations (jev-assist → bench/improve.py → next iteration; goal: 0 fallbacks, "
                      "then pass jev-solo)", "", it, ""]
    parts += ["## Runs", ""]
    for r in sorted(cli, key=rank_key):
        parts += [run_section(r)]
    for r in sorted(jev, key=rank_key):
        parts += [jev_section(r)]
    return "\n".join(parts)


def write_results_md(results_dir: Path, out: Path) -> Path:
    out.write_text(build_results_md(load_results(results_dir)))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results"
    print(write_results_md(rd, ROOT / "RESULTS.md"))
