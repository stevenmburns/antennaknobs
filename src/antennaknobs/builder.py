from collections.abc import Mapping

from .core import save_or_show
import numpy as np

# matplotlib (pyplot + the mplot3d Line3DCollection) is imported lazily inside
# draw() below — it costs ~0.1 s to import and only the drawing path needs it,
# so keeping it off module import keeps `import antennaknobs` and web startup
# (which never plots) lean.


def merge_params(base, over):
    """Recursively overlay ``over`` onto a copy of ``base``.

    Dict values merge key-by-key at any depth; every other value replaces
    wholesale. In practice ``ui_params`` (the only dict-valued param in the
    catalog) deep-merges, so a variant can flip one nested ui hint without
    restating the subtree, while scalars and the multiband ``bands`` *tuple*
    replace as a unit. That tuple is the shallow-overlay "floor": a variant
    that touches one sub-band must restate the whole ``bands`` tuple, because
    a positional tuple has no key identity to merge on.
    """
    out = dict(base)
    for k, v in over.items():
        # Match Mapping, not dict: the catalog stores ui_params as
        # MappingProxyType, which is a Mapping but not a dict subclass.
        if isinstance(out.get(k), Mapping) and isinstance(v, Mapping):
            out[k] = merge_params(out[k], v)
        else:
            out[k] = v
    return out


def resolve_variant_params(cls, variant):
    """Seed params for the named variant, as an overlay on ``default_params``.

    A variant lists only the keys it changes; the rest come from
    ``default_params``. Overlaying a *complete* variant dict reproduces that
    dict verbatim, so variants written before this became an overlay resolve
    identically. Falls back to ``default_params`` when ``variant`` is falsy,
    ``"default"``, or names no resolvable ``<variant>_params`` attribute
    (stale frontend / unknown name).
    """
    base = dict(cls.default_params)
    if variant and variant != "default":
        v = getattr(cls, f"{variant}_params", None)
        if v is not None and hasattr(v, "keys"):
            return merge_params(base, v)
    return base


def diff_params(base, target):
    """Minimal overlay ``d`` such that ``merge_params(base, d) == target``.

    The inverse of :func:`merge_params`: recurse into Mappings, keeping only the
    leaves of ``target`` that ``base`` lacks or disagrees with. Used to trim a
    fully-merged variant back down to just its deltas from ``default_params`` —
    the same minimal form a hand-authored ``<variant>_params`` overlay takes.

    Assumes ``target``'s keys are a superset of ``base``'s: a variant overlays
    ``default_params`` and so only adds or changes keys, never drops one, which
    is exactly the round-trip case this supports.
    """
    out = {}
    for k, v in target.items():
        if k not in base:
            out[k] = v
        elif isinstance(base[k], Mapping) and isinstance(v, Mapping):
            sub = diff_params(base[k], v)
            if sub:
                out[k] = sub
        elif base[k] != v:
            out[k] = v
    return out


