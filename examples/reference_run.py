"""
Reference agent: plays Pokémon Red from power-on to the Boulder Badge using only the public
tool functions (the same ones the MCP server exposes). It is a scripted strategy, not an LLM,
and doubles as an end-to-end regression run: every unexpected tool reply is logged as an ODD line.

    python examples/reference_run.py path/to/pokemon-red.gb [seed-frames]

Strategy: Charmander -> parcel -> 5 Poké Balls -> level to 12 in Viridian Forest -> catch a
Caterpie/Metapod -> level it as lead to Butterfree with Confusion -> Pewter -> Brock.
Runs in about a minute; writes metrics/saves under ./reference_run_data next to the ROM copy.
"""
import sys, os, time, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging; logging.basicConfig(level="WARNING", stream=sys.stderr)
from emulator import Emulator
from server import build_server
from games import gen1_data as D

if len(sys.argv) < 2:
    print(__doc__); sys.exit(1)
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 0
WORK = tempfile.mkdtemp(prefix="reference_run_")
ROM = os.path.join(WORK, "rom.gb")
shutil.copy(sys.argv[1], ROM)                       # a copy, so the run never touches your battery save
emu = Emulator(ROM, base_dir=WORK, autosave_every=25, save_screenshots=False, ai_model=f"reference{SEED}")
emu.boot()
T = {n: t.fn for n, t in build_server(emu)._tool_manager._tools.items()}
prof = emu.profile
ODD, CALLS = [], [0]
STATUS = {"Growl", "Tail Whip", "String Shot", "Leer", "Sand-Attack", "Harden", "PoisonPowder", "Stun Spore", "Sleep Powder"}
BUGS = ("Caterpie", "Metapod", "Butterfree"); FIRE = ("Charmander", "Charmeleon", "Charizard")
def out_of_pp(p): return all(pp == 0 for n, pp in p["moves"] if n not in STATUS)
t_start = time.time()

def txt(res): return "\n".join(c.text for c in res if c.type == "text")
def call(name, **kw):
    CALLS[0] += 1
    kw.setdefault("screenshot", False) if name in ("press", "walk", "battle", "talk", "wait") else None
    return txt(T[name](**kw))
def press(b): return call("press", buttons=b)
def walk(p): return call("walk", path=p)
def talk(): return call("talk")
def battle(a, t=""): return call("battle", action=a, target=t)
def state(s="summary"): return call("state", section=s)
def shop(i, q): return call("shop", item=i, qty=q)
def manage(a, t="", t2=""): return call("manage", action=a, target=t, target2=t2)
def log(*a): print(f"[{time.time()-t_start:6.1f}s #{CALLS[0]}]", *a, flush=True)
def odd(what): ODD.append(what); log("ODD:", what)

def until(fn, needle, tries=30, label=""):
    out = ""
    for _ in range(tries):
        out = fn()
        if needle in out: return out
    odd(f"never saw {needle!r} ({label}); last: {out[:160]!r}")
    return out

def skip_text(max_n=40):
    for _ in range(max_n):
        if not prof.is_text_visible() or prof.in_battle(): return
        r = talk()
        if r.startswith("choice"):
            odd("unexpected choice while skipping text: " + r[:120]); press("B"); return
    odd("text never ended: " + (prof.screen_text() or "")[:100].replace("\n", "|") + " @ " + state())

