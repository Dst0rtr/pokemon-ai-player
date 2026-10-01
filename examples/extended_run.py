"""
Extended scripted run: from the Boulder Badge through Mt. Moon to Cerulean City and the Cascade
Badge (Misty), using only the public tool functions. Like reference_run.py it is a regression run:
every unexpected reply is logged as an ODD line and the script ends with "N oddities".

    python examples/extended_run.py path/to/pokemon-red.gb [after-brock.state] [seed-frames]

The start state defaults to saves/<rom stem>/after-brock.state next to the ROM (a local file made by
a previous run; not in the repository). Exercises: trainer intercepts on Route 3, cave ladders and
elevation steps in Mt. Moon, the world graph across many maps, heals at three Poké Centers, in-battle
Potions on a switched-in Pokémon, and Misty. Saves after-misty.state next to the start state.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging; logging.basicConfig(level="WARNING", stream=sys.stderr)  # noqa: E702
from emulator import Emulator  # noqa: E402
from _agentlib import ScriptedAgent, FIRE, _norm  # noqa: E402
from games import gen1_data as D  # noqa: E402

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)
ROM_SRC = sys.argv[1]
STATE = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].endswith(".state") else \
    os.path.join(os.path.dirname(os.path.abspath(ROM_SRC)), "saves", os.path.splitext(os.path.basename(ROM_SRC))[0], "after-brock.state")
SEED = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 0
if not os.path.exists(STATE):
    print(f"start state not found: {STATE}\nrun examples/reference_run.py first, or pass a .state file")
    sys.exit(2)

WORK = tempfile.mkdtemp(prefix="extended_run_")
ROM = os.path.join(WORK, "rom.gb")
shutil.copy(ROM_SRC, ROM)
emu = Emulator(ROM, base_dir=WORK, autosave_every=25, save_screenshots=False, ai_model=f"extended{SEED}")
emu.boot()
with open(STATE, "rb") as f:
    emu.pyboy.load_state(f)
emu.tick(2 + SEED)
emu.profile.after_load()
A = ScriptedAgent(emu)
prof = emu.profile
press, walk, talk, battle, state, shop, manage = A.press, A.walk, A.talk, A.battle, A.state, A.shop, A.manage
log, odd, skip_text, go, travel, heal_at = A.log, A.odd, A.skip_text, A.go, A.travel, A.heal_at

BK = dict(smart=True, heal_below=0.3)          # battle policy: switch/heal sensibly


def at(map_name):
    return _norm(D.map_name(prof.position()[0])) == _norm(map_name)


def lead_strongest():
    best = max(prof.party(), key=lambda p: (p["hp"] > 0, p["level"]))
    if prof.party()[0]["species"] != best["species"]:
        log("  lead ->", manage("lead", best["species"])[:80])


def need_heal():
    party = prof.party()
    alive = [p for p in party if p["hp"] > 0]
    return len(alive) <= 1 or any(p["status"] == "PSN" for p in party) or sum(p["hp"] for p in party) < sum(p["max_hp"] for p in party) * 0.4


def buy(item, qty, center_city, mart):
    travel(mart, **BK)
    go("to 2,5")
    press("LEFT:2")
    r = shop(item, qty)
    log(f"  shop {item}: {r[:90]}")
    if "bought" not in r:
        odd(f"could not buy {item}: {r[:120]}")
    press("B*3")
    go("to outside")


log("START", state())
log(state("party"))
# ---------------------------------------------------------------- Stage 1: Pewter -> Mt. Moon -> Cerulean
if at("Pewter Gym"):                              # still inside Pewter Gym
    go("to outside")
heal_at("Pewter Poké Center")
buy("Potion", 4, "Pewter City", "Pewter Mart")
lead_strongest()
travel("Route 3", **BK)
travel("Route 4", **BK)
log("route 4:", state())
if need_heal():
    heal_at("Mt. Moon Poké Center")
travel("Mt. Moon 1F", **BK)
# 1F: the top-left ladder (5,5) -> B1F (5,5) pocket -> ladder (21,17) -> B2F -> ladder (5,7) -> B1F exit pocket -> (27,3)
go("to 5,5", **BK)
if not at("Mt. Moon B1F"):
    odd("not on Mt. Moon B1F after the first ladder: " + state())
go("to 21,17", **BK)
if not at("Mt. Moon B2F"):
    odd("not on Mt. Moon B2F: " + state())
log("B2F:", state())
# The two fossils at (12,6)/(13,6) block the passage to the exit until the Super Nerd at (12,8) is beaten
# and one fossil is taken (he keeps the other).
go("to 13,8", **BK)                               # he usually spots us and the fight happens on the way
if not prof.in_battle():
    press("LEFT:2")
    r = talk()
    log("  nerd:", r[:100])
if prof.in_battle():
    A.resolve_battle(**BK)
skip_text()
go("to 12,7", **BK)
press("UP:2")
r = talk()
if "choice" in r:
    press("A")                                    # YES: take the Helix Fossil
    skip_text()
else:
    odd("fossil prompt missing: " + r[:120])
if "Fossil" not in state("items"):
    odd("no fossil in the bag: " + state("items"))
go("to 5,7", **BK)                                # exit ladder, up to B1F's exit pocket
if not at("Mt. Moon B1F"):
    odd("not back on B1F after B2F: " + state())
go("to 27,3", **BK)
log("out of Mt. Moon:", state())
if not at("Route 4"):
    odd("not on Route 4 after Mt. Moon: " + state())
go("to Cerulean City", **BK)                      # Route 4's east edge (a connection, not yet in the world graph)
if not at("Cerulean City"):
    travel("Cerulean City", **BK)
log("STAGE 1 done:", state(), state("party"))
manage("save")
with open(os.path.join(os.path.dirname(STATE), "cerulean.state"), "wb") as f:
    emu.pyboy.save_state(f)                       # local checkpoint for probing (gitignored)

# ---------------------------------------------------------------- Stage 2: Nugget Bridge and Route 25 (experience)
heal_at("Cerulean Poké Center")
lead_strongest()
go("to Route 24", **BK)                           # north edge of Cerulean (the rival ambushes here)
for _ in range(3):
    if at("Route 24"):
        break
    travel("Route 24", **BK)
for _ in range(4):                                # across Nugget Bridge (five trainers and a Rocket) to Route 25's edge
    if not at("Route 24"):
        break
    r = go("to Route 25", **BK)
    log("  bridge:", r[-120:])
log("after the bridge:", state(), state("party"))
if at("Route 25"):
    go("to Bill's House", **BK)                   # Route 25's trainers line the way
    log("Route 25 done:", state())
if need_heal():
    heal_at("Cerulean Poké Center")
travel("Cerulean City", **BK)
heal_at("Cerulean Poké Center")
buy("Potion", 6, "Cerulean City", "Cerulean Mart")              # Cerulean sells no Super Potions
lead_strongest()
log("before Misty:", state(), state("party"))

# ---------------------------------------------------------------- Stage 3: Misty


def misty_fight():
    turns, r = 0, ""
    while prof.in_battle() and turns < 45:
        turns += 1
        b = prof.battle()
        if b is None or b["mine"]["max_hp"] == 0:
            press("A")
            continue
        me = b["mine"]
        potion = next((n for n, _ in prof.items() if "Potion" in n), None)
        if me["hp"] < me["max_hp"] * 0.4 and potion and me["species"] in FIRE:
            r = battle("item", potion)
            log("  misty turn", turns, "potion:", r[:120])
        else:
            moves = [n for n, pp in me["moves"] if pp > 0 and n != me.get("disabled")]
            pick = next((m for m in ("Slash", "Scratch", "Confusion", "Gust", "Tackle", "Ember") if m in moves), "")
            r = battle("fight", pick)
            log("  misty turn", turns, pick, "->", r[:160])
        if "battle('switch'" in r:
            alive = [i + 1 for i, p in enumerate(prof.party()) if p["hp"] > 0]
            if alive:
                battle("switch", str(alive[0]))
        elif "needs a decision" in r:
            press("DOWN A")
    return r


def approach_misty():
    """Misty stands at (4,2) on her platform. The trainer guarding row 3 walks over and parks on (4,3),
    the cell below Misty, so approach from (5,2) beside her and face left."""
    for attempt in range(6):
        go("to 7,3", **BK)
        go("to 5,2", **BK)
        if prof.in_battle():
            A.resolve_battle(**BK)
            skip_text()
            continue
        if prof.position()[1:] == (5, 2):
            press("LEFT:2")
            return True
        A.call("wait", frames=180, screenshot=False)
    odd("could not stand next to Misty: " + state() + "\n" + state("map"))
    return False


for attempt in range(3):
    travel("Cerulean Gym", **BK)
    if not at("Cerulean Gym"):
        continue
    if not approach_misty():
        break
    if need_heal():
        go("to outside"); heal_at("Cerulean Poké Center"); travel("Cerulean Gym", **BK); approach_misty()
    r = talk()
    if not prof.in_battle():
        A.until(lambda: press("A"), "BATTLE", 6, "misty")
    r = misty_fight()
    log("misty:", r[:200])
    skip_text(); skip_text()
    if prof.badges() >= 2:
        break
    log("  lost to Misty, retrying")
    heal_at("Cerulean Poké Center")
log("RESULT badges:", prof.badges(), state(), state("party"))
if prof.badges() >= 2:
    out = os.path.join(os.path.dirname(STATE), "after-misty.state")
    with open(out, "wb") as f:
        emu.pyboy.save_state(f)
    log("saved", out)
else:
    log("no Cascade Badge: Misty won (a game outcome, not a tool anomaly); the tools were exercised all the way")
A.finish()
emu.stop()
