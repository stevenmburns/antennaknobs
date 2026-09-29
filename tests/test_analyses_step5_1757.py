"""AK#1757, sweep framework step 5, unit 1: crosses over measurement planes,
designs and a second knob (families), and the two-sweep map, in the CLI.

Every oracle computes the other side by a route that does not pass through
the cross under test:

- planes: each plane curve equals the per-point solve at that plane through
  the workbench's own plane seam (``web.adapter._apply_plane``, which calls
  `plane.driven_at`), and E5's best-SWR rows reproduce;
- designs: each design's curve equals ``analyze`` of that design alone, and
  NEC-2 x the apex knot is a named refused cell while the rest run (E7);
- families: each curve equals ``sweep --param ... --set <step>=<value>``;
- the map: every grid cell equals a per-point solve at (x, y), the contours
  are drawn from that same grid, and E2's recorded grid agrees.

Each cross kind also has an adversarial check that fails if the cross
collapsed to one curve (or one cell): the curves differ, one per value.
"""

from __future__ import annotations

import importlib
import itertools
import json
import math
import re
import shutil
from pathlib import Path

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import cli, get_builder

sw = importlib.import_module("antennaknobs.sweep")
cli_mod = importlib.import_module("antennaknobs.cli")

FIXTURES = Path(__file__).parent / "fixtures"
E5_DECK = FIXTURES / "simnec_ac6la_1679" / "Bydipole-TL-Xfmr-CLC.ssn"
EX2_GRID = FIXTURES / "sweep_examples_1757" / "ex2_grid.json"
E5_PLANES = ("rig", "C1", "L1", "C2", "B", "R1", "T1", "feed")


def _offer(monkeypatch, cls, analyses):
    """``cls`` offers ``analyses`` as its own, through the CLI's lookup."""
    monkeypatch.setattr(cls, "build_analyses", lambda self: list(analyses))


def _invvee_cls():
    return type(get_builder("dipoles.invvee")())


def _capture_run(monkeypatch):
    """Wrap `analysis_run.run` (the CLI calls it through the module) and
    keep what each call returned."""
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    return got


def _record(monkeypatch, module, name):
    """Wrap ``module.<name>`` to record ``(args, kwargs, result)`` of every
    call."""
    calls = []
    inner = getattr(module, name)

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        calls.append((args, kwargs, out))
        return out

    monkeypatch.setattr(module, name, wrapped)
    return calls


def _max_rel(a, b) -> float:
    a, b = np.asarray(a, dtype=complex), np.asarray(b, dtype=complex)
    return float(np.max(np.abs(a - b) / np.abs(b)))


def _analyze(args, tmp_path, name="a.png"):
    cli(["analyze", *args, "--fn", str(tmp_path / name)])


# ── crosses multiply, under the cap, refused when listed ──────────────────


def test_crosses_multiply_across_every_kind_and_the_product_is_named_over_cap():
    b = get_builder("dipoles.invvee")()
    ok = an.Analysis(
        "six",
        an.Sweep("length_factor", 0.9, 1.0, points=3),
        cross=(
            an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
            an.Cross(step=an.Sweep("angle_deg", values=(0, 30, 60))),
        ),
    )
    assert ok.curves == 6 and an.problems(ok, b) == []
    over = an.Analysis(
        "eight",
        an.Sweep("length_factor", 0.9, 1.0, points=3),
        cross=(
            an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex")),
            an.Cross(engines=("momwire:bspline", "momwire:razor-2p")),
            an.Cross(step=an.Sweep("angle_deg", values=(0, 60))),
        ),
    )
    assert an.problems(over, b) == [
        "REFUSED: 2 designs x 2 engines x 2 values = 8 curves, over the cap of 6"
    ]
    planes = an.band_swr(
        cross=(
            an.Cross(planes=("rig", "T1", "feed")),
            an.Cross(grounds=("free", "finite:13,0.005", "finite:5,0.001")),
        )
    )
    assert an.problems(planes, b) == [
        "REFUSED: 3 planes x 3 grounds = 9 curves, over the cap of 6"
    ]


