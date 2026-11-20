"""Courses and races: one boat, banks, obstacles, gates, timer, recorded input timeline.

Course files are courses/*.json (format in CLAUDE.md, "Courses"). Conventions:
- pond.banks: list of polygons. The first is the shoreline (the boat stays inside); any
  further polygon is an island (the boat stays outside).
- obstacles: circles {"type": "circle", "c": [x, y], "r": r}.
- gates: segments a-b, to be crossed in order, in either direction. Crossing the last
  gate finishes the race.
- The boat is a disc of radius `boat_radius` for collisions and a point for gates.

A race advances by fixed steps dt. Button events carry exact times; a step containing an
event is split at that time (dynamics.boat_step), so the run depends only on the input
timeline. After each step the boat is pushed out of any bank or obstacle it overlaps
(along the normal of the nearest edge) and, if it was, its forward speed is set to zero
for `stop_time` seconds; the rotational dynamics keep running. The speed is held constant
over a step, so the stop starts and ends on the step grid.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .dynamics import boat_step, rest_state
from .params import Params

STOP_TIME = 1.0  # s, forward motion stopped after a collision (CLAUDE.md)


@dataclass(frozen=True)
class Course:
    id: str
    name: str
    size: tuple[float, float]
    banks: list[np.ndarray]  # first: shoreline; others: islands
    circles: list[tuple[np.ndarray, float]]
    gates: list[tuple[np.ndarray, np.ndarray]]
    start_pos: np.ndarray
    start_heading: float
    phi: float
    phi_drift: float
    boat: str
    par: float | None
    raw: dict[str, Any] = field(repr=False, compare=False)


def load_course(path: str | Path) -> Course:
    with open(path) as f:
        d = json.load(f)
    pond = d["pond"]
    circles = []
    for ob in d.get("obstacles", []):
        if ob["type"] != "circle":
            raise ValueError(f"unknown obstacle type {ob['type']!r}")
        circles.append((np.asarray(ob["c"], dtype=float), float(ob["r"])))
    return Course(
        id=d["id"],
        name=d["name"],
        size=tuple(pond["size"]),
        banks=[np.asarray(poly, dtype=float) for poly in pond["banks"]],
        circles=circles,
        gates=[(np.asarray(g["a"], float), np.asarray(g["b"], float)) for g in d["gates"]],
        start_pos=np.asarray(d["start"]["pos"], dtype=float),
        start_heading=float(d["start"]["heading"]),
        phi=float(pond["phi"]),
        phi_drift=float(pond.get("phi_drift", 0.0)),
        boat=d["boat"],
        par=d.get("par"),
        raw=d,
    )


# --- geometry -------------------------------------------------------------------------


def inside_polygon(p: np.ndarray, poly: np.ndarray) -> bool:
    """Even-odd rule (ray casting along +x)."""
    x, y = p
    xs, ys = poly[:, 0], poly[:, 1]
    xs2, ys2 = np.roll(xs, -1), np.roll(ys, -1)
    crosses = (ys > y) != (ys2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = xs + (y - ys) * (xs2 - xs) / (ys2 - ys)
    return bool(np.count_nonzero(crosses & (x < x_at)) % 2)


def nearest_on_polygon(p: np.ndarray, poly: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    """Nearest point of the polygon's boundary, its distance, and the outward edge normal
    of the nearest edge for a counter-clockwise polygon (used when p is on the boundary)."""
    a = poly
    b = np.roll(poly, -1, axis=0)
    ab = b - a
    s = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.einsum("ij,ij->i", ab, ab), 0.0, 1.0)
    q = a + s[:, None] * ab
    dist = np.hypot(*(p - q).T)
    i = int(np.argmin(dist))
    normal = np.array([ab[i, 1], -ab[i, 0]]) / np.hypot(*ab[i])
    if signed_area(poly) < 0:
        normal = -normal
    return q[i], float(dist[i]), normal


def signed_area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def segment_crossing(p0: np.ndarray, p1: np.ndarray, a: np.ndarray, b: np.ndarray) -> float | None:
    """Fraction s in [0, 1] along p0 -> p1 where it crosses segment a-b, or None."""
    r, q = p1 - p0, b - a
    den = r[0] * q[1] - r[1] * q[0]
    if den == 0.0:
        return None
    w = a - p0
    s = (w[0] * q[1] - w[1] * q[0]) / den
    t = (w[0] * r[1] - w[1] * r[0]) / den
    if 0.0 <= s <= 1.0 and 0.0 <= t <= 1.0:
        return float(s)
    return None


def clearance(course: Course, p: np.ndarray) -> float:
    """Signed distance from p to the nearest bank or obstacle (negative inside one)."""
    best = np.inf
    for k, poly in enumerate(course.banks):
        _, d, _ = nearest_on_polygon(p, poly)
        inside = inside_polygon(p, poly)
        sign = (1.0 if inside else -1.0) if k == 0 else (-1.0 if inside else 1.0)
        best = min(best, sign * d)
    for c, r in course.circles:
        best = min(best, float(np.hypot(*(p - c))) - r)
    return float(best)


def push_out(course: Course, p: np.ndarray, radius: float) -> tuple[np.ndarray, bool]:
    """Move p so that the disc of `radius` around it overlaps no bank or obstacle."""
    hit = False
    for _ in range(4):
        moved = False
        for k, poly in enumerate(course.banks):
            q, d, n_out = nearest_on_polygon(p, poly)
            inside = inside_polygon(p, poly)
            water_side = inside if k == 0 else not inside
            if water_side and d >= radius:
                continue
            # unit vector from the boundary towards the water
            if d > 1e-12:
                n_water = (p - q) / d if water_side else (q - p) / d
            else:
                n_water = -n_out if k == 0 else n_out
            p = q + n_water * (radius + 1e-9)
            hit = moved = True
        for c, r in course.circles:
            d = float(np.hypot(*(p - c)))
            if d >= r + radius:
                continue
            n = (p - c) / d if d > 1e-12 else np.array([1.0, 0.0])
            p = c + n * (r + radius + 1e-9)
            hit = moved = True
        if not moved:
            break
    return p, hit


# --- race -----------------------------------------------------------------------------


class Race:
    """One boat on one course. Times are simulation seconds from the start."""

    def __init__(self, p: Params, course: Course, boat_radius: float) -> None:
        self.p = p.with_(phi=course.phi)
        self.course = course
        self.radius = boat_radius
        self.z = self._initial_state()
        self.moored = False  # True: the boat turns (or feels the wind) but does not move
        self.n = 0
        self.u = 0.0
        self.stop_timer = 0.0
        self.next_gate = 0
        self.gate_times: list[float] = []
        self.finish_time: float | None = None
        self.collisions = 0
        self.timeline: list[tuple[float, int]] = []  # recorded input (time, state)
        self._pending: deque[tuple[float, int]] = deque()

    # The dynamics live in the next three methods; a subclass replaces them and keeps the
    # heading in z[2] and the position in z[4:6].

    def _initial_state(self) -> np.ndarray:
        return np.concatenate(
            [rest_state(self.p, self.course.start_heading), self.course.start_pos]
        )

    def _advance(self, t: float, z: np.ndarray, h: float, speed: float) -> np.ndarray:
        return boat_step(self.p, t, z, self.u, h, speed)

    def _on_hit(self, z: np.ndarray) -> None:
        """Called after the boat was pushed out of a bank or obstacle."""

    @property
    def steer(self) -> tuple[float, float]:
        """Vector whose beat average says where the boat is going (used by the drill)."""
        return math.cos(self.heading), math.sin(self.heading)

    @property
    def t(self) -> float:
        return self.n * self.p.dt

    @property
    def pos(self) -> np.ndarray:
        return self.z[4:6]

    @property
    def heading(self) -> float:
        return float(self.z[2])

    @property
    def magnet(self) -> float:
        return float(self.z[0])

    @property
    def finished(self) -> bool:
        return self.finish_time is not None

    def set_button(self, t: float, state: int) -> None:
        """Queue a button event at time t (clamped to the current time; repeats ignored)."""
        if self._pending:
            last = self._pending[-1][1]
        else:
            last = self.timeline[-1][1] if self.timeline else 0
        if state == last:
            return
        t = max(float(t), self.t, self._pending[-1][0] if self._pending else -np.inf)
        self._pending.append((t, int(state)))

    def step(self) -> None:
        dt = self.p.dt
        t, t_next = self.t, (self.n + 1) * dt
        speed = 0.0 if self.stop_timer > 0.0 or self.moored else 1.0
        z = self.z
        p0 = z[4:6].copy()
        while self._pending and self._pending[0][0] < t_next:
            te, state = self._pending.popleft()
            if te > t:
                z = self._advance(t, z, te - t, speed)
                t = te
            self.u = float(state)
            self.timeline.append((te, state))
        z = self._advance(t, z, t_next - t, speed)
        self.n += 1
        if self.stop_timer > 0.0:
            self.stop_timer = max(0.0, self.stop_timer - dt)
        self._gates(p0, z[4:6], t_next - dt)
        pos, hit = push_out(self.course, z[4:6].copy(), self.radius)
        if hit:
            z[4:6] = pos
            self._on_hit(z)
            if self.stop_timer == 0.0:
                self.collisions += 1
            self.stop_timer = STOP_TIME
        self.z = z

    def _gates(self, p0: np.ndarray, p1: np.ndarray, t0: float) -> None:
        while self.next_gate < len(self.course.gates):
            a, b = self.course.gates[self.next_gate]
            s = segment_crossing(p0, p1, a, b)
            if s is None:
                return
            tc = t0 + s * self.p.dt
            self.gate_times.append(tc)
            self.next_gate += 1
            if self.next_gate == len(self.course.gates) and self.finish_time is None:
                self.finish_time = tc
            p0 = p0 + s * (p1 - p0)  # a single step may cross the next gate too

    def run_until(self, t_end: float) -> None:
        while self.t < t_end - 1e-12:
            self.step()


def replay(
    p: Params, course: Course, boat_radius: float, timeline: list[tuple[float, int]], t_end: float
) -> Race:
    """Race driven by a recorded input timeline up to t_end."""
    race = Race(p, course, boat_radius)
    for t, state in timeline:
        race.set_button(t, state)
    race.run_until(t_end)
    return race


@dataclass(frozen=True)
class Boat:
    id: str
    name: str
    radius: float
    params: dict[str, Any]  # overrides of the base parameter file (same keys)


def load_boat(path: str | Path) -> Boat:
    with open(path) as f:
        d = json.load(f)
    return Boat(id=d["id"], name=d["name"], radius=float(d["radius"]), params=dict(d["params"]))
