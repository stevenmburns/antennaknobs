"""AK#1757, sweep framework step 5, unit 5: the workbench draws R and X
against frequency, sweeps an analysis's explicit frequencies, and prints its
Table, as ``antennaknobs analyze`` does.

Each is the SERVED solve (the request the analysis chart sends, built from
what ``/analyses`` served) against the CLI's ``analyze`` on the same
analysis, both in free space on momwire:bspline at one pinned density:

- R/X against frequency: the chart's grid for the served range (lib/sweep.ts
  `sweepGrid` on `specRange`, re-derived here) is the CLI's grid, and the
  served /sweep over it is the CLI's curve;
- explicit frequencies: ``/analyses`` serves exactly the analysis's values,
  in its order, the chart sends them ascending, and the served Z at each is
  the CLI's at the same frequency;
- the Table: the CLI's printed rows are the served numbers printed in the
  CLI's formats, for a frequency sweep over two designs, a knob family and
  a density ladder. The served numbers and the CLI's rows are written to
  the frontend's ``tableOracle1757.json``, where ``chartTable.test.ts``
  holds lib/chartTable.ts to print the same rows from the same numbers.
  Regenerate with ``AK_WRITE_TABLE_ORACLE=1`` on this module after a
  deliberate change; without it the module holds the committed file to the
  current code.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.cli import cli, get_builder

INVVEE = "dipoles.invvee"
APEX = "dipoles.invvee_apex"
DESIGN_F = 28.47
REL = 1e-9
ORACLE = (
    Path(__file__).resolve().parent.parent
    / "src/antennaknobs/web/frontend/src/__tests__/fixtures/tableOracle1757.json"
)
SOLVE = {
    "solver": "momwire",
    "momwire_model": "bspline",
    "n_per_wire": 15,
    "ground": False,
}
CLI_SOLVE = ["--ground", "free", "--engine", "momwire:bspline", "--nominal-nsegs", "15"]


@pytest.fixture(scope="module")
def client() -> TestClient:
    from antennaknobs.web import server

    return TestClient(server.app)


def _offer(monkeypatch, analyses):
    cls = type(get_builder(INVVEE)())
    monkeypatch.setattr(cls, "build_analyses", lambda self: list(analyses))


def _served(client, name, geometry=INVVEE) -> dict:
    req = {
        "geometry": geometry,
        "design_freq_mhz": DESIGN_F,
        "measurement_freq_mhz": DESIGN_F,
    }
    r = client.post("/analyses", json=req)
    assert r.status_code == 200, r.text
    (entry,) = [a for a in r.json()["analyses"] if a["name"] == name]
    return entry["workbench"]


def _capture_run(monkeypatch):
    got = []
    inner = ar.run

    def wrapped(*args, **kwargs):
        out = inner(*args, **kwargs)
        got.append(out)
        return out

    monkeypatch.setattr(ar, "run", wrapped)
    return got


def _analyze(monkeypatch, capsys, tmp_path, name, *, density=False) -> tuple:
    runs = _capture_run(monkeypatch)
    solve = CLI_SOLVE[:4] if density else CLI_SOLVE
    cli(["analyze", "--builder", INVVEE, "--analysis", name, *solve,
         "--fn", str(tmp_path / "a.png")])  # fmt: skip
    return runs[0], capsys.readouterr().out


def _defaults(client, geometry) -> dict:
    (ex,) = [
        e for e in client.get("/examples").json()["examples"] if e["name"] == geometry
    ]
    return {
        p["name"]: p["default"]
        for p in ex["param_schema"]
        if "default" in p and "params" not in p
    }


def _records(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _sweep(client, freqs, geometry=INVVEE) -> tuple[list[float], list[complex]]:
    body = {
        "geometry": geometry,
        "variant": "default",
        **_defaults(client, geometry),
        "design_freq_mhz": DESIGN_F,
        "measurement_freq_mhz": DESIGN_F,
        **SOLVE,
        "freqs_mhz": list(freqs),
    }
    recs = [r for r in _records(client.post("/sweep", json=body).text) if "z_re" in r]
    return [r["freq_mhz"] for r in recs], [complex(r["z_re"], r["z_im"]) for r in recs]


def _param_sweep(client, param, values, **over) -> list[dict]:
    body = {
        "geometry": INVVEE,
        **_defaults(client, INVVEE),
        "design_freq_mhz": DESIGN_F,
        "measurement_freq_mhz": DESIGN_F,
        **SOLVE,
        **over,
        "param": param,
        "values": list(values),
    }
    recs = _records(client.post("/param_sweep", json=body).text)[:-1]
    assert all("z_re" in r for r in recs), recs
    return recs


def _max_rel(a, b) -> float:
    a, b = np.asarray(a, dtype=complex), np.asarray(b, dtype=complex)
    return float(np.max(np.abs(a - b) / np.abs(b)))


def chart_grid(spec: dict) -> list[float]:
    """lib/sweep.ts: `sweepGrid(specRange(spec))` for a lin range with a
    point count: `specRange` turns the count into a step, and the grid is
    lo + i·step, closing on hi."""
    lo, hi, n = spec["lo"], spec["hi"], spec["points"]
    step = (hi - lo) / (n - 1)
    out = [min(hi, lo + i * step) for i in range(n)]
    out[-1] = hi
    return out


# ── R/X against frequency ─────────────────────────────────────────────────


def test_rx_against_frequency_is_the_clis_curve(monkeypatch, client, capsys, tmp_path):
    a = an.Analysis(
        "rxf", an.Sweep(an.FREQUENCY, 28.0, 29.0, points=5), views=(an.Rx(),)
    )
    _offer(monkeypatch, [a])
    w = _served(client, "rxf")
    assert w["runs"] is True and w["views"] == ["Rx"] and w["freqs"] is None
    run, _ = _analyze(monkeypatch, capsys, tmp_path, "rxf")
    ((label, (xs, want)),) = run["curves"].items()
    grid = chart_grid(w["range"])
    # The chart's grid is the CLI's (to the last bits of the step's sum).
    assert grid == pytest.approx([float(x) for x in xs], rel=1e-14, abs=0)
    got_f, got = _sweep(client, grid)
    assert got_f == grid
    assert _max_rel(got, want) <= REL
    # Adversarial: R and X move across the band (a flat curve would pass
    # any agreement).
    assert np.ptp(np.real(want)) > 1.0 and np.ptp(np.imag(want)) > 10.0


# ── explicit frequencies ──────────────────────────────────────────────────


def test_explicit_frequencies_are_served_and_swept_exactly(
    monkeypatch, client, capsys, tmp_path
):
    values = (28.6, 28.2, 28.45)
    a = an.band_swr(name="listed", sweep=an.Sweep(an.FREQUENCY, values=values))
    _offer(monkeypatch, [a])
    w = _served(client, "listed")
    assert w["runs"] is True
    assert w["freqs"] == list(values)
    run, out = _analyze(monkeypatch, capsys, tmp_path, "listed")
    assert "(the analysis's own values)" in out
    ((_, (xs, want)),) = run["curves"].items()
    assert [float(x) for x in xs] == list(values)
    # The chart sends them ascending (lib/analyses.ts listRange).
    sent = sorted(w["freqs"])
    got_f, got = _sweep(client, sent)
    assert got_f == sent
    by_f = dict(zip(got_f, got, strict=True))
    assert _max_rel([by_f[f] for f in values], want) <= REL


# ── the Table ─────────────────────────────────────────────────────────────


def _cli_blocks(out: str, ncols: int) -> list[tuple[str, list[list[str]]]]:
    """The CLI's printed table: per ``== ... ==`` block, its curve name (the
    header's text after the colon) and its rows (lines of ``ncols`` numeric
    fields)."""
    blocks: list[tuple[str, list[list[str]]]] = []
    for line in out.splitlines():
        if line.startswith("== ") and line.endswith(" =="):
            blocks.append((line[3:-3].split(": ", 1)[1], []))
            continue
        parts = line.split()
        if blocks and len(parts) == ncols:
            try:
                [float(p) for p in parts]
            except ValueError:
                continue
            blocks[-1][1].append(parts)
    return blocks


def _py_rows(case: dict, curve: dict) -> list[list[str]]:
    """The CLI's row formats (`_print_frequency_table`, `_print_sweep_table`,
    `sweep._print_convergence_table`) on one curve's numbers."""
    z = [complex(r, i) for r, i in zip(curve["re"], curve["im"], strict=True)]
    z0 = case["z0"]
    rows = []
    if case["kind"] == "frequency":
        for x, zz in zip(curve["xs"], z, strict=True):
            rho = abs((zz - z0) / (zz + z0))
            rows.append(
                [
                    f"{x:.6g}",
                    f"{zz.real:.3f}",
                    f"{zz.imag:+.3f}",
                    f"{(1 + rho) / (1 - rho):.3f}",
                ]
            )
    elif case["kind"] == "knob":
        rows = [
            [f"{x:.6g}", f"{zz.real:.3f}", f"{zz.imag:+.3f}"]
            for x, zz in zip(curve["xs"], z, strict=True)
        ]
    else:
        g_fin = (z[-1] - z0) / (z[-1] + z0)
        for x, n, zz in zip(curve["xs"], curve["n_seg"], z, strict=True):
            dg = abs((zz - z0) / (zz + z0) - g_fin)
            rows.append(
                [str(int(x)), str(n), f"{zz.real:.3f}", f"{zz.imag:+.3f}", f"{dg:.4f}"]
            )
    return rows


