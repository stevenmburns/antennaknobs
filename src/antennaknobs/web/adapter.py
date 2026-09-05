"""Bridge antennaknobs's Builder idiom into momwire's web AntennaExample.

Each `designs/<name>.py` exposes a `Builder` class with `default_params`
(a MappingProxyType of physics knobs). We walk that registry, derive a
`ParamSpec` schema from `default_params` (with optional per-design
overrides under the reserved `ui_params` key), and register one
`AntennaExample` per design so the existing momwire web frontend can
drive it without per-design glue.

Reserved keys inside `ui_params`:
  default_view     : "xy" | "yz" | "xz"  — initial 2D projection
  target_z0        : float — reference impedance for SWR (default 50)
  meas_freq_range  : (lo, hi)  — measurement-freq slider span override
  bands            : tuple[BandSpec] — band tabs (default amateur set, 160m–70cm)
  sweep_policy     : (anchor, lo_factor, hi_factor)
  multi_feed       : bool — declare multi-feed response shape
  notes            : str — informational note shown under the antenna
                     selector (deck-backed designs fill it from
                     NecDeck.skipped_note() to list the cards the import
                     recorded but did not apply)
  ground_requirement : "sommerfeld" — the design only means anything under
                     that ground model (the buried-wire designs); the
                     frontend auto-selects finite ground + the Sommerfeld
                     method on load and notes it in the ground panel
                     instead of letting the default refl-coef method hit
                     the solver's by-name refusal
  budget_labels    : dict {structural_label: display_label} — display
                     renames for power-budget rows (issue #489). Keys are
                     the STRUCTURAL labels the solver emits ("unun:
                     Transformer pri→ant (mag)", "TL rig→pri"); values
                     are what the UI shows ("unun core (mag)",
                     "feedline"). Exact-match only, unmatched rows pass
                     through unchanged — the mapping can retitle rows but
                     never hide one. Tests keep pinning the structural
                     labels; this is presentation only.
  layout           : dict {columns: int} — pin the knob grid to a fixed
                     column count so per-param `layout` col positions are
                     stable (default: responsive auto-flow packing)
  <param_name>     : dict of {min, max, step, unit, label, precision,
                              kind, sweepable, enum_options, layout, hidden}
                     — slider-bounds + metadata overrides for one param.
                     `layout` is {row, col, row_span, col_span} (1-indexed
                     CSS grid lines, all optional) to place this knob
                     explicitly. `hidden: True` suppresses the control
                     entirely (the param stays pinned at its default value
                     through solves) — for a knob that's degenerate with
                     another. Anything missing falls back to auto-derived
                     defaults.

Everything else in `default_params` becomes a `ParamSpec`. Numeric
defaults become float sliders with auto bounds (±50% around default);
ints become int sliders; bools become checkboxes; complex defaults are
skipped (no UI yet — the request can still override via re/im dict).
"""

from __future__ import annotations

import importlib
import logging
import math
import os
import pathlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, NamedTuple

import numpy as np

from antennaknobs.builder import (
    Array1x2Builder,
    Array1x4Builder,
    Array1x4GroupedBuilder,
    Array2x2Builder,
    Array2x4Builder,
    diff_params,
    resolve_variant_params,
)
from antennaknobs.network import PortAtEnd, PortAtVertex, as_wire

try:
    from antennaknobs.engines.pynec import DEFAULT_GROUND, PyNECEngine
except ImportError:
    PyNECEngine = None
    DEFAULT_GROUND = ("finite", 10.0, 0.002)
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.nec5 import NEC5Engine
from antennaknobs.terrain import (
    Terrain,
    cliff_terrain,
    hillside_terrain,
    levee_terrain,
)
from momwire import (
    ArrayBlockSolver,
    BSplineSolver,
    HMatrixSolver,
    RazorSolver,
    SinusoidalGalerkinSolver,
    SinusoidalSolver,
)

from ..geometry import flat_wires_to_polylines
from .examples import register
from .examples._base import (
    DEFAULT_AMATEUR_BANDS,
    DEFAULT_SWEEP_POLICY,
    AntennaExample,
    BandSpec,
    ParamGroupSpec,
    ParamSpec,
    ResultFieldSpec,
    SweepPolicy,
)

C_LIGHT = 299_792_458.0

_logger = logging.getLogger(__name__)

# Sentinel impedance for an open-circuited feed on the wire protocol. The
# network core reports a true open (e.g. a series matchbox capacitor slider
# at 0 F) as Z = inf (issue #289), but JSON has no Infinity/NaN — json.dumps
# would emit literals the browser's JSON.parse rejects, killing the whole
# solve/sweep response. Clamp to this huge-but-finite value instead: |Γ|
# lands at ~1−1e−7 so the SWR readout shows ∞, the Smith chart pins at the
# open point, and the R/X readout renders it as "∞ (open)" (the frontend
# treats ≥1e8 Ω as open).
Z_OPEN_OHMS = 1.0e9


def _json_safe_z(z: complex) -> complex:
    """Clamp a non-finite impedance to the open-circuit sentinel."""
    z = complex(z)
    if math.isfinite(z.real) and math.isfinite(z.imag):
        return z
    return complex(Z_OPEN_OHMS, 0.0)


DESIGNS_PKG = "antennaknobs.designs"
# Resolve the designs directory from the installed package, never a path relative
# to this file: web/ and src/antennaknobs/ are siblings in a source checkout, but
# once installed from a wheel they are separate top-level packages with no `src/`
# in between. __path__ points at the real location in both layouts.
DESIGNS_DIR = pathlib.Path(importlib.import_module(DESIGNS_PKG).__path__[0])

# Memory budget (MB) for momwire's batched frequency sweeps, injected into
# the bspline-family solvers' `swept_mem_mb` kwarg (momwire >= 0.9). None
# (unset) leaves momwire's default (256 MB) — appropriate for local use;
# the hosted fly.toml sets ANTENNAKNOBS_SWEPT_MEM_MB=64 so two concurrent
# worst-case sweeps stay well inside the 2 GB VM. Read at import, like the
# server's ANTENNAKNOBS_MAX_BASIS caps.
_SWEPT_MEM_MB = (
    int(os.environ["ANTENNAKNOBS_SWEPT_MEM_MB"])
    if os.environ.get("ANTENNAKNOBS_SWEPT_MEM_MB")
    else None
)

# ---------------------------------------------------------------------------
# Backend registry (issue #628)
# ---------------------------------------------------------------------------

# The solver roster is ONE structure: the class the server constructs plus the
# metadata the frontend renders its picker from. Before #628 the two halves
# lived in different languages (this dict here, a hand-kept `BACKEND_ORDER` /
# `BACKEND_LABEL` / `BackendOptsMap` in lib/backends.ts) and the failure mode of
# drift was silent absence — sinusoidal-galerkin landed server-side with both
# repos' CI green and no tab in the UI (#626/#627). Now GET /capabilities serves
# this list and the frontend has no roster of its own, so registering a solver
# here is the whole change.


@dataclass(frozen=True)
class _BackendOption:
    """One generic numeric solver knob the frontend renders from the roster.

    `key` is BOTH the client-side opts key and the snake_case constructor
    kwarg on the wire — one name, so a served knob cannot land under the
    wrong wire key. [min, max] must sit inside the hosted sanitiser's range
    for that kwarg (_HOSTED_MODEL_OPTIONS below); pinned by a test.
    """

    key: str
    label: str
    min: float
    max: float
    step: float
    default: float


@dataclass(frozen=True)
class _BackendSpec:
    name: str
    label: str
    # The momwire solver class, or None for the PyNEC entry — PyNEC rides the
    # separate `solver: "pynec"` request field, never `momwire_model`.
    solver: type | None
    kind: str = "momwire"
    supports_ground: bool = True
    options: tuple[_BackendOption, ...] = ()
    # Bespoke frontend panel for the knobs no generic numeric renderer can
    # carry (degree tabs, checkbox-gated smoothing, the feed-model tablist).
    # A name, not a backend check: the component is selected by this hint.
    panel: str | None = None
    # Interactive default for the client-side segments/wire knob.
    default_n_per_wire: int = 30
    # comboInappropriate policy, as capabilities rather than name lists:
    # `accelerator` = built for arrays (overkill on one element), and
    # `dense_family` = minutes per solve on a benchmark-class mesh.
    accelerator: bool = False
    dense_family: bool = False
    # Constructor kwargs this roster entry BINDS, the shape momwire's own deck
    # roster and antennaknobs' CLI variants already use (class + kwargs). They
    # are applied after the request's model_options and win over them, so a
    # bound lane cannot be flipped into a different one from the wire.
    bound: Mapping[str, object] = field(default_factory=dict)
    # Which of `_OPTION_SPECS` this backend EXPOSES (antennaknobs#1006 G2-6).
    #
    # "ACCEPTS" AND "EXPOSES" ARE DIFFERENT FACTS AND THIS FIELD IS THE
    # SECOND ONE. What a constructor accepts is measurable — construct it and
    # see. What the product offers is a DECISION, and it used to be encoded by
    # the `panel` hint. This field is the decision; the `panel` hint is what it
    # replaces.
    #
    # The distinction is not academic. `BSplineSolver` accepts `feed_model`
    # and its `feed_model` axis holds only "segment-gap", so the panel has
    # never offered or sent it. `SinusoidalSolver` accepts it too and REFUSES
    # the value "point" (momwire#212) — which is the served default — so a
    # roster built from what the class accepts would have sent a point gap to
    # the one solver that raises on it, on every stock request. `RazorSolver`
    # accepts `degree` and `n_qp_source` and has never shown either.
    #
    # GATED AS `exposed ⊆ accepted`, by construction, in
    # tests/test_backend_model_kwargs_1006.py: every exposed kwarg must be
    # constructible on this class, so the product can never offer a knob the
    # engine rejects. The reverse is deliberately NOT gated — requiring
    # accepted ⊆ exposed would assert a product decision as if it were a fact
    # about the class, which is precisely the error that produced the
    # `feed_model` bug above.
    #
    # `inspect.signature` cannot measure the "accepted" half either:
    # `HMatrixSolver` reports NO keyword arguments and takes the full B-spline
    # set through `**kwargs`, and `SinusoidalGalerkinSolver` reports only
    # `feed_model` while plainly accepting `extended_kernel`. Construct it.
    model_kwargs: tuple[str, ...] = ()


_N_QP_CONST = _BackendOption(
    key="n_qp_const",
    label="n_qp_const (GL pts)",
    min=2,
    max=32,
    step=1,
    default=8,
)

# The constructor kwargs each family takes, MEASURED by construction (see
# `_BackendSpec.model_kwargs`). Shared tuples because the families genuinely
# share a constructor surface — bspline/hmatrix/arrayblock are one class and
# two accelerated subclasses — so a per-entry literal would be three copies
# that drift apart.
#
# The one asymmetry worth noticing: `n_qp_const` is the sinusoidal family's
# and NOT the b-spline family's, while everything else runs the other way.
# That is not an oversight — the two families quadrature differently, and it
# is exactly the kind of fact the `panel` hint could not express, since it
# named a panel rather than a set of knobs.
# EXPOSED, not accepted — see `_BackendSpec.model_kwargs`. These lists
# reproduce the request payloads the bespoke panels produced, which is what
# makes the renderer swap a refactor rather than a behaviour change.
#
# THE ORDER IS THE WIRE ORDER, and it is the panels' emission order rather
# than alphabetical for exactly one reason: it makes the serialized request
# BYTE-IDENTICAL to the pre-refactor one, so the equivalence fixture can
# compare bytes instead of parsed objects. JSON key order carries no meaning
# to the server — these are constructor kwargs — so this ordering is a
# testing affordance, not a contract, and it can be re-sorted freely once
# that fixture is retired.
#
# `feed_model` is exposed by the GALERKIN member only: the point-matched
# `SinusoidalSolver` refuses the point gap (momwire#212), so exposing it there
# would offer — and default to — a value that raises.
_SIN_KWARGS = ("n_qp_const", "extended_kernel")
_SIN_GALERKIN_KWARGS = ("n_qp_const", "feed_model", "extended_kernel")
_BSPLINE_FAMILY_KWARGS = (
    "degree",
    # EXPOSED as of momwire#891 + Steve's decision. The row used to declare
    # only the segment gap while the constructor defaulted to the POINT gap —
    # so the family had a feed model it could not be asked about, and the
    # composition line said the wrong one. Now the axis is honestly
    # multi-valued and the choice is offered.
    #
    # The request payload therefore GAINS `feed_model` for these three
    # backends. That is a deliberate wire change, and it does not move any
    # number: "point" was already the solver's default, so the stock request
    # now states explicitly what it was getting implicitly.
    "feed_model",
    "n_qp_pair",
    "n_qp_source",
    "feed_smoothing_factor",
    "use_singular_enrichment",
    "enrichment_variant",
    "tikhonov_lambda",
    "auto_tap_ratio_threshold",
    "n_qp_sing",
    "enrichment_min_k",
    "extended_kernel",
)
# `degree` and `n_qp_source` are ACCEPTED here and have never been offered:
# the basis axis is ("tent",), and the razor panel has only ever shown the
# kernel toggle. Exposing either would change the request payload.
_RAZOR_KWARGS = ("extended_kernel",)


_BACKENDS: tuple[_BackendSpec, ...] = (
    _BackendSpec(
        name="sinusoidal",
        model_kwargs=_SIN_KWARGS,
        label="Sinusoidal",
        solver=SinusoidalSolver,
        options=(_N_QP_CONST,),
    ),
    # The same three-term basis as "sinusoidal", tested variationally rather
    # than point-matched (momwire#182). Not the interactive default — no C++
    # accelerator and no distributed wire loading, and the fill costs several
    # times the point-matched one — but a first-class backend tab, and the one
    # solver carrying the feed-model choice ("NEC-compatible vs converged",
    # issue #640), which is what its bespoke panel renders.
    _BackendSpec(
        name="sinusoidal-galerkin",
        model_kwargs=_SIN_GALERKIN_KWARGS,
        label="Sin-Galerkin",
        solver=SinusoidalGalerkinSolver,
        options=(_N_QP_CONST,),
        panel="sin-galerkin",
        dense_family=True,
    ),
    _BackendSpec(
        name="bspline",
        model_kwargs=_BSPLINE_FAMILY_KWARGS,
        label="B-spline",
        solver=BSplineSolver,
        panel="bspline",
        dense_family=True,
    ),
    # Hierarchical (H-matrix / ACA) accelerator — same B-spline basis as
    # bspline; model_options forward verbatim (degree, aca_eta,
    # aca_leaf_size, aca_tol, solve_tol, …). Only singular enrichment falls
    # back to the dense bspline solve inside HMatrixSolver
    # (`_hmatrix_unsupported`); every ground model — PEC image, reflection
    # coefficient, Sommerfeld — rides the accelerated path (measured, #830).
    _BackendSpec(
        name="hmatrix",
        model_kwargs=_BSPLINE_FAMILY_KWARGS,
        label="H-matrix (ACA)",
        solver=HMatrixSolver,
        panel="bspline",
        accelerator=True,
        dense_family=True,
    ),
    # Element-aware array-block accelerator (sibling of hmatrix) for arrays of
    # identical/few-shape elements: dense per-shape self-blocks + low-rank
    # coupling, block-Jacobi GMRES. Same B-spline basis and model_options as
    # bspline/hmatrix (degree, aca_tol, solve_tol, …); on a single connected
    # structure it degrades to one element and matches the dense bspline solve.
    # 21 segs/wire is the converged, correct-parity default for B-spline d=2
    # (odd → interior knot at the feed).
    _BackendSpec(
        name="arrayblock",
        model_kwargs=_BSPLINE_FAMILY_KWARGS,
        label="Array-block",
        solver=ArrayBlockSolver,
        panel="bspline",
        default_n_per_wire=21,
        accelerator=True,
        dense_family=True,
    ),
    # Tent basis tested by NEC-5's razor-blade (mixed-potential) rule rather
    # than point-matched or Galerkin (momwire#309/#432), with the two-point
    # centroid trapezoid momwire#316 identified for the testing-path integral.
    #
    # ONLY THE TWO-POINT LANE IS OFFERED HERE. `RazorSolver`'s other lane takes
    # `n_qp_path` Gauss-Legendre nodes per wing instead, and momwire renamed
    # these `razor` (GL) and `razor-2p` so the names describe the rule. Measured
    # on the ByDipole1 ladder, the GL rule's advantage over this one evaporates
    # by N~192 -- the two agree within 3% of each other's self-convergence at
    # N=384, having been 2x apart at N=12 -- while costing ~10x the wall time
    # (momwire#780). A knob that buys nothing on any mesh a person would sit
    # and wait for is not a knob; the GL lane is off the CLI roster too
    # (momwire#753, 2026-09-02) and reached only via the constructor, for
    # convergence work.
    #
    # `bound` rather than a served option for the same reason: `n_qp_path` is
    # IGNORED under this rule (momwire's own docstring says so), so exposing it
    # would render an inert control.
    #
    # Slower-converging than bspline, and honestly so: ~16x the mesh for the
    # same self-convergence on that ladder, which is why the default segment
    # count is higher than bspline's. Even, because a centre-fed deck wants a
    # knot at the feed for this basis.
    _BackendSpec(
        name="razor-2p",
        model_kwargs=_RAZOR_KWARGS,
        label="Razor (2-point)",
        solver=RazorSolver,
        default_n_per_wire=40,
        dense_family=True,
        bound={"nec5_quadrature": True},
    ),
    # Optional (needs pynec-accel): served only when HAVE_PYNEC, so the
    # frontend derives availability from roster membership instead of a
    # second flag (#429). `kind` — not the name — is what marks it as the
    # entry that rides `solver: "pynec"`.
    _BackendSpec(
        name="pynec",
        label="PyNEC",
        solver=None,
        kind="pynec",
        panel="pynec",
        default_n_per_wire=21,
    ),
    # Licensed, user-supplied binary (issue #825): served only when the
    # machine running the server resolves $NEC5_EXE. The hosted simulator
    # never defines it, so this entry cannot appear hosted (the #824 EULA's
    # no-SaaS term); on a personal machine it is the operator's own
    # licensed use. Same roster-membership availability contract as pynec.
    _BackendSpec(
        name="nec5",
        label="NEC-5",
        solver=None,
        kind="nec5",
        panel="nec5",
        default_n_per_wire=20,
    ),
)

_MOMWIRE_MODELS = {b.name: b.solver for b in _BACKENDS if b.kind == "momwire"}
_MOMWIRE_BOUND = {
    b.name: dict(b.bound) for b in _BACKENDS if b.kind == "momwire" and b.bound
}


def backend_roster(*, have_pynec: bool, have_nec5: bool = False) -> list[dict]:
    """The self-describing solver catalog served on GET /capabilities.

    Order is list order; the frontend renders its tabs, generic numeric knobs
    and ground gating straight from this, and selects its bespoke panels
    by the `panel` hint rather than by backend name. Computed per request so
    the PyNEC entry follows pynec_backend.HAVE_PYNEC and the NEC-5 entry
    follows the $NEC5_EXE binary probe.
    """
    availability = {"pynec": have_pynec, "nec5": have_nec5}
    return [
        {
            "name": b.name,
            "label": b.label,
            "kind": b.kind,
            "supports_ground": b.supports_ground,
            # Which knobs this backend's constructor takes (#1006 G2-6),
            # measured by construction. The SPECS for them are served once on
            # the capabilities payload rather than repeated per row — thirteen
            # descriptions copied across eight rows is the duplication this
            # unit exists to remove, not a new one to add.
            "model_kwargs": list(b.model_kwargs),
            # Axis -> the value this preset pins it to (#1006 G2-7).
            "bound_axes": _bound_axes(b),
            "options_schema": [
                {
                    "key": o.key,
                    "label": o.label,
                    "min": o.min,
                    "max": o.max,
                    "step": o.step,
                    "default": o.default,
                }
                for o in b.options
            ],
            "panel": b.panel,
            "default_n_per_wire": b.default_n_per_wire,
            "accelerator": b.accelerator,
            "dense_family": b.dense_family,
            "buried": _backend_serves_buried(b),
            # momwire's sentence for a backend that cannot (#1006 review);
            # AK's own measured sentence for AK's own wrappers (#1167).
            "buried_refusal": _backend_buried_refusal(b),
            # Which issue that sentence should cite (#1167). Served rather
            # than hardcoded in the frontend, where it named momwire#553 for
            # every backend including the ones momwire#553 says nothing about.
            "buried_issue": _backend_buried_issue(b),
            "axes": _backend_axes(b),
            "constraints": _backend_constraints(b),
            # The roster entry's bound kwargs, verbatim (antennaknobs#1006
            # G2-5). `axes` says what the CLASS can be configured to; `bound`
            # says what this PRESET pins, and the two must stay separable or
            # the class/preset distinction the unit exists to make is lost.
            #
            # The rule the panel derives from them: an axis is a CONTROL iff
            # it is multi-valued in `axes` AND not pinned by `bound` AND (on
            # the hosted instance) its kwarg is on the model-options
            # allowlist. `razor-2p` binds `nec5_quadrature`, so its quadrature
            # axis is fixed on a LOCAL install too — the preset is the reason,
            # not host policy.
            "bound": dict(b.bound),
        }
        for b in _BACKENDS
        if availability.get(b.kind, True)
    ]


