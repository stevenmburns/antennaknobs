"""antennaknobs#1554: `sweep --param nominal_nsegs` is a convergence study.

Ask: one command sweeps `nominal_nsegs` across several engines the way the
app's convergence overlay is one checkbox — Smith-chart trajectories with a
per-engine Richardson Z* marker, plus a table on stdout.

What is gated here, matching the issue's own gate paragraph:

  1. a dipole ladder on momwire:bspline and momwire:razor-2p gives two
     monotone trajectories whose Richardson estimates agree with each other
     and with a high-N bspline solve, and the achieved-N column shows the
     parity rounding;
  2. a frequency sweep with two engines draws two loci;
  3. the existing single-engine sweeps are unchanged: they still print
     nothing to stdout;
  4. the usage errors from the design decisions fire with one-sentence
     messages.

The dipole and the 4-rung range (rather than the full 7-rung default ladder)
are what keeps this under ~10s: `dipoles.invvee:dipole` is the smallest
catalog design with a plain one-port feed, momwire is fast, and 8 solves
(2 engines x 4 rungs) plus one bs2 reference solve is the whole test.
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt

import antennaknobs as ant
from antennaknobs.cli import get_builder

DIPOLE = "dipoles.invvee:dipole"
# Geometric, not the app's default 7-rung ladder (#1554 decision 2): fast
# enough for the fast test loop and still spans a >4x refinement.
RANGE = "--range 8 34 --npoints 4"

_ROW_RE = re.compile(
    r"^\s*(?P<nominal>\d+)\s+(?P<achieved>\d+)\s+(?P<r>[+-]?\d+\.\d+)\s+"
    r"(?P<x>[+-]?\d+\.\d+)\s+(?P<dgamma>\d+\.\d+)\s*$"
)
_ZSTAR_RE = re.compile(
    r"^(?P<name>\S+)\s+Z\* = (?P<re>[+-]?\d+\.\d+)(?P<im>[+-]\d+\.\d+)j\s+"
    r"\(shrinking: (?P<shrink>yes|no)\)$"
)
_HEADER_RE = re.compile(r"^== nominal_nsegs convergence: (?P<name>\S+) ==$")


def _parse_convergence_table(text):
    """{engine: {"rows": [(nominal, achieved, z), ...], "z_star": complex,
    "shrinking": bool}} from the table `_print_convergence_table` writes."""
    out = {}
    current = None
    for line in text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            current = m.group("name")
            out[current] = {"rows": []}
            continue
        m = _ROW_RE.match(line)
        if m and current is not None:
            z = complex(float(m.group("r")), float(m.group("x")))
            out[current]["rows"].append(
                (int(m.group("nominal")), int(m.group("achieved")), z)
            )
            continue
        m = _ZSTAR_RE.match(line)
        if m:
            out[m.group("name")]["z_star"] = complex(
                float(m.group("re")), float(m.group("im"))
            )
            out[m.group("name")]["shrinking"] = m.group("shrink") == "yes"
    return out


def test_density_ladder_two_engines_converge_and_agree(capsys):
    ant.cli(
        f"sweep --builder {DIPOLE} --param nominal_nsegs {RANGE} "
        f"--engine momwire:bspline,momwire:razor-2p --fn /dev/null".split()
    )
    out = capsys.readouterr().out
    table = _parse_convergence_table(out)
    assert set(table) == {"momwire:bspline", "momwire:razor-2p"}

    # Achieved N tracks the ladder rung, and the two engines' PARITY
    # rounding differs (bspline odd, razor-2p even) at every rung.
    bs_ach = [a for _, a, _ in table["momwire:bspline"]["rows"]]
    rz_ach = [a for _, a, _ in table["momwire:razor-2p"]["rows"]]
    assert all(n % 2 == 1 for n in bs_ach), bs_ach
    assert all(n % 2 == 0 for n in rz_ach), rz_ach
    assert bs_ach != rz_ach

    for name in table:
        rows = table[name]["rows"]
        z_star = table[name]["z_star"]
        # Monotone convergence: |Z_k - Z*| strictly decreases over the last
        # three rungs.
        dists = [abs(z - z_star) for _, _, z in rows[-3:]]
        assert dists == sorted(dists, reverse=True), (name, dists)
        assert table[name]["shrinking"]

    z_bs = table["momwire:bspline"]["z_star"]
    z_rz = table["momwire:razor-2p"]["z_star"]
    # The two engines' Richardson estimates agree with each other...
    assert abs(z_bs - z_rz) / abs(z_bs) < 0.02

    # ...and with a high-N (nominal 160) bspline reference solve, the same
    # seam tolerance the density studies (#1525) use.
    from momwire import BSplineSolver

    from antennaknobs.engines.momwire import MomwireEngine

    ref_builder = get_builder(DIPOLE)()
    ref_builder.nominal_nsegs = 160
    z_ref = complex(MomwireEngine(ref_builder, solver=BSplineSolver).impedance()[0])
    assert abs(z_bs - z_ref) / abs(z_ref) < 0.02
    assert abs(z_rz - z_ref) / abs(z_ref) < 0.02


def test_two_engine_frequency_sweep_draws_two_loci(monkeypatch):
    # save_or_show always closes the figure; hold it open long enough to
    # inspect the axes' artists (matches the existing test_smith_chart.py
    # pattern for the same reason).
    monkeypatch.setattr(plt, "close", lambda *a, **k: None)
    try:
        ant.cli(
            f"sweep --builder {DIPOLE} --npoints 3 "
            "--engine momwire:bspline,momwire:razor-2p "
            "--use_smithchart --fn /dev/null".split()
        )
        fig = plt.gcf()
        ax = fig.axes[0]
        labels = {
            line.get_label()
            for line in ax.get_lines()
            if not line.get_label().startswith("_")
        }
        assert labels == {"momwire:bspline", "momwire:razor-2p"}
    finally:
        plt.close("all")


def test_single_engine_sweep_output_is_unchanged(capsys):
    """Requirement 2 (#1554): a single-engine sweep prints nothing new to
    stdout, in Smith or rectangular mode, exactly as before this issue."""
    for extra in ("", " --use_smithchart"):
        ant.cli(f"sweep --builder {DIPOLE} --npoints 3{extra} --fn /dev/null".split())
        assert capsys.readouterr().out == ""


def test_nominal_nsegs_refuses_nominal_nsegs_flag():
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --param nominal_nsegs "
            "--nominal-nsegs 25 --fn /dev/null"
        )
    )
    assert "--nominal-nsegs" in msg and "nominal_nsegs" in msg


def test_nominal_nsegs_refuses_swr():
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --param nominal_nsegs --swr --fn /dev/null"
        )
    )
    assert "--swr" in msg


def test_nominal_nsegs_refuses_gain():
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --param nominal_nsegs --gain --fn /dev/null"
        )
    )
    assert "--gain" in msg


def test_nominal_nsegs_refuses_measured(tmp_path):
    s1p = tmp_path / "meas.s1p"
    s1p.write_text("# MHz S RI R 50\n14.0 0.0 0.0\n")
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --param nominal_nsegs "
            f"--measured {s1p} --fn /dev/null"
        )
    )
    assert "--measured" in msg


def test_nominal_nsegs_refuses_patterns():
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --param nominal_nsegs --patterns --fn /dev/null"
        )
    )
    assert "--patterns" in msg


def test_swr_refuses_multiple_engines():
    msg = str(
        _expect_system_exit(
            f"sweep --builder {DIPOLE} --swr "
            "--engine momwire:bspline,momwire:razor-2p --fn /dev/null"
        )
    )
    assert "--swr" in msg


def _expect_system_exit(argv):
    import pytest

    with pytest.raises(SystemExit) as exc:
        ant.cli(argv.split())
    return exc.value
