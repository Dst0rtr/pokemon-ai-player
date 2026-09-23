"""
Generic, headless Game Boy emulator core built on PyBoy.

Independent of MCP so it can be driven from tests and scripts. Everything the
MCP tools do is a thin call into this class. Design goals:

* fast: frames are advanced in batches with rendering disabled; the screen is
  rendered exactly once, right before it is read.
* token-cheap: results are short strings; screenshots are only produced when
  requested and only when the screen actually changed.
* game-agnostic: game-specific knowledge lives in `games/` profiles.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from pyboy import PyBoy

from games import detect_profile
from games.base import GameProfile
from metrics import MetricsTracker

log = logging.getLogger("gameboy")

BUTTONS = {
    "A": "a", "B": "b", "START": "start", "SELECT": "select",
    "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right",
    "U": "up", "D": "down", "L": "left", "R": "right", "ST": "start", "SEL": "select",
}
DIRECTIONS = {"up", "down", "left", "right"}

_TOKEN = re.compile(r"^(?P<btn>[A-Z]+)(?:\s*[x×*]\s*(?P<rep>\d+))?(?::(?P<hold>\d+))?$", re.I)
_WAIT = re.compile(r"^W(?:AIT)?\s*:?\s*(?P<n>\d+)$", re.I)
_WALK = re.compile(r"^(?P<dir>UP|DOWN|LEFT|RIGHT|U|D|L|R)(?P<n>\d+)?$", re.I)

MAX_PRESSES = 100
_GOTO = re.compile(r"^(?:to|goto)\s*\(?\s*(?P<x>\d+)\s*[, ]\s*(?P<y>\d+)\s*\)?$", re.I)
_GOTO_NAME = re.compile(r"^(?:to|goto)\s+(?P<name>[^\d].*)$", re.I)
MAX_HOLD = 600
MAX_STEPS = 60
MAX_WAIT = 3600


class Emulator:
    def __init__(
        self,
        rom_path: str,
        *,
        profile: str = "auto",
        scale: int = 2,
        fast_text: bool = True,
        save_screenshots: bool = True,
        autosave_every: int = 20,
        allow_memory_write: bool = False,
        charmap_file: Optional[str] = None,
        ai_model: str = "unknown",
        base_dir: Optional[Path] = None,
        session_id: Optional[str] = None,
        max_tool_calls: int = 0,
        max_real_seconds: float = 0,
        finalize_on_exit: bool = False,
    ):
        self.rom_path = Path(rom_path).expanduser().resolve()
        if not self.rom_path.exists():
            raise FileNotFoundError(f"ROM not found: {self.rom_path}")
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.resolve()
        self.screenshots_dir = self.base_dir / "screenshots"
        self.saves_dir = self.base_dir / "saves" / self.rom_path.stem
        self.metrics_dir = self.base_dir / "metrics"
        self.profile_name = profile
        self.scale = max(1, min(int(scale), 4))
        self.save_screenshots = save_screenshots
        self.autosave_every = autosave_every
        self.allow_memory_write = allow_memory_write
        self.ai_model = ai_model
        self.options: dict[str, Any] = {"fast_text": fast_text}
        if charmap_file:
            with open(charmap_file) as f:
                raw = json.load(f)
            self.options["charmap"] = {int(k, 0) if isinstance(k, str) else int(k): v for k, v in raw.items()}

        self.pyboy: Optional[PyBoy] = None
        self.profile: GameProfile = None  # type: ignore
        self.frame = 0
        self.actions = 0
        self._last_sent_hash: Optional[str] = None
        self._boot_time = time.time()
        self.finalize_on_exit = finalize_on_exit
        self.metrics = MetricsTracker(ai_model, self.rom_path.name, self.metrics_dir, session_id=session_id,
                                      max_tool_calls=max_tool_calls, max_real_seconds=max_real_seconds)
        if session_id:
            # A fixed session id continues an earlier run: real time, calls and milestones accumulate.
            for cand in (self.metrics_dir / f"{session_id}_checkpoint.json", self.metrics_dir / f"{session_id}.json"):
                if cand.exists() and self.metrics.resume_from(cand):
                    self.frame = max(self.frame, self.metrics.frames)
                    break

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def boot(self, resume: bool = False) -> str:
        if self.pyboy is not None:
            return "already running"
        self.pyboy = PyBoy(str(self.rom_path), window="null", sound_emulated=False)
        self.profile = detect_profile(self.pyboy, self.options, self.profile_name)
        self.tick(1)
        msg = f"booted {self.pyboy.cartridge_title!r} profile={self.profile.name}"
        if resume and (self.saves_dir / "autosave.state").exists():
            self._load_slot("autosave")
            msg += " (resumed autosave)"
        self._load_world()
        self.profile.after_load()
        self.metrics.set_profile(self.profile.name)
        self.metrics.observe(self._safe_snapshot(), self.frame, [])
        log.info(msg)
        return msg

    def stop(self) -> None:
        if self.pyboy is None:
            return
        try:
            if self.autosave_every:
                self._autosave()
            if not self.metrics.finalized:
                if self.finalize_on_exit:
                    self.metrics.finalize()
                else:
                    self.metrics.checkpoint()
        finally:
            self.pyboy.stop(save=True)  # writes battery save (.ram) next to the ROM
            self.pyboy = None

    def reset(self) -> str:
        if self.pyboy is not None:
            self.pyboy.stop(save=True)
            self.pyboy = None
        self._last_sent_hash = None          # frames keep counting: the metrics clock never rewinds
        self.boot()
        self.tick(60)
        return "game reset to power-on"

    def _ensure(self) -> PyBoy:
        if self.pyboy is None:
            self.boot()
        return self.pyboy  # type: ignore

    # ------------------------------------------------------------------ #
    # low-level stepping
    # ------------------------------------------------------------------ #
    def tick(self, n: int = 1, render: bool = False) -> None:
        if n <= 0:
            return
        self._ensure().tick(n, render, False)
        self.frame += n

    def _render(self) -> None:
        """Render one frame so the screen buffer is current."""
        self.tick(1, render=True)

    def _settle(self, max_frames: int = 180, step: int = 6) -> None:
        """Advance until the tilemaps stop changing (text finished printing, scroll done)."""
        pb = self._ensure()
        last, same = None, 0
        for _ in range(max_frames // step):
            self.tick(step)
            if self.profile.busy():
                same = 0
                continue
            h = hashlib.blake2b(bytes(pb.memory[0x9800:0xA000]), digest_size=8).digest()
            if h == last:
                same += 1
                if same >= 2:
                    return
            else:
                same = 0
            last = h

    def _press(self, button: str, hold: int, gap: int) -> None:
        pb = self._ensure()
        pb.button_press(button)
        self.tick(hold)
        pb.button_release(button)
        self.tick(gap)
        self._settle(300)  # let text print / menus / battle animations finish before the next input

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def press(self, script: str, hold: int = 8, gap: int = 24, settle: int = 30) -> str:
        """
        Run a button script. Tokens are separated by spaces/commas:
          A            press A once
          A*5  A x5    press A five times
          UP:16        hold UP for 16 frames
          W60 / WAIT60 wait 60 frames
        """
        self._ensure()
        tokens = [t for t in re.split(r"[\s,;]+", script.strip()) if t]
        if not tokens:
            return "no buttons given"
        plan: list[tuple[str, int, int]] = []  # (button|"wait", reps, hold/frames)
        for t in tokens:
            m = _WAIT.match(t)
            if m:
                plan.append(("wait", 1, min(int(m.group("n")), MAX_WAIT)))
                continue
            m = _TOKEN.match(t)
            if not m or m.group("btn").upper() not in BUTTONS:
                return f"bad token '{t}'. Use A B START SELECT UP DOWN LEFT RIGHT, e.g. 'A*3 DOWN A W30'"
            reps = int(m.group("rep") or 1)
            h = int(m.group("hold") or hold)
            if reps < 1 or h < 1:
                return f"bad token '{t}': repeat and hold must be at least 1"
            plan.append((BUTTONS[m.group("btn").upper()], reps, min(h, MAX_HOLD)))
        total = sum(r for b, r, _ in plan if b != "wait")
        if total > MAX_PRESSES:
            return f"too many presses ({total} > {MAX_PRESSES}); split into several calls"
        done = []
        for btn, reps, h in plan:
            if btn == "wait":
                self.tick(h)
                done.append(f"W{h}")
                continue
            for _ in range(reps):
                self._press(btn, h, gap)
            done.append(btn.upper() + (f"*{reps}" if reps > 1 else "") + (f":{h}" if h != hold else ""))
        self.tick(settle)
        self._settle()
        self._after_action()
        return "pressed " + " ".join(done)

    def wait(self, frames: int = 60) -> str:
        frames = max(1, min(int(frames), MAX_WAIT))
        self.tick(frames)
        self._settle(60)
        self._after_action()
        return f"waited {frames} frames"

    def walk(self, path: str, on_battle: str = "stop") -> str:
        """
        Walk a path like "up 5, right 3" / "U5 R3", or "to <target>". Uses the
        game profile's position reader to count real steps, stop when blocked,
        and stop on map changes, battles or dialogue. on_battle: "stop" (default),
        "run" (flee wild battles and keep walking) or "auto" (fight them).
        """
        on_battle = (on_battle or "stop").lower()
        if on_battle not in ("stop", "run", "auto"):
            return "on_battle must be stop, run or auto"
        if on_battle == "stop":
            return self._walk_once(path)
        notes = []
        for _ in range(8):
            out = self._walk_once(path)
            if "battle started" not in out or not getattr(self.profile, "in_battle", lambda: 0)():
                return ("\n".join(notes) + "\n" if notes else "") + out
            kind = self.profile.battle().get("kind", "wild") if self.profile.battle() else "wild"
            action = "run" if (on_battle == "run" and kind == "wild") else "auto"
            res = self.profile.battle_action(self, action, "")
            if action == "run" and getattr(self.profile, "in_battle", lambda: 0)():
                res = self.profile.battle_action(self, "auto", "")      # could not flee: fight instead
            self._settle()
            if getattr(self.profile, "in_battle", lambda: 0)():
                self._after_action()
                return ("\n".join(notes) + "\n" if notes else "") + out + "\n" + res + "\n— still in the battle: finish it with battle()"
            self.tick(60)
            self._settle()
            notes.append(f"battle on the way: {res[:160]}")
            if "blacked out" in res:
                self._after_action()
                return "\n".join(notes) + "\n" + "blacked out — " + self.status()
        self._after_action()
        return "\n".join(notes) + "\ntoo many battles; stopped"

    def _walk_once(self, path: str) -> str:
        self._ensure()
        goto = _GOTO.match(path.strip())
        named = None if goto else _GOTO_NAME.match(path.strip())
        segs = None if (goto or named) else self._parse_walk(path)
        if isinstance(segs, str):
            return segs
        if getattr(self.profile, "in_battle", lambda: 0)():
            return "cannot walk: in a battle (use press: FIGHT is top-left, RUN bottom-right)"
        if self.profile.is_text_visible():
            return "cannot walk: a text box or menu is open (press A to continue or B to close it first)"
        if self.profile.scripted():
            for _ in range(50):                    # a scene may be about to hand control back
                self.tick(12)
                if not self.profile.scripted():
                    break
            if self.profile.scripted():
                return "cannot walk: a cutscene is running (use talk() to advance it)"
        if goto:
            return self._goto(int(goto.group("x")), int(goto.group("y")))
        if named:
            name = named.group("name").strip().strip("'\"")
            outs = []
            for hop in range(10):
                resolved = self.profile.resolve_target(name)
                if resolved == "here":
                    return f"already in {name}" if not outs else f"'{name}' → " + " | then ".join(outs)
                if resolved is None:
                    if outs:
                        break
                    places = getattr(self.profile, "place_names", lambda: [])()
                    return (f"'{name}' is not on this map and no explored route leads there. Here you can walk to: " + ", ".join(places)
                            if places else f"unknown place '{name}': use x,y coordinates on this map")
                tx, ty, edge = resolved
                before = self.profile.position()
                out = self._goto(tx, ty)
                if edge and out.startswith(("arrived", "already")):
                    steps, reason = self._walk_segment(edge, 1)
                    if reason and reason.startswith("entered"):
                        self.tick(96)
                        self._settle()
                        self._after_action()
                        out += f" — {reason}"
                outs.append(f"({tx},{ty}): {out}")
                after = self.profile.position()
                arrived_map = after and after[0] != before[0]
                if not arrived_map or "stopped:" in out.split("entered")[0] and "entered" not in out:
                    break
                # keep going while the destination is still a different, known map
                note = getattr(self.profile, "far_destination_note", lambda n: "")(name)
                if not note:
                    break
            return f"'{name}' → " + " | then ".join(outs)
        report = []
        stop_reason = None
        for direction, n in segs:
            steps, reason = self._walk_segment(direction, n)
            report.append(f"{direction} {steps}/{n}")
            if reason:
                stop_reason = reason
                if reason.startswith("entered"):
                    self.tick(96)  # warp fade-in ignores input for ~70 frames
                break
        self.tick(8)
        self._settle()
        # A script may freeze the player before its text box appears: re-classify after settling.
        if stop_reason in (None, "blocked"):
            if getattr(self.profile, "in_battle", lambda: 0)():
                stop_reason = "battle started"
            elif self.profile.is_text_visible():
                stop_reason = "dialogue appeared"
        self._after_action()
        self.profile.last_stop = stop_reason
        out = "walked " + ", ".join(report)
        if stop_reason:
            out += f" — stopped: {stop_reason}"
        return out

    def _goto(self, tx: int, ty: int, _retry: bool = True) -> str:
        """Plan a route on the decoded map and walk it, re-planning if something gets in the way."""
        prof = self.profile
        report: list[str] = []
        stop_reason = None
        for attempt in range(4):
            segs = prof.find_path(tx, ty)
            if segs is None:
                pos = prof.position()
                self._after_action()
                why = getattr(prof, "route_hint", lambda x, y: "")(tx, ty)
                return (f"no walkable route from ({pos[1]},{pos[2]}) to ({tx},{ty}) on this map"
                        + (" — " + ", ".join(report) if report else "") + (f" — {why}" if why else ""))
            if not segs:
                break
            total = sum(n for _, n in segs)
            if total > 300:
                self._after_action()
                return f"route to ({tx},{ty}) is {total} steps; move closer first"
            for direction, n in segs:
                steps, reason = self._walk_segment(direction, n)
                report.append(f"{direction} {steps}/{n}")
                if reason:
                    stop_reason = reason
                    break
            if stop_reason != "blocked":
                break
            stop_reason = None                      # an NPC probably stepped in the way: re-plan
            self.tick(30)
        pos = prof.position()
        if (_retry and stop_reason in (None, "blocked") and pos is not None and (pos[1], pos[2]) != (tx, ty)
                and abs(pos[1] - tx) + abs(pos[2] - ty) == 1):
            # Refused to step onto the door tile itself: try its twin (two-wide doorways).
            for ax, ay in getattr(prof, "alternate_warps", lambda x, y: [])(tx, ty):
                return self._goto(ax, ay, _retry=False)
        if (stop_reason is None and pos is not None and (pos[1], pos[2]) == (tx, ty)
                and any((wx, wy) == (tx, ty) for wx, wy, _ in getattr(prof, "warps", list)())):
            # Standing on a door/warp tile: step through it (off the map edge for exits).
            last_dir = report[-1].split()[0] if report else None
            edge_dir = getattr(prof, "edge_direction", lambda x, y: None)(tx, ty)
            go = edge_dir or last_dir
            if go:
                steps, reason = self._walk_segment(go, 1)
                if reason:
                    stop_reason = reason
                    report.append(f"{go} {steps}/1")
        self.tick(8)
        self._settle()
        if stop_reason in (None, "blocked"):
            if getattr(prof, "in_battle", lambda: 0)():
                stop_reason = "battle started"
            elif prof.is_text_visible():
                stop_reason = "dialogue appeared"
        if stop_reason and stop_reason.startswith("entered"):
            self.tick(96)
        self._after_action()
        pos = prof.position()
        arrived = pos is not None and (pos[1], pos[2]) == (tx, ty)
        prof.last_stop = stop_reason or (None if arrived else "blocked")
        if arrived and not report:
            out = f"already at ({tx},{ty})"
        else:
            out = ("arrived at" if arrived else "went toward") + f" ({tx},{ty}): " + ", ".join(report)
        if stop_reason:
            out += f" — stopped: {stop_reason}"
        elif not arrived:
            out += " — could not get closer"
        return out

    def _parse_walk(self, path: str):
        tokens = [t for t in re.split(r"[\s,;]+", path.strip()) if t]
        if not tokens:
            return "no path given"
        segs = []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            m = re.match(r"^(?P<dir>UP|DOWN|LEFT|RIGHT|U|D|L|R)(?P<n>\d+)?$", t, re.I)
            if not m:
                return f"bad path '{t}'. Use e.g. 'up 5, right 3' or 'U5 R3'"
            n = m.group("n")
            if n is None and i + 1 < len(tokens) and tokens[i + 1].isdigit():
                n = tokens[i + 1]
                i += 1
            steps = int(n) if n is not None else 1
            if steps < 1:
                return f"bad path '{t} {n}': steps must be at least 1"
            segs.append((BUTTONS[m.group("dir").upper()], min(steps, MAX_STEPS)))
            i += 1
        return segs

    def _walk_segment(self, direction: str, n: int) -> tuple[int, Optional[str]]:
        pb = self._ensure()
        prof = self.profile
        pos = prof.position()
        if pos is None:  # generic game: timed hold
            pb.button_press(direction)
            self.tick(prof.frames_per_step * n)
            pb.button_release(direction)
            return n, None
        start_map = pos[0]
        last = pos
        steps, idle, reason = 0, 0, None
        pb.button_press(direction)
        try:
            for f in range(prof.frames_per_step * n * 4 + 160):   # ledge jumps take ~3x a normal step
                self.tick(1)
                cur = prof.position()
                if cur[0] != start_map:
                    reason = f"entered {prof.map_label(cur[0])}"
                    break
                if cur != last:
                    steps += abs(cur[1] - last[1]) + abs(cur[2] - last[2])   # a ledge jump moves 2 cells
                    last = cur
                    idle = 0
                    if steps >= n:
                        break
                else:
                    idle += 1
                if f % 4 == 3:
                    if getattr(prof, "in_battle", lambda: 0)():
                        reason = "battle started"
                        break
                    if prof.is_text_visible():
                        reason = "dialogue appeared"
                        break
                if idle > (90 if steps == 0 else 40):   # first step may wait out a fade-in; ledge jumps are slow
                    reason = "blocked"
                    break
        finally:
            pb.button_release(direction)
        if reason is None:
            # Walking off a map edge: the coordinates leave the map first and the new map loads a
            # few frames later. Wait for it so callers never see out-of-map positions.
            cur = prof.position()
            if cur is not None and cur[0] == start_map and getattr(prof, "off_map", lambda p: False)(cur):
                for _ in range(40):
                    self.tick(6)
                    cur = prof.position()
                    if cur[0] != start_map:
                        reason = f"entered {prof.map_label(cur[0])}"
                        break
        if reason is None and steps < n:
            reason = "blocked"                     # ran out of time without finishing: treat as blocked
        return steps, reason

    # ------------------------------------------------------------------ #
    # observation
    # ------------------------------------------------------------------ #
    def status(self) -> str:
        self._ensure()
        line = self.profile.status_line()
        return f"f{self.frame} {line}".strip()

    def talk(self) -> str:
        self._ensure()
        out = self.profile.talk(self)
        self._settle()
        self._after_action()
        return out

    def shop(self, item: str, qty: int = 1) -> str:
        self._ensure()
        out = self.profile.shop(self, item, qty)
        self._settle()
        self._after_action()
        return out

    def manage(self, action: str, target: str = "", target2: str = "") -> str:
        self._ensure()
        out = self.profile.manage(self, action, target, target2)
        self._settle()
        self._after_action()
        return out

    def battle(self, action: str = "fight", target: str = "") -> str:
        self._ensure()
        was_map = self.profile.position()
        out = self.profile.battle_action(self, action, target)
        self._settle()
        if not getattr(self.profile, "in_battle", lambda: 0)():
            self.tick(60)                 # battle exit fade / black-out teleport: let the map load
            self._settle()
            if was_map and self.profile.position() and self.profile.position()[0] != was_map[0]:
                self._last_full_map = None    # new map after a black-out: show it in full next time
        self._after_action()
        return out

    def state(self, section: str = "summary") -> str:
        self._ensure()
        return self.profile.state(section)

    def screen_text(self) -> Optional[str]:
        self._ensure()
        return self.profile.screen_text()

    def map_view(self) -> str:
        """Full map the first time a map is seen, the local window afterwards."""
        self._ensure()
        pos = self.profile.position()
        if pos is None or getattr(self.profile, "in_battle", lambda: 0)():
            return ""
        if pos[0] != self._last_full_map:
            self._last_full_map = pos[0]
            return self.state("map")
        sections = self.profile.sections()
        return self.state("nearby" if "nearby" in sections else "map")

    _last_full_map: Optional[int] = None

    def screenshot(self, scale: Optional[int] = None, force: bool = False) -> Optional[bytes]:
        """
        PNG bytes of the current screen, or None if identical to the last
        screenshot returned (unless force=True). Also saved to screenshots/.
        """
        pb = self._ensure()
        self._render()
        arr = pb.screen.ndarray
        digest = hashlib.blake2b(arr.tobytes(), digest_size=8).hexdigest()
        if not force and digest == self._last_sent_hash:
            return None
        self._last_sent_hash = digest
        img = Image.fromarray(arr[:, :, :3]).convert("L")
        s = max(1, min(int(scale or self.scale), 4))
        if s > 1:
            img = img.resize((img.width * s, img.height * s), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        data = buf.getvalue()
        self._save_screenshot_file(data)
        return data

    def _save_screenshot_file(self, data: bytes) -> None:
        try:
            self.screenshots_dir.mkdir(exist_ok=True)
            (self.screenshots_dir / "latest.png").write_bytes(data)
            if self.save_screenshots:
                (self.screenshots_dir / f"frame_{self.frame:08d}.png").write_bytes(data)
        except OSError as e:  # pragma: no cover
            log.warning("could not save screenshot: %s", e)

    # ------------------------------------------------------------------ #
    # save states
    # ------------------------------------------------------------------ #
    def _slot_path(self, slot: str) -> Path:
        slot = re.sub(r"[^A-Za-z0-9_.-]", "_", str(slot)) or "1"
        return self.saves_dir / f"{slot}.state"

    def list_states(self) -> list[str]:
        if not self.saves_dir.exists():
            return []
        return sorted(p.stem for p in self.saves_dir.glob("*.state"))

    def save_state(self, slot: str = "1") -> str:
        pb = self._ensure()
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        path = self._slot_path(slot)
        tmp = path.with_suffix(".state.tmp")
        with open(tmp, "wb") as f:
            pb.save_state(f)
        os.replace(tmp, path)          # atomic: an interrupted save never leaves a truncated slot
        meta = {"frame": self.frame, "status": self.profile.status_line(), "saved": time.strftime("%Y-%m-%d %H:%M:%S")}
        path.with_suffix(".json").write_text(json.dumps(meta))
        return f"saved state '{path.stem}'"

    def load_state(self, slot: str = "1") -> str:
        path = self._slot_path(slot)
        if not path.exists():
            slots = self.list_states()
            return f"no state '{slot}'. available: {', '.join(slots) or 'none'}"
        self._load_slot(path.stem)
        self.metrics.mark_load(path.stem)     # reloads are visible in the benchmark timeline
        return f"loaded state '{path.stem}'"

    def _load_slot(self, slot: str) -> None:
        """Raw state load. Frames keep counting (the emulated clock is cumulative, never rewound)."""
        pb = self._ensure()
        with open(self._slot_path(slot), "rb") as f:
            pb.load_state(f)
        self._last_sent_hash = None
        self.tick(2)
        self.profile.after_load()

    def _autosave(self) -> None:
        try:
            self.save_state("autosave")
            self._save_world()
        except Exception as e:  # pragma: no cover
            log.warning("autosave failed: %s", e)

    def _world_path(self) -> Path:
        return self.saves_dir / "world.json"

    def _save_world(self) -> None:
        data = self.profile.world_data() if self.profile else None
        if not data:
            return
        self.saves_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._world_path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data))
        os.replace(tmp, self._world_path())

    def _load_world(self) -> None:
        path = self._world_path()
        if not path.exists() or self.profile is None:
            return
        try:
            self.profile.load_world(json.loads(path.read_text()))
        except (OSError, ValueError) as e:  # pragma: no cover
            log.warning("could not load world graph: %s", e)

    # ------------------------------------------------------------------ #
    # memory
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_addr(address: str | int) -> int:
        if isinstance(address, int):
            a = address
        else:
            txt = str(address).strip().lower().replace("$", "0x")
            try:
                a = int(txt, 16) if not txt.startswith("0x") else int(txt, 16)
            except ValueError:
                raise ValueError(f"bad address '{address}': use hex like D163 or 0xD163") from None
        if not 0 <= a <= 0xFFFF:
            raise ValueError(f"address {a:#x} out of range 0000-FFFF")
        return a

    def read_memory(self, address: str | int, length: int = 16) -> str:
        pb = self._ensure()
        a = self._parse_addr(address)
        n = max(1, min(int(length), 256, 0x10000 - a))
        data = list(pb.memory[a:a + n])
        lines = []
        for off in range(0, n, 16):
            chunk = data[off:off + 16]
            lines.append(f"{a + off:04X}: " + " ".join(f"{b:02X}" for b in chunk))
        return "\n".join(lines)

    def write_memory(self, address: str | int, values: str) -> str:
        if not self.allow_memory_write:
            return "memory writes are disabled (start the server with --allow-memory-write)"
        pb = self._ensure()
        a = self._parse_addr(address)
        vals = [int(v, 16) & 0xFF for v in re.split(r"[\s,]+", values.strip()) if v]
        for i, v in enumerate(vals):
            pb.memory[a + i] = v
        return f"wrote {len(vals)} byte(s) at {a:04X}"

    # ------------------------------------------------------------------ #
    # bookkeeping after every action
    # ------------------------------------------------------------------ #
    def _safe_snapshot(self) -> dict[str, Any]:
        try:
            return self.profile.snapshot()
        except Exception as e:  # pragma: no cover
            log.debug("snapshot failed: %s", e)
            return {}

    def _after_action(self) -> list[str]:
        self.actions += 1
        self.profile.last_stop = None            # walk helpers set it again right after this
        try:
            self.profile.after_action()
        except Exception as e:  # pragma: no cover
            log.debug("after_action failed: %s", e)
        snap = self._safe_snapshot()
        events = self.metrics.observe(snap, self.frame, self.profile.milestones(self.metrics.last_snapshot or {}, snap) if self.metrics.last_snapshot is not None else [])
        if self.autosave_every and self.actions % self.autosave_every == 0:
            self._autosave()
            self.metrics.checkpoint()
        self.pending_events = events
        return events

    pending_events: list[str] = []

    def pop_events(self) -> list[str]:
        ev, self.pending_events = self.pending_events, []
        return ev
