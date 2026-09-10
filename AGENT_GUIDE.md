# Agent Guide: playing efficiently

The server sends the model a short version of this guide as MCP *instructions*. This page is the
long version for humans writing prompts, and for agents that want the details.

## The cost model

Every tool call costs a full model turn (the whole context is re-read). Tool *results* are cheap
by comparison: a 2x screenshot is about 120 tokens, a status line plus screen text about 50-150.
So the goal is **fewer, bigger calls**. Prefer goals (`walk("to Pewter Gym")`, `battle("auto")`,
`talk()`) over steps (`press("UP")`), and read what comes back instead of asking again.

## What every action returns

```
pressed A*3
f12345 Pallet Town (5,6) facing down | Charmander L5 19/19 (+Pidgey L4) | ¥3000 | 0 badges
EVENT: obtained: Pidgey
screen:
▶NEW GAME
 OPTION
hint: a menu is open: UP/DOWN then A, or B to close
```

* **status line**: frame, map, coordinates, facing, party (lead in detail, the rest briefly),
  money, badges. In a battle it shows both active Pokémon, your moves with PP, and which prompt
  is active (`menu: FIGHT/PKMN/ITEM/RUN`, `menu: choose a move`, `text: press A`, `animating`).
* **EVENT** lines: milestones the metrics tracker just recorded.
* **screen**: the on-screen text decoded from video memory. After a `walk` with no text on screen
  you get the map instead (the whole area the first time you enter it, a 10x9 window afterwards).
* **hint**: appears only when the game is waiting for an answer or something needs attention
  (YES/NO prompt, HEAL/CANCEL, choose a Pokémon, shop menu, cutscene running, poison, out of PP).
* an **image** only when the screen changed since the last one; `(screen image unchanged)`
  otherwise. Pass `screenshot=false` when the text is enough. `screen("text")` re-reads cheaply.

## Tool cheat sheet

```
walk("to Viridian Mart")                 # named exit on this map (doors are entered automatically)
walk("to Pewter City", on_battle="run")  # cross-map travel through maps you have visited; flee wild battles
walk("to north edge")                    # leave by a map edge
walk("to 23,25")                         # coordinates from state("map")
walk("up 5, right 3")                    # explicit steps
talk()                                   # face an NPC/sign/nurse/PC/clerk; reads the whole conversation
battle("auto", "Ember")                  # a whole routine battle; stops at questions or low HP
battle("fight", "Ember")                 # one turn; battle("run"), battle("switch", 2), battle("item", "Poké Ball")
shop("Potion", 3)                        # facing the clerk; reports money and bag
manage("lead", "Butterfree")             # party order; manage("swap", 2, 3)
manage("use", "Potion", "Charmander")    # items outside battle
manage("save")                           # in-game save (battery); save_state("name") is an emulator snapshot
state("map" | "nearby" | "party" | "battle" | "items" | "full")
press("A*4 DOWN A W30")                  # raw input when nothing else fits
```

Press script tokens: `A B START SELECT UP DOWN LEFT RIGHT` (or `U D L R`), `X*N` repeat,
`X:frames` hold, `Wframes` wait. Max 100 presses per call. Each press waits for text and
animations to finish, so `A*5` really advances five text boxes.

## Answering the game

`talk()`, `battle()`, `shop()` and `manage()` never guess: they stop at every question and say so.
Answer with `press("A")` (YES / first option) or `press("DOWN A")` (NO / second option), then
continue. Common questions: keep a nickname? learn a new move? (a YES/NO, then a move to forget),
"Bring out which Pokémon?" (answer with `battle("switch", n)`), HEAL/CANCEL at the nurse.

## Maps and movement (Pokémon)

* Legend: `P` you, `N` NPC, `D` door/warp, `#` blocked, `.` walkable, `,` tall grass (wild
  encounters), `v` `<` `>` one-way ledges (you can only jump across in that direction; the
  pathfinder uses them). The map header lists `exits:` with destinations and `connections:` to
  neighbouring maps by edge.
