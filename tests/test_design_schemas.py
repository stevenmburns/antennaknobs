"""Per-antenna schema unit tests.

For every Builder registered by antennaknobs.web.adapter, assert the derived
ParamSpec / variants / sweep policy / view shape the frontend depends on.
This is the generic cousin of test_fandipole_schema.py — fandipole keeps
its bespoke tests for the bands-group wiring; everything else is covered
here with one parametrized sweep.

Targeted tests at the bottom pin down design-specific UI choices
(yagi.n_directors as an int slider, hentenna_slant's tight precision
overrides, hexbeam/moxon variant lists, twoband_fan_dipole's sweep
variant family).
"""

from __future__ import annotations

import importlib
import math

import pytest

import antennaknobs.web.examples  # noqa: F401 — primes the adapter
from antennaknobs.web.adapter import (
    _auto_paramspec,
    _build_builder,
    _make_example,
    _nice_step,
    _precision_for_step,
)
from antennaknobs.web.examples import REGISTRY
from antennaknobs.web.examples._base import (
    DEFAULT_HF_BANDS,
    AntennaExample,
    BandSpec,
    ParamGroupSpec,
    ParamSpec,
    SweepPolicy,
)


# ---------------------------------------------------------------------------
# Generic coverage — every registered design
# ---------------------------------------------------------------------------


DESIGN_NAMES = sorted(REGISTRY.keys())


def _builder_cls(name: str):
    mod = importlib.import_module(f"antennaknobs.designs.{name}")
    return mod.Builder


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_schema_excludes_freq_and_design_freq_sliders(name):
    ex = REGISTRY[name]
    slider_names = {s.name for s in ex.param_schema}
    # The dedicated meas-freq slider and the design-freq band-tab row own
    # these — the schema must never duplicate them.
    assert "freq" not in slider_names
    assert "design_freq" not in slider_names


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_schema_covers_every_non_freq_default_param(name):
    cls = _builder_cls(name)
    dp = dict(cls.default_params)
    ui = dp.get("ui_params") or {}
    slider_names = {s.name for s in REGISTRY[name].param_schema}
    for key, val in dp.items():
        if key in ("ui_params", "freq", "design_freq"):
            continue
        ov = ui.get(key)
        if isinstance(ov, dict) and ov.get("hidden"):
            # Explicitly suppressed via `ui_params[key] = {"hidden": True}`:
            # a pinned/degenerate param (e.g. bisquare.side_frac, which only
            # ever multiplies length_factor). No slider by design; it stays at
            # its default through solves.
            continue
        if isinstance(val, complex):
            # Complex defaults intentionally have no UI; settable via
            # request body's {re, im} shape only.
            continue
        if isinstance(val, str):
            # String defaults need an enum_options override to surface.
            continue
        if val is None:
            # None carries no type info, so the adapter emits no auto-UI
            # (web/adapter.py _param_spec_from_default returns None for
            # complex/None/exotic). Used by programmatic-only params such as
            # sterba_driven.feed_voltages / active_junctions, set via the
            # request body rather than a slider.
            continue
        assert key in slider_names, f"{name}: missing slider for {key!r}"


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_default_variant_listed_first(name):
    variants = REGISTRY[name].variants
    assert variants, f"{name}: no variants discovered"
    assert variants[0] == "default"


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_variant_values_serialise_for_every_variant(name):
    ex = REGISTRY[name]
    for v in ex.variants:
        assert v in ex.variant_values, f"{name}: missing values for variant {v!r}"
        # ui_params is solver-internal; the wire to the frontend must
        # not carry it (variant_values goes straight to App.tsx).
        assert "ui_params" not in ex.variant_values[v]


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_default_view_is_a_valid_2d_plane(name):
    assert REGISTRY[name].default_view in {"xy", "yz", "xz"}


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_sweep_policy_is_well_formed(name):
    sp = REGISTRY[name].sweep_policy
    assert isinstance(sp, SweepPolicy)
    assert sp.anchor in {"design_freq", "meas_freq"}
    assert sp.lo_factor > 0 and sp.hi_factor > sp.lo_factor


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_bands_default_to_hf_set_unless_overridden(name):
    bands = REGISTRY[name].bands
    assert all(isinstance(b, BandSpec) for b in bands)
    # No design currently zeroes out the band row — guard against an
    # accidental ui_params['bands'] = () regressing the design-freq UI.
    assert len(bands) >= 1
    # Defaulted designs share the HF set object; overrides have their
    # own tuple but still parse as BandSpecs (covered above).
    if "ui_params" not in dict(_builder_cls(name).default_params):
        assert bands is DEFAULT_HF_BANDS


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_param_schema_specs_are_typed_correctly(name):
    for spec in REGISTRY[name].param_schema:
        assert isinstance(spec, (ParamSpec, ParamGroupSpec))
        if isinstance(spec, ParamSpec) and spec.kind in ("float", "int"):
            assert spec.min is not None and spec.max is not None
            assert spec.min < spec.max


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_example_round_trips_through_make_example(name):
    # Re-deriving the example mid-test shakes out hidden mutation in
    # _make_example (closures over Builder dicts that get mutated on
    # subsequent solves, etc.).
    cls = _builder_cls(name)
    ex = _make_example(name, cls)
    assert isinstance(ex, AntennaExample)
    assert ex.name == name


