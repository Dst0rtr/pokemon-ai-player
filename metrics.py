"""
Benchmark metrics for an AI playthrough of any Game Boy game.

Tracks real time, emulated frames, tool-call and token-ish counts, and a list
of timestamped milestones. Game profiles supply the milestones (badges,
captures, levels, score...) and a progress snapshot; the tracker is generic.

A session can span several server launches: `resume_from()` reloads a
checkpoint so real time, tool calls and milestones keep accumulating, and
optional budgets (tool calls / real seconds) let a harness end a run cleanly.

All logging goes to stderr: stdout is the MCP transport.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("gameboy.metrics")

# List-valued snapshot keys worth keeping per milestone (the team at each badge etc.); other lists are dropped.
_SNAPSHOT_LISTS = {"party", "team"}
MAX_NOTES = 30


@dataclass
class Milestone:
    name: str
    frame: int
    elapsed_s: float
    tool_calls: int
    at: str
    snapshot: dict[str, Any] = field(default_factory=dict)


class MetricsTracker:
    def __init__(self, ai_model: str, rom_name: str, out_dir: Path, session_id: Optional[str] = None,
                 max_tool_calls: int = 0, max_real_seconds: float = 0):
        self.ai_model = ai_model
        self.rom_name = rom_name
        self.out_dir = Path(out_dir)
        self.profile_name = "generic"
        self.max_tool_calls = int(max_tool_calls or 0)
        self.max_real_seconds = float(max_real_seconds or 0)
        self.last_snapshot: Optional[dict[str, Any]] = None
        self._fresh(session_id)

    def _fresh(self, session_id: Optional[str] = None) -> None:
        self.session_id = session_id or f"{_slug(self.ai_model)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = time.time()          # start of this chunk
        self.first_start = self.start_time     # start of the whole session
        self.prior_seconds = 0.0               # real seconds spent in earlier chunks
        self.end_time: Optional[float] = None
        self.frames = 0
        self.tool_calls: dict[str, int] = {}
        self.images_sent = 0
        self.text_chars_sent = 0
        self.milestones: list[Milestone] = []
        self.notes: list[str] = []
        self.chunks = 1
        self.loads = 0
        self.finalized = False

    # -- called by the server ---------------------------------------------- #
    def set_profile(self, name: str) -> None:
        self.profile_name = name

    def restart(self, ai_model: Optional[str] = None) -> str:
        if ai_model:
            self.ai_model = ai_model
        self._fresh()
        return f"metrics session {self.session_id} started for model '{self.ai_model}'"

    def resume_from(self, path: Path) -> bool:
        """Continue a session from a checkpoint / final report written earlier."""
        try:
            d = json.loads(Path(path).read_text())
        except (OSError, ValueError) as e:
            log.warning("cannot resume metrics from %s: %s", path, e)
            return False
        self.session_id = d.get("session_id", self.session_id)
        self.profile_name = d.get("profile", self.profile_name)
        try:
            self.first_start = datetime.fromisoformat(d["started"]).timestamp()
        except (KeyError, ValueError, TypeError):
            pass
        self.prior_seconds = float(d.get("real_seconds", 0) or 0)
        self.start_time = time.time()
        self.end_time = None
        self.frames = int(d.get("frames", 0) or 0)
        self.tool_calls = {k: int(v) for k, v in (d.get("tool_calls") or {}).items()}
        self.images_sent = int(d.get("images_sent", 0) or 0)
        self.text_chars_sent = int(d.get("text_chars_sent", 0) or 0)
        self.milestones = [
            Milestone(name=m.get("name", "?"), frame=int(m.get("frame", 0) or 0), elapsed_s=float(m.get("elapsed_s", 0) or 0),
                      tool_calls=int(m.get("tool_calls", 0) or 0), at=m.get("at", ""), snapshot=m.get("snapshot") or {})
            for m in d.get("milestones") or []
        ]
        self.notes = list(d.get("notes") or [])[-MAX_NOTES:]
        self.chunks = int(d.get("chunks", 1) or 1) + 1
        self.loads = int(d.get("loads", 0) or 0)
        self.finalized = False
        log.info("metrics session %s resumed (chunk %d, %d calls so far)", self.session_id, self.chunks, sum(self.tool_calls.values()))
        return True

    def record_call(self, tool: str, text_len: int, image: bool) -> None:
        self.tool_calls[tool] = self.tool_calls.get(tool, 0) + 1
        self.text_chars_sent += text_len
        if image:
            self.images_sent += 1

    def observe(self, snapshot: dict[str, Any], frames: int, milestones: list[str]) -> list[str]:
        self.frames = frames
        for name in milestones:
            self._add(name, snapshot)
        self.last_snapshot = snapshot
        return milestones

    def mark(self, name: str) -> str:
        self._add(name, self.last_snapshot or {})
        return f"milestone recorded: {name}"

    def mark_load(self, slot: str) -> None:
        self.loads += 1
        self._add(f"loaded state '{slot}'", self.last_snapshot or {})

    def note(self, text: str) -> str:
        text = " ".join(text.split())[:300]
        if not text:
            return "note needs some text"
        self.notes.append(text)
        del self.notes[:-MAX_NOTES]
        return f"note saved ({len(self.notes)} notes; metrics('report') shows them)"

    def elapsed(self) -> float:
        return self.prior_seconds + ((self.end_time or time.time()) - self.start_time)

    def budget_exhausted(self) -> Optional[str]:
        calls = sum(self.tool_calls.values())
        if self.max_tool_calls and calls >= self.max_tool_calls:
            return f"tool-call budget of {self.max_tool_calls} used ({calls} calls)"
        if self.max_real_seconds and self.elapsed() >= self.max_real_seconds:
            return f"time budget of {int(self.max_real_seconds)}s used ({int(self.elapsed())}s)"
        return None

    def _add(self, name: str, snapshot: dict[str, Any]) -> None:
        m = Milestone(name=name, frame=self.frames, elapsed_s=round(self.elapsed(), 1),
                      tool_calls=sum(self.tool_calls.values()), at=datetime.now().isoformat(timespec="seconds"),
                      snapshot={k: v for k, v in snapshot.items()
                                if not isinstance(v, (list, dict)) or k in _SNAPSHOT_LISTS})
        self.milestones.append(m)
        log.info("[milestone] %s", name)

    # -- output ------------------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "ai_model": self.ai_model,
            "rom": self.rom_name,
            "profile": self.profile_name,
            "started": datetime.fromtimestamp(self.first_start).isoformat(timespec="seconds"),
            "ended": datetime.fromtimestamp(self.end_time).isoformat(timespec="seconds") if self.end_time else None,
            "real_seconds": round(self.elapsed(), 1),
            "frames": self.frames,
            "game_seconds": round(self.frames / 60, 1),
            "tool_calls_total": sum(self.tool_calls.values()),
            "tool_calls": self.tool_calls,
            "images_sent": self.images_sent,
            "text_chars_sent": self.text_chars_sent,
            "chunks": self.chunks,
            "loads": self.loads,
            "budget": {"max_tool_calls": self.max_tool_calls, "max_real_seconds": self.max_real_seconds},
            "notes": list(self.notes),
            "milestones": [asdict(m) for m in self.milestones],
            "final_state": self.last_snapshot or {},
        }

    def summary(self) -> str:
        d = self.to_dict()
        lines = [
            f"session {d['session_id']} model={d['ai_model']} rom={d['rom']} profile={d['profile']}"
            + (f" chunk {d['chunks']}" if d["chunks"] > 1 else ""),
            f"real {d['real_seconds']}s | game {d['game_seconds']}s ({d['frames']} frames) | "
            f"tool calls {d['tool_calls_total']} | images {d['images_sent']} | text chars {d['text_chars_sent']}",
        ]
        if self.max_tool_calls or self.max_real_seconds:
            parts = []
            if self.max_tool_calls:
                parts.append(f"{d['tool_calls_total']}/{self.max_tool_calls} calls")
            if self.max_real_seconds:
                parts.append(f"{int(self.elapsed())}/{int(self.max_real_seconds)}s")
            lines.append("budget: " + ", ".join(parts))
        fs = d["final_state"]
        if fs:
            keep = {k: v for k, v in fs.items() if not isinstance(v, (list, dict)) and k != "badge_bits"}
            lines.append("state: " + ", ".join(f"{k}={v}" for k, v in keep.items()))
        if self.milestones:
            lines.append("milestones:")
            for m in self.milestones:
                lines.append(f"  {m.elapsed_s:>8.1f}s  call#{m.tool_calls:<5} f{m.frame:<9} {m.name}")
        else:
            lines.append("milestones: none yet")
        if self.notes:
            lines.append("notes:")
            lines.extend(f"  - {n}" for n in self.notes)
        return "\n".join(lines)

    def checkpoint(self) -> Path:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{self.session_id}_checkpoint.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=1))
        tmp.replace(path)
        return path

    def finalize(self) -> str:
        self.end_time = time.time()
        self.finalized = True
        self.out_dir.mkdir(parents=True, exist_ok=True)
        jpath = self.out_dir / f"{self.session_id}.json"
        jpath.write_text(json.dumps(self.to_dict(), indent=1))
        tpath = self.out_dir / f"{self.session_id}_summary.txt"
        tpath.write_text(self.summary() + "\n")
        cp = self.out_dir / f"{self.session_id}_checkpoint.json"
        if cp.exists():
            cp.unlink()
        log.info("metrics written to %s", jpath)
        return f"metrics saved: {jpath.name}, {tpath.name}\n{self.summary()}"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s) or "unknown"
