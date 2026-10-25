"""
Command builders for the agent CLIs. Each provider knows how to launch its CLI headless with the
gameboy MCP server attached, how to resume its own session, and which stream parser to use.

Only the provider-specific parts live here; the chunk loop is in run.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class Provider:
    name = "base"
    cli = "cli"
    default_model = ""
    stream = ""                 # which bench/stream.py parser reads the output ("" = same as name)
    track = "cli"               # "jev" rows get code scaffolding and are reported separately
    variant = ""

    @property
    def label(self) -> str:
        return self.name

    @property
    def parser(self) -> str:
        return self.stream or self.name

    def server_args(self, run_dir: Path) -> list[str]:
        """Extra server flags for this provider."""
        return []

    def prompt_suffix(self) -> str:
        return ""

    def __init__(self, model: str):
        self.model = model

    def version(self) -> str:
        try:
            out = subprocess.run([self.cli, "--version"], capture_output=True, text=True, timeout=30)
            return (out.stdout or out.stderr).strip().splitlines()[0]
        except Exception as e:  # pragma: no cover
            return f"unknown ({e})"

    def prepare(self, run_dir: Path, server_cmd: list[str]) -> None:
        """Write per-run config files (nothing global is touched)."""

    def command(self, run_dir: Path, prompt_file: Path, session_id: Optional[str], first: bool) -> list[str]:
        raise NotImplementedError

    def env(self, run_dir: Path) -> dict[str, str]:
        env = dict(os.environ)
        # Never nest inside a Claude Code session's identity; the harness may itself run under one.
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            env.pop(k, None)
        return env

    def stdin_prompt(self) -> bool:
        """True when the prompt is piped on stdin rather than passed as an argument."""
        return True


class ClaudeProvider(Provider):
    name = "claude"
    cli = "claude"
    default_model = "claude-haiku-4-5-20251001"

    def prepare(self, run_dir: Path, server_cmd: list[str]) -> None:
        cfg = {"mcpServers": {"gameboy": {"command": server_cmd[0], "args": server_cmd[1:]}}}
        (run_dir / "mcp.json").write_text(json.dumps(cfg, indent=1))

    def command(self, run_dir, prompt_file, session_id, first):
        cmd = [self.cli, "-p", "--model", self.model,
               "--mcp-config", str(run_dir / "mcp.json"), "--strict-mcp-config",
               "--tools", "", "--permission-mode", "bypassPermissions", "--setting-sources", "",
               "--output-format", "stream-json", "--verbose"]
        if first:
            cmd += ["--session-id", session_id]
        else:
            cmd += ["--resume", session_id]
        return cmd


class CodexProvider(Provider):
    name = "codex"
    cli = "codex"
    default_model = "gpt-5.6-sol"

    def __init__(self, model: str, reasoning: str = "high"):
        super().__init__(model)
        self.reasoning = reasoning
        self._server_cmd: list[str] = []

    def prepare(self, run_dir: Path, server_cmd: list[str]) -> None:
        self._server_cmd = server_cmd
        (run_dir / "codex-mcp.txt").write_text("\n".join(self._mcp_overrides()))

    def _mcp_overrides(self) -> list[str]:
        args = json.dumps(self._server_cmd[1:])              # JSON strings are valid TOML strings
        return [f"mcp_servers.gameboy.command={json.dumps(self._server_cmd[0])}",
                f"mcp_servers.gameboy.args={args}",
                "mcp_servers.gameboy.default_tools_approval_mode=\"approve\"",   # no per-call approval prompts
                "mcp_servers.gameboy.startup_timeout_sec=90",
                "mcp_servers.gameboy.tool_timeout_sec=600"]

    def command(self, run_dir, prompt_file, session_id, first):
        common = ["--ignore-user-config", "--skip-git-repo-check", "--json",
                  "-c", f"model_reasoning_effort={json.dumps(self.reasoning)}",
                  "-c", "approval_policy=\"never\"", "-c", "sandbox_mode=\"read-only\""]
        for o in self._mcp_overrides():
            common += ["-c", o]
        if first:
            return [self.cli, "exec", "-m", self.model, "-C", str(run_dir)] + common + ["-"]
        return [self.cli, "exec", "resume", session_id, "-m", self.model] + common + ["-"]


def codex_rollout_usage(session_ids) -> dict:
    """Sum token usage from Codex's local session rollouts (~/.codex/sessions/**/rollout-*-<thread>.jsonl).
    `codex exec --json` reports usage only when a turn completes, so a chunk that was rotated or killed
    loses it; the rollout logs a token_count event after every model call instead."""
    import glob as _glob
    totals = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0, "reasoning": 0}
    found = 0
    for sid in {s for s in session_ids if s}:
        for f in _glob.glob(os.path.expanduser(f"~/.codex/sessions/**/rollout-*-{sid}.jsonl"), recursive=True):
            found += 1
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"token_count"' not in line:
                        continue
                    try:
                        u = json.loads(line)["payload"]["info"]["last_token_usage"]
                    except (ValueError, KeyError, TypeError):
                        continue
                    cached = int(u.get("cached_input_tokens", 0) or 0)
                    totals["input"] += max(int(u.get("input_tokens", 0) or 0) - cached, 0)   # uncached input, like Claude
                    totals["cached_input"] += cached
                    totals["cache_write"] += int(u.get("cache_write_input_tokens", 0) or 0)
                    totals["output"] += int(u.get("output_tokens", 0) or 0)
                    totals["reasoning"] += int(u.get("reasoning_output_tokens", 0) or 0)
    return totals if found else {}


def claude_transcript_usage(session_ids, root: str = "~/.claude/projects") -> dict:
    """Sum token usage from Claude Code's session transcripts (<root>/*/<session>.jsonl).
    The stream's per-message usage carries only a partial output count, and a rotated chunk never sees
    the final result event; the transcript stores each assistant message's final usage (repeated once per
    content block, so it is counted once per message id)."""
    import glob as _glob
    totals = {"input": 0, "cached_input": 0, "cache_write": 0, "output": 0, "reasoning": 0}
    found = 0
    for sid in {s for s in session_ids if s}:
        for f in _glob.glob(os.path.join(os.path.expanduser(root), "*", f"{sid}.jsonl")):
            found += 1
            usage: dict[str, dict] = {}
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                        msg = e["message"]
                        if e.get("type") == "assistant" and msg.get("usage"):
                            usage[msg.get("id") or str(len(usage))] = msg["usage"]
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
            for u in usage.values():
                totals["input"] += int(u.get("input_tokens", 0) or 0)
                totals["cached_input"] += int(u.get("cache_read_input_tokens", 0) or 0)
                totals["cache_write"] += int(u.get("cache_creation_input_tokens", 0) or 0)
                totals["output"] += int(u.get("output_tokens", 0) or 0)
                totals["reasoning"] += int((u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0)
    return totals if found else {}


def estimate_cost(tokens: dict, prices: dict) -> float:
    """USD at list prices (per million tokens) for the token columns the harness records."""
    return sum(tokens.get(k, 0) * prices.get(k, 0) / 1e6 for k in ("input", "cached_input", "cache_write", "output"))


class JevProvider(Provider):
    """Jev plays through bench/jev_agent.py (an MCP client of the server, launched like a CLI per chunk).
    `model` is the Jev model; variants: solo (no LLM at all), hybrid (Claude planner), scripted."""
    name = "jev"
    cli = "jev-agent"
    default_model = "jev-latest"
    stream = "jev"
    track = "jev"

    def __init__(self, model: str, variant: str = "solo", mock: bool = False, planner_model: str = "",
                 agent_args: Optional[list[str]] = None, fallback_model: str = ""):
        super().__init__(model)
        self.variant = variant
        self.mock = mock
        self.planner_model = planner_model or ClaudeProvider.default_model
        self.fallback_model = fallback_model or self.planner_model
        self.agent_args = list(agent_args or [])
        self._server_cmd: list[str] = []

    @property
    def label(self) -> str:
        return f"jev-{self.variant}"

    @property
    def display_model(self) -> str:
        if self.variant == "hybrid":
            return f"{self.model} + {self.planner_model} planner"
        if self.variant == "assist":
            return f"{self.model} + {self.fallback_model} fallback"
        return self.model

    def version(self) -> str:
        from bench.jev_agent import AGENT_VERSION
        return f"jev_agent.py v{AGENT_VERSION}" + (" (mock Jev)" if self.mock else "")

    def server_args(self, run_dir: Path) -> list[str]:
        # the Jev player builds its own map from the map view and decides each new trainer matchup itself: it asks the
        # server for both (a plain MCP client gets neither)
        return ["--auto-hand-back", "--map-elevation"]

    def prepare(self, run_dir: Path, server_cmd: list[str]) -> None:
        self._server_cmd = server_cmd

    def command(self, run_dir, prompt_file, session_id, first):
        root = Path(__file__).resolve().parent
        cmd = [self._server_cmd[0], str(root / "jev_agent.py"), "--run-dir", str(run_dir), "--session-id", run_dir.name,
               "--variant", self.variant, "--jev-model", self.model, "--planner-model", self.planner_model,
               "--fallback-model", self.fallback_model] + self.agent_args
        if self.mock:
            cmd.append("--mock")
        return cmd + ["--"] + self._server_cmd


class JevBattlesProvider(ClaudeProvider):
    """The normal Claude Code run (Haiku by default), but the server's battle('auto') asks Jev for every turn."""
    name = "jev"
    stream = "claude"
    track = "jev"
    variant = "battles"

    def __init__(self, model: str, jev_model: str = "jev-latest", mock: bool = False):
        super().__init__(model)
        self.jev_model = jev_model
        self.mock = mock

    @property
    def label(self) -> str:
        return "jev-battles"

    @property
    def display_model(self) -> str:
        return f"{self.model} + {self.jev_model} (battles)"

    def server_args(self, run_dir: Path) -> list[str]:
        return ["--battle-advisor", "mock-jev" if self.mock else "jev", "--jev-model", self.jev_model,
                "--jev-log", str(run_dir / "data" / "jev_decisions.jsonl")]

    def prompt_suffix(self) -> str:
        return ("\nIn this run battle('auto') is decided turn by turn by a separate battle model: use battle('auto') for "
                "every battle turn unless you need a specific item or switch.\n")


