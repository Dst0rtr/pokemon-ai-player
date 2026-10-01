"""
Helpers shared by the scripted example agents (reference_run.py, extended_run.py).

A ScriptedAgent drives the emulator through the public tool functions only (the same ones the MCP
server exposes) and logs every unexpected reply as an ODD line, so the scripts double as end-to-end
regression runs.
"""
import time

from games import gen1_data as D
from server import build_server

STATUS = {"Growl", "Tail Whip", "String Shot", "Leer", "Sand-Attack", "Harden", "PoisonPowder", "Stun Spore", "Sleep Powder",
          "Rage", "Bide", "Focus Energy", "Smokescreen", "Supersonic", "Whirlwind", "Roar", "Teleport", "Mist", "Agility"}
BUGS = ("Caterpie", "Metapod", "Butterfree")
FIRE = ("Charmander", "Charmeleon", "Charizard")
CITY_OF = {"Viridian Poké Center": "Viridian City", "Pewter Poké Center": "Pewter City",
           "Cerulean Poké Center": "Cerulean City", "Mt. Moon Poké Center": "Route 4",
           "Vermilion Poké Center": "Vermilion City", "Lavender Poké Center": "Lavender Town",
           "Celadon Poké Center": "Celadon City", "Fuchsia Poké Center": "Fuchsia City",
           "Cinnabar Poké Center": "Cinnabar Island", "Saffron Poké Center": "Saffron City"}


def out_of_pp(p):
    return all(pp == 0 for n, pp in p["moves"] if n not in STATUS)


def _norm(x):
    return "".join(c for c in x.lower() if c.isalnum())