def _table_cases(monkeypatch, client, capsys, tmp_path) -> list[dict]:
    """Each case's served numbers and the CLI's printed rows."""
    cases = []
    freq = an.band_swr(
        name="table bands",
        sweep=an.Sweep(an.FREQUENCY, values=(28.2, 28.45, 28.7)),
        cross=an.Cross(designs=(INVVEE, APEX)),
        views=(an.Table(),),
    )
    fam = an.Analysis(
        "table family",
        an.Sweep("length_factor", 0.95, 1.0, points=3),
        cross=an.Cross(step=an.Sweep("angle_deg", values=(0, 30))),
        views=(an.Table(),),
    )
    ladder = an.convergence(
        name="table ladder",
        sweep=an.Sweep(an.DENSITY, values=(8, 12, 17)),
        cross=an.Cross(engines=("momwire:bspline",)),
        views=(an.Table(),),
    )
    _offer(monkeypatch, [freq, fam, ladder])

    w = _served(client, "table bands")
    _, out = _analyze(monkeypatch, capsys, tmp_path, "table bands")
    curves = []
    for d in w["designs"]:
        xs, z = _sweep(client, sorted(d["freqs"]), d["name"])
        curves.append(_curve(d["name"], xs, z))
    cases.append(
        _case("frequency, two designs", "frequency", "frequency", curves, out, 4)
    )

    w = _served(client, "table family")
    _, out = _analyze(monkeypatch, capsys, tmp_path, "table family")
    curves = []
    for value, label in zip(w["step"]["values"], w["step"]["labels"], strict=True):
        recs = _param_sweep(
            client, w["param"], w["values"], **{w["step"]["knob"]: value}
        )
        curves.append(
            _curve(
                label,
                [r["value"] for r in recs],
                [complex(r["z_re"], r["z_im"]) for r in recs],
            )
        )
    cases.append(_case("knob family", "knob", w["param"], curves, out, 3))

    w = _served(client, "table ladder")
    assert w["param"] == "n_per_wire"
    _, out = _analyze(monkeypatch, capsys, tmp_path, "table ladder", density=True)
    recs = _param_sweep(client, w["param"], w["values"])
    c = _curve(
        "momwire:bspline",
        [r["value"] for r in recs],
        [complex(r["z_re"], r["z_im"]) for r in recs],
    )
    c["n_seg"] = [r["n_seg"] for r in recs]
    cases.append(_case("density ladder", "density", w["param"], [c], out, 5))
    return cases


