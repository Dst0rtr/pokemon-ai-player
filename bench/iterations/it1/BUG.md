# Iteration 1 (after-brock): scaffolding bug, not counted

Run `jev-assist_after-brock_it1_jev-latest_20261016_160032`, 2026-10-16 16:00–17:12, ended at the 20,000-call budget
without reaching Cerulean City. From step 118 on, the agent looped on Butterfree's learn-move prompts in Mt. Moon B2F
("Delete an older move...?" → NO → "Abandon learning STUN SPORE?" → NO → back) for ~19,800 steps.

Causes (both in the code scaffolding, fixed for iteration 2):

1. The repeat filter (`drop_repeats`) counted the code-forced `press A` on the battle-text screens between the prompts,
   so it dropped `press A` (YES on "Abandon learning?", the only way out) from the options Jev and Haiku chose from.
2. Stuck detection only watched the overworld position, so nothing noticed a menu/dialog/prompt loop.

`fallbacks-bug-learn-move-loop.jsonl.gz` keeps its 225 fallback events (182 on that prompt) as a labeled example of
this failure. The run's results file and calibration numbers were discarded and are not in RESULTS.md.
