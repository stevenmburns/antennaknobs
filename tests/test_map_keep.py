"""Copy as analysis and keep as study for an edited map
(docs/design/sweep-framework-map.md, unit 4, decision 12).

An edited map axis is written back as ``Sweep(knob, lo, hi, points=)``, never
as a list of values, on the analysis's own knob; an unedited axis stays as
the analysis wrote it. The gate: ``eval(to_code(a)) == a`` for the kept map,
and the kept map's grid (`analysis_run.knob_xs`) is the one the chart solved
to within the chart's own 12-digit ladder.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs import analysis_run as ar
from antennaknobs import keep
from antennaknobs.cli import get_builder
from antennaknobs.web import server

INVVEE = "dipoles.invvee"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(server.app)


def _entry(client) -> dict:
    r = client.post("/analyses", json={"geometry": INVVEE})
    (e,) = [e for e in r.json()["analyses"] if e["name"] == "tuning map"]
    return e


def _body(e, **over) -> dict:
    return {
        "origin": "chart",
        "form": "analysis",
        "spec": e["spec"],
        "tab": {"geometry": INVVEE, "variant": "default"},
        **over,
    }


def test_an_edited_map_is_copied_with_ranges_and_round_trips(client):
    e = _entry(client)
    edit = {"y": {"lo": 10.0, "hi": 50.0, "points": 9, "spacing": "lin"}}
    r = client.post("/keep", json=_body(e, axes=edit))
    assert r.status_code == 200, r.text
    out = r.json()
    code = out["code"]
    a = eval(code, {"an": an})
    # The gate: the text IS the analysis.
    assert eval(an.to_code(a), {"an": an}) == a
    assert code == an.to_code(a) + "\n"
    sx, sy = a.sweeps
    # x as the analysis wrote it; y as the edit, a range with a count.
    assert sx == an.Sweep("length_factor", 0.9, 1.06, points=33)
    assert sy == an.Sweep("angle_deg", 10.0, 50.0, points=9)
    assert 'an.Sweep("angle_deg", 10.0, 50.0, points=9)' in code
    assert "values=" not in code
    assert a.views == (an.Map(),) and a.references == an.Ref(r=(50, 75), x=(0,))
    assert out["problems"] == []
    # The CLI's grid for the kept axis is the chart's ladder.
    ys = ar.knob_xs(sy, get_builder(INVVEE)(), "angle_deg")
    assert np.allclose(ys, [10 + 5 * k for k in range(9)], rtol=0, atol=1e-12)


def test_a_log_axis_and_both_axes_edited(client):
    e = _entry(client)
    edit = {
        "x": {"lo": 0.95, "hi": 1.0, "points": 5, "spacing": "log"},
        "y": {"lo": 60.0, "hi": 0.0, "points": 4, "spacing": "lin"},
    }
    a = eval(client.post("/keep", json=_body(e, axes=edit)).json()["code"], {"an": an})
    assert a.sweeps == (
        an.Sweep("length_factor", 0.95, 1.0, points=5, spacing="log"),
        an.Sweep("angle_deg", 0.0, 60.0, points=4),
    )


def test_an_edited_map_is_kept_as_a_study_too(client):
    e = _entry(client)
    edit = {"x": {"lo": 0.95, "hi": 1.0, "points": 11, "spacing": "lin"}}
    out = client.post("/keep", json=_body(e, form="study", axes=edit)).json()
    ns: dict = {}
    exec(out["code"], ns)
    (a,) = ns["build_studies"]()
    assert a.sweeps[0] == an.Sweep("length_factor", 0.95, 1.0, points=11)
    assert out["study_refusal"] is None


@pytest.mark.parametrize(
    ("axes", "words"),
    [
        ({"z": {}}, "axes is {x?, y?}"),
        ({}, "axes is {x?, y?}"),
        ({"x": [1, 2]}, "axes.x is {lo, hi, points, spacing}"),
        ({"x": {"lo": 1, "hi": "2", "points": 3}}, "axes.x.hi is a finite number"),
        (
            {"x": {"lo": 1, "hi": 2, "points": 1}},
            "axes.x.points is a count of at least 2",
        ),
        (
            {"x": {"lo": 1, "hi": 2, "points": 3, "spacing": "geo"}},
            "spacing is 'lin' or 'log'",
        ),
        ({"x": {"lo": 1, "hi": 1, "points": 3}}, "lo and hi are the same value"),
        (
            {"x": {"lo": -1, "hi": 2, "points": 3, "spacing": "log"}},
            "a log sweep needs lo",
        ),
    ],
)
def test_a_bad_axis_edit_is_refused_by_name(client, axes, words):
    r = client.post("/keep", json=_body(_entry(client), axes=axes))
    assert r.status_code == 422
    assert words in r.json()["detail"]


def test_only_a_map_has_axes_to_keep():
    a = an.Analysis("one", an.Sweep("length_factor", 0.9, 1.1, points=3))
    with pytest.raises(keep.KeepError, match="only a map has x and y axes"):
        keep._with_axes(a, {"x": {"lo": 1, "hi": 2, "points": 3}})
    # And a map still has no x values to keep (that is the one-sweep form).
    m = an.Analysis(
        "m",
        (an.Sweep("length_factor", 0.9, 1.1, points=3), an.Sweep("angle_deg", 0, 60)),
        views=(an.Map(),),
    )
    with pytest.raises(keep.KeepError, match="only a one-sweep chart has x values"):
        keep._with_values(m, [1.0])
