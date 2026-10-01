"""AK#1828 unit 4: M0AGP's inverted L vs full-size vertical study (QRZ
thread 1005128), in the catalog.

- ``n_radials`` on ``verticals.inverted_l`` (4) and ``verticals.vertical``
  (3): today's defaults, so no existing geometry moves (pinned wire for
  wire against the counts they hard-coded);
- ``verticals.inverted_l:topband``: the 160 m variant, two radials 5 ft up,
  the vertical section and the top wire in feet, no top wire at 0 ft;
- ``inverted_l``'s ``Builder.build_studies()``: DX gain against the vertical
  section, relative to the full vertical (a FIXED reference), the top wire
  held at resonance (step 6's hold), listed on its own tab only;
- the reproduction THROUGH ``analyze --study`` on momwire: every point held,
  the vertical fixed, the shape monotone, within 0.02 dB of the earlier
  hand-held script and 0.2 dB of his table but at 30 ft (0.75)
  (scratch/1828-m0agp/README.md has the whole table on both engines).
"""

from __future__ import annotations

import itertools
import math

import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import studies
from antennaknobs.cli import get_builder
from antennaknobs.designs.verticals.inverted_l import FT

L = "verticals.inverted_l"
TOPBAND = f"{L}:topband"


def _wires(spec, **knobs):
    b = get_builder(spec)()
    for k, v in knobs.items():
        setattr(b, k, v)
    return b, b.build_wires()


def _radials(b, wires):
    return [w for w in wires if w[0] == (0.0, 0.0, b.base) and w[1][2] == b.base]


def test_the_radial_count_is_a_knob_and_the_defaults_are_todays():
    b, wires = _wires(L)
    assert b.n_radials == 4 and len(_radials(b, wires)) == 4
    assert b.in_feet is False
    # The fractions build it, as they always did: the riser to 0.17 lambda.
    lam = b.design_wavelength
    assert any(math.isclose(w[1][2], b.base + 0.17 * lam) for w in wires)
    v, vw = _wires("verticals.vertical")
    assert v.n_radials == 3 and len(_radials(v, vw)) == 3
    b6, w6 = _wires(L, n_radials=6)
    assert len(_radials(b6, w6)) == 6
    # The feet knobs do nothing until the feet mode is on.
    _, moved = _wires(L, vert_ft=20.0, horiz_ft=5.0)
    assert repr(moved) == repr(wires)


def test_the_topband_variant_is_two_radials_5_ft_up_in_feet():
    b, wires = _wires(TOPBAND, vert_ft=70.0, horiz_ft=60.0)
    assert (b.freq, b.base, b.n_radials, b.in_feet) == (1.83, 1.524, 2, True)
    radials = _radials(b, wires)
    assert len(radials) == 2
    # Perpendicular to the top wire (along x; the top wire runs along +y).
    assert all(abs(w[1][1]) < 1e-9 for w in radials)
    top = b.base + 70.0 * FT
    assert any(w[1] == (0.0, 0.0, top) for w in wires)
    assert any(w[0] == (0.0, 0.0, top) and w[1] == (0.0, 60.0 * FT, top) for w in wires)
    # No top wire at all is the plain vertical.
    _, straight = _wires(TOPBAND, vert_ft=131.2, horiz_ft=0.0)
    assert len(straight) == len(wires) - 1
    assert not any(abs(w[1][1] - w[0][1]) > 1e-9 for w in straight)


def test_the_study_is_its_own_tabs_and_states_its_azimuth():
    b = get_builder(L)()
    found = studies.pool(L, b)
    (st,) = [
        s for s in found.studies if s.analysis.name == "DX gain vs the vertical (M0AGP)"
    ]
    assert st.host == L and st.includes(L) and not st.includes("verticals.vertical")
    a = st.analysis
    (plot,) = an.metric_plots(a)
    assert plot.relative_to == "vertical"
    assert plot.metric == an.ElevationWindow("DX gain", 2, 10, step=0.1, az=0)
    assert a.sweep == an.Sweep(
        "vert_ft", values=tuple(float(v) for v in range(20, 101, 10))
    )
    assert a.hold == an.Hold("resonance", adjust=("horiz_ft",)) and a.ground == "finite"
    assert an.problems(a, b) == []
    # The reference sets the swept knob (and the held one): fixed, solved
    # once at its own setting.
    ref = next(c for c in ar.cells(a, "nec5") if c.label.endswith("vertical"))
    assert ar.reference_fixed(ref, a, get_builder(TOPBAND)())
    # The hold runs (step 6), and the Knobs view draws the held top wire.
    assert ar.cli_gaps(a, b) == []
    assert a.views == (an.MetricPlot(plot.metric, relative_to="vertical"), an.Knobs())
    assert eval(an.to_code(a), {"an": an}) == a


