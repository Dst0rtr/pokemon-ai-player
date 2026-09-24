"""
Parsers for the machine-readable event streams of the agent CLIs.

Each provider prints one JSON object per line. `ChunkStats.feed(obj)` folds an event into the
running totals of a chunk: tokens, cost, tool calls seen, session id, rate-limit signals, errors.
Field names come from real captures (Claude Code 2.1 `--output-format stream-json`, Codex 0.156
`exec --json`); unknown events are ignored.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

TOKEN_KEYS = ("input", "cached_input", "cache_write", "output", "reasoning")


@dataclass
class ChunkStats:
    provider: str
    session_id: Optional[str] = None
    tokens: dict[str, int] = field(default_factory=lambda: {k: 0 for k in TOKEN_KEYS})
    cost_usd: Optional[float] = None
    tool_calls: int = 0
    mcp_servers: list[dict] = field(default_factory=list)
    last_activity: float = field(default_factory=time.time)
    rate_limited: bool = False
    rate_limit_note: str = ""
    errors: list[str] = field(default_factory=list)
    result_text: str = ""
    turns: int = 0
    finished: bool = False

    def feed_line(self, line: str) -> None:
        line = line.strip()
        if not line or not line.startswith("{"):
            return
        try:
            obj = json.loads(line)
        except ValueError:
            return
        self.feed(obj)

    def feed(self, obj: dict[str, Any]) -> None:
        if self.provider == "claude":
            _feed_claude(self, obj)
        elif self.provider == "codex":
            _feed_codex(self, obj)

    def add_tokens(self, **kw: int) -> None:
        for k, v in kw.items():
            if v:
                self.tokens[k] = self.tokens.get(k, 0) + int(v)


# ---------------------------------------------------------------- Claude Code
def _feed_claude(st: ChunkStats, obj: dict[str, Any]) -> None:
    t = obj.get("type")
    if t == "system" and obj.get("subtype") == "init":
        st.session_id = obj.get("session_id") or st.session_id
        st.mcp_servers = list(obj.get("mcp_servers") or [])
        st.last_activity = time.time()
    elif t == "assistant":
        msg = obj.get("message") or {}
        for c in msg.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                st.tool_calls += 1
                st.last_activity = time.time()
        st.turns += 1
    elif t == "user":
        st.last_activity = time.time()
    elif t == "rate_limit_event":
        info = obj.get("rate_limit_info") or {}
        status = str(info.get("status", ""))
        if status.startswith("rejected") or status == "blocked":
            st.rate_limited = True
            st.rate_limit_note = f"{info.get('rateLimitType')} resetsAt={info.get('resetsAt')}"
    elif t == "result":
        st.finished = True
        st.session_id = obj.get("session_id") or st.session_id
        u = obj.get("usage") or {}
        st.add_tokens(input=u.get("input_tokens", 0), cached_input=u.get("cache_read_input_tokens", 0),
                      cache_write=u.get("cache_creation_input_tokens", 0), output=u.get("output_tokens", 0),
                      reasoning=(u.get("output_tokens_details") or {}).get("thinking_tokens", 0))
        if obj.get("total_cost_usd") is not None:
            st.cost_usd = (st.cost_usd or 0.0) + float(obj["total_cost_usd"])
        st.result_text = str(obj.get("result") or "")[:2000]
        if obj.get("is_error") or str(obj.get("subtype", "")).startswith("error"):
            st.errors.append(f"{obj.get('subtype')}: {st.result_text[:300]}")
            low = st.result_text.lower()
            if "rate limit" in low or "usage limit" in low or "429" in low or "overloaded" in low:
                st.rate_limited = True
                st.rate_limit_note = st.result_text[:200]


# ---------------------------------------------------------------- Codex
def _feed_codex(st: ChunkStats, obj: dict[str, Any]) -> None:
    t = obj.get("type", "")
    if t == "thread.started":
        st.session_id = obj.get("thread_id") or st.session_id
        st.last_activity = time.time()
    elif t.startswith("item."):
        item = obj.get("item") or {}
        if item.get("type") == "mcp_tool_call" and t == "item.started":
            st.tool_calls += 1
        if t != "item.updated":
            st.last_activity = time.time()
        if item.get("type") == "agent_message" and t == "item.completed":
            st.result_text = str(item.get("text") or "")[:2000]
    elif t == "turn.completed":
        st.turns += 1
        st.finished = True
        u = obj.get("usage") or {}
        st.add_tokens(input=u.get("input_tokens", 0), cached_input=u.get("cached_input_tokens", 0),
                      cache_write=u.get("cache_write_input_tokens", 0), output=u.get("output_tokens", 0),
                      reasoning=u.get("reasoning_output_tokens", 0))
    elif t in ("turn.failed", "error"):
        msg = str((obj.get("error") or {}).get("message") or obj.get("message") or obj)[:300]
        st.errors.append(msg)
        low = msg.lower()
        if "rate limit" in low or "429" in low or "usage limit" in low or "quota" in low:
            st.rate_limited = True
            st.rate_limit_note = msg[:200]
