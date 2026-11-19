"""Rotational dynamics of the boat: magnet and hull joined by the magnetic tiller.

State s = (theta_m, theta_m', theta_h, theta_h'), shape (4,) or (4, ...) for an
ensemble. With alpha = theta_m - theta_h and I_m + I_h = 1:

    I_m theta_m'' = -mu B sin(omega t) sin(theta_m - phi) - tau
    I_h theta_h'' = +tau - gamma theta_h'
    tau = k (alpha - alpha0 (2u - 1)) + c alpha' + stop torque

Field: B (sin(omega t) e_phi + e cos(omega t) e_perp), with e_phi along the field axis,
e_perp at +90 deg from it and e the ellipticity. e = 0 is the oscillating field of the
brief and the equations above; e = +-1 is a field of constant strength rotating at omega
(clockwise for e = 1). The field torque on the magnet is then
mu B (-sin(omega t) sin(theta_m - phi) + e cos(omega t) cos(theta_m - phi)).

u = 1 while the button is held, 0 otherwise: the spring rests at -alpha0 and the
held equilibrium is +alpha0 (alpha_r = -alpha0, tau_b = 2 k alpha0). Written this
way the press and release responses are mirror images (alpha -> -alpha, u -> 1 - u),
which also holds for the soft stops at +- stop_ratio alpha0.

Derived results (checked in model/tests and tools/sweeps.py):
- tau is internal: d/dt (I_m theta_m' + I_h theta_h') = field torque - gamma theta_h'.
  Without field, L' = -gamma theta_h', so a periodic stroke gives no net hull
  rotation: the beat-averaged heading returns to its initial value.
- The relative motion obeys alpha'' + 2 zeta omega_s alpha' + omega_s^2 (alpha - alpha_eq)
  = (gamma / I_h) theta_h' - (mu B / I_m) sin(omega t) sin(theta_m - phi), so the tiller
  alone oscillates at omega_s with damping ratio zeta (hull drag couples in weakly).

Integration: RK4 with fixed dt. Time is n * dt with integer n, so runs are deterministic.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from .params import Params

Button = Callable[[float], "float | np.ndarray"]


def rhs(p: Params, t: float, s: np.ndarray, u: float | np.ndarray) -> np.ndarray:
    th_m, w_m, th_h, w_h = s
    alpha = th_m - th_h
    tau = p.k * (alpha - p.alpha0 * (2.0 * u - 1.0)) + p.c * (w_m - w_h)
    if p.stop_k_ratio > 0.0:
        lim = p.stop_ratio * p.alpha0
        tau = tau + p.stop_k_ratio * p.k * (
            np.maximum(alpha - lim, 0.0) + np.minimum(alpha + lim, 0.0)
        )
    field = -p.mu_b * np.sin(p.omega * t) * np.sin(th_m - p.phi)
    if p.ellipticity != 0.0:
        field = field + p.ellipticity * p.mu_b * np.cos(p.omega * t) * np.cos(th_m - p.phi)
    out = np.empty(s.shape)
    out[0] = w_m
    out[1] = (field - tau) / p.i_m
    out[2] = w_h
    out[3] = (tau - p.gamma_hat * w_h) / p.i_h
    return out


def rk4_step(p: Params, t: float, s: np.ndarray, u: float | np.ndarray, dt: float) -> np.ndarray:
    """One RK4 step of size dt from time t, with the button state u held constant."""
    k1 = rhs(p, t, s, u)
    k2 = rhs(p, t + 0.5 * dt, s + 0.5 * dt * k1, u)
    k3 = rhs(p, t + 0.5 * dt, s + 0.5 * dt * k2, u)
    k4 = rhs(p, t + dt, s + dt * k3, u)
    return s + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def rest_state(p: Params, heading: float | np.ndarray = 0.0) -> np.ndarray:
    """Boat at rest, button released: hull at `heading`, magnet at heading - alpha0."""
    h = np.asarray(heading, dtype=float)
    z = np.zeros_like(h)
    return np.array([h - p.alpha0 + z, z, h, z])


def advance(
    p: Params, s: np.ndarray, n0: int, n_steps: int, button: Button | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Ensemble integrator for sweeps: n_steps from step index n0.

    The button is sampled at the middle of each step and held over the step, so
    press and release times are rounded to the grid (error up to dt / 2). Use
    `simulate` when exact event times matter.

    Returns the new state and the time averages of (theta_m, theta_h) over the steps.
    """
    dt = p.dt
    acc = np.zeros((2,) + s.shape[1:])
    for n in range(n0, n0 + n_steps):
        t = n * dt
        u = 0.0 if button is None else button(t + 0.5 * dt)
        acc[0] += s[0]
        acc[1] += s[2]
        s = rk4_step(p, t, s, u, dt)
    return s, acc / n_steps


