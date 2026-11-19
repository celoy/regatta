"""Averaged theory of the rhythm lock, to be compared with the simulation.

Assumptions: (i) the stroke alpha(t) is the button signal filtered by the tiller
oscillator, the field torque and the hull drag being neglected in the relative motion;
(ii) the slow angle varies little over one beat. (ii) needs omega well above omega0; at
the default omega = 1.2 omega0 the formulas are a guide, not a prediction.

Slow variable. The tiller torque is internal, so the slow variable is the
inertia-weighted angle Theta_c = (I_m theta_m + I_h theta_h) / (I_m + I_h), with
theta_m = Theta_c + i_h alpha and theta_h = Theta_c - i_m alpha (i_m = I_m / (I_m + I_h),
i_h = 1 - i_m).

Stroke. For a periodic press of duty cycle D with the hold centred at field phase psi_c,

    u = D + sum_n (2 / (n pi)) sin(n pi D) cos(n (omega t - psi_c)),
    alpha = alpha0 (2 D - 1) + 2 alpha0 sum_n (2 / (n pi)) sin(n pi D) |H_n|
            cos(n (omega t - psi_c) - delta_n),
    H_n = omega_s^2 / (omega_s^2 - n^2 omega^2 + 2 i zeta omega_s n omega) = |H_n| e^{-i delta_n}.

Rectification. With Theta = Theta_c - phi, the beat average of the field torque is

    < -mu B sin(omega t) sin(Theta + i_h alpha) > = -mu B (C sin Theta + S cos Theta),
    C = < sin(omega t) cos(i_h alpha) >,  S = < sin(omega t) sin(i_h alpha) >,

the torque of a static field of relative strength R = hypot(C, S). For a stiff tiller
(alpha = +-alpha0, square stroke) C = 0 and

    S = (2 / pi) sin(pi D) sin(psi_c) sin(i_h alpha0)        (exact in that limit),

so the lock puts Theta_c at -sign(sin psi_c) 90 deg from the axis for every D: the
harmonics of the stroke cancel the shift of its mean. The duty cycle changes the grip
through sin(pi D) but moves the mean hull heading only by the recoil -i_m alpha_mean:

    mean hull heading = phi -+ 90 deg - i_m alpha0 (2 D - 1).

(The brief's "phi +- 90 deg - mean alpha" kept only the fundamental of the stroke.)

Kapitza torque. The field also shakes the boat at omega. For a rigid boat this adds the
slow torque -(omega0^4 / (4 omega^2)) sin(2 Theta), which pulls the magnet towards the
axis. The tiller compliance reduces it by the factor

    kappa = 1 - (I_h / I_m) omega^2 (omega_s^2 - omega^2)
                / ((omega_s^2 - omega^2)^2 + (2 zeta omega_s omega)^2),

(the magnet's receptance at omega: rigid-body term minus the in-phase spring term).

Slow equation:

    Theta'' + gamma_hat Theta' = -omega0^2 (C sin Theta + S cos Theta)
                                 - kappa (omega0^4 / (4 omega^2)) sin(2 Theta).

With the grip g = 2 (omega / omega0)^2 R / kappa (rectification over Kapitza) and C = 0:
|g| >= 1 gives one stable state, perpendicular to the axis; |g| < 1 gives two,
sin(Theta) = -g sign(S), mirror images about the perpendicular.
"""

from __future__ import annotations

import numpy as np

from .params import Params, Real

MATHIEU_Q = 0.908  # stability boundary of y'' + (a - 2 q cos 2x) y = 0 at a = 0 (recalled)
N_HARMONICS = 400
N_TIME = 1024


def wrap(x: Real) -> Real:
    """Wrap an angle to (-pi, pi]."""
    return -np.mod(-np.asarray(x) + np.pi, 2.0 * np.pi) + np.pi


def transfer(p: Params, n: Real = 1) -> tuple[Real, Real]:
    """Gain |H| and phase lag delta of the tiller at n times the field frequency."""
    re = p.omega_s**2 - (n * p.omega) ** 2
    im = 2.0 * p.zeta * p.omega_s * n * p.omega
    return p.omega_s**2 / np.hypot(re, im), np.arctan2(im, re)


