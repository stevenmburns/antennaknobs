"""A load moved along one wire without a rebuild, for the optimizer (opt-in).

momwire's ``BSplineSolver.port_sites`` (momwire#1915) solves, beside a
solver's own ports, one shorted port per B-spline basis on a chosen wire, and
then answers the short-circuit Y with a point port at ANY arclength on that
wire from the cached columns (``PortSites.y``). A point gap on a Galerkin
basis leaves Z alone, so this is the same Y a fresh solver with an ordinary
point feed there returns, to rounding, at a few hundred microseconds per
position instead of a fill and a factorisation.

A multi-band optimize evaluates one design at several frequencies per trial.
When the only thing that moved between two trials is where one port sits on
one wire (a load's position knob), every solver input but that port's
arclength is the same, and `PortSitesSession` serves the trial from a cached
`PortSites` per (everything else, frequency). The trial's own engine still
builds its own network reducer, so the loads, the station chain and any
``.s2p`` block are stamped on that Y exactly as a rebuild stamps them; only
the antenna's port Y comes from the cache.

Validity is read off the solver's construction inputs, never off knob names:
the key is momwire's construction kwargs (`engines.momwire._z_fill_key`, the
digest the Z cache trusts) with the moving port's arclength taken out and its
wire kept in. A trial whose inputs differ anywhere else is solved by the
ordinary rebuild, and the reason is counted (`summary`), as momwire's own
``pair_reuse`` declines are reported.

The fast path needs the moving wire to stay ONE wire. By default the momwire
engine splits a wire at a positioned port that is not a site of its count
(AK#1519) so the mesh matches PyNEC / NEC-5, which re-meshes the wire on
every move; `engine_kwargs` builds the run's engines with that split off, on
the fast path and on its fallback rebuilds alike, so one run sees one model:
the load at its exact arclength on the wire's own mesh. On a site the two
models are the same mesh; between sites they differ by the mesh difference.

Off unless asked: `asked` reads a request's value, else the
``ANTENNAKNOBS_PORT_SITES`` server seed; an explicit off wins. B-spline only
(``nec5-bspline`` / ``nec42-bspline``), and only where the installed momwire
has the method (`available`, a live probe).
"""

from __future__ import annotations

import os
from collections import Counter, OrderedDict

import numpy as np

#: The server env that seeds an unset request (``1`` / ``on``).
SEED_ENV = "ANTENNAKNOBS_PORT_SITES"

#: The reason a trial is solved by a rebuild because this momwire has no
#: ``port_sites``. Tests skip on the same probe.
NO_PORT_SITES = "the installed momwire has no BSplineSolver.port_sites (momwire#1915)"


def available() -> bool:
    """Whether the installed momwire's ``BSplineSolver`` has ``port_sites``."""
    from momwire import BSplineSolver

    return callable(getattr(BSplineSolver, "port_sites", None))


def asked(value) -> bool:
    """A request's ``port_sites`` value, the server seed filling an unset one."""
    if value is None:
        return os.environ.get(SEED_ENV, "") in ("1", "on")
    return bool(value)


def engine_kwargs() -> dict:
    """The momwire engine kwargs a port-sites run builds every engine with."""
    return {"whole_wire_ports": True}


def _sig(cls, kwargs, moving=None):
    """`_z_fill_key` of ``kwargs`` less the wavelength, with feed ``moving``
    (if any) reduced to its wire: equal digests mean equal solver inputs
    except, at most, that one port's arclength."""
    from .engines.momwire import _z_fill_key

    kw = {k: v for k, v in kwargs.items() if k != "wavelength"}
    if moving is not None:
        feeds = list(kw["feeds"])
        feeds[moving] = (feeds[moving][0], None, 0j)
        kw["feeds"] = feeds
    return _z_fill_key(cls, kw)


