# Magnet Regatta: Game Off 2026 project brief

Working title "Magnet Regatta" (not cleared, see Open questions). This file is the single brief for the whole jam, from the Python toy to the submitted Godot game. Claude Code reads it at the start of every session.

## How to work with this file

- The user, Chris, is a fluid-mechanics professor and a solo part-time developer. He judges the physics and the feel by playing and watching. Make the physics visible and every parameter easy to change.
- Work only on the phase marked CURRENT in Status. Do not start the next phase without the user's go.
- At the end of each task: run the tests, then report what passes, every assumption you made that is not in this file, and anything here you think is wrong.
- Never change an entry in Decisions on your own; propose the change and wait.
- At the end of each session, append one dated line to Status.
- Do not add features that are not in the current phase. When in doubt, ask.

## Status

- CURRENT: Phase 2
- 2026-11-17: brief written; nothing built yet.
- 2026-11-19: Phase 0 done: public repo celoy/regatta, layout, .venv (Python 3.12, uv), pytest smoke test passing, empty Godot 4.7.2 project exported to web (no threads) and loaded in headless Chrome. Awaiting Chris's go for Phase 1.
- 2026-11-19: Phase 1 built: model, tests 1-5 (10 pass), sweeps 1-5 plus a design scan, report in docs/phase1_report.md. Findings: defaults give no lock; still tiller spins with the field (not chaotic); duty cycle does not steer (two opposite headings only). Awaiting Chris's review, the steering decision and the parameter set for Phase 2.
- 2026-11-19: Phase 1 second pass after Chris's review (phase steering then heavier magnet; chaos without dissipation; set A). Chaos confirmed at zero dissipation and lost at the game's damping (8-beat transient at 0.7 /s); phase steering works only in the stable regime and fails at 40 ms jitter; heavier magnet gives at most ±7° near A. 13 tests pass. Awaiting Chris's decision on steering (changing field axis or stable regime) and on hull damping (0.4 /s proposed).
- 2026-11-19: Phase 1 third pass, rotating field tried at Chris's request (new parameter field_ellipticity; 0 keeps the brief's field). Result: the press phase sets the heading degree for degree; candidate R (rotating, omega/omega0 = 2, alpha0 = 65°, hull damping 3 /s) turns 90° in 2 beats, 9° heading scatter at 40 ms jitter, idle boat circles at 13° per beat, no chaos. 15 tests pass. Awaiting Chris's choice between R and A; R contradicts three Decisions entries (listed in docs/phase1_report.md), not changed.
- 2026-11-19: Chris chose R; Decisions and dependent brief sections updated for the rotating field. Phase 2 built: race model, test courses T01-T03 (par 10.83, 23.56, 22.56 s), boats tin_tug and barge, bots, pygame viewer with aim dial, test 6; 23 tests pass. Fun hypothesis: jitter gradient, 3-beat turn and time cost of jitter pass; naive-bot hypothesis fails in substance (bot artefact). Report docs/phase2_report.md. Awaiting Gate B: Chris plays.

## Deadline and jam

- GitHub Game Off 2026, theme SHIFT. Submissions close 1 December 2026 at 21:37 UTC (13:37 PST). Target submission: 30 November, evening (Paris time).
- The source must be in a public GitHub repository. Any engine is allowed.
- Rated categories: overall, gameplay, graphics, audio, innovation, theme interpretation.
- Before submitting, the user checks the jam page for any rule on AI-assisted code.

## The game in one page

Pitch. Race a toy pop-pop boat across a pond whose coils make a magnetic field that turns once per beat. The boat's heading is set by its own magnet. One button works a magnetic tiller; pressed in rhythm with the field, it locks the boat onto a heading, and the moment you press picks the heading. Shift the beat to turn. Left alone, the boat drifts round in slow circles.

Setting. A nineteenth-century physics cabinet: a basin with coils on its banks, tin boats with candle engines, buoys. A uniform field exerts a torque and no force, so the field only orients the boat; the engine pushes it at constant speed. Period hook for the itch page: a 1900 US patent describes a game of racing model boats steered by magnets (US658197).

The control. The magnet is joined to the hull by a torsional spring (the magnetic tiller). Holding the button applies a constant torque that swings the magnet to one side; releasing it lets the spring swing it back. One button, nothing else.

