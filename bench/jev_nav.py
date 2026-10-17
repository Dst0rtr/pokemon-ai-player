"""Static world navigation for the Jev player (no LLM): a warp/edge graph of every map, read from the ROM.

Jev only sees local options; "walk to Mt. Moon B1F" makes the server pick the *nearest* ladder to that floor, which
in a multi-floor dungeon can be the wrong one (Mt. Moon, iteration 2: 215 fallbacks bouncing between B1F and B2F).
This module gives the director the concrete waypoint instead:

* nodes are arrival points (map, x, y): where a warp or an edge crossing drops the player;
* inside a map, reachability is a grid search over the ROM collision data (same rules as the server's pathfinder:
  solid tiles, cave/forest elevation pairs, one-way ledges, water only when surfing, cut trees only with Cut; other
  warps are never crossed on the way);
* transitions are the warps reachable from the arrival point (to the destination warp's tile on the destination
  map; 0xFF "last map" warps are resolved from the maps that lead into this one) and the edge cells of connected
  sides (to the aligned cell on the neighbour map);
* Dijkstra over arrival points finds the cheapest route to the goal map. Warps already taken since the last
  progress cost extra and hops that failed are blocked for a while (per-dungeon memory against ping-pong).

Everything is generic: Mt. Moon, Rock Tunnel, Rocket Hideout, Silph Co., Pokémon Tower, Seafoam, Victory Road.
Event-driven changes (opened Silph doors, boulders, spinners) are not in the ROM; a hop that fails is blocked and
the route re-planned, and the player's options always keep the server's own walk targets as a fallback.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Optional

from games import gen1_data as D

MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
LEDGE_DIR = {"v": "down", "<": "left", ">": "right"}
HOP_COST = 10                        # a warp or edge crossing, in steps
TAKEN_COST = 60                      # per time a warp was already taken since the last progress
NAME_TO_ID = {v: k for k, v in D.MAPS.items()}


@dataclass
class Hop:
    map: int                         # map the hop starts on
    kind: str                        # "warp" or "edge"
    x: int                           # warp tile, or the edge cell to leave from
    y: int
    dest: int                        # destination map id
    side: str = ""                   # edge hops: north/south/west/east
    steps: int = 0                   # grid steps to reach it from the previous arrival point

    @property
    def dest_name(self) -> str:
        return D.map_name(self.dest)

    def label(self) -> str:
        if self.kind == "edge":
            return f"walk to {self.dest_name} ({self.side} edge)"
        return f"walk to the warp at ({self.x},{self.y}) → {self.dest_name}"


class WorldNav:
    """Lazy, cached map data from a ROM image. Map ids are pokered's (the server's status line uses their names)."""

    def __init__(self, rom: bytes):
        self.rom = rom
        self._maps: dict[int, dict] = {}
        self._entries: Optional[dict[int, list[tuple[int, int]]]] = None

    # ---------------------------------------------------------------- per-map data
    def map(self, mid: int) -> dict:
        if mid not in self._maps:
            tileset, tiles = D.map_tiles(self.rom, mid)
            self._maps[mid] = {"tileset": tileset, "tiles": tiles, "cells": D.map_cells(self.rom, mid),
                               "warps": D.map_warps(self.rom, mid), "conns": D.map_connections(self.rom, mid)}
        return self._maps[mid]

    def entries(self) -> dict[int, list[tuple[int, int]]]:
        """map id -> [(source map, source warp index)] for every warp that leads into it (to resolve 0xFF)."""
        if self._entries is None:
            self._entries = {}
            for mid in D.MAPS:
                try:
                    warps = self.map(mid)["warps"]
                except (IndexError, ValueError):
                    continue
                for i, (_, _, _, dm) in enumerate(warps):
                    if dm != 0xFF:
                        self._entries.setdefault(dm, []).append((mid, i))
        return self._entries

    def warp_dest(self, mid: int, i: int, last_map: Optional[int] = None) -> list[tuple[int, int, int]]:
        """Where warp i of map mid puts the player: [(map, x, y)] (0xFF warps can have several candidates)."""
        x, y, dw, dm = self.map(mid)["warps"][i]
        if dm != 0xFF:
            dwarps = self.map(dm)["warps"]
            return [(dm, dwarps[dw][0], dwarps[dw][1])] if dw < len(dwarps) else []
        exact, other = [], []
        for src, si in self.entries().get(mid, []):
            if last_map is not None and src != last_map:
                continue
            sx, sy, sdw, _ = self.map(src)["warps"][si]
            if sdw == i:
                exact.append((src, sx, sy))       # the warp that leads into this one
            elif sdw < len(self.map(mid)["warps"]) and self.map(mid)["warps"][sdw][3] == 0xFF:
                other.append((src, sx, sy))       # the same outside (second half of a two-wide door)
        return exact or other

    # ---------------------------------------------------------------- grid search inside one map
    def reach(self, mid: int, start: tuple[int, int], surf: bool = False, cut: bool = False,
              avoid: frozenset = frozenset()) -> tuple[dict, list]:
        """Grid BFS from `start`: (distance per reachable cell, transitions [(steps, Hop, (dest map, x, y))])."""
        m = self.map(mid)
        cells, tiles, h = m["cells"], m["tiles"], len(m["cells"])
        w = len(cells[0]) if cells else 0
        warp_at = {(x, y): i for i, (x, y, _, _) in enumerate(m["warps"])}
        pairs = set(D.TILE_PAIR_COLLISIONS_LAND.get(m["tileset"], ()))
        if surf:
            pairs |= set(D.TILE_PAIR_COLLISIONS_WATER.get(m["tileset"], ()))
        passable = {".", ","} | ({"~"} if surf else set()) | ({"T"} if cut else set())
        dist = {start: 0}
        q = [start]
        trans: list = []
        seen_warp: set = {start}
        if start in warp_at:                      # standing on a warp: step off and back on to take it again
            for arr in self.warp_dest(mid, warp_at[start]):
                trans.append((2, Hop(mid, "warp", start[0], start[1], arr[0], steps=2), arr))
        while q:
            nq = []
            for (x, y) in q:
                d = dist[(x, y)]
                for name, (dx, dy) in MOVES.items():
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < w and 0 <= ny < h):
                        side = {"up": "north", "down": "south", "left": "west", "right": "east"}[name]
                        for s, dm, ya, xa in m["conns"]:
                            if s == side and ((x, y), s) not in seen_warp:
                                seen_warp.add(((x, y), s))
                                arr = self._edge_arrival(s, dm, ya, xa, x, y, passable)
                                if arr:
                                    trans.append((d + 1, Hop(mid, "edge", x, y, dm, side=s, steps=d + 1), arr))
                        continue
                    if pairs and frozenset((tiles[y][x], tiles[ny][nx])) in pairs or (nx, ny) in avoid:
                        continue
                    if (nx, ny) in warp_at:
                        if (nx, ny) not in seen_warp:
                            seen_warp.add((nx, ny))
                            i = warp_at[(nx, ny)]
                            for arr in self.warp_dest(mid, i):
                                trans.append((d + 1, Hop(mid, "warp", nx, ny, arr[0], steps=d + 1), arr))
                        continue
                    c = cells[ny][nx]
                    if c in LEDGE_DIR:
                        if LEDGE_DIR[c] != name:
                            continue
                        nx, ny = nx + dx, ny + dy                 # a ledge jump lands two cells on
                        if not (0 <= nx < w and 0 <= ny < h) or cells[ny][nx] not in passable:
                            continue
                    elif c not in passable:
                        continue
                    if (nx, ny) not in dist:
                        dist[(nx, ny)] = d + 1
                        nq.append((nx, ny))
            q = nq
        # warps the start cell itself sits next to diagonally do not count; a warp tile entered as a door from a
        # walkable neighbour is covered above (warps are checked before walkability)
        return dist, trans

    def _edge_arrival(self, side: str, dm: int, ya: int, xa: int, x: int, y: int,
                      passable: frozenset | set = frozenset({".", ","})) -> Optional[tuple[int, int, int]]:
        sb = lambda v: v - 256 if v > 127 else v               # noqa: E731 (signed byte)
        if side in ("north", "south"):
            ax, ay = x + sb(xa), ya
        else:
            ax, ay = xa, y + sb(ya)
        try:
            cells = self.map(dm)["cells"]
        except (IndexError, ValueError):
            return None
        # a crossing only where the cell across is walkable (Route 3 (63,0) -> Route 4 is solid; iteration 2 looped there)
        if 0 <= ay < len(cells) and 0 <= ax < len(cells[0]) and cells[ay][ax] in passable | set(LEDGE_DIR):
            return dm, ax, ay
        return None

    def path_cells(self, mid: int, start: tuple[int, int], target: tuple[int, int], **kw) -> list[tuple[int, int]]:
        """Cells of one shortest grid path from start to target (a warp or edge cell), by walking the BFS distances
        back from the target. Used to find what stands in the way when the server finds no route."""
        dist, _ = self.reach(mid, start, **kw)
        cur = target if target in dist else min(((x + dx, y + dy) for x, y in [target] for dx, dy in MOVES.values()
                                                 if (x + dx, y + dy) in dist), key=lambda c: dist[c], default=None)
        out = [target]
        while cur is not None and cur != start:
            out.append(cur)
            cur = min(((cur[0] + dx, cur[1] + dy) for dx, dy in MOVES.values() if dist.get((cur[0] + dx, cur[1] + dy), 1 << 30)
                       < dist[cur]), key=lambda c: dist[c], default=None)
        if cur == start:
            out.append(start)
        return out[::-1]

    # ---------------------------------------------------------------- route
    def route(self, mid: int, pos: tuple[int, int], goal: int, surf: bool = False, cut: bool = False,
              taken: Optional[dict] = None, blocked: frozenset = frozenset(), max_nodes: int = 4000,
              arrival: bool = False):
        """Cheapest hop list from (mid, pos) to any cell of map `goal`; [] when already there, None if no route.
        With arrival=True: (hops, (map, x, y) where the last hop lands), or None."""
        if mid == goal:
            return ([], (mid, pos[0], pos[1])) if arrival else []
        taken = taken or {}
        start = (mid, pos[0], pos[1])
        best = {start: 0}
        prev: dict = {}
        heap = [(0, start)]
        n = 0
        while heap and n < max_nodes:
            cost, node = heapq.heappop(heap)
            if cost > best.get(node, 1 << 30):
                continue
            n += 1
            if node[0] == goal:
                end, hops = node, []
                while node in prev:
                    node, hop = prev[node]
                    hops.append(hop)
                return (hops[::-1], end) if arrival else hops[::-1]
            try:
                _, trans = self.reach(node[0], (node[1], node[2]), surf=surf, cut=cut)
            except (IndexError, ValueError, KeyError):         # a map with no data (learned atlas): a dead end
                continue
            for steps, hop, arr in trans:
                key = f"{hop.map}:{hop.x},{hop.y}"
                if key in blocked:
                    continue
                c = cost + steps + HOP_COST + TAKEN_COST * taken.get(key, 0)
                if c < best.get(arr, 1 << 30):
                    best[arr] = c
                    prev[arr] = (node, hop)
                    heapq.heappush(heap, (c, arr))
        return None


def map_id(name: str) -> Optional[int]:
    return NAME_TO_ID.get(name)