def test_cells_enumerate_the_product_in_written_order_with_their_labels():
    a = an.Analysis(
        "p",
        an.Sweep(an.FREQUENCY),
        cross=(
            an.Cross(planes=("rig", "feed")),
            an.Cross(step=an.Sweep("angle_deg", values=(0, 30))),
            an.Cross(engines=("momwire:bspline",)),
        ),
    )
    got = ar.cells(a, "momwire", get_builder("dipoles.invvee")())
    assert [c.label for c in got] == [
        "rig, angle_deg = 0, momwire:bspline",
        "rig, angle_deg = 30, momwire:bspline",
        "feed, angle_deg = 0, momwire:bspline",
        "feed, angle_deg = 30, momwire:bspline",
    ]
    assert [(c.plane, c.step, c.engine) for c in got][1] == (
        "rig",
        ("angle_deg", 30),
        "momwire:bspline",
    )


def test_a_value_named_twice_in_a_cross_is_refused_when_listed():
    b = get_builder("dipoles.invvee")()
    for cross, word in (
        (an.Cross(planes=("rig", "rig")), "'rig'"),
        (an.Cross(designs=("dipoles.invvee", "dipoles.invvee")), "'dipoles.invvee'"),
        (an.Cross(step=an.Sweep("angle_deg", values=(10, 10))), "10"),
    ):
        a = an.Analysis("t", an.Sweep("length_factor", 0.9, 1.0), cross=cross)
        assert f"names {word} twice" in "; ".join(an.problems(a, b)), cross


def test_a_knob_swept_and_stepped_or_mapped_twice_is_refused_when_listed():
    b = get_builder("dipoles.invvee")()
    fam = an.Analysis(
        "f",
        an.Sweep("angle_deg", 0, 60),
        cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 30))),
    )
    assert an.problems(fam, b) == [
        "REFUSED: the family steps angle_deg, which is the swept knob"
    ]
    twice = an.Analysis(
        "m",
        (an.Sweep("base", 2, 4), an.Sweep(an.HEIGHT, 2, 4)),
        views=(an.Map(),),
    )
    assert an.problems(twice, b) == ["REFUSED: the map sweeps base on both axes"]


def test_the_density_knob_as_a_family_or_map_axis_is_refused_by_name():
    # The CLI's engines hold a non-ladder sweep at the engine's own density
    # (#1543): stepping that knob would draw one mesh N times.
    b = get_builder("dipoles.invvee")()
    for a in (
        an.Analysis(
            "f",
            an.Sweep("length_factor", 0.9, 1.0),
            cross=an.Cross(step=an.Sweep(an.DENSITY, values=(8, 16))),
        ),
        an.Analysis(
            "g",
            an.Sweep("length_factor", 0.9, 1.0),
            cross=an.Cross(step=an.Sweep("nominal_nsegs", values=(8, 16))),
        ),
        an.Analysis(
            "m",
            (an.Sweep("length_factor", 0.9, 1.0), an.Sweep("nominal_nsegs", 8, 16)),
            views=(an.Map(),),
        ),
    ):
        (gap,) = ar.cli_gaps(a, b)
        assert gap.startswith("a map axis or family over the density knob"), a.name


def test_the_map_view_and_the_curve_views_refuse_the_other_sweep_shape():
    one = an.Analysis("m1", an.Sweep("angle_deg", 0, 60), views=(an.Map(),))
    assert ar.cli_gaps(one) == [
        "the Map view: a map draws a pair of sweeps, an.Analysis(name, (x, y)); "
        "this analysis sweeps one"
    ]
    pair = (an.Sweep("length_factor", 0.9, 1.0), an.Sweep("angle_deg", 0, 60))
    rx = an.Analysis("m2", pair, views=(an.Rx(),))
    (gap,) = ar.cli_gaps(rx)
    assert gap.startswith("the Rx view of a two-sweep map")
    mixed = an.Analysis("m3", pair, views=(an.Map(), an.Smith()))
    assert ar.cli_gaps(mixed) == []
    assert ar.skipped_views(mixed)[0].startswith("the Smith view of a two-sweep map")


