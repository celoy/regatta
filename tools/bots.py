"""Phase 2 bots: they race the test courses and give the fun-hypothesis table.

    .venv/bin/python tools/bots.py                       # all courses, bots, jitter levels
    .venv/bin/python tools/bots.py --courses T01 --seeds 4

Bots press once per beat and choose, at the start of each beat, when to press (the
press phase) and for how long (duty cycle 0.5). Timing jitter: independent Gaussian
errors of standard deviation sigma on the press and on the release.

- rhythm: a fixed press phase.
- pilot: aims at the centre of the next gate until it is within SWITCH of it; from then
  on it aims at a point LOOKAHEAD beyond the centre along the approach direction frozen at
  that moment (aiming at the centre to the end makes the bearing swing just before the
  gate; the aim point is pulled back to stay 1 unit inside the water; after a missed gate
  it turns back and aims at the centre again). Press phase from the measured relation
  heading = h0 - psi_c (analysis.heading_offset, one calibration run per boat and
  course), commanded heading = bearing + lead x (bearing - heading).
- naive: aims at the centre of the next gate with the uncalibrated formula
  heading = phi - psi_c - delta (theory.py, stiff-tiller rotating field), no lead.

Writes runs/phase2/<time>_bots/ (results.csv, summary.txt, meta.json, one input timeline
per best pilot run) and appends a line to docs/run_log.md. Nothing is overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from regatta_model import analysis as an
from regatta_model import theory as th
from regatta_model.params import Params, load_params
from regatta_model.race import Course, Race, clearance, load_boat, load_course

ROOT = Path(__file__).resolve().parents[1]
BASE_PARAMS = ROOT / "toy" / "params" / "candidate_r_rotating.toml"
DEG = np.pi / 180.0
ON_COURSE_TOL = 15 * DEG
MIN_GAP = 0.03  # s, shortest hold and shortest gap between holds
LOOKAHEAD = 2.5  # length units beyond the gate centre (pilot)
SWITCH = 3.0  # length units from the gate centre where the pilot freezes its approach


def wrap(x: float) -> float:
    return float(th.wrap(x))


def setup(course_id: str, boat_id: str | None = None) -> tuple[Params, Course, float, str]:
    """Parameters (base file + boat overrides + course phi), course, boat radius, boat id."""
    course = load_course(ROOT / "courses" / f"{course_id}.json")
    boat = load_boat(ROOT / "boats" / f"{boat_id or course.boat}.json")
    p = load_params(BASE_PARAMS, boat.params).with_(phi=course.phi)
    return p, course, boat.radius, boat.id


@dataclass
class Bot:
    """Chooses the press phase psi_c of each beat; returns (psi_c, commanded heading)."""

    kind: str  # rhythm | pilot | naive
    h0: float  # heading for psi_c = 0 (pilot: measured; naive: formula)
    lead: float = 0.0
    psi_fixed: float = 0.0
    duty: float = 0.5
    frozen: dict[int, np.ndarray] = field(default_factory=dict)  # gate -> approach direction

    def reset(self) -> None:
        self.frozen.clear()

    def command(self, race: Race, heading: float) -> tuple[float, float]:
        if self.kind == "rhythm":
            return self.psi_fixed, self.h0 - self.psi_fixed
        gates = race.course.gates
        k = min(race.next_gate, len(gates) - 1)
        centre = 0.5 * (gates[k][0] + gates[k][1])
        target = centre
        if self.kind == "pilot":
            to_centre = centre - race.pos
            dist = float(np.hypot(*to_centre))
            if k not in self.frozen and dist < SWITCH:
                self.frozen[k] = to_centre / max(dist, 1e-9)
            elif k in self.frozen and dist > SWITCH + 0.5:
                del self.frozen[k]  # gate missed: come back to it from where the boat is
            if k in self.frozen:
                # pull the aim point back until it lies 1 unit inside the water
                for look in np.arange(LOOKAHEAD, 0.0, -0.25):
                    target = centre + look * self.frozen[k]
                    if clearance(race.course, target) >= 1.0:
                        break
                else:
                    target = centre
        d = target - race.pos
        bearing = float(np.arctan2(d[1], d[0]))
        wanted = bearing + self.lead * wrap(bearing - heading)
        return self.h0 - wanted, bearing


def make_bot(kind: str, p: Params, lead: float = 0.0, psi: float = 0.0) -> Bot:
    if kind == "naive":
        _, delta = th.transfer(p)
        return Bot("naive", h0=float(p.phi - delta))
    return Bot(kind, h0=an.heading_offset(p), lead=lead, psi_fixed=psi)


@dataclass
class Result:
    time: float  # finish time, nan if not finished
    on_course: float  # fraction of beats within ON_COURSE_TOL of the commanded heading
    scatter_deg: float  # rms of (heading - commanded) over the on-course beats
    collisions: int
    big_shifts: int  # beats where the press phase moved by more than 90 deg
    timeline: list[tuple[float, int]]


def run(
    p: Params, course: Course, radius: float, bot: Bot, sigma: float, seed: int, t_max: float
) -> Result:
    """Closed-loop race of one bot."""
    rng = np.random.default_rng(seed)
    bot.reset()
    race = Race(p, course, radius)
    period, spb = p.period, p.steps_per_beat
    heading = race.heading
    last_off, last_psi = -np.inf, None
    errors, shifts = [], 0
    b = 0
    while race.t < t_max and not race.finished:
        psi, wanted = bot.command(race, heading)
        if last_psi is not None and abs(wrap(psi - last_psi)) > 0.5 * np.pi:
            shifts += 1
        last_psi = psi
        t_on = b * period + np.mod(psi / p.omega - 0.5 * bot.duty * period, period)
        t_off = t_on + bot.duty * period
        t_on += sigma * rng.standard_normal()
        t_off += sigma * rng.standard_normal()
        t_on = max(t_on, race.t, last_off + MIN_GAP)
        t_off = max(t_off, t_on + MIN_GAP)
        race.set_button(t_on, 1)
        race.set_button(t_off, 0)
        last_off = t_off
        acc = 0.0
        for _ in range(spb):
            race.step()
            acc += race.heading
            if race.finished:
                break
        heading = acc / max(1, (race.n - b * spb))
        errors.append(wrap(heading - wanted))
        b += 1
    err = np.abs(np.array(errors[1:]))  # the first beat starts from rest
    on = err < ON_COURSE_TOL
    return Result(
        time=race.finish_time if race.finished else float("nan"),
        on_course=float(on.mean()) if err.size else float("nan"),
        scatter_deg=float(np.sqrt(np.mean(err[on] ** 2)) / DEG) if on.any() else float("nan"),
        collisions=race.collisions,
        big_shifts=shifts,
        timeline=race.timeline,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--courses", default="T01,T02,T03")
    ap.add_argument("--sigmas", default="0,20,40,80,120", help="ms")
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--leads", default="0,0.3", help="pilot leads to try")
    ap.add_argument("--t-max", type=float, default=90.0)
    ap.add_argument("--seed", type=int, default=20261122)
    ap.add_argument("--why", default="")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / "phase2" / f"{stamp}_bots"
    out.mkdir(parents=True, exist_ok=False)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        != ""
    )
    meta = {
        "time": stamp,
        "git": git.stdout.strip(),
        "dirty": dirty,
        "argv": sys.argv[1:],
        "seed": args.seed,
        "base_params": str(BASE_PARAMS.relative_to(ROOT)),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    lines: list[str] = []

    def say(text: str = "") -> None:
        print(text, flush=True)
        lines.append(text)

    sigmas = [float(x) / 1000.0 for x in args.sigmas.split(",")]
    leads = [float(x) for x in args.leads.split(",")]
    rows, table = [], {}
    for ci, cid in enumerate(args.courses.split(",")):
        p, course, radius, boat_id = setup(cid)
        say(f"== {cid} {course.name} (boat {boat_id})")
        bots = [(f"pilot_lead{lead:g}", make_bot("pilot", p, lead)) for lead in leads]
        bots.append(("naive", make_bot("naive", p)))
        for name, bot in bots:
            for sigma in sigmas:
                res = []
                for k in range(args.seeds):
                    seed = int(np.random.SeedSequence([args.seed, ci, k]).generate_state(1)[0])
                    r = run(p, course, radius, bot, sigma, seed, args.t_max)
                    res.append(r)
                    rows.append(
                        [
                            cid,
                            boat_id,
                            name,
                            1000 * sigma,
                            k,
                            r.time,
                            r.on_course,
                            r.scatter_deg,
                            r.collisions,
                            r.big_shifts,
                        ]
                    )
                times = np.array([r.time for r in res])
                table[(cid, name, sigma)] = (times, res)
                fin = np.isfinite(times)
                say(
                    f"  {name:12s} sigma {1000 * sigma:3.0f} ms: finished {fin.sum()}/{len(res)}"
                    f", time median {np.nanmedian(times) if fin.any() else np.nan:6.2f} s"
                    f" (best {np.nanmin(times) if fin.any() else np.nan:6.2f}), on course "
                    f"{np.nanmean([r.on_course for r in res]):.2f}, scatter "
                    f"{np.nanmean([r.scatter_deg for r in res]):4.1f} deg, collisions "
                    f"{np.mean([r.collisions for r in res]):.1f}"
                )
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "course",
                "boat",
                "bot",
                "sigma_ms",
                "seed_index",
                "time_s",
                "on_course",
                "scatter_deg",
                "collisions",
                "big_shifts",
            ]
        )
        for row in rows:
            w.writerow([f"{x:.6g}" if isinstance(x, float) else x for x in row])

    say()
    say("== Par (best pilot at 20 ms) and fun-hypothesis ratios (medians)")
    for cid in args.courses.split(","):
        best_name, best_med = None, np.inf
        for lead in leads:
            name = f"pilot_lead{lead:g}"
            med = (
                np.nanmedian(table[(cid, name, 0.02)][0]) if (cid, name, 0.02) in table else np.inf
            )
            if np.isfinite(med) and med < best_med:
                best_name, best_med = name, med
        if best_name is None:
            say(f"  {cid}: no pilot finished at 20 ms")
            continue
        times, res = table[(cid, best_name, 0.02)]
        k = int(np.nanargmin(times))
        par = float(times[k])
        (out / f"par_{cid}.json").write_text(
            json.dumps(
                {
                    "course": cid,
                    "bot": best_name,
                    "sigma_ms": 20,
                    "seed_index": k,
                    "time": par,
                    "timeline": res[k].timeline,
                }
            )
            + "\n"
        )
        slow = (
            np.nanmedian(table[(cid, best_name, 0.12)][0])
            if (cid, best_name, 0.12) in table
            else np.nan
        )
        naive = (
            np.nanmedian(table[(cid, "naive", 0.02)][0])
            if (cid, "naive", 0.02) in table
            else np.nan
        )
        say(
            f"  {cid}: par {par:.2f} s ({best_name}); pilot median at 20 ms {best_med:.2f} s; "
            f"120 ms / 20 ms = {slow / best_med:.2f}; "
            f"naive / pilot at 20 ms = {naive / best_med:.2f}"
        )
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    with open(ROOT / "docs" / "run_log.md", "a") as f:
        f.write(
            f"- {stamp} `{meta['git'][:8]}{'+' if dirty else ''}` "
            f"`tools/bots.py {' '.join(sys.argv[1:])}` -> `{out.relative_to(ROOT)}` {args.why}\n"
        )


if __name__ == "__main__":
    main()
