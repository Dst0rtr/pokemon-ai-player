## Summary

The Mt. Moon clusters (B2F 86, B1F 50, 1F 33 low; 21 + 12 stuck) were recorded before `jev_nav` existed: none of their samples has a "follow the map route" option. So I left the route graph alone and fixed four places where it still fails. I checked the server and found that `battle('switch', target)` also accepts a species name and resolves it against the live party, which explains the switch loops.

**1. Battle, low confidence (90) and battle loops (6 + 6).**
- **Diagnosis:** Jev's battle options were nearly indistinguishable, so its probabilities came out flat.
  - Every move had the description "attack with X".
  - Status moves (Growl, Leer, String Shot) sat beside damaging ones.
  - Balls and switches were always offered.
  - With 7–9 options, a top probability of 0.31 gives a confidence of 0.21.
- **Two code bugs** caused the loops:
  - Switches targeted a party slot number. Gen 1 reorders the party mid-battle, so "switch to Butterfree" hit Pidgey ("PIDGEY is already out!") or a fainted Charmeleon ("no will to fight").
  - The active Pokémon was never excluded from the switch list, because `"PIDGEY" != "Pidgey"`.
- **Changes:**
  - Each move is rated in code (type chart × power × same-type bonus × accuracy). The description says "super/not very effective", and the best move is marked "the strongest move against this foe".
  - Status moves are dropped while a damaging move has PP.
  - A switch is offered only when the active Pokémon is under 35% HP or the other Pokémon hits much harder (more than 1.5×).
  - Switches target the species name, and the active Pokémon is excluded case-insensitively.
  - Heal items appear only under 50% HP, and balls only when the party has fewer than 3 Pokémon.
  - Code decides the "run away" criterion: it says "recommended" while healing or when the lead is weak, and "fight" when training.
  - The party is re-read after a switch or a faint, and a refused switch is not offered again.
  - The battle state now includes `enemy_types`.
- **Expected effect:** the loop clusters go away and most battle choices become clear-cut. Some choices will remain close calls; that is a real limit of Jev, not something code can fix.

**2. Route 3 (23 low + 5 loop at (63,0)).**
- **Diagnosis:**
  - The server's "to north edge" and "to Route 4" both stop at (63,0), and the cell across that edge is solid.
  - `_edge_arrival` accepted any in-bounds arrival cell, so the static graph could pick that same bad crossing.
  - Edge hops in the nav were still executed as "to <side> edge", which lets the server choose the cell.
  - Edge hops were keyed by side, but `route()` checks blocked hops by coordinates, so a failed edge hop was never actually blocked.
- **Changes:**
  - An edge crossing must land on a walkable cell.
  - An edge hop now walks to its own cell, then takes one step across.
  - All hops use the same coordinate key, and a hop is blocked when the player reaches the warp or edge cell without changing map.

**3. Route graph gaps (Mt. Moon remainder).**
- **Diagnosis:** after arriving on a ladder, its option resolved to "walk to x,y", which only returned "already at". Many samples show this.
- **Changes:**
  - A warp the player is standing on is taken by stepping off and back on.
  - `nav_taken` is keyed from the label, so these warps are counted too.
  - With a known route and no stuck recovery, the four blind "walk d 4 tiles" options are dropped.
  - The objective text now says "take the 'follow the map route' option" instead of "ladders down, then up", which the samples show was pushing choices toward B2F.
  - `INSTRUCTIONS` referred to a nonexistent `situation` field; it now explains the route option.

**4. Healing at the Poké Center (11 low + 5 loop).**
- **Diagnosis:**
  - The nurse stands behind the counter, and the generic talk-to option tried to reach her from (4,1), which has no route.
  - Jev ended up talking to the Cable Club clerk, the phone guy and Jigglypuff.
  - Separately, while healing the nav aimed at the farthest Poké Center (the last target).
- **Changes:**
  - A code option walks to (3,3), faces up and talks; every Gen 1 Poké Center has this layout. While healing in a Poké Center it replaces the other talk-to options.
  - While healing, the nav goal is the nearest Poké Center.
- **Expected effect:** this cluster should drop to roughly zero.

**Verification:**
- The patch below passes `git apply --check` against your tree.
- Applied in a throwaway worktree, it produces files byte-identical to the ones I tested. Your working tree is untouched.
- `test_jev.py` + `test_jev_nav.py`: 58 pass, 1 fails. The failure is `test_battle_options_switch_slots`, which asserts the old slot target `"2"` and expects a switch to always be offered. That is exactly the behaviour this patch changes. The test is outside the four files I was allowed to edit, so it needs updating separately: target `"Charmeleon"`, and a weak or outmatched active Pokémon so the switch is offered.

## Patch