@pytest.mark.parametrize(
    ("name", "refused"),
    [("tuning family", False), ("tuning map", True), ("feed spellings", False)],
)
def test_step5_analyses_run_in_the_cli_and_the_map_stays_refused_in_the_workbench(
    name, refused
):
    """The workbench draws crosses over planes, designs and families since
    step 5 unit 4b; the two-sweep map is still refused there."""
    from antennaknobs.web import analyses_offer as ao

    b = get_builder("dipoles.invvee")()
    a = ar.find(b, name)
    assert an.problems(a, b) == [] and ar.cli_gaps(a, b) == []
    later = [g for g in ao.gaps(a) if "not in the workbench yet" in g]
    assert bool(later) is refused, later


# ── planes (E5) ────────────────────────────────────────────────────────────


def _workbench_plane_z(plane, xs, spec="momwire", ground=None):
    """Z at port 0 at each frequency, one solve per point, at ``plane``
    through the workbench's own seam (`web.adapter._apply_plane`)."""
    import antennaknobs.web.examples  # noqa: F401 — before the adapter (import cycle)
    from antennaknobs.web.adapter import _apply_plane

    design = get_builder(f"@{E5_DECK}")
    g = cli_mod.resolve_ground(
        cli_mod._GROUND_UNSET if ground is None else ground, design
    )
    factory = cli_mod.make_engine_factory(
        spec, g, nominal_nsegs=cli_mod.engine_density(spec)
    )
    out = []
    for f in xs:
        b = design()
        b.freq = float(f)
        solved_at, planes = _apply_plane(b, {"plane": plane})
        assert solved_at == plane and list(planes) == list(E5_PLANES)
        out.append(complex(factory(b).impedance()[0]))
    return out


def test_every_plane_curve_equals_the_workbench_solve_at_that_plane(
    monkeypatch, capsys, tmp_path
):
    """All eight of the deck's planes, on its own 15-point range and its own
    ground: each curve is the workbench's plane solve, point by point."""
    a = an.band_swr(
        name="planes", cross=an.Cross(planes=E5_PLANES), views=(an.Swr(), an.Table())
    )
    # Eight planes are over the cap: this test lifts it to reach them all.
    monkeypatch.setattr(an, "CURVE_CAP", 8)
    _offer(monkeypatch, AntennaBuilder, [a])
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", f"@{E5_DECK}", "--analysis", "planes"], tmp_path)
    out = capsys.readouterr().out
    curves = runs[0]["curves"]
    assert list(curves) == list(E5_PLANES) and runs[0]["refused"] == {}
    xs = curves["rig"][0]
    assert len(xs) == 15 and xs[0] == 14.0 and xs[-1] == pytest.approx(14.35)
    worst = 0.0
    for plane in E5_PLANES:
        want = _workbench_plane_z(plane, xs)
        worst = max(worst, _max_rel(curves[plane][1], want))
        assert f"== frequency sweep: {plane} ==" in out  # the table, per curve
    assert worst <= 1e-12, worst
    # Adversarial: not one plane drawn eight times. rig and C1 read the same
    # Z, and must: the deck joins them by an ideal 1:1 transformer. The
    # other six planes each differ from every other.
    first = {plane: complex(curves[plane][1][0]) for plane in E5_PLANES}
    assert _max_rel([first["rig"]], [first["C1"]]) < 1e-12
    distinct = {round(z.real, 6) for p, z in first.items() if p != "C1"}
    assert len(distinct) == 7, first


# E5 as docs/design/sweep-framework-examples.md records it (0.90.0,
# momwire:bspline, 13.9..14.45 MHz in 23 points): best SWR, where, and Z
# there. Those numbers are FREE SPACE, though the page captions them "the
# file's own ground": on this deck's own Sommerfeld ground (εr 20, σ 0.0303)
# the rig reads 51.24 − j4.16 at 14.45, SWR 1.09. The 0.90.0 script ran with
# no ground given, and momwire's no-ground default was free space then (the
# engine-ground trap); today no --ground is the file's own.
E5_BEST = {
    "rig": (1.19, 14.450, 43.12 - 4.33j),
    "T1": (1.39, 14.250, 37.59 - 7.39j),
    "feed": (1.45, 14.250, 72.51 - 1.90j),
}


