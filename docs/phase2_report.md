# Phase 2 report: playable toy and bots

2026-11-19. Rotating field, candidate R (boat `tin_tug`). Bots run `runs/phase2/20261119-205024_bots` (listed in `docs/run_log.md`).

## Summary

The toy is playable and the bots race the three test courses.

- **What passes.** Three of the four fun hypotheses pass: the jitter skill gradient, the 3-beat half-beat turn, and race times that grow with timing jitter.
- **What fails.** The naive bot is not slower in the way the hypothesis means. When it finishes it is as fast as the pilot. When it loses, it is because it orbits a gate it has just missed.
- **What is left for Chris.** Gate B: play the toy and judge whether steering by phase feels right, especially with the aim dial.

## Run it

```
.venv/bin/python toy/viewer.py                  # T01 with its boat
.venv/bin/python toy/viewer.py --course T03 --boat barge
```

- **Keys:** Space (the button), P pause (resumes after a one-beat count-in), R restart, G ghost of your best run, S screenshot, L reload parameters, 1–3 courses, B cycle boats, Esc quit.
- **How to steer:** the blue hand of the aim dial points where a press made now (held half a beat) would send the boat. Press every beat when it points where you want to go; to turn, press earlier or later.
- **Also on the dial:** the boat's heading (black) and the bearing of the next gate (red).
- **The strip below the pond:** the two field components, the tiller stroke (red) and your holds (black bars), over the last three beats and the next one.
- **What the toy saves:** best runs and screenshots go to `runs/toy/` (gitignored).

## What was built

- **`model/regatta_model/race.py`**: courses, boats, banks and islands (polygons), circular obstacles, gates crossed in order (either direction), collisions, the race clock, the recorded input timeline, and replay.
  - **Collisions:** the boat is pushed out along the normal and stopped for 1 s while it keeps turning. Speed is held over each step, so stops start and end on the 1/480 s grid.
  - **Events:** button events are applied at their exact time by splitting the step, as in `dynamics.simulate`, which now shares the same step function.
- **`analysis.heading_offset`**: one calibration run gives h0 in heading = h0 − psi_c (psi_c is the field phase at the hold centre). It holds for every phase by the rotational symmetry of the rotating field; checked to within 1° at three other phases.
- **Content:** `courses/T01–T03.json` (straight, zigzag, round the island); `boats/tin_tug.json` (candidate R) and `boats/barge.json` (weaker magnet and smaller stroke, ω/ω0 = 2.5, α0 = 50°: steadier but slower to answer, from the Phase 1 response sweep). Boat files override keys of `toy/params/candidate_r_rotating.toml`.
- **`tools/bots.py`**: rhythm, pilot and naive bots, run closed-loop, with jitter on press and release times. Outputs CSV, a summary, and the par input timelines.
- **`toy/viewer.py`**: the viewer described above.

## Tests

23 pass (`.venv/bin/pytest`). New in this phase:

- **Test 6a:** a gate lying before the next one on the path is not counted when crossed out of order.
- **Test 6b:** a gate crossed back and forth counts once.
- **Test 6c:** 60 s of random presses in a pond with an island and two circles; the boat hits things and never ends a step closer than its radius to any bank or obstacle.
- **Push-out:** the boat is pushed clear from inside each kind of obstacle, including a corner.
- **Replay:** reproduces a race bit for bit.
- **Courses:** all load, with start and gates in open water.
- **Calibration:** heading = h0 − psi_c at three other phases.

## Bots and par times

Six seeds per cell, duty cycle 0.5. Median finish time in seconds, with finished runs out of 6 where not all finished:

| | jitter 0 ms | 20 ms | 40 ms | 80 ms | 120 ms |
|---|---|---|---|---|---|
| T01 pilot | 10.85 | 10.89 | 11.01 | 17.38 | 44.76 |
| T01 naive | DNF (0/6) | 26.52 (2/6) | 55.72 (4/6) | 46.94 | 33.78 |
| T02 pilot | 22.71 | 26.58 | 35.95 | 50.19 | 41.26 (5/6) |
| T02 naive | DNF (0/6) | 57.38 (2/6) | 47.13 | 36.40 | 46.55 |
| T03 pilot | 23.07 | 23.11 | 23.29 | 27.61 (5/6) | 36.19 (5/6) |
| T03 naive | 23.22 | 22.76 | 23.31 | 27.89 | 36.63 |

