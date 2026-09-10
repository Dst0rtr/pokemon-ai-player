#!/usr/bin/env python3
"""
Compare benchmark runs written by metrics.py.

Usage: python compare_benchmarks.py [--dir metrics]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(metrics_dir: Path) -> list[dict]:
    runs = []
    for f in sorted(metrics_dir.glob("*.json")):
        if f.name.endswith("_checkpoint.json") and (metrics_dir / f.name.replace("_checkpoint", "")).exists():
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if "session_id" in d and "milestones" in d:
            d["_file"] = f.name
            runs.append(d)
    return runs


def _progress(run: dict) -> str:
    fs = run.get("final_state", {})
    for key in ("badges", "score", "level", "world"):
        if key in fs:
            extra = f" dex {fs['dex_owned']}" if "dex_owned" in fs else ""
            return f"{key} {fs[key]}{extra}"
    return f"{len(run['milestones'])} milestones"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="metrics")
    args = ap.parse_args()
    runs = load(Path(args.dir))
    if not runs:
        print("no runs found in", args.dir)
        return

    print(f"{'session':<34} {'model':<18} {'profile':<14} {'real s':>7} {'calls':>6} {'imgs':>5} {'progress'}")
    for r in runs:
        tag = "" if r.get("ended") else " (in progress)"
        print(f"{r['session_id']:<34} {r['ai_model']:<18} {r.get('profile', ''):<14} {r['real_seconds']:>7.0f} "
              f"{r['tool_calls_total']:>6} {r['images_sent']:>5} {_progress(r)}{tag}")

    # time-to-milestone: tool calls needed to reach milestones shared by >= 2 runs
    reached: dict[str, dict[str, int]] = defaultdict(dict)
    for r in runs:
        for m in r["milestones"]:
            reached[m["name"]].setdefault(r["session_id"], m["tool_calls"])
    shared = {k: v for k, v in reached.items() if len(v) >= 2}
    if shared:
        print("\ntool calls to reach shared milestones (lower is better):")
        for name, by_run in shared.items():
            cells = ", ".join(f"{sid.split('_')[0]}={calls}" for sid, calls in sorted(by_run.items(), key=lambda kv: kv[1]))
            print(f"  {name:<36} {cells}")

    # per-model averages
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_model[r["ai_model"]].append(r)
    if len(by_model) > 1:
        print("\nper-model averages:")
        for model, rs in by_model.items():
            avg = lambda k: sum(x[k] for x in rs) / len(rs)  # noqa: E731
            print(f"  {model:<18} runs {len(rs)}  real {avg('real_seconds'):.0f}s  calls {avg('tool_calls_total'):.0f}  "
                  f"images {avg('images_sent'):.0f}  milestones {sum(len(x['milestones']) for x in rs) / len(rs):.1f}")


if __name__ == "__main__":
    main()
