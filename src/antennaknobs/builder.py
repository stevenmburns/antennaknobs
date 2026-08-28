from collections.abc import Mapping

from .core import save_or_show
from .network import Wire, as_wire
import numpy as np

# matplotlib (pyplot + the mplot3d Line3DCollection) is imported lazily inside
# draw() below — it costs ~0.1 s to import and only the drawing path needs it,
# so keeping it off module import keeps `import antennaknobs` and web startup
# (which never plots) lean.

# Speed of light in the units radio work actually uses: a free-space
# wavelength in metres is ``C_LIGHT_MHZ_M / freq_MHz``. It is the same physical
# constant the engines carry as SI ``C_LIGHT = 299_792_458`` m/s, pre-scaled so
# that dividing by a frequency in MHz yields metres with no 1e6 bookkeeping —
# the form catalog designs (which work in MHz and metres throughout) want. One
# canonical spelling of the number, exported from the package top level, so a
# design never has to write the bare ``299.792458`` literal again.
C_LIGHT_MHZ_M = 299.792458


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

    def __init_subclass__(cls, **kwargs):
        """Auto-meshing is part of the stack: every subclass's
        ``build_wires`` is wrapped so its result passes through
        :meth:`auto_mesh` before any consumer sees it. A builder can
        therefore return ``None`` segment counts and never mention
        meshing; engines, the preview, exporters, and scripts all
        receive resolved integer counts. The wrap is idempotent — a
        legacy builder that calls ``auto_mesh`` itself, or returns only
        explicit counts, passes through unchanged."""
        super().__init_subclass__(**kwargs)
        inner = cls.__dict__.get("build_wires")
        if inner is not None:
            import functools

            @functools.wraps(inner)
            def build_wires(self):
                return self.auto_mesh(list(inner(self)))

            cls.build_wires = build_wires

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

    @property
    def design_wavelength(self):
        """Free-space wavelength in metres at ``design_freq`` (MHz).

        The single named quantity for the ``299.792458 / self.design_freq``
        idiom that every wavelength-scaled builder repeats — geometry held as
        wavelength fractions (``half_frac * self.design_wavelength``) then reads
        as what it is, and the constant lives in exactly one place. This is the
        *design* wavelength (the frequency the geometry is dimensioned for), not
        the *measurement* ``freq``: sweeping ``freq`` must never resize the
        antenna, so wavelength-fraction specs scale against this, matching
        :meth:`auto_mesh`'s density.

        Raises ``ValueError`` if the design declares no ``design_freq`` — a
        builder holding its geometry in wavelength fractions must say what
        frequency those fractions are of, the same contract ``auto_mesh``
        enforces for ``None`` segment counts."""
        design_freq = getattr(self, "design_freq", None)
        if not design_freq:
            raise ValueError(
                f"{type(self).__name__}: design_wavelength needs a design_freq "
                "param (the frequency the geometry is designed for); declare "
                "one in default_params."
            )
        return C_LIGHT_MHZ_M / float(design_freq)

    @property
    def design_medium_wavelength(self):
        """In-medium wavelength in metres BELOW the interface, or ``None``.

        ``lambda_m = lambda_0 / |n|``, refractive-index magnitude
        ``|n| = |sqrt(eps_tilde)|``, ``eps_tilde = eps_r - j*sigma/(omega*eps_0)``
        — the wavelength a buried conductor actually sees. Returns ``None``
        unless the design declares BOTH ``design_eps_r`` and ``design_sigma``;
        a design with no soil declaration meshes everything against free space
        exactly as before (issue #983).

        The soil is the design's stated ASSUMPTION about the dirt, held next
        to ``design_freq`` and for the same reason: the mesh is a property of
        the geometry, so it must not move when the solve-time ``--ground``
        moves. antennaknobs chooses the actual half-space at SOLVE time, and a
        solve over different dirt keeps this mesh -- close, not exact, which is
        what makes it a *nominal* declaration. Sweeping or fitting soil
        therefore never remeshes, matching :meth:`auto_mesh`'s standing rule
        that the measurement ``freq`` never does either.

        Every quantity here is momwire's: ``eps_0`` off a solver class,
        ``eps_tilde`` from ``_ground_refl``, and the wavelength from
        ``_sommerfeld_below.lambda_medium``, which momwire#553 U4 shipped as
        the ONE owner of ``|n|``. Nothing here re-derives it -- the lossless
        ``1/sqrt(eps_r)`` shortcut is NOT this quantity (it drops the
        conduction term, and at eps_r 13 / sigma 0.005 / 7 MHz reads 3.61
        against a true 4.27: an under-mesh that looks fine).
        """
        eps_r = getattr(self, "design_eps_r", None)
        sigma = getattr(self, "design_sigma", None)
        if eps_r is None or sigma is None:
            return None

        import math as _math

        from momwire import RazorSolver as _Solver
        from momwire._ground_refl import eps_tilde as _eps_tilde
        from momwire._sommerfeld_below import lambda_medium as _lambda_medium

        # Derived from design_wavelength, so a soil declaration without a
        # design_freq raises that property's error rather than a bare
        # AttributeError, and design_freq is read in exactly one place.
        k0 = 2.0 * _math.pi / self.design_wavelength
        omega = k0 * C_LIGHT_MHZ_M * 1e6
        eps_t = _eps_tilde((float(eps_r), float(sigma)), omega, _Solver.eps)
        return float(_lambda_medium(eps_t, k0))

    def build_tls(self):
        return []

    def build_network(self):
        """Return a port-based network spec, or None to fall through to the
        legacy `build_tls()` path. See `antennaknobs.network` for the
        type shape (Network/Port*/Branch*/Driven). When non-None, engines
        consume this instead of `build_tls()` — virtual ports don't need
        a dummy stub wire, branches refer to ports by name, etc."""
        return None

    def build_wire_material(self):
        """Return a `WireSpec` (see `antennaknobs.network.WIRES`) describing
        the antenna wire's conductor and insulation, or None for the classic
        idealization (PEC, 0.5 mm radius). Default behavior: a design with a
        `wire_type` param (usually an enum knob over the WIRES catalog keys)
        resolves it here; empty string / None / absent = ideal wire. Engines
        consume the spec for the wire radius, skin-effect loss, and — on
        solvers that model it — the insulated-wire velocity factor."""
        wire_type = getattr(self, "wire_type", None)
        if wire_type:
            from .network import wire_from_catalog

            return wire_from_catalog(wire_type)
        return None

    def segs_for(self, length, ref):
        """Mesh segment count for a wire of the given `length`.

        Scales `self.nominal_nsegs` (the segment count for a reference-length
        wire) by `length / ref`, so longer wires get proportionally more
        segments and the segment length stays roughly constant. `ref` is
        usually a quarter-wavelength; the count is clipped at 1 (issue #457
        — the old floor of 3 defeated the constant-segment-length goal on
        short wires, and on short *fat* wires could push the segment length
        below the wire radius, outside thin-wire-kernel validity). A fed
        wire's count is still parity-coerced at solve time, so the delta
        gap always has a middle segment to land on; since issue #450 an
        unfed wire keeps this count verbatim.

        Parity is intentionally NOT forced here. Each solver wants a particular
        segment parity so the feed lands on (or symmetrically across) the
        center — sinusoidal, B-spline degree-2 and PyNEC want odd; B-spline
        degree-1 wants even — and every engine coerces each count to its own
        parity at solve time (`SimulationEngine.coerce_n_seg`). Returning the
        natural count and letting the solver round is why this is `segs_for`,
        not the old `odd_nsegs`: baking in odd here would just make an
        even-parity solve bump the count up by one."""
        return max(1, round(self.nominal_nsegs * length / ref))

    def auto_mesh(self, tups):
        """Resolve ``None`` segment counts to the design density:
        ``nominal_nsegs`` segments per quarter-wavelength at
        ``design_freq``.

        The recurring catalog defect class (#481 radials, #484 folded/fan,
        #521/#522 hentenna/hourglass/moxon, the trap-wire study) is a
        builder hand-assigning per-wire counts that leave one wire's
        segment length out of step with its junction partners — either a
        short wire carrying the full nominal count (over-dense: Δ/a
        breakdown, tip-gap poisoning) or a fixed count that the rest of
        the mesh refines past (a graded junction that worsens with N, and
        a frozen discretization that biases even the Galerkin bases).
        This helper removes the arithmetic: mark a wire's count ``None``
        and it meshes at the design density; every ``None`` wire in every
        design gets the same segment length for the same N.

        The rules, deliberately per-wire with no interactions:

        * ``None`` -- the wire gets ``max(1, round(N * L / (lambda/4)))``
          segments, lambda from ``design_freq``. The measurement ``freq``
          plays no part, so sweeping it never remeshes the geometry.
        * ``None`` on a wire below the z = 0 interface -- same rule, but
          against the IN-MEDIUM wavelength (:attr:`design_medium_wavelength`),
          which is shorter by ``|n|``. Only for designs declaring
          ``design_eps_r``/``design_sigma``; without them every wire meshes
          against free space as before. A buried wire meshed against lambda_0
          is under-resolved by exactly the refractive index the free-space
          mesher never knew about -- ~4.3x at eps_r 13 / sigma 0.005 / 7 MHz
          (issue #983). The soil is DECLARED, not read from the solve-time
          ground, so sweeping ``--ground`` never remeshes either.
        * an int — taken verbatim. This is the legacy path (builders may
          still compute counts with ``segs_for``); it is allowed but not
          recommended — the catalog lint polices the outcome either way.

        ``nominal_nsegs`` thereby becomes a physical density: N=15 means
        a segment length of lambda/60 on every design that uses it, and
        mesh ladders are comparable across designs. Designs must declare
        ``design_freq`` (the frequency the geometry is designed for) to
        use ``None`` counts — a design without one raises here rather
        than silently guessing a scale.

        Builders never need to call this: ``__init_subclass__`` wraps
        every subclass's ``build_wires`` so its result passes through
        here automatically. Calling it explicitly is harmless (the
        resolution is idempotent)."""
        import math as _math

        tups = list(tups)
        if all(t[2] is not None for t in tups):
            return tups
        design_freq = getattr(self, "design_freq", None)
        if not design_freq:
            raise ValueError(
                f"{type(self).__name__}: auto_mesh needs a design_freq "
                "param to define the mesh density (nominal_nsegs segments "
                "per quarter-wavelength); declare one in default_params "
                "or give every wire an explicit segment count."
            )
        quarter_wave = 0.25 * C_LIGHT_MHZ_M / float(design_freq)
        # Below the interface the wave is shorter by |n|, so the same
        # nominal_nsegs-per-quarter-wave density needs a different reference
        # there (issue #983). None when the design declares no soil: every
        # wire then meshes against free space, as it always has.
        lam_m = self.design_medium_wavelength
        quarter_wave_below = None if lam_m is None else 0.25 * lam_m

        def _is_below(t):
            """True if any of this wire lies under the z = 0 interface.

            A wire that STRADDLES the interface counts as below and meshes
            at the denser in-medium reference over its whole length: the
            buried part is what the free-space reference under-resolves, and
            splitting the count mid-wire is not something a single ``n_seg``
            can express. Denser than needed above the interface is the safe
            direction, and the straddling wires in this catalog are short
            interface-adjacent rises where that costs a segment or two.
            """
            return min(t[0][2], t[1][2]) < 0.0

        def resolve(t):
            if t[2] is not None:
                return t
            ref = quarter_wave
            if quarter_wave_below is not None and _is_below(t):
                ref = quarter_wave_below
            n = self.segs_for(_math.dist(t[0], t[1]), ref)
            if isinstance(t, Wire):
                return t._replace(n_seg=n)
            return (t[0], t[1], n, *t[3:])

        return [resolve(t) for t in tups]

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


