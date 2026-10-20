"""--map-source learned: the Jev player builds its own atlas while it plays, with no ROM map tables.

What it may use is what any player of the MCP server can see:

* on entering a map, wLastMap (0xD365: where its "outside" warps lead), the server's full map view (`state map`: walls, walkable tiles, grass, water, ledges, `D` warp
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
ROW_RE = re.compile(r"^\s*(\d+) ([#.,NPDvT<>~^LoS:BXH]+)$")
HEX_RE = re.compile(r"^([0-9A-F]{4}): ((?:[0-9A-F]{2} ?)+)$", re.M)
SIDES = ("north", "south", "west", "east")
OPPOSITE = {"north": "south", "south": "north", "west": "east", "east": "west"}


def parse_view(text: str) -> list[list[str]]:
    """Map rows of the server's full map view; P (you), N (people) and o (item balls) stand on walkable cells, D marks a
    warp, L a card-key door (solid until opened)."""
    rows = []
    for ln in text.splitlines():
        m = ROW_RE.match(ln)
        if m and int(m[1]) == len(rows):
            rows.append([("." if c in "PNoB" else c) for c in m[2]])   # (a boulder stands on floor; it moves)
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
        self._groups: dict[int, dict] = {}               # map id -> cell -> section root, from the walks made
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
            for key in ("cells", "warps", "conns", "outside"):
                if m.get(key):
                    mine[key] = m[key]
            for wk, arr in (m.get("arrivals") or {}).items():
                if wk not in mine["arrivals"] or not mine["arrivals"][wk].get("seen") and arr.get("seen"):
                    mine["arrivals"][wk] = arr
            mine["visits"] = max(mine.get("visits", 0), m.get("visits", 0))
            for nk, n in (m.get("nocross") or {}).items():
                nc = mine.setdefault("nocross", {})
                nc[nk] = max(nc.get(nk, 0), n)
            for key in ("noroute", "walked"):
                for rec in m.get(key, []):
                    if rec not in mine.setdefault(key, []):
                        mine[key].append(rec)
        for k, e in (other.get("edges") or {}).items():
            self.data["edges"].setdefault(k, e)
        self._maps.clear()
        self._groups.clear()

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
    def observe(self, mid: int, view: str, warps_text: str, conns: list[tuple[str, str]], last_map_text: str = "") -> None:
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
        lm = HEX_RE.search(last_map_text or "")
        if lm and int(lm[2].split()[0], 16) in D.MAPS:
            m["outside"] = int(lm[2].split()[0], 16)
        m["visits"] = m.get("visits", 0) + 1
        self._maps.pop(mid, None)
        self.dirty = True

    def record_warp(self, mid: int, x: int, y: int, dest: int, ax: int, ay: int) -> None:
        """Taking warp (x,y) of map mid put the player at (ax,ay) on dest; assume the warp there leads back."""
        self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        self.data["maps"][str(mid)]["arrivals"][f"{x},{y}"] = {"map": dest, "x": ax, "y": ay, "seen": True}
        back = self.data["maps"].setdefault(str(dest), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        # stored even before the destination's warp list is known: observe() reads it on the next step, so on a first
        # visit the check left Mt. Moon 1F's other door tile pointing at "Route 4, anywhere" (the east edge to Cerulean
        # looked one hop away; full-run iteration 36 walked back out and on to Pallet Town)
        if not back["arrivals"].get(f"{ax},{ay}", {}).get("seen"):
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

    def forget_noroute(self, mid: int, walked: bool = False) -> None:
        """The map changed under the player (a Card Key door opened): its walls learned from refusals may be gone. With
        `walked`, doors may also have shut (a Pokémon Mansion switch): the walks that linked its sections go too."""
        m = self.data["maps"].get(str(mid))
        if m and (m.pop("noroute", None) or walked and m.pop("walked", None)):
            if walked:
                m.pop("walked", None)
                self._groups.pop(mid, None)
            self._maps.pop(mid, None)
            self.dirty = True

    def record_nocross(self, mid: int, x: int, y: int, side: str) -> None:
        """Walking across the `side` edge from (x,y) was blocked: the cell across is solid. Twice (a person may have
        stood there once) and the cell is no longer a crossing (Lavender Town's west edge crosses to Route 8 only on
        row 8; full run 53 tried rows 5-7 and 13-14, then explored the Pokémon Tower instead)."""
        m = self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        k = f"{x},{y},{side}"
        nc = m.setdefault("nocross", {})
        nc[k] = nc.get(k, 0) + 1
        self._maps.pop(mid, None)
        self.dirty = True

    def record_walk(self, mid: int, a: tuple[int, int], b: tuple[int, int]) -> None:
        """The player got from a to b on this map without a warp: both lie in the same walkable section."""
        if a == b or self.linked(mid, a, b):
            return
        m = self.data["maps"].setdefault(str(mid), {"cells": [], "warps": [], "conns": [], "arrivals": {}, "visits": 0})
        m.setdefault("walked", []).append([a[0], a[1], b[0], b[1]])
        self._groups.pop(mid, None)
        self.dirty = True

    def linked(self, mid: int, a: tuple[int, int], b: tuple[int, int]) -> bool:
        if a == b:
            return True
        if mid not in self._groups:
            root: dict = {}
            def find(c):
                while root.setdefault(c, c) != c:
                    root[c] = root[root[c]]
                    c = root[c]
                return c
            for x1, y1, x2, y2 in (self.data["maps"].get(str(mid)) or {}).get("walked", []):
                root[find((x1, y1))] = find((x2, y2))
            self._groups[mid] = {c: find(c) for c in list(root)}
        g = self._groups[mid]
        return a in g and b in g and g[a] == g[b]

    def unreachable(self, mid: int, start: tuple[int, int], target: tuple[int, int]) -> bool:
        """A "no walkable route" counts only near the cell it was learned at, and only where the player has walked
        from that cell: the map view hides cave elevation, so Rock Tunnel B1F's (23,16) looks connected to the ladder
        arrival at (23,11) 5 cells away, and its "no route to (3,3)" hid the real way out (full run 51, ~6,000 steps
        exploring elsewhere). A start never walked to from there retries once and learns its own record."""
        m = self.data["maps"].get(str(mid)) or {}
        return any((tx, ty) == target and abs(fx - start[0]) + abs(fy - start[1]) <= NOROUTE_NEAR
                   and self.linked(mid, start, (fx, fy)) for fx, fy, tx, ty in m.get("noroute", []))

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
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):   # the other half of a two-wide door
            twin = m["arrivals"].get(f"{nx},{ny}")
            if twin and any((w[0], w[1]) == (nx, ny) for w in m["warps"]):
                return [(twin["map"], twin["x"], twin["y"])]
        if dm == 0xFF:                                       # "back outside": wLastMap, arrival unknown until taken once
            out = self.data["maps"].get(str(mid), {}).get("outside")
            return [(out, *UNKNOWN)] if out is not None else []
        try:
            dwarps = self.map(dm)["warps"]
            if dw < len(dwarps):
                return [(dm, dwarps[dw][0], dwarps[dw][1])]  # the destination's warp list is known (seen in WRAM)
        except KeyError:
            pass
        return [(dm, *UNKNOWN)]

    def _edge_arrival(self, side, dm, ya, xa, x, y, passable=frozenset({".", ",", ":", "X"})):
        return None                                          # handled in reach() from learned edge data

    def reach(self, mid: int, start: tuple[int, int], surf: bool = False, cut: bool = False,
              avoid: frozenset = frozenset(), parents: Optional[dict] = None) -> tuple[dict, list]:
        m = self.map(mid)
        if start == UNKNOWN:                                 # somewhere on this map: everything at a fixed cost
            trans = []
            for i, (x, y, _, _) in enumerate(m["warps"]):
                for arr in self.warp_dest(mid, i):
                    trans.append((UNKNOWN_COST, Hop(mid, "warp", x, y, arr[0], steps=UNKNOWN_COST), arr))
            for side, dm, _, _ in m["conns"]:
                trans.append((UNKNOWN_COST, Hop(mid, "edge", -1, -1, dm, side=side, steps=UNKNOWN_COST), (dm, *UNKNOWN)))
            return {}, trans
        dist, trans = super().reach(mid, start, surf=surf, cut=cut, avoid=avoid, parents=parents)
        out = [t for t in trans if t[1].kind == "warp" and not self.unreachable(mid, start, (t[1].x, t[1].y))]
        cells = m["cells"]
        h, w = len(cells), len(cells[0]) if cells else 0
        for side, dm, _, _ in m["conns"]:
            edge = [c for c in dist if (side == "north" and c[1] == 0) or (side == "south" and c[1] == h - 1)
                    or (side == "west" and c[0] == 0) or (side == "east" and c[0] == w - 1)]
            if not edge:
                continue
            e = self.data["edges"].get(f"{mid}:{side}")
            nocross = (self.data["maps"].get(str(mid)) or {}).get("nocross", {})
            edge = [c for c in edge if not self.unreachable(mid, start, c) and nocross.get(f"{c[0]},{c[1]},{side}", 0) < 2]
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
                 blocked: frozenset = frozenset(), prefer: tuple = ()) -> list[tuple]:
        """Untaken warps and uncrossed edges reachable from pos, best first: to a map the objective names (`prefer`,
        later entries first), then to never-visited maps, then nearest."""
        try:
            _, trans = self.reach(mid, pos, surf=surf, cut=cut)
        except KeyError:
            return []
        m = self.map(mid)
        out, seen = [], set()
        for steps, hop, arr in trans:
            if hop.kind == "warp":
                taken = any(m["arrivals"].get(f"{hop.x + dx},{hop.y + dy}", {}).get("seen")      # or its door twin
                            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)))
                key = ("warp", hop.x, hop.y)
            else:
                taken = self.data["edges"].get(f"{mid}:{hop.side}", {}).get("seen")
                key = ("edge", hop.side)
            if taken or key in seen or f"{mid}:{hop.x},{hop.y}" in blocked:
                continue
            seen.add(key)
            name = D.map_name(hop.dest)
            rank = -1 - list(prefer).index(name) if name in prefer else (0 if name not in visited else 1)
            out.append((rank, steps, hop))
        return [h for *_, h in sorted(out, key=lambda t: (t[0], t[1]))]


def explored_count(atlas: "LearnedAtlas") -> int:
    """Warps and edges actually taken so far."""
    return sum(1 for m in atlas.data["maps"].values() for a in m.get("arrivals", {}).values() if a.get("seen")) + \
        sum(1 for e in atlas.data["edges"].values() if e.get("seen"))


def frontier_maps(atlas: "LearnedAtlas", visited: set) -> list[int]:
    """Known maps that still have an untaken warp (not a door twin of a taken one) or an uncrossed edge."""
    out = []
    for k, m in atlas.data["maps"].items():
        if not m.get("cells"):
            continue
        mid = int(k)
        arr = m.get("arrivals", {})
        for w in m.get("warps", []):
            key = f"{w[0]},{w[1]}"
            twin = any(arr.get(f"{w[0] + dx},{w[1] + dy}", {}).get("seen") for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if not arr.get(key, {}).get("seen") and not twin:
                out.append(mid)
                break
        else:
            if any(not atlas.data["edges"].get(f"{mid}:{side}", {}).get("seen") for side, _ in m.get("conns", [])):
                out.append(mid)
    return out


def move_dir(a: tuple[int, int], b: tuple[int, int]) -> str:
    d = (b[0] - a[0], b[1] - a[1])
    return next((k for k, v in MOVES.items() if v == d), "")
