"""
Reference agent: plays Pokémon Red from power-on to the Boulder Badge using only the public
tool functions (the same ones the MCP server exposes). It is a scripted strategy, not an LLM,
and doubles as an end-to-end regression run: every unexpected tool reply is logged as an ODD line.

    python examples/reference_run.py path/to/pokemon-red.gb [seed-frames]

Strategy: Charmander -> parcel -> 5 Poké Balls -> level to 12 in Viridian Forest -> catch a
Caterpie/Metapod -> level it as lead to Butterfree with Confusion -> Pewter -> Brock.
Runs in about a minute; writes metrics/saves under ./reference_run_data next to the ROM copy.
"""
import sys, os, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging; logging.basicConfig(level="WARNING", stream=sys.stderr)
from emulator import Emulator
from _agentlib import ScriptedAgent, BUGS, FIRE, out_of_pp

if len(sys.argv) < 2:
    print(__doc__); sys.exit(1)
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 0
WORK = tempfile.mkdtemp(prefix="reference_run_")
ROM = os.path.join(WORK, "rom.gb")
shutil.copy(sys.argv[1], ROM)                       # a copy, so the run never touches your battery save
emu = Emulator(ROM, base_dir=WORK, autosave_every=25, save_screenshots=False, ai_model=f"reference{SEED}")
emu.boot()
A = ScriptedAgent(emu)
prof = emu.profile
press, walk, talk, battle, state, shop, manage, call = A.press, A.walk, A.talk, A.battle, A.state, A.shop, A.manage, A.call
log, odd, until, skip_text, resolve_battle, go, travel, heal_at = A.log, A.odd, A.until, A.skip_text, A.resolve_battle, A.go, A.travel, A.heal_at
t_start = A.t_start

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
A.finish()
emu.stop()
