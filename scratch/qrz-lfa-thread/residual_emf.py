"""Measure the residual loop EMF behind the coupled-loop pathology.

The identity under test: around the closed 80x80 loop of Roy's model, the
line integral of the scattered E field from ANY current distribution has no
electrostatic (1/omega) part — the scalar potential's loop circulation
vanishes in the continuum regardless of the charge. A discretization either
inherits that cancellation structurally (the potential term enters as
differences of shared potential values — pulse's four-point stencil,
NEC-5-class interval testing, Galerkin with in-basis charge) or it doesn't
(NEC-2-class pointwise closed-form field evaluation), and in the second
case the epsilon-level residual acts as a spurious EMF source in series
with the loop.

Measured here, on the same 6-wire geometry the other lanes use:

  1. w^T G alpha_clean — the discrete loop circulation of the SINUSOIDAL
     lane's matrix applied to the CLEAN current shape (the Harrington
     solution mapped into the sin basis by least squares on knot currents).
     Any nonzero value is pure discretization residual. Frequency-fit
     F = j*omega*a + b/(j*omega) over a ladder to show the residual is
     electrostatic-side (the b term).
  2. The same functional in the PULSE lane (rows already integrate E dl,
     so loop weights are 1): its charge term is a four-point endpoint
     difference, so the loop sum telescopes and b should be machine-zero.
  3. The prediction: I_spur = -(w^T G alpha_clean)/(w^T G alpha_u), with
     alpha_u the sin-basis representation of a unit circulating loop
     current. Compare against the observed spurious circulating current of
     the sin lane's own solve, per k across the dense ladder.
  4. The 1/f exhibit: the sin lane's loop/source ratio vs frequency at
     k=4, next to the flat clean-lane ratios already in results-pulse.json.

Writes results-residual-emf.json. Run: .venv/bin/python this file.
"""

import json
from pathlib import Path

import numpy as np
from momwire import HarringtonSolver
from momwire.sinusoidal import SinusoidalSolver

MHZ0 = 0.0005
V = -404675.9j
RADIUS = 0.005
HERE = Path(__file__).parent

W = [
    ((20, -40, 300), (20, -40, 0), 15),
    ((40, -40, 0), (40, 40, 0), 4),
    ((40, 40, 0), (-40, 40, 0), 4),
    ((-40, 40, 0), (-40, -40, 0), 4),
    ((-40, -40, 0), (20, -40, 0), 3),
    ((20, -40, 0), (40, -40, 0), 1),
]
J6 = [
    [(0, "end"), (4, "end"), (5, "start")],
    [(5, "end"), (1, "start")],
    [(1, "end"), (2, "start")],
    [(2, "end"), (3, "start")],
    [(3, "end"), (4, "start")],
]


def wires6(k):
    return (
        [np.array([a, b], float) for a, b, _ in W],
        [[n * k] for _, _, n in W],
    )


def sin_solver(k, mhz):
    ws, npe = wires6(k)
    return SinusoidalSolver(
        wires=ws,
        n_per_edge_per_wire=npe,
        feeds=[(0, 280.0 - 10.0 / k, 0j)],
        junctions=J6,
        wire_radius=RADIUS,
        wavelength=299.8 / mhz,
    )


def harrington_solver(k, mhz):
    ws, npe = wires6(k)
    return HarringtonSolver(
        wires=ws,
        n_per_edge_per_wire=npe,
        feeds=[(0, 280.0 - 10.0 / k, V)],
        wire_radius=RADIUS,
        wavelength=299.8 / mhz,
    )


def flatten_knots(per_wire):
    return np.concatenate([np.asarray(c) for c in per_wire])


def knot_map(s, n):
    """K[:, j] = knot currents of unit coefficient j (the basis-to-knot
    linear map, built column by column; geometry is cached so this is
    cheap at these sizes)."""
    cols = []
    for j in range(n):
        e = np.zeros(n, dtype=np.complex128)
        e[j] = 1.0
        cols.append(flatten_knots(s.currents_at_knots(e)))
    return np.column_stack(cols)


def loop_rows(geom):
    firsts, lasts = geom["wire_first"], geom["wire_last"]
    rows = []
    for w in range(1, 6):
        rows.extend(range(firsts[w], lasts[w] + 1))
    return np.array(rows, dtype=np.int64)


def sin_G(s):
    geom = s._build_geometry()
    G, _ = s._assemble_Z(geom, s.k)
    return G, geom


