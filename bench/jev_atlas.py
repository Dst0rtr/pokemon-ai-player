"""--map-source learned: the Jev player builds its own atlas while it plays, with no ROM map tables.

What it may use is what any player of the MCP server can see:

* on entering a map, the server's full map view (`state map`: walls, walkable tiles, grass, water, ledges, `D` warp
  tiles) and the connection sides (`connections:`), plus the map's warp list from WRAM (`memory D3AE`:
  wWarpEntries, y / x / destination warp index / destination map per warp);
* when the server answers "no walkable route from A to B" (the map view does not show cave elevation steps), that
  B is out of reach from around A;
* when it takes a warp or crosses an edge, where it actually arrived. An arrival on a warp tile is assumed to lead
  back (Gen 1 warps come in pairs) until a real crossing says otherwise; one edge crossing gives that edge's
  alignment for every other cell on it.

The atlas answers the same questions as `WorldNav` (bench/jev_nav.py), so the agent's route and per-warp options
work unchanged. Arrivals it does not know yet are "somewhere on that map": from there every warp and edge of that map
counts as reachable at a fixed cost, so routes through half-known maps are optimistic and get corrected as Jev plays.
When the objective's map is not in the atlas (or not reachable through it), the agent explores frontier-first:
warps never taken (to maps never visited first), then edges never crossed.

The atlas is saved as `<run>/data/jev_atlas.json` after every change; `--atlas FILE` seeds a run with an earlier
run's atlas, so Jev gets better each time.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from bench.jev_nav import MOVES, Hop, WorldNav
from games import gen1_data as D

UNKNOWN = (-1, -1)                    # arrival point not known yet: "somewhere on that map"
UNKNOWN_COST = 30                     # steps assumed from an unknown arrival point to any warp/edge of that map
NOROUTE_NEAR = 6                      # a "no walkable route" learned from a cell applies to starts this close to it
ROW_RE = re.compile(r"^\s*(\d+) ([#.,NPDvT<>~^]+)$")
HEX_RE = re.compile(r"^([0-9A-F]{4}): ((?:[0-9A-F]{2} ?)+)$", re.M)
SIDES = ("north", "south", "west", "east")
OPPOSITE = {"north": "south", "south": "north", "west": "east", "east": "west"}


def parse_view(text: str) -> list[list[str]]:
    """Map rows of the server's full map view; P (you) and N (people) stand on walkable cells, D marks a warp."""
    rows = []
    for ln in text.splitlines():
        m = ROW_RE.match(ln)
        if m and int(m[1]) == len(rows):
            rows.append([("." if c in "PN" else c) for c in m[2]])
    return rows


