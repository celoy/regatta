"""Model parameters, read from TOML. No default values live in the code.

Inertias are normalised by I_m + I_h = 1, so torques per unit total inertia are
in rad/s^2. Fields may be numpy arrays (one value per ensemble member) in sweeps;
dt is always a scalar.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

Real = Any  # float or numpy array broadcastable over the ensemble


@dataclass(frozen=True)
class Params:
    omega: Real  # field angular frequency, rad/s
    omega0: Real  # sqrt(mu B / (I_m + I_h)), rad/s; 0 switches the field off
    gamma_hat: Real  # hull yaw damping gamma / (I_m + I_h), 1/s
    inertia_ratio: Real  # I_m / I_h
    alpha0: Real  # tiller half-range, rad
    omega_s: Real  # tiller natural frequency, rad/s
    zeta: Real  # tiller damping ratio
    v: float  # boat speed
    dt: float  # time step, s
    phi: Real  # field axis, rad
    stop_ratio: float  # soft stops at +- stop_ratio * alpha0
    stop_k_ratio: float  # stop stiffness / k (0: no stops)

    # Derived quantities (I_m + I_h = 1).
    @property
    def i_m(self) -> Real:
        return self.inertia_ratio / (1.0 + self.inertia_ratio)

    @property
    def i_h(self) -> Real:
        return 1.0 / (1.0 + self.inertia_ratio)

    @property
    def i_red(self) -> Real:
        """Reduced inertia I_m I_h / (I_m + I_h) of the relative (tiller) motion."""
        return self.i_m * self.i_h

    @property
    def mu_b(self) -> Real:
        return self.omega0**2

    @property
    def k(self) -> Real:
        """Spring stiffness, from omega_s^2 = k (I_m + I_h) / (I_m I_h)."""
        return self.omega_s**2 * self.i_red

    @property
    def c(self) -> Real:
        """Tiller damping, from c / I_red = 2 zeta omega_s."""
        return 2.0 * self.zeta * self.omega_s * self.i_red

    @property
    def period(self) -> float:
        return 2.0 * np.pi / self.omega

    @property
    def steps_per_beat(self) -> int:
        """Steps per field period; the field period must be a multiple of dt."""
        n = self.period / self.dt
        if abs(n - round(n)) > 1e-9:
            raise ValueError("field period is not an integer number of time steps")
        return int(round(n))

    def with_(self, **changes: Real) -> Params:
        return replace(self, **changes)


def load_params(path: str | Path) -> Params:
    """Read a parameter file in the format of toy/params/default.toml."""
    with open(path, "rb") as f:
        d = tomllib.load(f)
    omega = 2.0 * np.pi * d["field_hz"]
    return Params(
        omega=omega,
        omega0=omega / d["omega_over_omega0"],
        gamma_hat=d["hull_damping"],
        inertia_ratio=d["inertia_ratio"],
        alpha0=np.deg2rad(d["alpha0_deg"]),
        omega_s=omega * d["omega_s_over_omega"],
        zeta=d["zeta"],
        v=d["v"],
        dt=1.0 / d["steps_per_second"],
        phi=np.deg2rad(d["phi_deg"]),
        stop_ratio=d["stop_ratio"],
        stop_k_ratio=d["stop_stiffness_ratio"],
    )