def resolve_battle(policy_move=None, trainee=None, strong=None, want=None):
    turns = 0
    while prof.in_battle() and turns < 45:
        turns += 1
        b = prof.battle()
        if b is None or b["mine"]["max_hp"] == 0 or b["mine"]["species"].startswith("MissingNo"):
            press("A"); continue
        mine = b["mine"]
        party = prof.party()
        dmg_pp = sum(pp for n, pp in mine["moves"] if n not in STATUS)
        if trainee and mine["species"] in trainee and (mine["hp"] < mine["max_hp"] * 0.5 or dmg_pp == 0):
            idx = next((i + 1 for i, p in enumerate(party) if p["species"] in strong and p["hp"] > 0), None)
            if idx:
                r = battle("switch", str(idx))
                if "battle over" in r or not prof.in_battle(): return r
                continue
            if dmg_pp == 0:                            # helpless trainee and nobody to switch to: flee
                r = battle("run")
                if not prof.in_battle(): return r
        if want and b["enemy"]["species"] in want and any("Ball" in n for n, _ in prof.items()):
            r = battle("item", "Poké Ball")           # tiny bugs: throw right away
            log("  throw:", r[:120])
            if "needs a decision" in r:                # nickname prompt
                press("DOWN A")
                return r
            continue
        moves = [n for n, pp in mine["moves"] if pp > 0]
        pick = policy_move if policy_move in moves else next((m for m in moves if m not in STATUS), moves[0] if moves else "")
        if not trainee and not want:
            r = battle("auto", pick)                  # routine fight: one call
        else:
            r = battle("fight", pick)
        if turns >= 30: log("  long battle turn", turns, r[:160])
        if "needs a decision" in r:
            if "learn" in r.lower() or "forget" in r.lower():
                press("DOWN A")                       # don't learn, keep moves (simplest)
                r2 = press("A")
                log("  learn prompt ->", r2[:80])
            else:
                press("A")
        elif "battle('switch'" in r:
            alive = [i + 1 for i, p in enumerate(prof.party()) if p["hp"] > 0]
            if alive: battle("switch", str(alive[0]))
            else: press("A*3")
        elif r.startswith(("could not", "cannot", "no move", "unknown")):
            odd("battle helper: " + r[:150]); press("A")
    if prof.in_battle(): odd("battle did not end in 45 turns")
    return r if turns else "no battle"

def go(target, **bk):
    """walk to a target; auto-resolve battles/dialogue on the way. Returns the last walk text."""
    for _ in range(12):
        r = walk(target)
        if prof.in_battle():
            resolve_battle(**bk); continue
        if "cannot walk" in r and "text" in r:
            t = talk()
            if t.startswith("choice"): odd("choice during travel: " + t[:100]); press("B")
            continue
        if "dialogue appeared" in r:
            skip_text()
            if prof.in_battle(): resolve_battle(**bk)
            continue
        if r.startswith(("'", "arrived", "went toward", "walked", "already")):
            if "stopped: blocked" in r: odd(f"blocked going {target}: {r[:120]}"); return r
            if "could not get closer" in r: odd(f"could not reach {target}: {r[:700]}"); return r
            return r
        odd(f"walk({target!r}) -> {r[:140]}"); return r
    odd(f"gave up going {target}"); return r

def travel(map_name, **bk):
    """Go to a named map (through explored maps), resolving battles/dialogue on the way."""
    for _ in range(14):
        m = prof.position()[0]
        if _norm(D.map_name(m)) == _norm(map_name): return True
        r = go(f"to {map_name}", **bk)
        if "no explored route" in r or "unknown place" in r:
            odd(f"travel to {map_name} failed from {state()}: {r[:100]}"); return False
    m = prof.position()[0]
    return _norm(D.map_name(m)) == _norm(map_name)

def _norm(x): return "".join(c for c in x.lower() if c.isalnum())

CITY_OF = {"Viridian Poké Center": "Viridian City", "Pewter Poké Center": "Pewter City"}
def heal_at(center_name):
    city = CITY_OF[center_name]
    if _norm(D.map_name(prof.position()[0])) not in (_norm(city), _norm(center_name)):
        travel(city)
    if _norm(D.map_name(prof.position()[0])) != _norm(center_name):
        go(f"to {center_name}")
    go("to 3,4"); press("UP:2")
    r = talk()
    if "HEAL" in r: press("A"); r = talk()
    if "fighting fit" not in r: odd("heal text odd: " + r[:120])
    go("to outside")