def parse_warps(text: str) -> list[tuple[int, int, int, int]]:
    """wWarpEntries from a `memory` read starting at 0xD3AE (count byte, then y, x, dest warp, dest map)."""
    data: list[int] = []
    for m in HEX_RE.finditer(text):
        data += [int(b, 16) for b in m[2].split()]
    if not data:
        return []
    n = min(data[0], 32, (len(data) - 1) // 4)
    return [(data[2 + 4 * i], data[1 + 4 * i], data[3 + 4 * i], data[4 + 4 * i]) for i in range(n)]


class LearnedAtlas(WorldNav):
    """A WorldNav over what the player has seen. Maps are keyed by map id (the name table in gen1_data is only used
    to turn the status line's map name into a key)."""

    def __init__(self, path: Optional[Path] = None, seed: Optional[Path] = None):
        super().__init__(b"")
        self.path = Path(path) if path else None
        self.data: dict = {"maps": {}, "edges": {}, "version": 1}
        for p in (seed, self.path):
            if p and Path(p).exists():
                try:
                    self.merge(json.loads(Path(p).read_text()))
                except (OSError, ValueError):
                    pass
        self.dirty = False

    # ---------------------------------------------------------------- persistence
    def merge(self, other: dict) -> None:
        for k, m in (other.get("maps") or {}).items():
            mine = self.data["maps"].setdefault(k, {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
            for key in ("cells", "warps", "conns"):
                if m.get(key):
                    mine[key] = m[key]
            for wk, arr in (m.get("arrivals") or {}).items():
                if wk not in mine["arrivals"] or not mine["arrivals"][wk].get("seen") and arr.get("seen"):
                    mine["arrivals"][wk] = arr
            mine["visits"] = max(mine.get("visits", 0), m.get("visits", 0))
            for rec in m.get("noroute", []):
                if rec not in mine.setdefault("noroute", []):
                    mine["noroute"].append(rec)
        for k, e in (other.get("edges") or {}).items():
            self.data["edges"].setdefault(k, e)
        self._maps.clear()

    def save(self) -> None:
        if self.path and self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")))
            tmp.replace(self.path)
            self.dirty = False

    def known(self, mid: int) -> bool:
        return str(mid) in self.data["maps"] and bool(self.data["maps"][str(mid)].get("cells"))

    def stats(self) -> dict:
        maps = self.data["maps"].values()
        warps = sum(len(m.get("warps", [])) for m in maps)
        seen = sum(1 for m in maps for a in m.get("arrivals", {}).values() if a.get("seen"))
        return {"maps": len(self.data["maps"]), "warps": warps, "warps_taken": seen, "edges": len(self.data["edges"])}

    # ---------------------------------------------------------------- learning
    def observe(self, mid: int, view: str, warps_text: str, conns: list[tuple[str, str]]) -> None:
        """Record a map on entry: its grid from the map view, its warps from WRAM, its connection sides."""
        m = self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        cells = parse_view(view)
        if cells:
            m["cells"] = ["".join(r) for r in cells]
        warps = parse_warps(warps_text)
        if warps:
            m["warps"] = [list(w) for w in warps]
        if conns:
            ids = {v: k for k, v in D.MAPS.items()}
            m["conns"] = [[side, ids[name]] for side, name in conns if name in ids]
        m["visits"] = m.get("visits", 0) + 1
        self._maps.pop(mid, None)
        self.dirty = True

    def record_warp(self, mid: int, x: int, y: int, dest: int, ax: int, ay: int) -> None:
        """Taking warp (x,y) of map mid put the player at (ax,ay) on dest; assume the warp there leads back."""
        self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        self.data["maps"][str(mid)]["arrivals"][f"{x},{y}"] = {"map": dest, "x": ax, "y": ay, "seen": True}
        back = self.data["maps"].setdefault(str(dest), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        if any((w[0], w[1]) == (ax, ay) for w in back.get("warps", [])) and not back["arrivals"].get(f"{ax},{ay}", {}).get("seen"):
            back["arrivals"][f"{ax},{ay}"] = {"map": mid, "x": x, "y": y, "seen": False}
        self._maps.pop(mid, None)
        self._maps.pop(dest, None)
        self.dirty = True

    def record_noroute(self, mid: int, frm: tuple[int, int], to: tuple[int, int]) -> None:
        m = self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        rec = [frm[0], frm[1], to[0], to[1]]
        if rec not in m.setdefault("noroute", []):
            m["noroute"].append(rec)
            self._maps.pop(mid, None)
            self.dirty = True

    def unreachable(self, mid: int, start: tuple[int, int], target: tuple[int, int]) -> bool:
        m = self.data["maps"].get(str(mid)) or {}
        return any((tx, ty) == target and abs(fx - start[0]) + abs(fy - start[1]) <= NOROUTE_NEAR
                   for fx, fy, tx, ty in m.get("noroute", []))

    def record_edge(self, mid: int, side: str, x: int, y: int, dest: int, ax: int, ay: int) -> None:
        """Crossing the `side` edge at (x,y) arrived at (ax,ay): that edge's offset, and the way back."""
        off = ax - x if side in ("north", "south") else ay - y
        fixed = ay if side in ("north", "south") else ax
        self.data["edges"][f"{mid}:{side}"] = {"map": dest, "offset": off, "fixed": fixed, "seen": True}
        back = f"{dest}:{OPPOSITE[side]}"
        if not self.data["edges"].get(back, {}).get("seen"):
            back_fixed = y if side in ("north", "south") else x
            self.data["edges"][back] = {"map": mid, "offset": -off, "fixed": back_fixed, "seen": False}
        self._maps.pop(mid, None)
        self.dirty = True

    # ---------------------------------------------------------------- WorldNav interface
    def map(self, mid: int) -> dict:
        if mid not in self._maps:
            m = self.data["maps"].get(str(mid))
            if not m or not m.get("cells"):
                raise KeyError(mid)
            cells = [list(r) for r in m["cells"]]
            for w in m.get("warps", []):                     # warp tiles: entered as a destination, never crossed
                if 0 <= w[1] < len(cells) and 0 <= w[0] < len(cells[0]) and cells[w[1]][w[0]] == "D":
                    cells[w[1]][w[0]] = "."
            cells = [[("." if c == "D" else c) for c in r] for r in cells]
            self._maps[mid] = {"tileset": None, "tiles": None, "cells": cells,
                               "warps": [tuple(w) for w in m.get("warps", [])],
                               "conns": [(side, dm, None, None) for side, dm in m.get("conns", [])],
                               "arrivals": m.get("arrivals", {})}
        return self._maps[mid]

    def entries(self) -> dict:
        return {}

    def warp_dest(self, mid: int, i: int, last_map: Optional[int] = None) -> list[tuple[int, int, int]]:
        m = self.map(mid)
        x, y, dw, dm = m["warps"][i]
        arr = m["arrivals"].get(f"{x},{y}")
        if arr:
            return [(arr["map"], arr["x"], arr["y"])]
        if dm == 0xFF:
            return []                                        # "back outside": unknown until taken once
        try:
            dwarps = self.map(dm)["warps"]
            if dw < len(dwarps):
                return [(dm, dwarps[dw][0], dwarps[dw][1])]  # the destination's warp list is known (seen in WRAM)
        except KeyError:
            pass
        return [(dm, *UNKNOWN)]

    def _edge_arrival(self, side, dm, ya, xa, x, y, passable=frozenset({".", ","})):
        return None                                          # handled in reach() from learned edge data

    def reach(self, mid: int, start: tuple[int, int], surf: bool = False, cut: bool = False,
              avoid: frozenset = frozenset()) -> tuple[dict, list]:
        m = self.map(mid)
        if start == UNKNOWN:                                 # somewhere on this map: everything at a fixed cost
            trans = []
            for i, (x, y, _, _) in enumerate(m["warps"]):
                for arr in self.warp_dest(mid, i):
                    trans.append((UNKNOWN_COST, Hop(mid, "warp", x, y, arr[0], steps=UNKNOWN_COST), arr))
            for side, dm, _, _ in m["conns"]:
                trans.append((UNKNOWN_COST, Hop(mid, "edge", -1, -1, dm, side=side, steps=UNKNOWN_COST), (dm, *UNKNOWN)))
            return {}, trans
        dist, trans = super().reach(mid, start, surf=surf, cut=cut, avoid=avoid)
        out = [t for t in trans if t[1].kind == "warp" and not self.unreachable(mid, start, (t[1].x, t[1].y))]
        cells = m["cells"]
        h, w = len(cells), len(cells[0]) if cells else 0
        for side, dm, _, _ in m["conns"]:
            edge = [c for c in dist if (side == "north" and c[1] == 0) or (side == "south" and c[1] == h - 1)
                    or (side == "west" and c[0] == 0) or (side == "east" and c[0] == w - 1)]
            if not edge:
                continue
            e = self.data["edges"].get(f"{mid}:{side}")
            edge = [c for c in edge if not self.unreachable(mid, start, c)]
            for c in sorted(edge, key=lambda c: dist[c])[:6]:  # a few nearest crossing cells per side
                if e and e["map"] == dm:
                    arr = (dm, c[0] + e["offset"], e["fixed"]) if side in ("north", "south") else (dm, e["fixed"], c[1] + e["offset"])
                else:
                    arr = (dm, *UNKNOWN)
                out.append((dist[c] + 1, Hop(mid, "edge", c[0], c[1], dm, side=side, steps=dist[c] + 1), arr))
        return dist, out

    def route(self, mid, pos, goal, **kw):
        try:
            return super().route(mid, pos, goal, **kw)
        except KeyError:
            return None

    # ---------------------------------------------------------------- frontier
    def frontier(self, mid: int, pos: tuple[int, int], visited: set, surf: bool = False, cut: bool = False,
                 blocked: frozenset = frozenset()) -> list[tuple]:
        """Untaken warps and uncrossed edges reachable from pos, best first: to never-visited maps, then nearest."""
        try:
            _, trans = self.reach(mid, pos, surf=surf, cut=cut)
        except KeyError:
            return []
        m = self.map(mid)
        out, seen = [], set()
        for steps, hop, arr in trans:
            if hop.kind == "warp":
                taken = m["arrivals"].get(f"{hop.x},{hop.y}", {}).get("seen")
                key = ("warp", hop.x, hop.y)
            else:
                taken = self.data["edges"].get(f"{mid}:{hop.side}", {}).get("seen")
                key = ("edge", hop.side)
            if taken or key in seen or f"{mid}:{hop.x},{hop.y}" in blocked:
                continue
            seen.add(key)
            new = D.map_name(hop.dest) not in visited
            out.append((0 if new else 1, steps, hop))
        return [h for *_, h in sorted(out, key=lambda t: (t[0], t[1]))]


def move_dir(a: tuple[int, int], b: tuple[int, int]) -> str:
    d = (b[0] - a[0], b[1] - a[1])
    return next((k for k, v in MOVES.items() if v == d), "")
