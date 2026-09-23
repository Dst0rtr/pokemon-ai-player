"""
Benchmark metrics for an AI playthrough of any Game Boy game.

Tracks real time, emulated frames, tool-call and token-ish counts, and a list
of timestamped milestones. Game profiles supply the milestones (badges,
captures, levels, score...) and a progress snapshot; the tracker is generic.

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


@dataclass
class Milestone:
    name: str
    frame: int
    elapsed_s: float
    tool_calls: int
    at: str
    snapshot: dict[str, Any] = field(default_factory=dict)


class MetricsTracker:
    def __init__(self, ai_model: str, rom_name: str, out_dir: Path):
        self.ai_model = ai_model
        self.rom_name = rom_name
        self.out_dir = Path(out_dir)
        self.profile_name = "generic"
        self.session_id = f"{_slug(ai_model)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.frames = 0
        self.tool_calls: dict[str, int] = {}
        self.images_sent = 0
        self.text_chars_sent = 0
        self.milestones: list[Milestone] = []
        self.last_snapshot: Optional[dict[str, Any]] = None
        self.finalized = False

    # -- called by the server ---------------------------------------------- #
    def set_profile(self, name: str) -> None:
        self.profile_name = name

    def restart(self, ai_model: Optional[str] = None) -> str:
        if ai_model:
            self.ai_model = ai_model
        self.session_id = f"{_slug(self.ai_model)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = time.time()
        self.end_time = None
        self.tool_calls = {}
        self.images_sent = 0
        self.text_chars_sent = 0
        self.milestones = []
        self.finalized = False
        return f"metrics session {self.session_id} started for model '{self.ai_model}'"

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

    def _add(self, name: str, snapshot: dict[str, Any]) -> None:
        m = Milestone(name=name, frame=self.frames, elapsed_s=round(time.time() - self.start_time, 1),
                      tool_calls=sum(self.tool_calls.values()), at=datetime.now().isoformat(timespec="seconds"),
                      snapshot={k: v for k, v in snapshot.items()
                                if not isinstance(v, (list, dict)) or k in _SNAPSHOT_LISTS})
        self.milestones.append(m)
        log.info("[milestone] %s", name)

    # -- output ------------------------------------------------------------- #
    def to_dict(self) -> dict[str, Any]:
        elapsed = (self.end_time or time.time()) - self.start_time
        return {
            "session_id": self.session_id,
            "ai_model": self.ai_model,
            "rom": self.rom_name,
            "profile": self.profile_name,
            "started": datetime.fromtimestamp(self.start_time).isoformat(timespec="seconds"),
            "ended": datetime.fromtimestamp(self.end_time).isoformat(timespec="seconds") if self.end_time else None,
            "real_seconds": round(elapsed, 1),
            "frames": self.frames,
            "game_seconds": round(self.frames / 60, 1),
            "tool_calls_total": sum(self.tool_calls.values()),
            "tool_calls": self.tool_calls,
            "images_sent": self.images_sent,
            "text_chars_sent": self.text_chars_sent,
            "milestones": [asdict(m) for m in self.milestones],
            "final_state": self.last_snapshot or {},
        }

    def summary(self) -> str:
        d = self.to_dict()
        lines = [
            f"session {d['session_id']} model={d['ai_model']} rom={d['rom']} profile={d['profile']}",
            f"real {d['real_seconds']}s | game {d['game_seconds']}s ({d['frames']} frames) | "
            f"tool calls {d['tool_calls_total']} | images {d['images_sent']} | text chars {d['text_chars_sent']}",
        ]
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
        return "\n".join(lines)

    def checkpoint(self) -> Path:
        self.out_dir.mkdir(exist_ok=True)
        path = self.out_dir / f"{self.session_id}_checkpoint.json"
        path.write_text(json.dumps(self.to_dict(), indent=1))
        return path

    def finalize(self) -> str:
        self.end_time = time.time()
        self.finalized = True
        self.out_dir.mkdir(exist_ok=True)
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
