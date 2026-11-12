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
wire kept in. A trial whose base is not cached builds that base's PortSites
as its own solve; a trial the path cannot serve at all (the wrong basis, no
network, the moving port not yet identified, a momwire refusal) is solved by
the ordinary rebuild, and the reason is counted (`summary`), as momwire's own
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

# Trials remembered while the moving port is still unknown.
_HISTORY = 64


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


def place_loads_exactly(builder):
    """Ask ``builder`` (a file design) to carry each load at its exact place
    along its wire (`NecDeck.exact_load_places`), and return it.

    A deck's load on a wire that keeps the cut spelling (a SimNEC NECSource
    on a wire fed at its end, say) is otherwise cut out as a one-segment
    piece of its own, so a position knob only moves it segment by segment
    and its slope reads zero. Set outside the builder's params, so nothing
    the CLI prints or a study keeps carries it. A catalog design ignores it."""
    object.__setattr__(builder, "exact_load_places", True)
    return builder


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
    (``(n_freqs, n_driven)``).

    Until the moving port is known every trial is a rebuild, and each one's
    per-port base digests are remembered. The first trial whose digest with
    port i taken out matches ANY earlier trial's, at a different arclength
    on that port, fixes i as the moving port: a finite-difference probe that
    stepped the position from a base the run solved earlier does, whatever
    was solved in between.

    From then on a trial is answered from the cache when its base (the
    digest without port i) is cached, and otherwise by building that base's
    `PortSites` per band and answering from it: the build IS the trial's
    solve, never a rebuild followed by a build. ``max_entries`` and
    ``max_bytes`` bound the cached (base, band) entries, least recently used
    first."""

    def __init__(
        self,
        max_entries: int = 64,
        max_bytes: int = 256 * 2**20,
        build_new_bases: bool = True,
    ) -> None:
        # ``build_new_bases=False`` rebuilds a base the run has not solved
        # before and builds its PortSites only when it comes round again:
        # cheaper where most new bases never recur (a geometry knob's probes),
        # dearer where they do. Kept for measuring the two against each other.
        self.build_new_bases = bool(build_new_bases)
        self._bases_seen: set = set()
        self.max_entries = int(max_entries)
        self.max_bytes = int(max_bytes)
        self.counts = {"fast": 0, "first": 0, "rebuild": 0, "built": 0}
        # Knob gradients served by `gradients`, no solve each.
        self.n_gradients = 0
        # Solvers built only to note where ports landed (`_construction`),
        # and whether one has shown the notes are empty on this run.
        self.n_solvers = 0
        self._notes_empty = False
        self._last: dict | None = None
        self.declined: Counter = Counter()
        self._cache: OrderedDict = OrderedDict()
        self._moving: int | None = None
        # (n_feeds, per-feed arclengths, per-feed base digests) per trial
        # solved before the moving port was known.
        self._history: list[tuple] = []
        self._bytes = 0

    # -- the one entry point ------------------------------------------------

    def sweep(self, eng, freqs) -> np.ndarray:
        freqs = [float(f) for f in freqs]
        self._last = None
        why = self._ineligible(eng)
        if why is not None:
            return self._rebuild(eng, freqs, why)
        cls, kwargs = self._construction(eng, eng._wavelength_for(freqs[0]))
        n = len(kwargs["feeds"])
        moving = self._moving
        if moving is None or moving >= n:
            moving = self._find_moving(cls, kwargs)
            if moving is None:
                return self._rebuild(
                    eng,
                    freqs,
                    "no earlier trial differs from this one in one port's position only",
                )
            self._moving = moving
            # The bases the run already solved, with the moving port out.
            self._bases_seen.update(
                h[2][moving] for h in self._history[:-1] if h[0] == n
            )
            self._history.clear()
        base = _sig(cls, kwargs, moving)
        if base is None:
            return self._rebuild(eng, freqs, "the solver's inputs do not digest")
        wls = [eng._wavelength_for(f) for f in freqs]
        keys = [(base, float(wl)) for wl in wls]
        missing = [
            (k, wl) for k, wl in zip(keys, wls, strict=True) if k not in self._cache
        ]
        if missing and not self.build_new_bases and base not in self._bases_seen:
            self._bases_seen.add(base)
            return self._rebuild(eng, freqs, "a base this run had not solved before")
        self._bases_seen.add(base)
        built = {}
        try:
            for key, wl in missing:
                built[key] = self._build(cls, kwargs, moving, wl)
        except ValueError as exc:
            # momwire's refusal, by name: a non-point feed, smoothing, the
            # sector route, enrichment "auto", a dropped duplicate wire.
            return self._rebuild(eng, freqs, f"momwire refused: {exc}")
        x = float(kwargs["feeds"][moving][1])
        zs = np.empty((len(freqs), eng._reducer.n_driven), dtype=np.complex128)
        sites = []
        for row, (key, wl, f) in enumerate(zip(keys, wls, freqs, strict=True)):
            eng._raise_if_cancelled()
            ps = built.get(key)
            if ps is None:
                self._cache.move_to_end(key)
                ps = self._cache[key]
            sites.append(ps)
            zs[row] = self._z_at(eng, ps, moving, x, wl, f)
        for key, ps in built.items():
            self._put(key, ps)
        self.counts["first" if missing else "fast"] += 1
        self._last = {
            "n": n,
            "moving": moving,
            "base": base,
            "x": x,
            "sites": sites,
            "wls": wls,
            "freqs": freqs,
        }
        return zs

    def ready(self) -> bool:
        """Whether a trial can be served (and differentiated) from the cache:
        the moving port is known."""
        return self._moving is not None

    def gradients(self, at, knobs, rel: float = 1e-6) -> dict:
        """``{knob: (n_freqs, n_driven) dZ/dknob}`` at the trial `sweep` just
        served, for each knob of ``knobs`` (``{name: value}``) that moves
        only the cached port's position and the network; no solve.

        ``at(name, value)`` is an engine (unsolved) with that knob at
        ``value`` and every other knob at the trial's. Each knob is stepped by
        ``rel`` of its value either side. When the engines either side keep
        the trial's base (the solver's inputs less the moving port's
        arclength), the knob reaches Z only through that arclength x and the
        network the reducer stamps, so

            dZ/dk = d/dk R_k(Y(x(k))),   Y(x(k ± d)) = Y(x) ± d · x'(k) · dY/dx,

        with dY/dx exact (`PortSites.dy_dx`), x'(k) the arclength's central
        difference (exact for a percentage of a fixed wire, x = pct/100 · L),
        and R_k± the two engines' own reducers: a central difference in the
        knob of a solve-free function, O(d^2). A knob whose either side moves
        the base (a geometry knob) is left out: the caller differentiates it
        by a solve. Empty when the trial was not served from a PortSites."""
        last = getattr(self, "_last", None)
        if last is None:
            return {}
        out = {}
        moving = last["moving"]
        for name, v in knobs.items():
            v = float(v)
            d = rel * max(abs(v), 1e-3)
            sides = []
            for s in (1.0, -1.0):
                e = at(name, v + s * d)
                if self._ineligible(e) is not None:
                    break
                cls, kw = self._construction(e, last["wls"][0])
                if (
                    len(kw["feeds"]) != last["n"]
                    or _sig(cls, kw, moving) != last["base"]
                ):
                    break
                sides.append((e, float(kw["feeds"][moving][1])))
            if len(sides) != 2:
                continue
            (ep, xp), (em, xm) = sides
            dxdk = (xp - xm) / (2.0 * d)
            rows = []
            for ps, wl, f in zip(
                last["sites"], last["wls"], last["freqs"], strict=True
            ):
                y = ps.y([last["x"]])
                dy = ps.dy_dx([last["x"]])[0] * (d * dxdk)
                zp = self._z_from_y(ep, y + dy, moving, wl, f)
                zm = self._z_from_y(em, y - dy, moving, wl, f)
                rows.append((np.asarray(zp) - np.asarray(zm)) / (2.0 * d))
            out[name] = np.array(rows, dtype=np.complex128)
        self.n_gradients += len(out)
        return out

    def summary(self) -> dict:
        """The run's tally: trials served from the cache (``fast``), trials
        answered by building their base's PortSites (``first``), trials
        rebuilt, PortSites built (one per base and band), the reasons a trial
        was rebuilt (with counts), and the bytes held."""
        return {
            "fast": self.counts["fast"],
            "first": self.counts["first"],
            "rebuild": self.counts["rebuild"],
            "built": self.counts["built"],
            "gradients": self.n_gradients,
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

    def _construction(self, eng, wl):
        """The trial's solver class and constructor kwargs, with no solver
        built (`MomwireEngine._construction`), and its placement notes.

        A solver is what notes where each positioned port landed
        (`_note_feed_placements`), and the CLI holds an engine until it has
        them. On this path the basis is the B-spline one with point feeds,
        which honours every arclength exactly, so the notes are empty: the
        first engines of a run are noted by a real solver until one has
        confirmed that, and from then on each engine's notes are set empty
        without one. A run whose solver ever notes an offset keeps building
        the solver for every engine."""
        if getattr(eng, "_placement_notes", None) is None:
            if self._notes_empty:
                eng._placement_notes = []
            else:
                self.n_solvers += 1
                eng._make_solver(wavelength=wl)
                self._notes_empty = eng._placement_notes == []
        return eng._construction(wavelength=wl)

    def _rebuild(self, eng, freqs, why: str) -> np.ndarray:
        self.counts["rebuild"] += 1
        self.declined[why] += 1
        return np.asarray(eng.impedance_sweep(list(freqs)), dtype=np.complex128)

    def _find_moving(self, cls, kwargs) -> int | None:
        """The feed whose arclength alone differs between this trial and some
        earlier one, or None; this trial joins the history either way.

        Feed i's base digest keeps its wire and every other input, so an
        equal digest at a different arclength on i is exactly "only port i
        moved along its wire". At most one feed can match a given earlier
        trial: if i's digests agree, every other feed's digest still carries
        i's differing arclength."""
        feeds = kwargs["feeds"]
        n = len(feeds)
        arcs = tuple(float(f[1]) for f in feeds)
        sigs = tuple(_sig(cls, kwargs, i) for i in range(n))
        hit = None
        for hn, harcs, hsigs in self._history:
            if hn != n:
                continue
            hit = next(
                (
                    i
                    for i in range(n)
                    if sigs[i] is not None
                    and sigs[i] == hsigs[i]
                    and arcs[i] != harcs[i]
                ),
                None,
            )
            if hit is not None:
                break
        self._history.append((n, arcs, sigs))
        del self._history[:-_HISTORY]
        return hit

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
        if ps.nbytes > self.max_bytes:
            return
        self._cache[key] = ps
        self._bytes += ps.nbytes
        while len(self._cache) > self.max_entries or self._bytes > self.max_bytes:
            _k, old = self._cache.popitem(last=False)
            self._bytes -= old.nbytes

    @classmethod
    def _z_at(cls, eng, ps, moving, x, wl, f):
        """The driven ports' Z at frequency ``f`` with the moving port at
        arclength ``x``: Y in the engine's port order, contracted and reduced
        by the trial's own reducer, as `MomwireEngine.impedance_sweep` does."""
        return cls._z_from_y(eng, ps.y([x]), moving, wl, f)

    @staticmethod
    def _z_from_y(eng, y, moving, wl, f):
        """`_z_at` from a PortSites-ordered Y already in hand."""
        from .network_reduce import poison_singular_sample

        # PortSites orders [the other ports..., the moved port]; the engine's
        # order has the moved port at its feed index.
        n = y.shape[0]
        order = [
            j if j < moving else (n - 1 if j == moving else j - 1) for j in range(n)
        ]
        y = eng._contract_y(y[np.ix_(order, order)])
        z = poison_singular_sample(eng._reduce_at, y, wl, where=f" at {f:.6g} MHz")
        return np.nan if z is None else z
