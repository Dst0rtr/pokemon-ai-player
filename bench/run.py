#!/usr/bin/env python3
"""
Run one benchmark: an agent CLI plays the ROM through the gameboy MCP server until it becomes
Champion or a budget runs out. The CLI is launched in resumable chunks; the server resumes from its
autosave and continues the same metrics session each time.

    venv/bin/python bench/run.py --provider claude --model claude-haiku-4-5-20251001
    venv/bin/python bench/run.py --provider codex --model gpt-5.6-sol --budget-hours 12 --max-calls 20000
    venv/bin/python bench/run.py --provider claude --smoke          # two short chunks, prints a checklist

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
from bench.providers import make_provider  # noqa: E402
from bench.stream import ChunkStats  # noqa: E402
from bench.report import derive, dump_result, write_results_md  # noqa: E402

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


class Run:
    def __init__(self, a: argparse.Namespace):
        self.args = a
        self.provider = make_provider(a.provider, a.model)
        self.model = self.provider.model
        if a.resume_run:
            self.dir = Path(a.resume_run).resolve()
            self.run_id = self.dir.name
        else:
            self.run_id = f"{a.provider}_{_slug(self.model)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.dir = ROOT / "bench" / "runs" / self.run_id
        self.state_path = self.dir / "harness.json"
        self.state = _read_json(self.state_path) or {
            "run_id": self.run_id, "provider": a.provider, "cli": self.provider.cli, "cli_version": self.provider.version(),
            "model": self.model, "started": datetime.now().isoformat(timespec="seconds"), "ended": None,
            "server_commit": _git_commit(), "budget": {"hours": a.budget_hours, "max_calls": a.max_calls},
            "chunks": [], "active_seconds": 0.0, "paused_seconds": 0.0, "exit_reason": None, "cli_session": None,
        }
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
        prompt = ROOT / "bench" / "PROMPT.md"
        cont = ROOT / "bench" / "CONTINUE.md"
        shutil.copy(prompt, self.dir / "prompt.md")
        shutil.copy(cont, self.dir / "continue.md")
        self.state["prompt_sha256"] = hashlib.sha256(prompt.read_bytes()).hexdigest()[:16]
        self.provider.prepare(self.dir, self.server_cmd())
        self.save()

    def server_cmd(self) -> list[str]:
        return [PYTHON, str(ROOT / "server.py"), "--rom", str(self.dir / "rom.gb"), "--data-dir", str(self.dir / "data"),
                "--ai-model", self.model, "--session-id", self.run_id, "--resume", "--autosave-every", "5",
                "--no-screenshot-files", "--max-tool-calls", str(self.args.max_calls),
                "--max-real-seconds", str(int(self.max_seconds)), "--log-file", str(self.dir / "data" / "server.log")]

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
        first = self.state["cli_session"] is None
        session = self.state["cli_session"] or (str(uuid.uuid4()) if self.provider.name == "claude" else None)
        prompt_file = self.dir / ("prompt.md" if first else "continue.md")
        cmd = self.provider.command(self.dir, prompt_file, session, first)
        out_path, err_path = self.dir / "chunks" / f"{n:03d}.jsonl", self.dir / "chunks" / f"{n:03d}.stderr"
        (self.dir / "chunks" / f"{n:03d}.cmd").write_text(" ".join(cmd) + "\n")
        stats = ChunkStats(self.provider.name)
        started = time.time()
        self.log(f"chunk {n}: {'start' if first else 'resume ' + str(session)} ({self.provider.cli} {self.model})")
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
               "exit_code": code, "exit_reason": exit_reason, "cli_session": stats.session_id or session,
               "tool_calls_seen": stats.tool_calls, "tokens": stats.tokens, "cost_usd": stats.cost_usd,
               "turns": stats.turns, "errors": stats.errors[:5], "rate_limited": stats.rate_limited,
               "mcp_servers": stats.mcp_servers, "server_tool_calls_total": cp.get("tool_calls_total"),
               "milestones_total": len(cp.get("milestones", []))}
        self.state["chunks"].append(rec)
        self.state["active_seconds"] += seconds
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
            if rec["exit_reason"] in ("champion", "budget_calls", "budget_time", "manual", "max_chunks"):
                return rec["exit_reason"]
            if rec["exit_reason"] == "rate_limited":
                self.log(f"rate limited: pausing {backoff} min")
                self._pause(backoff * 60)
                backoff = min(backoff * 2, 60)
                continue
            backoff = 5
            if rec["exit_code"] not in (0, None, -15) and rec["tool_calls_seen"] == 0:
                fails += 1
                if fails >= 3:
                    return "cli_error"
                self._pause(30)
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
        costs = [c["cost_usd"] for c in self.state["chunks"] if c.get("cost_usd") is not None]
        self.state["tokens"] = tok
        # Claude Code reports total_cost_usd for the whole (resumed) session, so the last figure is the total.
        self.state["cost_usd"] = round(max(costs) if self.provider.name == "claude" else sum(costs), 4) if costs else None
        self.state["cost_estimated"] = False
        if not costs:                                        # the CLI reported no cost at all: estimate from list prices
            prices = _read_json(ROOT / "bench" / "prices.json").get(self.model)
            if prices:
                est = sum(tok.get(k, 0) * prices.get(k, 0) / 1e6 for k in ("input", "cached_input", "cache_write", "output"))
                self.state["cost_usd"] = round(est, 4)
                self.state["cost_estimated"] = True
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

    def smoke_report(self) -> None:
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
    p.add_argument("--provider", required=True, choices=["claude", "codex"])
    p.add_argument("--model", default="")
    p.add_argument("--rom", default=str(ROOT / "Pokemon-Red_Version.gb"))
    p.add_argument("--budget-hours", type=float, default=12.0)
    p.add_argument("--max-calls", type=int, default=20000)
    p.add_argument("--chunk-minutes", type=float, default=60)
    p.add_argument("--stall-minutes", type=float, default=15)
    p.add_argument("--max-chunks", type=int, default=0, help="stop after this many chunks (0 = unlimited)")
    p.add_argument("--poll-seconds", type=float, default=5)
    p.add_argument("--grace-seconds", type=float, default=60)
    p.add_argument("--resume-run", help="continue an interrupted run directory")
    p.add_argument("--smoke", action="store_true", help="two 4-minute chunks with tiny budgets; prints a checklist")
    a = p.parse_args(argv)
    if a.smoke:
        a.chunk_minutes, a.max_chunks, a.budget_hours, a.max_calls, a.stall_minutes = 4, 2, 0.5, 400, 5
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