PROVIDERS = {"claude": ClaudeProvider, "codex": CodexProvider, "jev": JevProvider}
JEV_VARIANTS = ("solo", "assist", "hybrid", "scripted", "battles")
# play modes (run.py --mode): what decides each action. "llm" = an agent CLI alone (--provider claude or codex).
MODES = {"jev-solo": ("jev", "solo"), "jev-assist": ("jev", "assist"), "jev-hybrid": ("jev", "hybrid"),
         "jev-scripted": ("jev", "scripted"), "jev-battles": ("jev", "battles"), "llm": ("", "")}
MODEL_ALIASES = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5",
                 "fable": "claude-fable-5-1"}


def resolve_model(name: str) -> str:
    """haiku / sonnet / opus / fable -> the Claude model id; anything else is passed through."""
    return MODEL_ALIASES.get((name or "").lower(), name or "")


def resolve_mode(mode: str, provider: str, variant: str) -> tuple[str, str, str]:
    """(provider, variant, mode label) from --mode, or from --provider/--variant when no mode is given."""
    if mode:
        if mode not in MODES:
            raise SystemExit(f"unknown mode '{mode}'; choose from {', '.join(MODES)}")
        prov, var = MODES[mode]
        if mode == "llm":
            if provider not in ("claude", "codex"):
                raise SystemExit("--mode llm needs --provider claude or --provider codex")
            return provider, variant, "llm"
        if provider and provider != prov:
            raise SystemExit(f"--mode {mode} runs Jev; drop --provider {provider}")
        return prov, var, mode
    if not provider:
        raise SystemExit("choose a play mode: --mode " + "|".join(MODES) + " (or --provider claude|codex|jev)")
    return provider, variant, (f"jev-{variant}" if provider == "jev" else "llm")


def make_provider(name: str, model: str = "", variant: str = "solo", jev_model: str = "", mock: bool = False,
                  agent_args: Optional[list[str]] = None, fallback_model: str = "") -> Provider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise SystemExit(f"unknown provider '{name}'; choose from {', '.join(PROVIDERS)}")
    if name == "jev":
        if variant not in JEV_VARIANTS:
            raise SystemExit(f"unknown jev variant '{variant}'; choose from {', '.join(JEV_VARIANTS)}")
        needs_claude = variant == "battles" or (variant in ("hybrid", "assist") and not mock)
        if needs_claude and shutil.which("claude") is None:
            raise SystemExit("claude is not installed or not on PATH (needed by the jev-" + variant + " variant)")
        if variant == "battles":
            return JevBattlesProvider(model or ClaudeProvider.default_model, jev_model or JevProvider.default_model, mock)
        return JevProvider(jev_model or JevProvider.default_model, variant, mock, model, agent_args, fallback_model)
    if shutil.which(cls.cli) is None:
        raise SystemExit(f"{cls.cli} is not installed or not on PATH")
    return cls(model or cls.default_model)