def _shift_entry(t, yoff, zoff, new_ex):
    """Translate one ``build_wires()`` entry by (0, yoff, zoff) for array
    placement, replacing a non-None excitation with ``new_ex(old_ex)``
    (each array builder has its own replace-vs-multiply phasor convention,
    so the policy comes in as a callable). Preserves the entry's shape:
    plain 4/5-tuples stay plain, ``Wire`` entries keep ``name`` and
    ``spec`` untouched — per-wire specs ride through array placement and
    are never scaled (issue #388: a spec is physical wire stock, not
    geometry)."""
    w = as_wire(t)
    (x0, y0, z0), (x1, y1, z1) = w.p0, w.p1
    moved = w._replace(
        p0=(x0, y0 + yoff, z0 + zoff),
        p1=(x1, y1 + yoff, z1 + zoff),
        ex=new_ex(w.ex) if w.ex is not None else w.ex,
    )
    if isinstance(t, Wire) or len(t) == 6:
        return moved
    return tuple(moved)[: len(t)]


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
                # 2x2 convention: the element's drive is REPLACED by the
                # array phasor (unit magnitude), not multiplied.
                new_tups.extend(
                    _shift_entry(t, yoff, zoff, lambda ex, p=ph0 * ph1: p) for t in tups
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
                    _shift_entry(t, yoff, zoff, lambda ex, p=ph_lr * ph_tb: p * ex)
                    for t in tups
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
                    _shift_entry(t, yoff, zoff, lambda ex, p=ph_lr: p * ex)
                    for t in tups
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
                    _shift_entry(t, yoff, zoff, lambda ex, p=ph_lr: p * ex)
                    for t in tups
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
            # 1x2 convention: like the 2x2, the drive is REPLACED by the
            # array phasor. No z offset (see the comment above).
            new_tups.extend(
                _shift_entry(t, yoff, 0.0, lambda ex, p=ph0: p) for t in tups_top
            )

        return new_tups
