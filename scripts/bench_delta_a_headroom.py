"""Per-design Δ/a headroom: the largest ``nominal_nsegs`` a design can
scale to before some wire's segment length falls under FLOOR × its
radius — the reduced-kernel thin-wire floor (issue #484).

Geometry-only: ``build_wires()`` returns per-wire counts without meshing,
so probing any N is O(n_wires) and the doubling-scan + bisection costs
milliseconds per design. Run as a script for the catalog table
(ascending — the designs that cap refinement earliest first); the Δ/a
lint test imports :func:`n_max` to enforce per-design headroom floors.

Interpretation: a LOW headroom is not automatically a bug. Builder
defects (a short wire carrying a long wire's count — the #484 folded/fan
class) crater it and must be fixed; fat-conductor designs (tube whips,
fat yagi elements) cap early for physical reasons — their radius simply
bounds how far the thin-wire mesh may refine, and convergence ladders
should stop there.
"""

from __future__ import annotations

import math

FLOOR = 2.0
CAP = 100_000
DEFAULT_RADIUS = 0.0005


def min_delta_a(builder_cls, n: int) -> float:
    """Min over wires of (segment length / wire radius) at nominal N."""
    b = builder_cls()
    b.nominal_nsegs = n
    try:
        mat = b.build_wire_material()
        default_r = getattr(mat, "radius", DEFAULT_RADIUS) or DEFAULT_RADIUS
    except Exception:
        default_r = DEFAULT_RADIUS
    worst = math.inf
    for w in b.build_wires():
        p0, p1, ns = w[0], w[1], w[2]
        spec = getattr(w, "spec", None)
        r = getattr(spec, "radius", None) or default_r
        length = math.dist(p0, p1)
        if ns > 0 and length > 0:
            worst = min(worst, (length / ns) / r)
    return worst


def n_max(builder_cls, floor: float = FLOOR, cap: int = CAP) -> int:
    """Largest nominal N with ``min_delta_a >= floor`` (0 if even N=7
    violates; ``cap`` if the design never hits the floor below it)."""
    if min_delta_a(builder_cls, 7) < floor:
        return 0
    lo, hi = 7, 14
    while hi < cap and min_delta_a(builder_cls, hi) >= floor:
        lo, hi = hi, hi * 2
    if hi >= cap and min_delta_a(builder_cls, cap) >= floor:
        return cap
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if min_delta_a(builder_cls, mid) >= floor:
            lo = mid
        else:
            hi = mid
    return lo


def main() -> None:
    import importlib

    from antennaknobs.cli import list_builtin_designs

    rows = []
    for name in sorted(list_builtin_designs()):
        mod = importlib.import_module(f"antennaknobs.designs.{name}")
        rows.append((n_max(mod.Builder), name))
    rows.sort()
    print(f"Δ/a headroom (floor {FLOOR}, cap {CAP}) — ascending:")
    for nm, name in rows:
        nm_s = f">{CAP}" if nm >= CAP else str(nm)
        tag = "   <-- below census top rung (641)" if nm < 641 else ""
        print(f"  {nm_s:>7s}  {name}{tag}")


if __name__ == "__main__":
    main()
