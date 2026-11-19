"""Phase 1 sweeps (CLAUDE.md, "Sweeps" 1 to 5, plus a design scan). Headless, CSV outputs.

    .venv/bin/python tools/sweeps.py --params toy/params/default.toml
    .venv/bin/python tools/sweeps.py --params toy/params/default.toml --only lock,jitter

Each call writes a new directory runs/phase1/<time>_<params name>/ with the CSV files,
a copy of the parameter file, meta.json (git hash, command, seed) and summary.txt, and
appends one line to docs/run_log.md. Nothing is overwritten.

Conventions used in all sweeps:
- heading = hull heading averaged over one field period (a "beat"), relative to phi;
- lock = that heading stays within LOCK_TOL over LOCK_WINDOW consecutive beats;
- the press phase is given by the centre of the hold, as a field phase (omega t_c);
  the press itself comes half a hold earlier;
- "nominal" phase: the fundamental of the stroke in phase with the field, for which the
  theory puts the boat on the tack at -90 deg from the field axis.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from regatta_model import analysis as an
from regatta_model import dynamics as dyn
from regatta_model import theory as th
from regatta_model.params import Params, load_params

ROOT = Path(__file__).resolve().parents[1]
DEG = np.pi / 180.0
LOCK_WINDOW = 5  # beats
LOCK_TOL = 10 * DEG
TACK_TOL = 15 * DEG  # "on the predicted heading"
ON_TACK_TOL = 30 * DEG  # jitter sweep: still on the same tack
CHAOS_MIN = 0.05  # 1/s; Lyapunov exponents above this count as chaotic


class Out:
    """Output directory of one call: CSV files and a text summary."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory
        self.lines: list[str] = []

    def csv(self, name: str, header: list[str], rows: list[list]) -> None:
        with open(self.dir / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            for row in rows:
                w.writerow([f"{x:.6g}" if isinstance(x, float) else x for x in row])
        self.say(f"[{name}: {len(rows)} rows]")

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.lines.append(text)

    def close(self) -> None:
        (self.dir / "summary.txt").write_text("\n".join(self.lines) + "\n")


def press_time(p: Params, duty, centre_phase):
    """Press time (in the first beat) of a hold of duty cycle `duty` centred on a phase."""
    return np.mod(centre_phase / p.omega - 0.5 * duty * p.period, p.period)


def circ_mean(x: np.ndarray) -> float:
    return float(np.angle(np.mean(np.exp(1j * x)))) if x.size else float("nan")


def tack_target(p: Params, duty, sign: int = -1):
    """Derived mean hull heading on a tack: phi + sign 90 deg - i_m alpha_mean."""
    return p.phi + sign * 0.5 * np.pi - p.i_m * th.alpha_mean(p, duty)


def jitter_run(
    p: Params, duty, sigma, n_pre: int, n_beats: int, rng: np.random.Generator, n: int
) -> np.ndarray:
    """Nominal presses with Gaussian jitter (s) on press and release times.

    The boat starts on the tack and gets n_pre beats without jitter. Returns the
    beat-averaged hull headings of the n_beats jittered beats, shape (n_beats, n).
    """
    period = p.period
    t0 = press_time(p, duty, th.nominal_centre_phase(p))
    base = np.arange(n_pre + n_beats)[:, None] * period + t0
    noise = rng.standard_normal((2, n_pre + n_beats, n)) * sigma
    noise[:, :n_pre] = 0.0
    t_on = base + noise[0]
    t_off = base + duty * period + noise[1]
    s0 = dyn.rest_state(p, tack_target(p, duty) + np.zeros(n))
    _, _, hull = dyn.run_beats(p, s0, n_pre + n_beats, dyn.timeline_button(t_on, t_off, period))
    return hull[n_pre:]


def tack_run(
    p: Params, duty, at_release: bool, h0: np.ndarray, n_pre: int, n_post: int
) -> tuple[np.ndarray, np.ndarray]:
    """Half-beat shift of the press pattern after n_pre beats on the nominal phase.

    The new pattern replaces the old one from a press instant (the press comes half a
    beat late) or from a release instant (`at_release`). Returns (started, beats):
    started marks the boats that were on the first tack before the shift; beats is the
    number of beats after the shift until the heading is within TACK_TOL of the opposite
    tack and stays there (nan if it does not within n_post beats).
    """
    period = p.period
    t_a = press_time(p, duty, th.nominal_centre_phase(p))
    t_sw = n_pre * period + t_a + (duty * period if at_release else 0.0)
    a = dyn.periodic_button(t_a, duty, period)
    b = dyn.periodic_button(t_a + 0.5 * period, duty, period)

    def button(t: float) -> np.ndarray:
        return np.where(t < t_sw, a(t), b(t))

    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0), n_pre + n_post, button)
    err_a = np.abs(th.wrap(hull[n_pre - 5 : n_pre] - tack_target(p, duty, -1)))
    started = np.all(err_a < TACK_TOL, axis=0)
    err_b = np.abs(th.wrap(hull[n_pre:] - tack_target(p, duty, +1)))
    off = err_b >= TACK_TOL
    # index of the last beat off target, +1: first beat from which it stays on target
    last_off = np.where(off.any(axis=0), n_post - 1 - np.argmax(off[::-1], axis=0), -1)
    beats = (last_off + 1).astype(float)
    beats[last_off >= n_post - LOCK_WINDOW] = np.nan
    return started, beats


