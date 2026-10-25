"""Spawn the real MCP server over stdio and exercise it through an MCP client."""

import asyncio
import json
import shutil
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.conftest import ROOT, requires_rom

pytestmark = requires_rom

EXPECTED_TOOLS = {"press", "walk", "battle", "talk", "shop", "manage", "wait", "screen", "state", "save_state", "load_state", "reset_game", "memory", "metrics"}


async def _session(rom_path, scratch, fn):
    rom = scratch / rom_path.name                    # Emulator.stop() writes <rom>.ram: keep it off the project ROM
    if not rom.exists():
        shutil.copy(rom_path, rom)
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "server.py"), "--rom", str(rom), "--ai-model", "pytest", "--autosave-every", "0",
              "--no-screenshot-files", "--log-level", "WARNING", "--data-dir", str(scratch)],
        cwd=str(scratch),
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            return await fn(s, init)


def test_tool_list_is_small_and_complete(rom_path, scratch):
    async def body(s, init):
        tools = await s.list_tools()
        names = {t.name for t in tools.tools}
        assert names == EXPECTED_TOOLS
        size = len(json.dumps([t.model_dump() for t in tools.tools]))
        assert size < 10000, f"tool schema JSON is {size} chars; keep it small (sent with every request)"
        assert init.instructions and "press(" in init.instructions and "Pokémon" in init.instructions
        return True

    assert asyncio.run(_session(rom_path, scratch, body))


def test_press_returns_text_and_image(rom_path, scratch):
    async def body(s, init):
        r = await s.call_tool("press", {"buttons": "W600"})
        for _ in range(12):
            r = await s.call_tool("press", {"buttons": "A"})
            if "NEW GAME" in r.content[0].text:
                break
        kinds = [c.type for c in r.content]
        assert kinds[0] == "text" and "image" in kinds
        assert "NEW GAME" in r.content[0].text
        r2 = await s.call_tool("press", {"buttons": "W5", "screenshot": True})
        assert "unchanged" in r2.content[0].text and [c.type for c in r2.content] == ["text"]
        r3 = await s.call_tool("screen", {"mode": "text"})
        assert "OPTION" in r3.content[0].text
        r4 = await s.call_tool("metrics", {"action": "report"})
        assert "tool calls" in r4.content[0].text and "images 1" not in r4.content[0].text[:0]
        r5 = await s.call_tool("reset_game", {})
        assert "confirm=true" in r5.content[0].text
        r6 = await s.call_tool("memory", {"action": "write", "address": "C000", "values": "00"})
        assert "disabled" in r6.content[0].text
        return True

    assert asyncio.run(_session(rom_path, scratch, body))


def test_plain_mcp_mode_has_no_jev_in_what_the_llm_sees(rom_path, scratch):
    """The MCP server is the primary product; the Jev player is an optional mode outside it (bench/). Without
    --battle-advisor nothing the LLM sees mentions Jev, and battle('auto') is the server's own move scorer."""
    async def body(s, init):
        tools = await s.list_tools()
        text = init.instructions + json.dumps([t.model_dump() for t in tools.tools])
        for name, args in (("press", {"buttons": "W300 A W60 A"}), ("state", {"section": "summary"}),
                           ("walk", {"path": "up 1"}), ("battle", {"action": "auto"}), ("metrics", {"action": "report"})):
            r = await s.call_tool(name, args)
            text += "\n" + "\n".join(c.text for c in r.content if c.type == "text")
        low = text.lower()
        assert "jev" not in low and "typesafe" not in low and "codex review" not in low, text[-2000:]
        return True

    assert asyncio.run(_session(rom_path, scratch, body))


def test_plain_mcp_mode_imports_no_jev_code(rom_path, tmp_path):
    """server.main without --battle-advisor builds the server without importing anything from bench/ (the Jev player,
    the benchmark harness), with the Jev mode's opt-in flags (--auto-hand-back, --map-elevation) off: the plain MCP
    mode works with no TypeSafe key and no Jev defaults."""
    import subprocess
    rom = tmp_path / rom_path.name
    shutil.copy(rom_path, rom)                       # Emulator.stop() writes <rom>.ram: keep it off the project ROM
    code = ("import sys, server\n"
            "server.FastMCP.run = lambda self, *a, **k: None\n"
            "real = server.build_server\n"
            "def spy(emu, advisor=None):\n"
            "    print('FLAGS', emu.profile.auto_hand_back, emu.profile.map_elevation, advisor)\n"
            "    return real(emu, advisor)\n"
            "server.build_server = spy\n"
            f"server.main(['--rom', {str(rom)!r}, '--ai-model', 'pytest', '--autosave-every', '0', "
            f"'--no-screenshot-files', '--log-level', 'WARNING', '--data-dir', {str(tmp_path)!r}])\n"
            "print('BENCH', sorted(m for m in sys.modules if m == 'bench' or m.startswith('bench.')))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    assert "BENCH []" in out.stdout, out.stdout + out.stderr
    assert "FLAGS False False None" in out.stdout, out.stdout     # the Jev mode's opt-in flags are off by default


def test_shop_and_manage_replies_carry_their_own_events():
    """An evolution from manage('use', 'Moon Stone') or a milestone during a purchase is reported in that call's reply,
    not on the next walk (review of the MCP path, 2026-10-24)."""
    from types import SimpleNamespace

    import server
    events = []
    metrics = SimpleNamespace(budget_exhausted=lambda: None, record_call=lambda *a: None)
    emu = SimpleNamespace(metrics=metrics, profile=None, pop_events=lambda: [events.pop() for _ in list(events)],
                          manage=lambda *a: events.append("evolved: Clefairy → Clefable") or "used Moon Stone",
                          shop=lambda *a: events.append("obtained: Bicycle") or "bought 1 Bicycle")
    mcp = server.build_server(emu)
    out = asyncio.run(mcp.call_tool("manage", {"action": "use", "target": "Moon Stone", "target2": "Clefairy"}))
    text = json.dumps([c.model_dump() for c in (out[0] if isinstance(out, tuple) else out)])
    assert "used Moon Stone" in text and "EVENT: evolved: Clefairy" in text, text
    out = asyncio.run(mcp.call_tool("shop", {"item": "Bicycle"}))
    text = json.dumps([c.model_dump() for c in (out[0] if isinstance(out, tuple) else out)])
    assert "EVENT: obtained: Bicycle" in text, text
