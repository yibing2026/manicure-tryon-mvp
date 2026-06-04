# Try-On Agent Workflow v1

This workflow safely reuses existing generated outputs, runs quality evaluation, builds a retry plan, and prepares operations actions.

## Workflow Steps

1. Load official paired generation manifest.
2. Run `evaluate:tryon` quality checks.
3. Split candidates into pass/review/fail queues.
4. Generate retry commands for non-pass candidates.
5. Produce operations actions for recommendation and campaign planning.

## Quality Gate

- Total candidates: 13
- Average score: 98.46
- Pass: 11
- Review: 2
- Fail: 0

## Retry Plan

| Pair | Score | Decision | Preset | Command |
| :--- | ---: | :--- | :--- | :--- |
| hand_01_style_01 | 90 | review | style | `python scripts/batch_generate_official_pairs.py --pairs hand_01_style_01 --quality-retry-attempts 2 --retry-preset style --overwrite` |
| hand_10_style_10 | 90 | review | style | `python scripts/batch_generate_official_pairs.py --pairs hand_10_style_10 --quality-retry-attempts 2 --retry-preset style --overwrite` |

## Operations Actions

- Ready for recommendation: 11
- Held for quality review: 2
- Top categories: elegant (4), cool-girl (4), luxury (2), daily (1)
- Top occasions: party (5), wedding (3), dating (1), commute (1), daily (1)
- Top personas: fashion-lover (4), young-professional (3), student (1), luxury-seeker (1), trend-follower (1)

## Top Ready Styles

| Pair | Style | Category | Occasion | Persona | Keywords |
| :--- | :--- | :--- | :--- | :--- | :--- |
| hand_13_style_13 | style_13 | elegant | wedding | young-professional | pink-nude, line, elegant |
| hand_12_style_12 | style_12 | cool-girl | party | fashion-lover | black, green, luxe |
| hand_11_style_11 | style_11 | elegant | wedding | bridal-user | pearl, bridal, reflective |
| hand_09_style_09 | style_09 | cool-girl | party | trend-follower | black, star, glam |
| hand_08_style_08 | style_08 | cool-girl | party | fashion-lover | black, chrome, sharp |

## Notes

- This v1 workflow does not call image generation by default, so it is safe to run without spending API credits.
- Retry commands are explicit suggestions; the operator can run them after reviewing cost and quality tradeoffs.
- The next upgrade is to let the workflow optionally execute retries and re-run evaluation automatically.
