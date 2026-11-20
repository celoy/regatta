"""Wind boat: a sail in a wind that turns once per beat (prototype, 2026-11-20).

Alternative to the magnet boat with the same one-button rhythm. The wind blows at constant
strength in the direction theta_w(t) = phi - omega t (clockwise, like the field). Holding
the button raises the sail; the hull has linear drag and no keel, and the hull's heading
plays no part in the dynamics:

    m v' = -c v + s(t) F w(t),   w = (cos theta_w, sin theta_w),
    s = 1 with the sail up, s = windage with it down.

With tau = m / c and v_max = F / c (the speed in a steady wind with the sail up):

    v' = (s v_max w - v) / tau.

Derived results (checked in model/tests/test_wind.py):
- The equation is linear, so in the periodic state the mean velocity is the mean force over
  c. Sail up for a fraction D of each beat, centred on the time t_c:
      <v> = v_max (1 - windage) sin(pi D) / pi * w(t_c).
  The boat goes where the wind blew at the middle of the hold; a later hold turns the
  course clockwise by the same fraction of a turn; D = 1/2 is the fastest.
- Sail left up (or down, with windage): the boat goes round a circle of radius
  s v_max / (omega sqrt(1 + omega^2 tau^2)), with no net motion.
- A change of the hold phase is followed with the time constant tau.

Sail as a vane with inertia (vane_ratio > 0; added 2026-11-20 at Chris's request). The sail
swings on the mast, at the angle theta_s. While it is up the wind pulls it round like a
weathervane; while it is furled it coasts and slows down on the pivot's friction:

    up:      theta_s'' = omega_v^2 sin(theta_w - theta_s) - 2 zeta_v omega_v theta_s'
    furled:  theta_s'' = - theta_s' / tau_f

The push on the hull is along the sail, with the area the sail shows to the wind:
s v_max max(0, cos(theta_w - theta_s)) (cos theta_s, sin theta_s) replaces s v_max w.

- Sail left up: it trails the wind by delta, sin(delta) = 2 zeta_v omega / omega_v, and the
  boat circles with radius cos(delta) times the value above.
- A sail at rest is caught by the wind at once if omega_v > omega / 2 (pendulum in the
  frame turning with the wind: relative speed omega below the separatrix speed 2 omega_v).
- The equations do not change under a rotation of the pond together with a shift of time,
  so for periodic holds the mean velocity turns degree for degree with the hold phase. Its
  angle from the wind at the middle of the hold and its size are measured (`hold_response`),
  not derived.
vane_ratio = 0 switches the vane off and gives back the isotropic sail above.

Assumptions: the force does not depend on the boat's velocity (wind much faster than the
boat), the sail is isotropic (force along the wind, whatever the hull's heading), linear
hull drag, no yaw dynamics of the hull; the vane's damping acts on its rotation over the
ground. The heading stored in z[2] is the direction of the velocity,
kept for drawing; it freezes when the boat is nearly at rest.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from .race import Race


@dataclass(frozen=True)
class WindParams:
    omega: float  # wind angular frequency, rad/s (one turn per beat)
    tau: float  # hull response time m / c, s
    v_max: float  # speed in a steady wind with the sail up, F / c
    windage: float  # wind force with the sail down, as a fraction of the force with it up
    omega_v: float  # vane frequency sqrt(wind torque / sail inertia), rad/s; 0: no vane
    zeta_v: float  # vane damping ratio while the sail is up
    tau_f: float  # coasting time of the furled sail, s
    dt: float  # time step, s
    phi: float  # wind direction at t = 0, rad

    @property
    def period(self) -> float:
        return 2.0 * math.pi / self.omega

    @property
    def steps_per_beat(self) -> int:
        n = self.period / self.dt
        if abs(n - round(n)) > 1e-9:
            raise ValueError("wind period is not an integer number of time steps")
        return int(round(n))

    def with_(self, **changes: Any) -> WindParams:
        return replace(self, **changes)

    def wind_angle(self, t: float) -> float:
        """Direction the wind blows towards."""
        return self.phi - self.omega * t

    def mean_speed(self, duty: float) -> float:
        """Mean speed in the periodic state for holds of duty cycle `duty`."""
        return self.v_max * (1.0 - self.windage) * math.sin(math.pi * duty) / math.pi

    def idle_radius(self, sail: float = 1.0) -> float:
        """Radius of the circle described with the sail held at `sail` (1 up, windage down)."""
        lag = math.cos(self.vane_lag) if sail == 1.0 else 1.0
        return lag * sail * self.v_max / (self.omega * math.hypot(1.0, self.omega * self.tau))

    @property
    def vane_lag(self) -> float:
        """Angle by which the raised sail trails a steadily turning wind (0 without vane)."""
        if not self.omega_v:
            return 0.0
        return math.asin(2.0 * self.zeta_v * self.omega / self.omega_v)


def load_wind_params(path: str | Path, overrides: dict[str, Any] | None = None) -> WindParams:
    with open(path, "rb") as f:
        d = tomllib.load(f)
    for key, value in (overrides or {}).items():
        if key not in d:
            raise KeyError(f"unknown parameter {key!r}")
        d[key] = value
    return WindParams(
        omega=2.0 * math.pi * d["wind_hz"],
        tau=d["tau"],
        v_max=d["v_max"],
        windage=d["windage"],
        omega_v=2.0 * math.pi * d["wind_hz"] * d["vane_ratio"],
        zeta_v=d["vane_zeta"],
        tau_f=d["vane_coast"],
        dt=1.0 / d["steps_per_second"],
        phi=math.radians(d["phi_deg"]),
    )


def wind_rhs(p: WindParams, t: float, z: np.ndarray, u: float, speed: float) -> np.ndarray:
    """State z = (theta_s, theta_s', heading, unused, x, y, vx, vy)."""
    a = p.wind_angle(t)
    d = np.zeros(8)
    push, direction = (1.0 if u else p.windage), a
    if p.omega_v:
        d[0] = z[1]
        if u:
            d[1] = p.omega_v**2 * math.sin(a - z[0]) - 2.0 * p.zeta_v * p.omega_v * z[1]
            push, direction = max(0.0, math.cos(a - z[0])), z[0]
        else:
            d[1] = -z[1] / p.tau_f
    d[4] = speed * z[6]
    d[5] = speed * z[7]
    d[6] = (push * p.v_max * math.cos(direction) - z[6]) / p.tau
    d[7] = (push * p.v_max * math.sin(direction) - z[7]) / p.tau
    return d


def wind_step(
    p: WindParams, t: float, z: np.ndarray, u: float, h: float, speed: float
) -> np.ndarray:
    """One RK4 step of size h; button state and speed factor held."""
    k1 = wind_rhs(p, t, z, u, speed)
    k2 = wind_rhs(p, t + 0.5 * h, z + 0.5 * h * k1, u, speed)
    k3 = wind_rhs(p, t + 0.5 * h, z + 0.5 * h * k2, u, speed)
    k4 = wind_rhs(p, t + h, z + h * k3, u, speed)
    return z + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)


