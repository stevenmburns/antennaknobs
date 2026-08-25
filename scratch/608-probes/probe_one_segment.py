"""momwire#608 — what a one-segment wire actually does under RazorSolver.

The guard in `RazorSolver.__init__` refuses `sum(npe) < 2` on ANY wire. The
handoff measured case (a) — junctioned at both ends — against bspline and got
~0.2 %. This probe replaces that soft comparison with the EXACT oracle razor
already owns: `tests/test_razor_junctions.py`'s split identity. A wire split
at a knot is the same linear system with one basis re-labelled, so a split
that leaves a ONE-SEGMENT piece must reproduce the unsplit wire to solver
precision — 1e-9 relative, not 0.2 %.

  (a) junctioned at BOTH ends  -> split a 20-seg wire at knots 8 and 9
  (b) junctioned at ONE end    -> split a 20-seg wire at knot 1
  (c) junctioned at NEITHER    -> a free-floating 1-seg wire: carries no
                                  basis at all. Compared against bspline,
                                  which gives it one.

Run from the antennaknobs root with the venv active.
"""

import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAZOR = ROOT / "momwire" / "src" / "momwire" / "razor.py"
PROBE = ROOT / "momwire" / "src" / "momwire" / "_razor_nogate_probe.py"

GUARD = "            if sum(npe) < 2:\n                raise ValueError("
NO_UNKNOWNS = '        if n_interior == 0:\n            raise ValueError("no unknowns'


def install_neutered(also_n_interior=False):
    """Write a copy of razor.py with the one-segment guard(s) disabled.

    The guard is inline in `__init__` and cannot be monkeypatched. The copy
    must live INSIDE the package or its relative imports fail.
    """
    src = RAZOR.read_text()
    assert GUARD in src, "the per-wire guard moved"
    patched = src.replace(GUARD, "            if False:\n                raise ValueError(", 1)
    if also_n_interior:
        assert NO_UNKNOWNS in src, "the n_interior guard moved"
        patched = patched.replace(
            NO_UNKNOWNS,
            '        if False:\n            raise ValueError("no unknowns',
            1,
        )
    PROBE.write_text(patched)
    for mod in [m for m in sys.modules if "_razor_nogate_probe" in m]:
        del sys.modules[mod]
    import momwire._razor_nogate_probe as m

    return m.RazorSolver


# ---- ByDipole1 in free space, the house wire ------------------------------
LEN = 10.18946
RAD = 0.0010262
WL = 299792458.0 / 14.0e6
KW = dict(wire_radius=RAD, wavelength=WL)
N = 20
D = LEN / N


def pt(arc):
    return np.array([0.0, arc, 0.0])


def rel(a, b):
    return abs(a - b) / abs(b)


def report(name, z, z_ref, note=""):
    print(f"  {name:<34s} {z.real:11.6f}{z.imag:+11.6f}j   rel {rel(z, z_ref):.3e} {note}")