- **Par** (best pilot run at 20 ms, written into the course files): T01 10.83 s, T02 23.56 s, T03 22.56 s. Each par replays bit for bit from its saved timeline.
- **Fastest possible:** T01's straight-line time is 10.3 s, so the pilot loses about 5 % to wobble.
- **Pilot lead:** a lead of 0.3 on the heading error was also tried; it was slower or equal everywhere. A lead of 1 was unstable, because the boat answers a command in about 2 beats.
- **T02 at high jitter:** the median at 120 ms is lower than at 80 ms. With 6 seeds and one DNF at 120 ms, the difference is noise.
- **Collisions:** at 80–120 ms the pilot averages 12 to 15 collisions on T03. These are episodes of being pinned against the island, where each 1 s stop ends with another hit until the heading comes round.

## Fun hypothesis

| Hypothesis | Result | Source |
|---|---|---|
| Heading scatter ≤ 10° rms at 40 ms jitter, > 20° at 120 ms | Pass: 9° and 23° | Phase 1 response sweep, candidate R |
| Half-beat shift turns 180° within 3 beats | Pass: 3 beats | Phase 1 response sweep and tack sweep |
| Pilot at 120 ms at least 15 % slower than at 20 ms | Pass: ×4.1 (T01), ×1.55 (T02), ×1.57 (T03) | bots |
| Naive bot at least 15 % slower than the pilot | Fails in substance; see below | bots |

On the first row: on-course rate is the better skill measure in the race, since the bots' scatter column only covers on-course beats. The pilot's on-course rate falls from 0.84 at 20 ms to 0.39 at 120 ms on T01.

Where 40 ms starts to cost time: ×1.01 on T01 and T03, ×1.35 on T02. At 80 ms: ×1.60, ×1.89, ×1.19. So the race punishes timing worse than about 50 ms.

**Naive bot.** On T01 and T02 its medians are 2.2 to 2.4 times the pilot's, but they come from one failure mode. It aims at a gate's centre right up to the gate, the bearing swings as it gets close, it misses the gate by a fraction of a unit, and then it circles round the gate centre. Without jitter that orbit is a stable cycle and it never finishes; jitter breaks it out. When it does pass a gate it is as fast as the pilot: on T03 the ratio is 0.99. Its uncalibrated heading formula (8.5° off) costs nothing measurable.

For the game this matters less than it looks, because the aim dial gives the player the calibrated relation. What separates players is timing precision and anticipating the 2-beat answer of the boat. The hypothesis should be restated against a bot that models that: for example, the pilot with a reaction delay. I propose this and have not done it.

## Assumptions not in the brief

- **Input timing:** pygame-ce key events carry no timestamps. The viewer polls at 250 Hz (`tick_busy_loop`, measured gap 4.0 ms; the plain `tick` gave 6 ms) and times a press at the poll. This uses one CPU core while the toy runs.
- **Lock meter:** it shows the change of the beat-averaged heading from one beat to the next, not the heading spread within a beat as the brief says. With α0 = 65° the hull swings 40–45° within every beat (recoil of the stroke), so that spread is always large and does not show whether the boat is holding course. The swing is shown as a number ("wobble").
- **Aim dial:** added to the beat indicator; the brief's text was updated with the Decisions.
- **Course format:** the first polygon in `banks` is the shoreline and any others are islands.
- **Boat files:** override keys of the base parameter file. `toy/params/default.toml` keeps the original guesses for the Phase 1 tests.
- **Ghost and best runs:** stored per course and boat in `runs/toy/best_<course>_<boat>.json`. Bot-driven viewer runs (`--bot`, for headless checks) do not save a best.
- **Gates:** may be crossed in either direction.
- **Collision count:** a boat held against a bank counts one collision per 1 s stop.

## Things in the brief I think need attention

- **The idle boat circles,** at 13° per beat, so "chaos returns" is gone from the game. The Decisions now say so.
- **The naive-bot hypothesis** measures a bot artefact (see above).
- **Two of the brief's keys need the stored best run:** G and the ghost need a best run on disk, which exists only after a human finish.
- **Audio:** the toy has none. A tick at each field reversal would probably help keep the rhythm when Chris plays. The brief puts audio in Phase 4; I did not add it.

## T01 as a tutorial (2026-11-20, after Chris's first look)