def test_e5_best_swr_rows_reproduce_in_free_space(monkeypatch, capsys, tmp_path):
    e5 = an.band_swr(
        name="rig vs antenna",
        sweep=an.Sweep(an.FREQUENCY, 13.9, 14.45, points=23),
        cross=an.Cross(planes=("rig", "T1", "feed")),
        views=(an.Swr(), an.Rx()),
    )
    _offer(monkeypatch, AntennaBuilder, [e5])
    runs = _capture_run(monkeypatch)
    overlay = _record(monkeypatch, sw, "_rx_overlay")
    _analyze(
        [
            "--builder",
            f"@{E5_DECK}",
            "--analysis",
            "rig vs antenna",
            "--ground",
            "free",
        ],
        tmp_path,
    )
    out = capsys.readouterr().out
    curves = runs[0]["curves"]
    for plane, (swr, mhz, z) in E5_BEST.items():
        xs, zs = np.asarray(curves[plane][0]), np.asarray(curves[plane][1])
        k = int(np.argmin(ar.swr_of(zs, 50.0)))
        assert round(float(ar.swr_of(zs, 50.0)[k]), 2) == swr, plane
        assert xs[k] == pytest.approx(mhz, abs=1e-9), plane
        assert abs(zs[k] - z) < 0.006, (plane, zs[k])
        assert f"{plane}: 2:1 BW" in out
    # The legend names each curve by its plane, exactly as the deck names
    # its ports.
    (call,) = overlay
    assert [row[0] for row in call[0][0]] == ["rig", "T1", "feed"]


def test_a_plane_the_design_lacks_is_a_named_refused_cell_and_the_rest_run(
    monkeypatch, capsys, tmp_path
):
    a = an.band_swr(
        name="p",
        sweep=an.Sweep(an.FREQUENCY, 14.0, 14.2, points=3),
        cross=an.Cross(planes=("rig", "nowhere")),
        views=(an.Swr(),),
    )
    _offer(monkeypatch, AntennaBuilder, [a])
    runs = _capture_run(monkeypatch)
    views = _record(monkeypatch, ar, "_views_figure")
    _analyze(["--builder", f"@{E5_DECK}", "--analysis", "p"], tmp_path)
    out = capsys.readouterr().out
    assert list(runs[0]["curves"]) == ["rig"]
    assert re.search(
        r"^nowhere: refused: no plane 'nowhere' on this design; it offers rig, C1,",
        out,
        re.M,
    ), out
    (call,) = views
    assert call[1]["refused"] == ["nowhere"]  # the legend names it


def test_a_design_with_no_network_refuses_every_plane_by_name(
    monkeypatch, capsys, tmp_path
):
    a = an.Analysis(
        "p",
        an.Sweep("length_factor", 0.95, 1.0, points=2),
        cross=an.Cross(planes=("feed",)),
    )
    _offer(monkeypatch, _invvee_cls(), [a])
    with pytest.raises(SystemExit, match="every curve was refused"):
        _analyze(["--builder", "dipoles.invvee", "--analysis", "p"], tmp_path)
    assert "feed: refused: no plane 'feed': this design has no network" in (
        capsys.readouterr().out
    )


# ── designs (E7) ──────────────────────────────────────────────────────────

LADDER = an.Sweep(an.DENSITY, values=(8, 12, 17))
TWO_DESIGNS = an.Cross(designs=("dipoles.invvee", "dipoles.invvee_apex"))
MOMWIRE = ("momwire:bspline", "momwire:razor-2p")