class PortSitesSession:
    """One optimize run's cache of `PortSites`, and its tally.

    ``sweep(eng, freqs)`` returns what ``eng.impedance_sweep(freqs)`` would
    (``(n_freqs, n_driven)``), from the cache when the trial differs from a
    cached one only in one port's arclength on one wire, else from that very
    call. ``max_entries`` bounds the cached (geometry, frequency) entries,
    least recently used first."""

    def __init__(self, max_entries: int = 16) -> None:
        self.max_entries = int(max_entries)
        self.counts = {"fast": 0, "rebuild": 0, "built": 0}
        self.declined: Counter = Counter()
        self._cache: OrderedDict = OrderedDict()
        self._moving: int | None = None
        self._prev: tuple | None = None
        self._bytes = 0

    # -- the one entry point ------------------------------------------------

    def sweep(self, eng, freqs) -> np.ndarray:
        freqs = [float(f) for f in freqs]
        why = self._ineligible(eng)
        if why is not None:
            return self._rebuild(eng, freqs, why)
        solver = eng._make_solver(wavelength=eng._wavelength_for(freqs[0]))
        cls, kwargs = solver._ak_construct
        del solver
        n = len(kwargs["feeds"])
        full = _sig(cls, kwargs)
        if full is None:
            return self._rebuild(eng, freqs, "the solver's inputs do not digest")
        prev, self._prev = self._prev, (full, n, cls, kwargs)
        moving = self._moving
        if moving is None or moving >= n:
            moving = self._find_moving(prev, full, n, cls, kwargs)
            if moving is None:
                return self._rebuild(
                    eng, freqs, "no trial yet differs from the last in one port only"
                )
            self._moving = moving
        base = _sig(cls, kwargs, moving)
        wls = [eng._wavelength_for(f) for f in freqs]
        keys = [(base, float(wl)) for wl in wls]
        if not all(k in self._cache for k in keys):
            seen = prev is not None and prev[1] == n and _sig(prev[2], prev[3], moving)
            if seen != base:
                return self._rebuild(
                    eng, freqs, "knobs other than the port's position moved"
                )
            try:
                for key, wl in zip(keys, wls, strict=True):
                    if key not in self._cache:
                        self._put(key, self._build(cls, kwargs, moving, wl))
            except ValueError as exc:
                # momwire's refusal, by name: a non-point feed, smoothing, the
                # sector route, enrichment "auto", a dropped duplicate wire.
                return self._rebuild(eng, freqs, f"momwire refused: {exc}")
        x = float(kwargs["feeds"][moving][1])
        zs = np.empty((len(freqs), eng._reducer.n_driven), dtype=np.complex128)
        for row, (key, wl, f) in enumerate(zip(keys, wls, freqs, strict=True)):
            eng._raise_if_cancelled()
            self._cache.move_to_end(key)
            zs[row] = self._z_at(eng, self._cache[key], moving, x, wl, f)
        self.counts["fast"] += 1
        return zs

    def summary(self) -> dict:
        """The run's tally: trials served fast, rebuilt, PortSites built, the
        reasons a trial was rebuilt (with counts), and the bytes held."""
        return {
            "fast": self.counts["fast"],
            "rebuild": self.counts["rebuild"],
            "built": self.counts["built"],
            "declined": dict(self.declined),
            "cached_bytes": self._bytes,
        }

    # -- pieces ---------------------------------------------------------------

    def _ineligible(self, eng) -> str | None:
        from momwire import BSplineSolver

        if not available():
            return NO_PORT_SITES
        if not hasattr(eng, "_make_solver") or getattr(eng, "_solver", None) is None:
            return "not the momwire engine"
        if eng._solver is not BSplineSolver:
            return (
                "the B-spline basis only (nec5-bspline / nec42-bspline), "
                f"not {eng._solver.__name__}"
            )
        if getattr(eng, "_network", None) is None:
            return "the design has no circuit network for a moved port to carry"
        w = getattr(eng, "_feed_W", None)
        if w is not None and w.shape[0] != w.shape[1]:
            # A square W is the walk-sign diagonal (issue #580), one solver
            # feed per port, which `_contract_y` applies to the cached Y as
            # it does to a rebuild's; only a sub-feed expansion is refused.
            return "a distributed (finite-gap) port"
        if getattr(eng, "_split_wires", None):
            return (
                "a wire is split at its ports (AK#1519); build the engines "
                "with port_sites.engine_kwargs()"
            )
        return None

    def _rebuild(self, eng, freqs, why: str) -> np.ndarray:
        self.counts["rebuild"] += 1
        self.declined[why] += 1
        return np.asarray(eng.impedance_sweep(list(freqs)), dtype=np.complex128)

    @staticmethod
    def _find_moving(prev, full, n, cls, kwargs) -> int | None:
        """The one feed whose arclength alone moved since ``prev``, or None."""
        if prev is None or prev[1] != n or prev[0] == full:
            return None
        hits = [
            i
            for i in range(n)
            if kwargs["feeds"][i][0] == prev[3]["feeds"][i][0]
            and _sig(cls, kwargs, i) == _sig(prev[2], prev[3], i)
        ]
        return hits[0] if len(hits) == 1 else None

    def _build(self, cls, kwargs, moving, wl):
        """A `PortSites` on the moving port's wire, solved with every other
        port configured, at wavelength ``wl``."""
        feeds = list(kwargs["feeds"])
        wire = int(feeds.pop(moving)[0])
        solver = cls(**{**kwargs, "feeds": feeds, "wavelength": wl})
        ps = solver.port_sites(wire)
        self.counts["built"] += 1
        return ps

    def _put(self, key, ps) -> None:
        self._cache[key] = ps
        self._bytes += ps.nbytes
        while len(self._cache) > self.max_entries:
            _k, old = self._cache.popitem(last=False)
            self._bytes -= old.nbytes

    @staticmethod
    def _z_at(eng, ps, moving, x, wl, f):
        """The driven ports' Z at frequency ``f`` with the moving port at
        arclength ``x``: Y in the engine's port order, contracted and reduced
        by the trial's own reducer, as `MomwireEngine.impedance_sweep` does."""
        from .network_reduce import poison_singular_sample

        y = ps.y([x])
        # PortSites orders [the other ports..., the moved port]; the engine's
        # order has the moved port at its feed index.
        n = y.shape[0]
        order = [
            j if j < moving else (n - 1 if j == moving else j - 1) for j in range(n)
        ]
        y = eng._contract_y(y[np.ix_(order, order)])
        z = poison_singular_sample(eng._reduce_at, y, wl, where=f" at {f:.6g} MHz")
        return np.nan if z is None else z
