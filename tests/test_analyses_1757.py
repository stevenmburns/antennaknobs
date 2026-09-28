"""AK#1757, sweep framework step 2: `antennaknobs.analyses` and ``analyze``.

What is pinned here:

- the spec's seven examples print back as code that ``eval``s to the same
  value, and E1/E3 print as the spec page writes them;
- the curve cap refuses a 7-curve product when LISTED, by name, and never
  when an analysis is built;
- roles: ``base`` is the invvee's height (and its variants' and the apex
  design's); a design without one lists no height analysis and refuses E3
  by name; a SimNEC ``JamSegments($segs)`` knob is the density knob;
- a ``role`` key leaves the workbench schema unchanged;
- ORACLE EQUALITY, through the real CLI on both sides: E1, E3 and E6 run by
  ``analyze`` give exactly the per-rung / per-point Z of the equivalent
  ``sweep`` commands, and the same Z∞ lines. The shared solve functions are
  wrapped to record every call, so each comparison also proves which
  function the ``analyze`` path ran;
- refused cells: an engine missing from the roster, and one that refuses the
  design, are named in the output and the rest runs.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import cli, get_builder

sw = importlib.import_module("antennaknobs.sweep")
cli_mod = importlib.import_module("antennaknobs.cli")

SSN = (
    Path(__file__).parent
    / "fixtures"
    / "ssn_numericparam_1716"
    / "snDipoleVarLenSegs.ssn"
)
VARLEN = SSN.with_name("DipoleVarLen.ssn")


# ── the seven examples, as the spec page writes them ─────────────────────


def _examples() -> dict[str, list[an.Analysis]]:
    lf = an.Sweep("length_factor", 0.90, 1.06, points=33)
    refs = an.Ref(r=(50, 75), x=(0,))
    return {
        "E1": [
            an.convergence(
                cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
                ground="finite:13,0.005",
            )
        ],
        "E2": [
            an.Analysis(
                "tuning family",
                lf,
                cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 15, 30, 45, 60))),
                references=refs,
            ),
            an.Analysis(
                "tuning map",
                (lf, an.Sweep("angle_deg", 0, 60, points=25)),
                views=(an.Map(),),
                references=refs,
            ),
        ],
        "E3": [
            an.Analysis(
                "height",
                an.Sweep(an.HEIGHT, 2, 20, points=37),
                cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
                references=an.Ref(r=(50,), x=(0,)),
            )
        ],
        "E4": [an.band_swr(views=(an.Swr(scale="rho"),))],
        "E5": [
            an.band_swr(
                name="rig vs antenna",
                cross=an.Cross(planes=("rig", "T1", "feed")),
                views=(an.Swr(), an.Rx()),
            )
        ],
        "E6": [
            an.convergence(
                sweep=an.Sweep(an.DENSITY, 10, 500, points=20, spacing="log"),
                cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),
            )
        ],
        "E7": [
            an.convergence(
                cross=(
                    an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
                    an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec2")),
                ),
            )
        ],
        # Holds (optimise at each point): data only in step 2.
        "E8": [
            an.Analysis(
                "match vs height",
                an.Sweep(an.HEIGHT, 2, 20, points=37),
                hold=an.Hold("match_z0", adjust=("length_factor", "angle_deg"), z0=50),
                views=(an.Rx(), an.Knobs()),
            )
        ],
        "E9": [
            an.Analysis(
                "resonance vs angle",
                an.Sweep("angle_deg", 0, 60, points=25),
                hold=an.Hold("resonance", adjust=("length_factor",)),
                views=(an.Rx(), an.Knobs()),
                references=an.Ref(r=(50,)),
            )
        ],
    }


@pytest.mark.parametrize(
    "example", ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"]
)
def test_every_spec_example_prints_back_as_code_that_evals_equal(example):
    for a in _examples()[example]:
        code = an.to_code(a)
        assert eval(code, {"an": an}) == a, code


def test_e1_and_e3_print_as_the_spec_page_writes_them():
    e1, e3 = _examples()["E1"][0], _examples()["E3"][0]
    assert an.to_code(e1) == (
        "an.convergence(\n"
        '    cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nec5")),\n'
        '    ground="finite:13,0.005",\n'
        ")"
    )
    assert an.to_code(e3) == (
        "an.Analysis(\n"
        '    "height",\n'
        "    an.Sweep(an.HEIGHT, 2, 20, points=37),\n"
        '    cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),\n'
        "    references=an.Ref(r=(50,), x=(0,)),\n"
        ")"
    )


def test_invvee_returns_e1_and_e3_as_the_spec_writes_them():
    own = get_builder("dipoles.invvee")().build_analyses()
    ex = _examples()
    assert own[0] == ex["E1"][0]
    assert own[1] == ex["E3"][0]
    assert ex["E8"][0] in own and ex["E9"][0] in own


# ── hold: data only ─────────────────────────────────────────────────────


def test_hold_objectives_are_the_optimizers_own():
    from antennaknobs.web.optimize import OBJECTIVES

    for objective, adjust in zip(OBJECTIVES, (("a",), ("a",), ("a", "b")), strict=True):
        assert an.Hold(objective, adjust=adjust).objective == objective
    with pytest.raises(ValueError, match="one of the optimizer's swr, resonance"):
        an.Hold("gain", adjust=("a",))


def test_a_hold_that_is_not_a_square_system_refuses_by_name():
    with pytest.raises(
        ValueError,
        match=re.escape(
            "match_z0 is two equations (R = Z0, X = 0); give it two knobs, or "
            "hold resonance with one (got 1)"
        ),
    ):
        an.Hold("match_z0", adjust=("length_factor",))
    with pytest.raises(ValueError, match="resonance is one equation"):
        an.Hold("resonance", adjust=("length_factor", "angle_deg"))
    with pytest.raises(ValueError, match="at least one knob"):
        an.Hold("swr", adjust=())
    with pytest.raises(ValueError, match="swept or held, not both"):
        an.Analysis(
            "x", an.Sweep("angle_deg"), hold=an.Hold("resonance", adjust=("angle_deg",))
        )
    with pytest.raises(ValueError, match="Knobs view draws a hold"):
        an.Analysis("x", an.Sweep("angle_deg"), views=(an.Knobs(),))


def test_a_role_and_a_name_meeting_on_one_knob_is_refused_when_listed():
    a = an.Analysis(
        "x", an.Sweep(an.HEIGHT), hold=an.Hold("resonance", adjust=("base",))
    )
    assert an.problems(a, get_builder("dipoles.invvee")()) == [
        "REFUSED: the hold adjusts base, which is the swept knob"
    ]


def test_analyze_refuses_a_hold_by_name(capsys):
    why = "hold (optimise at each point): not in the CLI yet (sweep-framework step 6)"
    with pytest.raises(SystemExit, match=re.escape(why)):
        cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "match vs height"])
    cli(["analyze", "--builder", "dipoles.invvee", "--list"])
    out = capsys.readouterr().out
    assert re.search(r"^resonance vs angle .*\n +" + re.escape(why), out, re.M), out


def test_a_malformed_spec_refuses_at_construction_by_name():
    with pytest.raises(TypeError, match="tuple, got the string"):
        an.Cross(engines="nec5")
    with pytest.raises(ValueError, match="exactly one of"):
        an.Cross(engines=("nec5",), grounds=("free",))
    with pytest.raises(ValueError, match="engines twice"):
        an.convergence(cross=(an.Cross(engines=("a",)), an.Cross(engines=("b",))))
    with pytest.raises(ValueError, match="spacing"):
        an.Sweep("x", spacing="geometric")
    with pytest.raises(ValueError, match="scale"):
        an.Swr(scale="log")


# ── the curve cap ────────────────────────────────────────────────────────


def _seven_curves() -> an.Analysis:
    return an.convergence(
        name="seven",
        cross=an.Cross(engines=tuple(f"momwire:e{k}" for k in range(7))),
    )


def test_seven_curves_build_but_are_refused_when_listed(monkeypatch, capsys):
    a = _seven_curves()  # building never refuses: one bad entry cannot sink a list
    assert a.curves == 7
    b = get_builder("dipoles.invvee")()
    assert an.problems(a, b) == ["REFUSED: 7 engines = 7 curves, over the cap of 6"]
    _offer_on_invvee(monkeypatch, [a])
    cli(["analyze", "--builder", "dipoles.invvee:dipole", "--list"])
    out = capsys.readouterr().out
    assert re.search(r"^seven .*\n +REFUSED: 7 engines = 7 curves", out, re.M), out
    with pytest.raises(SystemExit, match="over the cap of 6"):
        cli(["analyze", "--builder", "dipoles.invvee:dipole", "--analysis", "seven"])


def test_six_curves_are_within_the_cap():
    a = an.convergence(
        cross=(
            an.Cross(engines=("a", "b", "c")),
            an.Cross(grounds=("free", "finite")),
        )
    )
    assert a.curves == 6
    assert an.problems(a, get_builder("dipoles.invvee")()) == []


# ── roles ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spec", ["dipoles.invvee", "dipoles.invvee:dipole", "dipoles.invvee_apex"]
)
def test_base_is_the_height_knob(spec):
    b = get_builder(spec)()
    assert an.resolve(an.HEIGHT, b) == an.Resolved("base")
    assert an.resolve(an.DENSITY, b) == an.Resolved("nominal_nsegs")


def test_the_deck_segment_constant_is_the_density_knob():
    b = get_builder(f"@{SSN}")()
    assert an.density_knob(b) == "tmp_segs"
    assert b._params["ui_params"]["tmp_segs"]["role"] == "density"
    assert "role" not in b._params["ui_params"]["dcl_len"]


def test_a_missing_role_is_unavailable_by_name_not_an_error(capsys):
    b = get_builder(f"@{VARLEN}")()
    height = an.resolve(an.HEIGHT, b)
    assert height.knob is None
    assert height.reason == (
        'this design declares no height knob (a ui_params entry with role: "height")'
    )
    # JamSegments(30) is a literal here: the file's segment counts are its own.
    assert an.resolve(an.DENSITY, b).reason == (
        "this design's segment counts are its file's own, and it declares no "
        "density knob"
    )
    assert "height" not in {a.name for a in an.offered(b)}
    e3 = _examples()["E3"][0]
    assert an.problems(e3, b) == [f"UNAVAILABLE: {height.reason}"]
    cli(["analyze", "--builder", f"@{VARLEN}", "--list"])
    out = capsys.readouterr().out
    assert "UNAVAILABLE: this design's segment counts are its file's own" in out


def test_two_knobs_claiming_one_role_is_a_reason():
    b = get_builder("dipoles.invvee")()
    ui = dict(b._params["ui_params"])
    ui["angle_deg"] = {**ui["angle_deg"], "role": "height"}
    b._params["ui_params"] = ui
    assert an.resolve(an.HEIGHT, b).reason == (
        "this design declares 2 height knobs (angle_deg, base); a role names one knob"
    )


# ── the workbench schema ─────────────────────────────────────────────────


def _strip_roles(params):
    ui = {
        k: (
            {kk: vv for kk, vv in v.items() if kk != "role"}
            if hasattr(v, "items")
            else v
        )
        for k, v in params["ui_params"].items()
    }
    return {**params, "ui_params": ui}


@pytest.mark.parametrize("spec", ["dipoles.invvee", f"@{SSN}"])
def test_a_role_key_leaves_the_workbench_schema_unchanged(spec):
    import antennaknobs.web.examples  # noqa: F401  — primes the adapter
    from antennaknobs.web.adapter import _derive_schema

    params = dict(get_builder(spec)()._params)
    stripped = _strip_roles(params)
    assert stripped["ui_params"] != dict(params["ui_params"])  # a role was there
    assert _derive_schema(params) == _derive_schema(stripped)


# ── oracle equality through the CLI ──────────────────────────────────────


def _offer_on_invvee(monkeypatch, analyses):
    """The invvee offers ``analyses`` as its own, through the CLI's lookup."""
    cls = type(get_builder("dipoles.invvee")())
    monkeypatch.setattr(cls, "build_analyses", lambda self: list(analyses))