# ---------------------------------------------------------------- intro
press(f"W{600 + SEED}")
until(lambda: press("A"), "NEW GAME", label="menu")
until(lambda: press("A"), "NEW NAME", label="name")
press("DOWN A")
until(lambda: press("A"), "NEW NAME", label="rival")
press("DOWN A")
until(lambda: press("A"), "Red's House 2F", label="start")
skip_text()
log(state())
go("to 7,1"); go("to outside")
if prof.position()[0] != 0: odd("not in Pallet Town after leaving house: " + state())
r = walk("to Route 1")                   # Oak interrupts
if "dialogue" not in r: odd("Oak did not interrupt: " + r[:100])
r = talk(); log("oak:", r[:100])         # whole cutscene incl. the walk to the lab
if prof.position()[0] != 40: odd("expected Oak's Lab, got " + state())
skip_text()
go("to 6,4"); press("UP:2")             # first ball (Charmander) at (6,3)
r = talk()
if "choice" not in r or "YES" not in r: odd("starter prompt: " + r[:120])
press("A")                               # YES: take it
r = talk()
if "choice" not in r: odd("nickname prompt: " + r[:120])
press("DOWN A")                          # no nickname
if "Charmander" not in state("party"): odd("no Charmander: " + state("party"))
skip_text()
r = go("to 4,11")                        # rival stops us on the way out -> battle
if prof.in_battle(): resolve_battle()
skip_text()
if prof.position()[0] == 40: go("to 4,11")
if prof.position()[0] not in (0, 37, 38): odd("unexpected place after lab: " + state())
travel("Pallet Town")
manage("save")

# ---------------------------------------------------------------- to Viridian, parcel, back
travel("Route 1"); travel("Viridian City"); travel("Viridian Mart"); go("to 2,5"); press("LEFT:2")
if not prof.is_text_visible(): talk()
skip_text()
if "Parcel" not in state("items"): odd("no parcel: " + state("items"))
go("to outside")
travel("Route 1"); travel("Pallet Town"); travel("Oak's Lab"); go("to 5,3"); press("UP:2")
r = talk(); log("oak parcel:", r[:80]); skip_text()
if "Parcel" in state("items"): odd("parcel not delivered")
go("to 4,11")
travel("Route 1"); heal_at("Viridian Poké Center")
travel("Viridian Mart"); go("to 2,5"); press("LEFT:2")
r = shop("Poké Ball", 5); log(r[:120])
if "bought 5" not in r: odd("shop: " + r[:120])
press("B*3"); go("to outside")
manage("save")

# ---------------------------------------------------------------- forest: level Charmander, catch Caterpie
def leave_forest():
    travel("Viridian City")

def to_forest():
    if prof.position()[0] == 51: return
    if prof.position()[0] in (1, 41, 42): travel("Route 2")
    if prof.position()[0] == 13: travel("Viridian Forest South Gate")
    travel("Viridian Forest")
    if prof.position()[0] != 51: odd("could not get back to the forest: " + state())

def forest_loop(stop, **bk):
    fights = 0
    for _ in range(260):
        if stop(): return fights
        if bk.get("want") and not any("Ball" in n for n, _ in prof.items()):
            if prof.money() < 400: odd("no balls and no money"); return fights
            leave_forest(); heal_at("Viridian Poké Center")
            go("to Viridian Mart"); go("to 2,5"); press("LEFT:2"); log("  rebuy:", shop("Poké Ball", 5)[:60]); press("B*3"); go("to outside")
        to_forest()
        if bk.get("trainee") and prof.party()[0]["species"] not in bk["trainee"]:
            tr = next((p["species"] for p in prof.party() if p["species"] in bk["trainee"]), None)
            if tr: log("  lead ->", manage("lead", tr)[:60])
        lead = prof.party()[0]
        strong = next((p for p in prof.party() if p["species"] in FIRE), lead)
        if strong["hp"] < strong["max_hp"] * 0.35 or any(p["status"] == "PSN" for p in prof.party()) or out_of_pp(strong):
            leave_forest(); heal_at("Viridian Poké Center")
            to_forest()
        for p in ("1,8", "1,16"):
            r = walk(f"to {p}")
            if prof.in_battle():
                fights += 1; resolve_battle(**bk)
            elif "cannot walk" in r and "text" in r:
                skip_text()
                if prof.in_battle(): fights += 1; resolve_battle(**bk)
            if stop(): return fights
    odd("forest loop hit its cap")
    return fights

