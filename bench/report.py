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
    head = ["#", "Model", "Provider", "Starter", "Badges", "Furthest"] + BADGES + E4 + ["Champion", "Active h", "Tool calls", "Tokens in / cached / out", "Cost", "Exit"]
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
    out = [f"### {h.get('model')} via {h.get('provider')} ({r['run_id']})", "",
           f"- CLI: `{h.get('cli')}` {h.get('cli_version')} · server commit `{h.get('server_commit')}` · prompt `{h.get('prompt_sha256')}`",
           f"- Started {h.get('started')} · ended {h.get('ended')} · active {_hm(m.get('real_seconds'))} h · wall {_hm(h.get('wall_seconds'))} h · paused {_hm(h.get('paused_seconds'))} h · exit: **{h.get('exit_reason')}**",
           f"- Tool calls {d['tool_calls']} · images {m.get('images_sent')} · reloads {m.get('loads', 0)} · black-outs {d['blackouts']} · in-game playtime {d.get('playtime')} · Pokédex {d.get('dex_owned')} owned · maps visited {d.get('maps_visited')}",
           f"- Tokens in / cached / out: {_tokens(h.get('tokens'))} · cost {_cost(h)} · chunks {len(h.get('chunks', []))}", ""]
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
        out += ["<details><summary>Chunks</summary>", "", "| # | Started | Minutes | Exit | Tool calls seen | Tokens in / cached / out | Cost |", "|---|---|---|---|---|---|---|"]
        for c in chunks:
            out.append(f"| {c['n']} | {c['started']} | {c['seconds'] / 60:.0f} | {c['exit_reason']} | {c['tool_calls_seen']} | {_tokens(c.get('tokens'))} | {c.get('cost_usd') if c.get('cost_usd') is not None else '—'} |")
        out += ["", "</details>", ""]
    return "\n".join(out)


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
             "then the furthest story point, then fewer tool calls. Raw data: `results/*.json`; regenerate with "
             "`python bench/report.py`.", ""]
    if not results:
        return "\n".join(parts + ["_No runs yet._", ""])
    parts += [leaderboard(results), "", "## Runs", ""]
    for r in sorted(results, key=rank_key):
        parts += [run_section(r)]
    return "\n".join(parts)


def write_results_md(results_dir: Path, out: Path) -> Path:
    out.write_text(build_results_md(load_results(results_dir)))
    return out


if __name__ == "__main__":
    rd = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results"
    print(write_results_md(rd, ROOT / "RESULTS.md"))
