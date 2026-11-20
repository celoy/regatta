"""Tutorial drill: a moored boat (it turns but does not move) and a list of target headings.

Each stage asks the player to bring the boat onto a target heading and keep it there. With
the rotating field the heading is set by the press phase, so every stage is the same task
with the target moved: straight ahead, then a turn to the left (press earlier), then a turn
to the right (press later).

A stage is passed after `beats_needed` consecutive beats in which
- the beat-averaged heading is within `tolerance` of the target, and
- the button was pressed within the last 1.5 beats (the idle boat circles at about 13 deg
  per beat and would otherwise drift through the target and pass).

The drill only reads the race; call `update()` after every `Race.step()`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .params import Params
from .race import Course, Race
from .wind import WindParams, WindRace


def make_race(p: Params | WindParams, course: Course, boat_radius: float) -> Race:
    """The race that goes with the parameter type: magnet boat or wind boat."""
    cls = WindRace if isinstance(p, WindParams) else Race
    return cls(p, course, boat_radius)


def wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class Stage:
    name: str
    turn: float  # target change from the previous stage, rad; positive = to the left
    hint: list[str] = field(default_factory=list)


def load_stages(d: dict[str, Any]) -> tuple[list[Stage], float, int, float]:
    """Stages, tolerance (rad) and beats needed, from the `tutorial` block of a course."""
    stages = [
        Stage(s["name"], math.radians(s["turn_deg"]), list(s.get("hint", []))) for s in d["stages"]
    ]
    return (
        stages,
        math.radians(d["tolerance_deg"]),
        int(d["beats_needed"]),
        float(d.get("min_strength", 0.0)),
    )


class Drill:
    def __init__(
        self,
        p: Any,
        course: Course,
        boat_radius: float,
        stages: list[Stage],
        tolerance: float,
        beats_needed: int,
        min_strength: float = 0.0,
    ) -> None:
        self.race = make_race(p, course, boat_radius)
        self.race.moored = True
        self.stages = stages
        self.tolerance = tolerance
        self.beats_needed = beats_needed
        self.min_strength = min_strength  # wind boat: least mean speed / v_max that counts
        self.stage = 0
        self.target = course.start_heading + stages[0].turn
        self.streak = 0
        self.error = math.nan  # beat-averaged direction minus target, last beat
        self.strength = 0.0  # length of the beat-averaged steer vector, last beat
        self.passed_at: list[float] = []  # time at which each stage was passed
        self._sin = self._cos = 0.0
        self._u = 0.0
        self._last_press = -math.inf

    @property
    def done(self) -> bool:
        return self.stage >= len(self.stages)

    @property
    def current(self) -> Stage | None:
        return None if self.done else self.stages[self.stage]

    def update(self) -> None:
        race = self.race
        if race.u and not self._u:
            self._last_press = race.t
        self._u = race.u
        c, s = race.steer
        self._cos += c
        self._sin += s
        if race.n % race.p.steps_per_beat:
            return
        mean = math.atan2(self._sin, self._cos)
        self.strength = math.hypot(self._sin, self._cos) / race.p.steps_per_beat
        self._sin = self._cos = 0.0
        if self.done:
            return
        self.error = wrap(mean - self.target)
        pressed = race.t - self._last_press < 1.5 * race.p.period
        on_target = abs(self.error) <= self.tolerance and self.strength >= self.min_strength
        self.streak = self.streak + 1 if on_target and pressed else 0
        if self.streak >= self.beats_needed:
            self.passed_at.append(race.t)
            self.stage += 1
            self.streak = 0
            if not self.done:
                self.target += self.stages[self.stage].turn


def load_drill(p: Any, course: Course, boat_radius: float) -> Drill:
    return Drill(p, course, boat_radius, *load_stages(course.raw["tutorial"]))


def is_tutorial(course: Course) -> bool:
    return "tutorial" in course.raw
