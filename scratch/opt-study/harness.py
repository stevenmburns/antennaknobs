"""Shared solve harness for the #1202 optimiser study.

COST MODEL: a *distinct solve* is one call to the engine at a parameter tuple
never solved before in that run. Anything that reuses a tuple already solved is
free -- that is the memo #1176 shipped, and it is why a finite-difference
Jacobian that reuses the base point costs 2 solves on two knobs, not 3.

The disk cache is a STUDY convenience so the grid and the trajectories share
work across processes; per-method counting uses its own `seen` set and is not
affected by what another method already put on disk.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
CACHE = HERE / "solves.json"

_disk: dict[str, list[float]] = {}
if CACHE.exists():
    _disk = json.loads(CACHE.read_text())


def _flush():
    CACHE.write_text(json.dumps(_disk))


def make_deck(kind):
    """Return (builder_factory, engine_kwargs, knob_names, box, z0)."""
    if kind == "moxon":
        from antennaknobs.designs.beams.moxon import Builder

        # halfdriver sets X (crosses zero near 2.478), tipspacer_factor sets
        # R (57 -> 16 across the box). t0_factor is FIXED at its tuned value:
        # a (tipspacer, t0) pair never reaches X = 0 at all on this deck -- both
        # tune coupling, and the box has no root to find. Measured 2026-09-06.
        knobs = ["halfdriver", "tipspacer_factor"]
        box = [(2.40, 2.56), (0.030, 0.130)]
        return Builder, dict(ground=None), knobs, box, 50.0
    if kind == "brv12":
        from antennaknobs.designs.verticals.buried_radial_vertical import Builder

        # radial_factor's DEFAULT is 0.6 and the knob saturates above ~0.7:
        # sampled over [0.55, 1.45] it looks dead (R moves 43 -> 48 across the
        # whole range). Its live range is BELOW the default, where the screen
        # gets lossy: over [0.08, 1.0] R swings 75 -> 44 and X swings -42 -> -1.
        # Measured 2026-09-06; a box picked around the default alone would have
        # made this deck look single-knob.
        knobs = ["length_factor", "radial_factor"]
        box = [(0.88, 1.06), (0.08, 1.00)]
        return (
            Builder,
            dict(ground=("finite", 13.0, 0.005), ground_z=0.0, n_radials=12),
            knobs,
            box,
            50.0,
        )
    raise ValueError(kind)


class Deck:
    def __init__(self, kind):
        self.kind = kind
        self.Builder, self.ekw, self.knobs, self.box, self.z0 = make_deck(kind)
        self.n_radials = self.ekw.pop("n_radials", None)

    def z(self, x, seen=None):
        """Z at parameter tuple x. If `seen` is a set, add the key to it; the
        method's distinct-solve count is len(seen)."""
        key = self.kind + ":" + ",".join(f"{float(v):.10g}" for v in x)
        if seen is not None:
            seen.add(key)
        hit = _disk.get(key)
        if hit is not None:
            return complex(hit[0], hit[1])
        from antennaknobs.engines.momwire import MomwireEngine

        b = self.Builder()
        if self.n_radials is not None:
            b.n_radials = self.n_radials
        for name, v in zip(self.knobs, x, strict=True):
            setattr(b, name, float(v))
        zz = complex(MomwireEngine(b, **self.ekw).impedance()[0])
        _disk[key] = [zz.real, zz.imag]
        if len(_disk) % 25 == 0:
            _flush()
        return zz

    def flush(self):
        _flush()


def residual(z, z0):
    """The two-component root: R - R0 = 0 and X = 0."""
    return (z.real - z0, z.imag)


def obj_match_z0(z, z0):
    return abs(z - z0)


def obj_resonance(z, z0=None):
    return abs(z.imag)