What the rhythm does (measured in Phase 1, docs/phase1_report.md, candidate R):
- Swinging the magnet at the field frequency rectifies the turning field's torque into a steady one, like a static field pointing where the field pointed at the middle of your hold. The boat settles on that heading (plus a fixed offset).
- Phase is the tiller: pressing a fraction of a beat later turns the boat by the same fraction of a turn. A 90° turn settles in about 2 beats; a half-beat shift is a 180° turn in about 3 beats. This is the theme.
- Tempo turns: playing steadily fast or slow makes the boat turn steadily (3.6° per beat for each per cent of tempo error).
- Duty cycle trims: holding longer moves the heading by about 20° over D = 0.25 to 0.75, and the lock holds at every duty cycle.
- Timing error becomes heading error: 4° rms at 20 ms of jitter, 9° at 40 ms, 23° at 120 ms. There is no lock to lose; sloppy timing makes the boat wander.
- Left alone (button held or released), the boat circles slowly, at about 13° per beat.

The race. Real time. Pass the gates (pairs of buoys) in order, avoid banks and obstacles, finish. Pause is allowed (simulation and race clock stop) and resumes after a one-beat count-in.

Making the theme readable: a beat indicator showing the turning field against the tiller's stroke, and an aim dial whose hand points where a press made now would send the boat; a tutorial that names the move ("shift the beat to turn"); one sentence on the itch page.

Scoring. Time to finish; medals against a par time (gold, silver, bronze at 1.00, 1.15, 1.30 × par; guesses); ghost of your best run; a collision stops the boat for 1 s.

Boats as content. Boats differ by tiller spring, magnet strength and inertia, and handle differently. Default first boat: stiff tiller (crisp). Later: a heavy-magnet boat whose hull zigzags; a resonant tiller that must be pumped like a swing.

Fun hypothesis (falsifiable in Phase 2; rewritten for the rotating field):
- A bot pressing with Gaussian timing jitter of 40 ms holds its heading within 10° rms on a straight course; at 120 ms the scatter exceeds 20°. So there is a skill gradient within human range.
- A half-beat shift completes a 180° turn within 3 beats.
- The pilot bot with 120 ms of jitter is at least 15 % slower than with 20 ms on the test courses, so timing skill shows in the race time.
- A naive bot (aims straight at each gate, uncalibrated, no lead) is at least 15 % slower than the pilot bot on the campaign courses.

Kill criterion and fallback, at Gate B (Sunday 22 November): if steering by phase does not feel playable when Chris plays the toy (too twitchy, too sluggish, or the aim dial makes it trivial), first adjust omega/omega0, damping and stroke within the range measured in Phase 1; failing that, fall back to candidate A (oscillating field, two tacks per field axis) with the field axis changing along the course.

Out of scope for the jam: opponents racing at the same time (ghosts only), wind and currents, boat speed control, course editor, online leaderboards, touch controls, voice, 3D.

## Model

Units: seconds, radians, arbitrary length unit (pond about 20 × 12 units). Fixed time step, deterministic: the same input timeline gives the same run.

Field: B(t) = B (sin(omega t) e_phi + e cos(omega t) e_perp), with e_phi = (cos phi, sin phi), e_perp at +90° from it, and ellipticity e. The game uses e = 1, a field of constant strength turning clockwise at omega; e = 0 is the oscillating field of the original brief, kept for the Phase 1 tests. phi sets which press timing gives which heading, fixed per pond (optional slow drift phi(t) for "wind shift" ponds).

Two rigid bodies, magnet angle theta_m (inertia I_m) and hull heading theta_h (inertia I_h, including the added mass of water in yaw), relative angle alpha = theta_m − theta_h:

    I_m theta_m'' = mu B (−sin(omega t) sin(theta_m − phi) + e cos(omega t) cos(theta_m − phi)) − k (alpha − alpha_r) − c alpha' + tau_b u(t)
    I_h theta_h'' = + k (alpha − alpha_r) + c alpha' − tau_b u(t) − gamma theta_h'

- u(t) = 1 while the button is held, 0 otherwise.
- alpha_r = −alpha0 (spring rest); tau_b / k = 2 alpha0, so the held equilibrium is +alpha0.
- Optional soft stops at ±1.3 alpha0 (stiff springs), in case of overshoot.
- Boat: x' = v cos theta_h, y' = v sin theta_h, constant v.
- Collision with a bank or obstacle: push out along the normal, stop forward motion for 1 s; the rotational dynamics keep running.

