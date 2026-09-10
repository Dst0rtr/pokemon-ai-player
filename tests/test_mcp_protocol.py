"""Spawn the real MCP server over stdio and exercise it through an MCP client."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.conftest import ROOT, requires_rom

pytestmark = requires_rom

EXPECTED_TOOLS = {"press", "walk", "battle", "talk", "shop", "manage", "wait", "screen", "state", "save_state", "load_state", "reset_game", "memory", "metrics"}


async def _session(rom_path, scratch, fn):
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "server.py"), "--rom", str(rom_path), "--ai-model", "pytest", "--autosave-every", "0",
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
