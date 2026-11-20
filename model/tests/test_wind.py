"""Wind boat (prototype): derived results of regatta_model/wind.py, race rules, drill."""

import math
from pathlib import Path

import numpy as np
import pytest

from regatta_model.drill import load_drill
from regatta_model.race import load_course
from regatta_model.wind import WindParams, WindRace, hold_response, load_wind_params

ROOT = Path(__file__).resolve().parents[2]
DEG = math.pi / 180.0


@pytest.fixture(scope="module")
def pv() -> WindParams:
    """The game's wind boat: sail as a vane with inertia."""
    p = load_wind_params(ROOT / "toy" / "params" / "wind.toml")
    assert p.omega_v > 0.5 * p.omega  # a sail at rest is caught by the wind
    return p


@pytest.fixture(scope="module")
def pw(pv: WindParams) -> WindParams:
    """The same boat without the vane: isotropic sail, closed-form results."""
    return pv.with_(omega_v=0.0)


@pytest.fixture(scope="module")
def offset(pv: WindParams) -> float:
    """Angle of the course from the wind at the middle of a half-beat hold (vane)."""
    return hold_response(pv)[0]


def hold(race: WindRace, direction: float, duty: float, n_beats: int, t_from: float = 0.0) -> None:
    """Queue holds of duty cycle `duty` centred on the times the wind blows along `direction`."""
    p = race.p
    t_c = t_from + np.mod((p.phi - direction) / p.omega - t_from, p.period)
    for b in range(n_beats):
        race.set_button(t_c + (b - 0.5 * duty) * p.period, 1)
        race.set_button(t_c + (b + 0.5 * duty) * p.period, 0)


def beat_mean_velocity(race: WindRace, n_settle: int = 12) -> np.ndarray:
    """Velocity averaged over one beat of the periodic state (moored: banks play no part)."""
    p = race.p
    race.moored = True
    race.run_until(n_settle * p.period)
    vs = []
    for _ in range(p.steps_per_beat):
        race.step()
        vs.append(race.velocity.copy())
    return np.mean(vs, axis=0)


@pytest.mark.parametrize("duty", [0.25, 0.5, 0.75])
@pytest.mark.parametrize("direction_deg", [0.0, 70.0, 200.0])
def test_mean_velocity_follows_the_hold(pw: WindParams, duty: float, direction_deg: float) -> None:
    """<v> = v_max (1 - windage) sin(pi D) / pi along the wind at the middle of the hold."""
    race = WindRace(pw, load_course(ROOT / "courses" / "TUT_wind.json"), 0.3)
    hold(race, direction_deg * DEG, duty, 20)
    v = beat_mean_velocity(race)
    a = direction_deg * DEG
    expected = pw.mean_speed(duty) * np.array([math.cos(a), math.sin(a)])
    assert np.allclose(v, expected, atol=1e-3 * pw.v_max)


def test_sail_left_up_goes_round_a_circle(pw: WindParams) -> None:
    course = load_course(ROOT / "courses" / "TUT_wind.json")
    race = WindRace(pw, course, 0.3)
    race.set_button(0.0, 1)
    race.run_until(10 * pw.period)
    xs = [race.pos.copy()]
    while race.t < 11 * pw.period - 1e-9:
        race.step()
        xs.append(race.pos.copy())
    xs = np.array(xs)
    assert np.allclose(xs[-1], xs[0], atol=1e-3)  # no net motion over a beat
    radius = 0.5 * (xs.max(axis=0) - xs.min(axis=0))
    assert np.allclose(radius, pw.idle_radius(), rtol=1e-3)


def test_wind_race_finishes_t01_and_replays(pv: WindParams, offset: float) -> None:
    pw = pv
    course = load_course(ROOT / "courses" / "T01.json")
    race = WindRace(pw, course, 0.3)
    hold(race, -offset, 0.5, 40)  # holds centred so that the course is due east
    while not race.finished and race.t < 30.0:
        race.step()
    t_end = race.t
    assert race.finished and race.collisions == 0
    # 15.5 units at v_max / pi, plus the start-up
    assert race.finish_time == pytest.approx(15.5 / hold_response(pv)[1], abs=2.0)
    again = WindRace(pw, course, 0.3)
    for t, state in race.timeline:
        again.set_button(t, state)
    again.run_until(t_end)
    assert np.array_equal(again.z, race.z) and again.gate_times == race.gate_times


def test_wind_drill_passes_with_holds_on_the_target(pv: WindParams, offset: float) -> None:
    pw = pv
    drill = load_drill(pw, load_course(ROOT / "courses" / "TUT_wind.json"), 0.3)
    race = drill.race
    start = race.pos.copy()
    stage = -1
    while not drill.done and race.t < 40 * pw.period:
        if drill.stage != stage:  # new target: requeue the holds from now on
            stage = drill.stage
            race._pending.clear()
            if race.u:
                race.set_button(race.t, 0)
            hold(race, drill.target - offset, 0.5, 40, race.t + 0.05)
        race.step()
        drill.update()
    assert drill.done and np.array_equal(race.pos, start)
    assert drill.passed_at[-1] <= 20 * pw.period


@pytest.mark.parametrize("held", [0, 1])
def test_wind_drill_does_not_pass_without_rhythm(pv: WindParams, held: int) -> None:
    pw = pv
    drill = load_drill(pw, load_course(ROOT / "courses" / "TUT_wind.json"), 0.3)
    drill.race.set_button(0.0, held)
    while drill.race.t < 40 * pw.period:
        drill.race.step()
        drill.update()
    assert drill.stage == 0


# --- sail as a vane with inertia --------------------------------------------------------


def test_vane_trails_a_steady_wind(pv: WindParams) -> None:
    """Sail left up: lag sin(delta) = 2 zeta_v omega / omega_v; circle of the derived radius."""
    race = WindRace(pv, load_course(ROOT / "courses" / "TUT_wind.json"), 0.3)
    race.set_button(0.0, 1)
    race.run_until(12 * pv.period)
    lag = math.remainder(pv.wind_angle(race.t) - race.sail, 2 * math.pi)
    assert lag == pytest.approx(-pv.vane_lag, abs=1e-4)  # the wind turns clockwise
    xs = [race.pos.copy()]
    for _ in range(pv.steps_per_beat):
        race.step()
        xs.append(race.pos.copy())
    xs = np.array(xs)
    assert np.allclose(0.5 * (xs.max(axis=0) - xs.min(axis=0)), pv.idle_radius(), rtol=1e-3)


def test_vane_course_turns_with_the_hold_phase(pv: WindParams, offset: float) -> None:
    """Rotational symmetry: same offset from the wind and same speed for every direction,
    and a periodic state (the same mean velocity two beats running)."""
    speed = hold_response(pv)[1]
    assert speed > 0.7 * pv.with_(omega_v=0.0).mean_speed(0.5)  # the vane costs under 30 %
    for direction in (0.0, 1.3, math.pi, 4.0):
        race = WindRace(pv, load_course(ROOT / "courses" / "TUT_wind.json"), 0.3)
        hold(race, direction, 0.5, 40)
        v1 = beat_mean_velocity(race, n_settle=30)
        v2 = beat_mean_velocity(race, n_settle=31)
        assert np.allclose(v1, v2, atol=2e-3 * pv.v_max)
        a = direction + offset
        assert np.allclose(v1, speed * np.array([math.cos(a), math.sin(a)]), atol=5e-3 * pv.v_max)