def alpha_mean(p: Params, duty: Real) -> Real:
    return p.alpha0 * (2.0 * duty - 1.0)


def stroke_amplitude(p: Params, duty: Real) -> Real:
    """Amplitude of alpha at the field frequency: 2 alpha0 (2/pi) sin(pi D) |H(i omega)|."""
    gain, _ = transfer(p)
    return 2.0 * p.alpha0 * (2.0 / np.pi) * np.sin(np.pi * duty) * gain


def nominal_centre_phase(p: Params) -> float:
    """Hold-centre phase that puts the fundamental of the stroke in phase with the field."""
    _, delta = transfer(p)
    return float(0.5 * np.pi - delta)


def stroke(p: Params, duty: float, centre_phase: float) -> tuple[np.ndarray, np.ndarray]:
    """Field phase omega t on [0, 2 pi) and the periodic stroke alpha (scalar parameters)."""
    wt = np.arange(N_TIME) * 2.0 * np.pi / N_TIME
    n = np.arange(1, N_HARMONICS + 1)[:, None]
    gain, delta = transfer(p, n)
    coeff = (2.0 / (n * np.pi)) * np.sin(n * np.pi * duty) * gain
    series = np.sum(coeff * np.cos(n * (wt - centre_phase) - delta), axis=0)
    return wt, alpha_mean(p, duty) + 2.0 * p.alpha0 * series


def rectified(p: Params, duty: float, centre_phase: float) -> tuple[float, float]:
    """Coefficients (C, S) of the beat-averaged field torque -mu B (C sin + S cos)(Theta)."""
    wt, alpha = stroke(p, duty, centre_phase)
    beta = p.i_h * alpha
    return float(np.mean(np.sin(wt) * np.cos(beta))), float(np.mean(np.sin(wt) * np.sin(beta)))


def kapitza_factor(p: Params) -> Real:
    """kappa: Kapitza torque of the compliant boat over that of the rigid boat."""
    d = p.omega_s**2 - p.omega**2
    return 1.0 - (p.i_h / p.i_m) * p.omega**2 * d / (d**2 + (2 * p.zeta * p.omega_s * p.omega) ** 2)


def grip(p: Params, duty: float, centre_phase: float) -> float:
    """g = 2 (omega / omega0)^2 R / kappa; |g| >= 1 gives the perpendicular lock."""
    c, s = rectified(p, duty, centre_phase)
    return float(2.0 * (p.omega / p.omega0) ** 2 * np.hypot(c, s) / kapitza_factor(p))


def slow_torque(p: Params, theta: Real, c: float, s: float) -> Real:
    """Right-hand side of the slow equation (without the drag term)."""
    return -(p.omega0**2) * (c * np.sin(theta) + s * np.cos(theta)) - kapitza_factor(p) * (
        p.omega0**4 / (4.0 * p.omega**2)
    ) * np.sin(2.0 * theta)


def hull_headings(p: Params, duty: float, centre_phase: float) -> np.ndarray:
    """Predicted mean hull headings: stable zeros of the slow torque, minus the recoil."""
    c, s = rectified(p, duty, centre_phase)
    theta = np.linspace(-np.pi, np.pi, 7201)
    tq = slow_torque(p, theta, c, s)
    i = np.nonzero((tq[:-1] > 0.0) & (tq[1:] <= 0.0))[0]
    roots = theta[i] + (theta[i + 1] - theta[i]) * tq[i] / (tq[i] - tq[i + 1])
    return wrap(p.phi + roots - p.i_m * alpha_mean(p, duty))


def mathieu_threshold() -> float:
    """omega / omega0 above which the aligned still-tiller boat is stable (rigid, undamped).

    theta'' + omega0^2 sin(omega t) theta = 0 is Mathieu's equation with a = 0 and
    q = 2 omega0^2 / omega^2; stable for q < 0.908, i.e. omega / omega0 > 1.484.
    """
    return float(np.sqrt(2.0 / MATHIEU_Q))