class AntennaBuilder:
    # Framework-level params live alongside per-design default_params but
    # don't surface in the UI param panel (adapter._auto_paramspec walks
    # default_params, not this). Convergence drives nominal_nsegs from
    # the request's n_per_wire field; generators read it as
    # `self.nominal_nsegs` and scale per-edge segment counts accordingly.
    FRAMEWORK_PARAMS = {"nominal_nsegs": 21}

    def __init__(self, params=None):
        # write directly to __dict__ because otherwise __setattr__ goes into infinite loop
        merged = dict(self.FRAMEWORK_PARAMS)
        merged.update(self.__class__.default_params if params is None else params)
        self.__dict__["_params"] = merged

        "Check that params key's are legal"
        assert all(
            k in self.__class__.default_params or k in self.FRAMEWORK_PARAMS
            for k in self._params.keys()
        )

    def __getattr__(self, nm):
        if nm in self._params:
            return self._params[nm]
        else:
            # raise AttributeError to get hasattr() to work correctly
            classname = type(self).__name__
            msg = f"{classname!r} object has no attribute {nm!r}"
            raise AttributeError(msg)

    def __setattr__(self, nm, v):
        self._params[nm] = v

    def __str__(self):
        res = []
        for k, v in self._params.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                res.append(f"{k} = {v:.4f}")
            else:
                # Non-numeric values (ui_params dict, complex excitation,
                # variant overrides) — fall back to repr so optimizer logs
                # don't crash on them.
                res.append(f"{k} = {v!r}")
        return ", ".join(res)

    def build_tls(self):
        return []

    def build_network(self):
        """Return a port-based network spec, or None to fall through to the
        legacy `build_tls()` path. See `antennaknobs.network` for the
        type shape (Network/Port*/Branch*/Driven). When non-None, engines
        consume this instead of `build_tls()` — virtual ports don't need
        a dummy stub wire, branches refer to ports by name, etc."""
        return None

    def segs_for(self, length, ref):
        """Mesh segment count for a wire of the given `length`.

        Scales `self.nominal_nsegs` (the segment count for a reference-length
        wire) by `length / ref`, so longer wires get proportionally more
        segments and the segment length stays roughly constant. `ref` is
        usually a quarter-wavelength; the count is floored at 3.

        Parity is intentionally NOT forced here. Each solver wants a particular
        segment parity so the feed lands on (or symmetrically across) the
        center — sinusoidal, B-spline degree-2 and PyNEC want odd; B-spline
        degree-1 wants even — and every engine coerces each count to its own
        parity at solve time (`SimulationEngine.coerce_n_seg`). Returning the
        natural count and letting the solver round is why this is `segs_for`,
        not the old `odd_nsegs`: baking in odd here would just make an
        even-parity solve bump the count up by one."""
        return max(3, round(self.nominal_nsegs * length / ref))

    def _phasor(self, name):
        """Unit phasor exp(j·phase) for a degrees-valued phase param (e.g.
        phase_lr/phase_tb), or 1 if the param is absent."""
        if not hasattr(self, name):
            return 1
        return np.exp(1j * np.pi * getattr(self, name) / 180)

    @staticmethod
    def draw(tups, fn=None):
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Line3DCollection

        # Edges are 4-tuples (p0, p1, nsegs, excitation) or 5-tuples with a
        # trailing port name (named-edge designs like sterba_tl and the
        # network builders); take the endpoints regardless of arity.
        pairs = [(t[0], t[1]) for t in tups]

        lc = Line3DCollection(pairs, colors=(1, 0, 0, 1), linewidths=1)

        fig = plt.figure()
        ax = fig.add_subplot(111, projection="3d")
        ax.add_collection3d(lc)
        ax.set_xlim(-5, 5)
        ax.set_ylim(-5, 5)
        ax.set_zlim(0, 10)
        ax.set_aspect("equal")

        save_or_show(plt, fn)


class Array2x2Builder(AntennaBuilder):
    def __init__(self, element_builder, params=None):
        self.__dict__["element_builder"] = element_builder
        super().__init__(params)

    def build_wires(self):
        elem_params = self.element_builder.default_params
        elem_params_keys = set(elem_params.keys())

        changed_keys = set()
        for k, v in self._params.items():
            if k not in elem_params_keys:
                if k.endswith("_top") or k.endswith("_bot"):
                    elem_key = k[:-4]
                    assert elem_key in elem_params_keys
                    changed_keys.add(elem_key)

        def build_element_wires(suffix):
            local_element_params = dict(elem_params)
            for k, v in self._params.items():
                if k in elem_params_keys and k not in changed_keys:
                    local_element_params[k] = v

            for k in changed_keys:
                local_element_params[k] = self._params[k + suffix]

            # Propagate framework params (e.g. nominal_nsegs) — they live
            # outside default_params so the elem_params_keys filter above
            # skips them, but the child element builder needs them to
            # actually scale segmentation with the parent's setting.
            for k in self.FRAMEWORK_PARAMS:
                if k in self._params:
                    local_element_params[k] = self._params[k]

            element_builder_local = self.element_builder(local_element_params)

            return element_builder_local.build_wires()

        tups_top = build_element_wires("_top")
        tups_bot = build_element_wires("_bot")

        phasor_lr = self._phasor("phase_lr")
        phasor_tb = self._phasor("phase_tb")

        new_tups = []
        for yoff, ph0 in ((-self.del_y, 1), (self.del_y, phasor_lr)):
            for zoff, tups, ph1 in (
                (self.del_z, tups_top, 1),
                (-self.del_z, tups_bot, phasor_tb),
            ):
                for (x0, y0, z0), (x1, y1, z1), ns, ex in tups:
                    new_tups.extend(
                        [
                            (
                                (x0, y0 + yoff, z0 + zoff),
                                (x1, y1 + yoff, z1 + zoff),
                                ns,
                                ph0 * ph1 if ex is not None else ex,
                            )
                        ]
                    )

        return new_tups


