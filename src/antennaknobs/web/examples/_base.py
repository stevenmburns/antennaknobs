"""Base types for the antenna-example registry.

An `AntennaExample` bundles everything the web layer needs to serve one
geometry: parameter schema, momwire solve/sweep, and pynec build/solve. Any
callable left as None signals the backend doesn't support that operation
for this geometry.

Keeping these as plain callables (rather than a class hierarchy) means
each example module is a flat file of functions plus one EXAMPLE = ...
assignment at the bottom — easy to read, easy to delete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple, Union

# A pynec "build" returns the dict-of-context-plus-derived-geom that both
# solve() and pattern() consume — see web/pynec_backend.py for the shape.
PynecBuildFn = Callable[[dict], dict]

# momwire solve / pynec solve: take a request dict, return the response dict
# the frontend renders.
SolveFn = Callable[[dict], dict]

# momwire sweep: take a request dict + frequency list. Single-feed geometries
# return (re, im) — two parallel lists of input impedance. Multi-feed
# geometries (bowtie 1×2) return (primary_re, primary_im, feeds_re,
# feeds_im) where feeds_* is (n_freqs × n_feeds). The sweep endpoint
# detects the tuple length to know which shape it got.
SweepResult = Union[
    Tuple[list[float], list[float]],
    Tuple[list[float], list[float], list[list[float]], list[list[float]]],
]
SweepFn = Callable[[dict, list[float]], SweepResult]

# pynec pattern excitation: drive the NEC context using the build dict's
# feed metadata. Single-feed default lives in web.pynec_backend.pattern();
# multi-feed examples (bowtie) supply their own (e.g. two ex_card calls).
PynecPatternExciteFn = Callable[[dict, float], None]  # (build, freq_mhz)


@dataclass(frozen=True)
class ParamSpec:
    """One UI-exposed parameter for a geometry.

    Served from `GET /examples` so the frontend can render parameter
    controls generically — one ParamForm component reads the schema and
    builds the matching <input> elements without per-antenna JSX.

    `visible_when` makes a parameter conditional on another's value:
    e.g. yagi's director_spacing_wavelengths slider only appears when
    n_directors > 0. The dict is shaped {name, op, value}; ops include
    "eq", "ne", "gt", "ge", "lt", "le".

    `kind` switches the input type:
      - "float": continuous slider (use min/max/step)
      - "int": integer slider (use min/max/step=1)
      - "bool": checkbox
      - "enum": <select> dropdown; supply `enum_options`
    Bowtie's phase_lr_deg uses a signed range — kind="float" with min<0.

    For "enum" params, `enum_options` is a tuple of free-form dicts. Each
    dict must have at least {"value", "label"}; antennas can attach
    arbitrary extra keys to drive related controls. Fan_dipole's per-band
    `band_id` carries {"value": "20m", "label": "20m", "freq_min": 14.0,
    "freq_max": 14.35, "freq_default": 14.175} so a sibling freq slider
    can read its bounds + default off the active band.

    `range_from_enum_option` lets a slider's min/max/step come from the
    currently-selected enum value of a sibling param. Shape:
    {"param": <enum_param_name>, "min_key": <key>, "max_key": <key>}.

    `on_change_set` is a side-effect rule: when this enum changes value,
    write a sibling param using a key from the new enum option. Shape:
    {"set": <sibling_name>, "from_enum_key": <key>}. Fan_dipole's
    band_id uses {"set": "freq", "from_enum_key": "freq_default"} so
    flipping the band pulldown snaps the freq slider to that band's
    centre.

    `linked_to_design_freq` means this param's value also drives the
    global designFreq state on the frontend. Fan_dipole uses it on
    `bands[0].freq` so the first band's frequency stays the antenna's
    design frequency without a separate global slider.

    `link_meas_freq_to_param` is the flat-schema sibling of
    ParamGroupSpec.link_meas_freq_to_param: when this scalar slider
    moves, push the current value of the named sibling param into the
    global measFreq state (gated by the frontend's linkMeas toggle).
    Used by multi-band antennas with parallel `length_NN` / `freq_NN`
    params so dragging length_20 jumps the measurement-freq slider to
    the 20m band's freq. A self-reference (param links to itself, e.g.
    freq_20 → freq_20) is the natural way to mark "this slider's own
    value is a measurement-frequency anchor".
    """

    name: str
    label: str
    default: Any
    kind: str = "float"  # float | int | bool | enum
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    precision: int = 3  # decimal places shown in the value readout
    unit: Optional[str] = None  # rendered next to the value: "°", "m", "λ", etc.
    visible_when: Optional[dict] = None  # {"name": ..., "op": ..., "value": ...}
    enum_options: Optional[tuple[dict, ...]] = None
    range_from_enum_option: Optional[dict] = None
    on_change_set: Optional[dict] = None
    linked_to_design_freq: bool = False
    link_meas_freq_to_param: Optional[str] = None
    sweepable: bool = False
    # Optional explicit placement in the param grid, opting this knob out
    # of the default auto-flow packing. Shape: {"row", "col", "row_span",
    # "col_span"} — all optional ints, 1-indexed (CSS grid lines). The
    # frontend maps them straight onto grid-row / grid-column so a design
    # can lay its knobs out in a deliberate row/column arrangement. Pairs
    # with AntennaExample.layout["columns"], which fixes the grid's column
    # count so these positions are stable rather than width-dependent.
    # Authored under ui_params[<param>]["layout"]; None keeps auto-flow.
    layout: Optional[dict] = None


@dataclass(frozen=True)
class ParamGroupSpec:
    """A repeating section of params, count-controlled by another param.

    Used for multi-band / multi-element antennas where each band (or
    element) carries its own set of knobs. Fan_dipole is the first user
    (one group per band: band_id + freq + length_factor). The pattern
    generalises: a trapped multi-bander would have a group with
    {band_id, trap_freq, trap_q}; a multi-band Yagi would have a group
    with {driver_factor, reflector_factor, n_directors, ...} possibly
    containing its own nested director sub-group.

    The schema currently allows nested groups (params is a union type)
    but the frontend only renders one level of nesting in the first
    cut. Adding deeper nesting is a frontend-only change.

    `label_template` is the heading shown above each instance with
    {i} substituted to the 0-indexed instance number, e.g. "band {i}".

    `repeat_count` names a scalar param (kind="int") elsewhere in the
    same schema whose value determines how many instances render.
    `max_repeats` is the absolute cap used for state pre-allocation —
    matching the count param's `max`.
    """

    name: str  # key under which the frontend stores per-instance values
    label_template: str  # e.g. "band {i}" — {i} is the 0-indexed instance
    repeat_count: str  # name of the scalar param that controls how many
    max_repeats: int
    params: tuple[Any, ...]  # tuple[Union[ParamSpec, ParamGroupSpec], ...]
    # Optional per-instance default overrides. Index i applies to
    # instance i; each dict maps {param_name: default_value} and beats
    # the ParamSpec.default for that one instance. Used by fan_dipole
    # so the 5 max bands seed to (20m, 10m, 17m, 12m, 15m) instead of
    # all defaulting to the same band. Tuple length doesn't need to
    # match max_repeats; missing indices fall back to the ParamSpec
    # default.
    default_overrides: tuple[dict, ...] = ()
    # When set, names a param inside `params` (e.g. "freq") whose
    # current per-instance value drives the global measFreq state
    # *every time any leaf in the touched instance changes*. UX
    # rationale: tuning any knob of band i (length factor, t0 factor,
    # ...) signals the user is focused on band i, so the live
    # simulation should track that band's freq. Distinct from
    # ParamSpec.linked_to_design_freq, which is a steady-state link
    # to a single fixed instance (always band 0). This is a
    # per-interaction "follow the user's focus" link, fan_dipole and
    # hexbeam_5band both use "freq".
    # Gated by the frontend's linkMeas toggle.
    link_meas_freq_to_param: Optional[str] = None


@dataclass(frozen=True)
class BandSpec:
    """A frequency-preset tab the UI offers as a design-frequency selector.

    The solver only sees the resulting `design_freq_mhz` float; bands are
    purely a UI affordance. Examples that target HF amateur bands reuse
    `DEFAULT_HF_BANDS`; others can supply their own list, or set bands=()
    to suppress the row entirely (fan_dipole does this — its per-band
    schema-driven controls own the design frequency).
    """

    key: str  # stable identifier; also used as the visible tab label today
    label: str
    freq_mhz: float  # tab default — slider snaps here when the band is selected
    min_mhz: float  # slider lower bound while this band is active
    max_mhz: float


@dataclass(frozen=True)
class SweepPolicy:
    """Where to centre the freq sweep and how wide to make it.

    `anchor` picks which scalar the sweep range is anchored to:
      - "design_freq": sweep around the antenna's design frequency
        (the wider out-of-band picture; default for single-band antennas).
      - "meas_freq":   sweep around the current measurement frequency
        (multi-band antennas like fan_dipole — keeps the trace focused
        on the band the user is currently tuning, since the design
        frequency stays pinned to band 0).

    `lo_factor` / `hi_factor` are multiplicative bounds applied to the
    anchor. Defaults give a broad resonance/out-of-band view; multi-band
    antennas narrow to ±5% so the trace doesn't cross into neighbouring
    bands the user isn't tuning.
    """

    anchor: str = "design_freq"  # "design_freq" | "meas_freq"
    lo_factor: float = 0.8
    hi_factor: float = 1.25
    # When True, the frontend snaps the sweep range to the [min_mhz,
    # max_mhz] of the band whose range contains the current anchor
    # frequency (typically measFreq for multi-band antennas). Falls
    # back to lo_factor/hi_factor multiplicatively if the anchor sits
    # outside every band. Used by fandipole so the sweep trace stays
    # inside the amateur band the user is currently tuning instead of
    # bleeding into the adjacent bands.
    band_locked: bool = False


DEFAULT_SWEEP_POLICY = SweepPolicy()


DEFAULT_HF_BANDS: tuple[BandSpec, ...] = (
    # Full HF amateur set + 6m, low to high. The band dropdown scales to any
    # number, so designs (especially design_freq-scaled ones) can be placed and
    # tuned anywhere from 160m up. (key, label, snap-freq, slider-min, -max MHz)
    BandSpec("160m", "160m", 1.900, 1.800, 2.000),
    BandSpec("80m", "80m", 3.750, 3.500, 4.000),
    BandSpec("40m", "40m", 7.150, 7.000, 7.300),
    BandSpec("30m", "30m", 10.125, 10.100, 10.150),
    BandSpec("20m", "20m", 14.300, 14.000, 14.350),
    BandSpec("17m", "17m", 18.1575, 18.068, 18.168),
    BandSpec("15m", "15m", 21.383, 21.000, 21.450),
    BandSpec("12m", "12m", 24.970, 24.890, 24.990),
    BandSpec("10m", "10m", 28.470, 28.000, 29.700),
    BandSpec("6m", "6m", 50.150, 50.000, 54.000),
)


@dataclass(frozen=True)
class ResultFieldSpec:
    """One field from the solve response to surface in the result panel.

    The frontend's ResultPanel reads the field by name off the response,
    formats it with `precision`, appends `unit`, and renders one row
    labelled `label`. Scalar number fields only — multi-feed tables
    stay hardcoded for now.
    """

    field: str  # response key, e.g. "arm_len_m"
    label: str
    precision: int = 3
    unit: Optional[str] = None  # rendered after the value: " m", "°", " Ω", ...


@dataclass(frozen=True)
class ResultGroupSpec:
    """A repeating result row, one instance per element of a top-level
    array field on the solve response.

    The number of instances comes from the length of the first inner
    field's array. Each instance renders one row per inner ResultFieldSpec.

    `label_template` supports three substitutions:
      - `{i}`         → 0-based index
      - `{i1}`        → 1-based index
      - `{name:.Nf}`  → result[name][i] formatted as a fixed-N-decimal
                        float; lets the label pull values from sibling
                        arrays (e.g. "band {i1} ({band_freqs_mhz:.2f} MHz)").

    Fan_dipole is the first user: one group over `band_lengths_m`,
    label_template references `band_freqs_mhz` to show the per-band freq
    inline with the per-band length.
    """

    name: str
    label_template: str
    fields: tuple[ResultFieldSpec, ...]


@dataclass(frozen=True)
class AntennaExample:
    name: str
    label: str
    momwire_solve: SolveFn
    momwire_sweep: SweepFn
    # Geometry-only snapshot (wires, feed marker; no solve, no currents) for a
    # fast antenna-shape preview while the real solve runs. Optional so an
    # example without one degrades to "no preview".
    momwire_geometry: Optional[SolveFn] = None
    # Cheap geometry-only count of the wire segments (≈ MoM basis functions /
    # matrix dimension N) a solve request would build, used to reject solves
    # that would allocate an N×N matrix too large/slow for the live engine. None
    # if the geometry can't be built (the real solve surfaces that error). Takes
    # the same req dict as momwire_solve.
    count_basis: Optional[Callable[[dict], Optional[int]]] = None
    # Recommended default solver backend for this design (e.g. "arrayblock" for
    # grid arrays, where it's far faster than the dense default). None lets the
    # UI keep its own default. Surfaced in the /examples schema; the frontend
    # seeds the active slot's backend from it on antenna selection.
    default_backend: Optional[str] = None
    pynec_build: Optional[PynecBuildFn] = None
    pynec_solve: Optional[SolveFn] = None
    # Render the geometry as a NEC2 .nec card deck (str) for the current
    # request (params/variant/freq/ground). None when the design has no
    # faithful native-NEC representation (TL/DiffTL/virtual-driver networks).
    nec_export: Optional[Callable[[dict], str]] = None
    # Serialise the request's current knob values back to a paste-ready
    # Python `default_params = {...}` (or named-variant) block, so the UI can
    # offer a "Copy Python" action that drops straight into a design file.
    # None when the design can't be serialised.
    params_source: Optional[Callable[[dict], str]] = None
    # Compute scalar far-field metrics (peak gain, takeoff, F/B, beamwidths)
    # for the request's antenna, so the UI can show a side-by-side table when
    # comparing pinned patterns. Always the momwire engine (matches the
    # client-derived lobe on screen). None when the design can't be evaluated.
    far_field_metrics: Optional[Callable[[dict], dict]] = None
    # When set, pattern() calls this to excite the NEC context (e.g.
    # multi-source drive for bowtie's 1×2 array). When None, pattern()
    # uses the default single-feed excitation reading b["feed_seg"] /
    # b["feed_tag"] / b["n_per_wire"] from the build dict.
    pynec_pattern_excite: Optional[PynecPatternExciteFn] = None
    # Sweep returns the multi-feed 4-tuple instead of the single-feed
    # 2-tuple. Sweep endpoint uses this to dispatch the two response
    # streaming shapes.
    multi_feed: bool = False
    # Mixed sequence of ParamSpec (scalar) and ParamGroupSpec (repeat).
    # The Any erases the union; runtime discrimination is by presence of
    # `params` (groups have it, scalars don't).
    param_schema: tuple[Any, ...] = field(default_factory=tuple)
    # Mixed sequence of ResultFieldSpec (scalar row) and ResultGroupSpec
    # (repeat group). Runtime discrimination on presence of `fields`.
    result_schema: tuple[Any, ...] = field(default_factory=tuple)
    # Design-frequency band tabs offered by the UI. Defaults to the HF
    # amateur set; multi-band examples (fan_dipole) set this to () to
    # suppress the row.
    bands: tuple[BandSpec, ...] = DEFAULT_HF_BANDS
    # Optional override for the measurement-freq slider span. When None,
    # the UI uses a generic ±20%/+25% window around the design freq.
    # Multi-band examples that span the whole HF range set this to e.g.
    # (13.5, 30.2) so the slider can reach every band.
    meas_freq_range_mhz: Optional[tuple[float, float]] = None
    # Sweep range + anchor for the live freq sweep. Defaults to
    # design-freq-anchored ±20%/+25%; multi-band examples override
    # to meas-freq-anchored ±5% so the trace stays on the band the
    # user is tuning.
    sweep_policy: SweepPolicy = DEFAULT_SWEEP_POLICY
    # Initial 2D-view projection the wire-render canvas picks when the
    # user first selects this example. "xy" = top-down (beam-in-xy
    # antennas like yagi/moxon/hexbeam); "yz" = side (antennas whose
    # arms run along y and droop in z, like inverted_v / fan_dipole;
    # also the vertical-loop hentenna). The user can still override
    # via the projection buttons; this just sets the starting view.
    # None for a deferred (user) design with no override: the real view is
    # auto-detected and arrives with the first geometry/solve response, so the
    # frontend holds the current camera until then instead of snapping to a
    # provisional value.
    default_view: Optional[str] = None
    # The frequency this antenna is naturally designed for, in MHz.
    # Used by the frontend to snap the band selector + design-freq /
    # meas-freq sliders to the right starting value when the example
    # first loads, without exposing it as a redundant schema slider.
    # None means "no preferred freq" — frontend falls back to bands[0]
    # or its built-in default.
    default_freq_mhz: Optional[float] = None
    # True when the Builder has a `design_freq` parameter that scales
    # geometry (design_freq-sized designs). The frontend uses this to show
    # or hide the design-freq band-tab row: hand-tuned absolute
    # designs (top-level designs/) ignore design_freq, so the row
    # would just be a noop slider for them.
    has_design_freq: bool = False
    # Alternate seed dicts available on the Builder — class-level
    # attributes named `<variant>_params` (e.g. `default`, `opt`,
    # `original`, `z50`, `z100`). The bare name is what the frontend
    # sends back in the `variant` field of solve / sweep requests.
    # `default` is always first when present so the UI lists it as
    # the canonical starting point. Single-variant Builders ship
    # ('default',) — the frontend can suppress the selector then.
    variants: tuple[str, ...] = ("default",)
    # Per-variant param values, keyed by variant name → {param_name:
    # value}. The frontend uses this to reset schema sliders + design
    # freq when the user picks a different variant. Complex-valued
    # params are encoded as {"re": ..., "im": ...}; ui_params is
    # stripped. Single-variant designs ship {} since there's nothing
    # to switch between.
    variant_values: dict = field(default_factory=dict)
    # Per-variant UI-hint overrides, keyed by variant name → {hint_name:
    # value}. Today the only hint is `sweep_policy` (a SweepPolicy), emitted
    # only for variants whose derived policy differs from the design-level
    # `sweep_policy` above; the frontend falls back to that top-level value
    # for any variant absent here. Kept as an open map so more ui hints can
    # move per-variant later without another /examples contract change.
    variant_ui: dict = field(default_factory=dict)
    # Optional grid-level layout config for the top-level knob rail.
    # Recognised key today: {"columns": int} — pins the param grid to a
    # fixed column count so per-ParamSpec.layout col positions land
    # predictably (the default auto-flow grid varies its column count with
    # the rail width). None keeps the responsive auto-fill packing.
    # Authored under the reserved ui_params["layout"] key.
    layout: Optional[dict] = None
