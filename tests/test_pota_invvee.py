"""The POTA wire-gauge showcase design (issue #318): dipoles.pota_invvee.

Pins the three-way tradeoff story the design exists to tell — weight vs
radiated power vs resonance placement — plus the web plumbing (wire_type
enum knob, weight result rows, wire-loss budget row).
"""

import pytest

from antennaknobs.designs.dipoles.pota_invvee import Builder
from antennaknobs.engines.momwire import MomwireEngine
from antennaknobs.engines.pynec import DEFAULT_GROUND
from antennaknobs.network import WIRES


def _engine(wire_type=None, **params):
    b = Builder()
    for k, v in params.items():
        setattr(b, k, v)
    if wire_type is not None:
        b.wire_type = wire_type
    return MomwireEngine(b, ground=DEFAULT_GROUND)


def _eff(eng):
    eng.current_distribution()
    return eng._excited_efficiency


def test_default_resonant_on_20m():
    """Stock 22 AWG PVC at length_factor 0.9440 sits near resonance at
    14.1 MHz over average ground, in the ~65 Ω inverted-V window."""
    z = _engine().impedance()[0]
    assert abs(z.imag) < 3.0
    assert 55.0 < z.real < 75.0


def test_gauge_efficiency_ordering():
    """Thicker wire radiates more of the input power: 18 > 22 > 28 AWG,
    each in its physics window (−0.11 / −0.18 / −0.36 dB measured)."""
    eff = {g: _eff(_engine(f"{g}-awg-pvc")) for g in (28, 22, 18)}
    assert eff[18] > eff[22] > eff[28]
    assert 0.90 < eff[28] < 0.94
    assert 0.95 < eff[22] < 0.97
    assert 0.97 < eff[18] < 0.99


def test_insulation_velocity_factor_direction():
    """Bare wire cut to the insulated length resonates HIGH: at the stock
    length the bare 22 AWG shows a large capacitive X (resonance moved up
    by the missing jacket loading)."""
    z_pvc = _engine("22-awg-pvc").impedance()[0]
    z_bare = _engine("22-awg").impedance()[0]
    assert abs(z_pvc.imag) < 3.0
    assert z_bare.imag < -40.0


def test_weight_ordering_matches_catalog():
    w = {g: WIRES[f"{g}-awg-pvc"].weight_g_per_m for g in (28, 22, 18)}
    assert w[28] < w[22] < w[18]


def test_web_example_carries_the_story():
    """The registered example has the wire_type enum, the weight result
    rows, and a solve response with weight fields + wire-loss budget row."""
    from antennaknobs.web.examples import REGISTRY

    ex = REGISTRY["dipoles.pota_invvee"]
    fields = [r.field for r in ex.result_schema]
    assert fields == ["wire_length_m", "wire_weight_g"]
    specs = {p.name: p for p in ex.param_schema if hasattr(p, "name")}
    assert specs["wire_type"].kind == "enum"
    assert len(specs["wire_type"].enum_options) == len(WIRES)
    assert ex.sweep_policy.band_locked

    out = ex.momwire_solve(
        {"measurement_freq_mhz": 14.1, "design_freq_mhz": 14.1, "ground": True}
    )
    spec = WIRES["22-awg-pvc"]
    assert out["wire_weight_g"] == pytest.approx(
        out["wire_length_m"] * spec.weight_g_per_m
    )
    assert 9.0 < out["wire_length_m"] < 11.0
    labels = [b["label"] for b in out["power_budget"]]
    assert labels == ["wire loss (I²R)"]
    assert 0.9 < out["radiation_efficiency"] < 1.0


def test_wire_gauge_analyses_lead_and_run_here():
    """The four wire-gauge charts come first, under their own group, each
    one curve per PVC wire, with nothing the design or the CLI refuses; the
    inverted vee's own analyses follow, inherited."""
    from antennaknobs import analyses as an
    from antennaknobs.analysis_run import cli_gaps

    b = Builder()
    analyses = b.build_analyses()
    gauge = [a for a in analyses if a.group == "Wire gauge"]
    assert (
        [a.name for a in analyses[:4]]
        == [a.name for a in gauge]
        == [
            "Z vs length by gauge",
            "resonant length by gauge",
            "patterns by gauge",
            "band-tuned SWR by gauge",
        ]
    )
    for a in gauge:
        assert a.curves == 6, a.name
        assert an.problems(a, b) == [] and cli_gaps(a, b) == [], a.name
    # And the workbench serves them: /analyses builds the same offer, and a
    # cross it cannot express (a family over this dropdown knob, say) is a
    # 422 for the whole design's list, which the CLI checks above never see.
    from antennaknobs.web.analyses_offer import builder_for, offer
    from antennaknobs.web.server import example_for

    req = {"geometry": "dipoles.pota_invvee"}
    cls = example_for("dipoles.pota_invvee").builder_cls
    served = {e["name"]: e for e in offer(builder_for(cls, req), req)}
    for a in gauge:
        assert served[a.name]["workbench"]["runs"], served[a.name]["workbench"]
    assert "tuning map" in [a.name for a in analyses[4:]]