# ---------------------------------------------------------------------------
# beams.yagi — n_directors is the integer scalar that drives the
# director count in build_wires().
# ---------------------------------------------------------------------------


def test_yagi_n_directors_is_int_slider():
    schema = {s.name: s for s in REGISTRY["beams.yagi"].param_schema}
    n_dir = schema["n_directors"]
    assert isinstance(n_dir, ParamSpec)
    assert n_dir.kind == "int"
    assert n_dir.default == 2


def test_yagi_factor_sliders_present():
    schema = {s.name: s for s in REGISTRY["beams.yagi"].param_schema}
    for key in ("length_factor", "director_factor", "reflector_factor", "boom_factor"):
        assert key in schema
        assert schema[key].kind == "float"


# ---------------------------------------------------------------------------
# specialty.hentenna_slant — explicit ui_params overrides on
# length_factor, top_aspect, bot_aspect, slant_deg.
# ---------------------------------------------------------------------------


def test_degree_params_get_compact_label_and_unit():
    # Angle params keep their `_deg` key (used by tests/CLI/API/configs) but
    # the panel shows a compact label with a ° unit; the real name is still
    # surfaced via the knob tooltip on the frontend. Suffixed array params
    # drop the `_deg` token from the middle (angle_deg_itop -> angle_itop).
    arr = {s.name: s for s in REGISTRY["arrays.bowtiearray2x4"].param_schema}
    itop = arr["angle_deg_itop"]  # key unchanged
    assert itop.label == "angle_itop"
    assert itop.unit == "°"

    loop = {s.name: s for s in REGISTRY["loops.delta_loop"].param_schema}
    assert loop["angle_deg"].label == "angle"
    assert loop["angle_deg"].unit == "°"

    slant = {s.name: s for s in REGISTRY["specialty.hentenna_slant"].param_schema}
    assert slant["slant_deg"].label == "slant" and slant["slant_deg"].unit == "°"

    # Non-angle params are untouched.
    bowtie = {s.name: s for s in REGISTRY["specialty.bowtie"].param_schema}
    assert bowtie["length"].label == "length" and bowtie["length"].unit is None


def test_degree_params_default_to_half_degree_step():
    # Angle sliders default to a 0.5° step...
    loop = {s.name: s for s in REGISTRY["loops.delta_loop"].param_schema}
    assert loop["angle_deg"].step == 0.5
    arr = {s.name: s for s in REGISTRY["arrays.bowtiearray2x4"].param_schema}
    assert arr["angle_deg_itop"].step == 0.5

    # ...but a design's explicit ui_params step still wins.
    t2fd = {s.name: s for s in REGISTRY["broadband.t2fd"].param_schema}
    assert t2fd["tilt_deg"].step == 1.0

    # Non-angle params keep their auto-derived step (not the 0.5° default).
    bowtie = {s.name: s for s in REGISTRY["specialty.bowtie"].param_schema}
    assert bowtie["length"].step != 0.5