def test_each_design_curve_equals_analyze_of_that_design_alone(
    monkeypatch, capsys, tmp_path
):
    crossed = an.convergence(
        sweep=LADDER, cross=(TWO_DESIGNS, an.Cross(engines=MOMWIRE))
    )
    alone = an.convergence(sweep=LADDER, cross=an.Cross(engines=MOMWIRE))
    _offer(monkeypatch, _invvee_cls(), [crossed])  # invvee_apex inherits it
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "convergence"], tmp_path)
    capsys.readouterr()
    got = runs[0]["curves"]
    assert len(got) == 4 and runs[0]["refused"] == {}
    _offer(monkeypatch, _invvee_cls(), [alone])
    worst = 0.0
    for design in TWO_DESIGNS.designs:
        _analyze(["--builder", design, "--analysis", "convergence"], tmp_path)
        capsys.readouterr()
        want = runs[-1]["curves"]
        for engine in MOMWIRE:
            rungs, zs = got[f"{design}, {engine}"]
            assert rungs == want[engine][0] == [8, 12, 17]
            worst = max(worst, _max_rel(zs, want[engine][1]))
            est = runs[0]["estimates"][f"{design}, {engine}"]
            assert est.z_inf == runs[-1]["estimates"][engine].z_inf
    assert worst <= 1e-12, worst
    # Adversarial: the two spellings are different antennas (#898: about
    # 2 Ω, nearly all X), so a collapsed cross would show here.
    for engine in MOMWIRE:
        bridge = got[f"dipoles.invvee, {engine}"][1][-1]
        apex = got[f"dipoles.invvee_apex, {engine}"][1][-1]
        assert abs(bridge - apex) > 1.0, (engine, bridge, apex)


def _nec2_on_roster(monkeypatch):
    from antennaknobs.engines.nec2 import NEC2Engine

    monkeypatch.setenv("NEC2_EXE", shutil.which("nec2c"))
    monkeypatch.setitem(cli_mod.ENGINE_CLASSES, "nec2", NEC2Engine)


def _refused_apex(monkeypatch, capsys, tmp_path, engine):
    a = an.convergence(
        name="spellings",
        sweep=LADDER,
        cross=(TWO_DESIGNS, an.Cross(engines=("momwire:bspline", engine))),
    )
    _offer(monkeypatch, _invvee_cls(), [a])
    runs = _capture_run(monkeypatch)
    overlay = _record(monkeypatch, sw, "_rx_overlay")
    _analyze(["--builder", "dipoles.invvee", "--analysis", "spellings"], tmp_path)
    out = capsys.readouterr().out
    cell = f"dipoles.invvee_apex, {engine}"
    assert list(runs[0]["refused"]) == [cell]
    assert "PortAtVertex" in runs[0]["refused"][cell]
    assert re.search(
        rf"^{re.escape(cell)}: refused: this design uses PortAtVertex", out, re.M
    )
    assert list(runs[0]["curves"]) == [
        "dipoles.invvee, momwire:bspline",
        f"dipoles.invvee, {engine}",
        "dipoles.invvee_apex, momwire:bspline",
    ]
    (call,) = overlay
    assert call[1]["refused"] == [cell]  # in the legend


@pytest.mark.skipif(
    cli_mod.PyNECEngine is None, reason="pynec (NEC-2 in process) not installed"
)
def test_nec2_in_process_x_apex_is_a_named_refused_cell(monkeypatch, capsys, tmp_path):
    _refused_apex(monkeypatch, capsys, tmp_path, "pynec")


@pytest.mark.skipif(
    shutil.which("nec2c") is None,
    reason="no NEC-2 binary: set NEC2_EXE, or put nec2c on PATH",
)
def test_nec2_x_apex_is_a_named_refused_cell(monkeypatch, capsys, tmp_path):
    _nec2_on_roster(monkeypatch)
    _refused_apex(monkeypatch, capsys, tmp_path, "nec2")


# E7's Z∞ table (docs/design/sweep-framework-examples.md, momwire main, free
# space, the app's 7-rung ladder): the momwire rows.
E7_ZINF = {
    "dipoles.invvee, momwire:bspline": 55.144 - 9.674j,
    "dipoles.invvee, momwire:razor-2p": 55.097 - 10.072j,
    "dipoles.invvee_apex, momwire:bspline": 54.512 - 11.830j,
    "dipoles.invvee_apex, momwire:razor-2p": 54.464 - 12.271j,
}