def main():
    Razor = install_neutered()

    # ---------------- the reference: one unsplit 20-segment wire ----------
    ref = Razor(wires=[np.array([pt(0.0), pt(LEN)])], nsegs=N, **KW)
    z_ref, c_ref = ref.compute_impedance()
    print(f"\nreference: unsplit {N}-seg wire, {c_ref.shape[0]} bases")
    print(f"  {'':<34s} {z_ref.real:11.6f}{z_ref.imag:+11.6f}j")

    # ---------------- (b) junctioned at ONE end ---------------------------
    # Split at the FIRST knot: piece 0 is one segment, free at the tip and
    # junctioned at its other end. Its lone basis is the junction tent.
    print("\n(b) one-segment wire junctioned at ONE end  [split at knot 1]")
    b = Razor(
        wires=[np.array([pt(0.0), pt(D)]), np.array([pt(D), pt(LEN)])],
        n_per_edge_per_wire=[[1], [N - 1]],
        feeds=[(1, LEN / 2 - D, 1.0 + 0j)],
        **KW,
    )
    z_b, c_b = b.compute_impedance()
    report("split, 1-seg tip piece", z_b, z_ref, f"({c_b.shape[0]} bases)")

    # ---------------- (a) junctioned at BOTH ends -------------------------
    # Split at knots 8 and 9: the middle piece is one segment, junctioned at
    # both ends. Its two bases are the two junction tents, which is exactly
    # what an ordinary interior segment carries.
    print("\n(a) one-segment wire junctioned at BOTH ends  [split at knots 8, 9]")
    a = Razor(
        wires=[
            np.array([pt(0.0), pt(8 * D)]),
            np.array([pt(8 * D), pt(9 * D)]),
            np.array([pt(9 * D), pt(LEN)]),
        ],
        n_per_edge_per_wire=[[8], [1], [N - 9]],
        feeds=[(2, LEN / 2 - 9 * D, 1.0 + 0j)],
        **KW,
    )
    z_a, c_a = a.compute_impedance()
    report("split, 1-seg middle piece", z_a, z_ref, f"({c_a.shape[0]} bases)")

    # The reversed spelling of the middle piece — the sign test, since the
    # one-segment piece's arc direction is the only thing that can flip.
    a_rev = Razor(
        wires=[
            np.array([pt(0.0), pt(8 * D)]),
            np.array([pt(9 * D), pt(8 * D)]),  # reversed
            np.array([pt(9 * D), pt(LEN)]),
        ],
        n_per_edge_per_wire=[[8], [1], [N - 9]],
        feeds=[(2, LEN / 2 - 9 * D, 1.0 + 0j)],
        **KW,
    )
    z_a_rev, _ = a_rev.compute_impedance()
    report("same, middle spelled backwards", z_a_rev, z_ref)

    # Feed ON the one-segment piece's junction knot.
    a_fed = Razor(
        wires=[
            np.array([pt(0.0), pt(10 * D)]),
            np.array([pt(10 * D), pt(11 * D)]),
            np.array([pt(11 * D), pt(LEN)]),
        ],
        n_per_edge_per_wire=[[10], [1], [N - 11]],
        feeds=[(1, 0.0, 1.0 + 0j)],  # the junction at arc 10*D = the midpoint
        **KW,
    )
    z_a_fed, _ = a_fed.compute_impedance()
    report("fed AT the 1-seg piece's junction", z_a_fed, z_ref)

    # ---------------- (c) junctioned at NEITHER end -----------------------
    print("\n(c) one-segment wire junctioned at NEITHER end  [a free floater]")
    floater = np.array([[0.5, LEN / 2 - D / 2, 0.0], [0.5, LEN / 2 + D / 2, 0.0]])
    c_with = Razor(
        wires=[np.array([pt(0.0), pt(LEN)]), floater],
        n_per_edge_per_wire=[[N], [1]],
        feeds=[(0, LEN / 2, 1.0 + 0j)],
        **KW,
    )
    z_c, coeffs_c = c_with.compute_impedance()
    geom = c_with._build_geometry()
    print(f"  bases: {coeffs_c.shape[0]} (the lone wire alone has {c_ref.shape[0]})")
    print(f"  n_basis_interior={geom['n_basis_interior']}  junctions={len(geom['junctions'])}")
    report("dipole + inert 1-seg floater", z_c, z_ref, "<- vs the floater-free dipole")

    # The same model with the floater given 2 segments, so it carries a real
    # unknown and can actually scatter.
    c_two = Razor(
        wires=[np.array([pt(0.0), pt(LEN)]), floater],
        n_per_edge_per_wire=[[N], [2]],
        feeds=[(0, LEN / 2, 1.0 + 0j)],
        **KW,
    )
    z_c2, coeffs_c2 = c_two.compute_impedance()
    report("dipole + 2-seg floater", z_c2, z_ref, f"({coeffs_c2.shape[0]} bases)")

    # ---------------- what BSplineSolver does with the same floater -------
    from momwire import BSplineSolver

    print("\n  BSplineSolver (degree 2) on the same three models:")
    for label, npe in (("floater absent", None), ("1-seg floater", [[N], [1]]), ("2-seg floater", [[N], [2]])):
        wires = [np.array([pt(0.0), pt(LEN)])]
        if npe is not None:
            wires.append(floater)
        bs = BSplineSolver(
            wires=wires,
            n_per_edge_per_wire=npe if npe else [[N]],
            feeds=[(0, LEN / 2, 1.0 + 0j)],
            **KW,
        )
        z_bs, c_bs = bs.compute_impedance()
        print(f"    {label:<20s} {z_bs.real:11.6f}{z_bs.imag:+11.6f}j   ({c_bs.shape[0]} bases)")

    # ---------------- the all-one-segment corner --------------------------
    # A closed triangle of three one-segment wires: n_interior == 0, but
    # three junction tents. The SECOND guard ("no unknowns") refuses it.
    print("\n(d) corner: a triangle of three 1-seg wires (n_interior == 0)")
    Razor2 = install_neutered(also_n_interior=True)
    s = 1.0
    v = [np.array([0.0, 0.0, 0.0]), np.array([s, 0.0, 0.0]), np.array([s / 2, s * 0.866, 0.0])]
    try:
        tri = Razor2(
            wires=[
                np.array([v[0], v[1]]),
                np.array([v[1], v[2]]),
                np.array([v[2], v[0]]),
            ],
            n_per_edge_per_wire=[[1], [1], [1]],
            feeds=[(0, 0.0, 1.0 + 0j)],
            wire_radius=1e-3,
            wavelength=4.0,
        )
        z_t, c_t = tri.compute_impedance()
        g = tri._build_geometry()
        print(
            f"  solved: {z_t.real:.6f}{z_t.imag:+.6f}j  "
            f"({c_t.shape[0]} bases; interior={g['n_basis_interior']}, "
            f"junction tents={c_t.shape[0] - g['n_basis_interior']})"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  refused: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    try:
        main()
    finally:
        PROBE.unlink(missing_ok=True)