def _backend_constraints(spec):
    """Which axis values this backend cannot combine, with momwire's reason —
    or None when that cannot be asked (antennaknobs#1006 G2-4b).

    The axes are NOT freely combinable, so a panel rendering them as
    independent controls would offer a user a combination momwire refuses.
    momwire#885 measured five such couplings and holds them as data, each
    carrying the prose its own refusal raises.

    FILTERED ON `applies_to`, NEVER ON VALUE REACHABILITY. A coupling belongs
    to the class that raises it. Filtering by "can this backend be configured
    to `value_a`" mis-attributes three of the six rows — it would tell a
    `bspline` user that the extended kernel forbids `near_correction=False`,
    a keyword `BSplineSolver` does not have (measured: TypeError, not a
    refusal). That mis-attribution is exactly why `applies_to` exists.

    Matched EXACTLY, not by subclass. `ArrayBlockSolver` inherits
    `HMatrixSolver`'s buried refusal but carries its own row, because the two
    rows exist precisely to say their solve strategies differ; an
    `issubclass` match would hand it both and undo that.

    Probed as a feature on `_backend_axes`' precedent: the pointer runs ahead
    of the PyPI pin, so momwire reports the same version with and without this
    table — it reported 0.47.0 both before and after the pointer move that
    brought it. None means "cannot be asked" and renders as *not described*,
    the same unknown state an undeclared row already gets.

    The two rows whose `forbids_axis` is a constructor keyword rather than an
    axis are served WITH their marker rather than dropped, so the frontend
    decides what to do about a constraint it cannot draw as a cell — that is a
    presentation choice and it does not belong in this seam.
    """
    if spec.kind != "momwire" or spec.solver is None:
        return None
    try:
        from momwire._couplings import COUPLINGS
    except ImportError:  # a momwire predating momwire#885
        return None
    name = spec.solver.__name__
    return [
        {
            "axis": c.axis_a,
            "value": c.value_a,
            "forbids_axis": c.axis_b,
            "forbids_value": c.value_b,
            "forbids_is_axis": c.b_is_axis,
            # Verbatim, and None for a flat refusal: "refused" and "refused
            # when X" are different sentences and collapsing them overstates
            # the first.
            "condition": c.condition,
            "reason": c.reason,
            "issue": c.issue,
        }
        for c in COUPLINGS
        if name in c.applies_to
    ]


def _backend_axes(spec):
    """What this backend is MADE OF — axis -> sorted values — or None when
    that cannot be asked (antennaknobs#1006 G2-3).

    momwire's rows say what a solver SERVES; `axes_for` adds what it IS, which
    is what lets a panel show that `bspline` and `hmatrix` differ in assembly
    alone and `sinusoidal-galerkin` differs from `sinusoidal` in the testing.
    Read THROUGH `axes_for` and never re-derived here: `ground_model` and
    `wire_position` are computed from `grounds` / `buried` / `contact` inside
    momwire, and a second implementation on this side is exactly the drift
    that module refuses to allow.

    PROBED AS A FEATURE, NEVER AS A VERSION, on `_backend_serves_buried`'s
    precedent and for a sharper reason than convention. The submodule pointer
    runs AHEAD of the PyPI pin by design — the pointer is what the tests run
    against, the pin is what users get — so momwire reports 0.47.0 both with
    and without `axes_for`, and a version check reads the same number in the
    two cases it has to tell apart. The hosted app pins 0.47.0 and has no
    `axes_for`; this box's pointer has it at the same version number.

    None means "this momwire cannot describe itself compositionally", which
    the frontend renders as *not described* — the same rendering an undeclared
    row already gets in momwire's generated matrix, so there is one unknown
    state to design for rather than two. Non-momwire backends answer None for
    the honest reason: PyNEC and NEC-5 have no momwire capability row at all,
    and their composition is their own wrapper's business.
    """
    if spec.kind != "momwire" or spec.solver is None:
        return None
    caps = getattr(spec.solver, "capabilities", None)
    if caps is None or "axes" not in getattr(caps, "_fields", ()):
        return None
    try:
        from momwire._capabilities import axes_for
    except ImportError:  # a momwire predating antennaknobs#1006 G2-1
        return None
    # frozenset is not JSON; sorted lists keep the payload stable so a
    # response fixture does not churn on set iteration order.
    return {axis: sorted(values) for axis, values in axes_for(caps).items()}


# The buried scope of AK's OWN wrappers — MEASURED, not asserted
# (antennaknobs#1167). One row per wrapper kind: (serves_buried, sentence,
# issue). A wrapper with no row answers None, which is still the honest
# "nobody has asked" — so absence is how "unmeasured" is spelled, and there
# is exactly one way to spell it.
#
# This table exists because the momwire path cannot serve these: `buried` is a
# momwire capability cell carrying momwire's own refusal prose, and AK's
# wrappers have no such cell. What replaces it is a measurement plus the test
# that pins it (tests/test_pynec_buried_scope_1167.py), which is what keeps
# the sentence below from being the docstring assertion it replaced.
_PYNEC_BURIED_REFUSAL = (
    "PyNEC cannot model a conductor below the ground plane. NEC-2's "
    "Sommerfeld-Norton ground is formulated for sources ABOVE the interface "
    "and has no below-interface case — and nec2++ does not refuse such a "
    "deck. It solves it, without warning, as though the wire were still in "
    "air, and returns a plausible-looking number. Measured "
    "(antennaknobs#1167) on this catalog's buried dipole: moving the wire "
    "from 5 cm above the interface to 5 cm below moves PyNEC's impedance by "
    "12%, where momwire's buried fill moves it by a factor of 10. Use a "
    "momwire backend for buried decks."
)

_WRAPPER_BURIED_SCOPE = {
    "pynec": (False, _PYNEC_BURIED_REFUSAL, "antennaknobs#1167"),
    # NEC-5 SERVES buried geometry, measured on the licensed binary
    # (antennaknobs#1025 / #1167), so its row carries no sentence and the
    # frontend renders nothing — the same shape as a momwire that serves.
    #
    # It earns the True by modelling the interface rather than by returning a
    # number: on `specialty.buried_dipole`, whose wire AND excitation are both
    # below the surface, it prints 146.39+44.38j / 138.32+53.89j /
    # 135.64+57.16j at 0.15 / 1 / 2 m down, tracking momwire to 0.15-0.27 % in
    # R. That depth dependence is the evidence — the same wrapper before #1025
    # printed 0.85j at ALL THREE depths, which is what an engine that is not
    # modelling the burial looks like, and is exactly the failure mode PyNEC
    # is marked False for.
    #
    # WHAT THE True DOES NOT SAY. There is no third state here, so read it as
    # "the wrapper models the buried medium", not as "every buried sub-class is
    # equally trustworthy". Measured scope, so nobody has to re-derive it:
    #
    #   wholly buried, fed below   validated to 0.15-0.27 % against momwire
    #   buried wires, fed above    serves; the one catalog deck of this shape
    #                              (elevated_buried_counterpoise) has |X|/R
    #                              ~1400, so its R is numerical noise and it
    #                              validates nothing in either direction
    #   CONTACT (a bonded end)     serves, with a caveat below
    #
    # The contact caveat: that class needs ground flag 1, because flag -1
    # leaves the current expansion alone and the binary then refuses the run
    # outright — "voltage source specified where there is no basis function",
    # which is the flag working as documented, there being no bonded node at
    # the plane for the source to excite. But flag 1 is documented as not
    # usable when wires go below the surface, and the contact class asks for
    # both at once. The binary runs the combination without complaint (its
    # checks are looser than its documentation, the same lesson as the
    # mid-span straddle), and the answer it gives sits ~35 % in R from
    # momwire. That gap was independently adjudicated as the interface-node
    # convention difference — NEC-5 reads nearly the same impedance with the
    # radials connected or detached — on antennaknobs#1025 and
    # momwire#524/#567/#838, so it is not this bug and not fixed by it. Treat
    # a contact-class NEC-5 buried number as unvalidated rather than wrong.
    "nec5": (True, None, None),
}


def _wrapper_buried_row(spec):
    """The measured buried row for one of AK's own wrappers, or None."""
    if spec.kind == "momwire":
        return None
    return _WRAPPER_BURIED_SCOPE.get(spec.kind)


def _backend_serves_buried(spec):
    """Whether this backend serves BURIED geometry: True, False, or None when
    the question cannot be asked (issue #1108, momwire#814).

    Three states and not two, on purpose. The buried designs are the one place
    in the catalog where a backend the roster offers can be structurally unable
    to answer, and the frontend needs to tell "this one cannot" from "nobody
    here knows yet" — a momwire predating the `buried` capability cell answers
    `refusal("buried")` with None, which reads as SERVED and is the one answer
    that must never be inferred (issue #1103's rule, and issue #966's trap in
    the engine before it).

    momwire backends answer from momwire's own capability row. AK's wrappers
    answer from `_WRAPPER_BURIED_SCOPE`, which is a measurement.

    This docstring used to assert that "PyNEC refuses a wire below z = 0
    outright; NEC-5 serves buried decks natively since issue #825's stage".
    Both halves were prose, and measuring them (antennaknobs#1167, #1025) found
    both wrong.

    PyNEC does not refuse a buried wire, it solves it wrongly and silently. The
    one place that wrapper does raise on a buried catalog deck is
    `buried_radial_vertical`, and that refusal is about the graded-mesh
    spelling, not depth — it fires on graded decks above ground too.

    NEC-5 did serve buried GEOMETRY, but not the class whose EXCITATION is also
    below the surface: it printed milliohms there, and printed the same
    milliohms at every depth. The cause was ours — the wrapper had the two
    fields of the GE card transposed — and it is fixed in #1025, which is what
    makes the True above a measurement rather than the same prose restated.

    An unmeasured docstring is exactly how a guess becomes a gate, and this one
    managed it twice in a single sentence.
    """
    if spec.kind != "momwire":
        row = _wrapper_buried_row(spec)
        return None if row is None else row[0]
    if spec.solver is None:
        return None
    caps = getattr(spec.solver, "capabilities", None)
    if caps is None or "buried" not in getattr(caps, "_fields", ()):
        return None
    return bool(caps.buried)


def _backend_buried_refusal(spec):
    """momwire's own sentence for why this backend cannot solve a buried deck.

    The BOOLEAN alone was not enough, which a review found the hard way: with
    the buried capability served but no prose, nothing downstream could gate
    on it without inventing a reason — so nothing gated on it at all, and
    `razor-2p` on a buried design solved, raised, and showed the user a
    traceback banner instead of a refusal.

    This is a SINGLE-CELL refusal, not a pairwise coupling: the solver has no
    buried fill at all, whatever else is set. `COUPLINGS` therefore does not
    and should not name it — the couplings answer "which combinations are
    refused", and this is "which decks this solver cannot take". Two different
    questions, and the gate needs both.

    For AK's own wrappers the sentence is AK's, not the engine's, because the
    engine has none to carry — PyNEC does not refuse a buried deck, it answers
    one wrongly. That makes the pinning test the sentence's warrant, which is
    a weaker provenance than momwire's carried prose and is worth knowing when
    reading it.
    """
    if spec.kind != "momwire":
        row = _wrapper_buried_row(spec)
        return None if row is None else row[1]
    if spec.solver is None:
        return None
    caps = getattr(spec.solver, "capabilities", None)
    if caps is None or "buried" not in getattr(caps, "_fields", ()):
        return None
    if caps.buried:
        return None
    refusal = caps.refusal("buried")
    return refusal if isinstance(refusal, str) else None


def _backend_buried_issue(spec):
    """Which issue a buried refusal should cite.

    The frontend renders this to the user beside the sentence. It used to be
    a literal `momwire#553` in `capabilityRefusal`, which was right while
    momwire was the only backend that could refuse a deck; pointing a PyNEC
    user at a momwire issue for a PyNEC limitation is the same class of error
    as inventing the reason itself, just quieter.
    """
    if spec.kind != "momwire":
        row = _wrapper_buried_row(spec)
        return None if row is None else row[2]
    return "momwire#553" if _backend_serves_buried(spec) is False else None


# ---------------------------------------------------------------------------
# model_options sanitisation (issue #346)
# ---------------------------------------------------------------------------