class ScriptedAgent:
    def __init__(self, emu, max_odd=40):
        self.emu = emu
        self.T = {n: t.fn for n, t in build_server(emu)._tool_manager._tools.items()}
        self.prof = emu.profile
        self.ODD = []
        self.calls = 0
        self.max_odd = max_odd
        self.t_start = time.time()

    # -- raw tool calls ------------------------------------------------------ #
    @staticmethod
    def txt(res):
        return "\n".join(c.text for c in res if c.type == "text")

    def call(self, name, **kw):
        self.calls += 1
        if name in ("press", "walk", "battle", "talk", "wait"):
            kw.setdefault("screenshot", False)
        return self.txt(self.T[name](**kw))

    def press(self, b): return self.call("press", buttons=b)
    def walk(self, p, on_battle="stop"): return self.call("walk", path=p, on_battle=on_battle)
    def talk(self): return self.call("talk")
    def battle(self, a, t=""): return self.call("battle", action=a, target=t)
    def state(self, s="summary"): return self.call("state", section=s)
    def shop(self, i, q): return self.call("shop", item=i, qty=q)
    def manage(self, a, t="", t2=""): return self.call("manage", action=a, target=t, target2=t2)

    def log(self, *a):
        print(f"[{time.time() - self.t_start:6.1f}s #{self.calls}]", *a, flush=True)

    def odd(self, what):
        self.ODD.append(what)
        self.log("ODD:", what)
        if self.max_odd and len(self.ODD) >= self.max_odd:
            self.log("too many oddities: aborting the run")
            self.finish("ABORTED")
            self.emu.stop()
            raise SystemExit(3)

    # -- composite behaviours ------------------------------------------------ #
    def until(self, fn, needle, tries=30, label=""):
        out = ""
        for _ in range(tries):
            out = fn()
            if needle in out:
                return out
        self.odd(f"never saw {needle!r} ({label}); last: {out[:160]!r}")
        return out

    def skip_text(self, max_n=40):
        prof = self.prof
        for _ in range(max_n):
            if not prof.is_text_visible() or prof.in_battle():
                return
            r = self.talk()
            if r.startswith("choice"):
                self.odd("unexpected choice while skipping text: " + r[:120])
                self.press("B")
                return
        self.odd("text never ended: " + (prof.screen_text() or "")[:100].replace("\n", "|") + " @ " + self.state())

    def resolve_battle(self, policy_move=None, trainee=None, strong=None, want=None, heal_below=0.0, potion="Potion",
                       smart=True):
        """Fight the current battle to its end. trainee/strong: switch a weak trainee out for a strong
        species when low; want: throw balls at those species; heal_below: use a potion under that HP ratio;
        smart: switch a Pokémon below 30% HP for the healthiest team-mate when no potion is left."""
        prof, battle, press, log = self.prof, self.battle, self.press, self.log
        turns, r = 0, ""
        bad_moves: set = set()                          # moves the helper refused this battle (disabled / no PP)
        while prof.in_battle() and turns < 45:
            turns += 1
            b = prof.battle()
            if b is None or b["mine"]["max_hp"] == 0 or b["mine"]["species"].startswith("MissingNo"):
                press("A")
                continue
            mine = b["mine"]
            party = prof.party()
            dmg_pp = sum(pp for n, pp in mine["moves"] if n not in STATUS)
            if trainee and mine["species"] in trainee and (mine["hp"] < mine["max_hp"] * 0.5 or dmg_pp == 0):
                idx = next((i + 1 for i, p in enumerate(party) if p["species"] in strong and p["hp"] > 0), None)
                if idx:
                    r = battle("switch", str(idx))
                    if "battle over" in r or not prof.in_battle():
                        return r
                    continue
                if dmg_pp == 0:                            # helpless trainee and nobody to switch to: flee
                    r = battle("run")
                    if not prof.in_battle():
                        return r
            if want and b["enemy"]["species"] in want and any("Ball" in n for n, _ in prof.items()):
                r = battle("item", "Poké Ball")           # throw right away
                log("  throw:", r[:120])
                if "needs a decision" in r:                # nickname prompt
                    press("DOWN A")
                    return r
                continue
            if heal_below and mine["hp"] < mine["max_hp"] * heal_below and any(potion in n for n, _ in prof.items()):
                r = battle("item", potion)
                log("  heal:", r[:120])
                continue
            helpless = not any(pp > 0 for n, pp in mine["moves"] if n not in STATUS and n != mine.get("disabled") and n not in bad_moves)
            if smart and (mine["hp"] < mine["max_hp"] * 0.3 or helpless):
                cur = self.prof._u8(0xCC2F)
                best = max(((i, p) for i, p in enumerate(party) if i != cur and p["hp"] > p["max_hp"] * 0.5
                            and any(pp > 0 for n, pp in p["moves"] if n not in STATUS)),
                           key=lambda ip: ip[1]["level"], default=None)
                if best:
                    r = battle("switch", str(best[0] + 1))
                    log("  switch:", r[:100])
                    if not prof.in_battle():
                        return r
                    continue
                if helpless and b["kind"] == "wild":
                    r = battle("run")
                    if not prof.in_battle():
                        return r
            moves = [n for n, pp in mine["moves"] if pp > 0 and n != mine.get("disabled") and n not in bad_moves]
            pick = policy_move if policy_move in moves else next((m for m in moves if m not in STATUS), moves[0] if moves else "")
            if not trainee and not want and not heal_below and not smart:
                r = battle("auto", pick)                  # routine fight: one call
            else:
                r = battle("fight", pick)
            head = r.split("\n", 1)[0]                     # the helper's own line; the hint below it also mentions battle('switch')
            if turns >= 30 or turns <= 3:
                log("  battle turn", turns, pick, "->", head[:200])
            if "needs a decision" in head:
                if "learn" in head.lower() or "forget" in head.lower() or "delete" in head.lower():
                    log("  learn prompt ->", self.learn_move()[:100])
                else:
                    press("A")
            elif "battle('switch'" in head:
                self.switch_after_faint()
            elif "is DISABLED" in head or head.startswith("no PP left"):
                bad_moves.add(pick)
            elif head.startswith(("could not", "cannot", "no move", "unknown")):
                self.odd("battle helper: " + head[:150])
                press("A")
        if prof.in_battle():
            self.odd("battle did not end in 45 turns")
        return r if turns else "no battle"

    def switch_after_faint(self) -> str:
        """Answer 'Bring out which POKéMON?' with the healthiest alive party member."""
        prof = self.prof
        cur = prof._u8(0xCC2F)
        alive = sorted(((p["hp"] / max(p["max_hp"], 1), i) for i, p in enumerate(prof.party()) if p["hp"] > 0 and i != cur), reverse=True)
        r = ""
        for _, i in alive[:3]:
            r = self.battle("switch", str(i + 1)).split("\n", 1)[0]
            self.log("  switch after faint ->", r[:120])
            if "already out" not in r and "no will to fight" not in r and "fainted" not in r.split("—")[0]:
                return r
        if not alive:
            self.press("A*3")
        return r

    def learn_move(self) -> str:
        """Answer a 'learn new move' prompt: yes, forgetting the first status move (else the first move)."""
        prof, press = self.prof, self.press
        press("A")                                          # YES: delete an older move
        for _ in range(6):
            txt = prof.screen_text() or ""
            d = prof.dialog_text()
            if "▶" in txt and ("forgotten" in d or "Which move" in d):
                idx = prof._u8(0xCC2F) if prof.in_battle() else 0
                party = prof.party()
                mon = party[idx] if idx < len(party) else (party[0] if party else None)
                names = [n for n, _ in mon["moves"]] if mon else []
                k = next((i for i, n in enumerate(names) if n in STATUS), 0)
                cur = prof._list_cursor(txt, [prof._norm(n) for n in names]) or 0
                steps = k - cur
                if steps:
                    press(("DOWN " if steps > 0 else "UP ") * abs(steps))
                press("A")
                return f"forgot {names[k] if names else '?'}"
            if "▶YES" in txt or "▶NO" in txt:
                press("A")
                continue
            if d:
                press("A")
                continue
            break
        return "learned"

    def go(self, target, **bk):
        """walk to a target; auto-resolve battles/dialogue on the way. Returns the last walk text."""
        prof = self.prof
        r = ""
        for _ in range(20):
            r = self.walk(target)
            if prof.in_battle():
                self.resolve_battle(**bk)
                continue
            if "cannot walk" in r and "text" in r:
                t = self.talk()
                if t.startswith("choice"):
                    self.odd("choice during travel: " + t[:100])
                    self.press("B")
                continue
            if "dialogue appeared" in r:
                self.skip_text()
                if prof.in_battle():
                    self.resolve_battle(**bk)
                continue
            if r.startswith(("'", "arrived", "went toward", "walked", "already")):
                if "stopped: blocked" in r:
                    self.odd(f"blocked going {target}: {r[:120]}")
                    return r
                if "could not get closer" in r:
                    self.odd(f"could not reach {target}: {r[:700]}")
                    return r
                return r
            self.odd(f"walk({target!r}) -> {r[:140]}")
            return r
        self.odd(f"gave up going {target}")
        return r

    def travel(self, map_name, **bk):
        """Go to a named map (through explored maps), resolving battles/dialogue on the way."""
        prof = self.prof
        for _ in range(14):
            m = prof.position()[0]
            if _norm(D.map_name(m)) == _norm(map_name):
                return True
            r = self.go(f"to {map_name}", **bk)
            if "no explored route" in r or "unknown place" in r:
                self.odd(f"travel to {map_name} failed from {self.state()}: {r[:100]}")
                return False
        m = prof.position()[0]
        return _norm(D.map_name(m)) == _norm(map_name)

    def heal_at(self, center_name):
        prof = self.prof
        city = CITY_OF[center_name]
        if _norm(D.map_name(prof.position()[0])) not in (_norm(city), _norm(center_name)):
            self.travel(city)
        if _norm(D.map_name(prof.position()[0])) != _norm(center_name):
            self.go(f"to {center_name}")
        self.go("to 3,4")
        self.press("UP:2")
        r = self.talk()
        if "HEAL" in r:
            self.press("A")
            r = self.talk()
        if "fighting fit" not in r:
            self.odd("heal text odd: " + r[:120])
        self.go("to outside")

    def finish(self, label="DONE"):
        rep = self.call("metrics", action="finalize")
        self.log(rep.splitlines()[0])
        self.log(label, "in", f"{time.time() - self.t_start:.0f}s, {self.calls} tool calls, {len(self.ODD)} oddities")
        for o in self.ODD:
            self.log("  -", o)