def sweep_regime(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 1. Still-tiller regime map (button released)")
    ratios = np.round(np.arange(0.8, 3.01, 0.1), 2)
    damps = np.round(np.arange(0.2, 2.01, 0.2), 2)
    n_ic = 4
    r, g, h0 = np.meshgrid(ratios, damps, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij")
    p = p0.with_(omega0=p0.omega / r.ravel(), gamma_hat=g.ravel())
    s0 = dyn.rest_state(p, h0.ravel())
    lam = an.lyapunov(p, s0, 100, 300).reshape(r.shape)
    _, _, hull = dyn.run_beats(p, s0, 200)
    turn = (np.abs(np.diff(hull[100:], axis=0)).mean(axis=0) / (2 * np.pi)).reshape(r.shape)
    rows = []
    out.say("rows: gamma_hat (1/s); columns: omega/omega0 from 0.8 to 3.0 in steps of 0.1")
    out.say("C chaotic (largest exponent > 0.05 /s for some start), a aligned state stable")
    out.say("(Floquet) and no chaos found, p regular motion with the aligned state unstable")
    grid = [["?"] * len(ratios) for _ in damps]
    for i, ratio in enumerate(ratios):
        for j, damp in enumerate(damps):
            fl = float(an.floquet_aligned(p0.with_(omega0=p0.omega / ratio, gamma_hat=damp)))
            lmax, lmean = float(lam[i, j].max()), float(lam[i, j].mean())
            rows.append([float(ratio), float(damp), lmax, lmean, float(turn[i, j].mean()), fl])
            grid[j][i] = "C" if lmax > CHAOS_MIN else ("a" if fl < 1.0 else "p")
    for j, damp in enumerate(damps):
        out.say(f"  {damp:4.1f}  " + "".join(grid[j]))
    out.csv(
        "regime_map.csv",
        ["omega_over_omega0", "gamma_hat", "lyap_max", "lyap_mean", "turns_per_beat", "floquet"],
        rows,
    )
    out.say(f"rigid undamped Mathieu threshold: omega/omega0 = {th.mathieu_threshold():.3f}")


def sweep_lock(p: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 2. Lock window (ideal periodic presses)")
    duties = np.round(np.arange(0.1, 0.901, 0.05), 2)
    phases = np.arange(0, 360, 15) * DEG
    n_ic, n_beats = 8, 80
    d, ph, h0 = np.meshgrid(duties, phases, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij")
    button = dyn.periodic_button(press_time(p, d.ravel(), ph.ravel()), d.ravel(), p.period)
    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0.ravel()), n_beats, button)
    locked = (an.window_spread(hull[-LOCK_WINDOW:], LOCK_WINDOW)[0] < LOCK_TOL).reshape(d.shape)
    pair = 0.5 * (hull[-LOCK_WINDOW - 1 : -1] + hull[-LOCK_WINDOW:])
    locked2 = (an.window_spread(pair, LOCK_WINDOW)[0] < LOCK_TOL).reshape(d.shape)
    head = th.wrap(hull[-LOCK_WINDOW:].mean(axis=0) - p.phi).reshape(d.shape)
    rows, err_theory, err_brief = [], [], []
    for i, duty in enumerate(duties):
        for j, phase in enumerate(phases):
            pred = th.wrap(th.hull_headings(p, float(duty), float(phase)) - p.phi)
            row = [float(duty), float(phase / DEG), float(press_time(p, duty, phase) / p.period)]
            row += [float(locked[i, j].mean()), float(locked2[i, j].mean())]
            row += [th.grip(p, float(duty), float(phase))]
            for sign in (-1, 1):
                sel = locked[i, j] & (np.sign(np.sin(head[i, j])) == sign)
                h = circ_mean(head[i, j][sel])
                side = pred[np.sign(np.sin(pred)) == sign]
                ref = h if sel.any() else sign * 0.5 * np.pi
                pr = float(side[np.argmin(np.abs(th.wrap(side - ref)))]) if side.size else np.nan
                brief = float(th.wrap(sign * 0.5 * np.pi - th.alpha_mean(p, duty)))
                row += [int(sel.sum()), h / DEG, pr / DEG, brief / DEG]
                if sel.any():
                    err_theory.append(th.wrap(h - pr) if side.size else np.nan)
                    err_brief.append(th.wrap(h - brief))
            rows.append(row)
    cols = ["duty", "centre_phase_deg", "press_time_beats", "lock_frac", "lock2_frac", "grip"]
    for name in ("minus", "plus"):
        cols += [f"n_{name}", f"heading_{name}_deg", f"theory_{name}_deg", f"brief_{name}_deg"]
    out.csv("lock_window.csv", cols, rows)
    out.say(f"lock fraction over {n_ic} random starts, digit = tenths (9: at least 0.9)")
    out.say("rows: duty cycle; columns: hold-centre phase 0 to 345 deg in steps of 15 deg")
    for i, duty in enumerate(duties):
        out.say(f"  {duty:4.2f}  " + "".join(str(min(9, int(10 * x))) for x in locked[i].mean(-1)))
    j_nom = int(np.argmin(np.abs(th.wrap(phases - th.nominal_centre_phase(p)))))
    out.say(
        f"nominal phase {th.nominal_centre_phase(p) / DEG:.1f} deg; column used: "
        f"{phases[j_nom] / DEG:.0f} deg. Heading on the minus tack against duty cycle:"
    )
    out.say("  duty  lock  lock2  grip  heading  theory   brief   (deg from the field axis)")
    for i, duty in enumerate(duties):
        r = rows[i * len(phases) + j_nom]
        out.say(
            f"  {duty:4.2f}  {r[3]:4.2f}  {r[4]:5.2f} {r[5]:5.2f}  {r[7]:7.1f} {r[8]:7.1f} "
            f"{r[9]:7.1f}"
        )
    e_t, e_b = np.array(err_theory), np.array(err_brief)
    if e_t.size:
        out.say(
            f"locked headings ({e_t.size} cells and tacks): rms error of the theory "
            f"{np.sqrt(np.nanmean(e_t**2)) / DEG:.1f} deg, of the brief's formula "
            f"{np.sqrt(np.mean(e_b**2)) / DEG:.1f} deg"
        )

    out.say("-- tempo error (D = 0.5, nominal phase at the start), lock rate per beat")
    errors = np.array([-10, -5, -3, -2, -1, -0.5, 0, 0.5, 1, 2, 3, 5, 10]) / 100.0
    n_ic, n_beats, skip = 16, 200, 20
    e, h0 = np.meshgrid(errors, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij")
    period = p.period * (1.0 + e.ravel())
    t0 = press_time(p, 0.5, th.nominal_centre_phase(p))

    def button(t: float) -> np.ndarray:
        return (np.mod(t - t0, period) < 0.5 * period).astype(float)

    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0.ravel()), n_beats, button)
    rate = an.lock_flags(hull[skip:], LOCK_WINDOW, LOCK_TOL).mean(axis=0).reshape(e.shape)
    rows = [[float(100 * x), float(rate[i].mean())] for i, x in enumerate(errors)]
    out.csv("lock_tempo.csv", ["tempo_error_pct", "lock_rate"], rows)
    out.say("  " + "  ".join(f"{r[0]:+.1f}%: {r[1]:.2f}" for r in rows))


def sweep_jitter(p: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 3. Timing jitter on press and release (nominal phase, start on the tack)")
    sigmas = np.arange(0, 151, 10) / 1000.0
    n_seed, n_pre, n_beats = 32, 30, 200
    rows = []
    for duty in (0.5, 0.35):
        sg = np.repeat(sigmas, n_seed)
        hull = jitter_run(p, duty, sg, n_pre, n_beats, rng, sg.size)
        lock = an.lock_flags(hull, LOCK_WINDOW, LOCK_TOL).mean(axis=0).reshape(-1, n_seed)
        on = (np.abs(th.wrap(hull - tack_target(p, duty))) < ON_TACK_TOL).mean(axis=0)
        on = on.reshape(-1, n_seed)
        for i, sigma in enumerate(sigmas):
            rows.append([duty, float(1000 * sigma), float(lock[i].mean()), float(on[i].mean())])
        out.say(f"  D = {duty}: sigma (ms) -> lock rate / on-tack rate")
        out.say(
            "  "
            + "  ".join(
                f"{1000 * s:.0f}: {a.mean():.2f}/{b.mean():.2f}"
                for s, a, b in zip(sigmas, lock, on, strict=True)
            )
        )
    out.csv("jitter.csv", ["duty", "sigma_ms", "lock_rate", "on_tack_rate"], rows)


def sweep_tack(p: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 4. Tack: half-beat shift from a locked state")
    n_ic, n_pre, n_post = 16, 40, 40
    h0 = rng.uniform(-np.pi, np.pi, n_ic)
    rows = []
    for duty in (0.5, 0.35, 0.65):
        for at_release in (False, True):
            started, beats = tack_run(p, duty, at_release, h0, n_pre, n_post)
            done = beats[started]
            ok = np.isfinite(done)
            mode = "from_release" if at_release else "from_press"
            med = float(np.median(done[ok])) if ok.any() else float("nan")
            mx = float(done[ok].max()) if ok.any() else float("nan")
            frac = float(ok.mean()) if done.size else float("nan")
            rows.append([duty, mode, int(started.sum()), frac, med, mx])
            out.say(
                f"  D = {duty:4.2f} {mode:12s}: {int(started.sum()):2d}/{n_ic} on the first "
                f"tack; relocked {frac:.2f}; beats median {med:.0f}, max {mx:.0f}"
            )
    out.csv(
        "tack.csv", ["duty", "mode", "n_started", "relock_frac", "beats_median", "beats_max"], rows
    )


def sweep_reaction(p: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 5. Reaction check: field off, periodic presses, 100 beats")
    duties = np.array([0.2, 0.35, 0.5, 0.65, 0.8])
    q = p.with_(omega0=0.0)
    button = dyn.periodic_button(0.1 * q.period, duties, q.period)
    _, _, hull = dyn.run_beats(q, dyn.rest_state(q, np.zeros(duties.size)), 100, button)
    rows = [
        [float(d), float(hull[-1, i] / DEG), float(np.abs(hull[:, i]).max() / DEG)]
        for i, d in enumerate(duties)
    ]
    out.csv("reaction.csv", ["duty", "net_rotation_deg", "max_excursion_deg"], rows)
    out.say("  " + "  ".join(f"D={r[0]}: net {r[1]:+.4f} deg (max {r[2]:.1f})" for r in rows))


def sweep_design(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 6. Design scan: field strength and stroke (other parameters as given)")
    ratios = np.round(np.arange(1.0, 2.01, 0.1), 2)
    alphas = np.arange(35, 76, 5)
    n_ic = 16
    r, a, h0 = np.meshgrid(ratios, alphas * DEG, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij")
    p = p0.with_(omega0=p0.omega / r.ravel(), alpha0=a.ravel())
    shape = r.shape
    psi = th.nominal_centre_phase(p0)
    res: dict[str, np.ndarray] = {}
    for duty in (0.5, 0.3):
        button = dyn.periodic_button(press_time(p0, duty, psi), duty, p0.period)
        _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0.ravel()), 80, button)
        ok = an.window_spread(hull[-LOCK_WINDOW:], LOCK_WINDOW)[0] < LOCK_TOL
        ok &= np.abs(th.wrap(hull[-LOCK_WINDOW:].mean(0) - tack_target(p, duty))) < TACK_TOL
        res[f"lock_d{duty}"] = ok.reshape(shape).mean(-1)
    for sigma in (0.04, 0.08):
        hull = jitter_run(p, 0.5, sigma, 30, 150, rng, r.size)
        on = (np.abs(th.wrap(hull - tack_target(p, 0.5))) < ON_TACK_TOL).mean(axis=0)
        res[f"on_tack_{int(1000 * sigma)}ms"] = on.reshape(shape).mean(-1)
    started, beats = tack_run(p, 0.5, False, h0.ravel(), 40, 40)
    beats = np.where(started, beats, np.nan).reshape(shape)
    with np.errstate(all="ignore"):
        res["tack_ok"] = np.isfinite(beats).sum(-1) / np.maximum(started.reshape(shape).sum(-1), 1)
        res["tack_beats"] = np.where(
            np.isfinite(beats).any(-1),
            np.nanmedian(np.where(np.isfinite(beats), beats, np.nan), -1),
            np.nan,
        )
    # Still tiller: depends on the field strength only.
    pr = p0.with_(omega0=p0.omega / np.repeat(ratios, 4))
    lam = an.lyapunov(pr, dyn.rest_state(pr, rng.uniform(-np.pi, np.pi, pr.omega0.size)), 100, 300)
    lam = lam.reshape(-1, 4).max(axis=1)
    keys = list(res)
    rows = []
    for i, ratio in enumerate(ratios):
        fl = float(an.floquet_aligned(p0.with_(omega0=p0.omega / ratio)))
        for j, alpha in enumerate(alphas):
            g = th.grip(p0.with_(omega0=p0.omega / ratio, alpha0=alpha * DEG), 0.5, psi)
            rows.append(
                [float(ratio), float(alpha), float(lam[i]), fl, g]
                + [float(res[k][i, j]) for k in keys]
            )
    out.csv(
        "design_scan.csv",
        ["omega_over_omega0", "alpha0_deg", "still_lyap_max", "still_floquet", "grip"] + keys,
        rows,
    )
    out.say(
        "rows: omega/omega0 [still-tiller Lyapunov max, 1/s]; columns: alpha0 = "
        + ", ".join(str(x) for x in alphas)
        + " deg"
    )
    for k, label in (
        ("lock_d0.5", "lock on the tack from random starts, D = 0.5"),
        ("lock_d0.3", "same, D = 0.3"),
        ("on_tack_40ms", "on-tack rate with 40 ms jitter"),
        ("on_tack_80ms", "on-tack rate with 80 ms jitter"),
        ("tack_beats", "beats to tack (median; nan: none)"),
    ):
        out.say(f"-- {label}")
        for i, ratio in enumerate(ratios):
            out.say(f"  {ratio:3.1f} [{lam[i]:+5.2f}]  " + " ".join(f"{x:5.2f}" for x in res[k][i]))


def sweep_chaos(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 7. Still tiller: chaos against dissipation")
    ratios = np.round(np.arange(0.4, 1.51, 0.1), 2)
    gammas = np.array([0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4, 0.7])
    zetas = np.array([0.0, 0.05, 0.5])
    tillers = np.array([p0.omega_s / p0.omega, 20.0])
    n_ic, n_trans = 12, 300
    w, z, g, r, h0 = np.meshgrid(
        tillers, zetas, gammas, ratios, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij"
    )
    p = p0.with_(
        omega_s=p0.omega * w.ravel(),
        zeta=z.ravel(),
        gamma_hat=g.ravel(),
        omega0=p0.omega / r.ravel(),
    )
    s0 = dyn.rest_state(p, h0.ravel())
    lam = an.lyapunov(p, s0, 150, 450).reshape(w.shape)
    _, _, hull = dyn.run_beats(p, s0, n_trans)
    trans = an.transient_beats(hull).reshape(w.shape)
    chaotic = lam > CHAOS_MIN
    rows = []
    for a, tiller in enumerate(tillers):
        for b, zeta in enumerate(zetas):
            out.say(
                f"-- tiller omega_s = {tiller:.0f} omega, zeta = {zeta}: chaotic starts in "
                f"tenths (9: at least 0.9). Rows gamma_hat; columns omega/omega0 = "
                f"{ratios[0]} to {ratios[-1]}"
            )
            for c, gamma in enumerate(gammas):
                out.say(
                    f"  {gamma:5.2f}  "
                    + "".join(str(min(9, int(10 * x))) for x in chaotic[a, b, c].mean(-1))
                )
                for d, ratio in enumerate(ratios):
                    cell = lam[a, b, c, d]
                    rows.append(
                        [
                            float(tiller),
                            float(zeta),
                            float(gamma),
                            float(ratio),
                            float(cell.max()),
                            float(np.median(cell)),
                            float(chaotic[a, b, c, d].mean()),
                            float(np.median(trans[a, b, c, d])),
                            float(trans[a, b, c, d].max()),
                        ]
                    )
    out.csv(
        "chaos_dissipation.csv",
        [
            "omega_s_over_omega",
            "zeta",
            "gamma_hat",
            "omega_over_omega0",
            "lyap_max",
            "lyap_median",
            "chaotic_frac",
            "transient_beats_median",
            "transient_beats_max",
        ],
        rows,
    )
    out.say(
        f"-- beats before the motion is regular (median / max over starts; {n_trans - 3}: "
        "never), given tiller, zeta = 0.5"
    )
    for c, gamma in enumerate(gammas):
        out.say(
            f"  {gamma:5.2f}  "
            + " ".join(
                f"{np.median(trans[0, 2, c, d]):3.0f}/{trans[0, 2, c, d].max():3.0f}"
                for d in range(len(ratios))
            )
        )


def sweep_steer(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 8. Phase steering: settled headings against press phase and duty cycle")
    ratios = np.array([p0.omega / p0.omega0, 1.35, 1.5])
    alphas = np.array([15, 25, 35, 45, 55, 65])
    duties = np.round(np.arange(0.2, 0.81, 0.1), 1)
    phases = np.arange(0, 360, 10) * DEG
    n_ic, n_beats = 8, 160
    r, a, d, ph, h0 = np.meshgrid(
        ratios, alphas * DEG, duties, phases, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij"
    )
    p = p0.with_(omega0=p0.omega / r.ravel(), alpha0=a.ravel())
    button = dyn.periodic_button(press_time(p0, d.ravel(), ph.ravel()), d.ravel(), p0.period)
    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0.ravel()), n_beats, button)
    locked = (an.window_spread(hull[-LOCK_WINDOW:], LOCK_WINDOW)[0] < LOCK_TOL).reshape(r.shape)
    head = th.wrap(hull[-LOCK_WINDOW:].mean(axis=0) - p0.phi).reshape(r.shape)
    rows = []
    bins = np.zeros((len(ratios), len(alphas), len(duties), 36), dtype=bool)
    for i, ratio in enumerate(ratios):
        for j, alpha in enumerate(alphas):
            q = p0.with_(omega0=p0.omega / ratio, alpha0=alpha * DEG)
            for k, duty in enumerate(duties):
                for m, phase in enumerate(phases):
                    sel = locked[i, j, k, m]
                    grip = th.grip(q, float(duty), float(phase))
                    for centre, count in an.cluster_angles(head[i, j, k, m][sel], 8 * DEG):
                        c = float(th.wrap(centre))
                        if count >= n_ic // 2:
                            bins[i, j, k, int(np.floor(np.mod(c, 2 * np.pi) / (10 * DEG))) % 36] = (
                                True
                            )
                        pred = th.wrap(th.hull_headings(q, float(duty), float(phase)) - q.phi)
                        err = float(np.min(np.abs(th.wrap(pred - c)))) if pred.size else np.nan
                        rows.append(
                            [
                                float(ratio),
                                float(alpha),
                                float(duty),
                                float(phase / DEG),
                                grip,
                                c / DEG,
                                count / n_ic,
                                err / DEG,
                            ]
                        )
                    if not sel.any():
                        rows.append(
                            [
                                float(ratio),
                                float(alpha),
                                float(duty),
                                float(phase / DEG),
                                grip,
                                np.nan,
                                0.0,
                                np.nan,
                            ]
                        )
    out.csv(
        "steer_static.csv",
        [
            "omega_over_omega0",
            "alpha0_deg",
            "duty",
            "centre_phase_deg",
            "grip",
            "heading_deg",
            "share_of_starts",
            "theory_error_deg",
        ],
        rows,
    )
    out.say("heading coverage: number of 10 deg heading bins (of 36) held by at least half of the")
    out.say("starts at some phase; first with D = 0.5 only, then with any D from 0.2 to 0.8;")
    out.say(
        "then the mean lock fraction. Rows omega/omega0; columns alpha0 = "
        + ", ".join(str(x) for x in alphas)
        + " deg"
    )
    k5 = int(np.argmin(np.abs(duties - 0.5)))
    any_d = bins.any(axis=2)
    for i, ratio in enumerate(ratios):
        out.say(
            f"  {ratio:4.2f}  "
            + "  ".join(
                f"{bins[i, j, k5].sum():2d}/{any_d[i, j].sum():2d}/{locked[i, j].mean():.2f}"
                for j in range(len(alphas))
            )
        )

    out.say("-- phase ramp: locked at nominal phase, then the press tempo is off by a fixed")
    out.say("amount, so the press phase drifts by 360 deg x offset per beat (D = 0.5)")
    offsets = np.array([0.0025, 0.005, 0.01])
    n_start, n_pre = 4, 30
    r, a, e, _ = np.meshgrid(ratios, alphas * DEG, offsets, np.arange(n_start), indexing="ij")
    p = p0.with_(omega0=p0.omega / r.ravel(), alpha0=a.ravel())
    period = p0.period * (1.0 + e.ravel())
    n_ramp = int(1.25 / offsets.min())
    t0 = press_time(p0, 0.5, th.nominal_centre_phase(p0))
    t_sw = n_pre * p0.period + t0
    nominal = dyn.periodic_button(t0, 0.5, p0.period)

    def ramp(t: float) -> np.ndarray:
        late = (np.mod(t - t_sw, period) < 0.5 * period).astype(float)
        return late if t >= t_sw else nominal(t)

    h_start = tack_target(p, 0.5) + 0.05 * rng.standard_normal(r.size)
    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h_start), n_pre + n_ramp, ramp)
    hull = (hull[n_pre:] - p0.phi).reshape((n_ramp,) + r.shape)
    rows = []
    out.say("per cell: beats followed (heading change below 10 deg per beat) as a fraction of one")
    out.say("full drift of the phase, and 10 deg heading bins visited while following (of 36)")
    for kk, off in enumerate(offsets):
        n_cycle = int(round(1.0 / off))
        out.say(f"  tempo offset {100 * off:.2f} % ({n_cycle} beats per turn of the phase)")
        for i, ratio in enumerate(ratios):
            cells = []
            for j, alpha in enumerate(alphas):
                h = hull[:n_cycle, i, j, kk]
                smooth = np.abs(np.diff(h, axis=0)) < 10 * DEG
                follow = float(smooth.mean())
                visited = np.zeros((36, n_start), dtype=bool)
                idx = (np.floor(np.mod(h[1:], 2 * np.pi) / (10 * DEG)).astype(int)) % 36
                for s_i in range(n_start):
                    visited[idx[smooth[:, s_i], s_i], s_i] = True
                cover = float(visited.sum(axis=0).mean())
                net = float(np.mean(h[-1] - h[0]) / (2 * np.pi))
                rows.append([float(ratio), float(alpha), float(100 * off), follow, cover, net])
                cells.append(f"{follow:.2f}/{cover:4.1f}")
            out.say(f"    {ratio:4.2f}  " + "  ".join(cells))
    out.csv(
        "steer_ramp.csv",
        [
            "omega_over_omega0",
            "alpha0_deg",
            "tempo_offset_pct",
            "followed_frac",
            "heading_bins_visited",
            "net_turns",
        ],
        rows,
    )


def sweep_magnet(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 9. Heavier magnet: recoil steering by the duty cycle (nominal phase)")
    inertia = np.array([0.2, 0.5, 1.0, 2.0])
    alphas = np.array([p0.alpha0 / DEG, 80.0])
    duties = np.round(np.arange(0.2, 0.801, 0.05), 2)
    n_ic = 8
    ii, a, d, h0 = np.meshgrid(
        inertia, alphas * DEG, duties, rng.uniform(-np.pi, np.pi, n_ic), indexing="ij"
    )
    p = p0.with_(inertia_ratio=ii.ravel(), alpha0=a.ravel())
    psi = th.nominal_centre_phase(p0)
    button = dyn.periodic_button(press_time(p0, d.ravel(), psi), d.ravel(), p0.period)
    _, _, hull = dyn.run_beats(p, dyn.rest_state(p, h0.ravel()), 80, button)
    locked = (an.window_spread(hull[-LOCK_WINDOW:], LOCK_WINDOW)[0] < LOCK_TOL).reshape(ii.shape)
    head = th.wrap(hull[-LOCK_WINDOW:].mean(axis=0) - p0.phi).reshape(ii.shape)
    # Jitter and tack at D = 0.5, one value per (inertia ratio, stroke).
    i2, a2, s2 = np.meshgrid(inertia, alphas * DEG, np.arange(n_ic), indexing="ij")
    p2 = p0.with_(inertia_ratio=i2.ravel(), alpha0=a2.ravel())
    hj = jitter_run(p2, 0.5, 0.04, 30, 150, rng, i2.size)
    lock40 = an.lock_flags(hj, LOCK_WINDOW, LOCK_TOL).mean(axis=0).reshape(i2.shape).mean(-1)
    on40 = (np.abs(th.wrap(hj - tack_target(p2, 0.5))) < ON_TACK_TOL).mean(axis=0)
    on40 = on40.reshape(i2.shape).mean(-1)
    started, beats = tack_run(p2, 0.5, False, rng.uniform(-np.pi, np.pi, i2.size), 40, 40)
    beats = np.where(started, beats, np.nan).reshape(i2.shape)
    rows = []
    for i, ratio in enumerate(inertia):
        for j, alpha in enumerate(alphas):
            q = p0.with_(inertia_ratio=ratio, alpha0=alpha * DEG)
            good = []
            for k, duty in enumerate(duties):
                sel = locked[i, j, k] & (np.sin(head[i, j, k]) < 0)
                groups = an.cluster_angles(head[i, j, k][sel], 8 * DEG)
                h = float(th.wrap(groups[0][0])) if groups else np.nan
                share = groups[0][1] / n_ic if groups else 0.0
                recoil = float(-0.5 * np.pi - q.i_m * th.alpha_mean(q, duty))
                rows.append(
                    [
                        float(ratio),
                        float(alpha),
                        float(duty),
                        float(locked[i, j, k].mean()),
                        share,
                        h / DEG,
                        recoil / DEG,
                        th.grip(q, float(duty), psi),
                    ]
                )
                if share >= 0.75:
                    good.append((duty, h / DEG))
            with np.errstate(all="ignore"):
                tb = np.nanmedian(beats[i, j]) if np.isfinite(beats[i, j]).any() else np.nan
            rng_txt = "no duty cycle locks from 3 starts in 4"
            if good:
                hs = [g[1] for g in good]
                rng_txt = (
                    f"D {good[0][0]:.2f} to {good[-1][0]:.2f}: heading {hs[0]:+.0f} to "
                    f"{hs[-1]:+.0f} deg, range {max(hs) - min(hs):.0f} deg"
                )
            out.say(
                f"  I_m/I_h = {ratio:3.1f}, alpha0 = {alpha:.0f}: grip {th.grip(q, 0.5, psi):.2f}; "
                f"{rng_txt}; 40 ms jitter lock {lock40[i, j]:.2f}, on tack {on40[i, j]:.2f}; "
                f"tack {tb:.0f} beats"
            )
    out.csv(
        "magnet.csv",
        [
            "inertia_ratio",
            "alpha0_deg",
            "duty",
            "lock_frac",
            "share_on_minus_tack",
            "heading_deg",
            "recoil_formula_deg",
            "grip",
        ],
        rows,
    )


def sweep_response(p0: Params, out: Out, rng: np.random.Generator) -> None:
    out.say("== 10. Phase as a tiller: step response, jitter scatter and phase ramp (D = 0.5)")
    ratios = np.array([1.5, 2.0, 2.5, 3.0])
    alphas = np.array([35.0, 50.0, 65.0])
    period, psi = p0.period, th.nominal_centre_phase(p0)
    t0 = press_time(p0, 0.5, psi)
    n_pre = 40

    def members(*extra: np.ndarray) -> tuple[Params, list[np.ndarray], tuple[int, ...]]:
        grids = np.meshgrid(ratios, alphas * DEG, *extra, indexing="ij")
        q = p0.with_(omega0=p0.omega / grids[0].ravel(), alpha0=grids[1].ravel())
        return q, [g.ravel() for g in grids[2:]], grids[0].shape

    def start(q: Params, n: int) -> np.ndarray:
        return dyn.rest_state(q, tack_target(q, 0.5) + np.zeros(n))

    nominal = dyn.periodic_button(t0, 0.5, period)
    t_sw = n_pre * period + t0

    # Step of the press phase.
    steps = np.array([30.0, 90.0, 180.0])
    q, (dpsi,), shape = members(steps * DEG)
    shifted = dyn.periodic_button(t0 + dpsi / p0.omega, 0.5, period)
    n_post = 80
    _, _, hull = dyn.run_beats(
        q, start(q, dpsi.size), n_pre + n_post, lambda t: nominal(t) if t < t_sw else shifted(t)
    )
    before = hull[n_pre - 5 : n_pre].mean(axis=0)
    final = hull[-5:].mean(axis=0)
    off = np.abs(hull[n_pre:] - final) > 5 * DEG
    settle = np.where(off.any(axis=0), n_post - np.argmax(off[::-1], axis=0), 0).reshape(shape)
    turned = ((final - before) / DEG).reshape(shape)
    steady = (an.window_spread(hull[-LOCK_WINDOW:], LOCK_WINDOW)[0] < LOCK_TOL).reshape(shape)

    # Jitter on a locked boat.
    sigmas = np.array([0.02, 0.04, 0.08, 0.12])
    n_seed, n_beats = 8, 200
    q, (sg, _), shape_j = members(sigmas, np.arange(n_seed))
    base = np.arange(n_pre + n_beats)[:, None] * period + t0
    noise = rng.standard_normal((2, n_pre + n_beats, sg.size)) * sg
    noise[:, :n_pre] = 0.0
    button = dyn.timeline_button(base + noise[0], base + 0.5 * period + noise[1], period)
    _, _, hull = dyn.run_beats(q, start(q, sg.size), n_pre + n_beats, button)
    dev = (hull[n_pre:] - hull[n_pre - 5 : n_pre].mean(axis=0)).reshape((n_beats,) + shape_j)
    scatter = np.sqrt((dev**2).mean(axis=(0, -1))) / DEG
    worst = np.abs(dev).max(axis=(0, -1)) / DEG

    # Phase ramp: press tempo off by a fixed fraction.
    offsets = np.array([0.005, 0.01, 0.02, 0.04])
    n_ramp = 100
    q, (off_t,), shape_r = members(offsets)
    per = period * (1.0 + off_t)

    def ramp(t: float) -> np.ndarray:
        return (np.mod(t - t_sw, per) < 0.5 * per).astype(float) if t >= t_sw else nominal(t)

    _, _, hull = dyn.run_beats(q, start(q, off_t.size), n_pre + n_ramp, ramp)
    # the press comes later each beat, so the phase grows and the heading should fall
    expected = -360.0 * off_t * (n_ramp - 1)
    follow = (((hull[-1] - hull[n_pre]) / DEG) / expected).reshape(shape_r)

    rows = []
    out.say("per cell: beats to settle after a phase step of 30 / 90 / 180 deg (x: not settled);")
    out.say("heading scatter (rms, deg) at 20 / 40 / 80 / 120 ms jitter; turn achieved over turn")
    out.say("asked for a tempo offset of 0.5 / 1 / 2 / 4 % (3.6 deg per beat per %)")
    for i, ratio in enumerate(ratios):
        for j, alpha in enumerate(alphas):
            qq = p0.with_(omega0=p0.omega / ratio, alpha0=alpha * DEG)
            c, s = th.rectified(qq, 0.5, psi)
            slow = float(qq.omega0 * np.sqrt(np.hypot(c, s)))  # slow frequency of the lock, rad/s
            st = [f"{settle[i, j, k]:.0f}" if steady[i, j, k] else "x" for k in range(len(steps))]
            out.say(
                f"  omega/omega0 {ratio:3.1f}, alpha0 {alpha:2.0f}: slow period "
                f"{2 * np.pi / slow / period:4.1f} beats; step {' / '.join(st)}; turned "
                + " / ".join(f"{x:+.0f}" for x in turned[i, j])
                + "; scatter "
                + " / ".join(f"{x:.0f}" for x in scatter[i, j])
                + "; ramp "
                + " / ".join(f"{x:.2f}" for x in follow[i, j])
            )
            rows.append(
                [float(ratio), float(alpha), 2 * np.pi / slow / period]
                + [float(x) for x in settle[i, j]]
                + [float(x) for x in turned[i, j]]
                + [float(x) for x in scatter[i, j]]
                + [float(x) for x in worst[i, j]]
                + [float(x) for x in follow[i, j]]
            )
    cols = ["omega_over_omega0", "alpha0_deg", "slow_period_beats"]
    cols += [f"settle_beats_step{int(x)}" for x in steps] + [
        f"turned_deg_step{int(x)}" for x in steps
    ]
    cols += [f"scatter_deg_{int(1000 * x)}ms" for x in sigmas]
    cols += [f"max_dev_deg_{int(1000 * x)}ms" for x in sigmas]
    cols += [f"ramp_follow_{100 * x:g}pct" for x in offsets]
    out.csv("phase_response.csv", cols, rows)


SWEEPS: dict[str, Callable[[Params, Out, np.random.Generator], None]] = {
    "regime": sweep_regime,
    "lock": sweep_lock,
    "jitter": sweep_jitter,
    "tack": sweep_tack,
    "reaction": sweep_reaction,
    "design": sweep_design,
    "chaos": sweep_chaos,
    "steer": sweep_steer,
    "magnet": sweep_magnet,
    "response": sweep_response,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--params", type=Path, required=True)
    ap.add_argument(
        "--only", default=",".join(list(SWEEPS)[:6]), help="comma-separated: " + ", ".join(SWEEPS)
    )
    ap.add_argument("--seed", type=int, default=20261119)
    ap.add_argument("--why", default="", help="one line for docs/run_log.md")
    args = ap.parse_args()

    p = load_params(args.params)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    directory = ROOT / "runs" / "phase1" / f"{stamp}_{args.params.stem}"
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copy(args.params, directory / "params.toml")
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
        "numpy": np.__version__,
    }
    (directory / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    out = Out(directory)
    out.say(
        f"params: {args.params}  seed: {args.seed}  git: {meta['git'][:8]}"
        f"{' (dirty)' if dirty else ''}"
    )
    kappa = float(th.kapitza_factor(p))
    out.say(
        f"omega/omega0 = {p.omega / p.omega0:.2f}, alpha0 = {p.alpha0 / DEG:.0f} deg, "
        f"kappa = {kappa:.3f}, grip at D = 0.5 and nominal phase = "
        f"{th.grip(p, 0.5, th.nominal_centre_phase(p)):.2f}"
    )
    for name in args.only.split(","):
        t0 = time.time()
        SWEEPS[name](p, out, np.random.default_rng([args.seed, list(SWEEPS).index(name)]))
        out.say(f"({name}: {time.time() - t0:.0f} s)")
        out.say()
    out.close()
    with open(ROOT / "docs" / "run_log.md", "a") as f:
        f.write(
            f"- {stamp} `{meta['git'][:8]}{'+' if dirty else ''}` "
            f"`tools/sweeps.py {' '.join(sys.argv[1:])}` -> "
            f"`{directory.relative_to(ROOT)}` {args.why}\n"
        )


if __name__ == "__main__":
    main()