SLOW = 0.03  # heading frozen below this fraction of v_max


class WindRace(Race):
    """Race of the wind boat: same course rules and input handling as `Race`."""

    def _initial_state(self) -> np.ndarray:
        z = np.zeros(8)
        z[0] = z[2] = self.course.start_heading  # sail at rest along the hull
        z[4:6] = self.course.start_pos
        return z

    def _advance(self, t: float, z: np.ndarray, h: float, speed: float) -> np.ndarray:
        p = self.p
        z = wind_step(p, t, z, self.u, h, speed)
        if math.hypot(z[6], z[7]) > SLOW * p.v_max:
            z[2] = math.atan2(z[7], z[6])
        return z

    def _on_hit(self, z: np.ndarray) -> None:
        z[6:8] = 0.0  # the boat loses its way

    @property
    def velocity(self) -> np.ndarray:
        return self.z[6:8]

    @property
    def steer(self) -> tuple[float, float]:
        return self.z[6] / self.p.v_max, self.z[7] / self.p.v_max

    @property
    def sail(self) -> float:
        """Direction the sail points to (the wind direction when there is no vane)."""
        return float(self.z[0]) if self.p.omega_v else self.p.wind_angle(self.t)

    @property
    def magnet(self) -> float:  # no magnet; kept so that the viewer's histories work
        return self.heading


def hold_response(p: WindParams, duty: float = 0.5, n_beats: int = 30) -> tuple[float, float]:
    """Periodic holds centred on the times the wind blows along +x: angle of the mean
    velocity (rad, positive = to the left of the wind at the middle of the hold) and mean
    speed. By the rotational symmetry the same two numbers hold for every direction."""
    p = p.with_(phi=0.0)
    n = p.steps_per_beat
    z = np.zeros(8)
    acc = np.zeros(2)
    for i in range(n_beats * n):
        t = i * p.dt
        phase = (t + 0.5 * p.dt) / p.period % 1.0  # the hold is centred on phase 0
        u = 1.0 if min(phase, 1.0 - phase) < 0.5 * duty else 0.0
        z = wind_step(p, t, z, u, p.dt, 0.0)
        if i >= (n_beats - 1) * n:
            acc += z[6:8]
    v = acc / n
    return math.atan2(v[1], v[0]), float(np.hypot(*v))