def _record(monkeypatch, name):
    """Wrap ``sweep.<name>`` to record ``(args, result)`` of every call."""
    calls = []
    inner = getattr(sw, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, out))
        return out

    monkeypatch.setattr(sw, name, wrapped)
    return calls


def _zinf_lines(out):
    return [ln for ln in out.splitlines() if "Z∞ =" in ln]


def test_e1_via_analyze_equals_the_sweep_command(monkeypatch, capsys, tmp_path):
    """E1 as invvee declares it, nec5 off the roster (a refused cell): the
    two momwire curves equal ``sweep --param nominal_nsegs`` exactly, rung
    by rung, with the same Z∞."""
    monkeypatch.delitem(cli_mod.ENGINE_CLASSES, "nec5", raising=False)
    calls = _record(monkeypatch, "_convergence_rows")
    cli(
        [
            "sweep",
            "--builder",
            "dipoles.invvee",
            "--param",
            "nominal_nsegs",
            "--engine",
            "momwire:bspline,momwire:razor-2p",
            "--ground",
            "finite:13,0.005",
            "--fn",
            str(tmp_path / "s.png"),
        ]
    )
    sweep_out = capsys.readouterr().out
    oracle = [c[1][0] for c in calls]
    assert len(oracle) == 2
    calls.clear()
    cli(
        [
            "analyze",
            "--builder",
            "dipoles.invvee",
            "--analysis",
            "convergence",
            "--fn",
            str(tmp_path / "a.png"),
        ]
    )
    out = capsys.readouterr().out
    got = [c[1][0] for c in calls]
    assert len(got) == 2  # the shared function ran once per served curve
    assert got == oracle  # exact: (rung, N achieved, complex Z) per rung
    assert [r[0] for r in got[0]] == list(sw.NOMINAL_NSEGS_LADDER)
    assert _zinf_lines(out) == _zinf_lines(sweep_out)
    assert len(_zinf_lines(out)) == 2
    assert re.search(r"^nec5: refused: engine 'nec5' needs", out, re.M), out
    assert (tmp_path / "a.png").exists()