Derived results to check numerically (state them in docstrings):
- Tiller natural frequency omega_s = sqrt(k (I_m + I_h) / (I_m I_h)), damping ratio zeta from c.
- The stroke is the button signal filtered by H(i omega) = omega_s² / (omega_s² − omega² + 2 i zeta omega_s omega). Its component at the field frequency has amplitude (tau_b/k)(2/pi) sin(pi D) |H(i omega)|; its mean is alpha_r + (tau_b/k) D.
- Oscillating field (e = 0): the averaged torque is equivalent to a static field perpendicular to phi, of strength set by the press phase and duty cycle; the settled headings are phi ± 90° − i_m mean alpha (corrected in Phase 1; i_m = I_m / (I_m + I_h)), so phase only picks between two opposite headings.
- Rotating field (e = 1), stiff tiller: the averaged torque is −mu B (2/pi) sin(pi D) sin(i_h alpha0) sin(Theta + psi_c), so the heading is −psi_c plus a constant: the press phase sets the heading. Measured offset of about 7° from this formula (induction-motor torque on the wobble, not derived).
- Still tiller, rigid: a pendulum with zero-mean parametric forcing. Its aligned state is stable only for omega > about 1.48 omega0 with omega0² = mu B / (I_m + I_h) (undamped Mathieu boundary, recalled). Below that it tumbles, possibly chaotically.
- Internal torques cannot change total angular momentum; with drag only on the hull, a periodic stroke without field gives no net rotation. Mirror-image press and release responses keep this true for nonlinear drag. Test it.

Integration: RK4 at dt = 1/480 s for (theta_m, theta_m', theta_h, theta_h'). Resolve both the field period and the tiller period with at least 40 steps each.

Default parameters (the original guesses, kept in toy/params/default.toml for the Phase 1 tests; params in TOML for the toy, JSON for Godot). The game uses candidate R (toy/params/candidate_r_rotating.toml): e = 1, omega0 = omega / 2, gamma / (I_m + I_h) = 3.0 1/s, alpha0 = 65°, the rest as below.

| Name | Default | Note |
|---|---|---|
| omega | 2 pi × 1.0 rad/s | field beat about 60 per minute |
| omega0 | omega / 1.2 | still tiller below the Mathieu threshold: tumbles |
| gamma / (I_m + I_h) | 0.7 1/s | hull yaw damping |
| I_m / I_h | 0.2 | light magnet, steady hull |
| alpha0 | 35° | tiller half-range |
| omega_s | 4 omega | stiff tiller |
| zeta | 0.5 | tiller damping ratio |
| v | 1.5 units/s | |
| dt | 1/480 s | |

## Python toy (Phases 1 and 2)

Package `regatta_model` (numpy only) holds the model and is the reference twin of the Godot sim. `toy/` holds the pygame-ce viewer; `tools/` the sweeps and bots.

Sweeps (headless, CSV outputs), Phase 1:
1. Still-tiller regime map: largest Lyapunov exponent of the hull heading over omega/omega0 from 0.8 to 3 and damping from 0.2 to 2.
2. Lock window: with ideal periodic presses, sweep duty cycle D, press phase relative to the field, and tempo error; record lock (heading settled within 10° over 5 beats) and the settled heading. Compare with the derived formulas.
3. Jitter: repeat 2 with Gaussian timing jitter on press and release times, sigma from 0 to 150 ms; lock rate per beat.
4. Tack: a half-beat shift from a locked state; beats until relocked on the opposite heading.
5. Reaction check: field off, periodic presses; net hull rotation over 100 beats (should be zero).

Toy viewer, Phase 2: top view of the pond, two coil pairs on the banks pulsing in quadrature, the field drawn as an arrow turning once per beat, boat with the magnet visible on its pivot, wake trail, gates. Beat indicator: field phase and tiller stroke on one strip, and the aim dial. Lock meter (heading spread over the last beat). Keys: Space (the button), P pause, R restart, G ghost, S screenshot, L reload parameters, 1–3 test courses, B cycle boats.

Bots (tools/bots.py), Phase 2:
- Rhythm bot: presses at the field frequency with chosen phase and duty cycle; Gaussian timing jitter sigma.
- Pilot bot: sets the press phase from the bearing to the next gate through the measured heading-phase relation (calibrated once per boat), with a proportional lead on the heading error; duty cycle 0.5.
- Naive bot: sets the press phase from the bearing through the uncalibrated formula, without lead.
- Outputs: lap times, on-course rate (beats within 15° of the commanded heading), heading scatter, collisions; summary table for the fun hypothesis. Par time = best pilot bot at sigma = 20 ms.