def test_the_t_match_inherits_neither_the_variant_nor_the_study():
    """The T-match is the 10 m L tuned for 12 m: a 160 m variant of it, or
    M0AGP's study on its tab, would be nonsense."""
    from antennaknobs.cli import list_variants
    from antennaknobs.designs.verticals.inverted_l_tmatch import Builder as T

    assert list_variants(T) == ["default"]
    t = get_builder("verticals.inverted_l_tmatch")()
    assert studies.of_builder("verticals.inverted_l_tmatch", t).studies == ()
    assert (
        studies.including(
            "verticals.inverted_l_tmatch",
            studies.pool("verticals.inverted_l_tmatch", t),
        )
        == []
    )


# ── the reproduction, through `analyze --study` (the hold is step 6's) ────

NAME = "verticals.inverted_l:DX gain vs the vertical (M0AGP)"
ENGINE = "momwire:bspline"

#: M0AGP's table: DX gain vs the vertical (dB), by vertical section (ft).
M0AGP = {100: -0.26, 90: -0.45, 80: -0.72, 70: -1.10, 60: -1.66,
         50: -2.51, 40: -3.84, 30: -6.54, 20: -9.64}  # fmt: skip

#: The hand-held script's momwire values at azimuth 0 (relative dB, the
#: resonant top in ft): scratch/1828-m0agp/momwire-1.83.json, made before
#: the framework could hold, with Brent on X. The script resonates its own
#: vertical (131.10 ft); the study's is the catalog's fixed 131.2 ft, and that
#: and the two root searches' tolerances are the whole difference (0.006 dB).
SCRIPT = {100: (-0.1941, 32.979), 90: (-0.363, 43.374), 80: (-0.6138, 53.68),
          70: (-0.9822, 63.884), 60: (-1.5311, 73.976), 50: (-2.3666, 83.936),
          40: (-3.6852, 93.726), 30: (-5.841, 103.277), 20: (-9.4917, 112.424)}  # fmt: skip
TOL_SCRIPT_DB = 0.02
TOL_TOP_FT = 0.05


def _run_study(monkeypatch, tmp_path, values=None) -> dict:
    """``analyze --study NAME`` (the study's own `Builder.build_studies`, its
    sweep cut to ``values`` when given); what the runner computed."""
    import dataclasses

    from antennaknobs.cli import cli
    from antennaknobs.designs.verticals import inverted_l

    if values is not None:
        own = inverted_l.Builder.build_studies

        def reduced(self):
            return [
                dataclasses.replace(a, sweep=an.Sweep("vert_ft", values=values))
                for a in own(self)
            ]

        monkeypatch.setattr(inverted_l.Builder, "build_studies", reduced)
    runs = []
    inner = ar.run

    def rec(*args, **kw):
        out = inner(*args, **kw)
        runs.append(out)
        return out

    monkeypatch.setattr(ar, "run", rec)
    cli(["analyze", "--study", NAME, "--engine", ENGINE,
         "--fn", str(tmp_path / "m0agp.png")])  # fmt: skip
    (out,) = runs
    return out


def _check(out, values):
    per = out["metrics"]["DX gain"]
    (label,) = [k for k in per if k.endswith("inverted L")]
    (ref,) = [k for k in per if k.endswith("vertical")]
    curve, vertical = per[label], per[ref]
    # The vertical is the FIXED reference: solved once, drawn flat, never held.
    assert vertical.fixed and vertical.xs == () and ref not in out["held"]
    assert curve.xs == values and curve.reference == ref
    held = out["held"][label]
    assert all(pt.converged for pt in held)  # every point held: no gaps
    for k, x in enumerate(values):
        rel, top = SCRIPT[int(x)]
        assert abs(curve.relative[k] - rel) < TOL_SCRIPT_DB, (x, curve.relative[k])
        assert abs(held[k].params["horiz_ft"] - top) < TOL_TOP_FT, x
        # Within 0.2 dB of M0AGP's own table, but at 30 ft, where his table
        # breaks its own step pattern (0.7 dB: scratch/1828-m0agp/README.md).
        assert abs(curve.relative[k] - M0AGP[int(x)]) < (0.75 if x == 30 else 0.2)
    # The shape: the shorter the vertical section, the less DX gain, and the
    # longer the resonant top wire.
    rels = list(curve.relative)
    tops = [pt.params["horiz_ft"] for pt in held]
    assert all(a < b for a, b in itertools.pairwise(rels))
    assert all(a > b for a, b in itertools.pairwise(tops))
    return curve


def test_the_study_runs_through_analyze_on_a_reduced_grid(monkeypatch, tmp_path):
    """Three heights, the hold re-tuning the top wire at each: under the
    suite's per-test budget, so it runs on every PR."""
    values = (20.0, 70.0, 100.0)
    out = _run_study(monkeypatch, tmp_path, values)
    _check(out, values)
    assert (tmp_path / "m0agp.png").is_file()
    assert (tmp_path / "m0agp-knobs.png").is_file()


@pytest.mark.antenna_computation_check
def test_the_whole_study_reproduces_the_held_script(monkeypatch, tmp_path):
    """All nine heights, as the catalog declares them (main-only: about 7 s)."""
    out = _run_study(monkeypatch, tmp_path)
    _check(out, tuple(float(v) for v in range(20, 101, 10)))
