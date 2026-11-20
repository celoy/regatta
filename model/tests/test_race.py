"""Phase 2 tests: race geometry, gates, banks (CLAUDE.md, "Tests" 6), calibration."""

from pathlib import Path

import numpy as np
import pytest

from regatta_model import analysis as an
from regatta_model import dynamics as dyn
from regatta_model import theory as th
from regatta_model.drill import Drill, load_drill
from regatta_model.params import Params, load_params
from regatta_model.race import (
    Course,
    Race,
    clearance,
    load_boat,
    load_course,
    push_out,
    replay,
    segment_crossing,
)

ROOT = Path(__file__).resolve().parents[2]
DEG = np.pi / 180.0


@pytest.fixture(scope="module")
def pr() -> Params:
    boat = load_boat(ROOT / "boats" / "tin_tug.json")
    return load_params(ROOT / "toy" / "params" / "game.toml", boat.params)


def make_course(gates, obstacles=(), islands=(), start=(1.5, 6.0), heading=0.0) -> Course:
    shore = np.array([[0, 0], [20, 0], [20, 12], [0, 12]], dtype=float)
    return Course(
        id="X",
        name="test",
        size=(20.0, 12.0),
        banks=[shore] + [np.asarray(i, dtype=float) for i in islands],
        circles=[(np.asarray(c, dtype=float), float(r)) for c, r in obstacles],
        gates=[(np.asarray(a, dtype=float), np.asarray(b, dtype=float)) for a, b in gates],
        start_pos=np.asarray(start, dtype=float),
        start_heading=heading,
        phi=0.0,
        phi_drift=0.0,
        boat="tin_tug",
        par=None,
        raw={},
    )


def press_for_heading(race: Race, heading: float, n_beats: int, h0: float) -> None:
    """Queue ideal presses (D = 0.5) that hold the boat on `heading`."""
    p = race.p
    psi = h0 - heading
    t0 = np.mod(psi / p.omega - 0.25 * p.period, p.period)
    for b in range(n_beats):
        race.set_button(t0 + b * p.period, 1)
        race.set_button(t0 + (b + 0.5) * p.period, 0)


def test_heading_offset_holds_for_every_phase(pr: Params) -> None:
    h0 = an.heading_offset(pr)
    for psi in (1.0, 2.5, 4.4):
        t_press = np.mod(psi / pr.omega - 0.25 * pr.period, pr.period)
        button = dyn.periodic_button(t_press, 0.5, pr.period)
        _, _, hull = dyn.run_beats(pr, dyn.rest_state(pr, 0.0), 60, button)
        assert abs(th.wrap(hull[-5:].mean() - (h0 - psi))) < 1 * DEG


def test_segment_crossing() -> None:
    a, b = np.array([5.0, 5.0]), np.array([5.0, 7.0])
    assert segment_crossing(np.array([4.0, 6.0]), np.array([6.0, 6.0]), a, b) == pytest.approx(0.5)
    assert segment_crossing(np.array([4.0, 8.0]), np.array([6.0, 8.0]), a, b) is None
    assert segment_crossing(np.array([4.0, 6.0]), np.array([4.5, 6.0]), a, b) is None


def test_6a_gates_counted_once_and_in_order(pr: Params) -> None:
    """Gate 1 lies before gate 0 on the path: crossing it first does not count."""
    gates = [((8, 5), (8, 7)), ((4, 5), (4, 7)), ((12, 5), (12, 7))]
    race = Race(pr, make_course(gates), 0.3)
    press_for_heading(race, 0.0, 20, an.heading_offset(race.p))
    v = race.p.v
    race.run_until(18.0 / v)  # 18 units of travel from x = 1.5
    assert race.next_gate == 1  # gate 0 only: gate 1 (x = 4) was passed before gate 0
    assert len(race.gate_times) == 1
    assert 6.0 / v < race.gate_times[0] < 9.0 / v  # x = 8 is 6.5 units from the start


def test_6b_gate_crossed_back_and_forth_counts_once(pr: Params) -> None:
    gates = [((5, 4), (5, 8)), ((15, 4), (15, 8))]
    race = Race(pr, make_course(gates), 0.3)
    h0 = an.heading_offset(race.p)
    press_for_heading(race, 0.0, 4, h0)  # east through gate 0
    race.run_until(4.0)
    t = race.t
    p = race.p
    psi = h0 - np.pi  # then west, back through gate 0
    t0 = t + np.mod(psi / p.omega - 0.25 * p.period - t, p.period)
    for b in range(6):
        race.set_button(t0 + b * p.period, 1)
        race.set_button(t0 + (b + 0.5) * p.period, 0)
    race.run_until(12.0)
    assert race.pos[0] < 5.0  # it did come back across x = 5
    assert race.next_gate == 1 and len(race.gate_times) == 1
    assert not race.finished


