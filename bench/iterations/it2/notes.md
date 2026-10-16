- Iteration 1's learn-move prompt loop is fixed: code-forced presses are marked "(auto)" and do not count as repeats,
  "press A" is never dropped on prompts, a repeated menu/dialog/prompt screen offers untried options, any screen reloads
  the progress checkpoint after 500 idle steps.
- The Mt. Moon B1F/B2F ping-pong (clusters on node "cerulean" in Mt. Moon) is addressed by bench/jev_nav.py: a static
  warp/edge graph decoded from the ROM, Dijkstra to the objective's last target map, a "follow the map route to X"
  option with the concrete next warp, one option per warp by coordinates instead of "walk to <map name>", a cost for
  warps already taken since the last progress and blocked hops after a failed route step. Focus on the other clusters
  (Route 3, Poké Center healing, battle loops, low confidence) and on anything the route graph still misses.
