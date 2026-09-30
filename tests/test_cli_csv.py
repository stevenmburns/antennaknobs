"""``--csv PATH`` on ``sweep`` and ``analyze``: the run's numbers as a CSV,
one row per swept point. Small momwire-only runs on the smallest catalog
design (``dipoles.invvee:dipole``); no NEC binary is touched."""

from __future__ import annotations

import csv
import io

import pytest

import antennaknobs as ant

DIPOLE = "dipoles.invvee:dipole"


def _read(text_or_path):
    if "\n" in text_or_path:
        f = io.StringIO(text_or_path)
    else:
        f = open(text_or_path, newline="", encoding="utf-8")  # noqa: SIM115
    with f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def _floats(rows, col):
    return [float(r[col]) for r in rows]


def test_frequency_sweep_file(tmp_path):
    out = tmp_path / "f.csv"
    ant.cli(
        f"sweep --builder {DIPOLE} --param freq --npoints 3 "
        f"--engine momwire:bspline --fn /dev/null --csv {out}".split()
    )
    head, rows = _read(str(out))
    assert head == ["freq", "R_ohm", "X_ohm"]
    assert len(rows) == 3
    freqs = _floats(rows, 0)
    assert freqs == sorted(freqs) and len(set(freqs)) == 3
    # A dipole across the default window: R positive, X crossing zero.
    assert all(r > 0 for r in _floats(rows, 1))
    xs = _floats(rows, 2)
    assert min(xs) < 0 < max(xs)


def test_csv_is_the_same_solve_as_the_swr_table(tmp_path):
    """--swr adds the SWR column, computed at --z0 from the same Z."""
    out = tmp_path / "s.csv"
    ant.cli(
        f"sweep --builder {DIPOLE} --swr --npoints 3 --z0 75 "
        f"--engine momwire:bspline --fn /dev/null --csv {out}".split()
    )
    head, rows = _read(str(out))
    assert head == ["freq", "R_ohm", "X_ohm", "SWR"]
    for r in rows:
        z = complex(float(r[1]), float(r[2]))
        rho = abs((z - 75) / (z + 75))
        assert float(r[3]) == pytest.approx((1 + rho) / (1 - rho), rel=1e-9)


def test_density_two_engines_to_stdout_is_clean_csv(capsys):
    """`-` puts only the CSV on stdout (the printed convergence table goes
    to stderr), one N_ach/R/X/dGamma group per engine."""
    ant.cli(
        f"sweep --builder {DIPOLE} --param nominal_nsegs --range 8 34 "
        "--npoints 3 --engine momwire:bspline,momwire:razor-2p "
        "--fn /dev/null --csv -".split()
    )
    cap = capsys.readouterr()
    head, rows = _read(cap.out)
    assert head[0] == "nominal_N"
    assert head[1:] == [
        f"{e} {c}"
        for e in ("momwire:bspline", "momwire:razor-2p")
        for c in ("N_ach", "R_ohm", "X_ohm", "dGamma")
    ]
    assert [int(r[0]) for r in rows] == sorted(int(r[0]) for r in rows)
    assert len(rows) == 3
    # dGamma is against each engine's own finest rung: zero on the last row.
    assert float(rows[-1][4]) == 0.0 and float(rows[-1][8]) == 0.0
    # The printed table is still printed, on stderr.
    assert "convergence: momwire:bspline" in cap.err
    assert "convergence" not in cap.out


def test_two_engine_knob_sweep_has_a_group_per_engine(tmp_path):
    out = tmp_path / "k.csv"
    ant.cli(
        f"sweep --builder {DIPOLE} --param length_factor --npoints 3 "
        f"--engine momwire:bspline,momwire:razor-2p --fn /dev/null --csv {out}".split()
    )
    head, rows = _read(str(out))
    assert head == [
        "length_factor",
        "momwire:bspline R_ohm",
        "momwire:bspline X_ohm",
        "momwire:razor-2p R_ohm",
        "momwire:razor-2p X_ohm",
    ]
    assert len(rows) == 3 and all(len(r) == 5 for r in rows)


def test_analyze_frequency_sweep_has_swr(tmp_path):
    out = tmp_path / "a.csv"
    ant.cli(
        f"analyze --builder {DIPOLE} --analysis".split()
        + ["band SWR"]
        + f"--engine momwire:bspline --csv {out} --fn /dev/null".split()
    )
    head, rows = _read(str(out))
    assert head == [
        "MHz",
        "momwire:bspline R_ohm",
        "momwire:bspline X_ohm",
        "momwire:bspline SWR",
    ]
    assert len(rows) > 3
    assert all(float(r[3]) >= 1.0 for r in rows)


def test_analyze_map_refuses(tmp_path):
    with pytest.raises(SystemExit, match="two-sweep map"):
        ant.cli(
            f"analyze --builder {DIPOLE} --analysis".split()
            + ["tuning map"]
            + f"--engine momwire:bspline --csv {tmp_path / 'm.csv'}".split()
        )


def test_gain_refuses():
    with pytest.raises(SystemExit, match="--csv"):
        ant.cli(f"sweep --builder {DIPOLE} --gain --csv x.csv".split())


def test_table_unions_rows_and_blanks_missing_cells():
    from antennaknobs import sweep_csv

    head, rows = sweep_csv.table(
        "MHz",
        [
            ("a", [1.0, 2.0], [("R_ohm", [10.0, 20.0])]),
            ("b", [2.0, 3.0], [("R_ohm", [21.0, 31.0])]),
        ],
    )
    assert head == ["MHz", "a R_ohm", "b R_ohm"]
    assert rows == [["1", "10", ""], ["2", "20", "21"], ["3", "", "31"]]