def test_hentenna_slant_aspect_overrides_applied():
    schema = {s.name: s for s in REGISTRY["specialty.hentenna_slant"].param_schema}
    top = schema["top_aspect"]
    bot = schema["bot_aspect"]
    slant = schema["slant_deg"]
    assert (top.min, top.max) == (0.5, 4.5)
    assert (bot.min, bot.max) == (0.0, 2.0)
    assert (slant.min, slant.max) == (0.0, 45.0)
    assert top.precision == 4 and bot.precision == 4
    assert slant.precision == 0


def test_hentenna_slant_lists_z50_z100_variants():
    variants = REGISTRY["specialty.hentenna_slant"].variants
    assert set(variants) >= {"default", "z50", "z100"}


def test_hentenna_slant_z100_overrides_default_factors():
    vv = REGISTRY["specialty.hentenna_slant"].variant_values
    assert vv["z100"]["length_factor"] != vv["default"]["length_factor"]
    assert vv["z100"]["top_aspect"] != vv["default"]["top_aspect"]


# ---------------------------------------------------------------------------
# Variant family pinning — designs whose variants are the user-facing
# selectors. Catches an accidental rename of a class attribute.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("beams.hexbeam", {"default", "opt"}),
        ("beams.moxon", {"default", "opt", "original"}),
        ("arrays.invveearray", {"default", "old"}),
        ("loops.delta_loop", {"default", "z100", "z200"}),
        ("loops.diamond_loop", {"default", "z100", "z200"}),
        ("loops.inv_delta_loop", {"default", "z100", "z200"}),
        ("specialty.hentenna", {"default", "z50", "z100"}),
        ("loops.delta_loop_slanted", {"default", "slant0", "slant30"}),
        ("arrays.delta_looparray", {"default", "dy3", "dy35", "dy45"}),
    ],
)
def test_variant_family(name, expected):
    assert set(REGISTRY[name].variants) >= expected


def test_twoband_fan_dipole_carries_spacing_sweep_variants():
    # twoband_fan_dipole sweeps spacing factor across s01..s07 + an
    # eps-perturbed variant. The full set is what feeds the UI's
    # variant selector — losing any of them silently breaks the
    # comparison sweep the user runs after picking a baseline.
    expected = {
        "default",
        "current_physical",
        "s01",
        "s015",
        "s01_eps001",
        "s02",
        "s025",
        "s03",
        "s05",
        "s07",
    }
    assert set(REGISTRY["multiband.twoband_fan_dipole"].variants) >= expected


# ---------------------------------------------------------------------------
# design_freq presence — design_freq-sized designs derive geometry from
# design_freq; top-level designs are hand-tuned in absolute meters. The
# adapter uses has_design_freq to decide whether to write the request's
# design_freq_mhz onto the builder; the wrong polarity silently breaks
# every solve.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_has_design_freq_matches_default_params(name):
    cls = _builder_cls(name)
    expected = "design_freq" in dict(cls.default_params)
    assert REGISTRY[name].has_design_freq is expected


# ---------------------------------------------------------------------------
# Auto-derived slider resolution. A numeric param without an explicit
# ui_params step gets a 0.1% *relative* step (window / 1000, rounded to one
# significant figure) so any scaling factor / fraction / length is
# fine-tunable by hand regardless of magnitude. precision tracks the step.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (0.0010876, 0.001),
        (0.00099, 0.001),
        (0.0023, 0.002),
        (0.003, 0.005),
        (0.028, 0.02),
        (0.06, 0.05),
        (0.00005, 0.00005),
        (0.0, 0.0),
    ],
)
def test_nice_step_snaps_to_one_two_five_series(raw, expected):
    out = _nice_step(raw)
    assert out == pytest.approx(expected)
    if out > 0:
        # leading significant digit is always 1, 2, or 5
        mant = round(out / 10 ** math.floor(math.log10(out)))
        assert mant in (1, 2, 5)


@pytest.mark.parametrize(
    "step, expected",
    [(1.0, 1), (0.1, 2), (0.01, 3), (0.001, 4), (0.0001, 5), (0.00005, 6)],
)
def test_precision_tracks_step_decimals(step, expected):
    assert _precision_for_step(step) == expected


