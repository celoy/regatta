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

Assumptions: the force does not depend on the boat's velocity (wind much faster than the
boat), the sail is isotropic (force along the wind, whatever the hull's heading), linear
hull drag, no yaw dynamics. The heading stored in z[2] is the direction of the velocity,
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
        return sail * self.v_max / (self.omega * math.hypot(1.0, self.omega * self.tau))


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
        dt=1.0 / d["steps_per_second"],
        phi=math.radians(d["phi_deg"]),
    )


def wind_rhs(p: WindParams, t: float, z: np.ndarray, u: float, speed: float) -> np.ndarray:
    """State z = (unused, unused, heading, unused, x, y, vx, vy)."""
    a = p.wind_angle(t)
    s = 1.0 if u else p.windage
    d = np.zeros(8)
    d[4] = speed * z[6]
    d[5] = speed * z[7]
    d[6] = (s * p.v_max * math.cos(a) - z[6]) / p.tau
    d[7] = (s * p.v_max * math.sin(a) - z[7]) / p.tau
    return d


SLOW = 0.03  # heading frozen below this fraction of v_max


class WindRace(Race):
    """Race of the wind boat: same course rules and input handling as `Race`."""

    def _initial_state(self) -> np.ndarray:
        z = np.zeros(8)
        z[2] = self.course.start_heading
        z[4:6] = self.course.start_pos
        return z

    def _advance(self, t: float, z: np.ndarray, h: float, speed: float) -> np.ndarray:
        p, u = self.p, self.u
        k1 = wind_rhs(p, t, z, u, speed)
        k2 = wind_rhs(p, t + 0.5 * h, z + 0.5 * h * k1, u, speed)
        k3 = wind_rhs(p, t + 0.5 * h, z + 0.5 * h * k2, u, speed)
        k4 = wind_rhs(p, t + h, z + h * k3, u, speed)
        z = z + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
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
    def magnet(self) -> float:  # no magnet; kept so that the viewer's histories work
        return self.heading
