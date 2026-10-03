"""The CLI's cell labels name a ground's MODEL, as the workbench's do.

AK#1867 made the workbench's chart cells word a listed ground the way its
ground tabs word a slot (``chartCells.groundSpecWords``): ``finite:13,0.005``
is "Sommerfeld · average", ``finite-fast:…`` "refl-coef · …". A spec names
the soil but not the model, and Sommerfeld against refl-coef is a ~3 dB split
on a low vertical, so the label is where that difference has to show. The
CLI's ``analyze`` kept printing the spec; these pin it to the same words in
its tables, legends and CSV headers.

What does NOT change is everything a spec is read back from: the analysis
data (``an.Cell.label``, which ``/analyses`` serves and the frontend's
``listedLabel`` matches by its spec part), and ``relative_to``, which names a
cell by its spec spelling (`analysis_run.Cell.spelled`).
"""

from __future__ import annotations

import numpy as np
import pytest

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs.cli import get_builder
from antennaknobs.sweep_csv import CsvOut

INVVEE = "dipoles.invvee"


# The frontend's own cases (metricViews1867.test.tsx), one for one.
@pytest.mark.parametrize(
    ("spec", "words"),
    [
        ("finite:13,0.005", "Sommerfeld · average"),
        ("finite", "Sommerfeld · average"),
        ("finite-fast:13,0.005", "refl-coef · average"),
        ("finite-fast:5,0.001", "refl-coef · very poor"),
        ("finite-fast:5,0.002", "refl-coef · εr 5, σ 0.002 S/m"),
        ("finite:13.5,0.00005", "Sommerfeld · εr 13.5, σ 0.00005 S/m"),
        ("mininec:13,0.005", "MININEC · average"),
        ("free", "free space"),
        ("pec", "PEC"),
        ("finite:x", "finite:x"),
        ("finite:", "finite:"),
        ("lossy", "lossy"),
    ],
)
def test_a_ground_spec_reads_as_the_ground_tabs_word_it(spec, words):
    assert ar.ground_words(spec) == words


def _grounds(*specs: str, **kw) -> an.Analysis:
    return an.band_swr(
        sweep=an.Sweep(an.FREQUENCY, 7.0, 7.3, points=3),
        cross=an.Cross(grounds=specs),
        **kw,
    )


def test_a_grounds_cross_labels_its_cells_by_model():
    got = ar.cells(_grounds("finite:13,0.005", "finite-fast:13,0.005", "free"), "x")
    assert [c.label for c in got] == [
        "Sommerfeld · average",
        "refl-coef · average",
        "free space",
    ]
    # The spec each was crossed with is still the cell's.
    assert [c.ground for c in got] == [
        "finite:13,0.005",
        "finite-fast:13,0.005",
        "free",
    ]
    assert [c.spelled for c in got] == [
        "finite:13,0.005",
        "finite-fast:13,0.005",
        "free",
    ]


def test_two_specs_worded_alike_keep_their_specs_as_labels():
    """``finite`` and ``finite:13,0.005`` are one soil and one model, and a
    label is what tells two curves apart (it keys the table and the CSV)."""
    got = ar.cells(_grounds("finite", "finite:13,0.005", "pec"), "x")
    assert [c.label for c in got] == ["finite", "finite:13,0.005", "PEC"]


def test_a_listed_cells_ground_is_worded_in_place():
    a = an.Analysis(
        "pins",
        an.Sweep(an.FREQUENCY, 7.0, 7.3, points=3),
        cross=an.Cross(
            cells=(
                an.Cell(engine="nec2", ground="finite:5,0.001"),
                an.Cell(an.State("tall", base=12.0), ground="pec", plane="feed"),
            )
        ),
    )
    got = ar.cells(a, "momwire")
    assert [c.label for c in got] == ["nec2, Sommerfeld · very poor", "tall, PEC, feed"]
    assert [c.spelled for c in got] == ["nec2, finite:5,0.001", "tall, pec, feed"]


def test_a_reference_still_names_a_cell_by_its_spec():
    a = _grounds(
        "finite:13,0.005",
        "finite-fast:13,0.005",
        views=(
            an.MetricPlot(
                an.ElevationWindow("DX", 2, 10), relative_to="finite:13,0.005"
            ),
        ),
    )
    plot = an.metric_plots(a)[0]
    refs = ar.references(a, plot, ar.cells(a, "x"))
    assert refs == {
        "Sommerfeld · average": "Sommerfeld · average",
        "refl-coef · average": "Sommerfeld · average",
    }


class _Flat:
    """An engine that answers without solving: the labels are the subject."""

    def __init__(self, z):
        self.z = z

    def impedance(self):
        return np.array([self.z])

    def impedance_sweep(self, xs):
        return np.full((len(xs), 1), self.z)


def test_analyze_prints_tables_legends_and_csv_headers_in_words(
    monkeypatch, capsys, tmp_path
):
    import antennaknobs.core as core

    legends = []

    def shot(plt, fn):
        for ax in plt.gcf().axes:
            leg = ax.get_legend()
            if leg is not None:
                legends.extend(t.get_text() for t in leg.get_texts())
        plt.close("all")

    monkeypatch.setattr(core, "save_or_show", shot)
    zs = {"finite:13,0.005": 40 + 5j, "finite-fast:5,0.001": 45 - 5j}
    csv_path = tmp_path / "a.csv"
    out = ar.run(
        _grounds(*zs, views=(an.Swr(), an.Table())),
        get_builder(INVVEE),
        factory_for=lambda engine, ground, density: lambda b: _Flat(zs[ground]),
        ground_label_for=lambda spec: str(spec),
        session_engine="momwire",
        fn=str(tmp_path / "a.png"),
        csv=CsvOut(str(csv_path)),
    )
    text = capsys.readouterr().out
    assert "== frequency sweep: Sommerfeld · average ==" in text
    assert "== frequency sweep: refl-coef · very poor ==" in text
    assert "Sommerfeld · average: 2:1 BW" in text
    assert "finite:13,0.005:" not in text and "sweep: finite" not in text
    assert {"Sommerfeld · average", "refl-coef · very poor"} <= set(legends)
    assert not any("finite" in t for t in legends)
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "Sommerfeld · average R_ohm" in header
    assert "refl-coef · very poor SWR" in header
    assert "finite" not in header
    # Its curves come back under the same labels.
    assert set(out["curves"]) == {"Sommerfeld · average", "refl-coef · very poor"}