def run_beats(
    p: Params, s0: np.ndarray, n_beats: int, button: Button | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Integrate over n_beats field periods.

    Returns the final state and the beat averages of theta_m and theta_h (not wrapped),
    each of shape (n_beats, ...).
    """
    spb = p.steps_per_beat
    s = np.array(s0, dtype=float)
    means = np.empty((n_beats, 2) + s.shape[1:])
    for b in range(n_beats):
        s, means[b] = advance(p, s, b * spb, spb, button)
    return s, means[:, 0], means[:, 1]


def simulate(
    p: Params,
    s0: np.ndarray,
    events: Sequence[tuple[float, int]],
    n_steps: int,
    sample_every: int = 1,
    pos0: tuple[float, float] = (0.0, 0.0),
) -> dict[str, np.ndarray]:
    """Reference run of one boat from an input timeline, with exact event times.

    events: (time, state) pairs sorted by time, state 1 = press, 0 = release; the button
    starts released. A step containing events is split at each event time, so the result
    does not depend on how the events fall on the grid.

    The position integrates x' = v cos(theta_h), y' = v sin(theta_h) with the same RK4
    (no banks or gates here: those belong to the race, Phase 2).

    Returns t, the states (n_samples, 4) and the positions (n_samples, 2) every
    `sample_every` steps, including the initial state.
    """
    dt = p.dt
    # Augmented state: (theta_m, theta_m', theta_h, theta_h', x, y).
    z = np.concatenate([np.asarray(s0, dtype=float), np.asarray(pos0, dtype=float)])
    step = lambda t, z, u, h: boat_step(p, t, z, u, h)  # noqa: E731

    ts, zs = [0.0], [z.copy()]
    u, ie = 0.0, 0
    for n in range(n_steps):
        t, t_next = n * dt, (n + 1) * dt
        while ie < len(events) and events[ie][0] < t_next:
            te = max(events[ie][0], t)
            if te > t:
                z = step(t, z, u, te - t)
                t = te
            u = float(events[ie][1])
            ie += 1
        z = step(t, z, u, t_next - t)
        if (n + 1) % sample_every == 0:
            ts.append(t_next)
            zs.append(z.copy())
    out = np.array(zs)
    return {"t": np.array(ts), "state": out[:, :4], "pos": out[:, 4:]}


def boat_rhs(p: Params, t: float, z: np.ndarray, u: float, speed: float) -> np.ndarray:
    """Augmented state z = (theta_m, theta_m', theta_h, theta_h', x, y) of one boat."""
    d = np.empty(6)
    d[:4] = rhs(p, t, z[:4], u)
    d[4] = speed * p.v * np.cos(z[2])
    d[5] = speed * p.v * np.sin(z[2])
    return d


def boat_step(
    p: Params, t: float, z: np.ndarray, u: float, h: float, speed: float = 1.0
) -> np.ndarray:
    """One RK4 step of size h for the augmented state; button state and speed held."""
    k1 = boat_rhs(p, t, z, u, speed)
    k2 = boat_rhs(p, t + 0.5 * h, z + 0.5 * h * k1, u, speed)
    k3 = boat_rhs(p, t + 0.5 * h, z + 0.5 * h * k2, u, speed)
    k4 = boat_rhs(p, t + h, z + h * k3, u, speed)
    return z + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


def periodic_button(t_press: float | np.ndarray, duty: float | np.ndarray, period: float) -> Button:
    """Ideal presses: held on [t_press + n period, t_press + (n + duty) period) for all n."""

    def button(t: float) -> np.ndarray:
        return (np.mod(t - t_press, period) < duty * period).astype(float)

    return button


def timeline_button(t_on: np.ndarray, t_off: np.ndarray, period: float) -> Button:
    """Presses with one press and one release time per beat and per ensemble member.

    t_on, t_off: shape (n_beats, N), with t_on[b] near b * period. The button is held
    when t lies in [t_on, t_off) of any beat; a beat with t_off <= t_on has no press.
    """
    n_beats = t_on.shape[0]

    def button(t: float) -> np.ndarray:
        b = int(np.floor(t / period))
        u = np.zeros(t_on.shape[1], dtype=bool)
        for j in (b - 1, b, b + 1):
            if 0 <= j < n_beats:
                u |= (t_on[j] <= t) & (t < t_off[j])
        return u.astype(float)

    return button