def test_e7_as_the_invvee_declares_it(monkeypatch, capsys, tmp_path):
    """ "feed spellings" itself: the four momwire cells run and reproduce
    E7's Z∞ table; NEC-2 x apex is refused (by the engine where NEC-2 is on
    the roster, else with both NEC-2 cells by the roster)."""
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "feed spellings"], tmp_path)
    out = capsys.readouterr().out
    est = runs[0]["estimates"]
    for label, z in E7_ZINF.items():
        assert abs(est[label].z_inf - z) < 6e-4, (label, est[label].z_inf)
    assert "dipoles.invvee_apex, nec2" in runs[0]["refused"]
    assert "dipoles.invvee_apex, nec2: refused:" in out


# ── families (E2's family) ────────────────────────────────────────────────


def test_each_family_curve_equals_the_sweep_with_the_step_knob_set(
    monkeypatch, capsys, tmp_path
):
    fam = an.Analysis(
        "fam",
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 30, 60))),
        views=(an.Rx(), an.Table()),
    )
    _offer(monkeypatch, _invvee_cls(), [fam])
    runs = _capture_run(monkeypatch)
    overlay = _record(monkeypatch, sw, "_rx_overlay")
    _analyze(["--builder", "dipoles.invvee", "--analysis", "fam"], tmp_path)
    out = capsys.readouterr().out
    got = runs[0]["curves"]
    labels = ["angle_deg = 0", "angle_deg = 30", "angle_deg = 60"]
    assert list(got) == labels
    assert [row[0] for row in overlay[0][0][0]] == labels  # the legend
    for label in labels:
        assert f"== length_factor sweep: {label} ==" in out  # table per curve
    calls = _record(monkeypatch, sw, "_solve_at")
    worst = 0.0
    for label, angle in zip(labels, (0, 30, 60), strict=True):
        calls.clear()
        cli(["sweep", "--builder", "dipoles.invvee", "--param", "length_factor",
             "--range", "0.95", "1.0", "--npoints", "3",
             "--set", f"angle_deg={angle}",
             "--fn", str(tmp_path / f"s{angle}.png")])  # fmt: skip
        capsys.readouterr()
        (want,) = [c for c in calls if len(c[0][2])]
        assert list(want[0][2]) == got[label][0]
        worst = max(worst, _max_rel(got[label][1], [z[0] for z in want[2]]))
    assert worst <= 1e-12, worst
    # Adversarial: the droop moves R by tens of ohms (E2's family), so three
    # curves that agree would be one curve drawn three times.
    r_mid = [got[label][1][1].real for label in labels]
    assert min(abs(a - b) for a, b in itertools.pairwise(r_mid)) > 5.0, r_mid


def test_a_frequency_family_draws_every_panel_view_per_curve(
    monkeypatch, capsys, tmp_path
):
    """The step-4 views under a family: Swr, S11, Smith and Table each draw
    one curve per value, and each curve is the SWR sweep at that value."""
    fam = an.band_swr(
        name="fam swr",
        sweep=an.Sweep(an.FREQUENCY, 28.0, 29.0, points=3),
        cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 60))),
        views=(an.Swr(), an.S11(), an.Smith(), an.Table()),
    )
    _offer(monkeypatch, _invvee_cls(), [fam])
    runs = _capture_run(monkeypatch)
    views = _record(monkeypatch, ar, "_views_figure")
    _analyze(["--builder", "dipoles.invvee", "--analysis", "fam swr"], tmp_path)
    out = capsys.readouterr().out
    labels = ["angle_deg = 0", "angle_deg = 60"]
    (call,) = views
    assert [c[0] for c in call[0][0]] == labels
    assert [type(v).__name__ for v in call[0][1]] == ["Swr", "S11", "Smith"]
    for label in labels:
        assert f"== frequency sweep: {label} ==" in out
        assert f"{label}: 2:1 BW" in out
    got = runs[0]["curves"]
    calls = _record(monkeypatch, sw, "swr_curve")
    for label, angle in zip(labels, (0, 60), strict=True):
        calls.clear()
        cli(["sweep", "--builder", "dipoles.invvee", "--swr",
             "--range", "28", "29", "--npoints", "3",
             "--set", f"angle_deg={angle}",
             "--fn", str(tmp_path / f"s{angle}.png")])  # fmt: skip
        capsys.readouterr()
        (want,) = calls
        assert _max_rel(got[label][1], np.asarray(want[2][0])[:, 0]) <= 1e-12
    assert abs(got[labels[0]][1][1] - got[labels[1]][1][1]) > 5.0


