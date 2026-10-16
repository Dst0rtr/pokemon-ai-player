#!/usr/bin/env python3
"""
Run one benchmark: an agent CLI plays the ROM through the gameboy MCP server until it becomes
Champion or a budget runs out. The CLI is launched in resumable chunks; the server resumes from its
autosave and continues the same metrics session each time.

    venv/bin/python bench/run.py --provider claude --model claude-haiku-4-5-20251001
    venv/bin/python bench/run.py --provider codex --model gpt-5.6-sol --budget-hours 12 --max-calls 20000
    venv/bin/python bench/run.py --provider claude --smoke          # two short chunks, prints a checklist
    venv/bin/python bench/run.py --provider jev [--variant solo|hybrid|scripted|battles] [--mock] [--smoke]

Everything a run produces lives in bench/runs/<run_id>/ (gitignored); the final results/<run_id>.json
is what gets committed, and bench/report.py turns those into RESULTS.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bench.providers import (MODES, claude_transcript_usage, codex_rollout_usage, estimate_cost, make_provider,  # noqa: E402
                             resolve_mode, resolve_model)
from bench.stream import ChunkStats  # noqa: E402
from bench.report import derive, dump_result, write_results_md  # noqa: E402
from bench.jev import read_jsonl, summarize, summarize_fallbacks  # noqa: E402

PYTHON = str(ROOT / "venv" / "bin" / "python") if (ROOT / "venv" / "bin" / "python").exists() else sys.executable
CHAMPION = "champion defeated (Hall of Fame)"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # pragma: no cover
        return "unknown"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_segment(name: str) -> dict:
    segs = _read_json(ROOT / "bench" / "segments.json")
    seg = segs.get(name)
    if not seg or name.startswith("_"):
        raise SystemExit(f"unknown segment '{name}'; choose from {', '.join(k for k in segs if not k.startswith('_'))}")
    seg = dict(seg, name=name)
    if seg.get("state"):
        path = ROOT / seg["state"]
        if not path.exists():
            raise SystemExit(f"segment '{name}' needs the local save state {seg['state']} (gitignored; generate it first)")
        seg["state_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]   # comparability across iterations
    return seg


def analysis_cost(iteration: int) -> float | None:
    """Opus cost of the analysis whose proposal produced this iteration's code (bench/iterations/it<N-1>/analysis.json)."""
    a = _read_json(ROOT / "bench" / "iterations" / f"it{iteration - 1}" / "analysis.json")
    return a.get("cost_usd") if a else None


def run_cost(provider: str, chunks: list[dict], tokens: dict, prices: dict | None) -> tuple[float | None, bool]:
    """(cost_usd, estimated). Claude Code reports a cumulative cost per CLI session, but a chunk that is
    rotated or killed reports none, so the last figure only covers the whole session when the session's
    last working chunk reported one. Otherwise the list-price estimate is used when it is higher (or nothing
    was reported), so a missing last figure never hides the cost of the chunks after it."""
    worked = [c for c in chunks if any((c.get("tokens") or {}).values())]
    costs = [c["cost_usd"] for c in chunks if c.get("cost_usd") is not None]
    if provider == "claude":
        per_session: dict = {}
        for c in chunks:
            per_session.setdefault(c.get("cli_session"), []).append(c)
        last_worked = {c.get("cli_session"): c for c in worked}
        complete = all(c.get("cost_usd") is not None for c in last_worked.values())
        reported = sum(max((c["cost_usd"] for c in cs if c.get("cost_usd") is not None), default=0)
                       for cs in per_session.values())
    else:
        complete, reported = bool(costs), sum(costs)
    est = estimate_cost(tokens, prices) if prices and not (costs and complete) else None
    if est is not None and (not costs or est > reported):
        return round(est, 4), True
    return (round(reported, 4) if costs else None), False


