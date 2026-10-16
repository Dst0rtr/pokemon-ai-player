# Review of the Opus proposal (iteration 2)

`proposal.patch` did not apply: its hunk headers were malformed, and it was written against a tree from before
`jev_nav` gained reachable-warp filtering. It also called `D.species_types`, `D.move_info` and `D.type_multiplier`,
which do not exist; they were wrapped in try/except, so every move would silently have been rated "damage unknown".
Opus said it had verified the patch, but it had no tools to do so.

Applied by hand (commit "Jev: Opus it2 suggestions ..."):
- Switches name the species (the server resolves names against the live party), so slot numbers no longer go
  stale. The active Pokémon is excluded case-insensitively, a refused switch is not re-offered, and the party is
  re-read after a switch or faint.
- Heal items are offered under 50% HP and balls only while the team has fewer than 4 Pokémon. Code writes the
  "run away" criterion (train / heal / default).
- `INSTRUCTIONS` no longer cites a nonexistent `situation` field. It points to `map_route` and to the route option.
  The battle instructions point to auto-battle, which already scores moves with the Gen 1 damage formula on the server.
- An edge crossing must land on a walkable cell (Route 3 (63,0) loop). Edge hops walk to the route's own cell and
  step across; hops are keyed by coordinates.
- A warp the player stands on is taken by stepping off and back on. "already at" no longer counts as a failed
  hop: in iteration 4 that bug had blocked nearly every ladder.
- The four blind 4-tile walks are dropped while a route is known and no stuck recovery is active. The objective
  text names the route option.
- Healing: a "talk to the nurse across the counter" option (from (3,3) facing up), and the route goes to the
  nearest Poké Center.

Not applied: the move ratings (they need type data that the agent does not have; auto-battle covers this on the
server) and `enemy_types`.