# Mirrors server.py's _HOSTED master switch: the whitelist below only applies
# on the shared instance; a local install forwards model_options verbatim.
_HOSTED = os.environ.get("ANTENNAKNOBS_HOSTED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _int_in(lo: int, hi: int):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
            raise ValueError("must be an integer")
        n = int(v)
        if not lo <= n <= hi:
            raise ValueError(f"must be in [{lo}, {hi}]")
        return n

    return check


def _float_in(lo: float, hi: float, *, allow_none: bool = False):
    def check(v):
        if v is None and allow_none:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("must be a number")
        f = float(v)
        if not (math.isfinite(f) and lo <= f <= hi):
            raise ValueError(f"must be a finite number in [{lo}, {hi}]")
        return f

    return check


def _bool_opt(v):
    if not isinstance(v, bool):
        raise ValueError("must be a boolean")
    return v


def _enum_opt(*allowed: str):
    def check(v):
        if v not in allowed:
            raise ValueError(f"must be one of {sorted(allowed)}")
        return v

    return check


# The solver kwargs the frontend's gear menus actually send (App.tsx
# modelOptionsForRequest), each with a sane range. When hosted, model_options
# is filtered to THESE keys — anything else (ACA leaf sizes, GMRES/solve
# tolerances, the server-owned swept_mem_mb, arbitrary constructor kwargs) is
# dropped, so a hand-crafted request can't amplify per-solve CPU beyond what
# the segment-count cap models.
# Keys whose null means "let the solver decide" rather than "use null". Only
# n_qp_pair today: momwire#863 made its default depend on whether the deck has
# wire below the interface, which is a question this layer cannot answer and
# must not pretend to.
_AUTO_WHEN_NULL: frozenset[str]  # derived from _OPTION_SPECS below


class _OptionSpec(NamedTuple):
    """One solver knob, described once — for the sanitiser AND the schema.

    Before antennaknobs#1006 G2-6 this was a dict of opaque closures, and
    everything a UI needed to RENDER a knob (its type, its range, its enum
    values, whether null means auto) existed only as free variables captured
    inside them. The frontend therefore hand-wrote all of it a second time,
    which is why `BackendConfigModal` had a bespoke panel per engine at all.

    Reading the closures back with `__closure__` was the obvious shortcut and
    is deliberately NOT what happens: it is introspection archaeology that
    breaks silently the first time a sanitiser is rewritten. Instead the spec
    is the source and `_sanitiser_for` DERIVES the check, so the two cannot
    disagree — there is nothing to keep in sync.

    `label`/`step` are UI copy. They live here rather than in the frontend
    because a generic renderer cannot invent them, and a per-engine table of
    them in the client is exactly the thing G2-6 removes.
    """

    kind: str  # "int" | "float" | "bool" | "enum"
    lo: float | None = None
    hi: float | None = None
    values: tuple[str, ...] = ()
    allow_none: bool = False
    # Null means "let the solver decide", not "send null". Carried as DATA
    # because antennaknobs#1064 is what happens when a caller decides instead:
    # a literal here is sent unconditionally and silently overrides momwire's
    # own per-deck default for every hosted solve. momwire#863 made that
    # default depend on whether the deck has wire below the interface — a
    # question this layer cannot answer and must not pretend to.
    auto_when_null: bool = False
    label: str = ""
    step: float = 1
    default: object = None
    # RENDER bounds, which are NOT the sanitiser's. `lo`/`hi` are what the
    # hosted endpoint ACCEPTS and are deliberately loose; these are what the
    # control OFFERS. `feed_smoothing_factor` is the case that forced the
    # split — the panel has always offered 0.5..10 step 0.5 while the
    # sanitiser accepts 0..100, and a renderer fed the sanitiser bounds would
    # widen that knob tenfold and change its step.
    #
    # None means "same as the sanitiser bound". Gated as a SUBSET of it
    # (test_option_specs_1006), because the one shape that must be impossible
    # is a control offering a value the server will reject: the user would see
    # an available knob and a failed solve.
    render_lo: float | None = None
    render_hi: float | None = None
    render_step: float | None = None
    # Caption for the checkbox that turns a nullable knob on (or to auto),
    # when it has one. Not derivable from `label`: the gates read
    # "n_qp_pair: auto" and "feed source smoothing" against labels of
    # "n_qp_pair (GL pts/axis)" and "α (bump width / h_feed)".
    #
    # The POLARITY is not stored because it falls out: `auto_when_null` means
    # checked-when-null ("auto"), `allow_none` alone means checked-when-set.
    gate_label: str | None = None
    # The value a gate switches the knob ON to. Not derivable and not the
    # spec default: `n_qp_pair`'s default IS null (auto), and unticking auto
    # has always pinned 8; `feed_smoothing_factor` switches on to 3 against a
    # render range starting at 0.5. Both are the panel's long-standing
    # choices, so they are recorded rather than re-invented.
    gate_on_value: float | None = None
    # When set, `shown_when` is satisfied only if that option EQUALS this,
    # rather than merely being truthy. Two knobs need it: `tikhonov_lambda`
    # appears only for the tikhonov variant and `auto_tap_ratio_threshold`
    # only for the auto one — a truthiness gate would show both for every
    # variant, which is two extra controls on the commonest setting.
    #
    # Gates CHAIN: these name `enrichment_variant`, which is itself gated on
    # `use_singular_enrichment`, so a renderer that resolves the gate
    # transitively gets the old panel's nesting for free and neither this
    # table nor the client needs a chain syntax.
    shown_when_value: str | None = None
    # Rendered only while this other option is TRUTHY — pure UI gating, not a
    # refusal. Truthy, not "is True": `n_qp_source` is shown only while
    # `feed_smoothing_factor` is a non-null number, so a gate naming a
    # boolean is the common case and not the rule.
    #
    # A genuine cross-axis refusal (the extended kernel vs singular
    # enrichment) is momwire's to state and reaches the client through the
    # served `constraints`, never through a field here: a refusal invented in
    # this table would be the retyped-prose failure momwire#888 is about.
    shown_when: str | None = None


def _sanitiser_for(name: str, spec: _OptionSpec):
    """The hosted validator for one spec — the ONLY place a check is built.

    Messages are preserved verbatim from the closures this replaced, because
    they are asserted character for character by the baseline fixture
    (tests/data/hosted_option_sanitiser_baseline.json).
    """
    if spec.kind == "bool":
        return _bool_opt
    if spec.kind == "enum":
        return _enum_opt(*spec.values)
    if spec.kind == "int":
        return _int_in(int(spec.lo), int(spec.hi))
    if spec.kind == "float":
        return _float_in(spec.lo, spec.hi, allow_none=spec.allow_none)
    raise AssertionError(f"{name}: unknown option kind {spec.kind!r}")


_OPTION_SPECS: dict[str, _OptionSpec] = {
    "degree": _OptionSpec("int", 1, 2, label="degree", default=2),
    "n_qp_const": _OptionSpec(
        "int",
        1,
        64,
        label="n_qp_const (GL pts)",
        default=8,
        render_lo=2,
        render_hi=32,
    ),
    # Capped at 32, and the bound is now a COST choice rather than a crash
    # guard. It used to be 8 because momwire's accelerated pair kernels carried
    # a fixed n_qp^2 <= 64 scratch buffer and raised RuntimeError above that
    # (_accel_bspline.cpp, six sites); momwire#769 routes past the ceiling to
    # numpy instead of raising and momwire#762 tiled the qr loop away entirely,
    # both released in momwire 0.46.0. Raising this ahead of that pin
    # re-introduces the crash of #1055 on the hosted deployment.
    #
    # Why 32 and not higher. The figures this comment used to carry (8 sitting
    # 3.12 ohm from converged, 32 closing it to 0.30) were measured on
    # `buried_radial_vertical`'s **bundle** variant, the coincident-rise
    # spelling antennaknobs#1108 retired; the shipped hub is 0.17 ohm at 8 and
    # 0.0047 at 32 — a factor of 18 apart, so the old text overstated the knob
    # by that much. It also called the class "C/q, first order", which
    # momwire#760 closed as wrong: the error is superalgebraic (hub q^-3.11,
    # bundle q^-1.78), a large constant rather than a lost rate. Raising the
    # order is cheap on these decks (momwire#778), 32 is on the plateau for
    # every spelling that ships, and 64 is what the retired bundle would want.
    # Hosted is a public endpoint, so SOME bound stays: this is a raise, not a
    # removal. Since momwire#863 the usual case is that this key is ABSENT.
    "n_qp_pair": _OptionSpec(
        "int",
        1,
        32,
        auto_when_null=True,
        label="n_qp_pair (GL pts/axis)",
        default=None,
        render_lo=2,
        gate_label="n_qp_pair: auto",
        gate_on_value=8,
    ),
    "n_qp_source": _OptionSpec(
        "int",
        1,
        64,
        label="n_qp_source",
        default=16,
        render_lo=4,
        # The gate that widened `shown_when` past booleans: this knob is only
        # meaningful while the smoothed source is on, and that switch is a
        # nullable float rather than a flag.
        shown_when="feed_smoothing_factor",
    ),
    "n_qp_sing": _OptionSpec(
        "int",
        1,
        128,
        label="n_qp_sing (GL pts/axis)",
        default=32,
        render_lo=8,
        render_hi=64,
        shown_when="use_singular_enrichment",
    ),
    "feed_smoothing_factor": _OptionSpec(
        "float",
        0.0,
        100.0,
        allow_none=True,
        label="\u03b1 (bump width / h_feed)",
        step=0.1,
        default=None,
        # The panel has always offered a far narrower range than the
        # sanitiser accepts; 3 is what the gate switches on to.
        render_lo=0.5,
        render_hi=10.0,
        render_step=0.5,
        gate_label="feed source smoothing",
        gate_on_value=3,
    ),
    # Gap-source model on the solvers that offer it (momwire#192/#216):
    # "segment" is NEC's segment-wide gap, "point" the zero-width (converged)
    # gap. The UI words this "NEC-compatible vs converged" (issue #640). The
    # point-matched SinusoidalSolver refuses "point" with its own instructive
    # error (momwire#212), so no per-solver filtering is needed here.
    "feed_model": _OptionSpec(
        "enum", values=("segment", "point"), label="feed model", default="point"
    ),
    "use_singular_enrichment": _OptionSpec(
        # The panel's own caption, character for character — the equivalence
        # fixture compares captions, and "singular enrichment" would be a
        # quietly renamed control rather than the same one.
        "bool",
        label="K\u22653 junction singular enrichment",
        default=False,
    ),
    "enrichment_variant": _OptionSpec(
        "enum",
        values=("raw", "stable", "tikhonov", "auto"),
        label="variant:",
        default="raw",
        shown_when="use_singular_enrichment",
    ),
    "tikhonov_lambda": _OptionSpec(
        "float",
        0.0,
        1e3,
        label="tikhonov_lambda (\u03bb)",
        step=0.01,
        default=0.1,
        render_hi=10.0,
        render_step=0.05,
        # Gated on the VARIANT, which is itself gated on the enrichment
        # flag — the chain resolves transitively in the renderer, so neither
        # this table nor the client needs a chain syntax.
        shown_when="enrichment_variant",
        shown_when_value="tikhonov",
    ),
    "auto_tap_ratio_threshold": _OptionSpec(
        "float",
        0.0,
        1.0,
        label="auto_tap_ratio_threshold",
        step=0.05,
        default=0.3,
        shown_when="enrichment_variant",
        shown_when_value="auto",
    ),
    "enrichment_min_k": _OptionSpec(
        "int",
        2,
        64,
        label="enrichment_min_k",
        default=3,
        render_hi=6,
        shown_when="use_singular_enrichment",
    ),
    # NEC's extended thin-wire kernel (the EK card, issue #849, momwire >=
    # 0.26.0). A physics selection like feed_model, not a compute-
    # amplification lever, so it belongs on the hosted allowlist.
    # `_make_momwire_engine` pulls it back out and passes it as the named
    # `extended_kernel=` constructor kwarg rather than leaving it here —
    # MomwireEngine folds either spelling the same way (issue #849's
    # engine-side note), but the named kwarg keeps the adapter's intent
    # explicit and is what unit 1 documented at this call site.
    "extended_kernel": _OptionSpec("bool", label="extended kernel (EK)", default=False),
}

# Derived, never written twice. Same name and same shape as the dict of
# closures this replaced, so every existing call site is untouched.
_HOSTED_MODEL_OPTIONS = {
    k: _sanitiser_for(k, spec) for k, spec in _OPTION_SPECS.items()
}


def sanitize_model_options(req: dict) -> dict | None:
    """Validated solver kwargs from the request's ``model_options``.

    Everywhere: a non-dict value raises a clean ValueError instead of a
    TypeError deep inside a solver constructor. When hosted, additionally
    filters to the whitelisted keys above (unknown keys are dropped, not
    forwarded) and validates each value's type/range. Local instances keep
    verbatim forwarding — solver experiments stay unlocked.
    """
    raw = req.get("model_options")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("model_options must be an object of solver keyword arguments")
    # "auto": drop the key entirely rather than forwarding a null or
    # substituting a number. Dropped on BOTH paths, including the verbatim
    # local one, because a literal `None` reaching a momwire older than #863
    # is a TypeError in the constructor, and because choosing a value here is
    # exactly the override antennaknobs#1064 is about — the rule is geometric
    # and it is momwire's to apply, not ours.
    raw = {k: v for k, v in raw.items() if not (v is None and k in _AUTO_WHEN_NULL)}
    if not _HOSTED:
        return dict(raw) or None
    out = {}
    for k, v in raw.items():
        check = _HOSTED_MODEL_OPTIONS.get(k)
        if check is None:
            continue
        try:
            out[k] = check(v)
        except ValueError as e:
            raise ValueError(f"model_options.{k} {e}") from None
    return out or None


def _positive_finite(name: str, value) -> float:
    """Validate a client-supplied physics scalar: a number, finite, > 0.

    Client JSON reaches the solvers unvalidated and stdlib json.loads accepts
    NaN/Infinity literals, so this is the physics boundary's input check
    (issue #347): a zero frequency divides C_LIGHT by zero, a zero wire
    radius makes the MoM log-kernel singular, and non-finite values poison
    the matrices with an opaque solver error.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number (got {value!r})") from None
    if not math.isfinite(v) or v <= 0.0:
        raise ValueError(f"{name} must be a positive, finite number (got {value!r})")
    return v


# ---------------------------------------------------------------------------
# Schema derivation
# ---------------------------------------------------------------------------


def _strip_ui(params: dict) -> dict:
    """Return a copy of the params dict with the reserved `ui_params` key
    removed — what gets passed into Builder construction."""
    return {k: v for k, v in params.items() if k != "ui_params"}


def _nice_step(raw: float) -> float:
    """Snap a raw step to the 1-2-5 series (… 0.001, 0.002, 0.005, 0.01 …)
    so auto-derived sliders advance in familiar increments instead of odd
    grids like 0.003 or 0.0007. Picks the nearest 1/2/5·10ⁿ using the
    conventional log-spaced thresholds (1.5, 3, 7)."""
    if raw <= 0.0:
        return raw
    exp = math.floor(math.log10(raw))
    mant = raw / 10.0**exp  # in [1, 10)
    nice = 1.0 if mant < 1.5 else 2.0 if mant < 3.0 else 5.0 if mant < 7.0 else 10.0
    return nice * 10.0**exp


def _precision_for_step(step: float) -> int:
    """Decimal places to display a value stepped by `step`, with one digit
    of headroom so an off-grid default still reads meaningfully. Capped at
    6 to keep labels sane for very small factors."""
    if step <= 0.0:
        return 3
    return min(6, max(0, -math.floor(math.log10(step))) + 1)


def _is_degree_param(name: str) -> bool:
    """True for the standardized angle params (keys carry a `_deg` token,
    e.g. `angle_deg`, `slant_deg`, `angle_deg_itop`, `gap_angle_deg`)."""
    return name.endswith("_deg") or "_deg_" in name


def _display_label(name: str) -> str:
    """Default knob label for a param key. Angle params drop the redundant
    `_deg` token (the degree unit is shown on the slider instead), so
    `angle_deg_itop` reads as `angle_itop` and the panel stays compact. The
    underlying param *name* is unchanged — the frontend surfaces it via the
    knob tooltip so the displayed and program names never silently diverge."""
    if _is_degree_param(name):
        return name.replace("_deg_", "_").removesuffix("_deg")
    return name


def _auto_paramspec(name: str, default: Any, override: dict | None) -> ParamSpec | None:
    """Build a ParamSpec from a default value plus optional UI overrides.

    Returns None when the value type has no UI representation (complex,
    string-non-enum, etc.) and no override was supplied — the param is
    still settable via the API, it just doesn't appear in the UI.
    """
    override = dict(override or {})
    label = override.pop("label", _display_label(name))
    unit = override.pop("unit", None)
    # Optional explicit grid placement for this knob (row/col/spans). Only a
    # dict is meaningful; anything else is ignored so a typo can't crash the
    # registry. Passed verbatim to ParamSpec.layout for every kind.
    layout_raw = override.pop("layout", None)
    layout = dict(layout_raw) if isinstance(layout_raw, dict) else None
    # Precision (decimal places shown on the slider label) defaults to None
    # here so the numeric branch can derive it from the resolved step. Any
    # non-numeric path falls back to 3, matching the historical default.
    explicit_precision = override.pop("precision", None)
    precision = 3 if explicit_precision is None else int(explicit_precision)
    sweepable = bool(override.pop("sweepable", name == "freq"))

    if isinstance(default, bool):
        kind = override.pop("kind", "bool")
        return ParamSpec(
            name=name,
            label=label,
            default=default,
            kind=kind,
            unit=unit,
            precision=precision,
            layout=layout,
        )

    if isinstance(default, (int, float)) and not isinstance(default, bool):
        is_int = isinstance(default, int) and override.get("kind") != "float"
        kind = override.pop("kind", "int" if is_int else "float")
        d = float(default)
        # Auto bounds: a generous ±50% window. The step gives 0.1%
        # *relative* resolution (window / 1000) so any scaling factor,
        # fraction, length, or angle is fine-tunable by hand regardless of
        # its magnitude — a flat absolute step would be too coarse for
        # sub-unity fractions and needlessly fine for large values. Snapped
        # to the 1-2-5 series for clean slider stops. For an int
        # default of 0 the multiplicative window collapses, so fall back to
        # a small absolute range.
        if d == 0.0:
            lo, hi, step = -1.0, 1.0, 0.1
        else:
            lo = d * 0.5 if d > 0 else d * 1.5
            hi = d * 1.5 if d > 0 else d * 0.5
            step = _nice_step(max((hi - lo) / 1000.0, 1e-9))
        if kind == "int":
            lo = float(int(round(lo)))
            hi = float(int(round(hi)))
            step = 1.0
        # Phase params (phase_lr, phase_tb, ...) are degrees, converted
        # to a phasor by the array builders via exp(j π · phase / 180).
        # ±180° covers the full unit circle; signed range puts the
        # zero-phase reference at slider centre with positive = lead,
        # negative = lag. The auto-derived (-1, 1) fallback for
        # default=0 would otherwise give a useless 2° span.
        if name.startswith("phase_"):
            lo, hi, step = -180.0, 180.0, 1.0
            unit = unit or "°"
        # `design_freq` is the geometry-sizing frequency for
        # geometry-from-design_freq designs (wavelength = c / design_freq, then
        # dimensions are wavelength × factors). Wire it into the
        # global designFreq state on the frontend so the slider
        # actually retunes the geometry AND the meas-freq slider
        # follows when linkMeas is on. Top-level designs don't have a
        # design_freq param — their geometry is hand-tuned in absolute
        # meters and the measurement freq slider (at the top of the
        # UI) is the only thing that needs to move per solve.
        if name == "design_freq":
            unit = unit or "MHz"
            override["linked_to_design_freq"] = True  # keep around
        # Angle params read in degrees; show the ° unit on the slider so the
        # label can drop the redundant `_deg` token (see _display_label), and
        # default to a 0.5° step (finer than the auto 1-2-5 step is overkill,
        # coarser loses the half-degree tuning hams expect). A design's
        # ui_params `step` still overrides; int-typed angles keep whole steps.
        if _is_degree_param(name):
            unit = unit or "°"
            if kind != "int":
                step = 0.5
        final_step = float(override.pop("step", step))
        # Derive display precision from the resolved step (matching its
        # decimals plus one digit of headroom), unless the design pinned a
        # precision or this is an int / phase param fixed to whole units.
        if explicit_precision is not None:
            resolved_precision = int(explicit_precision)
        elif kind == "int" or name.startswith("phase_"):
            resolved_precision = 0
        else:
            resolved_precision = _precision_for_step(final_step)
        spec_kwargs = dict(
            name=name,
            label=label,
            default=int(d) if kind == "int" else d,
            kind=kind,
            min=float(override.pop("min", lo)),
            max=float(override.pop("max", hi)),
            step=final_step,
            precision=resolved_precision,
            unit=unit,
            sweepable=sweepable,
            layout=layout,
        )
        if "linked_to_design_freq" in override:
            spec_kwargs["linked_to_design_freq"] = bool(
                override.pop("linked_to_design_freq")
            )
        if "link_meas_freq_to_param" in override:
            spec_kwargs["link_meas_freq_to_param"] = str(
                override.pop("link_meas_freq_to_param")
            )
        return ParamSpec(**spec_kwargs)

    if isinstance(default, str):
        opts = override.pop("enum_options", None)
        if opts is None:
            return None
        # The frontend renders SchemaEnumOption dicts ({value, label}, plus
        # free-form extras). Designs with no per-option metadata may pass
        # bare strings (e.g. the CABLES keys) — normalise those here;
        # un-normalised strings render as empty <option>s.
        return ParamSpec(
            name=name,
            label=label,
            default=default,
            kind="enum",
            enum_options=tuple(
                o if isinstance(o, dict) else {"value": str(o), "label": str(o)}
                for o in opts
            ),
            precision=precision,
            unit=unit,
            layout=layout,
        )

    # complex, None, or anything exotic — skip the auto-UI; the request
    # body can still override via {"re": ..., "im": ...}.
    return None


def _group_spec_from_default(
    name: str,
    default_value: tuple | list,
    ui_override: dict,
    all_default_params: dict,
) -> ParamGroupSpec | None:
    """Build a ParamGroupSpec from a tuple/list-of-dicts default value.

    The default value's length seeds default_overrides for the group's
    instances; the inner ParamSpecs come from auto-deriving each key of
    the first instance dict (with optional per-leaf overrides supplied
    under the same ui_override dict, keyed by leaf name).

    `ui_override` is the dict stored under `ui_params[<group_name>]`.
    Recognised keys: label_template, repeat_count, max_repeats,
    link_meas_freq_to_param, plus any leaf-name → override-dict pairs.
    Falls back to sensible defaults when missing.
    """
    if not default_value or not all(isinstance(d, dict) for d in default_value):
        return None
    template = default_value[0]
    if not template:
        return None

    repeat_count = ui_override.get("repeat_count")
    if repeat_count is None:
        # Heuristic: prefer n_<name> (n_bands for bands), then n_<singular>.
        for cand in (f"n_{name}", f"n_{name.rstrip('s')}"):
            if cand in all_default_params:
                repeat_count = cand
                break
    if not isinstance(repeat_count, str):
        # No count param → can't render a repeating group.
        return None

    max_repeats = int(ui_override.get("max_repeats", len(default_value)))
    label_template = str(ui_override.get("label_template", f"{name} {{i}}"))
    link = ui_override.get("link_meas_freq_to_param")

    inner_params: list[ParamSpec] = []
    for leaf_name, leaf_default in template.items():
        leaf_override = ui_override.get(leaf_name)
        if leaf_override is None or not isinstance(leaf_override, dict):
            leaf_override = {}
        spec = _auto_paramspec(leaf_name, leaf_default, dict(leaf_override))
        if spec is not None:
            inner_params.append(spec)
    if not inner_params:
        return None

    default_overrides = tuple(dict(d) for d in default_value)

    return ParamGroupSpec(
        name=name,
        label_template=label_template,
        repeat_count=repeat_count,
        max_repeats=max_repeats,
        params=tuple(inner_params),
        default_overrides=default_overrides,
        link_meas_freq_to_param=str(link) if isinstance(link, str) else None,
    )


def _budget_rows(eng, builder):
    """Package the engine's power budget for the UI, applying the design's
    optional ``ui_params["budget_labels"]`` display renames (issue #489).
    Structural labels stay authoritative everywhere else (tests pin them);
    this rename happens only at the presentation boundary. Tiny negative
    float noise from reactive stamps is clamped to 0.

    Each row carries the instance ``path`` its branch came from ("" for
    top-level rows) so the UI can group and indent a composite's rows
    under its instance name. The path is recovered from the structural
    label's "<path>: " prefix — matched against the network's actual
    instance paths (``branch_paths``), never guessed from the colon alone —
    and rows resolved to a path drop that prefix from the display label
    (the group header already names the instance). Renames are keyed on
    the full structural label and win verbatim."""
    # The solve path builds the Builder with the reserved ui_params key
    # STRIPPED from its params (_build_builder), so the instance attribute
    # usually doesn't exist — fall back to the design class's declared
    # defaults. (The old `builder.ui_params` attribute read silently
    # returned nothing in the server path and the renames never applied.)
    ui = getattr(builder, "ui_params", None)
    if ui is None:
        ui = (getattr(type(builder), "default_params", None) or {}).get("ui_params")
    relabel = dict((ui or {}).get("budget_labels") or {})
    net = getattr(eng, "_network", None)
    instance_paths = sorted(
        {p[:-1] for p in (getattr(net, "branch_paths", None) or []) if p},
        key=len,
        reverse=True,  # longest first: "sta.tuner" must beat "sta"
    )
    rows = []
    for label, w in getattr(eng, "_excited_power_budget", None) or []:
        path = next((p for p in instance_paths if label.startswith(p + ": ")), "")
        if label in relabel:
            display = relabel[label]
        elif path:
            display = label[len(path) + 2 :]
        else:
            display = label
        # `key` keeps the raw structural label alongside the display rename:
        # the schematic fold-in (issue #652) matches blocks by "<path>: ..."
        # prefixes, which the relabelled/stripped display label no longer
        # carries. The frontend echoes (key, watts) back to /schematic.
        rows.append(
            {"label": display, "watts": max(0.0, float(w)), "path": path, "key": label}
        )
    return rows


def _req_budget(req):
    """The solve's power budget, read back out of a /schematic request.

    The schematic endpoint deliberately never solves — it stays cheap enough
    to refetch per knob change — so the frontend passes the budget it already
    holds from the latest solve: structural ``(key, watts)`` pairs (the `key`
    field `_budget_rows` carries) plus that solve's ``input_power_w``.
    Malformed entries are dropped rather than erroring: the budget is an
    annotation, and a drawing without watts beats a 422 for the whole panel.
    """
    out = []
    for row in req.get("budget") or ():
        if (
            isinstance(row, (list, tuple))
            and len(row) == 2
            and isinstance(row[0], str)
            and isinstance(row[1], (int, float))
            and math.isfinite(row[1])
        ):
            out.append((row[0], float(row[1])))
    p_in = req.get("input_power_w")
    ok = isinstance(p_in, (int, float)) and math.isfinite(p_in) and p_in > 0
    return out or None, (float(p_in) if ok else None)


def _apply_plane(builder, req):
    """Move the solve to the request's measurement plane (issue #652 c).

    Returns ``(plane, planes)`` for the response — the plane actually solved
    at (the natural source port when none was asked for) and every pickable
    one. Asking for a non-natural plane shadows the built builder's
    ``build_network`` with the pruned, re-sourced network from
    `plane.driven_at`: engines read the network exactly once, so the
    instance attribute is a sufficient seam. ``(None, None)`` when there is
    nothing to pick — no network, or a multi-feed drive with no single plane
    to move. An unknown plane raises ValueError like any bad request field.
    """
    from antennaknobs.plane import driven_at, planes_of

    build = getattr(builder, "build_network", None)
    net = build() if callable(build) else None
    if net is None or len(net.sources) != 1:
        return None, None
    natural = net.sources[0].port
    planes = planes_of(net)
    plane = req.get("plane")
    if not plane or plane == natural:
        return natural, planes
    if plane not in planes:
        raise ValueError(
            f"unknown measurement plane {plane!r}; this design offers {planes}"
        )
    pruned = driven_at(net, plane)
    # object.__setattr__, NOT plain assignment: Builder.__setattr__ files
    # every write into _params, where a normal read never finds it (the
    # class method wins the lookup) — the shadow would be silently absorbed
    # and every plane would quietly solve at the natural port.
    object.__setattr__(builder, "build_network", lambda: pruned)
    return plane, planes


def _derive_schema(default_params: dict) -> tuple:
    ui = dict(default_params.get("ui_params") or {})
    specs: list[ParamSpec] = []
    for key, default in default_params.items():
        if key == "ui_params":
            continue
        # `freq` is measurement frequency only — driven by the dedicated
        # meas-freq slider at the top of the UI, never by a schema
        # slider. The Builder's default_params['freq'] value is still
        # used as the initial measurement freq when the example loads;
        # the adapter just doesn't expose a redundant slider for it.
        #
        # `design_freq` is the geometry-sizing frequency for
        # design_freq-sized designs, driven by the "design freq" band-tab
        # row + slider in the UI (which sends design_freq_mhz on the
        # request). Skipping it here too prevents the auto-derived
        # schema slider from duplicating that control.
        if key in ("freq", "design_freq"):
            continue
        # `hidden`: the design pins this param at its default and suppresses its
        # control. The value still flows through every solve (it's in
        # default_params, which _build_builder seeds from), so this is a
        # display-only override — used to drop a knob that's degenerate with
        # another (e.g. a `_frac` that only ever multiplies `length_factor`).
        # Checked before the group/scalar branches so it applies to any kind.
        override_raw = ui.get(key)
        if isinstance(override_raw, dict) and override_raw.get("hidden"):
            continue
        # Repeating-group default: tuple/list of dicts → ParamGroupSpec.
        # The ui_params override (if any) carries the group-level
        # config (label_template, repeat_count, max_repeats,
        # link_meas_freq_to_param) plus per-leaf override dicts.
        if (
            isinstance(default, (tuple, list))
            and default
            and all(isinstance(x, dict) for x in default)
        ):
            group_override = ui.get(key)
            if not isinstance(group_override, dict):
                group_override = {}
            group_spec = _group_spec_from_default(
                key, default, group_override, default_params
            )
            if group_spec is not None:
                specs.append(group_spec)
            continue
        override = ui.get(key)
        if override is not None and not isinstance(override, dict):
            # Reserved scalar (e.g. `target_z0`) — not a per-param spec.
            continue
        spec = _auto_paramspec(key, default, override)
        if spec is not None:
            specs.append(spec)
    return tuple(specs)


# ---------------------------------------------------------------------------
# Builder construction from a request dict
# ---------------------------------------------------------------------------


def _rehydrate_param(default_value: Any, raw: Any) -> Any:
    if isinstance(default_value, complex) and isinstance(raw, dict):
        return complex(float(raw.get("re", 0.0)), float(raw.get("im", 0.0)))
    if isinstance(default_value, bool):
        return bool(raw)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return int(raw)
    if isinstance(default_value, float):
        return float(raw)
    return raw


def _build_builder(cls, req: dict):
    """Construct a Builder from default_params overlaid with request fields.

    The momwire frontend assembles its solve request by Object.assign'ing
    every live slider value as a *top-level* key on the request dict
    (App.tsx:buildRequest), so we read each Builder param off the request
    directly. A nested `params` dict is also accepted as a fallback for
    other clients.
    """
    # Seed from the named variant (e.g. `opt_params`, `z50_params`).
    # Unrecognised / absent → fall back to default_params.
    base = _strip_ui(_variant_params(cls, req.get("variant")))
    nested = req.get("params") or {}
    for k in list(base.keys()):
        if k in req:
            base[k] = _rehydrate_param(base[k], req[k])
        elif k in nested:
            base[k] = _rehydrate_param(base[k], nested[k])
    # The defaults are all finite, so this only fires on a client-sent value —
    # stdlib json accepts NaN/Infinity literals and a non-finite knob would
    # otherwise surface as an opaque solver error (issue #347).
    for k, v in base.items():
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(f"parameter {k!r} must be finite (got {v!r})")
        if isinstance(v, complex) and not (
            math.isfinite(v.real) and math.isfinite(v.imag)
        ):
            raise ValueError(f"parameter {k!r} must be finite (got {v!r})")
    builder = cls(params=base)
    # n_per_wire drives the per-Builder nominal_nsegs (the convergence
    # sweep at /converge overrides this value per N). Each generator
    # decides which per-edge segment counts scale with it and which stay
    # fixed (feed gaps). See AntennaBuilder.FRAMEWORK_PARAMS.
    n_per_wire = req.get("n_per_wire")
    if n_per_wire is not None:
        try:
            n = int(n_per_wire)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"n_per_wire must be an integer (got {n_per_wire!r})"
            ) from None
        if n < 1:
            raise ValueError(f"n_per_wire must be >= 1 (got {n})")
        builder.nominal_nsegs = n
    return builder


def _requested_ground_model(req: dict):
    """The frontend's three-way ground model when ground is on, else None.
    Defaults to "fast" (reflection-coefficient) when `ground_model` is
    absent — Sommerfeld is opt-in everywhere because it is the expensive
    model (seconds per solve on the bspline backend, and PyNEC's own gn 2
    is ~2x slower). The legacy boolean `ground_fast` remains accepted."""
    if not req.get("ground", False):
        return None
    model = req.get("ground_model")
    if model is None:
        model = "fast"
    return model


# Fixed terrain media (v1 of the web exposure, issue #534's QTH numbers):
# the panel shows them read-only; editable media are a possible follow-up.
_TERRAIN_WATER = (80.0, 0.005)
_TERRAIN_LAND = (13.0, 0.005)


# --- Soil constants for the finite ground models (issue #1173) -----------
#
# Until #1173 every finite-ground solve in the app used DEFAULT_GROUND's
# eps_r=10 / sigma=0.002 and the user had no handle on it, even though the
# soil decides both the answer (Z_in moves several ohms of reactance across
# the ladder below) and the cost profile of a Sommerfeld sweep.
#
# Clamp ranges. eps_r's floor is 1 = vacuum, which is what the Fresnel maths
# needs (nec_import refuses eps_r <= 1 for the same reason); sigma spans
# [1e-4, 5] S/m, log-scaled in the UI because that is four and a half
# decades.
#
# The ceiling is 81, not the 80 the issue suggested: sea water is eps_r 81,
# so a ceiling of 80 would have let the served "salt water" preset be
# silently clamped to 80.0 by the very endpoint that serves it. Measured,
# not reasoned — the preset round-trip test below is what caught it, and it
# is why `test_every_preset_survives_its_own_clamp` exists.
SOIL_EPS_R_RANGE = (1.0, 81.0)
SOIL_SIGMA_RANGE = (1e-4, 5.0)

# The named ladder. Every value here is sourced from a number this codebase
# already stands behind rather than retyped from a book:
#   v.poor / poor / average / v.good / sea  -- momwire's own ground ladder,
#     the one its reference-engine study tabulates (momwire
#     docs/design/contact-over-finite-ground.md 3.2, and the (eps_r, sigma)
#     pairs in momwire/scripts/spike_contact_plane_reference.py and
#     capture_contact_nec5_lane.py);
#   fresh water -- _TERRAIN_WATER above, so the soil menu and the terrain
#     panel cannot disagree about what water is.
#
# The issue's list also names a "good" between average and very good. It is
# deliberately ABSENT: no value for it exists anywhere in this repo, and a
# published soil constant is not something to interpolate or recall from
# memory into a physics default. Dial it by hand or add it here with a
# citation. See the PR discussion on #1173.
_SOIL_PRESETS: tuple[tuple[str, str, float, float, str], ...] = (
    ("very-poor", "very poor", 3.0, 0.0001, "Industrial / city, or dry barren rock."),
    ("poor", "poor", 5.0, 0.001, "Rocky, sandy or dry soil."),
    (
        "average",
        "average",
        13.0,
        0.005,
        "Pastoral, medium hills — the usual default soil.",
    ),
    (
        "very-good",
        "very good",
        20.0,
        0.0303,
        "Rich, moist agricultural soil; the classic 20/0.0303 earth.",
    ),
    (
        "fresh-water",
        "fresh water",
        *_TERRAIN_WATER,
        "Fresh water, matching the terrain panel's water medium.",
    ),
    ("salt-water", "salt water", 81.0, 5.0, "Sea water."),
)


def soil_presets_schema() -> list[dict]:
    """The named soil catalog served on GET /capabilities (issue #1173),
    the same self-describing shape as `terrain_presets_schema` — a
    Python-only preset needs no TypeScript. Carries the clamp ranges too,
    so the panel's two knobs get their bounds from the server that
    enforces them rather than from a second copy in TypeScript."""
    return [
        {
            "name": name,
            "label": label,
            "eps_r": eps_r,
            "sigma": sigma,
            "tooltip": f"{tooltip} \u03b5r {_num_or_int(eps_r)}, \u03c3 {sigma} S/m.",
        }
        for name, label, eps_r, sigma, tooltip in _SOIL_PRESETS
    ]


def _num_or_int(v: float) -> str:
    """3.0 -> "3" for a tooltip; 20.5 stays "20.5"."""
    return str(int(v)) if float(v).is_integer() else str(v)


def soil_ranges_schema() -> dict:
    """Clamp bounds + defaults for the two soil knobs, served alongside the
    presets so the UI slider bounds and the server clamp are one fact."""
    return {
        "eps_r": {
            "min": SOIL_EPS_R_RANGE[0],
            "max": SOIL_EPS_R_RANGE[1],
            "default": float(DEFAULT_GROUND[1]),
        },
        "sigma": {
            "min": SOIL_SIGMA_RANGE[0],
            "max": SOIL_SIGMA_RANGE[1],
            "default": float(DEFAULT_GROUND[2]),
            "log": True,
        },
    }


def _soil_from_request(req: Mapping) -> tuple[float, float]:
    """The (eps_r, sigma) the request asks for, clamped, defaulting to
    DEFAULT_GROUND's 10 / 0.002 so a request that predates #1173 — or any
    client that never sends the field — solves exactly what it did before.

    Client input is untrusted: same clamp-and-fall-back discipline as
    `_terrain_num`, because a NaN or a string here would otherwise reach
    NEC's GN card and momwire's Sommerfeld grid.
    """
    soil = req.get("soil")
    if not isinstance(soil, Mapping):
        return float(DEFAULT_GROUND[1]), float(DEFAULT_GROUND[2])
    return (
        _terrain_num(soil, "eps_r", float(DEFAULT_GROUND[1]), *SOIL_EPS_R_RANGE),
        _terrain_num(soil, "sigma", float(DEFAULT_GROUND[2]), *SOIL_SIGMA_RANGE),
    )


def _terrain_num(t: Mapping, key: str, default: float, lo: float, hi: float) -> float:
    """One clamped, finite terrain parameter — client input is untrusted."""
    try:
        v = float(t.get(key, default))
    except (TypeError, ValueError):
        v = default
    if not math.isfinite(v):
        v = default
    return min(max(v, lo), hi)


# --- Terrain preset registry (issue #560) --------------------------------
#
# One descriptor per preset is the single source of truth for three things
# that used to be spelled out three times (once per preset, in Python AND in
# App.tsx): the server-side clamp + constructor mapping, the response
# chart-orientation marker, and the self-describing field schema the frontend
# renders its knob panel from (served on GET /capabilities). Adding a preset
# is now one entry here — no TypeScript, no rebuild beyond the asset build.


@dataclass(frozen=True)
class _TerrainField:
    """One clamped numeric knob of a preset. `min`/`max`/`default` are
    authoritative server-side (the clamp) AND drive the frontend slider;
    `label`/`unit`/`step` are presentation the UI reads verbatim. `label`
    omits the unit — the panel renders it as ``"{label} ({unit})"``."""

    key: str
    label: str
    default: float
    min: float
    max: float
    step: float
    unit: str | None = None


@dataclass(frozen=True)
class _TerrainMarker:
    """Chart-orientation hint: which field carries the preset's characteristic
    bearing, and the two side labels drawn on the polar charts. `hide_when_ge`
    drops the marker for an azimuth-symmetric configuration (a full-circle
    cliff, arc_deg >= 360)."""

    bearing_key: str
    label: str
    opposite: str
    hide_when_ge: tuple[str, float] | None = None


@dataclass(frozen=True)
class _TerrainPreset:
    name: str
    label: str  # radio label shown in the panel
    tooltip: str  # radio hover text
    media_note: str  # read-only media line under the knobs
    fields: tuple[_TerrainField, ...]
    build: Callable[[Mapping[str, float]], Terrain]
    marker: _TerrainMarker | None = None


_TERRAIN_MEDIA_NOTE = "media: water εr=80 σ=0.005 · land/crest εr=13 σ=0.005"


def _build_levee(v: Mapping[str, float]) -> Terrain:
    return levee_terrain(
        crest_width=v["crest_width_m"],
        slope_deg=v["slope_deg"],
        drop_water=v["drop_water_m"],
        drop_land=v["drop_land_m"],
        water=_TERRAIN_WATER,
        land=_TERRAIN_LAND,
        water_azimuth=v["water_azimuth_deg"],
    )


def _build_cliff(v: Mapping[str, float]) -> Terrain:
    return cliff_terrain(
        edge=v["edge_m"],
        drop=v["drop_m"],
        inner=_TERRAIN_LAND,
        outer=_TERRAIN_WATER,
        azimuth=v["azimuth_deg"],
        arc=v["arc_deg"],
    )


def _build_hillside(v: Mapping[str, float]) -> Terrain:
    return hillside_terrain(
        flat_width=v["flat_width_m"],
        up_slope_deg=v["up_slope_deg"],
        down_slope_deg=v["down_slope_deg"],
        medium=_TERRAIN_LAND,
        downhill_azimuth=v["downhill_azimuth_deg"],
    )


_TERRAIN_PRESETS: tuple[_TerrainPreset, ...] = (
    _TerrainPreset(
        name="levee",
        label="levee",
        tooltip=(
            "A raised crest with two sloped sides: water drop_water below on "
            "the water bearing, land drop_land below opposite. Crest and slopes "
            "are earth; water starts at the toe."
        ),
        media_note=_TERRAIN_MEDIA_NOTE,
        fields=(
            _TerrainField("crest_width_m", "crest width", 3.0, 0.1, 1e3, 0.5, "m"),
            _TerrainField("slope_deg", "slope", 20.0, 1.0, 89.0, 1.0, "°"),
            _TerrainField("drop_water_m", "drop to water", 10.7, 0.01, 1e3, 0.5, "m"),
            _TerrainField("drop_land_m", "drop to land", 7.6, 0.01, 1e3, 0.5, "m"),
            _TerrainField(
                "water_azimuth_deg", "water bearing", 0.0, -360.0, 360.0, 5.0, "°"
            ),
        ),
        build=_build_levee,
        marker=_TerrainMarker("water_azimuth_deg", "water", "land"),
    ),
    _TerrainPreset(
        name="cliff",
        label="cliff",
        tooltip=(
            "Flat earth out to the cliff edge, then a sheer drop to water. "
            "arc < 360° restricts the cliff to a sector facing the bearing."
        ),
        media_note=_TERRAIN_MEDIA_NOTE,
        fields=(
            _TerrainField("edge_m", "cliff edge", 10.0, 0.1, 1e4, 1.0, "m"),
            _TerrainField("drop_m", "drop", 10.0, 0.01, 1e3, 0.5, "m"),
            _TerrainField("azimuth_deg", "bearing", 0.0, -360.0, 360.0, 5.0, "°"),
            _TerrainField("arc_deg", "arc", 360.0, 1.0, 360.0, 15.0, "°"),
        ),
        build=_build_cliff,
        marker=_TerrainMarker(
            "azimuth_deg", "cliff", "flat", hide_when_ge=("arc_deg", 360.0)
        ),
    ),
    _TerrainPreset(
        name="hillside",
        label="hillside",
        tooltip=(
            "A flat bench on a hillside: ground rises at the uphill slope on "
            "one side, falls at the downhill slope on the other (facing the "
            "downhill bearing). No bottom needed — the slope itself is the "
            "reflector, so effective height grows as the elevation drops. Below "
            "the uphill slope angle the model can't see the hill's shadowing."
        ),
        media_note="media: earth εr=13 σ=0.005",
        fields=(
            _TerrainField("flat_width_m", "flat width", 20.0, 0.1, 1e3, 1.0, "m"),
            _TerrainField("up_slope_deg", "uphill slope", 15.0, 1.0, 89.0, 1.0, "°"),
            _TerrainField(
                "down_slope_deg", "downhill slope", 10.0, 1.0, 89.0, 1.0, "°"
            ),
            _TerrainField(
                "downhill_azimuth_deg", "downhill bearing", 0.0, -360.0, 360.0, 5.0, "°"
            ),
        ),
        build=_build_hillside,
        marker=_TerrainMarker("downhill_azimuth_deg", "downhill", "uphill"),
    ),
)
_TERRAIN_PRESET_BY_NAME = {p.name: p for p in _TERRAIN_PRESETS}
_DEFAULT_TERRAIN_PRESET = _TERRAIN_PRESETS[0]  # levee


def _clamped_terrain(req: dict) -> tuple[_TerrainPreset, dict[str, float]]:
    """Resolve the request's `terrain` block to (preset, clamped values).
    Unknown or missing preset falls back to levee; every field is clamped to
    the descriptor's range so a hand-crafted request can't build a degenerate
    Terrain."""
    t = req.get("terrain") or {}
    if not isinstance(t, Mapping):
        t = {}
    preset = _TERRAIN_PRESET_BY_NAME.get(t.get("preset"), _DEFAULT_TERRAIN_PRESET)
    values = {
        f.key: _terrain_num(t, f.key, f.default, f.min, f.max) for f in preset.fields
    }
    return preset, values


def _terrain_from_request(req: dict) -> Terrain:
    """Build the faceted-terrain ground from the request's `terrain` preset
    params (ground_model="terrain"). The preset registry maps the clamped
    field values straight onto the antennaknobs.terrain constructors; media
    are fixed at the QTH constants (water 80/0.005 outward of the cliff/water-
    side toe; land 13/0.005 for crest, slopes and the land plain)."""
    preset, values = _clamped_terrain(req)
    return preset.build(values)


def _terrain_marker(req: dict) -> dict | None:
    """Chart-orientation hint for the response's terrain: the preset's
    characteristic bearing plus labels for its two sides, drawn on the
    polar charts so "which way is the water/downhill" reads off the chart
    instead of being inferred from lobes (which can legitimately peak
    toward the other side — e.g. a hillside's uphill mid-angle lobes).
    None when the terrain is azimuth-symmetric (full-circle cliff)."""
    preset, values = _clamped_terrain(req)
    m = preset.marker
    if m is None:
        return None
    if m.hide_when_ge is not None:
        key, threshold = m.hide_when_ge
        if values[key] >= threshold:
            return None
    return {
        "bearing_deg": values[m.bearing_key],
        "label": m.label,
        "opposite": m.opposite,
    }


def terrain_presets_schema() -> list[dict]:
    """The self-describing preset catalog served on GET /capabilities: each
    preset's radio label + tooltip, its ordered field schema (key, label,
    unit, default, min/max/step), and the read-only media note. The frontend
    renders its whole terrain knob panel from this — a Python-only preset
    needs no TypeScript."""
    return [
        {
            "name": p.name,
            "label": p.label,
            "tooltip": p.tooltip,
            "media_note": p.media_note,
            "fields": [
                {
                    "key": f.key,
                    "label": f.label,
                    "unit": f.unit,
                    "default": f.default,
                    "min": f.min,
                    "max": f.max,
                    "step": f.step,
                }
                for f in p.fields
            ],
        }
        for p in _TERRAIN_PRESETS
    ]


def _pack_terrain(t: Terrain) -> dict:
    """JSON-safe terrain description shipped on the solve response. The
    server's cut physics (server._mag2_at_directions) rebuilds the Terrain
    from this to run the per-direction specular-facet reflection — the
    response must be self-contained because /cuts is stateless."""
    return {
        "sectors": [
            {
                "az0": float(s.az0),
                "az1": float(s.az1),
                "facets": [
                    [
                        f.x1 if f.x1 is None else float(f.x1),
                        float(f.z1),
                        float(f.eps_r),
                        float(f.sigma),
                    ]
                    for f in s.facets
                ],
            }
            for s in t.sectors
        ]
    }


def _ground_for_engine(req: dict):
    """Map the frontend's ground knobs to MomwireEngine's ground spec —
    same three-way model as `_pynec_ground_spec`, one shared selector
    describing the GROUND; each engine approximates it as best it can.
    "pec" → the PEC image; "sommerfeld" → ("finite", ...), which momwire
    solves as the TRUE Sommerfeld ground on every solver (momwire >=
    0.8.0: bspline dense, sinusoidal field-based, hmatrix/arrayblock fast
    paths); "fast" → ("finite-fast", ...), the reflection-coefficient
    model everywhere. Both finite models carry the request's soil (issue
    #1173, `_soil_from_request`). The response ships the engine's actual
    eps/sigma so the frontend far-field Fresnel uses the real constants
    either way; `ground_model_applied` reports what the impedance solve
    really used."""
    model = _requested_ground_model(req)
    if model is None:
        return None
    if model == "pec":
        return "pec"
    if model == "fast":
        return ("finite-fast",) + _soil_from_request(req)
    if model == "terrain":
        # Faceted terrain (issue #534): impedance solves flat Sommerfeld on
        # the crest medium; the far field applies per-direction specular-
        # facet reflection (engine far_field and server cuts alike).
        return ("terrain", _terrain_from_request(req))
    return ("finite",) + _soil_from_request(req)


def _pynec_ground_applied(ground) -> str:
    """What PyNEC's impedance solve actually used, from the engine's ground
    spec — the PyNEC counterpart of the momwire path's ground_model_applied:
    "sommerfeld" / "refl-coef" for the finite specs, "pec-image", or
    "free". PyNEC honours every requested model directly, so unlike momwire
    this never differs from the request; it ships anyway so the frontend
    readout has one authoritative source across engines."""
    if isinstance(ground, tuple):
        return "refl-coef" if ground[0] == "finite-fast" else "sommerfeld"
    return "pec-image" if ground == "pec" else "free"


def _pynec_ground_spec(req: dict):
    """Map the frontend's ground knobs to PyNECEngine's ground spec, matching
    the UI labels. `ground_model` picks the model when ground is on:
    "sommerfeld" (default) — Sommerfeld-Norton finite ground; "fast" — the
    same finite ground via NEC's reflection-coefficient approximation;
    "pec" — perfectly conducting ground. Ground off is free space. Both
    finite models carry the request's soil (issue #1173,
    `_soil_from_request`), which defaults to DEFAULT_GROUND's 10 / 0.002."""
    model = _requested_ground_model(req)
    if model is None:
        return "free"
    if model == "pec":
        return "pec"
    if model == "fast":
        return ("finite-fast",) + _soil_from_request(req)
    if model == "terrain":
        # PyNEC terrain hybrid (issue #553): NEC-2 has no facet model, but
        # the #534 recipe never lets the facets touch the current solve —
        # impedance/currents run over flat Sommerfeld at the CREST medium,
        # which NEC solves natively (GN 2). The facets enter afterward in
        # the server's far-field composition, fed by the `ground_terrain`
        # field pynec_solve attaches to the response.
        return ("finite",) + _terrain_from_request(req).crest_medium
    return ("finite",) + _soil_from_request(req)


def _nec5_ground_spec(req: dict):
    """Map the frontend's ground knobs to NEC5Engine's ground spec. NEC-5
    has no reflection-coefficient model (its IPERF 0 IS full Sommerfeld),
    so the UI's "fast" request is served by the full Sommerfeld solve and
    `ground_model_applied` reports "sommerfeld" — the engine's honest
    upgrade, same convention as a momwire solver falling back to its best
    available model. Terrain rides the crest-medium hybrid exactly like
    the PyNEC path."""
    model = _requested_ground_model(req)
    if model is None:
        return None
    if model == "pec":
        return "pec"
    if model == "terrain":
        return ("finite",) + _terrain_from_request(req).crest_medium
    # "fast" and "sommerfeld" both land on NEC-5's native Sommerfeld.
    return ("finite",) + _soil_from_request(req)


def _nec5_ground_applied(ground) -> str:
    if isinstance(ground, tuple) and ground and ground[0] == "finite":
        return "sommerfeld"
    if ground == "pec" or (isinstance(ground, tuple) and ground[0] == "pec"):
        return "pec-image"
    return "free"


def _make_nec5_engine(req: dict, builder):
    return NEC5Engine(builder, ground=_nec5_ground_spec(req))


def _wire_material_results(builder) -> dict:
    """Wire length + weight response fields (issue #318) for designs that
    declare a wire material: total conductor run from build_wires(), weight
    from the catalog's grams/meter (jacket included). Per-wire specs
    (issue #388) sum wire by wire — a wire's own spec wins, spec-less wires
    fall back to the design default. {} when the design declares no
    material anywhere — the fields (and their Info-pane rows) only exist
    for designs with a wire material."""
    default = builder.build_wire_material()
    tups = list(builder.build_wires())
    specs = [as_wire(t).spec for t in tups]
    if default is None and not any(s is not None for s in specs):
        return {}
    length = weight = 0.0
    for t, s in zip(tups, specs, strict=True):
        p0 = np.asarray(t[0], dtype=float)
        p1 = np.asarray(t[1], dtype=float)
        ln = float(np.linalg.norm(p1 - p0))
        length += ln
        eff = s if s is not None else default
        if eff is not None:
            weight += ln * eff.weight_g_per_m
    return {
        "wire_length_m": length,
        "wire_weight_g": weight,
    }


def _rig_report_results(builder) -> dict:
    """Rigging tension/sag readout (issue #698 unit 3), surfaced under "rig"
    in the same solve responses that carry `_wire_material_results`. {} for
    every design without a `rig_report()` (nearly all of them) — the
    per-design method, not a registry flag, is the discovery mechanism, same
    idiom as `build_wire_material()` for `_wire_material_results`.

    A mid-scrub rig can be geometrically infeasible (e.g. the
    `dipoles.invvee_catenary` anchored-rope model with a rope too short to
    reach its anchor) independently of whether the antenna solve itself
    succeeded or failed — the readout is garnish on top of a solve that
    already stands on its own, so a `rig_report()` failure must never fail
    the response.
    Debug-logged and omitted rather than surfaced as an "error" key: the
    solve response already carries no other per-field error slots, and the
    solve's own success/failure is the signal that matters to the caller.
    """
    rig_report = getattr(builder, "rig_report", None)
    if not callable(rig_report):
        return {}
    try:
        return {"rig": rig_report()}
    except Exception:
        _logger.debug(
            "rig_report() failed for %r", type(builder).__name__, exc_info=True
        )
        return {}


# Every key a readout row may carry, and nothing else (issue #712). The row
# contract is deliberately tiny: `label` (display text), `value` (a number the
# frontend formats, a short string it prints verbatim, or None -> em-dash),
# `unit` (appended after the value), `group` (small heading rows cluster
# under; None = ungrouped, rendered first).
_READOUT_KEYS = frozenset({"label", "value", "unit", "group"})


def _readout_row(raw, owner: str) -> dict | None:
    """Validate one `readout_rows()` row, returning the normalised row (all
    four keys present) or None if it is malformed.

    Validation is server-side and per-row on purpose: these rows come from
    arbitrary design code — catalog designs AND whatever is in
    ~/.antennaknobs/designs — and the whole point of the contract is that a
    design author writes Python and gets a readout with no TypeScript. The
    other half of that bargain is that their typo cannot reach the client:
    one bad row is dropped, its siblings still render, and the browser never
    has to defend itself against a value it cannot display.
    """

    def bad(why: str) -> None:
        _logger.debug("dropping readout row from %s: %s (%r)", owner, why, raw)
        return None

    if not isinstance(raw, Mapping):
        return bad("not a mapping")
    extra = set(raw) - _READOUT_KEYS
    if extra:
        return bad(f"unknown key(s) {sorted(extra)}")
    label = raw.get("label")
    if not isinstance(label, str) or not label:
        return bad("label must be a non-empty string")
    value = raw.get("value")
    if isinstance(value, bool):
        # bool is an int subclass; a True/False readout is a design bug, not
        # a number to plot next to a tension.
        return bad("value must not be a bool")
    if isinstance(value, (int, float)):
        value = float(value)
        if not math.isfinite(value):
            # NaN/Infinity are not JSON, and the browser's JSON.parse
            # rejects them outright (same trap as the measured-open clamp).
            return bad("value is not finite")
    elif not (value is None or isinstance(value, str)):
        return bad(
            f"value must be a number, string or None, got {type(value).__name__}"
        )
    unit = raw.get("unit")
    if not (unit is None or isinstance(unit, str)):
        return bad("unit must be a string or None")
    group = raw.get("group")
    if not (group is None or isinstance(group, str)):
        return bad("group must be a string or None")
    return {"label": label, "value": value, "unit": unit, "group": group}


def _readout_rows_results(builder) -> dict:
    """Generic workbench readout rows (issue #712), surfaced under "readouts"
    beside `_wire_material_results` / `_rig_report_results`. {} for every
    design that defines no `readout_rows()` — the duck-typed per-design
    method is the discovery mechanism, the same idiom `rig_report()` and
    `build_wire_material()` use, so a user design in ~/.antennaknobs/designs
    gets a readout the moment it grows the method, with no registry entry and
    no frontend change.

    This is the generic successor to `_rig_report_results`'s bespoke "rig"
    key (which stays, unchanged, for compatibility): the rows are
    self-describing, so every future construction feature that wants numbers
    on screen is Python-only.

    Same omit-on-error contract as `_rig_report_results` — the readout is
    garnish on a solve that already stands on its own, so a producer that
    raises (a mid-scrub infeasible rig) is debug-logged and omitted, never
    surfaced as an error field and never allowed to fail the response. Rows
    are additionally validated one by one: a malformed row is dropped while
    its valid siblings survive, so one design-author typo cannot blank the
    whole panel.
    """
    readout_rows = getattr(builder, "readout_rows", None)
    if not callable(readout_rows):
        return {}
    owner = type(builder).__name__
    try:
        raw_rows = readout_rows()
        if not isinstance(raw_rows, (list, tuple)):
            _logger.debug(
                "readout_rows() for %r returned %s, not a list",
                owner,
                type(raw_rows).__name__,
            )
            return {}
        rows = [r for r in (_readout_row(raw, owner) for raw in raw_rows) if r]
    except Exception:
        _logger.debug("readout_rows() failed for %r", owner, exc_info=True)
        return {}
    return {"readouts": rows} if rows else {}


def _make_momwire_engine(req: dict, builder, cancel=None):
    # "bspline" is the default and the fallback for unknown/retired model
    # names (a stale client may still send "triangular").
    model = req.get("momwire_model", "bspline")
    solver_cls = _MOMWIRE_MODELS.get(model, BSplineSolver)
    wire_radius = _positive_finite("wire_radius", req.get("wire_radius", 0.0005))
    ground = _ground_for_engine(req)
    solver_kwargs = sanitize_model_options(req)
    # A roster entry's bound kwargs are applied AFTER the request's options and
    # win over them: `razor-2p` must stay the two-point lane whatever a client
    # sends, or the name on the tab stops describing what ran.
    if model in _MOMWIRE_BOUND:
        solver_kwargs = dict(solver_kwargs or {})
        solver_kwargs.update(_MOMWIRE_BOUND[model])
    # Extended thin-wire kernel (issue #849): pulled out of model_options and
    # passed as the named constructor kwarg instead, so it reaches the engine
    # the same way whether hosted (filtered through _HOSTED_MODEL_OPTIONS
    # above) or local (model_options forwarded verbatim, sanitize_model_options
    # skips the whitelist). MomwireEngine folds either spelling identically,
    # but the named kwarg is the explicit, testable path.
    extended_kernel = False
    if solver_kwargs and "extended_kernel" in solver_kwargs:
        solver_kwargs = dict(solver_kwargs)
        extended_kernel = bool(solver_kwargs.pop("extended_kernel"))
    if _SWEPT_MEM_MB is not None and issubclass(solver_cls, BSplineSolver):
        # Deployment-owned memory policy (momwire >= 0.9): cap the batched
        # frequency sweep's transient memory per solve. Server-side value
        # OVERRIDES any client-sent model_options entry — on the shared
        # hosted instance the budget bounds concurrent sweeps the same way
        # the ANTENNAKNOBS_MAX_BASIS caps bound single solves. Sinusoidal
        # has no batched sweep path and no such kwarg, so it is skipped
        # (HMatrix/ArrayBlock are BSplineSolver subclasses and inherit it).
        solver_kwargs = dict(solver_kwargs or {})
        solver_kwargs["swept_mem_mb"] = _SWEPT_MEM_MB
    return MomwireEngine(
        builder,
        solver=solver_cls,
        wire_radius=wire_radius,
        solver_kwargs=solver_kwargs,
        ground=ground,
        extended_kernel=extended_kernel,
        cancel=cancel,
    )


def _make_pynec_engine(req: dict, builder):
    return PyNECEngine(builder, ground=_pynec_ground_spec(req))


# ---------------------------------------------------------------------------
# Response packing
# ---------------------------------------------------------------------------


# Frontend Fresnel reflection treats this as the real part of the
# complex permittivity. For PEC the reflection coefficient ρ_h → −1 as
# eps_r → ∞; 1e10 is large enough to be numerically indistinguishable
# while staying away from float overflow. Matches momwire/web/server.py.
_PEC_GROUND_EPS_R = 1.0e10
_PEC_GROUND_SIGMA = 0.0


def _solver_advisories(eng) -> list:
    """The solver advisories one solve raised, for the response (issue #1144).

    Served on EVERY backend's response, `[]` where the engine has none, so the
    field's presence is not itself a signal the client has to branch on. PyNEC
    and NEC-5 are AK's own wrappers and raise no advisories of this kind; a
    missing key would make "this backend cannot say" and "this deck raised
    none" the same absence, which is the distinction #1103 exists to keep.

    ADVISORY, never error. Nothing was refused and nothing was remeshed — a
    deck momwire declines raises instead, and the request never gets here.
    """
    return list(getattr(eng, "advisories", ()) or ())


def _momwire_ground_fields(eng, req: dict) -> dict:
    """Ground-describing response fields for a momwire solve.

    Ships the eps_r/sigma of the ground the engine actually solved over,
    exactly like the PyNEC branch: the server's far-field cut applies the
    PEC image + Fresnel with these, so finite grounds get their real
    constants while ground_model="pec" and free space keep the PEC
    placeholders (ρ→−1). A faceted terrain ships its crest medium there
    (what the impedance solve used) plus the packed facet model under
    `ground_terrain` for the per-direction cut physics.

    `ground_model_applied` is what the impedance solve actually used, for
    honest UI wording: "sommerfeld" (any momwire solver + "finite", momwire
    >= 0.8.0), "refl-coef" ("finite-fast"), "pec-image", "free" — or
    "terrain" (crest-medium Sommerfeld impedance + faceted far field)."""
    g = eng._ground
    if isinstance(g, tuple) and g[0] == "terrain":
        eps_r, sigma = g[1].crest_medium
        gt = _pack_terrain(g[1])
        marker = _terrain_marker(req)
        if marker:
            gt["marker"] = marker
        return {
            "ground_eps_r": eps_r,
            "ground_sigma": sigma,
            "ground_model_applied": "terrain",
            "ground_terrain": gt,
        }
    if isinstance(g, tuple) and len(g) == 3:
        eps_r, sigma = g[1], g[2]
    else:
        eps_r, sigma = _PEC_GROUND_EPS_R, _PEC_GROUND_SIGMA
    return {
        "ground_eps_r": eps_r,
        "ground_sigma": sigma,
        "ground_model_applied": (
            "free" if g is None else (eng._ground_model or "pec-image")
        ),
    }


def _pack_wires(currents) -> list[dict]:
    return [
        {
            "label": f"wire{idx}",
            "knot_positions": w.knot_positions.tolist(),
            "knot_currents_re": w.knot_currents.real.tolist(),
            "knot_currents_im": w.knot_currents.imag.tolist(),
        }
        for idx, w in enumerate(currents)
    ]


def _primary_feed(engine):
    """(polyline_idx, arclength) of the driven feed, or None.

    MomwireEngine exposes `_feeds = [(polyline_idx, arclength, voltage)]`
    post-translator. For network-spec designs the geometry translator
    registers a feed for every named edge — including non-driven ports
    like trap stubs — so `_feeds[0]` is whichever named tuple appears
    first in `build_wires()`, not necessarily the driven feed. Look up
    the driven port's `_feeds` entry by index when a Network is present.
    """
    feeds = getattr(engine, "_feeds", None) or []
    feed_names = getattr(engine, "_feed_names", None) or []
    if not feeds:
        return None
    feed_idx = 0
    network = getattr(engine, "_network", None)
    if network is not None and network.sources:
        # The first Driven source is the primary feed. If it resolves to a
        # real (PortOnWire) port, use its position; otherwise (virtual port,
        # e.g. delta_looparray_network's "driver"), fall back to feeds[0].
        driven_name = network.sources[0].port
        if driven_name in feed_names:
            feed_idx = feed_names.index(driven_name)
    pl_idx, arclen, _v = feeds[feed_idx]
    return int(pl_idx), float(arclen)


def _interp_polyline(knots, cum, arclen):
    """3D point at `arclen` along a polyline (knots + cumulative arclength)."""
    arclen = min(max(arclen, 0.0), float(cum[-1]))
    seg = int(np.searchsorted(cum, arclen, side="right")) - 1
    seg = min(max(seg, 0), len(knots) - 2)
    span = cum[seg + 1] - cum[seg]
    t = 0.0 if span <= 0 else (arclen - cum[seg]) / span
    return (knots[seg] + t * (knots[seg + 1] - knots[seg])).tolist()


def _feed_indices(engine, currents) -> tuple[int, int]:
    """Pick a (wire, knot) for the feed marker — the knot nearest the feed.

    Kept for the feed_knot_index the frontend uses to read feed current and
    split the current envelope. The visible marker dot uses `_feed_position`
    instead (exact, not snapped to a knot).
    """
    pf = _primary_feed(engine)
    if pf is None:
        return 0, 0
    pl_idx, arclen = pf
    if pl_idx >= len(currents):
        return 0, 0
    knots = currents[pl_idx].knot_positions
    if knots.shape[0] < 2:
        return pl_idx, 0
    # Cumulative arclength along the polyline.
    deltas = np.linalg.norm(np.diff(knots, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(deltas)])
    j = int(np.argmin(np.abs(cum - arclen)))
    return pl_idx, j


def _position_at(currents, pl_idx, arclen):
    """Exact 3D point at `arclen` along polyline `pl_idx` of `currents`, or
    None. Shared by the primary-feed marker and the per-feed-port markers."""
    if pl_idx >= len(currents):
        return None
    knots = currents[pl_idx].knot_positions
    if knots.shape[0] < 2:
        return knots[0].tolist() if knots.shape[0] else None
    deltas = np.linalg.norm(np.diff(knots, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(deltas)])
    return _interp_polyline(knots, cum, arclen)


def _feed_position(engine, currents):
    """Exact 3D feed point for the primary feed — the physical location the
    solver actually feeds, independent of where segment knots fall. Avoids
    the half-segment marker shift from snapping to the nearest knot, which
    lands on an endpoint when the feed edge has no interior knot (e.g. a
    1-segment driven stub under odd-parity bases like sinusoidal/Bspline=2).
    """
    pf = _primary_feed(engine)
    if pf is None:
        return None
    return _position_at(currents, pf[0], pf[1])


def _declared_feed_ports(cls) -> list[str]:
    """Physical feed-port names a design declares in
    ``ui_params["feed_ports"]`` — the explicit, robust way to mark a multi-feed
    antenna whose drive is routed through ``build_network()`` (e.g. a lazy-H
    whose two element centres are fed in phase through a harness from one
    source). Topology is deliberately NOT inferred: a log-periodic feeds ~10
    chained elements from a single point, so "PortOnWire reachable from a
    source" would wrongly report ten feeds (issues #570 / #571). Empty when a
    design declares nothing — callers then keep the single-primary behaviour.
    """
    try:
        ui = dict(cls.default_params).get("ui_params", {})
        ports = ui.get("feed_ports")
        if isinstance(ports, (list, tuple)):
            return [str(p) for p in ports]
    except Exception:  # noqa: BLE001
        pass
    return []


def _feed_positions(engine, currents, multi_feed=False):
    """One marker per feed (issue #571), each ``{"name", "position": [x,y,z]}``.

    Gated by the resolved ``multi_feed`` flag so markers and the flag always
    agree — a design that overrides ``multi_feed=False`` (e.g. a common-feed
    antenna modelled with several driven gaps) shows a single marker.

    When multi-feed:
    * ``build_network()`` designs → the explicitly declared ``feed_ports``
      (topology is not trusted — see ``_declared_feed_ports``);
    * inline-``ex`` designs → every driven ``_feeds`` entry.

    Otherwise a single primary-feed marker, so single-feed designs and
    ``multi_feed=False`` overrides are unchanged."""
    if multi_feed:
        feeds = getattr(engine, "_feeds", None) or []
        feed_names = getattr(engine, "_feed_names", None) or []
        builder = getattr(engine, "builder", None)
        net = None
        if builder is not None and hasattr(builder, "build_network"):
            try:
                net = builder.build_network()
            except Exception:  # noqa: BLE001
                net = None
        out = []
        if net is not None:
            name_to_idx = {n: i for i, n in enumerate(feed_names) if n}
            for nm in _declared_feed_ports(type(builder)):
                idx = name_to_idx.get(nm)
                if idx is not None and idx < len(feeds):
                    pos = _position_at(currents, feeds[idx][0], feeds[idx][1])
                    if pos is not None:
                        out.append({"name": nm, "position": pos})
        elif len(feeds) > 1:
            for i, feed in enumerate(feeds):
                pos = _position_at(currents, feed[0], feed[1])
                if pos is not None:
                    nm = (
                        feed_names[i]
                        if i < len(feed_names) and feed_names[i]
                        else f"feed {i}"
                    )
                    out.append({"name": nm, "position": pos})
        if out:
            return out
    pos = _feed_position(engine, currents)
    return [{"name": "feed", "position": pos}] if pos is not None else []


def _pynec_feed_indices(builder, currents) -> tuple[int, int]:
    """PyNECEngine returns one WireCurrents per build_wires() tuple in
    the same order, so the feed wire index is the position of the tuple
    that carries the driven port. Place the marker on that wire's centre
    knot — close enough to NEC's per-segment feed for a UI dot.

    Network-spec designs route excitation through build_network() rather
    than the per-tuple `ev` field. Network-spec named tuples include
    non-driven ports (trap stubs, TL endpoints), so we look up the driven
    port's name and pick the tuple that matches.
    """
    tuples = list(builder.build_wires())
    driven_name = None
    if hasattr(builder, "build_network"):
        net = builder.build_network()
        if net is not None and net.sources:
            driven_name = net.sources[0].port
    for i, t in enumerate(tuples):
        ev = t[3]
        name = t[4] if len(t) >= 5 else None
        # Network-spec path: only the named tuple matching the Driven port.
        # Legacy path (no network): first `ev` is the feed.
        if driven_name is not None:
            if name != driven_name:
                continue
        elif ev is None:
            continue
        if i >= len(currents):
            return 0, 0
        k = currents[i].knot_positions.shape[0]
        return i, k // 2
    return 0, 0


def _pynec_feed_position(builder, currents):
    """Exact 3D feed point for PyNEC: the midpoint of the driven segment.
    NEC feeds at segment (n_seg+1)//2, so on a 1-segment feed edge the feed
    sits at the edge midpoint — not the wire's centre knot (`k//2`), which
    lands on an endpoint for a 2-knot wire. Mirrors `_pynec_feed_indices`'
    driven-tuple selection.
    """
    tuples = list(builder.build_wires())
    driven_name = None
    if hasattr(builder, "build_network"):
        net = builder.build_network()
        if net is not None and net.sources:
            driven_name = net.sources[0].port
    for i, t in enumerate(tuples):
        ev = t[3]
        name = t[4] if len(t) >= 5 else None
        if driven_name is not None:
            if name != driven_name:
                continue
        elif ev is None:
            continue
        if i >= len(currents):
            return None
        knots = currents[i].knot_positions
        n_seg = knots.shape[0] - 1
        if n_seg < 1:
            return knots[0].tolist() if knots.shape[0] else None
        mid_seg = (n_seg + 1) // 2  # 1-indexed driven segment
        return (0.5 * (knots[mid_seg - 1] + knots[mid_seg])).tolist()
    return None


def _pynec_feed_positions(builder, currents, multi_feed=False):
    """PyNEC analogue of `_feed_positions` (issue #571), gated by multi_feed:
    build_network() designs → declared feed ports (matched to their
    build_wires() tuple by name); inline-`ex` designs → each `ev`-driven tuple.
    Each marker sits on its wire's centre. Falls back to the single primary."""
    out = []
    if multi_feed:
        tuples = list(builder.build_wires())
        net = builder.build_network() if hasattr(builder, "build_network") else None

        def center(i):
            knots = currents[i].knot_positions
            return knots[knots.shape[0] // 2].tolist() if knots.shape[0] else None

        if net is not None:
            by_name = {t[4]: i for i, t in enumerate(tuples) if len(t) >= 5 and t[4]}
            for nm in _declared_feed_ports(type(builder)):
                i = by_name.get(nm)
                if i is not None and i < len(currents) and center(i) is not None:
                    out.append({"name": nm, "position": center(i)})
        else:
            for i, t in enumerate(tuples):
                if (t[3] if len(t) > 3 else None) is None or i >= len(currents):
                    continue
                if center(i) is not None:
                    nm = t[4] if len(t) >= 5 and t[4] else f"feed {len(out)}"
                    out.append({"name": nm, "position": center(i)})
    if out:
        return out
    pos = _pynec_feed_position(builder, currents)
    return [{"name": "feed", "position": pos}] if pos is not None else []


# ---------------------------------------------------------------------------
# Example factory
# ---------------------------------------------------------------------------


def _discover_variants(cls) -> tuple[str, ...]:
    """Names of every class-level `<name>_params` attribute (the variant
    convention used across the design library — e.g. `default_params`,
    `opt_params`, `z50_params`, `current_physical_params`). The
    returned list is suitable for a UI selector; the bare names (no
    `_params` suffix) are what the frontend sends back in the request.

    `default` is always first if present, so the UI lists it as the
    canonical starting point regardless of class attribute order.
    """
    suffix = "_params"
    found: list[str] = []
    for attr in dir(cls):
        if not attr.endswith(suffix) or attr.startswith("_"):
            continue
        v = getattr(cls, attr, None)
        # MappingProxyType / dict only — skip e.g. a method that happens
        # to end in _params.
        if not hasattr(v, "keys"):
            continue
        name = attr[: -len(suffix)]
        if name:
            found.append(name)
    # `default` first, rest in stable (alphabetical) order.
    found.sort(key=lambda n: (n != "default", n))
    return tuple(found)


def _serialize_param_values(params: dict) -> dict:
    """JSON-encode a params dict for shipping to the frontend.

    Complex values become {"re": ..., "im": ...} (matches the same
    shape `_rehydrate_param` accepts on the way back). Bool/int/float
    pass through. Anything exotic (None, strings that aren't enum
    options, etc.) passes through too — the frontend just ignores
    keys it doesn't have sliders for.
    """
    out: dict = {}
    for k, v in params.items():
        if isinstance(v, complex):
            out[k] = {"re": float(v.real), "im": float(v.imag)}
        else:
            out[k] = v
    return out


def _variant_params(cls, variant: str | None) -> dict:
    """Return the seed params dict for the named variant, overlaid on
    `default_params` (see `resolve_variant_params`). A variant need only
    list the keys it overrides — including nested `ui_params` hints, which
    deep-merge — and missing keys come from `default_params`. Falls back to
    `default_params` when variant is None, "default", or doesn't resolve to
    an attribute (stale frontend, unknown name)."""
    return resolve_variant_params(cls, variant)


def _ui_scalar(default_params: dict, key: str, default):
    ui = default_params.get("ui_params") or {}
    if key in ui and not isinstance(ui[key], dict):
        return ui[key]
    return default


_ARRAY_BASES = (
    Array1x2Builder,
    Array2x2Builder,
    Array1x4Builder,
    Array1x4GroupedBuilder,
    Array2x4Builder,
)


def _auto_target_z0(cls) -> float:
    """Default reference impedance for the SWR readout.

    Array designs scale 50 Ω by the element count (1×2 → 100, 2×2 → 200,
    2×4 → 400, ...) — the convention that each branch in the splitter
    sees 50 Ω after the chain of impedance transformers, so the
    combined driving point lands at N × 50.

    Everything else defaults to 50 Ω. Designs that violate either
    convention (turnstiles with per-port 50 Ω matching, designs tuned
    to 75 Ω, etc.) override via `ui_params["target_z0"]`.
    """
    if not issubclass(cls, _ARRAY_BASES):
        return 50.0
    try:
        b = cls()
        n_feeds = sum(1 for t in b.build_wires() if as_wire(t).ex is not None)
    except Exception:  # noqa: BLE001 — a design that will not construct gets the 50 ohm default; the real solve reports the failure
        return 50.0
    return 50.0 * max(1, n_feeds)


def _auto_multi_feed(cls) -> bool:
    """Detect whether the design has more than one feed.

    Two conventions, two signals (issue #570):

    * Inline-``ex`` designs: >1 wire carries an ``ex`` excitation in
      ``build_wires()`` — each is an independently driven feed.
    * ``build_network()`` designs: excitation comes from ``Driven`` sources,
      not the ``ex`` field, so the inline count is always 0. A network design
      is multi-feed when it has **>1 source** (=> >1 driving-point impedance in
      the per-feed table) or it explicitly declares **>1 physical feed port**
      via ``ui_params["feed_ports"]`` (a harness/split feed driven in phase
      from one source — one driving-point impedance but two feedpoints on the
      structure). Reachability over the branch graph is deliberately NOT used:
      it cannot tell a harness-split lazy-H from a log-periodic's chained
      feeder (see ``_declared_feed_ports``).

    When multi_feed is True the response shape switches to include a `feeds`
    array (per-port Z + V) and the frontend renders the per-feed table.
    Designs can still force the flag via ``ui_params["multi_feed"]``.
    """
    try:
        b = cls()
        net = b.build_network() if hasattr(b, "build_network") else None
        if net is not None:
            return len(net.sources) > 1 or len(_declared_feed_ports(cls)) > 1
        n_feeds = sum(1 for t in b.build_wires() if as_wire(t).ex is not None)
    except Exception:  # noqa: BLE001
        return False
    return n_feeds > 1


def _auto_default_view(cls) -> str:
    """Pick a 2D projection from the spans of the antenna's wires.

    Rule: if x_span is small (the antenna lies in the y-z plane —
    typical for dipoles, V's, loops, fan/bowtie variants), default to
    `yz`. Otherwise return the plane of the two largest spans (xy / yz
    / xz). The 0.5 m threshold catches feed-gap micro-offsets like
    fan_dipole's 0.22 m without flipping to xy.

    Hand-overridden via ui_params['default_view']; designs whose axis
    layout doesn't match this rule (vertical, moxonarray) supply the
    explicit value.
    """
    try:
        b = cls()
        pts = []
        for t in b.build_wires():
            w = as_wire(t)
            pts.append(w.p0)
            pts.append(w.p1)
        a = np.asarray(pts, dtype=float)
    except Exception:  # noqa: BLE001 — the derived view is a hint, not a contract; 'xy' is the safe default
        return "xy"
    sx = float(a[:, 0].max() - a[:, 0].min())
    sy = float(a[:, 1].max() - a[:, 1].min())
    sz = float(a[:, 2].max() - a[:, 2].min())
    if sx < 0.5:
        return "yz"
    spans = sorted([("x", sx), ("y", sy), ("z", sz)], key=lambda t: t[1], reverse=True)
    return "".join(sorted(s[0] for s in spans[:2]))


# Above this estimated b-spline basis count, a dense (or compressed) b-spline
# solve is minutes-per-knob-drag and the UI recommends the sinusoidal solver
# instead. Dense at 3,000 bases is a ~140 MB Z and ~10 s on a 4-core dev box —
# already past interactive; the whip benchmark sits at ~12,700.
_SINUSOIDAL_RECOMMEND_MIN_BASIS = 3000

# Backends that implement junction-node ports, in preference order — the
# allowlist a `PortAtEnd` design is restricted to. `bspline` stays FIRST
# because `_required_backends()[0]` becomes the design's default backend and
# the dense mixed-potential solver is the reference implementation for these
# ports. `sinusoidal-galerkin` joined in momwire#182 M5b: it holds the node's
# lumped charge outside the reaction integral and reproduces the B-spline port
# network entrywise to 3.4e-5 / 3.9e-6, which is what "widening this tuple"
# was waiting for. Caveat carried by the solver's own hard error, not by this
# list: its junction ports run in free space and over a PEC ground
# (momwire#191 removed the node-charge PEC image) but refuse FINITE grounds —
# the reflection-coefficient and Sommerfeld images of a point charge are not
# point charges — and reject mixed per-wire radii.
_JUNCTION_PORT_BACKENDS = ("bspline", "sinusoidal-galerkin")

# Backends that implement the SERIES vertex port (`PortAtVertex`, issue
# #898 / momwire#305's node gaps) — a wider list than the junction-port
# one: the iterative HMatrix/ArrayBlock solvers serve node gaps through
# the same dense port columns (Y) and, since momwire 0.28.1, drive them
# on the accelerated impedance route too; node gaps also run over EVERY
# ground model on both dense families (they ride the ordinary span — no
# node-charge machinery, so none of the junction-port ground caveats).
# `bspline` stays first for the same default-backend reason as above.
# `nec5` serves the port NATIVELY (EX at the shared knot, #898 piece 3);
# its tab exists only when the serving box resolves $NEC5_EXE, and an
# allowlist entry for an absent backend is simply not a tab — so listing
# it here enables the tab exactly where the engine exists.
_VERTEX_PORT_BACKENDS = (
    "bspline",
    "sinusoidal-galerkin",
    "hmatrix",
    "arrayblock",
    "nec5",
)


# Backend restriction copy, server-side (antennaknobs#1006 G2-5). It lived in
# the frontend as `RESTRICTED_BACKEND_REASON`, whose own comment said to
# broaden it "if _required_backends ever grows another cause" — G2-5 is that
# cause, and a reason served beside the restriction is what lets the gate stop
# carrying one hardcoded sentence for every cause. momwire's own prose is used
# for the axis COUPLINGS; this cause is antennaknobs' own restriction, so the
# sentence is antennaknobs'.
# ONE REASON PER CAUSE, and there are two — which is the bug retiring the
# frontend constant fixes rather than merely tidies. `RESTRICTED_BACKEND_REASON`
# says "only the B-spline and sinusoidal-Galerkin solvers implement them", and
# that is already FALSE for a vertex-port design: `dipoles.invvee_apex` allows
# five backends including NEC-5. The frontend comment asked for broadening "if
# _required_backends ever grows another cause"; it grew one at issue #898 and
# the copy did not follow.
_RESTRICTION_REASONS = {
    "junction_ports": (
        "This design attaches network elements at conductor ends "
        "(junction-node ports) — only the B-spline and sinusoidal-Galerkin "
        "solvers implement them, and NEC-2 has no equivalent card."
    ),
    "vertex_ports": (
        "This design attaches a network element in the middle of a conductor "
        "(a series vertex port) — the dense and accelerated momwire solvers "
        "serve it, and NEC-5 serves it natively, but the point-matched "
        "sinusoidal and razor solvers do not."
    ),
}


def _backend_restriction(required) -> dict | None:
    """The restriction with the reason for ITS cause, or None.

    Keyed off the allowlist identity rather than off a re-derivation: the two
    causes ARE the two tuples, so `is` on them cannot disagree with what
    `_required_backends` returned. A third cause that forgets a reason here
    gets a None reason rather than the wrong one — the gate then falls back to
    its generic copy, which is a worse message but not a false one.
    """
    if required is None:
        return None
    if required is _JUNCTION_PORT_BACKENDS:
        reason = _RESTRICTION_REASONS["junction_ports"]
    elif required is _VERTEX_PORT_BACKENDS:
        reason = _RESTRICTION_REASONS["vertex_ports"]
    else:
        reason = None
    return {"backends": list(required), "reason": reason}


def _has_stepped_radius_junction(cls, params=None) -> bool:
    """Whether any junction in this design joins wires of DIFFERENT radii.

    momwire refuses `extended_kernel=True` on such a deck
    (`_EK_STEPPED_RADIUS_JUNCTION_REFUSAL`, momwire#398 D2), so the panel warns
    before the user solves rather than letting the solve raise. Asked of the
    DESIGN because that is what the refusal is about; the backend and the
    kernel setting are the other two thirds of the condition and live on the
    other side.

    Computed the way momwire computes it: distinct radii among a junction's
    members, EXACT float equality — per-wire radii only ever differ when the
    caller asked them to, never from solver-side rounding. This reimplements
    the QUESTION, not the rule; the refusal stays momwire's.

    Cheap enough to ask per design: `flat_wires_to_polylines` is a pure
    function over the built wires, no solver and no engine. Measured 27 ms on
    `verticals.elt_whip` — 4067 wires, the catalog's largest and its only
    stepped-junction design — and sub-millisecond on everything else.

    Radius precedence mirrors `MomwireEngine`: an explicit per-wire `spec`
    beats the design's `build_wire_material()`, which beats the 0.5 mm
    idealisation. The web's `wire_radius` override only moves the DEFAULT, so
    it cannot create or remove a step — a design with one radius everywhere
    stays uniform whatever the user sets.
    """
    try:
        builder = _build_builder(cls, params or {})
        tups = builder.build_wires()
        translated = flat_wires_to_polylines(tups)
        junctions = translated.get("junctions") or []
        if not junctions:
            return False
        specs = translated["polyline_specs"]
        stock = builder.build_wire_material()
        default = stock.radius if stock is not None else 0.0005
        radii = [s.radius if s is not None else default for s in specs]
        return any(len({radii[w] for w, _end in jw}) > 1 for jw in junctions)
    except Exception:  # noqa: BLE001 — a design that will not build has its
        # real error surfaced through the normal solve path, exactly as
        # `_required_backends` does; a hint must never be the thing that
        # breaks a listing.
        return False


def _has_buried_wire(cls, params=None) -> bool:
    """Whether any conductor in this design sits BELOW the interface (z < 0).

    The design-side third of momwire's buried refusal: `HMatrixSolver` and
    `ArrayBlockSolver` refuse `extended_kernel=True` on a deck with a buried
    wire (momwire#553), and the ACA/element-block panels need to say so before
    the solve rather than after it raises.

    Distinct from `ground_requirement == "sommerfeld"`, which is the nearest
    existing field and NOT the same fact: that one is a statement about which
    ground MODEL the design needs to mean anything, declared by hand in
    `ui_params`. This is a measurement of the geometry. They agree on today's
    catalog, and relying on that agreement would be reading a hand-written
    hint as if it were geometry — the failure `_has_stepped_radius_junction`
    was written to avoid.

    STRICTLY below. A wire lying exactly on the interface is the `contact`
    case, which is a different axis value with different refusals; treating
    z == 0 as buried would grey out the extended kernel on every ground-plane
    design in the catalog.
    """
    try:
        builder = _build_builder(cls, params or {})
        translated = flat_wires_to_polylines(builder.build_wires())
        return any(z < 0.0 for poly in translated["polylines"] for (_x, _y, z) in poly)
    except Exception:  # noqa: BLE001 — same contract as the stepped-junction
        # helper above: a design that will not build surfaces its real error
        # on the solve path, and a hint never breaks a listing.
        return False


@lru_cache(maxsize=None)
def _required_backends(cls) -> tuple[str, ...] | None:
    """Backend allowlist a design is restricted to, or None (no restriction).

    Today's only restriction: a design whose network has any `PortAtEnd`
    resolves to junction-node ports, which only the dense B-spline solver
    and the sinusoidal-Galerkin solver implement (momwire#172 / momwire#182 —
    the point-matched sinusoidal and iterative HMatrix/ArrayBlock solvers
    raise NotImplementedError, and NEC-2 has no equivalent card at all, so
    `PyNECEngine` rejects the design at construction, issue #579). DERIVED
    from the flattened network spec rather than declared per design, so the
    capability cannot drift from what the design actually does. The frontend
    disables the other backend tabs (with an explanatory tooltip) and coerces
    an active disallowed selection to the first allowed entry on design
    switch; the solvers' hard errors remain the enforcement. Any failure to
    build the network falls back to None — the design's real error surfaces
    through the normal solve path. A future momwire release that widens
    junction-port support only needs to widen `_JUNCTION_PORT_BACKENDS`."""
    try:
        net = _build_builder(cls, {}).build_network()
    except Exception:  # noqa: BLE001 — capability probe at registry build — a design that cannot build a network simply has no junction ports
        return None
    if net is None:
        return None
    has_end = any(isinstance(p, PortAtEnd) for p in net.ports.values())
    has_vertex = any(isinstance(p, PortAtVertex) for p in net.ports.values())
    if has_end:
        # A design carrying BOTH port kinds is bound by the narrower
        # junction-port list (the vertex list is a superset of it).
        return _JUNCTION_PORT_BACKENDS
    if has_vertex:
        return _VERTEX_PORT_BACKENDS
    return None


@lru_cache(maxsize=None)
def _recommended_backend(cls) -> str | None:
    """Recommend a default solver for the design, or None to let the UI keep
    its own default (the dense B-spline path).

    Returns "arrayblock" for true grid arrays — multiple electrically separate
    elements with at least one repeated shape — where the element-aware block
    solver is dramatically faster than the dense default (e.g. bowtiearray2x4:
    ~1 s vs ~8 s). Single-element designs, and multi-element designs whose
    elements are all distinct (Yagi-style), keep the dense default so their
    basis/results are unchanged.

    Returns "sinusoidal" for benchmark-class meshes — thousands of explicit
    segments in one connected structure (e.g. verticals.elt_whip: 4,392
    segments in 4,067 junction-split pieces ⇒ ~12,700 b-spline bases) —
    where every b-spline-family solver takes minutes per solve and a few
    concurrent requests (live solve + sweep + norm-check) can exhaust a
    development machine's memory, while the sinusoidal solver answers in
    seconds. The frontend withholds the solve and warns when the selected
    solver conflicts with this recommendation (`comboInappropriate`).

    Detection is geometry-only (no solve) and any failure falls back to None.

    Memoised per design class: it already runs only once per design at registry
    build (the result is baked into the immutable `AntennaExample`, which the
    /examples endpoint and the frontend read at runtime — a slider change never
    re-runs it), but `lru_cache` makes that a hard guarantee regardless of
    call site.
    """
    try:
        from momwire.array_block import wire_to_element

        builder = _build_builder(cls, {})
        # B-spline basis estimate without meshing: explicit segments plus
        # degree (2) boundary bases per wire piece — the junction-split
        # inflation exactly (issue momwire#138: those extra bases are the
        # physics of junction current discontinuities, not overhead).
        # Designs that defer segmentation to the app (nseg None) raise on
        # int() and fall through to the array detection below.
        try:
            wires = builder.build_wires()
            est_basis = sum(int(w[2]) for w in wires) + 2 * len(wires)
            if est_basis > _SINUSOIDAL_RECOMMEND_MIN_BASIS:
                return "sinusoidal"
        except Exception:  # noqa: BLE001 — designs that defer segmentation raise on int(); fall through to the array detection below
            pass
        eng = _make_momwire_engine({}, builder)
        polylines = [np.asarray(p, dtype=float) for p in eng._polylines]
    except Exception:  # noqa: BLE001 — the recommendation is geometry-only and advisory; any failure means 'no recommendation'
        return None
    if len(polylines) < 2:
        return None
    wire_elem, n_elem = wire_to_element(polylines)
    # array-block only pays off for a genuine grid array: several elements where
    # ONE shape repeats many times (so per-shape block reuse dominates). Require
    # at least 4 elements — below that the speedup is marginal and 2-element
    # symmetric things (a split dipole, a 1x2) are ambiguous.
    if n_elem < 4:
        return None
    # Signature each element by its points recentred on its own centroid, then
    # require repetition to *dominate*: at least half the elements must be
    # duplicates of another (len(sigs) * 2 <= n_elem). The earlier test
    # (len(sigs) < n_elem) fired on a single repeated pair, which wrongly tagged
    # Yagis (their equal-length directors collapse to one signature while the
    # driven element and reflector stay distinct) as arrays.
    sigs = set()
    for e in range(n_elem):
        pts = np.vstack(
            [polylines[w] for w in range(len(polylines)) if wire_elem[w] == e]
        )
        pts = pts - pts.mean(axis=0)
        key = np.round(pts / 1e-4).astype(np.int64)
        key = key[np.lexsort(key.T)]
        sigs.add(key.tobytes())
    return "arrayblock" if len(sigs) * 2 <= n_elem else None


def _derive_sweep_policy(ui: dict) -> SweepPolicy:
    """Build a SweepPolicy from a `ui_params` dict's `sweep_policy` entry.

    Accepts the positional 3-tuple `(anchor, lo_factor, hi_factor)` form or the
    dict form (which can opt into named fields like `band_locked` without
    supplying every positional; missing fields fall back to the dataclass
    defaults). Anything else yields the default policy. Takes any ui dict, so
    the same derivation runs for the default's ui_params and for each variant's
    deep-merged ui_params (see `variant_ui` in `_make_example`)."""
    raw = ui.get("sweep_policy")
    if isinstance(raw, (tuple, list)) and len(raw) == 3:
        return SweepPolicy(
            anchor=str(raw[0]),
            lo_factor=float(raw[1]),
            hi_factor=float(raw[2]),
        )
    if isinstance(raw, dict):
        d = DEFAULT_SWEEP_POLICY
        return SweepPolicy(
            anchor=str(raw.get("anchor", d.anchor)),
            lo_factor=float(raw.get("lo_factor", d.lo_factor)),
            hi_factor=float(raw.get("hi_factor", d.hi_factor)),
            band_locked=bool(raw.get("band_locked", d.band_locked)),
        )
    return DEFAULT_SWEEP_POLICY


# Presentation fields a variant's explicit ui_params may move per-variant
# (forwarded through variant_ui["params"] and overlaid on the base schema by
# the frontend). Values/defaults are variant_values' job, never listed here.
# `hidden` only HIDES a base-visible knob for that variant (the value still
# flows through solves via variant_values); it cannot unhide a knob hidden at
# the design level — those never enter param_schema at all.
_VARIANT_SPEC_KEYS = ("min", "max", "step", "precision", "unit", "label", "hidden")


def _make_example(name: str, cls, *, defer_hints: bool = False) -> AntennaExample:
    dp = dict(cls.default_params)
    ui = dict(dp.get("ui_params") or {})

    # UI hints that need the built geometry — multi_feed, default_view, the
    # array target_z0, and the recommended array-block backend — are derived
    # by running the builder. They're computed once and memoised in `hints()`.
    #
    # Built-in designs prime them eagerly at registration (defer_hints=False)
    # so /examples and the array-block seed are correct up front. User designs
    # defer them (defer_hints=True): a slow or hanging build_wires never runs at
    # startup or on a page refresh — only when that design is actually selected
    # and solved, where the builder runs anyway and the closures fold the hints
    # into the solve/geometry response. A design can pin any hint statically in
    # ui_params to override the derived value.
    view_override = _ui_scalar(dp, "default_view", None)
    z0_override = _ui_scalar(dp, "target_z0", None)
    multi_feed_override = _ui_scalar(dp, "multi_feed", None)
    notes = _ui_scalar(dp, "notes", None)

    _hints: dict[str, Any] = {}

    def hints() -> dict[str, Any]:
        if not _hints:
            _hints["default_view"] = (
                str(view_override)
                if view_override is not None
                else _auto_default_view(cls)
            )
            _hints["target_z0"] = float(
                z0_override if z0_override is not None else _auto_target_z0(cls)
            )
            _hints["multi_feed"] = bool(
                multi_feed_override
                if multi_feed_override is not None
                else _auto_multi_feed(cls)
            )
            # A backend restriction trumps the fit-based recommendation: the
            # recommender's geometry heuristics (array detection, mesh size)
            # don't know about solver capabilities, and recommending a
            # backend the design cannot run would seed a guaranteed failure.
            required = _required_backends(cls)
            _hints["requires_backends"] = required
            _hints["backend_restriction"] = _backend_restriction(required)
            _hints["has_stepped_radius_junction"] = _has_stepped_radius_junction(cls)
            _hints["has_buried_wire"] = _has_buried_wire(cls)
            _hints["default_backend"] = (
                required[0] if required else _recommended_backend(cls)
            )
        return _hints

    # Grid-level layout config (reserved ui_params["layout"]). A dict today
    # carrying {"columns": int}; ignore non-dicts so a stray value can't
    # break registration. None keeps the responsive auto-flow grid.
    layout_raw = ui.get("layout")
    grid_layout = dict(layout_raw) if isinstance(layout_raw, dict) else None

    meas_range = (
        ui.get("meas_freq_range")
        if not isinstance(ui.get("meas_freq_range"), dict)
        else None
    )
    bands_override = ui.get("bands") if not isinstance(ui.get("bands"), dict) else None
    sweep_policy = _derive_sweep_policy(ui)

    # Band tabs default to the HF amateur set in canonical order. The
    # frontend snaps to whichever band contains the design's native
    # `freq` (looked up from the param schema's freq default) — see
    # the useEffect on currentExample in App.tsx. Designs can still
    # override via ui_params['bands'].
    if bands_override is not None:
        bands = tuple(BandSpec(*b) for b in bands_override)
    else:
        bands = DEFAULT_AMATEUR_BANDS

    param_schema = _derive_schema(dp)
    has_design_freq = "design_freq" in dp

    # A native freq outside every band tab would strand the frontend's
    # design-switch snap on its bands[0] fallback — 160 m for the default
    # HF set — framing a 406 MHz whip for a 95 m wavelength and dragging
    # measFreq along with it (issue #390). Synthesize a band covering the
    # native freq instead: the window comes from ui_params
    # ["meas_freq_range"] when it brackets the freq (deck imports seed it
    # from the FR card), else ±1.5%. Fixed-geometry designs (no
    # design_freq param) get JUST the synthetic band — the tabs can't
    # retune them, so the HF list is dead weight; retunable designs keep
    # their list with the synthetic band appended. An explicit bands=()
    # override still suppresses the row entirely.
    native_freq = float(dp["freq"]) if "freq" in dp else None
    if (
        bands
        and native_freq is not None
        and not any(b.min_mhz <= native_freq <= b.max_mhz for b in bands)
    ):
        if meas_range and float(meas_range[0]) <= native_freq <= float(meas_range[1]):
            lo, hi = float(meas_range[0]), float(meas_range[1])
        else:
            lo, hi = 0.985 * native_freq, 1.015 * native_freq
        label = f"{native_freq:g} MHz"
        synth = BandSpec(label, label, native_freq, lo, hi)
        bands = (synth,) if not has_design_freq else (*bands, synth)

    variants = _discover_variants(cls)

    # Wire-material designs (issue #318): a `wire_type` param means the
    # solve responses carry wire_length_m / wire_weight_g (see
    # _wire_material_results) — surface them as Info-pane result rows.
    # The weight row is the POTA question in one number: how many grams
    # of wire buy how much bandwidth and how many tenths of a dB.
    result_schema: tuple = ()
    if "wire_type" in dp:
        result_schema = (
            ResultFieldSpec(
                field="wire_length_m", label="wire length", precision=1, unit=" m"
            ),
            ResultFieldSpec(
                field="wire_weight_g", label="wire weight", precision=1, unit=" g"
            ),
        )

    # Per-variant UI hints. A variant's `ui_params` deep-merges over the
    # default's (resolve_variant_params), so a variant can flip a single nested
    # hint (e.g. sweep_policy.band_locked) without restating the subtree. We
    # emit only the variants whose derived hints differ from the design-level
    # (default) value; the frontend falls back to the top-level field otherwise.
    # Extensible per-variant map so more hints can move per-variant later
    # without another /examples contract change.
    #
    # Besides sweep_policy, per-param presentation hints (slider min/max/step,
    # precision, unit, label) forward under "params" — EXPLICIT hints only,
    # diffed against the default's ui_params. Deliberately NOT a diff of
    # re-derived schemas: the auto-derivation windows track each variant's
    # *values* (a flat variant's angle_deg=0 would auto-window to a useless
    # -1..1), so only hints a variant actually authors move with it. First
    # user: dipoles.invvee, whose long-wire variants carry their own
    # length_factor slider ranges.
    variant_ui: dict[str, dict[str, Any]] = {}
    for v in variants:
        if v == "default":
            continue
        v_ui = dict(resolve_variant_params(cls, v).get("ui_params") or {})
        hints_v: dict[str, Any] = {}
        v_sweep = _derive_sweep_policy(v_ui)
        if v_sweep != sweep_policy:
            hints_v["sweep_policy"] = v_sweep
        p_over: dict[str, dict[str, Any]] = {}
        for pname, hint in v_ui.items():
            if not isinstance(hint, Mapping):
                continue
            base_hint = ui.get(pname)
            base_hint = base_hint if isinstance(base_hint, Mapping) else {}
            diff = {
                k: hint[k]
                for k in _VARIANT_SPEC_KEYS
                if k in hint and hint[k] != base_hint.get(k)
            }
            if diff:
                p_over[pname] = diff
        if p_over:
            hints_v["params"] = p_over
        if hints_v:
            variant_ui[v] = hints_v

    def _design_freq_default(req: dict) -> float:
        # The active variant's `freq` is the right fallback when the
        # request hasn't supplied design_freq_mhz yet — different
        # variants of one design can target different bands (e.g.
        # hexbeam's opt vs default).
        vp = _variant_params(cls, req.get("variant"))
        return float(vp.get("freq", 14.0))

    def _req_freqs(req: dict) -> tuple[float, float]:
        # One validated (design_freq, meas_freq) pair for every solve-forming
        # closure below — the request values are client JSON and must be
        # positive and finite before they reach a wavelength division or the
        # MoM kernel (issue #347).
        design_freq = _positive_finite(
            "design_freq_mhz", req.get("design_freq_mhz", _design_freq_default(req))
        )
        meas_freq = _positive_finite(
            "measurement_freq_mhz", req.get("measurement_freq_mhz", design_freq)
        )
        return design_freq, meas_freq

    def count_basis(req: dict):
        """Total wire segments (≈ MoM basis functions, the N×N matrix dim) the
        request would build. Geometry-only (cheap) — runs build_wires but no
        solve. Returns None if the geometry can't be built; the real solve then
        surfaces the underlying error instead of a spurious size rejection."""
        try:
            builder = _build_builder(cls, req)
            return sum(int(w[2]) for w in builder.build_wires())
        except Exception:  # noqa: BLE001 — size probe only — returning None lets the real solve surface the underlying error instead of a spurious size rejection
            return None

    def momwire_solve(req: dict, cancel=None) -> dict:
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        # For design_freq-sized designs the geometry computes from
        # design_freq via build_wires(); apply the request's
        # design_freq_mhz so dragging the design-freq slider actually
        # retunes the antenna. Top-level designs don't carry the
        # parameter so the attribute write would be silently absorbed
        # into _params and never read — guard on has_design_freq.
        if has_design_freq:
            builder.design_freq = design_freq
        plane, planes = _apply_plane(builder, req)
        eng = _make_momwire_engine(req, builder, cancel=cancel)
        t0 = time.perf_counter()
        zs = [_json_safe_z(z) for z in eng.impedance()]
        currents = eng.current_distribution()
        solve_ms = (time.perf_counter() - t0) * 1e3
        feed_wire_idx, feed_knot_idx = _feed_indices(eng, currents)
        z_primary = zs[0] if zs else complex(0.0, 0.0)
        out = {
            "geometry": name,
            # Solver advisories from this solve (#1144). Advisory only: the UI
            # must render them as notes, not failures.
            "advisories": _solver_advisories(eng),
            "wires": _pack_wires(currents),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _feed_position(eng, currents),
            "feed_positions": _feed_positions(eng, currents, hints()["multi_feed"]),
            "z_in_re": float(z_primary.real),
            "z_in_im": float(z_primary.imag),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "solve_ms": solve_ms,
            "ground": bool(req.get("ground", False)),
            "height_m": 0.0,
            # Ground constants + applied-model label (+ the packed terrain
            # when the spec is faceted) — see _momwire_ground_fields.
            **_momwire_ground_fields(eng, req),
            "z0_ohms": hints()["target_z0"],
            # Geometry-derived UI hints, folded into the response so user
            # designs (which defer them) get correct values the moment they're
            # selected, without running the builder at registration.
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            # Fraction of input power actually radiated (1.0 unless the design
            # has resistive loads, e.g. a terminated rhombic / T2FD);
            # current_distribution() above populated it on the engine.
            "radiation_efficiency": float(getattr(eng, "_excited_efficiency", 1.0)),
            # Per-branch network dissipation from the MNA solve (issue
            # #299), with the design's optional display renames applied
            # (ui_params["budget_labels"], issue #489).
            "power_budget": _budget_rows(eng, builder),
            # Source input power in watts: the server's gain normaliser is
            # η₀k²/(8π·P_in), which is what makes the plot GAIN (load and
            # ground losses live inside P_in, so no efficiency multiply).
            "input_power_w": float(eng.input_power()),
            **_wire_material_results(builder),
            **_rig_report_results(builder),
            # Generic self-describing readout rows (issue #712): the same
            # duck-typed discovery, rendered by one frontend component.
            **_readout_rows_results(builder),
        }
        if planes is not None:
            # Measurement plane (issue #652 c): which port this solve is
            # referenced to, and which the picker may offer.
            out["plane"] = plane
            out["planes"] = planes
        # Array Block coupling-path diagnostics (issue #613): absent for
        # every other engine/model (eng.solver_diag() only returns a dict
        # for an ArrayBlockSolver-backed solve).
        solver_diag = eng.solver_diag()
        if solver_diag is not None:
            out["solver_diag"] = solver_diag
        if hints()["multi_feed"] and len(zs) > 1:
            # Pull per-feed drive voltages off the engine so the frontend
            # can render each feed's phase indicator. MomwireEngine stores
            # _feeds = [(polyline_idx, arclength, voltage)]; fall back to
            # 1+0j (the canonical unit drive) when missing.
            voltages = [f[2] for f in (getattr(eng, "_feeds", None) or [])]
            voltages += [complex(1.0, 0.0)] * (len(zs) - len(voltages))
            out["feeds"] = [
                {
                    "z_re": float(z.real),
                    "z_im": float(z.imag),
                    "v_re": float(v.real),
                    "v_im": float(v.imag),
                }
                for z, v in zip(zs, voltages, strict=True)
            ]
        return out

    def momwire_geometry(req: dict) -> dict:
        # Geometry-only snapshot: build the engine (cheap — geometry is
        # resolved in the constructor) and read its wire knot positions
        # without solving. The frontend draws this immediately on antenna
        # selection so a large design's shape shows up right away instead of
        # waiting tens of seconds for the MoM solve. Mirrors momwire_solve's
        # builder setup but returns zero currents and omits impedance / far
        # field (the live solve fills those in).
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        # THE PREVIEW MUST NOT CARRY A SOLVER'S REFUSAL.
        #
        # momwire#814 moved the buried refusal into engine CONSTRUCTION, so
        # building with the request's `momwire_model` makes a refused
        # solver+design combination fail here — in the drawing, before any
        # solve is decided. A user switching to a buried design with an
        # accelerated backend selected then saw the raw engine error and no
        # gate at all, because the client's preview-error path never releases
        # the gate that would have withheld the solve and shown momwire's own
        # sentence. This endpoint's docstring already promised the preview is
        # solver-independent; it was not.
        #
        # NOT "always use the default model", which was the obvious fix and is
        # wrong: measured across the roster, `geometry_distribution()` IS
        # model-dependent for `razor-2p` — on arrays.bowtiearray1x2 its feed
        # KNOT INDEX is 1 where every other model gives 0, because the
        # two-point lane snaps the feed to a different grid. Drawing the feed
        # marker in the wrong place on every razor preview would trade a rare
        # blank canvas for a permanent quiet lie.
        #
        # So: honour the request, and fall back only when the engine refuses
        # it. If the fallback fails too, the ORIGINAL error is re-raised —
        # a deck that genuinely cannot build has nothing to draw, and that
        # error is about the DESIGN, which the user did choose.
        try:
            eng = _make_momwire_engine(req, builder)
        except Exception as refusal:  # noqa: BLE001 — the refusal's TYPE is
            # the solver's business and varies (ValueError today,
            # NotImplementedError elsewhere); narrowing here would silently
            # stop routing around whichever one a future refusal raises. The
            # original is re-raised when the fallback fails too, so nothing is
            # swallowed — only deferred.
            fallback = {k: v for k, v in req.items() if k != "momwire_model"}
            try:
                eng = _make_momwire_engine(fallback, builder)
            except Exception:  # noqa: BLE001 — a deck that cannot build on
                # the default model either has nothing to draw; surface the
                # ORIGINAL error, which is about the design the user chose.
                raise refusal from None
        geom = eng.geometry_distribution()
        feed_wire_idx, feed_knot_idx = _feed_indices(eng, geom)
        return {
            "geometry": name,
            "wires": _pack_wires(geom),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _feed_position(eng, geom),
            "feed_positions": _feed_positions(eng, geom, hints()["multi_feed"]),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "ground": bool(req.get("ground", False)),
            "z0_ohms": hints()["target_z0"],
            # Carry the geometry-derived hints on the fast preview too: it's the
            # first request fired on selection, so a deferred user design gets
            # its multi_feed / default_view here, before the live solve lands.
            # default_backend lets the frontend seed the array-block solver from
            # the preview and then fire the first solve — no /examples-descriptor
            # dependency, so this stays correct if a design's hints go lazy.
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            "default_backend": hints()["default_backend"],
            "preview": True,
        }

    def pynec_build(req: dict) -> dict:
        # web.pynec_backend.pattern() expects this to return a build
        # dict with at least:
        #   context      — a nec_context with geometry built, ground
        #                  card applied, and excitation cards in place
        #   feed_seg     — 1-indexed segment number of the source
        #                  (only consulted by the default _run_solve()
        #                  excite path; ours supplies pynec_pattern_excite
        #                  so it's only present for parity)
        #   feed_tag     — NEC wire tag carrying the feed
        #   n_per_wire   — historical, _run_solve threads it through
        #                  but doesn't actually use it
        #   ground       — bool (informational; gn_card already on the
        #                  context)
        #   ground_fast  — bool (same)
        #   z_offset     — antenna height above ground, surfaced in
        #                  the pattern response
        #   _engine      — keep the PyNECEngine alive so the
        #                  underlying nec_context isn't released
        #                  before rp_card runs
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        # The pattern must be the same solve the impedance readout shows —
        # a picked plane (issue #652 c) moves both together.
        _apply_plane(builder, req)
        eng = _make_pynec_engine(req, builder)
        # Find the first excited wire to fill the feed_seg / feed_tag
        # parity fields. PyNECEngine.excitation_pairs is (tag, sub_seg,
        # voltage); take the first.
        feed_tag, feed_seg, _v = (eng.excitation_pairs or [(1, 1, 0)])[0]
        return {
            "context": eng.c,
            "feed_seg": int(feed_seg),
            "feed_tag": int(feed_tag),
            "n_per_wire": 1,
            "ground": bool(req.get("ground", False)),
            "ground_fast": bool(req.get("ground_fast", False)),
            "z_offset": 0.0,
            "_engine": eng,
        }

    def pynec_pattern_excite(b: dict, freq_mhz: float) -> None:
        # PyNECEngine already applied the gn_card and ex_card during
        # _build_geometry, so the pattern endpoint only needs to set
        # the frequency and execute. Reusing _run_solve() would add a
        # second ex_card on top of the one already in place.
        c = b["context"]
        c.fr_card(0, 1, float(freq_mhz), 0)
        c.xq_card(0)

    def pynec_solve(req: dict) -> dict:
        # Mirror momwire_solve but route through PyNECEngine. Response
        # shape is identical so the frontend renders the result the
        # same way; the `solver` field gets stamped to "pynec" by
        # server.solve()'s outer wrapper.
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        plane, planes = _apply_plane(builder, req)
        eng = _make_pynec_engine(req, builder)
        t0 = time.perf_counter()
        zs = [_json_safe_z(z) for z in eng.impedance()]
        currents = eng.current_distribution()
        solve_ms = (time.perf_counter() - t0) * 1e3
        feed_wire_idx, feed_knot_idx = _pynec_feed_indices(builder, currents)
        z_primary = zs[0] if zs else complex(0.0, 0.0)
        out = {
            "geometry": name,
            # Solver advisories from this solve (#1144). Advisory only: the UI
            # must render them as notes, not failures.
            "advisories": _solver_advisories(eng),
            "wires": _pack_wires(currents),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _pynec_feed_position(builder, currents),
            "feed_positions": _pynec_feed_positions(
                builder, currents, hints()["multi_feed"]
            ),
            "z_in_re": float(z_primary.real),
            "z_in_im": float(z_primary.imag),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "solve_ms": solve_ms,
            "ground": bool(req.get("ground", False)),
            "height_m": 0.0,
            # Ship the eps_r/sigma of the ground the engine actually solved
            # over: the frontend's far-field cut applies PEC image + Fresnel
            # with these, so finite grounds get their real constants (tracks
            # NEC's rp_card pattern to ~0.2 dB) while ground_model="pec" and
            # free space keep the PEC placeholders (ρ→−1).
            "ground_eps_r": (
                eng.ground[1] if isinstance(eng.ground, tuple) else _PEC_GROUND_EPS_R
            ),
            "ground_sigma": (
                eng.ground[2] if isinstance(eng.ground, tuple) else _PEC_GROUND_SIGMA
            ),
            "ground_model_applied": _pynec_ground_applied(eng.ground),
            "z0_ohms": hints()["target_z0"],
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            # Same fields as the momwire path, so switching engines in the UI
            # keeps the far-field plot meaning GAIN. current_distribution()
            # set both from the solved feed/load currents.
            "radiation_efficiency": float(getattr(eng, "_excited_efficiency", 1.0)),
            "power_budget": _budget_rows(eng, builder),
            "input_power_w": float(getattr(eng, "_excited_p_in", None) or 0.0),
            **_wire_material_results(builder),
            **_rig_report_results(builder),
            # Generic self-describing readout rows (issue #712): the same
            # duck-typed discovery, rendered by one frontend component.
            **_readout_rows_results(builder),
        }
        if planes is not None:
            # Same plane fields as the momwire path (issue #652 c).
            out["plane"] = plane
            out["planes"] = planes
        if _requested_ground_model(req) == "terrain":
            # PyNEC terrain hybrid (issue #553): the engine solved over the
            # crest-medium Sommerfeld spec (so ground_eps_r/sigma above are
            # already the crest constants); re-stamp the applied label and
            # attach the facet model so the server's cut physics applies the
            # per-facet reflection — the same response contract as momwire.
            out["ground_model_applied"] = "terrain"
            gt = _pack_terrain(_terrain_from_request(req))
            marker = _terrain_marker(req)
            if marker:
                gt["marker"] = marker
            out["ground_terrain"] = gt
        if hints()["multi_feed"] and len(zs) > 1:
            # PyNECEngine.excitation_pairs is [(tag, sub_seg, voltage)];
            # pull the voltage off each so per-feed phase comes through.
            voltages = [v for _t, _s, v in (eng.excitation_pairs or [])]
            voltages += [complex(1.0, 0.0)] * (len(zs) - len(voltages))
            out["feeds"] = [
                {
                    "z_re": float(z.real),
                    "z_im": float(z.imag),
                    "v_re": float(v.real),
                    "v_im": float(v.imag),
                }
                for z, v in zip(zs, voltages, strict=True)
            ]
        return out

    def nec5_solve(req: dict) -> dict:
        # Mirror pynec_solve through the licensed NEC-5 binary: one
        # subprocess run serves Z, currents and the power budget
        # (NEC5Engine.solve_snapshot), and the response shape is identical
        # so the frontend renders it unchanged.
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        plane, planes = _apply_plane(builder, req)
        eng = _make_nec5_engine(req, builder)
        t0 = time.perf_counter()
        zs_raw, currents, _budget = eng.solve_snapshot()
        zs = [_json_safe_z(z) for z in zs_raw]
        solve_ms = (time.perf_counter() - t0) * 1e3
        feed_wire_idx, feed_knot_idx = _pynec_feed_indices(builder, currents)
        z_primary = zs[0] if zs else complex(0.0, 0.0)
        finite = isinstance(eng.ground, tuple) and eng.ground[0] == "finite"
        out = {
            "geometry": name,
            # Solver advisories from this solve (#1144). Advisory only: the UI
            # must render them as notes, not failures.
            "advisories": _solver_advisories(eng),
            "wires": _pack_wires(currents),
            "feed_wire_index": feed_wire_idx,
            "feed_knot_index": feed_knot_idx,
            "feed_position": _pynec_feed_position(builder, currents),
            "feed_positions": _pynec_feed_positions(
                builder, currents, hints()["multi_feed"]
            ),
            "z_in_re": float(z_primary.real),
            "z_in_im": float(z_primary.imag),
            "design_freq_mhz": design_freq,
            "measurement_freq_mhz": meas_freq,
            "lambda_design_m": C_LIGHT / (design_freq * 1e6),
            "solve_ms": solve_ms,
            "ground": bool(req.get("ground", False)),
            "height_m": 0.0,
            "ground_eps_r": eng.ground[1] if finite else _PEC_GROUND_EPS_R,
            "ground_sigma": eng.ground[2] if finite else _PEC_GROUND_SIGMA,
            "ground_model_applied": _nec5_ground_applied(eng.ground),
            "z0_ohms": hints()["target_z0"],
            "multi_feed": hints()["multi_feed"],
            "default_view": hints()["default_view"],
            "radiation_efficiency": float(getattr(eng, "_excited_efficiency", 1.0)),
            "power_budget": _budget_rows(eng, builder),
            "input_power_w": float(getattr(eng, "_excited_p_in", None) or 0.0),
            **_wire_material_results(builder),
            **_rig_report_results(builder),
            **_readout_rows_results(builder),
        }
        if planes is not None:
            out["plane"] = plane
            out["planes"] = planes
        if _requested_ground_model(req) == "terrain":
            # Same crest-medium hybrid as the PyNEC path: the engine solved
            # flat Sommerfeld at the crest constants; the facets enter in
            # the server's far-field composition via ground_terrain.
            out["ground_model_applied"] = "terrain"
            gt = _pack_terrain(_terrain_from_request(req))
            marker = _terrain_marker(req)
            if marker:
                gt["marker"] = marker
            out["ground_terrain"] = gt
        if hints()["multi_feed"] and len(zs) > 1:
            # NEC5Engine._sources is [(wire_idx, ex_type, value)] in feed
            # order; value is volts for EX 0 and amps for EX 4.
            values = [v for _i, _t, v in eng._sources]
            values += [complex(1.0, 0.0)] * (len(zs) - len(values))
            out["feeds"] = [
                {
                    "z_re": float(z.real),
                    "z_im": float(z.imag),
                    "v_re": float(v.real),
                    "v_im": float(v.imag),
                }
                for z, v in zip(zs, values, strict=True)
            ]
        return out

    def nec5_pattern(req: dict) -> dict:
        # Same response contract as pynec_backend.pattern (46 thetas
        # 0..90 x 73 phis 0..360, gains in dBi), from one RP deck run.
        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        _apply_plane(builder, req)
        eng = _make_nec5_engine(req, builder)
        n_theta, n_phi = 46, 73
        del_theta = 90.0 / (n_theta - 1)
        del_phi = 360.0 / (n_phi - 1)
        t0 = time.perf_counter()
        text = eng._run(
            eng.deck([meas_freq], rp=(n_theta, n_phi - 1, del_theta, del_phi))
        )
        gains_by_angle = eng._parse_radiation_patterns(text)
        pattern_ms = (time.perf_counter() - t0) * 1e3
        thetas = [ti * del_theta for ti in range(n_theta)]
        phis = [pi * del_phi for pi in range(n_phi)]
        gains = [
            [gains_by_angle[(round(th, 2), round(ph, 2))] for ph in phis]
            for th in thetas
        ]
        return {
            "available": True,
            "geometry": name,
            "ground": bool(req.get("ground", False)),
            "ground_fast": bool(req.get("ground_fast", False)),
            "height_m": 0.0,
            "measurement_freq_mhz": meas_freq,
            "theta_deg": thetas,
            "phi_deg": phis,
            "gain_dbi": gains,
            "pattern_ms": pattern_ms,
        }

    def params_source(req: dict) -> str:
        # Overlay the request's live knob values onto the chosen variant's
        # params (which still carry ui_params and the design's real nesting —
        # bands tuples etc.), then serialise. Knob-values-only by default
        # (include_ui), matching the manual "copy the printed values" workflow
        # this replaces; pass include_ui=true to emit a wholesale block.
        from antennaknobs.serialize import _precision_map
        from antennaknobs.serialize import params_source as _emit

        variant = req.get("variant")
        base = dict(_variant_params(cls, variant))  # retains ui_params
        ui = base.get("ui_params")
        nested = req.get("params") or {}
        for k in list(base.keys()):
            if k == "ui_params":
                continue
            if k in req:
                base[k] = _rehydrate_param(base[k], req[k])
            elif k in nested:
                base[k] = _rehydrate_param(base[k], nested[k])
        # A variant is stored as an *overlay* on default_params (only the keys it
        # changes — see resolve_variant_params), so emit its block that way too:
        # trim to just the deltas from default_params. This matches the minimal
        # hand-authored form and keeps a copied variant paste-ready as a
        # <variant>_params overlay. default_params itself is the baseline, so it
        # is always emitted in full. A stale / unknown variant name (one with no
        # <variant>_params attribute) resolves to default_params, where a delta
        # would be an empty, misleading block — so fall back to the full block.
        v_attr = (
            getattr(cls, f"{variant}_params", None)
            if variant and variant != "default"
            else None
        )
        if v_attr is not None and hasattr(v_attr, "keys"):
            name = f"{variant}_params"
            emit = diff_params(dict(_variant_params(cls, "default")), base)
        else:
            name = (
                f"{variant}_params"
                if variant and variant != "default"
                else "default_params"
            )
            emit = base
        return _emit(
            emit,
            name=name,
            precision=_precision_map(ui),
            include_ui=bool(req.get("include_ui", False)),
            wrap="mappingproxy" if req.get("wrap") == "mappingproxy" else "dict",
        )

    def far_field_metrics(req: dict, cancel=None) -> dict:
        # Scalar metrics for the pattern-compare table. Uses the same builder
        # setup as momwire_solve and the momwire engine (so the numbers match
        # the client-derived lobe on screen), then summarises the full grid.
        from antennaknobs.far_field import pattern_metrics

        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        _apply_plane(builder, req)
        eng = _make_momwire_engine(req, builder, cancel=cancel)
        ff = eng.far_field(n_theta=90, n_phi=360, del_theta=1, del_phi=1)
        metrics = pattern_metrics(ff)
        metrics["measurement_freq_mhz"] = meas_freq
        return metrics

    def nec_export(req: dict) -> str:
        # Same builder construction as pynec_solve, then serialise to a NEC2
        # card deck. Ground/freq mirror what the live solve uses so the
        # downloaded deck matches the antenna the user is viewing.
        from antennaknobs.nec_export import export_nec as _export_nec

        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        ground = _ground_for_engine(req) or "free"
        if isinstance(ground, tuple) and ground[0] == "terrain":
            # A NEC deck can't carry the facet model (and the GD card is
            # silently ignored under RP 0 anyway — see
            # scripts/bench_levee_bracket.py): export the crest medium as
            # the flat finite ground the impedance solve uses.
            ground = ("finite",) + ground[1].crest_medium
        return _export_nec(builder, ground=ground, freq=meas_freq)

    def schematic_svg(req: dict) -> str | None:
        # Same builder construction as the live solve, so the schematic's
        # component labels (lengths, C/L values, turns ratios) match the
        # knobs on screen. No solve happens — build_network() plus the
        # schemdraw render is milliseconds, cheap enough to refetch on
        # every knob change like the geometry preview. None (not a raise)
        # for a plain build_wires antenna: "no feed circuit" is an answer,
        # not an error, and it can only be told by building the builder —
        # the base class defines build_network() returning None, so the
        # override cannot be detected statically on cls.
        from antennaknobs.schematic import lower, render_svg

        design_freq, meas_freq = _req_freqs(req)
        builder = _build_builder(cls, req)
        builder.freq = meas_freq
        if has_design_freq:
            builder.design_freq = design_freq
        net = builder.build_network()
        if net is None:
            return None
        # Budget fold-in (issue #652): still no solve here — the frontend
        # echoes the latest solve's structural (key, watts) rows and input
        # power, and each block gets its burn drawn where it happens.
        budget, p_in = _req_budget(req)
        # A picked plane (issue #652 c) draws as a marker on the FULL chain
        # with the disconnected upstream dimmed — lower() quietly ignores a
        # name the chain doesn't visit, so no validation needed here.
        plane = req.get("plane")
        plane = plane if isinstance(plane, str) else None
        # "currentColor": the frontend inlines the SVG, so strokes/text
        # inherit the app theme's CSS colour (see render_svg's docstring).
        return render_svg(
            lower(net, title=name, budget=budget, p_in=p_in, plane=plane),
            color="currentColor",
        )

    def momwire_sweep(req: dict, freqs_mhz: list[float], cancel=None):
        builder = _build_builder(cls, req)
        # MomwireEngine reads builder.freq only for the initial wavelength
        # passed to _make_solver — impedance_sweep overrides k per point.
        builder.freq = float(freqs_mhz[0]) if freqs_mhz else float(builder.freq)
        # Geometry is fixed across the sweep; honour the request's
        # design_freq so the sweep sees the same antenna the live
        # solve sees. See momwire_solve for the rationale.
        if has_design_freq:
            builder.design_freq = _req_freqs(req)[0]
        # A sweep at a picked plane sweeps THAT plane's impedance — the
        # curve the measured overlay lands on (issue #652 c).
        _apply_plane(builder, req)
        eng = _make_momwire_engine(req, builder, cancel=cancel)
        zs = np.asarray(eng.impedance_sweep(list(freqs_mhz)))
        # Open-circuited points sweep through as inf; clamp for JSON.
        zs = np.where(np.isfinite(zs), zs, complex(Z_OPEN_OHMS, 0.0))
        # MomwireEngine.impedance_sweep returns (n_freqs, n_feeds).
        primary = zs[:, 0]
        re = primary.real.tolist()
        im = primary.imag.tolist()
        if hints()["multi_feed"] and zs.shape[1] > 1:
            feeds_re = zs.real.tolist()  # (n_freqs, n_feeds) list of lists
            feeds_im = zs.imag.tolist()
            return re, im, feeds_re, feeds_im
        return re, im

    # Static fields served by /examples. Built-ins prime hints() now (eager,
    # unchanged behaviour); user designs ship provisional values — overrides if
    # declared, else neutral defaults — and the real values arrive with the
    # first solve/geometry response (see the closures above).
    if defer_hints:
        field_multi_feed = (
            bool(multi_feed_override) if multi_feed_override is not None else False
        )
        # No view override and hints deferred → leave it None rather than
        # guessing "xy". The frontend keeps the current camera until the first
        # geometry/solve response carries the real auto-detected view, instead
        # of snapping to a wrong "xy" and then flipping when the preview lands.
        field_default_view = str(view_override) if view_override is not None else None
        field_default_backend = None
        # Provisional None for deferred (user) designs: every backend tab
        # stays enabled, and a PortAtEnd user design surfaces the solver's
        # hard error through the normal solve-error banner instead.
        field_requires_backends = None
        field_backend_restriction = None
        # Deferred (user) designs: False rather than None, on
        # `requires_backends`' precedent — an unmeasured design gets every
        # control enabled and the solver's own error if it is wrong. The
        # panel treats False as "no note", which is the same non-claim.
        field_has_stepped_radius_junction = False
        field_has_buried_wire = False
    else:
        h = hints()
        field_multi_feed = h["multi_feed"]
        field_default_view = h["default_view"]
        field_default_backend = h["default_backend"]
        field_requires_backends = h["requires_backends"]
        field_backend_restriction = h["backend_restriction"]
        field_has_stepped_radius_junction = h["has_stepped_radius_junction"]
        field_has_buried_wire = h["has_buried_wire"]

    return AntennaExample(
        name=name,
        label=name.replace("_", " "),
        momwire_solve=momwire_solve,
        momwire_sweep=momwire_sweep,
        momwire_geometry=momwire_geometry,
        count_basis=count_basis,
        default_backend=field_default_backend,
        requires_backends=field_requires_backends,
        backend_restriction=field_backend_restriction,
        has_stepped_radius_junction=field_has_stepped_radius_junction,
        has_buried_wire=field_has_buried_wire,
        # Static ui_params pin, never derived — safe to read eagerly even for
        # deferred (user) designs, unlike the geometry hints above.
        converged_feed_suggested=bool(
            _ui_scalar(dp, "converged_feed_suggested", False)
        ),
        # Same static-pin contract: the buried-wire designs declare
        # "sommerfeld" so the frontend never seeds them onto the refl-coef
        # wall (see AntennaExample.ground_requirement).
        ground_requirement=(
            str(gr) if (gr := _ui_scalar(dp, "ground_requirement", None)) else None
        ),
        pynec_solve=pynec_solve,
        pynec_build=pynec_build,
        pynec_pattern_excite=pynec_pattern_excite,
        nec5_solve=nec5_solve,
        nec5_pattern=nec5_pattern,
        nec_export=nec_export,
        schematic_svg=schematic_svg,
        params_source=params_source,
        far_field_metrics=far_field_metrics,
        multi_feed=field_multi_feed,
        param_schema=param_schema,
        result_schema=result_schema,
        bands=bands,
        meas_freq_range_mhz=tuple(meas_range) if meas_range else None,
        sweep_policy=sweep_policy,
        default_view=field_default_view,
        default_freq=float(dp["freq"]) if "freq" in dp else None,
        default_design_freq=(float(dp["design_freq"]) if has_design_freq else None),
        has_design_freq=has_design_freq,
        variants=variants,
        variant_values={
            v: _serialize_param_values(_strip_ui(_variant_params(cls, v)))
            for v in variants
        },
        variant_ui=variant_ui,
        notes=str(notes) if notes else None,
        layout=grid_layout,
    )


# ---------------------------------------------------------------------------
# Registration entrypoint
# ---------------------------------------------------------------------------


def list_designs() -> list[str]:
    """Discover every Builder file under designs/.

    Every design lives in a family subpackage (`dipoles/`, `loops/`,
    `arrays/`, …) and registers under the dotted path the user sees in
    the UI (`dipoles.invvee`) — the same convention as the Python import
    path, minus the leading `antennaknobs.designs.`. The dotted name
    is what `register_all` feeds back to importlib too. Any bare top-level
    `*.py` (none today) would register under its stem.
    """
    names: list[str] = []
    for p in sorted(DESIGNS_DIR.glob("*.py")):
        if p.stem.startswith("_"):
            continue
        names.append(p.stem)
    for sub in sorted(d for d in DESIGNS_DIR.iterdir() if d.is_dir()):
        if sub.name.startswith("_") or sub.name == "__pycache__":
            continue
        for p in sorted(sub.glob("*.py")):
            if p.stem.startswith("_"):
                continue
            names.append(f"{sub.name}.{p.stem}")
    return names


def register_all() -> list[str]:
    """Walk designs/ and register one AntennaExample per Builder class.

    Returns the list of design names that registered successfully. Any
    individual failure is swallowed and logged (a single broken design
    must not take down the whole web UI).
    """
    registered: list[str] = []
    for name in list_designs():
        try:
            mod = importlib.import_module(f"{DESIGNS_PKG}.{name}")
        except Exception as exc:  # noqa: BLE001 — registry walk: one broken design must not take down the whole web UI
            print(f"[adapter] skip {name}: import error: {exc!r}")
            continue
        cls = getattr(mod, "Builder", None)
        if cls is None:
            continue
        try:
            cls()  # smoke-test that default_params constructs cleanly
            register(_make_example(name, cls))
            registered.append(name)
        except Exception as exc:  # noqa: BLE001 — same walk — a design whose default_params will not construct is skipped and logged
            print(f"[adapter] skip {name}: {exc!r}")
    return registered


# Derived from the specs rather than restated: `auto_when_null` is the fact,
# and this set is a view of it. A second literal here is how the two drift.
_AUTO_WHEN_NULL = frozenset(
    k for k, spec in _OPTION_SPECS.items() if spec.auto_when_null
)


# Retired backend names a saved session or an old client may still carry,
# mapped to what they mean now (#1006 G2-6). Served rather than hand-held in
# the frontend, which had `name === "triangular" ? "bspline" : name` inline —
# the last engine-name branch in that file.
#
# `_make_momwire_engine` already tolerates a retired name on the SOLVE path by
# falling back to bspline; this is the same fact said once, on the way out, so
# the picker resolves the old name to the right TAB rather than silently
# solving something the UI is not showing.
_BACKEND_ALIASES = {"triangular": "bspline"}


def backend_aliases() -> dict[str, str]:
    """Retired backend names -> the name that supersedes each."""
    return dict(_BACKEND_ALIASES)


# The stock A/B/C solver slots, served so the frontend names no engine.
#
# These are PRODUCT choices with measured reasons, which is why they are a
# table rather than something derived from the roster: "the first dense
# backend" would be an accident, and the N values below are census results.
_DEFAULT_SLOTS = (
    # A is the default working solver: B-spline d=2 — most accurate per
    # unknown, converged at a small odd N (interior knot at the feed), and its
    # impedance solve honours finite grounds. N=15 per the basis-convergence
    # census (docs/status/2026-07-20): within 2% of the basis-agreed limit on
    # 50/66 scorable designs, patterns within 0.05 dB of the fine-mesh
    # reference, ~35% faster ticks. Odd parity keeps the feed's interior knot.
    {"slot": "A", "backend": "bspline", "n_per_wire": 15, "model": {}},
    # B is the cross-check basis: d=1 needs a larger N to reach the same
    # answer, which is what makes agreement with A a second opinion rather
    # than the same solve twice. N=20 trades tightness for speed.
    {"slot": "B", "backend": "bspline", "n_per_wire": 20, "model": {"degree": 1}},
    {"slot": "C", "backend": "pynec", "n_per_wire": None, "model": {}},
)


def default_slots() -> list[dict]:
    """The stock A/B/C seeds. A seed naming a backend this server does not
    serve is the frontend's to fall back on — the same tolerance a parked
    terrain preset gets (#560, #429)."""
    return [dict(s) for s in _DEFAULT_SLOTS]


# The axes a tab's COMPOSITION LINE states, in reading order (#1006 G2-7).
#
# Six of the seven. `charge_support` is omitted because it is a FUNCTION OF
# BASIS today — bspline-1/bspline-2 imply "spline", sinusoidal-3term/tent
# imply "basis-implied" — so a segment for it restates the basis segment in
# other words. Measured, not assumed, and pinned by
# test_composition_line_1006.py::test_charge_support_is_still_a_function_of_basis:
# if it ever varies independently, that test fails and this list should gain
# it rather than the line quietly staying wrong.
#
# The DERIVED axes (`ground_model`, `wire_position`) are absent for the reason
# they are never controls either: they describe the deck a solver can be
# pointed at, not how the solver is built. A line about the engine that
# changed when you switched design would be describing the wrong thing.
_COMPOSITION_AXES = (
    "basis",
    "testing",
    "kernel",
    "quadrature",
    "solve_strategy",
    "feed_model",
)


# Which AXIS VALUE each bound kwarg pins its axis to (#1006 G2-7).
#
# `bound` is keyed by constructor kwarg (`nec5_quadrature: True`); a
# composition line needs the axis VALUE ("nec5") to look up its phrase. That
# translation is engine vocabulary and is resolved here, not in the client —
# the frontend briefly did it and the no-engine-name grep caught it, because
# "nec5" is BOTH a backend name and a quadrature value and the ambiguity is
# exactly the sort a client should not be adjudicating.
_BOUND_AXIS_VALUES = {
    ("nec5_quadrature", True): ("quadrature", "nec5"),
    ("nec5_quadrature", False): ("quadrature", "converged"),
    ("extended_kernel", True): ("kernel", "extended"),
    ("extended_kernel", False): ("kernel", "reduced"),
}


def _bound_axes(spec) -> dict[str, str]:
    """Axis -> the value this preset pins it to. Empty when nothing is bound."""
    out = {}
    for kwarg, value in (spec.bound or {}).items():
        hit = _BOUND_AXIS_VALUES.get((kwarg, value))
        if hit is not None:
            out[hit[0]] = hit[1]
    return out


def composition_axes() -> list[str]:
    """The axes a composition line states, in reading order."""
    return list(_COMPOSITION_AXES)


# Axis value -> the phrase a composition line uses for it (#1006 G2-7).
#
# momwire's axis values are its own vocabulary ("bspline-2", "refl-coef");
# a line a user reads needs English. That mapping is UI COPY ABOUT ENGINES,
# so it lives here rather than in the client, on the same argument as
# `gate_label` and the served slot seeds — and the frontend's no-engine-name
# grep test is what keeps it here.
#
# Phrasing rules, so additions stay consistent:
#   * lower case except proper names (Galerkin, NEC), because the segments
#     read as a sentence rather than as labels;
#   * say the QUANTITY where the raw value is a bare number ("degree 2", not
#     "2"), since a lone digit in a list of words reads as noise;
#   * name what the thing IS, not what it is called internally ("two-point
#     quadrature", not "nec5").
_AXIS_VALUE_LABELS = {
    "basis": {
        "bspline-1": "degree 1",
        "bspline-2": "degree 2",
        "sinusoidal-3term": "3-term sinusoidal",
        "tent": "tent",
    },
    "testing": {
        "galerkin": "Galerkin",
        "point-matching": "point-matched",
        "path": "path-tested",
    },
    "kernel": {"extended": "extended kernel", "reduced": "reduced kernel"},
    "quadrature": {
        "converged": "converged quadrature",
        "nec5": "two-point quadrature",
    },
    "solve_strategy": {
        "dense": "dense",
        "aca": "ACA",
        "element-block": "element-block",
    },
    "feed_model": {
        "segment-gap": "segment gap",
        "point-gap": "point gap",
        "node-port": "node port",
    },
    "charge_support": {
        "spline": "spline charge",
        "basis-implied": "basis-implied charge",
    },
}


def axis_value_labels() -> dict[str, dict[str, str]]:
    """Axis value -> the phrase a composition line uses."""
    return {a: dict(v) for a, v in _AXIS_VALUE_LABELS.items()}


def model_option_specs() -> dict[str, dict]:
    """Every solver knob, described once, for a generic renderer (#1006 G2-6).

    Served flat and keyed by kwarg — a backend's `model_kwargs` names which of
    these apply to it. That split is deliberate: the DESCRIPTION of `degree`
    (an integer in [1, 2], captioned "degree") is the same fact for every
    backend that takes it, and copying it into each roster row would be the
    per-engine duplication G2-6 is removing, re-created one level down.

    `shown_when` is UI gating only. A genuine refusal — the extended kernel
    against singular enrichment — is momwire's to state and travels in the
    served `constraints` (momwire#888); nothing here may encode one.
    """
    out = {}
    for key, spec in _OPTION_SPECS.items():
        row = {
            "kind": spec.kind,
            "label": spec.label,
            "default": spec.default,
            "auto_when_null": spec.auto_when_null,
            "shown_when": spec.shown_when,
            "gate_label": spec.gate_label,
            "gate_on_value": spec.gate_on_value,
            "shown_when_value": spec.shown_when_value,
        }
        if spec.kind in ("int", "float"):
            # The RENDER bounds, falling back to the sanitiser's. What the
            # control offers, never what the endpoint merely tolerates —
            # `feed_smoothing_factor` differs by 10x, and a renderer given the
            # looser pair would widen the knob and change its step.
            row["min"] = spec.lo if spec.render_lo is None else spec.render_lo
            row["max"] = spec.hi if spec.render_hi is None else spec.render_hi
            row["step"] = spec.step if spec.render_step is None else spec.render_step
            row["allow_none"] = spec.allow_none
            # Served too, so a client can tell "the server would take this"
            # from "the control offers this" — the sweep UI and the API docs
            # both want the wider pair.
            row["accepts_min"] = spec.lo
            row["accepts_max"] = spec.hi
        if spec.kind == "enum":
            row["values"] = list(spec.values)
        out[key] = row
    return out