class Run:
    def __init__(self, a: argparse.Namespace):
        self.args = a
        agent_args = [f"--replan-every={a.replan_every}", f"--confidence-threshold={a.confidence_threshold}",
                      f"--fallback-threshold={a.fallback_threshold}", f"--stuck-fail-steps={a.stuck_fail_steps}",
                      f"--fallback-budget-usd={a.fallback_budget_usd}", f"--max-fallbacks={a.max_fallbacks}",
                      f"--map-source={a.map_source}"] + ([f"--atlas={Path(a.atlas).resolve()}"] if a.atlas else [])
        self.segment = load_segment(a.segment) if a.segment else None
        self.provider = make_provider(a.provider, a.model, variant=a.variant, jev_model=a.jev_model, mock=a.mock,
                                      agent_args=agent_args, fallback_model=a.fallback_model)
        self.model = self.provider.model
        if a.resume_run:
            self.dir = Path(a.resume_run).resolve()
            self.run_id = self.dir.name
        else:
            seg = f"_{a.segment}" if a.segment else ""
            it = f"_it{a.iteration}" if a.iteration is not None else ""
            learned = "-learned" if a.provider == "jev" and a.map_source == "learned" else ""
            self.run_id = f"{self.provider.label}{learned}{seg}{it}_{_slug(self.model)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.dir = ROOT / "bench" / "runs" / self.run_id
        self.state_path = self.dir / "harness.json"
        self.state = _read_json(self.state_path) or {
            "run_id": self.run_id, "provider": a.provider, "cli": self.provider.cli, "cli_version": self.provider.version(),
            "model": self.model, "started": datetime.now().isoformat(timespec="seconds"), "ended": None,
            "server_commit": _git_commit(), "budget": {"hours": a.budget_hours, "max_calls": a.max_calls},
            "chunks": [], "active_seconds": 0.0, "paused_seconds": 0.0, "exit_reason": None, "cli_session": None,
        }
        self.state.setdefault("mode", a.mode)
        if self.provider.name == "jev" and a.variant != "battles":
            self.state.setdefault("map_source", {"source": a.map_source, "atlas_seed": a.atlas or None})
        if self.provider.name == "jev" and a.variant == "assist":
            self.state.setdefault("fallback", {"model": a.fallback_model, "budget_usd": a.fallback_budget_usd,
                                               "max_fallbacks": a.max_fallbacks, "threshold": a.fallback_threshold})
        if self.segment:
            self.state.setdefault("segment", self.segment)
        if a.iteration is not None:
            self.state.setdefault("iteration", a.iteration)
            self.state.setdefault("analysis_cost_usd", analysis_cost(a.iteration))
        if self.provider.track != "cli":
            self.state.update(track=self.provider.track, variant=self.provider.variant,
                              display_model=getattr(self.provider, "display_model", self.model), mock=bool(a.mock),
                              jev_model=getattr(self.provider, "jev_model", self.model))
        self.max_seconds = a.budget_hours * 3600
        self.stop_requested = False
        self.proc: subprocess.Popen | None = None

    # ------------------------------------------------------------- setup
    def prepare(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "chunks").mkdir(exist_ok=True)
        (self.dir / "data").mkdir(exist_ok=True)
        rom = self.dir / "rom.gb"
        if not rom.exists():
            shutil.copy(self.args.rom, rom)
            if self.segment and self.segment.get("state"):     # fixed start state: the server resumes from it
                saves = self.dir / "data" / "saves" / "rom"
                saves.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / self.segment["state"], saves / "autosave.state")
        prompt = ROOT / "bench" / "PROMPT.md"
        cont = ROOT / "bench" / "CONTINUE.md"
        suffix = self.provider.prompt_suffix()
        (self.dir / "prompt.md").write_text(prompt.read_text() + suffix)
        (self.dir / "continue.md").write_text(cont.read_text() + suffix)
        self.state["prompt_sha256"] = hashlib.sha256((self.dir / "prompt.md").read_bytes()).hexdigest()[:16]
        self.provider.prepare(self.dir, self.server_cmd())
        self.save()

    def server_cmd(self) -> list[str]:
        return [PYTHON, str(ROOT / "server.py"), "--rom", str(self.dir / "rom.gb"), "--data-dir", str(self.dir / "data"),
                "--ai-model", self.model, "--session-id", self.run_id, "--resume", "--autosave-every", "5",
                "--no-screenshot-files", "--max-tool-calls", str(self.args.max_calls),
                "--max-real-seconds", str(int(self.max_seconds)), "--log-file", str(self.dir / "data" / "server.log")
                ] + self.provider.server_args(self.dir)

    def save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=1))

    def log(self, *a) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] " + " ".join(str(x) for x in a)
        print(line, flush=True)
        with open(self.dir / "harness.log", "a") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------- metrics from the server
    def checkpoint(self) -> dict:
        m = self.dir / "data" / "metrics"
        final = m / f"{self.run_id}.json"
        return _read_json(final) if final.exists() else _read_json(m / f"{self.run_id}_checkpoint.json")

    def stop_reason(self) -> str | None:
        cp = self.checkpoint()
        names = [x.get("name") for x in cp.get("milestones", [])]
        if CHAMPION in names:
            return "champion"
        if self.segment and self.segment.get("goal") and any(str(n).startswith(self.segment["goal"]) for n in names
                                                               if n not in self.segment.get("initial_milestones", [])):
            return "segment_goal"
        if cp.get("tool_calls_total", 0) >= self.args.max_calls:
            return "budget_calls"
        if self.state["active_seconds"] >= self.max_seconds or cp.get("real_seconds", 0) >= self.max_seconds:
            return "budget_time"
        if self.args.max_chunks and len(self.state["chunks"]) >= self.args.max_chunks:
            return "max_chunks"
        return None

    # ------------------------------------------------------------- one chunk
    def run_chunk(self) -> dict:
        n = len(self.state["chunks"]) + 1
        first = self.state["cli_session"] is None                 # no CLI session to resume: start a fresh one
        fresh_continue = first and bool(self.state["chunks"])     # ...but the game is already in progress
        session = self.state["cli_session"] or (str(uuid.uuid4()) if self.provider.parser == "claude" else None)
        prompt_file = self.dir / ("continue.md" if self.state["chunks"] else "prompt.md")
        cmd = self.provider.command(self.dir, prompt_file, session, first)
        self._resuming = not first
        out_path, err_path = self.dir / "chunks" / f"{n:03d}.jsonl", self.dir / "chunks" / f"{n:03d}.stderr"
        (self.dir / "chunks" / f"{n:03d}.cmd").write_text(" ".join(cmd) + "\n")
        stats = ChunkStats(self.provider.parser)
        started = time.time()
        self.log(f"chunk {n}: {'fresh session (continue)' if fresh_continue else 'start' if first else 'resume ' + str(session)} "
                 f"({self.provider.cli} {self.model})")
        with open(out_path, "wb") as out, open(err_path, "wb") as err, open(prompt_file, "rb") as pin:
            self.proc = subprocess.Popen(cmd, stdin=pin, stdout=out, stderr=err, cwd=self.dir, env=self.provider.env(self.dir))
            exit_reason = self._watch(out_path, stats, started)
            code = self.proc.returncode
        self.proc = None
        self._kill_orphan_server()
        seconds = time.time() - started
        cp = self.checkpoint()
        if stats.session_id and first:
            self.state["cli_session"] = stats.session_id
        elif first and session:
            self.state["cli_session"] = session
        rec = {"n": n, "started": datetime.fromtimestamp(started).isoformat(timespec="seconds"), "seconds": round(seconds, 1),
               "exit_code": code, "exit_reason": exit_reason, "cli_session": stats.session_id or session, "fresh": first,
               "tool_calls_seen": stats.tool_calls, "tokens": stats.tokens, "cost_usd": stats.cost_usd,
               "turns": stats.turns, "errors": stats.errors[:5], "rate_limited": stats.rate_limited,
               "mcp_servers": stats.mcp_servers, "server_tool_calls_total": cp.get("tool_calls_total"),
               "milestones_total": len(cp.get("milestones", []))}
        self.state["chunks"].append(rec)
        if stats.tool_calls or exit_reason in ("rotate", "budget_time", "budget_calls", "champion", "manual"):
            self.state["active_seconds"] += seconds           # a chunk that never played is not active time
        if not first and stats.tool_calls == 0 and exit_reason in ("stall", "resume_failed", "cli_error", "exited"):
            # The CLI could not continue its own session (e.g. Codex's remote compaction of a huge thread
            # failing): next time start a fresh session with the continue prompt; the server holds the game.
            self.log(f"resume of {session} produced no tool calls: switching to a fresh CLI session")
            self.state["cli_session"] = None
            self.state["fresh_sessions"] = self.state.get("fresh_sessions", 0) + 1
        self.save()
        self.log(f"chunk {n} done: {exit_reason}, exit {code}, {seconds:.0f}s, {stats.tool_calls} tool calls seen, "
                 f"server total {cp.get('tool_calls_total')}, tokens {stats.tokens}, cost {stats.cost_usd}"
                 + (f", errors: {stats.errors[:2]}" if stats.errors else ""))
        return rec

    def _watch(self, out_path: Path, stats: ChunkStats, started: float) -> str:
        assert self.proc is not None
        pos = 0
        reason = "exited"
        last_cp_mtime = 0.0
        while True:
            time.sleep(self.args.poll_seconds)
            with open(out_path, "rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos += len(chunk)
            for line in chunk.decode("utf-8", "replace").splitlines():
                stats.feed_line(line)
            cp_path = self.dir / "data" / "metrics" / f"{self.run_id}_checkpoint.json"
            try:
                mt = cp_path.stat().st_mtime
                if mt > last_cp_mtime:
                    last_cp_mtime = mt
                    stats.last_activity = max(stats.last_activity, mt)
            except OSError:
                pass
            if self.proc.poll() is not None:
                if self.provider.parser == "jev" and stats.result_text == "stuck":
                    return "stuck"                       # the Jev agent gave up: no progress for --stuck-fail-steps
                return "rate_limited" if stats.rate_limited else ("cli_error" if stats.errors and not stats.tool_calls else "exited")
            elapsed = time.time() - started
            if self.stop_requested:
                reason = "manual"
            elif self.stop_reason() is not None:
                reason = self.stop_reason()
            elif self.state["active_seconds"] + elapsed >= self.max_seconds:
                reason = "budget_time"
            elif elapsed >= self.args.chunk_minutes * 60:
                reason = "rotate"
            elif time.time() - stats.last_activity >= self.args.stall_minutes * 60:
                reason = "stall"
            elif getattr(self, "_resuming", False) and stats.tool_calls == 0 and elapsed >= self.args.resume_timeout_minutes * 60:
                reason = "resume_failed"
            else:
                continue
            self._terminate()
            return reason

    def _terminate(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        self.proc.send_signal(signal.SIGTERM)
        for _ in range(int(self.args.grace_seconds * 2)):
            if self.proc.poll() is not None:
                return
            time.sleep(0.5)
        self.proc.kill()
        self.proc.wait()

    def _kill_orphan_server(self) -> None:
        """A killed CLI can leave its MCP server behind; it must be gone before the next chunk resumes."""
        pattern = f"server.py --rom {self.dir / 'rom.gb'}"
        for _ in range(60):
            out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
            if not out:
                return
            for pid in out:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except OSError:
                    pass
            time.sleep(1)

    # ------------------------------------------------------------- main loop
    def loop(self) -> str:
        backoff = 5
        fails = 0
        while True:
            reason = self.stop_reason()
            if reason:
                return reason
            if self.stop_requested:
                return "manual"
            rec = self.run_chunk()
            if rec["exit_reason"] in ("champion", "budget_calls", "budget_time", "manual", "max_chunks", "segment_goal", "stuck"):
                return rec["exit_reason"]
            if rec["exit_reason"] == "rate_limited":
                self.log(f"rate limited: pausing {backoff} min")
                self._pause(backoff * 60)
                backoff = min(backoff * 2, 60)
                continue
            backoff = 5
            if rec["tool_calls_seen"] == 0 and rec["exit_reason"] in ("cli_error", "stall", "resume_failed", "exited"):
                fails += 1
                if fails >= 6:
                    return "cli_error"
                self._pause(30 if fails < 3 else 300)
                continue
            fails = 0
            if rec["exit_reason"] == "stall":
                self.log("stall: restarting the CLI")
            time.sleep(2)

    def _pause(self, seconds: float) -> None:
        self.state["paused_seconds"] += seconds
        self.save()
        end = time.time() + seconds
        while time.time() < end and not self.stop_requested:
            time.sleep(1)

    def finish(self, reason: str) -> Path:
        self.state["exit_reason"] = reason
        self.state["ended"] = datetime.now().isoformat(timespec="seconds")
        tok = {k: sum(int((c.get("tokens") or {}).get(k, 0)) for c in self.state["chunks"]) for k in ("input", "cached_input", "cache_write", "output", "reasoning")}
        if self.provider.parser == "codex":                 # the stream loses usage for rotated chunks: use the rollouts
            recovered = codex_rollout_usage([c.get("cli_session") for c in self.state["chunks"]])
            if recovered and sum(recovered.values()) > sum(tok.values()):
                tok = recovered
                self.state["tokens_source"] = "codex session rollouts"
        if self.provider.parser == "claude":                # the stream undercounts output: use the transcripts
            recovered = claude_transcript_usage([c.get("cli_session") for c in self.state["chunks"]])
            if recovered and sum(recovered.values()) > sum(tok.values()):
                tok = recovered
                self.state["tokens_source"] = "claude session transcripts"
        self.state["tokens"] = tok
        self.state["cost_usd"], self.state["cost_estimated"] = run_cost(
            self.provider.parser, self.state["chunks"], tok, _read_json(ROOT / "bench" / "prices.json").get(self.model))
        if self.provider.track == "jev":
            self.state["jev"] = self.jev_summary()
            j = self.state["jev"]
            if self.provider.variant == "battles":       # the CLI's cost does not include the server-side Jev calls
                self.state["cost_usd"] = round((self.state["cost_usd"] or 0) + j["jev_cost_usd"], 4)
            else:                                        # the decision/objective logs survive a killed chunk; the stream may not
                logged = round(j["jev_cost_usd"] + j["planner_cost_usd"], 4)
                if self.state["cost_usd"] is None or logged > self.state["cost_usd"]:
                    self.state["cost_usd"], self.state["cost_estimated"] = logged, False
        for c in self.state["chunks"][1:]:                   # keep the published file small: per-chunk essentials only
            c.pop("mcp_servers", None)
            if not c.get("errors"):
                c.pop("errors", None)
        self.state["wall_seconds"] = round((datetime.fromisoformat(self.state["ended"]) - datetime.fromisoformat(self.state["started"])).total_seconds(), 1)
        self.save()
        metrics = self.checkpoint()
        result = {"schema": 1, "run_id": self.run_id, "harness": {k: v for k, v in self.state.items() if k != "run_id"},
                  "metrics": metrics, "derived": derive(metrics, self.state)}
        if self.args.smoke:                       # a smoke run is not a benchmark result
            out = self.dir / "result.json"
        else:
            out = ROOT / "results" / f"{self.run_id}.json"
            out.parent.mkdir(exist_ok=True)
        out.write_text(dump_result(result))
        self.log(f"results written to {out}; exit reason {reason}")
        if not self.args.smoke:
            write_results_md(ROOT / "results", ROOT / "RESULTS.md")
        return out

    def jev_summary(self) -> dict:
        objectives = read_jsonl(self.dir / "data" / "jev_objectives.jsonl")
        out = summarize(read_jsonl(self.dir / "data" / "jev_decisions.jsonl"),
                        [o for o in objectives if o.get("source") == "planner"])
        out["objective_changes"] = len(objectives)
        agent = _read_json(self.dir / "jev_agent.json")
        fb = read_jsonl(self.dir / "fallbacks.jsonl")
        pending = agent.get("pending_fallbacks") or []
        if pending:                                      # outcomes not yet due when the run ended: record them as incomplete
            with open(self.dir / "fallbacks.jsonl", "a", encoding="utf-8") as f:
                for ev in pending:
                    ev.pop("sig_before", None)
                    ev["outcome_after"] = {"complete": False, "steps": (agent.get("step") or 0) - ev["step"]}
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            agent["pending_fallbacks"] = []
            (self.dir / "jev_agent.json").write_text(json.dumps(agent, ensure_ascii=False))
            fb = read_jsonl(self.dir / "fallbacks.jsonl")
        if self.provider.variant == "assist" or fb:
            out.update(summarize_fallbacks(fb, agent.get("step")))
            out["planner_cost_usd"] = round(out.get("planner_cost_usd", 0) + out["fallback_cost_usd"], 6)
        out["jev_marked_done"] = sum(1 for o in objectives if o.get("source") == "jev")
        agent = _read_json(self.dir / "jev_agent.json")
        if agent:
            out["steps"] = agent.get("step")
            out["final_objective"] = agent.get("last_objective") or agent.get("objective")
        return out

    def smoke_report_jev(self) -> None:
        chunks = self.state["chunks"]
        cp = self.checkpoint()
        j = self.state.get("jev") or self.jev_summary()
        c1 = chunks[0] if chunks else {}
        c2 = chunks[1] if len(chunks) > 1 else {}
        ok = lambda b: "x" if b else " "  # noqa: E731
        print(f"\nSMOKE CHECKLIST (jev-{self.provider.variant}{', MOCK Jev' if self.args.mock else ''})")
        print(f"  [{ok(c1.get('tool_calls_seen'))}] agent connected to the server and played in chunk 1 ({c1.get('tool_calls_seen')} tool calls)")
        print(f"  [{ok(j['jev_calls'])}] Jev answered: {j['jev_calls']} calls, models {j['models']}, latency p50 {j['latency_ms']['p50']} ms "
              f"p95 {j['latency_ms']['p95']} ms, {j['input_tokens']} input tokens, ${j['jev_cost_usd']:.4f}")
        print(f"  [{ok(j['scored'])}] decisions labelled for calibration: {j['scored']} (accuracy {j['accuracy']}, ECE {j['ece']})")
        if self.provider.variant == "hybrid":
            print(f"  [{ok(j['planner_calls'] and not j['planner_errors'])}] planner: {j['planner_calls']} calls, "
                  f"{j['planner_errors']} errors, ${j['planner_cost_usd']:.4f}")
        if self.provider.variant == "assist":
            print(f"  [{ok((self.dir / 'fallbacks.jsonl').exists())}] fallback events: {j.get('fallbacks')} "
                  f"({j.get('fallbacks_per_1k_steps')} per 1k steps, by trigger {j.get('by_trigger')}, errors {j.get('fallback_errors')}, "
                  f"${j.get('fallback_cost_usd', 0):.4f}) -> {self.dir / 'fallbacks.jsonl'}")
        if self.provider.variant == "solo":
            print(f"  [{ok(not j['planner_calls'])}] no LLM called (planner calls {j['planner_calls']}); objective changes {j['objective_changes']}")
        if self.provider.variant == "battles":
            print(f"  [{ok(c1.get('tool_calls_seen'))}] Claude CLI played; Jev battle turns {j['jev_calls']} (0 is possible if no battle came up)")
        print(f"  [{ok(self.state.get('cost_usd') is not None)}] run cost recorded: {self.state.get('cost_usd')}")
        print(f"  [{ok(c2 and c2.get('tool_calls_seen'))}] chunk 2 continued playing ({c2.get('tool_calls_seen')} tool calls)")
        print(f"  [{ok(c2 and cp.get('chunks', 1) >= 2)}] server metrics session continued across chunks (chunks={cp.get('chunks')})")
        print(f"  [{ok(cp.get('tool_calls_total'))}] server checkpoint: {cp.get('tool_calls_total')} calls, milestones "
              f"{[m.get('name') for m in cp.get('milestones', []) if not str(m.get('name')).startswith('loaded state')]}")
        errs = [e for c in chunks for e in c.get("errors", [])]
        print(f"  [{ok(not errs)}] no errors" + (f": {errs[:3]}" if errs else ""))
        print("  see", self.dir, "(data/jev_decisions.jsonl, data/jev_objectives.jsonl, chunks/)\n")

    def smoke_report(self) -> None:
        if self.provider.track == "jev" and self.provider.parser == "jev":
            return self.smoke_report_jev()
        chunks = self.state["chunks"]
        cp = self.checkpoint()
        print("\nSMOKE CHECKLIST")
        c1 = chunks[0] if chunks else {}
        c2 = chunks[1] if len(chunks) > 1 else {}
        srv = c1.get("mcp_servers") or []
        print(f"  [{'x' if (not srv or any(s.get('status') == 'connected' for s in srv)) and c1.get('tool_calls_seen') else ' '}] gameboy MCP server connected and used in chunk 1 (servers: {srv or 'n/a'}, calls {c1.get('tool_calls_seen')})")
        print(f"  [{'x' if any(v for v in (c1.get('tokens') or {}).values()) else ' '}] token usage reported: {c1.get('tokens')} cost {c1.get('cost_usd')}")
        print(f"  [{'x' if cp.get('tool_calls_total') else ' '}] server metrics checkpoint written: {cp.get('tool_calls_total')} calls, {len(cp.get('milestones', []))} milestones")
        print(f"  [{'x' if c2 and c2.get('cli_session') == c1.get('cli_session') and c2.get('tool_calls_seen') else ' '}] chunk 2 resumed the CLI session and kept playing (session {c2.get('cli_session')}, calls {c2.get('tool_calls_seen')})")
        print(f"  [{'x' if c2 and (cp.get('chunks', 1) >= 2) else ' '}] server metrics session continued across chunks (chunks={cp.get('chunks')})")
        errs = [e for c in chunks for e in c.get("errors", [])]
        print(f"  [{'x' if not errs else ' '}] no CLI errors" + (f": {errs[:3]}" if errs else ""))
        print("  see", self.dir / "chunks", "for the raw streams\n")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Game Boy MCP benchmark runner")
    p.add_argument("--mode", choices=list(MODES), default="",
                   help="what decides each action: jev-solo (Jev, no LLM), jev-assist (Jev + LLM fallback when unsure/stuck), "
                        "jev-hybrid (Jev actions, LLM objectives), jev-scripted (Jev actions on a fixed route list), "
                        "jev-battles (LLM CLI plays, Jev decides battle turns), llm (an agent CLI alone: --provider claude|codex)")
    p.add_argument("--provider", choices=["claude", "codex", "jev"], default="",
                   help="claude / codex for --mode llm; jev is implied by the jev-* modes")
    p.add_argument("--model", default="", help="CLI model (haiku/sonnet/opus/fable or a full id); for jev: the planner "
                                               "(hybrid) or CLI (battles) model")
    p.add_argument("--fallback-model", default="haiku", help="jev-assist: model for uncertain/stuck decisions: "
                                                             "haiku, sonnet, opus or a full Claude model id")
    p.add_argument("--fallback-budget-usd", type=float, default=25.0,
                   help="jev-assist: stop calling the fallback model after this much spend (0 = no cap); Jev plays on alone")
    p.add_argument("--max-fallbacks", type=int, default=0, help="jev-assist: at most this many fallbacks (0 = no cap)")
    p.add_argument("--map-source", choices=["rom", "learned"], default="rom",
                   help="jev: where map knowledge comes from: rom (world/warp graph from the ROM map tables; the benchmark "
                        "default) or learned (no ROM tables: Jev builds an atlas while playing, data/jev_atlas.json)")
    p.add_argument("--atlas", default="", help="jev --map-source learned: start from an earlier run's data/jev_atlas.json")
    p.add_argument("--variant", default="solo", choices=["solo", "assist", "hybrid", "scripted", "battles"],
                   help="jev: solo = Jev + code only, no LLM, stuck = fail (final exam); assist = solo + Haiku fallback per "
                        "uncertain/stuck decision, logged to fallbacks.jsonl; hybrid = Haiku planner; scripted = short route; "
                        "battles = Haiku run, Jev battles")
    p.add_argument("--fallback-threshold", type=float, default=0.3, help="jev-assist: fall back below this Jev confidence")
    p.add_argument("--stuck-fail-steps", type=int, default=2000, help="jev solo/assist: steps without progress that end the run as stuck (solo: a fail)")
    p.add_argument("--segment", help="start from a fixed save state and stop at its goal (bench/segments.json)")
    p.add_argument("--iteration", type=int, help="self-improvement iteration number (recorded; RESULTS.md tracks the trend)")
    p.add_argument("--jev-model", default="jev-latest")
    p.add_argument("--mock", action="store_true", help="jev: offline MockJev/MockPlanner (no network); never a benchmark result")
    p.add_argument("--replan-every", type=int, default=40, help="jev-hybrid: planner at least every N steps")
    p.add_argument("--confidence-threshold", type=float, default=0.3, help="jev-hybrid: replan below this Jev confidence")
    p.add_argument("--rom", default=str(ROOT / "Pokemon-Red_Version.gb"))
    p.add_argument("--budget-hours", type=float, default=12.0)
    p.add_argument("--max-calls", type=int, default=20000)
    p.add_argument("--chunk-minutes", type=float, default=60)
    p.add_argument("--stall-minutes", type=float, default=15)
    p.add_argument("--resume-timeout-minutes", type=float, default=5,
                   help="a resumed CLI session with no tool call after this long is abandoned for a fresh session")
    p.add_argument("--max-chunks", type=int, default=0, help="stop after this many chunks (0 = unlimited)")
    p.add_argument("--poll-seconds", type=float, default=5)
    p.add_argument("--grace-seconds", type=float, default=60)
    p.add_argument("--resume-run", help="continue an interrupted run directory")
    p.add_argument("--smoke", action="store_true", help="two 4-minute chunks with tiny budgets; prints a checklist")
    a = p.parse_args(argv)
    a.provider, a.variant, a.mode = resolve_mode(a.mode, a.provider, a.variant)
    a.model, a.fallback_model = resolve_model(a.model), resolve_model(a.fallback_model)
    if a.provider == "jev" and not a.mock and not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not set (Jev needs it); use --mock for an offline run")
    if a.provider == "jev" and a.mock and not a.smoke and not a.resume_run:
        a.smoke = True                                    # a mock run is a harness check, never a published result
    if a.smoke:
        a.chunk_minutes, a.max_chunks, a.budget_hours, a.max_calls, a.stall_minutes = 4, 2, 0.5, 400, 5
        if a.provider == "jev" and a.variant != "battles":
            a.chunk_minutes, a.max_calls, a.stall_minutes = (0.4 if a.mock else 2), 3000, 2
    run = Run(a)
    run.prepare()

    def _sigint(*_):
        run.log("interrupt: finishing after this chunk")
        run.stop_requested = True
        run._terminate()
    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)
    reason = run.loop()
    run.finish(reason)
    if a.smoke:
        run.smoke_report()


if __name__ == "__main__":
    main()