* `walk("to x,y")` plans a route on the current map, avoids NPCs and prefers paths without tall
  grass, re-plans if someone steps in the way, and enters doors on arrival.
* `walk("to <map name>")` routes hop by hop through maps the server has seen you visit. For a map
  you have never entered, name the next hop instead (an exit or an edge such as `to Route 2`).
* A walk stops early and says why: `blocked`, `entered Viridian City`, `battle started`,
  `dialogue appeared`, or `cannot walk` when a text box, menu, battle or cutscene is active.
  `on_battle="run"` flees wild battles and continues; `"auto"` fights them. Trainer battles are
  always fought.
* Walking while poisoned costs HP every few steps. Heal (nurse or Antidote) before long trips;
  the hint line warns you.

## Battles (Pokémon)

* `battle("auto")` picks damaging moves with PP left and keeps attacking until the battle ends, a
  question appears, or your Pokémon drops to a quarter of its HP. Call it again to continue, or
  switch, use an item, or run.
* `battle("fight", "<move>")` refuses a move with no PP and lists the usable ones; with every move
  empty the game uses Struggle.
* Results include the battle messages and HP before/after: `Critical hit! | Enemy PIDGEY fainted!
  (enemy 13→0, you 19→17)`.
* Losing every Pokémon blacks you out: you wake at the last Poké Center with half your money.
  The `EVENT: blacked out` line and a money drop tell you it happened.

## Towns (Pokémon)

* Poké Center: walk to the counter, face the nurse, `talk()`, answer HEAL with `press("A")`, then
  `talk()` again. The PC is the object in the top-right corner: stand below it, face up, `talk()`.
  `state("party")` also lists the current PC box.
* Poké Mart: stand in front of the clerk (usually left of you behind the counter), then
  `shop("Poké Ball", 5)`; press `B` to leave the shop menu.
* Signs, NPCs and items: face them and `talk()`.

## Game options

Text speed FAST, battle animations OFF and battle style SET are applied automatically (the same
settings the OPTION menu offers), so text is quick and trainers never ask "change Pokémon?".
Start the server with `--no-fast-text` to keep the game's defaults.

## Checkpoints

```
save_state("before-brock")
load_state("before-brock")
load_state("list")
```

An `autosave` slot is written every 20 actions and on shutdown; start the server with `--resume`
to continue from it. `manage("save")` is the in-game save, which persists across server restarts
as the battery file.

## Metrics

Milestones (badges, captures, evolutions, landmarks, black-outs, Hall of Fame) are recorded
automatically together with tool-call and image counts. Add your own with
`metrics("milestone", "beat Brock")` and finish with `metrics("finalize")`.
See [BENCHMARKING.md](BENCHMARKING.md).

## A worked opening (about 15 calls)

```
press("W600")  then press("A") until the menu shows NEW GAME; press("A")
press("A") until NEW NAME appears; press("DOWN A")           # pick a preset name (twice)
press("A") until the bedroom appears; talk()                 # first text box
walk("to 7,1")  →  walk("to outside")                        # stairs, then the front door
walk("to Route 1")                                           # Oak stops you: dialogue appeared
talk()                                                       # the whole cutscene into the lab
walk("to 6,4"); press("UP:2"); talk(); press("A")            # first Poké Ball, YES
talk(); press("DOWN A")                                      # no nickname
walk("to 4,11")  →  battle("auto")                           # the rival ambush
```

## Sample system prompt

> You are playing Pokémon Red through the `gameboy` MCP server. Read the server instructions.
> Use goals, not steps: `walk("to ...")`, `talk()`, `battle("auto")`, `shop`, `manage`. Trust the
> returned text, map and hints; take a screenshot only when the text is ambiguous. Keep your
> Pokémon healthy (heal when low or poisoned), `save_state` before gyms, and call
> `metrics("finalize")` when you stop.