def freq_fit(mhz_ladder, values):
    """Fit F = j*omega*a + b/(j*omega); return (a, b, relative residual)."""
    om = 2e6 * np.pi * np.asarray(mhz_ladder)
    A = np.column_stack([1j * om, 1.0 / (1j * om)])
    v = np.asarray(values)
    (a, b), *_ = np.linalg.lstsq(A, v, rcond=None)
    resid = float(np.linalg.norm(A @ np.array([a, b]) - v) / np.linalg.norm(v))
    return a, b, resid


def main():
    out = {}

    # ---- per-k prediction vs observation, sinusoidal lane at 500 Hz ----
    pred_table = {}
    for k in (1, 2, 4, 8, 16):
        h = harrington_solver(k, MHZ0)
        _, c_h = h.compute_impedance()
        h._build_geometry()
        t_clean = flatten_knots(h.currents_at_knots(c_h))

        s = sin_solver(k, MHZ0)
        G, geom = sin_G(s)
        n = geom["n_segs"]
        K = knot_map(s, n)

        alpha_clean, *_ = np.linalg.lstsq(K, t_clean, rcond=None)
        fit_err_clean = float(np.max(np.abs(K @ alpha_clean - t_clean)))

        nk = t_clean.size
        t_u = np.zeros(nk, dtype=np.complex128)
        # knots of wires 1..5 = 1 (unit circulation), vertical = 0
        pos = 0
        for w, (a, b, nseg) in enumerate(W):
            m = nseg * k + 1
            if w >= 1:
                t_u[pos : pos + m] = 1.0
            pos += m
        alpha_u, *_ = np.linalg.lstsq(K, t_u, rcond=None)
        fit_err_u = float(np.max(np.abs(K @ alpha_u - t_u)))

        rows = loop_rows(geom)
        w_vec = np.zeros(n)
        w_vec[rows] = geom["seg_h"][rows]

        E_clean = complex(w_vec @ (G @ alpha_clean))
        Z_loop = complex(w_vec @ (G @ alpha_u))
        I_pred = -E_clean / Z_loop

        # observed circulating current of the sin lane's own solve
        sol = s.compute_port_solution()
        alpha_solved = sol.coeffs @ np.array([V])
        t_sin = flatten_knots(s.currents_at_knots(alpha_solved))
        loop_mask = np.abs(t_u) > 0.5
        I_obs = complex(np.mean(t_sin[loop_mask]) - np.mean(t_clean[loop_mask]))
        pred_table[str(k)] = {
            "E_clean_V": [E_clean.real, E_clean.imag],
            "Z_loop": [Z_loop.real, Z_loop.imag],
            "I_pred": [I_pred.real, I_pred.imag],
            "I_obs_circ": [I_obs.real, I_obs.imag],
            "fit_err": [fit_err_clean, fit_err_u],
        }
        print(
            f"sin k={k:2d}  E_res {abs(E_clean):.4e} V  Z_loop {abs(Z_loop):.4e}"
            f"  I_pred {abs(I_pred):10.3f} A  I_obs {abs(I_obs):10.3f} A"
            f"  (fit {fit_err_clean:.1e}/{fit_err_u:.1e})",
            flush=True,
        )
    out["prediction"] = pred_table

    # ---- frequency split of the residual, sin vs pulse, k=1 ----
    # The test current is FIXED across the ladder (mapped once, at 500 Hz):
    # the identity says the loop circulation of ANY fixed current has no
    # 1/omega part, and refitting per frequency lets minimum-norm lstsq
    # jitter masquerade as frequency dependence.
    ladder = [0.00005, 0.000158, 0.0005, 0.00158, 0.005]
    k = 1

    h0 = harrington_solver(k, MHZ0)
    _, c_h0 = h0.compute_impedance()
    t_clean0 = flatten_knots(h0.currents_at_knots(c_h0))

    s0 = sin_solver(k, MHZ0)
    K0 = knot_map(s0, s0._build_geometry()["n_segs"])
    alpha_fixed, *_ = np.linalg.lstsq(K0, t_clean0, rcond=None)

    # loop-knot mask in flatten_knots layout, for the per-ampere reading:
    # fixed COEFFICIENTS are not a fixed CURRENT in this basis (the
    # junction conditions carry 1/sin(k*d) normalizations, so the
    # represented current grows toward low f) — normalize the circulation
    # by the represented mean loop current to remove that.
    mask = []
    for w, (_a, _b, nseg) in enumerate(W):
        mask.extend([w >= 1] * (nseg * k + 1))
    mask = np.array(mask)
    i_loop_clean = complex(np.mean(t_clean0[mask]))

    sin_vals, pulse_vals, sin_per_amp = [], [], []
    for mhz in ladder:
        s = sin_solver(k, mhz)
        G, geom = sin_G(s)
        w_vec = np.zeros(geom["n_segs"])
        rows = loop_rows(geom)
        w_vec[rows] = geom["seg_h"][rows]
        E = complex(w_vec @ (G @ alpha_fixed))
        sin_vals.append(E)
        K = knot_map(s, geom["n_segs"])
        i_repr = complex(np.mean((K @ alpha_fixed)[mask]))
        sin_per_amp.append(E / i_repr)

        p = harrington_solver(k, mhz)  # Harrington lane as the clean contrast
        p.compute_impedance()  # fills p.z
        geom_p = p._build_geometry()
        off = geom_p["seg_offsets"]
        w_p = np.zeros(off[-1])
        for w in range(1, 6):
            w_p[off[w] : off[w + 1]] = 1.0  # rows already carry h_m
        # segment-current representation of the same clean shape
        c_seg = c_h0  # pulse-family coeffs ARE segment currents, same mesh
        pulse_vals.append(complex(w_p @ (p.z @ c_seg)))

    a_s, b_s, r_s = freq_fit(ladder, sin_vals)
    a_p, b_p, r_p = freq_fit(ladder, pulse_vals)
    om0 = 2e6 * np.pi * MHZ0
    out["freq_split"] = {
        "ladder_mhz": ladder,
        "sin": {"a": [a_s.real, a_s.imag], "b": [b_s.real, b_s.imag], "resid": r_s},
        "harrington": {
            "a": [a_p.real, a_p.imag],
            "b": [b_p.real, b_p.imag],
            "resid": r_p,
        },
        "sin_vals": [[v.real, v.imag] for v in sin_vals],
        "harrington_vals": [[v.real, v.imag] for v in pulse_vals],
    }
    print(
        f"\nfreq split at k=1 (loop circulation of one FIXED current @500 Hz):"
        f"\n  sin        |b/omega| = {abs(b_s) / om0:.4e} V"
        f"   |a*omega| = {abs(a_s) * om0:.4e} V   fit resid {r_s:.1e}"
        f"\n  harrington |b/omega| = {abs(b_p) / om0:.4e} V"
        f"   |a*omega| = {abs(a_p) * om0:.4e} V   fit resid {r_p:.1e}",
        flush=True,
    )

    # the headline reading: spurious EMF per ampere of loop current
    om = 2e6 * np.pi * np.asarray(ladder)
    slope = float(np.polyfit(np.log(om), np.log(np.abs(np.asarray(sin_per_amp))), 1)[0])
    per_amp_p = [v / i_loop_clean for v in pulse_vals]
    out["per_amp"] = {
        "ladder_mhz": ladder,
        "sin_V_per_A": [[v.real, v.imag] for v in sin_per_amp],
        "harrington_V_per_A": [[v.real, v.imag] for v in per_amp_p],
        "sin_loglog_slope_vs_f": slope,
    }
    print("\nspurious loop EMF per ampere of loop current (k=1):")
    for mhz, vs, vp in zip(ladder, sin_per_amp, per_amp_p):
        print(
            f"  f={mhz * 1e6:>9.1f} Hz   sin {abs(vs):.4e} V/A   "
            f"harrington {abs(vp):.4e} V/A",
            flush=True,
        )
    print(f"  sin log-log slope vs f: {slope:+.3f}  (electrostatic error = -1)")

    # ---- the 1/f exhibit: sin lane ratio vs frequency, k=4 ----
    fsweep = {}
    for mhz in (0.05, 0.005, 0.0005, 0.00005, 0.000005):
        s = sin_solver(4, mhz)
        sol = s.compute_port_solution()
        alpha = sol.coeffs @ np.array([V])
        i_src = complex(sol.y[0, 0]) * V
        knots = s.currents_at_knots(alpha)
        loop = max(
            float(np.max(np.abs(0.5 * (np.asarray(c)[:-1] + np.asarray(c)[1:]))))
            for c in knots[1:]
        )
        fsweep[str(mhz)] = loop / abs(i_src)
        print(f"sin f={mhz * 1e6:>9.1f} Hz  ratio {loop / abs(i_src):.4f}", flush=True)
    out["sin_fsweep_k4"] = fsweep

    (HERE / "results-residual-emf.json").write_text(json.dumps(out, indent=1))
    print("wrote", HERE / "results-residual-emf.json")


if __name__ == "__main__":
    main()
