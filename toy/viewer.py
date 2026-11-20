"""Magnet Regatta toy viewer (pygame-ce): play the one-button race on the test courses.

    .venv/bin/python toy/viewer.py                     # the tutorial (moored boat)
    .venv/bin/python toy/viewer.py --course T01        # first course, its boat
    .venv/bin/python toy/viewer.py --course T03 --boat barge

Keys: Space the button (hold = magnet swung to one side), P pause (resumes after a
one-beat count-in), R restart, G ghost of the best run, S screenshot, L reload parameters,
courses and boats from their files, 0 tutorial, 1-3 test courses, B cycle boats, Esc quit.

How to steer: the field turns once per beat. The aim dial (right) has a hand that points
where a press made now (held for half a beat) would send the boat. Press every beat when
the hand points where you want to go; press earlier or later to turn.

Timing: pygame-ce key events carry no timestamp, so a press is timed when the loop polls
it. The loop polls at up to 240 Hz and draws at 60 Hz, so the timing error is at most
about 4 ms on a machine that keeps up. The simulation follows the wall clock in fixed
steps of 1/480 s and applies each press at its exact time (split step).

Headless check (no window): SDL_VIDEODRIVER=dummy and --frames N --fixed-fps 60
--bot pilot --screenshot out.png.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import pygame

from regatta_model import analysis as an
from regatta_model.drill import Drill, is_tutorial, load_drill
from regatta_model.params import Params, load_params
from regatta_model.race import Boat, Course, Race, load_boat, load_course

ROOT = Path(__file__).resolve().parents[1]
BASE_PARAMS = ROOT / "toy" / "params" / "game.toml"
COURSES = ["TUT", "T01", "T02", "T03"]  # keys 0-3
RUNS = ROOT / "runs" / "toy"

PAPER = (243, 236, 218)
WATER = (233, 228, 210)
INK = (43, 38, 33)
FAINT = (175, 165, 145)
RED = (165, 45, 35)
BLUE = (45, 75, 150)
GREEN = (60, 120, 60)

W, H = 1280, 860
SCALE = 54  # pixels per length unit
ORIGIN = (40, 70)  # screen position of the pond's top-left corner
STRIP = pygame.Rect(40, 732, 1080, 112)
PANEL_X = 1165
DIAL_C, DIAL_R = (1218, 170), 50
POLL_HZ, DRAW_HZ = 240, 60
RING_R = 1.0  # aim ring radius round the boat, length units
DISPLAY_DEFAULTS = {"field_arrow": True, "coils": True, "ring": False, "hint": []}


def load_setup(course_id: str, boat_id: str | None) -> tuple[Params, Course, Boat]:
    course = load_course(ROOT / "courses" / f"{course_id}.json")
    boat = load_boat(ROOT / "boats" / f"{boat_id or course.boat}.json")
    return load_params(BASE_PARAMS, boat.params), course, boat


class Viewer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.boats = sorted(p.stem for p in (ROOT / "boats").glob("*.json"))
        self.course_id = args.course
        self.boat_id = args.boat
        self.show_ghost = True
        self.font = pygame.font.Font(None, 26)  # pygame's bundled font
        self.small = pygame.font.Font(None, 20)
        self.big = pygame.font.Font(None, 56)
        self.bot = None
        self.load()

    # --- setup -----------------------------------------------------------------------

    def load(self) -> None:
        p, self.course, self.boat = load_setup(self.course_id, self.boat_id)
        self.boat_id = self.boat.id
        # tutorial courses run a drill on a moored boat instead of a race
        self.drill: Drill | None = (
            load_drill(p, self.course, self.boat.radius) if is_tutorial(self.course) else None
        )
        self.race = self.drill.race if self.drill else Race(p, self.course, self.boat.radius)
        self.p = self.race.p
        self.h0 = an.heading_offset(self.p)  # heading = h0 - (field phase at hold centre)
        # what the course shows (tutorial courses hide the field and add the aim ring)
        self.display = DISPLAY_DEFAULTS | self.course.raw.get("display", {})
        self.best = self.read_best()
        self.ghost = self.make_ghost()
        self.wake: deque[tuple[float, float]] = deque(maxlen=400)
        self.alpha_hist: deque[tuple[float, float]] = deque(maxlen=4000)
        self.head_hist: deque[tuple[float, float]] = deque(maxlen=4000)
        self.state = "countin"
        self.countin_left = self.p.period
        self.message = ""
        self.bot = None
        if self.args.bot and self.drill is None:
            sys.path.insert(0, str(ROOT / "tools"))
            import bots  # noqa: PLC0415

            self.bot = bots.make_bot(self.args.bot, self.p)
            self.bot.reset()
            self.bot_beat = 0
            self.bot_heading = self.race.heading
            self.bot_last_off = -np.inf

    def best_path(self) -> Path:
        """One best run per course, boat and exact set-up (parameters, gates, banks).

        A timeline only replays under the set-up it was recorded with, so the file name
        carries a hash of it; runs made before a parameter change are kept and not used.
        """
        c = self.course
        setup = repr((self.p, c.start_pos, c.start_heading, c.gates, c.banks, c.circles))
        sig = hashlib.sha1(setup.encode()).hexdigest()[:8]
        return RUNS / f"best_{c.id}_{self.boat.id}_{sig}.json"

    def read_best(self) -> dict | None:
        try:
            return json.loads(self.best_path().read_text())
        except (OSError, ValueError):
            return None

    def make_ghost(self) -> Race | None:
        if not self.best:
            return None
        ghost = Race(self.p, self.course, self.boat.radius)
        for t, s in self.best["timeline"]:
            ghost.set_button(t, s)
        return ghost

    # --- time and input --------------------------------------------------------------

    def display_time(self) -> float:
        """Time used for the field and the dial: runs through the count-in too."""
        if self.state == "countin":
            return self.race.t - self.countin_left
        return self.race.t

    def press(self, state: int) -> None:
        if self.state in ("running", "finished"):
            self.race.set_button(self.target, state)

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYUP and event.key == pygame.K_SPACE:
            self.press(0)
        if event.type != pygame.KEYDOWN:
            return True
        k = event.key
        if k == pygame.K_ESCAPE:
            return False
        if k == pygame.K_SPACE:
            self.press(1)
        elif k == pygame.K_p:
            if self.state == "running":
                self.state = "paused"
            elif self.state == "paused":
                self.state, self.countin_left = "countin", self.p.period
        elif k == pygame.K_r:
            self.load()
        elif k == pygame.K_l:
            self.load()
            self.message = "parameters reloaded"
        elif k == pygame.K_g:
            self.show_ghost = not self.show_ghost
        elif k == pygame.K_b:
            self.boat_id = self.boats[(self.boats.index(self.boat_id) + 1) % len(self.boats)]
            self.load()
        elif k in (pygame.K_0, pygame.K_1, pygame.K_2, pygame.K_3):
            self.course_id = COURSES[k - pygame.K_0]
            self.boat_id = None
            self.load()
        elif k == pygame.K_s:
            self.screenshot()
        return True

    def screenshot(self, path: Path | None = None) -> Path:
        if path is None:
            path = RUNS / "screens" / f"{time.strftime('%Y%m%d-%H%M%S')}_{self.course.id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(pygame.display.get_surface(), str(path))
        self.message = f"saved {path.name}"
        return path

    def advance(self, dt_wall: float) -> None:
        race = self.race
        if self.state == "countin":
            self.countin_left -= dt_wall
            if self.countin_left <= 0.0:
                self.state = "running"
                self.target = race.t
                held = pygame.key.get_pressed()[pygame.K_SPACE]
                if bool(held) != bool(race.u) and not self.bot:
                    race.set_button(race.t, int(held))
            return
        if self.state == "paused":
            return
        self.target = min(self.target + dt_wall, race.t + 0.25)  # no catch-up spiral

    def step_sim(self) -> None:
        race = self.race
        if self.state not in ("running", "finished"):
            return
        while race.t < self.target - 1e-12:
            if self.bot is not None:
                self.bot_step()
            race.step()
            if self.drill is not None:
                self.drill_step()
            if race.n % 8 == 0:
                self.alpha_hist.append((race.t, race.magnet - race.heading))
                self.head_hist.append((race.t, race.heading))
            if race.n % 48 == 0:
                self.wake.append(tuple(race.pos))
        if self.ghost is not None:
            while self.ghost.t < race.t - 1e-12:
                self.ghost.step()
        if race.finished and self.state == "running":
            self.state = "finished"
            self.finish()

    def bot_step(self) -> None:
        """Bot input at the start of each beat (same rule as tools/bots.py, no jitter)."""
        race, p = self.race, self.p
        spb = p.steps_per_beat
        if race.n % spb:
            return
        if race.n:
            hs = [h for t, h in self.head_hist if t > race.t - p.period]
            self.bot_heading = float(np.mean(hs)) if hs else race.heading
        psi, _ = self.bot.command(race, self.bot_heading)
        b = race.n // spb
        t_on = max(
            b * p.period + np.mod(psi / p.omega - 0.25 * p.period, p.period),
            race.t,
            self.bot_last_off + 0.03,
        )
        race.set_button(t_on, 1)
        race.set_button(t_on + 0.5 * p.period, 0)
        self.bot_last_off = t_on + 0.5 * p.period

    def finish(self) -> None:
        t = self.race.finish_time
        msg = f"finished in {t:.2f} s"
        if self.course.par:
            ratio = t / self.course.par
            medal = next(
                (m for m, r in (("gold", 1.0), ("silver", 1.15), ("bronze", 1.3)) if ratio <= r),
                "no medal",
            )
            msg += f"  ({ratio:.2f} x par: {medal})"
        if self.bot is None and (not self.best or t < self.best["time"]):
            msg += "  new best"
            RUNS.mkdir(parents=True, exist_ok=True)
            record = {
                "course": self.course.id,
                "boat": self.boat.id,
                "time": t,
                "timeline": self.race.timeline,
            }
            self.best_path().write_text(json.dumps(record) + "\n")
            self.best = record
        self.message = msg
        print(msg, flush=True)

    # --- drawing ---------------------------------------------------------------------

    def to_screen(self, xy) -> tuple[int, int]:
        x, y = xy
        return (round(ORIGIN[0] + x * SCALE), round(ORIGIN[1] + (self.course.size[1] - y) * SCALE))

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(PAPER)
        t = self.display_time()
        self.draw_pond(screen, t)
        self.draw_gates(screen)
        for i, (x, y) in enumerate(self.wake):
            if i % 2 == 0:
                pygame.draw.circle(screen, FAINT, self.to_screen((x, y)), 2)
        if self.ghost is not None and self.show_ghost:
            self.draw_boat(screen, self.ghost, ghost=True)
        self.draw_boat(screen, self.race)
        if self.drill is not None:
            self.draw_drill(screen, t)
        elif self.display["ring"]:
            self.draw_ring(screen, t)
        for i, line in enumerate(self.display["hint"]):
            self.text(screen, line, (ORIGIN[0] + 12, ORIGIN[1] + 8 + 20 * i), self.small, BLUE)
        self.draw_hud(screen)
        self.draw_dial(screen, t)
        self.draw_strip(screen, t)

    def field_angle(self, t: float) -> float:
        """Direction of B in world coordinates (angle from +x)."""
        p = self.p
        return p.phi + math.atan2(p.ellipticity * math.cos(p.omega * t), math.sin(p.omega * t))

    def draw_pond(self, screen: pygame.Surface, t: float) -> None:
        c = self.course
        shore = [self.to_screen(q) for q in c.banks[0]]
        pygame.draw.polygon(screen, WATER, shore)
        pygame.draw.polygon(screen, INK, shore, 3)
        for poly in c.banks[1:]:
            pts = [self.to_screen(q) for q in poly]
            pygame.draw.polygon(screen, PAPER, pts)
            pygame.draw.polygon(screen, INK, pts, 2)
        for centre, r in c.circles:
            cx, cy = self.to_screen(centre)
            pr = round(r * SCALE)
            pygame.draw.circle(screen, PAPER, (cx, cy), pr)
            for k in range(-pr, pr, 7):  # engraving hatch
                h = math.sqrt(max(pr * pr - k * k, 0))
                pygame.draw.line(screen, FAINT, (cx + k, cy - h), (cx + k, cy + h), 1)
            pygame.draw.circle(screen, INK, (cx, cy), pr, 2)
        # two coil pairs: along the field axis (sin) and across it (e cos)
        p = self.p
        w, h = c.size
        along, across = math.sin(p.omega * t), p.ellipticity * math.cos(p.omega * t)
        e_phi = np.array([math.cos(p.phi), math.sin(p.phi)])
        e_perp = np.array([-e_phi[1], e_phi[0]])
        centre = np.array([w / 2, h / 2])
        if self.display["coils"]:
            for axis, current in ((e_phi, along), (e_perp, across)):
                reach = min(
                    abs(w / 2 / axis[0]) if axis[0] else 1e9,
                    abs(h / 2 / axis[1]) if axis[1] else 1e9,
                )
                for sign in (-1, 1):
                    self.draw_coil(screen, centre + sign * reach * axis, axis, current)
        if not self.display["field_arrow"]:
            return
        a = self.field_angle(t)
        strength = math.hypot(along, across)
        tip = centre + 2.2 * strength * np.array([math.cos(a), math.sin(a)])
        self.arrow(screen, centre, tip, FAINT, 3)

    def draw_coil(self, screen, pos, axis, current) -> None:
        normal = np.array([-axis[1], axis[0]])
        half_l, half_w = 0.45, 0.8
        corners = [
            pos + sx * half_l * axis + sy * half_w * normal
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]
        pts = [self.to_screen(q) for q in corners]
        level = min(1.0, abs(current))
        tint = RED if current > 0 else BLUE
        fill = tuple(round(PAPER[i] + (tint[i] - PAPER[i]) * 0.6 * level) for i in range(3))
        pygame.draw.polygon(screen, fill, pts)
        for s in np.linspace(-0.8, 0.8, 7):  # windings
            a = pos + s * half_w * normal - half_l * axis
            b = pos + s * half_w * normal + half_l * axis
            pygame.draw.line(screen, INK, self.to_screen(a), self.to_screen(b), 1)
        pygame.draw.polygon(screen, INK, pts, 2)

    def arrow(self, screen, a, b, colour, width) -> None:
        pa, pb = self.to_screen(a), self.to_screen(b)
        pygame.draw.line(screen, colour, pa, pb, width)
        d = np.subtract(pb, pa).astype(float)
        n = np.hypot(*d)
        if n < 1:
            return
        d /= n
        side = np.array([-d[1], d[0]])
        head = [
            pb,
            tuple(np.array(pb) - 14 * d + 6 * side),
            tuple(np.array(pb) - 14 * d - 6 * side),
        ]
        pygame.draw.polygon(screen, colour, head)

    def draw_gates(self, screen) -> None:
        for i, (a, b) in enumerate(self.course.gates):
            nxt = i == self.race.next_gate
            colour = FAINT if i < self.race.next_gate else (RED if nxt else INK)
            pa, pb = self.to_screen(a), self.to_screen(b)
            n = max(1, int(np.hypot(pb[0] - pa[0], pb[1] - pa[1]) // 10))
            for k in range(0, n, 2):  # dashed line
                q0 = np.add(pa, np.subtract(pb, pa) * k / n)
                q1 = np.add(pa, np.subtract(pb, pa) * min(k + 1, n) / n)
                pygame.draw.line(screen, colour, q0, q1, 2 if nxt else 1)
            for q in (pa, pb):
                pygame.draw.circle(screen, PAPER, q, 8)
                pygame.draw.circle(screen, colour, q, 8, 2)
            label = self.small.render(str(i + 1), True, colour)
            screen.blit(label, (pa[0] + 10, pa[1] - 6))
        sx, sy = self.to_screen(self.course.start_pos)
        pygame.draw.line(screen, INK, (sx - 6, sy - 14), (sx - 6, sy + 14), 2)

    def draw_boat(self, screen, race: Race, ghost: bool = False) -> None:
        x, y = race.pos
        th, tm = race.heading, race.magnet
        c, s = math.cos(th), math.sin(th)
        hull = [(0.5, 0.0), (0.2, 0.2), (-0.42, 0.2), (-0.42, -0.2), (0.2, -0.2)]
        pts = [self.to_screen((x + c * u - s * v, y + s * u + c * v)) for u, v in hull]
        if ghost:
            pygame.draw.polygon(screen, FAINT, pts, 2)
            return
        pygame.draw.polygon(screen, PAPER, pts)
        pygame.draw.polygon(screen, INK, pts, 2)
        cm, sm = math.cos(tm), math.sin(tm)
        north = self.to_screen((x + 0.32 * cm, y + 0.32 * sm))
        south = self.to_screen((x - 0.32 * cm, y - 0.32 * sm))
        mid = self.to_screen((x, y))
        pygame.draw.line(screen, RED, mid, north, 6)
        pygame.draw.line(screen, BLUE, mid, south, 6)
        pygame.draw.circle(screen, INK, mid, 3)
        if race.stop_timer > 0:
            pygame.draw.circle(screen, RED, mid, round(0.6 * SCALE), 1)

    def drill_step(self) -> None:
        drill = self.drill
        stage = drill.stage
        drill.update()
        if drill.stage != stage:
            self.message = f"{drill.stages[stage].name}: done"

    def draw_drill(self, screen, t: float) -> None:
        """Moored boat: ring with a green part (press while the dot is there) and a red part.

        The dot sits at the heading a press made now would give, so the green part, centred
        on the target heading and as wide as the tolerance, is both where to press and where
        the boat will point. Pips under the ring count the beats held on target.
        """
        drill, race = self.drill, self.race
        tut = self.course.raw["tutorial"]
        radius = tut.get("ring_radius", 1.5)
        pos = race.pos

        def on_ring(angle, r=radius):
            return self.to_screen(pos + r * np.array([math.cos(angle), math.sin(angle)]))

        def band(a0, a1, colour):
            n = max(2, int(abs(a1 - a0) / math.radians(3)))
            outer = [on_ring(a0 + (a1 - a0) * k / n, radius + 0.09) for k in range(n + 1)]
            inner = [on_ring(a0 + (a1 - a0) * k / n, radius - 0.09) for k in range(n + 1)]
            pygame.draw.polygon(screen, colour, outer + inner[::-1])

        if drill.done:
            band(0.0, 2 * math.pi, GREEN)
            lines, title = tut.get("done", []), "Done"
        else:
            tol = drill.tolerance
            band(drill.target + tol, drill.target - tol + 2 * math.pi, RED)
            band(drill.target - tol, drill.target + tol, GREEN)
            stage = drill.current
            lines = stage.hint
            title = f"{drill.stage + 1}/{len(drill.stages)}  {stage.name}"
        if race.u and race.timeline:  # arc swept by the dot since the press
            a0, a1 = self.aim_angle(race.timeline[-1][0]), self.aim_angle(t)
            arc = [on_ring(a0 + (a1 - a0) * k / 24, radius - 0.28) for k in range(25)]
            pygame.draw.lines(screen, BLUE, False, arc, 4)
        dot = on_ring(self.aim_angle(t))
        pygame.draw.circle(screen, PAPER, dot, 12)
        pygame.draw.circle(screen, BLUE, dot, 10)
        x, y = ORIGIN[0] + 16, ORIGIN[1] + 12
        self.text(screen, title, (x, y), self.font)
        for i, line in enumerate(lines):
            self.text(screen, line, (x, y + 30 + 22 * i), self.small, BLUE)
        if not drill.done:  # pips: beats held on target
            cx, cy = self.to_screen(pos - np.array([0.0, radius + 0.6]))
            for i in range(drill.beats_needed):
                c = (cx + 26 * (i - 0.5 * (drill.beats_needed - 1)), cy)
                pygame.draw.circle(screen, GREEN if i < drill.streak else PAPER, c, 8)
                pygame.draw.circle(screen, INK, c, 8, 1)

    def aim_angle(self, t: float) -> float:
        """Heading that a press made at time t (held half a beat) settles on."""
        return self.h0 - self.p.omega * t - 0.5 * math.pi

    def draw_ring(self, screen, t: float) -> None:
        """Ring round the boat: a dot turning with the aim, and a mark at the bow.

        The dot sits at the heading a press made now would give, so pressing as it
        passes the bow mark (beat-averaged heading) keeps the boat on its course.
        While the button is held, the arc swept by the dot since the press is drawn.
        """
        race = self.race
        pos = race.pos

        def on_ring(angle, r=RING_R):
            return self.to_screen(pos + r * np.array([math.cos(angle), math.sin(angle)]))

        centre = self.to_screen(pos)
        pygame.draw.circle(screen, FAINT, centre, round(RING_R * SCALE), 1)
        last = [h for tt, h in self.head_hist if tt > race.t - self.p.period]
        bow = math.atan2(np.mean(np.sin(last)), np.mean(np.cos(last))) if last else race.heading
        tip = on_ring(bow, RING_R + 0.05)
        base = [on_ring(bow + s * 0.12, RING_R + 0.35) for s in (-1, 1)]
        pygame.draw.polygon(screen, INK, [tip, *base])
        if race.u and race.timeline:
            t_on = race.timeline[-1][0]
            a0, a1 = self.aim_angle(t_on), self.aim_angle(t)
            arc = [on_ring(a0 + (a1 - a0) * k / 24) for k in range(25)]
            pygame.draw.lines(screen, BLUE, False, arc, 4)
        pygame.draw.circle(screen, BLUE, on_ring(self.aim_angle(t)), 7)

    def text(self, screen, s: str, pos, font=None, colour=INK) -> None:
        screen.blit((font or self.font).render(s, True, colour), pos)

    def draw_hud(self, screen) -> None:
        race = self.race
        clock = race.finish_time if race.finished else race.t
        self.text(screen, f"{self.course.id}  {self.course.name}", (40, 22))
        if self.drill is None:  # the drill is not timed
            self.text(screen, f"{clock:6.2f} s", (300, 14), self.big)
        n_gates = len(self.course.gates)
        info = f"gate {min(race.next_gate + 1, n_gates)}/{n_gates}" if n_gates else ""
        if self.course.par:
            info += f"   par {self.course.par:.1f} s"
        if self.best:
            info += f"   best {self.best['time']:.2f} s"
        self.text(screen, info, (680, 22))
        x0 = PANEL_X
        self.text(screen, self.boat.name, (x0, 22))
        self.text(screen, "aim", (DIAL_C[0] - 14, DIAL_C[1] - DIAL_R - 24), self.small)
        # steadiness: change of the beat-averaged heading from the previous beat to the
        # last one (the hull also swings within each beat; that wobble is shown as a number)
        T = self.p.period
        last = [h for t, h in self.head_hist if t > race.t - T]
        prev = [h for t, h in self.head_hist if race.t - 2 * T < t <= race.t - T]
        drift = math.degrees(abs(np.mean(last) - np.mean(prev))) if last and prev else 0.0
        wobble = math.degrees(max(last) - min(last)) if len(last) > 1 else 0.0
        y = DIAL_C[1] + DIAL_R + 30
        self.text(screen, f"turn {drift:3.0f} deg/b", (x0, y), self.small)
        bar = pygame.Rect(x0, y + 18, 105, 10)
        pygame.draw.rect(screen, INK, bar, 1)
        fill = bar.copy()
        fill.width = round(105 * min(1.0, drift / 40.0))
        pygame.draw.rect(screen, GREEN if drift < 10 else RED, fill)
        self.text(screen, f"wobble {wobble:3.0f} deg", (x0, y + 34), self.small, FAINT)
        self.text(screen, f"collisions {race.collisions}", (x0, y + 54), self.small)
        keys = [
            "Space: tiller",
            "P pause",
            "R restart",
            "G ghost",
            "S screenshot",
            "L reload",
            "0 tutorial",
            "1-3 course",
            "B boat",
            "Esc quit",
        ]
        for i, k in enumerate(keys):
            self.text(screen, k, (x0, y + 90 + 20 * i), self.small, FAINT)
        status = {"countin": "ready...", "paused": "paused (P)"}.get(self.state, "")
        if status:
            self.text(screen, status, (480, 330), self.big, RED)
        if self.message:
            self.text(screen, self.message, (40, 46), self.small, RED)

    def draw_dial(self, screen, t: float) -> None:
        """Hand: heading a press made at time t would give (D = 0.5)."""
        cx, cy = DIAL_C
        pygame.draw.circle(screen, PAPER, DIAL_C, DIAL_R)
        pygame.draw.circle(screen, INK, DIAL_C, DIAL_R, 2)
        for k in range(12):
            a = k * math.pi / 6
            pygame.draw.line(
                screen,
                FAINT,
                (cx + 0.85 * DIAL_R * math.cos(a), cy - 0.85 * DIAL_R * math.sin(a)),
                (cx + DIAL_R * math.cos(a), cy - DIAL_R * math.sin(a)),
                1,
            )

        def ray(angle, length, colour, width):
            end = (cx + length * math.cos(angle), cy - length * math.sin(angle))
            pygame.draw.line(screen, colour, DIAL_C, end, width)

        race = self.race
        gates = self.course.gates
        if gates:
            a, b = gates[min(race.next_gate, len(gates) - 1)]
            d = 0.5 * (a + b) - race.pos
            ray(math.atan2(d[1], d[0]), DIAL_R, RED, 2)  # bearing to the next gate
        elif self.drill is not None and not self.drill.done:
            ray(self.drill.target, DIAL_R, GREEN, 2)  # the drill's target heading
        ray(race.heading, 0.6 * DIAL_R, INK, 4)  # boat heading
        ray(self.aim_angle(t), 0.95 * DIAL_R, BLUE, 2)
        pygame.draw.circle(screen, INK, DIAL_C, 4)

    def draw_strip(self, screen, t: float) -> None:
        r = STRIP
        pygame.draw.rect(screen, PAPER, r)
        pygame.draw.rect(screen, INK, r, 1)
        T = self.p.period
        t0, t1 = t - 3 * T, t + T

        def sx(tt):
            return r.left + (tt - t0) / (t1 - t0) * r.width

        mid = r.top + 44
        amp = 30
        ts = np.linspace(t0, t1, 400)
        p = self.p
        along = [(sx(u), mid - amp * math.sin(p.omega * u)) for u in ts]
        across = [(sx(u), mid - amp * p.ellipticity * math.cos(p.omega * u)) for u in ts]
        pygame.draw.lines(screen, FAINT, False, across, 1)
        pygame.draw.lines(screen, INK, False, along, 2)
        k0 = math.ceil(t0 * p.omega / math.pi)
        for k in range(k0, int(t1 * p.omega / math.pi) + 1):  # field reversals
            x = sx(k * math.pi / p.omega)
            pygame.draw.line(screen, FAINT, (x, mid - amp - 6), (x, mid + amp + 6), 1)
        stroke = [(sx(tt), mid - amp * a / p.alpha0) for tt, a in self.alpha_hist if tt > t0]
        if len(stroke) > 1:
            pygame.draw.lines(screen, RED, False, stroke, 2)
        # button holds
        y_bar = r.bottom - 18
        events = list(self.race.timeline)
        on = None
        for te, s in events:
            if s == 1:
                on = te
            elif on is not None:
                if te > t0:
                    pygame.draw.rect(
                        screen, INK, (sx(max(on, t0)), y_bar, sx(te) - sx(max(on, t0)), 10)
                    )
                on = None
        if on is not None:
            pygame.draw.rect(screen, INK, (sx(max(on, t0)), y_bar, sx(t) - sx(max(on, t0)), 10))
        pygame.draw.line(screen, RED, (sx(t), r.top), (sx(t), r.bottom), 1)
        self.text(screen, "field (along / across)", (r.left + 6, r.top + 4), self.small, FAINT)
        self.text(screen, "tiller", (r.left + 6, r.bottom - 38), self.small, RED)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--course", default="TUT", choices=COURSES)
    ap.add_argument("--boat", default=None)
    ap.add_argument("--frames", type=int, default=0, help="quit after N frames (0: never)")
    ap.add_argument("--fixed-fps", type=float, default=0.0, help="advance 1/F s per frame")
    ap.add_argument("--bot", choices=["pilot", "naive"], default=None, help="a bot drives")
    ap.add_argument("--screenshot", type=Path, default=None, help="save at the end")
    args = ap.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Magnet Regatta (toy)")
    viewer = Viewer(args)
    clock = pygame.time.Clock()
    last = time.perf_counter()
    last_draw = -1.0
    frame = 0
    running = True
    while running:
        now = time.perf_counter()
        dt_wall = 1.0 / args.fixed_fps if args.fixed_fps else now - last
        last = now
        viewer.advance(dt_wall)
        for event in pygame.event.get():
            running = viewer.handle(event) and running
        viewer.step_sim()
        if args.fixed_fps or now - last_draw >= 1.0 / DRAW_HZ:
            viewer.draw(screen)
            pygame.display.flip()
            last_draw = now
        frame += 1
        if args.frames and frame >= args.frames:
            running = False
        if not args.fixed_fps:
            clock.tick_busy_loop(POLL_HZ)
    if args.screenshot:
        viewer.draw(screen)
        viewer.screenshot(args.screenshot)
    pygame.quit()


if __name__ == "__main__":
    main()
