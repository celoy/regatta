"""Phase 1 tests (CLAUDE.md, "Tests" 1 to 5) and checks of the derived formulas."""

from pathlib import Path

import numpy as np
import pytest

from regatta_model import analysis as an
from regatta_model import dynamics as dyn
from regatta_model import theory as th
from regatta_model.params import Params, load_params

DEFAULT = Path(__file__).resolve().parents[2] / "toy" / "params" / "default.toml"
DEG = np.pi / 180.0


@pytest.fixture(scope="module")
def p0() -> Params:
    return load_params(DEFAULT)


def settled(p: Params, duty: float, centre_phase: float, headings: np.ndarray) -> np.ndarray:
    """Beat-averaged hull heading after 80 beats of ideal presses; asserts the lock."""
    button = dyn.periodic_button((centre_phase / p.omega) - 0.5 * duty * p.period, duty, p.period)
    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, headings), 80, button)
    assert np.all(an.window_spread(hull[-5:], 5) < 10 * DEG)
    return hull[-5:].mean(axis=0)


def test_1_tiller_free_oscillation(p0: Params) -> None:
    """Field off, no hull drag: alpha oscillates at omega_s with damping ratio zeta."""
    p = p0.with_(omega0=0.0, gamma_hat=0.0)
    s0 = dyn.rest_state(p)
    s0[0] += 0.3
    run = dyn.simulate(p, s0, [], n_steps=480)
    x = run["state"][:, 0] - run["state"][:, 2] + p.alpha0
    t = run["t"]
    i = np.nonzero(x[:-1] * x[1:] < 0)[0][:2]
    t_zero = t[i] + (t[i + 1] - t[i]) * x[i] / (x[i] - x[i + 1])
    omega_d = np.pi / (t_zero[1] - t_zero[0])
    j = i[0] + np.argmin(x[i[0] : i[1] + 1])  # first extremum after the start
    log_dec = np.log(x[0] / abs(x[j]))  # over half a damped period
    zeta = log_dec / np.hypot(np.pi, log_dec)
    omega_s = omega_d / np.sqrt(1.0 - zeta**2)
    assert zeta == pytest.approx(p.zeta, rel=0.05)
    assert omega_s == pytest.approx(p.omega_s, rel=0.05)


def test_2_no_net_rotation_without_field(p0: Params) -> None:
    """Field off, periodic presses: the beat-averaged hull heading returns to its start."""
    p = p0.with_(omega0=0.0)
    duty = np.array([0.2, 0.35, 0.5, 0.65, 0.8])
    s0 = dyn.rest_state(p, np.zeros(5))
    s, _, hull = dyn.run_beats(p, s0, 100, dyn.periodic_button(0.1, duty, p.period))
    assert np.all(np.abs(hull[-1]) < 1.0 * DEG)
    # Angular momentum: L' = -gamma theta_h', so L + gamma_hat theta_h is conserved.
    invariant = p.i_m * s[1] + p.i_h * s[3] + p.gamma_hat * s[2]
    assert np.all(np.abs(invariant) < 1e-9)


def test_3_settled_heading_stable_regime(p0: Params) -> None:
    """Small stroke, omega = 3 omega0: hull settles perpendicular to the field axis."""
    p = p0.with_(omega0=p0.omega / 3.0, alpha0=10 * DEG, phi=0.4)
    h = settled(p, 0.5, th.nominal_centre_phase(p), np.array([-2.0, -0.5, 1.0, 2.5]))
    assert np.all(np.abs(th.wrap(h - (p.phi - 0.5 * np.pi))) < 10 * DEG)


def test_3b_duty_cycle_moves_the_heading_by_the_recoil_only(p0: Params) -> None:
    """At D = 0.3 the hull sits at phi - 90 deg - i_m alpha_mean, not - alpha_mean."""
    p = p0.with_(omega0=p0.omega / 3.0)
    duty = 0.3
    h = settled(p, duty, th.nominal_centre_phase(p), np.array([-2.0, 1.0]))
    mean_alpha = th.alpha_mean(p, duty)
    derived = p.phi - 0.5 * np.pi - p.i_m * mean_alpha
    brief = p.phi - 0.5 * np.pi - mean_alpha
    assert np.all(np.abs(th.wrap(h - derived)) < 2 * DEG)
    assert np.all(np.abs(th.wrap(h - brief)) > 8 * DEG)
    assert np.all(
        np.abs(th.wrap(h - th.hull_headings(p, duty, th.nominal_centre_phase(p)))) < 2 * DEG
    )


def test_4_half_beat_shift_turns_the_boat(p0: Params) -> None:
    p = p0.with_(omega0=p0.omega / 3.0)
    psi = th.nominal_centre_phase(p)
    h1 = settled(p, 0.5, psi, np.array([0.3]))
    h2 = settled(p, 0.5, psi + np.pi, np.array([0.3]))
    assert abs(th.wrap(h2 - h1 - np.pi)) < 5 * DEG


def test_5_determinism_and_event_splitting(p0: Params) -> None:
    events = [(0.2137, 1), (0.7411, 0), (1.25, 1), (1.6003, 0), (2.31, 1), (2.9, 0)]
    a = dyn.simulate(p0, dyn.rest_state(p0, 0.3), events, n_steps=1920, sample_every=48)
    b = dyn.simulate(p0, dyn.rest_state(p0, 0.3), events, n_steps=1920, sample_every=48)
    assert np.array_equal(a["state"], b["state"]) and np.array_equal(a["pos"], b["pos"])
    # Events on the grid: the reference run and the ensemble integrator agree.
    spb = p0.steps_per_beat
    on_grid = [(b + frac, state) for b in range(4) for frac, state in ((0.125, 1), (0.625, 0))]
    ref = dyn.simulate(p0, dyn.rest_state(p0, 0.3), on_grid, n_steps=4 * spb)
    s = dyn.rest_state(p0, np.array([0.3]))
    s, _ = dyn.advance(p0, s, 0, 4 * spb, dyn.periodic_button(0.125, 0.5, p0.period))
    assert np.allclose(ref["state"][-1], s[:, 0], atol=1e-10)


def test_stiff_tiller_rectification_closed_form(p0: Params) -> None:
    p = p0.with_(omega_s=400.0 * p0.omega)
    for duty, psi in ((0.5, 1.2), (0.3, 0.7), (0.8, 2.5)):
        c, s = th.rectified(p, duty, psi)
        exact = (2 / np.pi) * np.sin(np.pi * duty) * np.sin(psi) * np.sin(p.i_h * p.alpha0)
        assert abs(c) < 1e-3
        assert s == pytest.approx(exact, abs=1e-3)


def test_mathieu_threshold_rigid_undamped(p0: Params) -> None:
    """Nearly rigid, undamped boat: the aligned state loses stability at omega = 1.484 omega0."""
    rigid = p0.with_(omega_s=40.0 * p0.omega, gamma_hat=0.0)
    r = th.mathieu_threshold()
    assert r == pytest.approx(1.484, abs=1e-3)
    assert an.floquet_aligned(rigid.with_(omega0=rigid.omega / (r - 0.04))) > 1.01
    assert an.floquet_aligned(rigid.with_(omega0=rigid.omega / (r + 0.04))) < 1.001