def _curve(label, xs, z) -> dict:
    return {
        "label": label,
        "xs": [float(x) for x in xs],
        "re": [zz.real for zz in z],
        "im": [zz.imag for zz in z],
    }


_COLUMNS = {
    "frequency": ("MHz", ["R (Ω)", "X (Ω)", "SWR"]),
    "knob": (None, ["R (Ω)", "X (Ω)"]),
    "density": ("nominal_N", ["N_ach", "R (Ω)", "X (Ω)", "|ΔΓ|"]),
}


def _case(name, kind, param, curves, out, ncols) -> dict:
    x_name, columns = _COLUMNS[kind]
    blocks = _cli_blocks(out, ncols)
    assert [b[0] for b in blocks] == [c["label"] for c in curves], (blocks, out)
    return {
        "name": name,
        "kind": kind,
        "param": param,
        "z0": 50.0,
        "curves": curves,
        "x_name": x_name or param,
        "columns": columns,
        "cli_rows": [rows for _, rows in blocks],
    }


def test_the_table_is_the_clis_printed_table(monkeypatch, client, capsys, tmp_path):
    cases = _table_cases(monkeypatch, client, capsys, tmp_path)
    for case in cases:
        for curve, rows in zip(case["curves"], case["cli_rows"], strict=True):
            # The served numbers, printed in the CLI's formats, ARE the rows
            # the CLI printed for the same analysis.
            assert _py_rows(case, curve) == rows, case["name"]
    if os.environ.get("AK_WRITE_TABLE_ORACLE") == "1":
        doc = {
            "about": (
                "The Table view's oracle (AK#1757 step 5 unit 5): served Z and "
                "the rows `antennaknobs analyze` printed for the same analysis. "
                "Do not edit by hand: regenerate."
            ),
            "generator": (
                "AK_WRITE_TABLE_ORACLE=1 PYTHONPATH=src python -m pytest "
                "tests/test_analyses_views_workbench_1757.py"
            ),
            "cases": cases,
        }
        ORACLE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    committed = json.loads(ORACLE.read_text())["cases"]
    assert [c["name"] for c in committed] == [c["name"] for c in cases]
    for old, new in zip(committed, cases, strict=True):
        assert {k: old[k] for k in ("kind", "param", "x_name", "columns")} == {
            k: new[k] for k in ("kind", "param", "x_name", "columns")
        }
        for oc, nc in zip(old["curves"], new["curves"], strict=True):
            assert oc["xs"] == nc["xs"] and oc.get("n_seg") == nc.get("n_seg")
            # The committed Z is today's to a tolerance that survives another
            # machine's last bits (never pin cross-machine bit equality).
            assert oc["re"] == pytest.approx(nc["re"], rel=1e-6)
            assert oc["im"] == pytest.approx(nc["im"], rel=1e-6, abs=1e-6)
        # And the committed rows are the committed numbers, printed.
        for curve, rows in zip(old["curves"], old["cli_rows"], strict=True):
            assert _py_rows(old, curve) == rows, old["name"]
