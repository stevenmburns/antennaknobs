from types import MappingProxyType

import pytest

from antennaknobs import AntennaBuilder, resolve_variant_params
from antennaknobs.cli import get_builder, list_variants
from antennaknobs.designs.beams import hexbeam, moxon
from antennaknobs.designs.multiband import twoband_fan_dipole
from antennaknobs.designs.loops import delta_loop
from antennaknobs.designs.specialty import hentenna


def _design_params(inst):
    """Builder _params with the framework keys (nominal_nsegs, ...)
    stripped. Variant resolution is about design params only."""
    return {k: v for k, v in inst._params.items() if k not in inst.FRAMEWORK_PARAMS}


def test_no_colon_uses_default_params():
    factory = get_builder("beams.hexbeam")
    inst = factory()
    assert _design_params(inst) == dict(hexbeam.Builder.default_params)


def test_explicit_default_variant():
    factory = get_builder("hexbeam:default")
    inst = factory()
    assert _design_params(inst) == dict(hexbeam.Builder.default_params)


def test_named_variant_resolves():
    factory = get_builder("hexbeam:opt")
    inst = factory()
    assert _design_params(inst) == dict(hexbeam.Builder.opt_params)


def test_variant_on_moxon_original():
    factory = get_builder("moxon:original")
    inst = factory()
    assert _design_params(inst) == dict(moxon.Builder.original_params)


def test_renamed_twoband_variant():
    # s07_params is complete in regular params but omits `ui_params`; under
    # the overlay it inherits `default_params["ui_params"]` (matching how the
    # default path already builds), so the resolved set is default ⊕ s07.
    factory = get_builder("twoband_fan_dipole:s07")
    inst = factory()
    expected = {
        **dict(twoband_fan_dipole.Builder.default_params),
        **dict(twoband_fan_dipole.Builder.s07_params),
    }
    assert _design_params(inst) == expected


def test_renamed_specialty_variant():
    factory = get_builder("specialty.hentenna:z100")
    inst = factory()
    assert _design_params(inst) == dict(hentenna.Builder.z100_params)


def test_renamed_loop_variant():
    factory = get_builder("loops.delta_loop:z200")
    inst = factory()
    assert _design_params(inst) == dict(delta_loop.Builder.z200_params)


def test_unknown_variant_raises_with_available():
    with pytest.raises(ValueError) as exc:
        get_builder("hexbeam:does_not_exist")
    msg = str(exc.value)
    assert "does_not_exist" in msg
    assert "opt" in msg
    assert "default" in msg


def test_list_variants_for_hexbeam():
    assert list_variants(hexbeam.Builder) == ["default", "opt"]


def test_list_variants_for_moxon():
    assert list_variants(moxon.Builder) == ["default", "opt", "original"]


# --- overlay semantics (Option A: recursive merge over default_params) ---


def test_partial_variant_overlays_default():
    """A partial variant inherits every key it doesn't state from default."""

    class B(AntennaBuilder):
        default_params = MappingProxyType(
            {"freq": 14.0, "length_factor": 1.00, "base": 7.0}
        )
        partial_params = MappingProxyType({"length_factor": 1.08})

    merged = resolve_variant_params(B, "partial")
    assert merged == {"freq": 14.0, "length_factor": 1.08, "base": 7.0}


def test_partial_variant_solves_like_full_equivalent():
    """The regression the overlay is meant to make safe: a partial variant
    (only the changed key) resolves identically to the equivalent full one."""

    class B(AntennaBuilder):
        default_params = MappingProxyType(
            {"freq": 14.0, "length_factor": 1.00, "base": 7.0}
        )
        partial_params = MappingProxyType({"length_factor": 1.08})
        full_params = MappingProxyType(
            {"freq": 14.0, "length_factor": 1.08, "base": 7.0}
        )

    assert resolve_variant_params(B, "partial") == resolve_variant_params(B, "full")


def test_complete_variant_reproduces_itself():
    """Overlaying a complete variant equals that variant — the backward-compat
    guarantee for every pre-overlay variant in the catalog."""

    class B(AntennaBuilder):
        default_params = MappingProxyType({"freq": 14.0, "length_factor": 1.00})
        v_params = MappingProxyType({"freq": 28.0, "length_factor": 1.08})

    assert resolve_variant_params(B, "v") == dict(B.v_params)


def test_ui_params_deep_merge():
    """The one dict-valued param deep-merges: a variant flips a nested ui hint
    without restating the subtree."""

    class B(AntennaBuilder):
        default_params = MappingProxyType(
            {
                "freq": 14.0,
                "ui_params": MappingProxyType(
                    {
                        "sweep_policy": MappingProxyType(
                            {"anchor": "center", "band_locked": False}
                        )
                    }
                ),
            }
        )
        banded_params = MappingProxyType(
            {
                "ui_params": MappingProxyType(
                    {"sweep_policy": MappingProxyType({"band_locked": True})}
                )
            }
        )

    merged = resolve_variant_params(B, "banded")
    # inherited anchor, flipped band_locked, regular params untouched
    assert merged["freq"] == 14.0
    assert merged["ui_params"]["sweep_policy"] == {
        "anchor": "center",
        "band_locked": True,
    }


def test_bands_tuple_replaced_wholesale():
    """The shallow-overlay floor: `bands` is a positional tuple, so a variant
    overriding it replaces the whole tuple rather than merging per-band."""

    class B(AntennaBuilder):
        default_params = MappingProxyType(
            {"n_bands": 2, "bands": ({"freq": 14.0}, {"freq": 21.0})}
        )
        one_band_params = MappingProxyType({"bands": ({"freq": 18.0},)})

    merged = resolve_variant_params(B, "one_band")
    assert merged["bands"] == ({"freq": 18.0},)  # not merged with the default pair
    assert merged["n_bands"] == 2  # untouched scalar still inherited