def test_e3_via_analyze_equals_one_sweep_per_ground(monkeypatch, capsys, tmp_path):
    """E3's crosses, on four heights: each ground's curve equals a separate
    ``sweep --param base --ground <g>`` exactly."""
    e3 = an.Analysis(
        "height",
        an.Sweep(an.HEIGHT, 2, 20, points=4),
        cross=an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
        references=an.Ref(r=(50,), x=(0,)),
    )
    _offer_on_invvee(monkeypatch, [e3])
    calls = _record(monkeypatch, "_solve_at")
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "height",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    capsys.readouterr()
    got = [(list(c[0][2]), c[1]) for c in calls]
    assert len(got) == 3  # one shared-function call per ground
    for k, g in enumerate(("free", "finite:13,0.005", "finite:5,0.001")):
        calls.clear()
        cli(["sweep", "--builder", "dipoles.invvee", "--param", "base",
             "--range", "2", "20", "--npoints", "4", "--ground", g,
             "--fn", str(tmp_path / f"s{k}.png")])  # fmt: skip
        capsys.readouterr()
        want = [(list(c[0][2]), c[1]) for c in calls if len(c[0][2])]
        assert len(want) == 1
        xs, zs = got[k]
        assert xs == want[0][0]
        assert len(zs) == len(want[0][1]) == 4
        # Exact: every port's complex Z at every height.
        assert all(np.array_equal(a, b) for a, b in zip(zs, want[0][1], strict=True)), g


