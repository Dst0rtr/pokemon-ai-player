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


PROVIDERS = {"claude": ClaudeProvider, "codex": CodexProvider}


def make_provider(name: str, model: str = "") -> Provider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise SystemExit(f"unknown provider '{name}'; choose from {', '.join(PROVIDERS)}")
    if shutil.which(cls.cli) is None:
        raise SystemExit(f"{cls.cli} is not installed or not on PATH")
    return cls(model or cls.default_model)