@pytest.mark.parametrize("default", [1.0876, 0.05, 0.012, 0.95, 3.48])
def test_auto_step_is_about_one_per_mille_relative(default):
    spec = _auto_paramspec("some_factor", default, None)
    rel = spec.step / abs(default)
    # 1-2-5 snapping spreads the target 0.1% to roughly [0.067%, 0.167%],
    # but it must stay near 0.1% and never regress to the old 1% auto-step.
    assert 0.0006 <= rel <= 0.0017


def test_explicit_step_override_still_wins():
    spec = _auto_paramspec("length_factor", 1.0, {"step": 0.0001, "precision": 4})
    assert spec.step == pytest.approx(0.0001)
    assert spec.precision == 4


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_auto_derived_length_factors_resolve_at_one_per_mille(name):
    """Every length_factor-family slider without an explicit step must land
    at <=0.12% relative resolution (the regression the centralised auto-step
    fixed: arrays and design_freq loops previously sat at ~1%)."""
    cls = _builder_cls(name)
    ui = dict(cls.default_params).get("ui_params") or {}

    def explicit_step(leaf):
        ov = ui.get(leaf)
        return isinstance(ov, dict) and "step" in ov

    def specs(seq):
        for s in seq:
            inner = getattr(s, "params", None)
            if inner:
                yield from specs(inner)
            else:
                yield s

    for s in specs(REGISTRY[name].param_schema):
        if "length_factor" not in s.name or s.kind != "float":
            continue
        if explicit_step(s.name):
            continue
        # 1-2-5 snapping caps the relative step at ~0.167%; assert well
        # under the old 1% to lock in the resolution fix.
        assert s.step / abs(s.default) <= 0.0018, (name, s.name, s.step, s.default)


# ---------------------------------------------------------------------------
# ui_param layout — explicit row/col knob placement
# ---------------------------------------------------------------------------


def test_layout_is_opt_in():
    """Layout is opt-in: a param with no `layout` override carries
    layout=None (auto-flow), and a design's grid layout is None unless it
    declares a `ui_params["layout"]` dict. Per-param layout likewise only
    appears where the design declared one under ui_params[<param>]."""
    assert _auto_paramspec("x", 1.0, None).layout is None
    for name, ex in REGISTRY.items():
        ui = dict(_builder_cls(name).default_params).get("ui_params") or {}
        expects_grid = isinstance(ui.get("layout"), dict)
        assert (ex.layout is not None) == expects_grid, name
        for s in ex.param_schema:
            if getattr(s, "params", None):  # group — leaves checked elsewhere
                continue
            declared = isinstance(ui.get(s.name), dict) and isinstance(
                ui[s.name].get("layout"), dict
            )
            assert (s.layout is not None) == declared, (name, s.name)


@pytest.mark.parametrize(
    "default, override",
    [
        (1.0, {"layout": {"row": 1, "col": 2, "col_span": 2}}),  # float
        (3, {"layout": {"row": 2, "col": 1}}),  # int
        (True, {"layout": {"col": 1}}),  # bool
        ("a", {"enum_options": ({"value": "a", "label": "A"},), "layout": {"row": 3}}),
    ],
)
def test_per_param_layout_passes_through_every_kind(default, override):
    spec = _auto_paramspec("p", default, dict(override))
    assert spec.layout == override["layout"]


def test_non_dict_layout_is_ignored():
    """A malformed layout value is dropped rather than crashing derivation."""
    assert _auto_paramspec("p", 1.0, {"layout": "nope"}).layout is None


