# Magnet Regatta (stopped prototype)

A one-button rhythm game about steering a toy boat, prototyped in November 2026 for GitHub Game Off 2026 (theme: SHIFT). The project was stopped on 20 November 2026 after playing the prototype, and nothing was submitted to the jam. This repository is archived.

What exists is a Python model with tests, a small pygame viewer to play it, and three reports. The Godot project in `game/` is an empty shell.

## The idea

A pond has a magnetic field, or a wind, that turns once per beat. The player has one button. Pressing in rhythm rectifies the turning field into a steady push or torque, and the moment of the press sets the boat's course. Pressing a fraction of a beat later turns the course by the same fraction of a turn: you steer by shifting the beat.

Two boats were built:

- **Magnet boat.** The boat carries a magnet on a sprung tiller. The button swings the magnet; the field orients the boat and a constant engine pushes it.
- **Wind boat.** The button raises a sail. The boat is pushed where the wind blew during the hold.

## What was found

- **An oscillating field cannot be steered by timing.** With a field that reverses along one axis, the press phase only selects between two opposite headings. The idle boat is chaotic only when dissipation is close to zero.
- **A rotating field can.** The heading follows the press phase degree for degree. This follows from the rotational symmetry and holds in the simulations. A 90° turn takes about 2 beats; 40 ms of timing error gives about 9° of heading scatter.
- **The wind boat has a closed form.** With linear hull drag, the mean velocity is `v_max sin(pi D) / pi` along the wind direction at the middle of the hold, where `D` is the fraction of the beat the sail is up. A scripted player loses about 8 % of race time at 120 ms of timing error, against 50 to 90 % for the magnet boat.
- **A sail with rotational inertia needs care.** If the sail swings like a soft weathervane (natural frequency at or below twice the wind frequency), some settings never settle to one state per beat. Timing the presses by the sail's own direction fails, because the raised sail races after the wind.

## Why it stopped

The author played both boats. The magnet boat was hard to control: his first run of the straight course took 92 s against a par of 10.8 s, with no sound to keep the beat. The wind boat was controllable but, in his words, not that interesting. Neither justified building the full game.

## Run it

Requires Python 3.11 or later.

```
python -m venv .venv
.venv/bin/pip install -e ".[toy,dev]"
.venv/bin/pytest                                   # 42 tests
.venv/bin/python toy/viewer.py                     # magnet boat, tutorial
.venv/bin/python toy/viewer.py --model wind        # wind boat, tutorial
.venv/bin/python toy/viewer.py --model wind --course T01
```

Keys: Space is the button, M switches boat, 0 is the tutorial, 1 to 3 are the test courses, P pauses, R restarts, L reloads the parameter files, B cycles magnet boats, G toggles the ghost of your best run, S saves a screenshot, Esc quits.

In the tutorial the boat is moored. A dot goes round a ring once per beat. For the magnet boat, press while the dot is in the green part; for the wind boat, hold while it is there.

## Layout

| Path | Contents |
|---|---|
| `model/regatta_model/` | The model (numpy only): magnet boat (`dynamics.py`, `theory.py`, `analysis.py`), wind boat (`wind.py`), race rules (`race.py`), tutorial drill (`drill.py`) |
| `model/tests/` | pytest suite |
| `toy/viewer.py` | pygame-ce viewer |
| `toy/params/` | Parameter files; `game.toml` (magnet boat) and `wind.toml` (wind boat) are the ones the viewer uses |
| `tools/` | Parameter sweeps and bots for the magnet boat |
| `courses/`, `boats/` | Courses and boats as JSON |
| `docs/` | Reports and the log of runs |
| `game/` | Empty Godot 4 project |
| `CLAUDE.md` | The project brief, with the dated status log and the decisions |

## Reports

- [docs/phase1_report.md](docs/phase1_report.md): the magnet model, its regimes, and why the field had to rotate.
- [docs/phase2_report.md](docs/phase2_report.md): the playable toy, the bots, the wind boat, and the outcome.
- [docs/run_log.md](docs/run_log.md): every sweep and bot run, with its command and git hash. The outputs are in `runs/`, which is not in the repository.

The few references used are listed, with their verification status, under "Sources" in [CLAUDE.md](CLAUDE.md).

## Licence and credits

MIT, see [LICENSE](LICENSE). Design and physics by Christophe Eloy; code written with Claude Code.