def test_e2s_family_runs_as_declared(monkeypatch, capsys, tmp_path):
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "tuning family"], tmp_path)
    capsys.readouterr()
    curves = runs[0]["curves"]
    assert list(curves) == [f"angle_deg = {v}" for v in (0, 15, 30, 45, 60)]
    assert all(len(xs) == 33 for xs, _ in curves.values())


# ── the map (E2's map) ─────────────────────────────────────────────────────


def _small_map(**kw):
    return an.Analysis(
        "small map",
        (
            an.Sweep("length_factor", 0.95, 1.0, points=3),
            an.Sweep("angle_deg", 0, 60, points=4),
        ),
        views=(an.Map(), an.Table()),
        references=an.Ref(r=(50, 75), x=(0,)),
        **kw,
    )


def test_every_map_cell_equals_the_per_point_solve(monkeypatch, capsys, tmp_path):
    _offer(monkeypatch, _invvee_cls(), [_small_map()])
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "small map"], tmp_path)
    out = capsys.readouterr().out
    xs, ys, z = runs[0]["maps"]["momwire"]
    assert z.shape == (4, 3)  # rows are y, columns x: not transposed
    design = get_builder("dipoles.invvee")
    ground = cli_mod.resolve_ground(cli_mod._GROUND_UNSET, design)
    factory = cli_mod.make_engine_factory(
        "momwire", ground, nominal_nsegs=cli_mod.engine_density("momwire")
    )
    want = np.empty_like(z)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            b = design()
            b.length_factor = float(x)
            b.angle_deg = float(y)
            want[j, i] = factory(b).impedance()[0]
    assert _max_rel(z, want) <= 1e-12, _max_rel(z, want)
    # Adversarial: the grid varies along both axes.
    assert np.min(np.abs(np.diff(z, axis=0))) > 1e-3
    assert np.min(np.abs(np.diff(z, axis=1))) > 1e-3
    assert "== length_factor x angle_deg map: momwire ==" in out
    assert re.search(r"^momwire: least \|Γ\| .* at length_factor ", out, re.M)


def test_the_maps_contours_are_drawn_from_its_own_grid(monkeypatch, capsys, tmp_path):
    from matplotlib.axes import Axes

    drawn = []
    inner = Axes.contour

    def contour(self, *args, **kwargs):
        drawn.append((args, kwargs))
        return inner(self, *args, **kwargs)

    monkeypatch.setattr(Axes, "contour", contour)
    figures = _record(monkeypatch, ar, "_map_figure")
    _offer(monkeypatch, _invvee_cls(), [_small_map()])
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "small map"], tmp_path)
    capsys.readouterr()
    xs, ys, z = runs[0]["maps"]["momwire"]
    assert ar.map_contours(an.Ref(r=(50, 75), x=(0,)), 50) == [
        ("X", 0.0),
        ("R", 50.0),
        ("R", 75.0),
    ]
    levels = {}
    for args, kwargs in drawn:
        cx, cy, field = args
        assert np.array_equal(cx, xs) and np.array_equal(cy, ys)
        (level,) = kwargs["levels"]
        levels[level] = field
    # Each drawn contour is of this grid's own R or X; a level the grid
    # never reaches is named, not drawn.
    for level, field in levels.items():
        assert np.array_equal(field, z.imag if level == 0.0 else z.real)
    assert 0.0 in levels
    assert (tmp_path / "a.png").exists()
    assert len(figures) == 1


def test_no_ref_contours_are_resonance_and_the_match():
    assert ar.map_contours(an.Ref(), 75.0) == [("X", 0.0), ("R", 75.0)]