def test_grid_level_layout_from_ui_params():
    """Reserved ui_params['layout'] surfaces on AntennaExample.layout and
    does not leak into the param schema as a phantom slider."""
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder

    class _LayoutBuilder(AntennaBuilder):
        default_params = MappingProxyType(
            {
                "freq": 14.0,
                "a": 1.0,
                "b": 2.0,
                "ui_params": MappingProxyType(
                    {
                        "layout": {"columns": 3},
                        "a": {"layout": {"row": 1, "col": 1}},
                    }
                ),
            }
        )

        def build_wires(self):
            return [((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 3, None, None)]

    ex = _make_example("layout_demo", _LayoutBuilder, defer_hints=True)
    assert ex.layout == {"columns": 3}
    assert "layout" not in {s.name for s in ex.param_schema}
    by_name = {s.name: s for s in ex.param_schema}
    assert by_name["a"].layout == {"row": 1, "col": 1}
    assert by_name["b"].layout is None


def test_hidden_param_suppressed_but_pinned_through_solves():
    """`ui_params[key] = {"hidden": True}` drops the slider but keeps the value.

    bisquare.side_frac only ever multiplies length_factor (one DOF, two knobs),
    so it's hidden. The schema must omit it while length_factor stays, and a
    solve request that doesn't mention side_frac (the frontend can't, having no
    control) must still build with side_frac at its default.
    """
    names = {s.name for s in REGISTRY["loops.bisquare"].param_schema}
    assert "side_frac" not in names
    assert "length_factor" in names  # the visible trim knob remains

    cls = _builder_cls("loops.bisquare")
    b = _build_builder(cls, {"length_factor": 1.1})
    assert b.side_frac == cls.default_params["side_frac"]  # pinned at default
    assert b.length_factor == 1.1


def test_hidden_override_is_generic():
    """The `hidden` override works for any scalar param, not just bisquare."""
    from types import MappingProxyType

    from antennaknobs import AntennaBuilder

    class _HiddenBuilder(AntennaBuilder):
        default_params = MappingProxyType(
            {
                "shown": 1.0,
                "secret": 2.0,
                "ui_params": MappingProxyType({"secret": {"hidden": True}}),
            }
        )

        def build_wires(self):
            return [((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 3, None, None)]

    ex = _make_example("hidden_demo", _HiddenBuilder, defer_hints=True)
    names = {s.name for s in ex.param_schema}
    assert names == {"shown"}  # `secret` suppressed, others untouched


@pytest.mark.parametrize("name", DESIGN_NAMES)
def test_variant_values_fit_their_effective_slider_ranges(name):
    """Every variant's param values must sit inside the slider range the
    frontend will actually show for that variant: the base schema min/max
    overlaid with the variant's explicit variant_ui["params"] hints. A
    variant whose value lands outside its slider strands the knob (the
    invvee flat variants' angle_deg=0 sat below the auto-derived 15.8°
    minimum until the design authored an explicit range)."""
    ex = REGISTRY[name]
    for v in ex.variants:
        over = (ex.variant_ui.get(v) or {}).get("params", {})
        vals = ex.variant_values.get(v, {})
        for spec in ex.param_schema:
            if getattr(spec, "kind", None) not in ("float", "int"):
                continue
            val = vals.get(spec.name, spec.default)
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                continue
            lo = over.get(spec.name, {}).get("min", spec.min)
            hi = over.get(spec.name, {}).get("max", spec.max)
            if lo is not None:
                assert val >= lo, f"{name}/{v}: {spec.name}={val} below min {lo}"
            if hi is not None:
                assert val <= hi, f"{name}/{v}: {spec.name}={val} above max {hi}"


def test_invvee_variant_length_factor_ranges():
    """dipoles.invvee showcases per-variant slider ranges: half-wave
    window (0.8–1.25) for default/dipole, the same ×0.8–×1.25 window
    around each long-wire variant's own length. The dipole variant
    inherits the default window, so it must NOT appear in variant_ui."""
    ex = REGISTRY["dipoles.invvee"]
    lf = next(s for s in ex.param_schema if s.name == "length_factor")
    assert (lf.min, lf.max) == (0.8, 1.25)
    assert ex.variant_ui["three_halves"]["params"]["length_factor"] == {
        "min": 2.38,
        "max": 3.71,
    }
    assert ex.variant_ui["classic_edz"]["params"]["length_factor"] == {
        "min": 2.05,
        "max": 3.2,
    }
    assert "dipole" not in ex.variant_ui
    # the angle slider covers both the drooping default and the flat variants
    ang = next(s for s in ex.param_schema if s.name == "angle_deg")
    assert ang.min == 0.0 and ang.max >= 45.0