def test_e6_via_analyze_equals_the_sweep_command_and_prints_zinf(
    monkeypatch, capsys, tmp_path
):
    """E6 on Dan's circuit, a short log ladder on two engines: the density
    role gives ``tmp_segs`` the convergence treatment in both commands (table,
    Z∞), the rungs equal ``sweep --range --npoints --log``'s, and the Z at
    each equals the plain knob sweep the command ran before AK#1757 (the
    density wrapper on, one engine at a time)."""
    e6 = an.convergence(
        sweep=an.Sweep(an.DENSITY, 10, 40, points=4, spacing="log"),
        cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p")),
    )
    monkeypatch.setattr(AntennaBuilder, "build_analyses", lambda self: [e6])
    calls = _record(monkeypatch, "_convergence_rows")
    cli(["analyze", "--builder", f"@{SSN}", "--analysis", "convergence",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    out = capsys.readouterr().out
    got = [c[1][0] for c in calls]
    assert len(got) == 2
    assert "== tmp_segs convergence: momwire:bspline ==" in out
    assert len(_zinf_lines(out)) == 2
    calls.clear()
    cli(["sweep", "--builder", f"@{SSN}", "--param", "tmp_segs",
         "--range", "10", "40", "--npoints", "4", "--log",
         "--engine", "momwire:bspline,momwire:razor-2p",
         "--fn", str(tmp_path / "s.png")])  # fmt: skip
    sweep_out = capsys.readouterr().out
    assert [c[1][0] for c in calls] == got
    assert _zinf_lines(sweep_out) == _zinf_lines(out)
    rungs = [r[0] for r in got[0]]
    xs = sw.gen_xs(30, (10.0, 40.0), None, None, 4, log=True)
    assert rungs == [int(x) for x in xs]
    # The pre-AK#1757 path: the plain knob sweep, #1543's wrapper on.
    design = get_builder(f"@{SSN}")
    ground = cli_mod.resolve_ground(cli_mod._GROUND_UNSET, design)
    for spec, rows in zip(("momwire:bspline", "momwire:razor-2p"), got, strict=True):
        factory = cli_mod.make_engine_factory(
            spec, ground, nominal_nsegs=cli_mod.engine_density(spec)
        )
        builder = design()
        old = sw._solve_at(builder, "tmp_segs", xs, factory)
        assert [complex(z[0]) for z in old] == [r[2] for r in rows], spec


# ── refusals ────────────────────────────────────────────────────────────


class _Refuses:
    def __init__(self, builder, **kwargs):
        raise ValueError("this engine refuses the design")


def test_an_engine_refusing_the_design_is_a_named_cell(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(cli_mod.ENGINE_CLASSES, "refuser", _Refuses)
    a = an.convergence(
        sweep=an.Sweep(an.DENSITY, values=(8, 12, 17)),
        cross=an.Cross(engines=("momwire:bspline", "refuser")),
    )
    _offer_on_invvee(monkeypatch, [a])
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "convergence",
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    out = capsys.readouterr().out
    assert "refuser: refused: this engine refuses the design" in out
    assert "momwire:bspline  Z∞ =" in out


@pytest.mark.parametrize(
    ("name", "why"),
    [
        (
            "tuning family",
            "a cross over step: not in the CLI yet (sweep-framework step 5)",
        ),
        ("tuning map", "a two-sweep map: not in the CLI yet (sweep-framework step 5)"),
    ],
)
def test_what_step_2_cannot_run_is_refused_by_name(name, why):
    with pytest.raises(SystemExit, match=re.escape(why)):
        cli(["analyze", "--builder", "dipoles.invvee", "--analysis", name])


def test_code_prints_the_analysis(capsys):
    cli(["analyze", "--builder", "dipoles.invvee", "--analysis", "height", "--code"])
    code = capsys.readouterr().out
    assert eval(code, {"an": an}) == _examples()["E3"][0]


# ── Steve's 2026-09-28 rulings: names and spacing ────────────────────────────


def test_two_own_analyses_with_one_name_are_refused_with_the_fix(monkeypatch, capsys):
    """Names pick one analysis, so two alike refuse, and say how to fix it."""
    from antennaknobs.designs.dipoles.invvee import Builder

    twins = [an.convergence(), an.convergence(cross=an.Cross(grounds=("free",)))]
    monkeypatch.setattr(Builder, "build_analyses", lambda self: twins)
    msg = an.problems(twins[0], Builder())
    assert msg == [
        "REFUSED: 2 analyses are named 'convergence'; give one a name= "
        '(e.g. an.convergence(name="…", …))'
    ]


def test_a_design_analysis_replaces_the_library_one_of_its_name():
    """E1 is the invvee's own "convergence": it replaces the generic one and
    is not a duplicate of it."""
    from antennaknobs.designs.dipoles.invvee import Builder

    b = Builder()
    conv = [a for a in an.offered(b) if a.name == "convergence"]
    assert len(conv) == 1 and conv[0].crosses
    assert not any("named" in p for p in an.problems(conv[0], b))


def test_spacing_none_is_the_sweeps_own_and_prints_nothing():
    s = an.Sweep(an.DENSITY, 10, 500, points=20)
    assert s.spacing is None
    assert "spacing" not in an.to_code(an.convergence(sweep=s))


def test_a_linear_density_ladder_is_refused():
    with pytest.raises(ValueError, match="density ladder is geometric"):
        an.Sweep(an.DENSITY, 10, 500, points=20, spacing="lin")


def test_a_density_knob_named_directly_with_lin_is_refused_when_listed():
    from antennaknobs.designs.dipoles.invvee import Builder

    a = an.Analysis("nsegs lin", an.Sweep("nominal_nsegs", 8, 68, spacing="lin"))
    assert any("plays the density role" in p for p in an.problems(a, Builder()))


# ── a view the design defines itself ──────────────────────────────────────


@dataclass(frozen=True)
class _Gain(an.View):
    """A design's own view class: no view antennaknobs draws."""


@dataclass(frozen=True)
class _MyMap(an.Map):
    """A subclass of a planned view is that view."""


def test_a_views_own_class_is_refused_by_name_not_a_keyerror():
    # Alone, it refuses the analysis in the CLI; beside Rx, it is left out
    # and the rest runs. Both name it and list the views that exist, and
    # neither claims `analyze` draws it (it was a bare KeyError, AK#1757).
    alone = an.Analysis("g", an.Sweep("angle_deg", 0, 60, points=5), views=(_Gain(),))
    mixed = an.Analysis(
        "gm", an.Sweep("angle_deg", 0, 60, points=5), views=(an.Rx(), _Gain())
    )
    (gap,) = ar.cli_gaps(alone)
    assert gap.startswith("the _Gain view: not a view antennaknobs draws")
    assert "an.Rx()" in gap and "an.Knobs()" in gap
    assert ar.skipped_views(mixed) == [gap]
    assert ar.cli_gaps(mixed) == []
    from antennaknobs.web import analyses_offer as ao

    (why,) = ao.gaps(alone)
    assert why == gap


def test_a_subclass_of_a_planned_view_takes_that_views_step():
    a = an.Analysis("m", an.Sweep("angle_deg", 0, 60, points=5), views=(_MyMap(),))
    assert ar.cli_gaps(a) == [
        "the _MyMap view: not in the CLI yet (sweep-framework step 5)"
    ]