class Array2x4Builder(AntennaBuilder):
    def __init__(self, element_builder, params=None):
        self.__dict__["element_builder"] = element_builder
        super().__init__(params)

    def build_wires(self):
        elem_params = self.element_builder.default_params
        elem_params_keys = set(elem_params.keys())

        suffixes = ["_itop", "_ibot", "_otop", "_obot"]

        changed_keys = set()
        for k, v in self._params.items():
            if k not in elem_params_keys:
                if any(k.endswith(suffix) for suffix in suffixes):
                    elem_key = k[:-5]
                    assert elem_key in elem_params_keys
                    changed_keys.add(elem_key)

        def build_element_wires(suffix):
            local_element_params = dict(elem_params)
            for k, v in self._params.items():
                if k in elem_params_keys and k not in changed_keys:
                    local_element_params[k] = v

            for k in changed_keys:
                local_element_params[k] = self._params[k + suffix]

            # Propagate framework params (e.g. nominal_nsegs) — they live
            # outside default_params so the elem_params_keys filter above
            # skips them, but the child element builder needs them to
            # actually scale segmentation with the parent's setting.
            for k in self.FRAMEWORK_PARAMS:
                if k in self._params:
                    local_element_params[k] = self._params[k]

            element_builder_local = self.element_builder(local_element_params)

            return element_builder_local.build_wires()

        tups_itop = build_element_wires("_itop")
        tups_otop = build_element_wires("_otop")
        tups_ibot = build_element_wires("_ibot")
        tups_obot = build_element_wires("_obot")

        phasor_lr = self._phasor("phase_lr")
        phasor_tb = self._phasor("phase_tb")

        new_tups = []
        # ph_lr is applied to the right-half (yoff > 0) columns and
        # ph_tb to the bottom-half (negative zoff) rows — same
        # left/right + top/bottom split convention as Array2x2Builder.
        for yoff, ph_lr, pairs in (
            (-3 * self.del_y, 1, ((self.del_z, tups_otop), (-self.del_z, tups_obot))),
            (-1 * self.del_y, 1, ((self.del_z, tups_itop), (-self.del_z, tups_ibot))),
            (
                1 * self.del_y,
                phasor_lr,
                ((self.del_z, tups_itop), (-self.del_z, tups_ibot)),
            ),
            (
                3 * self.del_y,
                phasor_lr,
                ((self.del_z, tups_otop), (-self.del_z, tups_obot)),
            ),
        ):
            for zoff, tups in pairs:
                ph_tb = 1 if zoff > 0 else phasor_tb
                new_tups.extend(
                    [
                        (
                            (x0, y0 + yoff, z0 + zoff),
                            (x1, y1 + yoff, z1 + zoff),
                            ns,
                            ph_lr * ph_tb * ex if ex is not None else ex,
                        )
                        for ((x0, y0, z0), (x1, y1, z1), ns, ex) in tups
                    ]
                )

        return new_tups


class Array1x4Builder(AntennaBuilder):
    def __init__(self, element_builder, params=None):
        self.__dict__["element_builder"] = element_builder
        super().__init__(params)

    def build_wires(self):
        elem_params = self.element_builder.default_params
        elem_params_keys = set(elem_params.keys())

        suffixes = ["_itop", "_otop"]

        changed_keys = set()
        for k, v in self._params.items():
            if k not in elem_params_keys:
                if any(k.endswith(suffix) for suffix in suffixes):
                    elem_key = k[:-5]
                    assert elem_key in elem_params_keys
                    changed_keys.add(elem_key)

        def build_element_wires(suffix):
            local_element_params = dict(elem_params)
            for k, v in self._params.items():
                if k in elem_params_keys and k not in changed_keys:
                    local_element_params[k] = v

            for k in changed_keys:
                local_element_params[k] = self._params[k + suffix]

            # Propagate framework params (e.g. nominal_nsegs) — they live
            # outside default_params so the elem_params_keys filter above
            # skips them, but the child element builder needs them to
            # actually scale segmentation with the parent's setting.
            for k in self.FRAMEWORK_PARAMS:
                if k in self._params:
                    local_element_params[k] = self._params[k]

            element_builder_local = self.element_builder(local_element_params)

            return element_builder_local.build_wires()

        tups_itop = build_element_wires("_itop")
        tups_otop = build_element_wires("_otop")

        phasor_lr = self._phasor("phase_lr")

        new_tups = []
        # phase_lr is applied to the right half (yoff > 0); left half
        # (yoff < 0) stays at ph=1. Matches the Array1x2Builder split
        # convention extended to 4 elements.
        for yoff, ph_lr, pairs in (
            (-3 * self.del_y, 1, ((self.del_z, tups_otop),)),
            (-1 * self.del_y, 1, ((self.del_z, tups_itop),)),
            (1 * self.del_y, phasor_lr, ((self.del_z, tups_itop),)),
            (3 * self.del_y, phasor_lr, ((self.del_z, tups_otop),)),
        ):
            for zoff, tups in pairs:
                new_tups.extend(
                    [
                        (
                            (x0, y0 + yoff, z0 + zoff),
                            (x1, y1 + yoff, z1 + zoff),
                            ns,
                            ph_lr * ex if ex is not None else ex,
                        )
                        for ((x0, y0, z0), (x1, y1, z1), ns, ex) in tups
                    ]
                )

        return new_tups