def test_a_map_crossed_with_engines_draws_one_map_per_cell_and_names_refused(
    monkeypatch, capsys, tmp_path
):
    import matplotlib.pyplot as plt

    legends = []
    inner = ar._map_figure

    def spy(*args, **kwargs):
        inner(*args, **kwargs)
        legends.extend(
            t.get_text()
            for ax in plt.gcf().axes
            if ax.get_legend() is not None
            for t in ax.get_legend().get_texts()
        )

    monkeypatch.setattr(ar, "_map_figure", spy)
    a = _small_map(
        cross=an.Cross(engines=("momwire:bspline", "momwire:razor-2p", "nope"))
    )
    _offer(monkeypatch, _invvee_cls(), [a])
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", "small map"], tmp_path)
    out = capsys.readouterr().out
    maps = runs[0]["maps"]
    assert list(maps) == ["momwire:bspline", "momwire:razor-2p"]
    assert not np.allclose(maps["momwire:bspline"][2], maps["momwire:razor-2p"][2])
    assert "nope: refused:" in out
    assert "nope: refused" in legends and "X = 0 Ω" in legends


def _map_vs_recorded(monkeypatch, capsys, tmp_path, name):
    """Run map ``name`` at E2's recorded grid's own density (the design's
    nominal_nsegs, 21) and ground; return (xs, ys, Z) and the recorded grid
    at those points."""
    rec = json.loads(EX2_GRID.read_text())
    lf, ang = np.array(rec["LF"]), np.array(rec["ANG"])
    grid = np.array(rec["Z_re"]) + 1j * np.array(rec["Z_im"])
    runs = _capture_run(monkeypatch)
    _analyze(["--builder", "dipoles.invvee", "--analysis", name,
              "--ground", "finite:13,0.005", "--nominal-nsegs", "21"],
             tmp_path)  # fmt: skip
    capsys.readouterr()
    xs, ys, z = runs[0]["maps"]["momwire"]
    cols = [int(np.argmin(np.abs(lf - x))) for x in xs]
    rows = [int(np.argmin(np.abs(ang - y))) for y in ys]
    assert np.allclose(lf[cols], xs, rtol=0, atol=1e-12)
    assert np.allclose(ang[rows], ys, rtol=0, atol=1e-12)
    return xs, ys, z, grid[np.ix_(rows, cols)]


# The bound is a sanity bound across releases, not a pin of bit equality:
# measured 2026-09-28, max |ΔZ| is 0 Ω over all 825 cells (bit-identical to
# 0.90.0's grid). --nominal-nsegs 21 states the density the grid was made at;
# the session's plain `momwire` runs at the design's own 21 anyway, while
# `momwire:bspline` at its roster density (15) moves cells by about 0.15 Ω,
# which is the mesh, not the map.
EX2_TOL_OHM = 1e-6


def test_a_map_agrees_with_e2s_recorded_grid(monkeypatch, capsys, tmp_path):
    """Every fourth point of E2's grid each way (9 x 7 cells)."""
    rec = json.loads(EX2_GRID.read_text())
    sub = an.Analysis(
        "sub map",
        (
            an.Sweep("length_factor", values=tuple(rec["LF"][::4])),
            an.Sweep("angle_deg", values=tuple(rec["ANG"][::4])),
        ),
        views=(an.Map(),),
        references=an.Ref(r=(50, 75), x=(0,)),
    )
    _offer(monkeypatch, _invvee_cls(), [sub])
    xs, ys, z, want = _map_vs_recorded(monkeypatch, capsys, tmp_path, "sub map")
    assert z.shape == (7, 9)
    assert float(np.max(np.abs(z - want))) < EX2_TOL_OHM


@pytest.mark.antenna_computation_check
def test_e2s_map_as_declared_agrees_with_the_recorded_grid(
    monkeypatch, capsys, tmp_path
):
    """ "tuning map" itself, all 825 solves (about 6 s, so main-only)."""
    xs, ys, z, want = _map_vs_recorded(monkeypatch, capsys, tmp_path, "tuning map")
    assert z.shape == (25, 33)
    assert float(np.max(np.abs(z - want))) < EX2_TOL_OHM
    # E2's reading: X = 0 meets R = 50 near 32.5° and length_factor 0.978.
    j = int(np.argmin(np.abs(ys - 32.5)))
    i = int(np.argmin(np.abs(z[j].imag)))
    assert math.isclose(xs[i], 0.978, abs_tol=0.006) and abs(z[j, i].real - 50) < 3
