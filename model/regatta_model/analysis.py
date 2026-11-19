"""Measurements on simulated runs: lock, Lyapunov exponent, Floquet multipliers."""

from __future__ import annotations

import numpy as np

from .dynamics import Button, advance, rk4_step
from .params import Params


def window_spread(h: np.ndarray, window: int) -> np.ndarray:
    """Max minus min of h over each run of `window` consecutive beats.

    h: beat-averaged headings, not wrapped, shape (n_beats, ...). Entry j of the result
    covers beats j .. j + window - 1.
    """
    n = h.shape[0] - window + 1
    stack = np.stack([h[i : i + n] for i in range(window)])
    return stack.max(axis=0) - stack.min(axis=0)


def lock_flags(h: np.ndarray, window: int, tol: float) -> np.ndarray:
    """True where the beat-averaged heading stays within `tol` over `window` beats."""
    return window_spread(h, window) < tol


def lyapunov(
    p: Params,
    s0: np.ndarray,
    n_transient: int,
    n_beats: int,
    button: Button | None = None,
    d0: float = 1e-8,
    seed: int = 0,
) -> np.ndarray:
    """Largest Lyapunov exponent (1/s) by the two-trajectory method of Benettin et al.

    A copy displaced by d0 in a random direction of the 4-dimensional state follows each
    trajectory; the separation is measured and rescaled to d0 once per beat. The norm
    mixes angles (rad) and rates (rad/s); the exponent does not depend on that choice.
    """
    rng = np.random.default_rng(seed)
    spb = p.steps_per_beat
    s = np.array(s0, dtype=float)
    s, _ = advance(p, s, 0, n_transient * spb, button)
    e = rng.standard_normal(s.shape)
    e /= np.linalg.norm(e, axis=0)
    pair = np.stack([s, s + d0 * e], axis=1)  # (4, 2, ...)
    log_sum = np.zeros(s.shape[1:])
    for b in range(n_transient, n_transient + n_beats):
        pair, _ = advance(p, pair, b * spb, spb, button)
        diff = pair[:, 1] - pair[:, 0]
        d = np.linalg.norm(diff, axis=0)
        log_sum += np.log(d / d0)
        pair[:, 1] = pair[:, 0] + diff * (d0 / d)
    return log_sum / (n_beats * p.period)


def floquet_aligned(p: Params, eps: float = 1e-6) -> np.ndarray:
    """Largest Floquet multiplier (modulus) of the aligned still-tiller state.

    Aligned state: magnet along the field axis, hull at +alpha0 from it, at rest, button
    released. The monodromy matrix over one field period is obtained by central
    differences on the full model. Modulus > 1: the aligned state is unstable.
    Scalar parameters only.
    """
    spb = p.steps_per_beat
    base = np.array([p.phi, 0.0, p.phi + p.alpha0, 0.0])
    s = np.empty((4, 8))
    for j in range(4):
        s[:, 2 * j] = base
        s[:, 2 * j + 1] = base
        s[j, 2 * j] += eps
        s[j, 2 * j + 1] -= eps
    for n in range(spb):
        s = rk4_step(p, n * p.dt, s, 0.0, p.dt)
    mono = (s[:, 0::2] - s[:, 1::2]) / (2.0 * eps)
    return np.max(np.abs(np.linalg.eigvals(mono)))