class Array1x4GroupedBuilder(AntennaBuilder):
    def __init__(self, element_builder, params=None):
        self.__dict__["element_builder"] = element_builder
        super().__init__(params)

    def build_wires(self):
        elem_params = self.element_builder.default_params
        elem_params_keys = set(elem_params.keys())

        suffixes = ["_itop", "_otop"]

        changed_keys = set()
        for k, v in self._params.items():
            if k not in elem_params_keys:
                if any(k.endswith(suffix) for suffix in suffixes):
                    elem_key = k[:-5]
                    assert elem_key in elem_params_keys
                    changed_keys.add(elem_key)

        def build_element_wires(suffix):
            local_element_params = dict(elem_params)
            for k, v in self._params.items():
                if k in elem_params_keys and k not in changed_keys:
                    local_element_params[k] = v

            for k in changed_keys:
                local_element_params[k] = self._params[k + suffix]

            # Propagate framework params (e.g. nominal_nsegs) — they live
            # outside default_params so the elem_params_keys filter above
            # skips them, but the child element builder needs them to
            # actually scale segmentation with the parent's setting.
            for k in self.FRAMEWORK_PARAMS:
                if k in self._params:
                    local_element_params[k] = self._params[k]

            element_builder_local = self.element_builder(local_element_params)

            return element_builder_local.build_wires()

        tups_itop = build_element_wires("_itop")
        tups_otop = build_element_wires("_otop")

        phasor_lr = self._phasor("phase_lr")

        new_tups = []
        # phase_lr applied to the right half (yoff > 0). The grouped
        # variant uses del_y0 ± del_y1 spacings but the left/right split
        # is the same as Array1x4Builder.
        for yoff, ph_lr, pairs in (
            (-self.del_y0 - self.del_y1, 1, ((self.del_z, tups_otop),)),
            (-self.del_y0 + self.del_y1, 1, ((self.del_z, tups_itop),)),
            (self.del_y0 - self.del_y1, phasor_lr, ((self.del_z, tups_itop),)),
            (self.del_y0 + self.del_y1, phasor_lr, ((self.del_z, tups_otop),)),
        ):
            for zoff, tups in pairs:
                new_tups.extend(
                    [
                        (
                            (x0, y0 + yoff, z0 + zoff),
                            (x1, y1 + yoff, z1 + zoff),
                            ns,
                            ph_lr * ex if ex is not None else ex,
                        )
                        for ((x0, y0, z0), (x1, y1, z1), ns, ex) in tups
                    ]
                )

        return new_tups


class Array1x2Builder(AntennaBuilder):
    def __init__(self, element_builder, params=None):
        self.__dict__["element_builder"] = element_builder
        super().__init__(params)

    def build_wires(self):
        elem_params = self.element_builder.default_params
        elem_params_keys = set(elem_params.keys())

        changed_keys = set()
        for k, v in self._params.items():
            if k not in elem_params_keys:
                if k.endswith("_top"):
                    elem_key = k[:-4]
                    assert elem_key in elem_params_keys
                    changed_keys.add(elem_key)

        def build_element_wires(suffix):
            local_element_params = dict(elem_params)
            for k, v in self._params.items():
                if k in elem_params_keys and k not in changed_keys:
                    local_element_params[k] = v

            for k in changed_keys:
                local_element_params[k] = self._params[k + suffix]

            # Propagate framework params (e.g. nominal_nsegs) — they live
            # outside default_params so the elem_params_keys filter above
            # skips them, but the child element builder needs them to
            # actually scale segmentation with the parent's setting.
            for k in self.FRAMEWORK_PARAMS:
                if k in self._params:
                    local_element_params[k] = self._params[k]

            element_builder_local = self.element_builder(local_element_params)

            return element_builder_local.build_wires()

        tups_top = build_element_wires("_top")

        phasor_lr = self._phasor("phase_lr")

        # A 1x2 array is a single row of two elements offset to ∓del_y — the
        # left at unit drive, the right at the phase_lr phasor. There is NO z
        # iteration: with one row the elements keep the element builder's own z
        # (their `base`), and there is no array z-spacing. (The 2x2/1x4/2x4
        # builders DO iterate z; this one was originally copied from the 2x2 and
        # carried a vestigial single-entry z-loop + `del_z` that only rigidly
        # shifted the whole array — inert in free space — now removed.)
        new_tups = []
        for yoff, ph0 in ((-self.del_y, 1), (self.del_y, phasor_lr)):
            for (x0, y0, z0), (x1, y1, z1), ns, ex in tups_top:
                new_tups.append(
                    (
                        (x0, y0 + yoff, z0),
                        (x1, y1 + yoff, z1),
                        ns,
                        ph0 if ex is not None else ex,
                    )
                )

        return new_tups
