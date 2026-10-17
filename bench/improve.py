#!/usr/bin/env python3
"""
Self-improvement step for the Jev track (between runs, offline).

    # 1. cluster the fallback events of one or more jev-assist runs; writes the exact Opus prompt (no API call)
    venv/bin/python bench/improve.py analyze bench/runs/<run_id> [more runs...] --iteration 1
    # 2. the same with the Opus call (costs money: needs Bijan's go)
    venv/bin/python bench/improve.py analyze bench/runs/<run_id> --iteration 1 --call
    # 3. apply the proposal on a new iteration branch (never on main; nothing is committed)
    venv/bin/python bench/improve.py apply --iteration 1
    # 4. rerun from the same segment state, then compare iterations
    venv/bin/python bench/run.py --provider jev --variant assist --segment after-brock --iteration 2
    venv/bin/python bench/improve.py compare --segment after-brock

Outputs go to bench/iterations/it<N>/: clusters.json, prompt.md, and with --call reply.md, summary.md,
proposal.patch and analysis.json (model, cost, clusters, source runs). run.py --iteration N+1 records that
analysis cost so RESULTS.md can show Jev + Haiku + Opus cost per iteration.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.jev import read_jsonl  # noqa: E402

OPUS = "claude-opus-5-5"
SCAFFOLDING = ["bench/jev_solo.py", "bench/jev.py", "bench/jev_agent.py", "bench/jev_nav.py"]

PROMPT = """You are improving the code scaffolding that lets Jev (TypeSafe's "System One" decision model) play Pokémon Red.
Jev cannot write text or call tools: every step, code lists the legal actions as a closed set, sends Jev a JSON `state`
and a Choice question, and executes the option Jev picks. Long-horizon structure (the objective graph, rules for healing,
training and HMs, stuck recovery) is code. In jev-assist runs, when Jev's confidence is below a threshold or code detects
that the player is stuck or looping, Claude Haiku picks that one action instead and a "fallback event" is recorded. The goal
is zero fallbacks: Jev playing alone (the strict jev-solo mode, where stuck = fail).

Below are the fallback events of {n_runs} run(s), clustered by (trigger, objective node, map, situation), followed by the
current scaffolding source. For each cluster (largest first):
1. Diagnose why Jev could not decide on its own: missing or misleading candidate options, state text that hides what
   matters, an objective/graph entry that is wrong or too vague, a threshold that fires too often, a stuck rule that is
   missing, or a genuine limit of Jev (say so plainly when code cannot fix it).
2. Propose concrete code changes: objective-graph entries (bench/jev_solo.py GRAPH), candidate-action generators
   (bench/jev.py *_options, talk_to_options), the questions and state text sent to Jev (JevPolicy.INSTRUCTIONS,
   Agent.jev_state), thresholds, stuck-recovery rules. Jev's docs: keep arithmetic in code, keep the state small and
   relevant, write literal instructions, give each option clear criteria, and do not rely on option order.

Reply in two parts:
## Summary
A short human-readable report: per cluster, the diagnosis, the proposed change and the expected effect on fallbacks.
## Patch
One ```diff fenced block with a unified diff (paths relative to the repository root, a/ and b/ prefixes) that applies
cleanly to the files shown. Change only bench/jev_solo.py, bench/jev.py, bench/jev_agent.py and bench/jev_nav.py.
Keep the code style.
{notes}

# Clusters
{clusters}

# Source
{source}
"""


def cluster_key(e: dict) -> tuple:
    return (e.get("trigger", "?"), e.get("node") or "?", e.get("map") or e.get("mode") or "?", e.get("mode", "?"))


def build_clusters(events: list[dict], per_cluster: int = 4) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        groups[cluster_key(e)].append(e)
    out = []
    for key, evs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        done = [e for e in evs if (e.get("outcome_after") or {}).get("complete")]
        choices: dict[str, int] = defaultdict(int)
        for e in evs:
            choices[f"jev: {e.get('jev_choice')} -> fallback: {e.get('fallback_choice')}"] += 1
        samples = []
        for e in evs[:per_cluster]:
            samples.append({k: e.get(k) for k in ("step", "trigger_detail", "pos", "objective", "screen", "recent_actions",
                                                   "options", "jev_choice", "jev_confidence", "fallback_choice",
                                                   "fallback_why", "immediate", "outcome_after", "summary")})
        out.append({"trigger": key[0], "node": key[1], "map": key[2], "mode": key[3], "count": len(evs),
                    "runs": sorted({e.get("run") for e in evs}),
                    "agreed_with_jev": sum(1 for e in evs if e.get("agreed")),
                    "progress_after": round(sum(1 for e in done if e["outcome_after"].get("progress")) / len(done), 3) if done else None,
                    "top_swaps": sorted(choices.items(), key=lambda kv: -kv[1])[:5],
                    "mean_jev_confidence": round(sum(float(e.get("jev_confidence") or 0) for e in evs) / len(evs), 3),
                    "samples": samples})
    return out


def load_events(run_dirs: list[str]) -> list[dict]:
    events = []
    for d in run_dirs:
        p = Path(d) / "fallbacks.jsonl"
        if not p.exists():
            raise SystemExit(f"{p} not found (fallback events come from jev-assist runs)")
        events += read_jsonl(p)
    return events


def build_prompt(clusters: list[dict], n_runs: int, max_clusters: int = 12, notes: str = "") -> str:
    source = "\n\n".join(f"## {f}\n```python\n{(ROOT / f).read_text()}\n```" for f in SCAFFOLDING)
    text = json.dumps(clusters[:max_clusters], ensure_ascii=False, indent=1)
    notes = f"\n# Changes already made since these runs (do not re-propose them; the source below includes them)\n{notes.strip()}\n" \
        if notes.strip() else ""
    return PROMPT.format(n_runs=n_runs, clusters=text, source=source, notes=notes)


def split_reply(reply: str) -> tuple[str, str]:
    m = re.search(r"```diff\n(.*?)```", reply, re.S)
    patch = m.group(1) if m else ""
    summary = reply[:m.start()].strip() if m else reply.strip()
    return summary, patch


def call_claude(prompt: str, model: str, timeout: float = 1800, runner=subprocess.run) -> dict:
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--tools", "", "--setting-sources", "",
           "--strict-mcp-config", "--mcp-config", '{"mcpServers": {}}']
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    t0 = time.time()
    out = runner(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, env=env)
    try:
        d = json.loads(out.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise SystemExit(f"no JSON from claude: {out.stderr[-500:]}")
    if d.get("is_error"):
        raise SystemExit(f"claude error: {str(d.get('result'))[:500]}")
    return {"reply": str(d.get("result") or ""), "cost_usd": float(d.get("total_cost_usd") or 0.0),
            "usage": d.get("usage") or {}, "seconds": round(time.time() - t0, 1)}


def analyze(a: argparse.Namespace, runner=subprocess.run) -> Path:
    events = load_events(a.runs)
    out = ROOT / "bench" / "iterations" / f"it{a.iteration}"
    out.mkdir(parents=True, exist_ok=True)
    clusters = build_clusters(events, a.per_cluster)
    (out / "clusters.json").write_text(json.dumps(clusters, ensure_ascii=False, indent=1))
    prompt = build_prompt(clusters, len(a.runs), a.max_clusters, Path(a.notes).read_text() if getattr(a, "notes", None) else "")
    (out / "prompt.md").write_text(prompt)
    print(f"{len(events)} fallback events in {len(clusters)} clusters from {len(a.runs)} run(s) -> {out}")
    for c in clusters[:10]:
        print(f"  {c['count']:4d}  {c['trigger']:<6} {c['node']:<10} {c['map']:<24} {c['mode']:<9} "
              f"agreed {c['agreed_with_jev']}, progress after {c['progress_after']}")
    print(f"prompt: {len(prompt):,} chars (~{len(prompt) // 4:,} tokens) -> {out / 'prompt.md'}")
    meta = {"iteration": a.iteration, "model": a.model, "runs": [str(Path(r).name) for r in a.runs], "events": len(events),
            "clusters": len(clusters), "called": bool(a.call), "cost_usd": 0.0}
    if not a.call:
        print("dry run: Opus was not called. Re-run with --call (an Opus analysis batch needs Bijan's go).")
        (out / "analysis.json").write_text(json.dumps(meta, indent=1))
        return out
    res = call_claude(prompt, a.model, runner=runner)
    summary, patch = split_reply(res["reply"])
    (out / "reply.md").write_text(res["reply"])
    (out / "summary.md").write_text(summary + "\n")
    (out / "proposal.patch").write_text(patch)
    meta.update(cost_usd=res["cost_usd"], usage=res["usage"], seconds=res["seconds"], patch_lines=patch.count("\n"))
    (out / "analysis.json").write_text(json.dumps(meta, indent=1))
    print(f"Opus reply: ${res['cost_usd']:.2f}, {res['seconds']}s; summary.md and proposal.patch ({patch.count(chr(10))} lines) in {out}")
    return out


def apply(a: argparse.Namespace) -> None:
    out = ROOT / "bench" / "iterations" / f"it{a.iteration}"
    patch = out / "proposal.patch"
    if not patch.exists() or not patch.read_text().strip():
        raise SystemExit(f"{patch} is missing or empty (run analyze --call first)")
    git = lambda *args: subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)  # noqa: E731
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch in ("main", "master"):
        raise SystemExit("refusing to apply a proposal on main: check out the branch to build on first")
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise SystemExit("the working tree has uncommitted changes; commit or stash them first")
    new = a.branch or f"jev-iter-{a.iteration + 1}"
    check = git("apply", "--check", str(patch))
    if check.returncode:
        raise SystemExit(f"the patch does not apply cleanly:\n{check.stderr}")
    # the prompt limits edits to the scaffolding files; the code enforces it (renames list both paths)
    paths, toks = set(), iter(git("apply", "--numstat", "-z", str(patch)).stdout.split("\0"))
    for tok in toks:                                      # "added\tdeleted\tpath", or "added\tdeleted\t" old new
        parts = tok.split("\t")
        if len(parts) == 3:
            paths |= {parts[2]} if parts[2] else {next(toks, ""), next(toks, "")}
    paths.discard("")
    outside = sorted(p for p in paths if p not in SCAFFOLDING)
    if not paths or outside:
        raise SystemExit("the patch changes files outside the scaffolding (" + ", ".join(SCAFFOLDING) + "): "
                         + (", ".join(outside) or "no files listed"))
    untracked = set(git("ls-files", "--others", "--exclude-standard").stdout.split("\n"))
    r = git("checkout", "-b", new)
    if r.returncode:
        raise SystemExit(r.stderr)

    def undo(why: str) -> None:
        for f in set(git("ls-files", "--others", "--exclude-standard").stdout.split("\n")) - untracked - {""}:
            (ROOT / f).unlink(missing_ok=True)
        git("checkout", "-f", branch)
        git("branch", "-D", new)
        raise SystemExit(f"{why}; back on {branch}, branch {new} removed")
    r = git("apply", str(patch))
    if r.returncode:
        undo(f"git apply failed:\n{r.stderr}")
    # what really changed (numstat shows only the new name of a rename): tracked edits, deletions and new files
    changed = set(git("diff", "--name-only", "HEAD").stdout.split("\n")) | \
        (set(git("ls-files", "--others", "--exclude-standard").stdout.split("\n")) - untracked)
    outside = sorted(p for p in changed - {""} if p not in SCAFFOLDING)
    if outside:
        undo("the patch changed files outside the scaffolding: " + ", ".join(outside))
    print(f"applied {patch} on new branch {new} (from {branch}); nothing committed. Review with `git diff`, run the tests, "
          f"then rerun the same segment with --iteration {a.iteration + 1}.")


def compare(a: argparse.Namespace) -> None:
    rows = []
    for p in sorted((ROOT / "results").glob("*.json")) + sorted((ROOT / "bench" / "runs").glob("*/result.json")):
        try:
            r = json.loads(p.read_text())
        except ValueError:
            continue
        h = r.get("harness") or {}
        if h.get("track") != "jev" or h.get("iteration") is None:
            continue
        if a.segment and (h.get("segment") or {}).get("name") != a.segment:
            continue
        j = h.get("jev") or {}
        rows.append((h.get("iteration"), h.get("variant"), (h.get("segment") or {}).get("name"), r.get("run_id"), j.get("steps"),
                     j.get("fallbacks"), j.get("fallbacks_per_1k_steps"), (r.get("derived") or {}).get("badges"),
                     h.get("exit_reason"), round((r.get("metrics") or {}).get("real_seconds", 0) / 3600, 2),
                     h.get("cost_usd"), h.get("analysis_cost_usd"), "smoke" if p.name == "result.json" else "result"))
    if not rows:
        print("no jev runs with --iteration found")
        return
    print("iter  variant  segment        steps  fallbacks  /1k    badges  exit           hours  run $   opus $  kind    run")
    for it, v, seg, rid, steps, fb, per, b, ex, hrs, cost, opus, kind in sorted(rows, key=lambda x: (x[2] or "", x[0], x[3])):
        print(f"{it:<5} {v:<8} {str(seg):<14} {str(steps):<6} {str(fb):<10} {str(per):<6} {str(b):<7} {str(ex):<14} "
              f"{hrs:<6} {str(cost):<7} {str(opus):<7} {kind:<7} {rid}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Jev self-improvement: cluster fallbacks, ask Opus, apply on an iteration branch")
    sub = p.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("runs", nargs="+", help="bench/runs/<run_id> directories of jev-assist runs")
    an.add_argument("--iteration", type=int, required=True)
    an.add_argument("--model", default=OPUS)
    an.add_argument("--call", action="store_true", help="actually call the model (costs money; needs Bijan's go)")
    an.add_argument("--per-cluster", type=int, default=4, help="sample events per cluster in the prompt")
    an.add_argument("--max-clusters", type=int, default=12)
    an.add_argument("--notes", help="file describing fixes made since the runs (added to the prompt)")
    ap = sub.add_parser("apply")
    ap.add_argument("--iteration", type=int, required=True)
    ap.add_argument("--branch", help="default: jev-iter-<N+1>")
    cp = sub.add_parser("compare")
    cp.add_argument("--segment")
    a = p.parse_args(argv)
    {"analyze": analyze, "apply": apply, "compare": compare}[a.cmd](a)


if __name__ == "__main__":
    main()
