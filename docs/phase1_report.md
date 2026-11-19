# Phase 1 report: model, tests and sweeps

2026-11-19, second pass the same day after Chris's review. Code at `model/regatta_model/`, sweeps in `tools/sweeps.py`, runs listed in `docs/run_log.md`.

## Summary

The model is built and tested, and the sweeps contradict three points of the brief.

1. **The default parameters do not give a lock.** With ideal presses the boat locks from at most 6 of 10 random starts in one cell of the lock window and from fewer than 3 of 10 elsewhere. Most starts end in a period-2 wobble.
2. **The still-tiller boat is chaotic without dissipation, and the game's damping removes it.** With no hull drag and no tiller damping it is chaotic at every field strength tested. At the default damping it tumbles irregularly for about 8 beats, then spins at exactly one turn per beat, locked to the field. Sustained chaos at that damping needs a much stronger field, omega/omega0 between about 0.4 and 0.6. (Corrected in the second pass; the first version of this report said "not chaotic" without having tested low damping.)
3. **The duty cycle does not steer.** The locked hull sits at phi ± 90° − i_m × (mean alpha), with i_m = I_m/(I_m + I_h) = 1/6, and not at phi ± 90° − (mean alpha). Measured: within 3° of the perpendicular for D from 0.3 to 0.7. A locked boat therefore has two headings, and they are opposite.

Two points of the brief hold once the stroke is larger (candidate A: alpha0 = 65°, omega/omega0 = 1.1):

4. **The lock has a skill gradient in human range.** Lock rate 0.99 at 40 ms jitter, 0.05 at 120 ms.
5. **A half-beat shift tacks the boat in 2 beats** when the new pattern starts from a press, 4 from a release.

Point 3 is the one that matters for the game: with one field axis and a locked boat, the course is a straight line. The second pass tested the two steering ideas Chris chose, and neither gives usable steering near candidate A (next section).

## Second pass: chaos, phase steering, heavier magnet

Chris's answers to the first version: try phase steering, then a heavier magnet; the system is chaotic without dissipation; parameter set A. Three sweeps were added (`chaos`, `steer`, `magnet` in `tools/sweeps.py`).

### Chaos against dissipation

Chris is right, and the sweep says where chaos stops. Still tiller, 12 starts per cell, exponent over 450 beats.

| Tiller | Tiller damping zeta | Chaotic at omega/omega0 = 1.1 (A) for hull damping up to | Chaotic at any damping tested (up to 0.7 /s) |
|---|---|---|---|
| Default, omega_s = 4 omega | 0 | 0.02 /s (1 start in 10; 2 in 10 at 0.01) | omega/omega0 = 0.4 to 0.6 |
| Default | 0.05 | none | 0.4 to 0.5 (0.6 up to 0.4 /s) |
| Default | 0.5 | none | 0.4 to 0.5 (0.6 at 0.7 /s only) |
| Stiff, omega_s = 20 omega | 0 | 0.02 /s (2 in 10; 5 in 10 at 0.01) | 0.6 |
| Stiff | 0.5 | 0.02 /s (2 in 10) | 0.6 |

- With no dissipation at all (hull drag and tiller damping zero), at least 8 starts in 10 are chaotic at every omega/omega0 from 0.4 to 1.5, for both tillers.
- For the default tiller the tiller damping does most of the damage: at zeta = 0.5 chaos is gone for omega/omega0 ≥ 0.6 even with no hull drag. A stiff tiller is barely excited by the field and keeps chaos at zero hull drag for any zeta.
- At the game's damping the tumbling is a transient. Candidate A's field, default tiller: median 8 beats (longest 11) before the spin sets in at 0.7 /s, 39 (51) at 0.1 /s, 52 (59) at 0.05 /s.
- Candidate A at almost no dissipation (zeta = 0, hull damping 0.01 /s, `candidate_a_low_damping.toml`) does not lock at any duty cycle or phase. The lock needs damping to settle.
- Checks of the exponent: started on the unstable aligned state it gives 1.9456 /s against 1.9434 /s from the Floquet multiplier (rigid, undamped, omega/omega0 = 1.2) and 1.2083 against 1.2055 (default tiller and damping); halving dt changes a chaotic exponent from 0.9265 to 0.9267 /s, inside its statistical error of 0.008.

A scan of the hull damping on candidate A (scratch script, 16 starts) shows a middle ground:

| Hull damping (1/s) | 0.05 | 0.1 | 0.2 | 0.3 | 0.4 | 0.7 |
|---|---|---|---|---|---|---|
| Still tiller: beats of tumbling before the spin (median) | 46 | 34 | 21 | 16 | 12 | 8 |
| Lock from a random start | 0.44 | 0.56 | 1.00 | 1.00 | 1.00 | 1.00 |
| Beats to reach the lock (median) | 44 | 30 | 20 | 20 | 7 | 3 |
| Lock rate at 40 ms jitter | 0.07 | 0.34 | 0.60 | 0.99 | 0.90 | 0.99 |
| Tack (beats) | 10 | 13 | 23 | 2 | 2 | 2 |

Around 0.3 to 0.4 /s the unlocked boat tumbles for 12 to 16 beats and the lock, the jitter tolerance and the 2-beat tack survive.

### Phase steering

It works for ideal presses in the stable regime with a small stroke, and fails at human timing.

- Static map (8 starts, 160 beats, phase in 10° steps, D from 0.2 to 0.8). Number of 10° heading bins, of 36, that at least half of the starts hold at some phase, for D = 0.5 alone / for any D, then the mean lock fraction:

| omega/omega0 | alpha0 = 15° | 25° | 35° | 45° | 55° | 65° |
|---|---|---|---|---|---|---|
| 1.10 (A's field) | 0 / 0 / 0.00 | 3 / 3 / 0.06 | 4 / 14 / 0.12 | 6 / 11 / 0.18 | 6 / 8 / 0.26 | 9 / 13 / 0.34 |
| 1.35 | 7 / 16 / 0.47 | 8 / 31 / 0.48 | 9 / 31 / 0.44 | 11 / 34 / 0.46 | 10 / 30 / 0.52 | 10 / 26 / 0.64 |
| 1.50 | 26 / 30 / 0.97 | 21 / 36 / 0.93 | 10 / 36 / 0.90 | 13 / 34 / 0.89 | 9 / 28 / 0.94 | 6 / 23 / 0.95 |

- At omega/omega0 = 1.5 and alpha0 = 15° (grip 0.93) the heading follows a slowly drifting press phase smoothly: −72°, −56°, −29°, 1°, 30°, 57°, 72°, then back, for each 30° of phase. It swings ±72° about the field axis and stays on one side; the mirror branch points the other way. The theory's headings are within 4° of the settled ones.
- A step of the press phase settles in 4 beats for 30°, 7 to 9 beats for 60° to 150°.
- With timing jitter, at a heading 60° of phase away from the tack: heading scatter 6° at 20 ms, 26° at 40 ms with jumps to the mirror branch, 62° at 80 ms.
- At candidate A's field the small strokes do not lock at all, and A itself shows only the two tacks.

Against the criterion of the plan (30° either side reachable, 90 % of starts, settled within 5 beats, scatter below 10° at 40 ms jitter): reach and starts pass, settling and jitter fail. It also means giving up A: the stable regime has no spin when unlocked and tacks take 8 beats or more.

### Heavier magnet

The recoil steering is real and small. Heading range over the duty cycles that lock from 3 starts in 4, lock rate at 40 ms jitter, and tack time:

| omega/omega0 | I_m/I_h | alpha0 | Heading range | Lock at 40 ms | Tack (beats) |
|---|---|---|---|---|---|
| 1.1 (A) | 0.2 | 65° | 6° | 0.98 | 2 |
| 1.1 | 0.5 | 80° | 15° | 0.89 | 2 |
| 1.1 | 0.5 | 65° | no lock | 0.25 | none |
| 1.1 | 1.0 | 65° or 80° | one duty cycle only | 0.17 to 0.39 | 12 to 23 |
| 1.3 | 0.5 | 80° | 17° | 0.95 | 5 |
| 1.5 | 0.5 | 80° | 21° | 0.96 | 8 |
| 1.5 | 1.0 | 80° | 28° | 0.77 | 18 |
| 1.5 | 2.0 | 65° | 34° | 0.60 | none |

A heavier magnet loses grip faster than it gains steering (the rectified torque goes as sin(i_h alpha0), with i_h the hull's share of the inertia). The best compromise near A is I_m/I_h = 0.5 with alpha0 = 80°: ±7° of steering.

### Where this leaves steering

Neither option steers a boat that keeps A's lock and tack. What the sweeps support:

- With one field axis, a locked boat goes along one line, in either direction. Trim of ±3° (A) to ±7° (heavier magnet, alpha0 = 80°) is available from the duty cycle.
- The remaining route to a course with turns is a field axis that changes along the course, which is already in the brief as the "wind shift" pond: the boat follows phi ± 90°, the player keeps the rhythm, picks the tack and trims with the duty cycle.
- Phase steering is a different game: stable regime, small stroke, timing precision near 20 ms.

## Fun hypothesis against the sweeps

| Hypothesis | Default | Candidate A | Candidate B |
|---|---|---|---|
| Still tiller chaotic | Only as a transient of about 8 beats, then spins with the field (exponent −0.40 /s) | Same | No: aligns with the axis |
| Lock rate ≥ 0.95 at 40 ms jitter | No lock even at 0 ms | 0.99 | 1.00 |
| Lock lost often at 120 ms | n/a | Yes: 0.05 | Half: 0.51, and never leaves the tack |
| Tack within 3 beats | n/a | 2 (from a press), 4 (from a release) | 9 |
| Lock falls as \|D − 0.5\| grows | n/a | Yes: locks for D from 0.30 to 0.70 | Barely: locks for all D |
| Naive bot 15 % slower | Phase 2 | Phase 2 | Phase 2 |

Candidates: A = `toy/params/candidate_a_strong_stroke.toml` (omega/omega0 = 1.1, alpha0 = 65°), B = `candidate_b_kapitza.toml` (omega/omega0 = 1.8, alpha0 = 35°, the brief's fallback). All other parameters are the defaults.

## Model and tests

The model is the two-body system of the brief, integrated by RK4 at dt = 1/480 s, with inertias normalised by I_m + I_h = 1. `dynamics.simulate` splits steps at the exact event times and is the reference for the golden files of Phase 3. `dynamics.run_beats` is the ensemble integrator of the sweeps; it rounds press and release times to the grid (error up to 1 ms).

All 13 tests pass (`.venv/bin/pytest`):

- Tests 1, 2, 4 and 5 of the brief, as written.
- Test 3 of the brief at D = 0.5, where both heading formulas agree.
- Test 3b, added: at D = 0.3 the heading is within 2° of phi − 90° − i_m × (mean alpha) and more than 8° from the brief's formula.
- Stiff-tiller rectification against its closed form; Mathieu threshold 1.484 for a nearly rigid, undamped boat.
- Heading clustering, transient length and off-tempo presses (helpers of the second pass).

The closed forms were also checked symbolically with sympy (run once through `uv run --with sympy`, not added as a dependency).

## Theory: what changed from the brief

The derivation is in the docstring of `model/regatta_model/theory.py`. Three results differ from the brief.

**Duty cycle.** For a stiff tiller the stroke is a square wave between −alpha0 and +alpha0. Averaging the field torque over a beat gives exactly

    −mu B (2/pi) sin(pi D) sin(psi_c) sin(i_h alpha0) cos(Theta),

with psi_c the field phase at the centre of the hold and Theta the inertia-weighted boat angle from the field axis. The zero is at Theta = ±90° for every D: the harmonics of the stroke cancel the shift of its mean. The brief kept only the fundamental. D changes the grip through sin(pi D), and moves the mean hull heading only by the recoil of the hull, −i_m alpha0 (2D − 1).

**Kapitza torque and grip.** The field also shakes the boat at omega, which pulls the magnet towards the axis with a torque −kappa (omega0⁴ / 4 omega²) sin(2 Theta). The compliant tiller reduces this by kappa = 0.69 for the default tiller. The lock is perpendicular only if the grip g = 2 (omega/omega0)² R / kappa exceeds 1, with R the rectified strength above. Below 1 the theory gives two mirror headings, sin(Theta) = −g.

**Stability threshold.** The aligned still-tiller state is stable above omega/omega0 ≈ 1.35 in the full model (Floquet multipliers, sweep 1), not 1.48. The estimate 1.484 × kappa^(1/4) = 1.35 agrees.

Agreement with the simulation: in the stable regime at small stroke (omega/omega0 = 3, alpha0 = 10°) the theory gives ±40° from the perpendicular branch point where the simulation gives 38° to 46°. For candidate A at nominal phase it is within 5° for D from 0.30 to 0.65. Averaging assumes omega well above omega0, so near omega/omega0 = 1.2 the theory is a guide only: it predicts g = 1.33 for the defaults, and the simulation does not lock.

## Sweep results

Definitions: heading is the hull heading averaged over one beat; lock means that heading stays within 10° over 5 beats; the "nominal" phase puts the fundamental of the stroke in phase with the field (hold centred at field phase 75°, so the press comes 15° before the field's upward zero crossing at D = 0.5).

### 1. Still-tiller regime map

Rows: hull damping gamma/(I_m + I_h) in 1/s. Columns: omega/omega0 from 0.8 to 3.0 in steps of 0.1. `C` chaotic, `a` aligned state stable and no chaos found, `p` regular motion with the aligned state unstable.

```
 0.2  ppppppaaaaaaaaaaaaaaaaa
 0.4  ppppppaaaaaaaaaaaaaaaaa
 0.6  ppppppaaaaaaaaaaaaaaaaa
 0.8  ppppppaaaaaaaaaaaaaaaaa
 1.0  ppppCpaaaaaaaaaaaaaaaaa
 1.2  ppppppaaaaaaaaaaaaaaaaa
 1.4  ppppppaaaaaaaaaaaaaaaaa
 1.6  pppCpaaaaaaaaaaaaaaaaaa
 1.8  pppCpaaaaaaaaaaaaaaaaaa
 2.0  pppCpaaaaaaaaaaaaaaaaaa
```

- In the `p` region the boat spins at one turn per beat, in either direction depending on the start. At omega/omega0 = 1.4 one start in four still ends in that spin, so it coexists with the aligned state.
- A separate scan below the brief's range (not saved as a run) found chaos for every start at omega/omega0 = 0.4 and 0.5, with exponents of 0.5 to 1 /s at the default damping.
- At omega/omega0 = 0.4, ideal presses still lock the boat for alpha0 ≥ 45°, at some phases only (17 to 38 % of the phase and start combinations). This is the only place found where chaos and lock coexist. It was not explored further.

### 2. Lock window

Lock fraction over 8 random starts; digit = tenths. Rows: D. Columns: hold-centre phase from 0° to 345° in steps of 15°.

Default:

```
0.30  002000110000002010100000
0.40  021011111010020212010000
0.50  010011200200011000011000
0.60  001221000000001100101020
0.70  001110000000001001100000
```

Candidate A:

```
0.25  000027000000000057000020
0.30  000099000000000098900000
0.40  029999800000019999920000
0.50  959999956567969999988278
0.60  059999720000059999800000
0.70  000098800000000098000000
0.75  000056000000000028000000
```

- Candidate A locks over about 90° of phase (250 ms) at D = 0.5, narrowing to 30° at D = 0.3 and 0.7. The two bands, half a beat apart, are the two tacks.
- Candidate B locks from every start at every D and phase.
- Heading on the −90° tack at nominal phase, candidate A:

| D | 0.30 | 0.40 | 0.50 | 0.60 | 0.70 |
|---|---|---|---|---|---|
| Measured | −87.8° | −87.4° | −90.0° | −92.6° | −92.2° |
| Theory | −83.2° | −86.9° | −90.0° | −93.1° | −96.8° |
| Brief's formula | −64.0° | −77.0° | −90.0° | −103.0° | −116.0° |

- Tempo error, candidate A, lock rate per beat: 1.00 at 0 %, 0.81 at ±0.5 %, 0.74 at ±1 %, 0.40 at ±2 %, 0.05 at ±5 %. A steady tempo error makes the press phase drift through both tacks.

### 3. Jitter

Gaussian jitter on every press and release time, 200 beats, 32 seeds, start on the tack. Lock rate, with the fraction of beats within 30° of the tack in brackets.

| sigma (ms) | 0 | 20 | 40 | 60 | 80 | 100 | 120 | 150 |
|---|---|---|---|---|---|---|---|---|
| A, D = 0.50 | 1.00 | 1.00 | 0.99 (1.00) | 0.81 (1.00) | 0.44 (0.97) | 0.15 (0.81) | 0.05 (0.65) | 0.01 (0.43) |
| A, D = 0.35 | 1.00 | 0.94 | 0.46 (1.00) | 0.16 (0.93) | 0.07 (0.74) | 0.02 (0.51) | 0.01 (0.43) | 0.00 (0.33) |
| B, D = 0.50 | 1.00 | 1.00 | 1.00 (1.00) | 1.00 (1.00) | 0.97 (1.00) | 0.76 (1.00) | 0.51 (1.00) | 0.21 (0.98) |

- Default: the lock rate is below 0.1 at every sigma, including 0.
- Candidate B wobbles under jitter but stays on its tack up to 150 ms, so sloppy timing costs little.

### 4. Tack

Half-beat shift after 40 locked beats, 16 starts; beats until the heading is within 15° of the opposite tack and stays there.

| | A, from a press | A, from a release | B |
|---|---|---|---|
| D = 0.50 | 2 | 4 | 9 |
| D = 0.35 | 3 | 3 | 8 |
| D = 0.65 | 6 | 4 | 9 |

All boats relocked. The slow tacks have a cause: a half-beat shift reverses the rectified torque, which puts the boat exactly on the unstable equilibrium of the new pattern, and it leaves only as fast as the instability grows.

### 5. Reaction check

Field off, 100 beats, D from 0.2 to 0.8: net hull rotation below 10⁻⁴ degrees; the heading excursion during the transient is at most 7°.

### 6. Design scan

omega/omega0 from 1.0 to 2.0, alpha0 from 35° to 75°, 16 starts (`design_scan.csv` in the default run).

- Lock from every start at D = 0.5 needs alpha0 ≥ 55° to 70° for omega/omega0 from 1.0 to 1.4, or omega/omega0 ≥ 1.7 at any stroke.
- Between these, around omega/omega0 = 1.3 to 1.5 and alpha0 = 40° to 55°, the boat falls off the tack even at 40 ms jitter.
- Tacks of 2 beats appear only at omega/omega0 = 1.1 with alpha0 ≥ 65°; elsewhere 3 to 17 beats.

## Candidates

| | Still tiller | Lock window | Jitter gradient | Tack | Steering |
|---|---|---|---|---|---|
| A: omega/omega0 = 1.1, alpha0 = 65° | Spins with the field | D 0.30 to 0.70, 90° of phase | Yes | 2 to 6 beats | Two headings, ±3° |
| B: omega/omega0 = 1.8, alpha0 = 35° | Aligns with the axis | Everything locks | Weak | 8 to 10 beats | Two headings; others in a 30° band of phase |
| C: omega/omega0 = 1.5, alpha0 = 17° | Aligns with the axis | Locks, 75 % of starts near nominal | Yes | 8 to 9 beats at D = 0.5; mostly fails at D = 0.35 and 0.65 | Phase moves the heading; inconclusive |

Candidate C (`candidate_c_phase_steer.toml`) tests a lead from the theory: with a grip near 1 the heading follows the press phase continuously (sin(Theta) = −g sin of the phase), which would make the phase the tiller. The sweep shows intermediate headings (for example 39° to 56° and 117° to 165° at D = 0.3), but the response is slow and a quarter of the starts do not lock, so this is not established.

My recommendation is candidate A for the feel of the lock and the tack, with the stroke at alpha0 = 65°. A stroke that large means the magnet swings 130° on the hull, and its overshoot reaches about 1.33 alpha0 = 86°; the soft stops are off in all runs.

## Decisions needed

1. **Steering.** Both options tested fail near A. Does the game take the changing field axis (course shape set by the coils, duty cycle as trim), or move to the stable regime for phase steering? "Duty cycle steers" in Decisions needs rewording either way; I have not changed it.
2. **Hull damping.** 0.7 /s gives 8 beats of tumbling before the spin; 0.3 to 0.4 /s gives 12 to 16 and keeps the lock. Sustained chaos needs near-zero damping, where nothing locks. The pitch line "tames the chaos" and the Decisions entry "with a still tiller the boat tumbles" fit a transient, not an attractor.
3. **Parameter set**: A is recorded as chosen. Proposed adjustment: hull damping 0.4 /s, to be confirmed by playing in Phase 2.

## Limits of these results

- Small ensembles: 8 to 16 starts per cell, 32 seeds for jitter. Fractions are coarse.
- In `lock_window.csv` the locked headings are averaged per side of the field axis. Where the grip is below 1 there are two mirror headings on the same side, and their average reads as ±90°. This affects candidates B and C near the edges of their phase bands, not the tables above. `steer_static.csv` (second pass) lists every branch separately.
- The jitter sweep starts on the tack; recovery after a lost lock is not measured.
- Linear hull drag only; no soft stops; one tiller (omega_s = 4 omega, zeta = 0.5) and one inertia ratio throughout.
- Run from scratch scripts, not from `tools/sweeps.py`: the stable-regime theory check, the hull-damping scan on A, and the phase-steering details (drifting phase, step response, jitter scatter), each for one start or 16 seeds.
- The heavier-magnet runs at omega/omega0 = 1.3 and 1.5 used temporary parameter files; copies are in their run directories.
- At strong field (omega/omega0 = 0.4 to 0.6), where chaos survives the game's damping, a quick scan found locks at some phases (default tiller at 0.4 with alpha0 ≥ 45°; stiff tiller at 0.4 to 0.6). Jitter, tack and steering were not measured there.

## Reproduce

```
.venv/bin/pytest
.venv/bin/python tools/sweeps.py --params toy/params/default.toml
.venv/bin/python tools/sweeps.py --params toy/params/candidate_a_strong_stroke.toml --only lock,jitter,tack
```

Each call writes CSV files, the parameter file, the git hash and a text summary to a new directory under `runs/phase1/` (gitignored) and adds a line to `docs/run_log.md`. All sweeps on one parameter file take about 4 minutes.