def test_6c_boat_never_ends_a_step_inside_a_bank(pr: Params) -> None:
    """Random presses for 60 s in a pond with an island and two circles."""
    island = [[13, 2], [16, 2], [16, 5], [13, 5]]
    course = make_course(
        gates=[((19, 11), (19.5, 11.5))],
        obstacles=[((6, 6), 1.5), ((10, 9), 1.0)],
        islands=[island],
        start=(3.0, 3.0),
    )
    radius = 0.3
    race = Race(pr, course, radius)
    rng = np.random.default_rng(3)
    t = 0.0
    while t < 60.0:
        t += rng.uniform(0.1, 0.9)
        race.set_button(t, 1)
        t += rng.uniform(0.1, 0.9)
        race.set_button(t, 0)
    worst = np.inf
    while race.t < 60.0:
        race.step()
        worst = min(worst, clearance(course, race.pos))
    assert race.collisions > 0  # the test did hit something
    assert worst >= radius - 1e-6


def test_push_out_from_inside_obstacles() -> None:
    course = make_course(
        gates=[((1, 1), (1, 2))],
        obstacles=[((6, 6), 1.5)],
        islands=[[[13, 2], [16, 2], [16, 5], [13, 5]]],
    )
    for p in ([6.1, 6.2], [14.0, 3.0], [-1.0, 5.0], [20.0, 12.0], [6.0, 6.0]):
        q, hit = push_out(course, np.array(p), 0.3)
        assert hit and clearance(course, q) >= 0.3 - 1e-6


def test_replay_reproduces_a_race(pr: Params) -> None:
    course = load_course(ROOT / "courses" / "T01.json")
    race = Race(pr, course, 0.3)
    t_end = 21.0 / race.p.v  # 15.5 units to the last gate, with margin
    press_for_heading(race, 0.0, int(t_end / race.p.period) + 1, an.heading_offset(race.p))
    race.run_until(t_end)
    again = replay(pr, course, 0.3, race.timeline, t_end)
    assert np.array_equal(again.z, race.z)
    assert again.gate_times == race.gate_times and race.finished


def test_courses_and_boats_load() -> None:
    for path in sorted((ROOT / "courses").glob("*.json")):
        course = load_course(path)
        assert load_boat(ROOT / "boats" / f"{course.boat}.json").radius > 0
        assert clearance(course, course.start_pos) > 0.3
        for a, b in course.gates:
            assert clearance(course, 0.5 * (a + b)) > 0.3


# --- tutorial drill ---------------------------------------------------------------------


def tutorial_drill(pr: Params) -> Drill:
    course = load_course(ROOT / "courses" / "TUT.json")
    return load_drill(pr, course, 0.3)


def test_drill_passes_with_presses_on_the_target(pr: Params) -> None:
    """Pressing when the aim (h0 - omega t - pi/2) equals the target passes every stage."""
    drill = tutorial_drill(pr)
    race, p = drill.race, drill.race.p
    h0 = an.heading_offset(p)
    start = race.pos.copy()
    t_off = 0.0
    while not drill.done and race.t < 40 * p.period:
        if race.n % p.steps_per_beat == 0:  # one press per beat, where the aim meets the target
            wait = np.mod((h0 - 0.5 * np.pi - drill.target) / p.omega - race.t, p.period)
            t_on = max(race.t + wait, t_off + 0.05)
            t_off = t_on + 0.5 * p.period
            race.set_button(t_on, 1)
            race.set_button(t_off, 0)
        race.step()
        drill.update()
    assert drill.done
    assert np.array_equal(race.pos, start)  # moored
    # 3 beats on target per stage, plus about 2 beats to turn 90 degrees
    assert drill.passed_at[-1] <= 20 * p.period
    assert abs(drill.error) < 10 * DEG


@pytest.mark.parametrize("held", [0, 1])
def test_drill_does_not_pass_without_rhythm(pr: Params, held: int) -> None:
    """The idle boat circles through the target; it must not pass a stage."""
    drill = tutorial_drill(pr)
    race = drill.race
    race.set_button(0.0, held)
    while race.t < 60 * race.p.period:
        race.step()
        drill.update()
    assert drill.stage == 0