Tests (pytest):
1. Field off, tiller oscillator alone: free oscillation at omega_s with damping zeta (within 5 %).
2. Field off, periodic presses: no net hull rotation over 100 beats (within 1°).
3. Small-amplitude stroke, field on, stable regime: settled heading within 10° of phi ± 90° − mean alpha.
4. Shifting the press phase by half a beat moves the settled heading by 180°.
5. Determinism: the same input timeline gives identical trajectories.
6. Gate crossing detected once, in order; the boat never ends a step inside a bank.

## Courses

Course file (courses/Cxx.json):

```
{
  "id": "C03",
  "name": "Tack up the basin",
  "pond": { "size": [20, 12], "banks": [[...polygon...]], "phi": 1.5708, "phi_drift": 0.0 },
  "obstacles": [ {"type": "circle", "c": [8, 6], "r": 1.2} ],
  "gates": [ {"a": [4, 2], "b": [4, 4]}, ... ],
  "start": { "pos": [1, 3], "heading": 0.0 },
  "boat": "tin_tug",
  "par": 41.5
}
```

Campaign of 6–8 hand-made courses, one idea each: keep the rhythm on a straight; turn by shifting the beat; a U-turn with a half-beat shift; slalom; a narrow channel where heading scatter matters; a pond whose field phase drifts (wind shift); then mixed. Boats in boats/*.json with the handling parameters.

## Godot game

- Godot 4.3 or later (confirm the user's version), GDScript only, Compatibility renderer, web export with thread support off. Flag any Godot 3 idiom (yield, export without @, onready without @, PoolByteArray...).
- Simulation in plain classes (RefCounted), no Nodes, testable headless: Params, BoatModel, Course, Race, Recorder (input timeline, ghosts). Scenes only display state and pass input.
- Input timing: read the button with event timestamps, not frame polling, so timing precision does not depend on frame rate. Apply presses in the sim at the exact event time (split the step).
- Golden tests: `godot --headless --script res://tests/run_tests.gd` replays input timelines exported by the Python twin and compares headings and positions at sample times (tolerance 1e-6).
- Scenes: Title, CourseSelect, Race, Results. Minimal text, a short interactive tutorial on course 1.
- Drawing: procedural vector drawing, no painted assets. Engraving look on cream paper, ink lines, coils on the banks, pulsing field arrow, boat with visible magnet, dotted wake. Fonts under the SIL Open Font License, credited.
- Audio: the field is the metronome (a soft tick at each reversal and a hum), tiller clicks, pop-pop engine pulses, splash on collision, bell at each gate. Synthesis with AudioStreamGenerator if it behaves in the web export, otherwise CC0 samples, credited.
- Progress: best times, medals and best-run input timelines in user://progress.json.
- Performance: under 2 ms of simulation per frame in Chrome on the user's laptop (guess). Test Chrome and Firefox, and measure input latency.

## Repository layout

```
regatta/
  CLAUDE.md
  README.md              # Phase 5
  LICENSE                # chosen by the user
  model/                 # Python package regatta_model (numpy only) + tests
  toy/                   # pygame-ce viewer, params/default.toml
  tools/                 # sweeps, bots, golden export
  courses/  boats/       # shared JSON
  game/                  # Godot project: sim/ scenes/ ui/ audio/ tests/ golden/
  docs/                  # screenshots, GIFs for the itch page
  runs/                  # gitignored
```

## Conventions

- Python 3.11+, one virtual environment at the repo root (.venv). Dependencies: numpy, pygame-ce, pytest. Ask before adding anything (matplotlib for plots needs approval).
- Parameters in files, never hard-coded. One seed per run where randomness exists.
- Content (courses, boats, texts) in JSON.
- Commit at the end of each task with a message naming the phase and task.

## Plan

Dates and hours are guesses. If a phase runs more than a day late, apply the cut list.

Phase 0, setup (Tue 17 – Wed 18 Nov, about 1 h)
- Public GitHub repo, layout above, .gitignore, .venv, pytest running, empty Godot project exporting to web and running in Chrome.

Phase 1, model and sweeps (Wed 18 – Fri 20 Nov, about 5 h)
- Model, tests 1–5, sweeps 1–5 with CSV outputs and a short report of the regime map, the lock window and its width against jitter.
- Acceptance: tests pass; Chris reviews the sweeps; the parameter set for Phase 2 is chosen.

Phase 2, playable toy and bots (Sat 21 – Sun 22 Nov, about 5 h)
- Viewer, one-button play, beat indicator, three test courses, bots, test 6, fun-hypothesis table.
- Gate B on Sunday 22: Chris plays. Go, adjust parameters, or fallback (see Kill criterion). Record the decision in Status.

Phase 3, Godot core (Mon 23 – Wed 25 Nov, about 6 h)
- GDScript port with golden tests, pond view, timestamped one-button input, beat indicator, pause with count-in.
- Acceptance: one course playable in a web export within the performance budget, with timing that feels as tight as in the toy.

Phase 4, race game (Thu 26 – Sat 28 Nov, about 6 h)
- Gates, timer, collisions, results, medals, best-run ghost, course select, tutorial, 6–8 courses with par times, 2–3 boats, audio, progress save.
- Acceptance: every course finishable; each par reproducible by replaying the bot's input timeline.

Phase 5, freeze and submit (Sun 29 – Mon 30 Nov, about 3 h; Tue 1 Dec buffer)
- Feature freeze on Sunday 29; bug fixes only after that.
- Two or three outside players try it without help; note where they get stuck.
- README (how to play, the physics in one paragraph, credits), itch page text and screenshots, web build, submission on Monday 30.

Cut list, in this order: field-drift ponds; resonant boat; best-run ghost; AudioStreamGenerator (use samples); courses beyond five; boats beyond one.

## Decisions

- Godot Wild Jam #99 dropped (no AI-written code); entry for GitHub Game Off 2026, theme SHIFT.
- Sand-frame and phase-space ideas dropped; a boat race steered through a driven nonlinear oscillator chosen.
- Rhythm game in real time; skill over strategy accepted.
- The pond's field rotates at the beat frequency (two coil pairs in quadrature; phi per pond); the boat's heading comes from its own magnet; with a still tiller the boat circles slowly. (Changed 2026-11-19 after Phase 1: the oscillating field with a tumbling idle boat was dropped because the press phase cannot set the heading in it.)
- One button. The magnetic tiller is a torsional spring between magnet and hull; holding the button applies a constant torque to one side, the spring returns it on release.
- The press phase sets the heading, degree for degree (a half-beat shift turns the boat 180°); the duty cycle only trims; timing error becomes heading error; playing off tempo makes the boat turn steadily. (Changed 2026-11-19 after Phase 1; replaces "phase picks the tack, duty cycle steers, losing the tempo returns the boat to chaos".)
- Parameter set: candidate R (toy/params/candidate_r_rotating.toml: rotating field, omega/omega0 = 2, alpha0 = 65°, hull damping 3 /s). Chosen 2026-11-19.
- One boat on the water at a time; constant boat speed; the field orients and never pushes.
- Boats differ by tiller spring, magnet and inertia; the first boat is stiff and crisp (default, open to change).
- Python twin first (model, tests, sweeps, bots), then GDScript port checked against golden files.

## Open questions (as tasks)

- Title: search Steam, itch.io and the web for clashes before adopting "Magnet Regatta" or any other title.
- Licence for the public repo. Answered 2026-11-19: MIT.
- Confirm the jam's rule on AI-assisted code before submitting.
- Godot version installed. Answered 2026-11-19: 4.7.2 stable, with web export templates.
- Parameter regime (omega/omega0, damping, stroke) from the Phase 1 sweeps. Answered 2026-11-19: candidate R (see Decisions).
- First boat stiff or resonant (default stiff).
- Medal thresholds, from bot and playtest times.
- Whether the itch page uses the 1900 patent drawing (check the specific scan's rights).

## Sources

- Y. Braiman and I. Goldhirsch, "Taming chaotic dynamics with weak periodic perturbations", Phys. Rev. Lett. 66, 2545 (1991), https://doi.org/10.1103/PhysRevLett.66.2545 (seen in search results): a weak periodic forcing can eliminate chaos in a driven pendulum.
- Z. Abbadi and E. Simiu, "Taming chaotic dynamics with weak periodic perturbations: an elucidation and critique", Nanotechnology 13, 153 (2002) (seen in search results): weak forcing suffices only for shallow potential wells; stronger forcing works more generally.
- US Patent 658197, "Game" (1900), https://patents.google.com/patent/US658197 (seen in search results): model boats with magnets steered and raced through passages.
- Recalled, not verified in this session: Kapitza averaging (Landau and Lifshitz, Mechanics, §30); Mathieu stability boundary near q ≈ 0.908 for a = 0; Purcell's scallop theorem; chaos of a compass needle in an oscillating field (Croquette and Poitou, 1981).