- **Open water:** the four gates span y = 1.5 to 10.5 instead of 5 to 7. The par timeline still replays to 10.83 s.
- **Field hidden:** no field arrow and no coils on T01. The strip and the dial stay.
- **Aim ring:** a circle round the boat with a blue dot that turns clockwise once per beat, at the heading a press made now would give (the dial's hand, moved onto the boat). A black mark on the ring shows the bow (heading averaged over the last beat). While the button is held, the arc the dot has swept since the press is drawn.
- **Hint:** three lines at the top of the pond: press when the dot reaches the bow mark, hold about half a turn; every turn keeps the boat straight; earlier or later turns it.
- **Course format:** a new optional `display` block in the course file (`field_arrow`, `coils`, `ring`, `hint`); courses without it look as before.
- **Check:** a scripted player that only follows the hint (press as the dot crosses the bow mark, release half a beat later) finishes T01 in 11.1 s without timing error, 10.9–11.0 s at 20 ms, 11.1–11.3 s at 40 ms (3 seeds each). At 80 ms it gets lost in 2 of 3 runs: following the bow holds whatever heading the boat has and never corrects back towards the gates.

## Slower beat and moored-boat tutorial (2026-11-20, after Chris played)

Chris's first run of T01 (kept in `runs/toy/best_T01_tin_tug.json`, old 1 Hz beat) took 92.5 s against a par of 10.8 s. He pressed about once per beat (median interval 1.02 s), but only 34 % of the intervals were within 10 % of a beat (10th to 90th percentile 0.75 to 1.33 s), and the press phase was spread uniformly round the beat. So the rhythm itself was not held, with no sound and no instruction.

**Slower beat.** The beat goes from 1 Hz to 0.75 Hz as a pure time rescaling: hull damping 3 to 2.25 /s and boat speed 1.5 to 1.125 units/s, with omega/omega0, alpha0, omega_s/omega and zeta unchanged. Game parameters are in `toy/params/game.toml`; `candidate_r_rotating.toml` stays as the Phase 1 record.

- **Check:** the beat-by-beat heading of a 12-beat run matches the 1 Hz run to 0.02°, and h0 is the same (−23.46°).
- **What changes:** everything takes 4/3 longer, and a timing error in ms is 3/4 as large a fraction of the beat (40 ms now gives the heading scatter that 30 ms gave).
- **New pars** (run `runs/phase2/20261120-150148_bots`, each replays exactly): T01 14.44 s, T02 29.97 s, T03 30.18 s.
- **Jitter cost, 120 ms / 20 ms:** T01 ×1.06, T02 ×1.91 (T02's best pilot now uses lead 0.3), T03 ×1.52. T01 no longer punishes jitter, because its gates are now nearly as wide as the pond; it is a first course, not a test of timing.
- **Naive bot:** finishes T01 6/6 at every jitter now that the gates are wide (6 % slower than the pilot); on T02 it still orbits missed gates.

**Tutorial** (`courses/TUT.json`, key 0, the viewer's default course). The boat is moored: it turns and does not move (v = 0). Round it is a ring with a green part, centred on the target heading and ±20° wide, and a red part elsewhere. A blue dot goes round once per beat at the heading a press made now would give, so the green part is both where to press and where the boat will point. Three stages: straight (target ahead), left (target +90°: press a quarter turn earlier), right (target −90°: press later). A stage is passed after 4 beats in a row with the beat-averaged heading inside the green and a press in the last 1.5 beats; pips under the ring count them. The field arrow, coils and race clock are hidden.

- **Logic:** `model/regatta_model/drill.py`, with stages, tolerance and beats needed in the course file.
- **Tests (3 new, 26 pass):** ideal presses on the target pass all three stages within 20 beats; a boat left alone, or with the button held down, never passes (it circles through the target at 13° per beat, which is why a press is required).
- **Scripted player** (presses when the dot reaches the middle of the green): passes the stages at beats 4, 10, 16 at 0 and 40 ms of timing error; at 80 ms by beat 19 to 22; at 120 ms by beat 34 to 51.
- **T01** keeps its ring and bow mark, with a one-line hint.
- **Best runs:** the file name now carries a hash of the parameters and the course, since a timeline only replays under the set-up it was recorded with. Runs made before a change are kept and not used.

## Gate B, for Chris

1. Play T01 to T03 with both boats.
2. Judge:
   - whether steering by press timing feels controllable;
   - whether the boat's 2-beat answer feels sluggish or right;
   - whether the aim dial makes it too easy or is needed;
   - whether the 40° in-beat wobble reads as charm or noise.
3. If it does not feel right, the first knobs are omega_over_omega0 (2 to 3: steadier but slower), alpha0_deg and hull_damping, in the boat files. L reloads them without restarting.