travel("Route 2"); travel("Viridian Forest South Gate"); travel("Viridian Forest")
if prof.position()[0] != 51: odd("not in forest: " + state())
n = forest_loop(lambda: prof.party()[0]["level"] >= 12); log("charmander grind fights:", n, state())
n = forest_loop(lambda: any(p["species"] in ("Caterpie", "Metapod") for p in prof.party()), want=("Caterpie", "Metapod"))
log("catch fights:", n, state("party"))
bug = next((p["species"] for p in prof.party() if p["species"] in ("Caterpie", "Metapod")), None)
if not bug: odd("no bug caught")
else:
    r = manage("lead", bug); log(r)
    def bug_ready():
        b = next((p for p in prof.party() if p["species"] in ("Caterpie", "Metapod", "Butterfree")), None)
        return b is not None and b["species"] == "Butterfree" and any(m == "Confusion" for m, _ in b["moves"])
    n = forest_loop(bug_ready, trainee=BUGS, strong=FIRE)
    if not bug_ready(): odd("Butterfree not ready: " + state("party"))
    if prof.party()[0]["species"] not in BUGS: manage("lead", next(p["species"] for p in prof.party() if p["species"] in BUGS))
    # keep the bug leading through evolutions (species name changes)
    log("bug grind fights:", n, state("party"))

# ---------------------------------------------------------------- Pewter and Brock
travel("Viridian Forest North Gate"); travel("Route 2"); travel("Pewter City")
heal_at("Pewter Poké Center")
travel("Pewter Mart"); go("to 2,5"); press("LEFT:2"); log("  potions:", shop("Potion", 3)[:80]); press("B*3"); go("to outside")
bf = next((p["species"] for p in prof.party() if p["species"] == "Butterfree"), None)
if bf: log("  lead ->", manage("lead", "Butterfree")[:60])

def brock_fight():
    turns = 0; r = ""
    while prof.in_battle() and turns < 40:
        turns += 1
        b = prof.battle()
        if b is None or b["mine"]["max_hp"] == 0: press("A"); continue
        me = b["mine"]
        if me["species"] == "Butterfree" and me["hp"] < me["max_hp"] * 0.45 and any("Potion" in n for n, _ in prof.items()):
            r = battle("item", "Potion"); log("  brock turn", turns, "potion:", r[:120]); continue
        r = battle("fight", "Confusion" if me["species"] == "Butterfree" else "")
        log("  brock turn", turns, r[:160])
        if "battle('switch'" in r:
            alive = [i + 1 for i, p in enumerate(prof.party()) if p["hp"] > 0]
            if alive: battle("switch", str(alive[0]))
        elif "needs a decision" in r: press("DOWN A")
    return r

for attempt in range(3):
    travel("Pewter Gym"); go("to 4,2")                  # gym trainer intercepts on the way the first time
    if prof.in_battle(): resolve_battle("Confusion")
    if prof.position()[0] != 54: continue
    bfp = next((p for p in prof.party() if p["species"] == "Butterfree"), None)
    if bfp and bfp["hp"] < bfp["max_hp"] * 0.8:
        go("to 4,13"); go("to outside"); heal_at("Pewter Poké Center"); travel("Pewter Gym"); go("to 4,2")
    r = talk()
    if not prof.in_battle(): until(lambda: press("A"), "BATTLE", 6, "brock")
    r = brock_fight(); log("brock:", r[:200])
    skip_text(); skip_text()
    if prof.badges() >= 1: break
    log("  lost to Brock, retrying"); heal_at("Pewter Poké Center")
badges = prof.badges()
log("RESULT badges:", badges, state(), state("party"))
rep = call("metrics", action="finalize")
log(rep.splitlines()[0])
log("DONE in", f"{time.time()-t_start:.0f}s, {CALLS[0]} tool calls, {len(ODD)} oddities")
for o in ODD: log("  -", o)
emu.stop()
