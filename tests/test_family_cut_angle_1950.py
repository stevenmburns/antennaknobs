"""AK#1950: a pattern family's cut angle, kept.

Dan AC6LA (QRZ 1005128 #61) sets the "Sweep a knob" chart's Elevation cut to
the bearing of the peak, or its Azimuth cut to the take-off angle, and then
copies the chart. The page sends the views it drew (``family.views``, in
/analyses' own shape), and the kept analysis must cut where the chart cut:
``an.patterns(views=...)`` where they differ from ``an.patterns()``'s own,
and nothing new where they do not (a family at its own angles keeps exactly
the text it kept before AK#1950). The page half is
``frontend/src/__tests__/familyCut.session.test.tsx``.

Mutation note (run by hand, 2026-10-07; reverted after): `analysis_from_family`
ignoring ``family.views`` (``views = None``) fails 6 of these 7: the round
trip (the code reads ``an.patterns(cross=...)`` with no ``views=``) and the
five refusals (each then keeps without complaint). The seventh, a family at
its own angles, passes either way, which is its point.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from antennaknobs import analyses as an
from antennaknobs.web import server

INVVEE = "dipoles.invvee"
FAMILY = {"knob": "base", "lo": 5, "hi": 15, "points": 3, "spacing": "lin"}
OWN = [
    {"view": "Elevation", "az": 0},
    {"view": "Azimuth", "el": 10},
    {"view": "PatternTable"},
]


@pytest.fixture()
def client():
    return TestClient(server.app)


def _keep(client, family: dict):
    body = {"origin": "chart", "form": "analysis", "spec": None, "family": family}
    return client.post("/keep", json={**body, "tab": {"geometry": INVVEE}})


def test_a_family_keeps_the_cut_angles_it_drew_and_round_trips(client):
    views = [
        {"view": "Elevation", "az": 35},
        {"view": "Azimuth", "el": 22},
        {"view": "PatternTable"},
    ]
    got = _keep(client, {**FAMILY, "views": views})
    assert got.status_code == 200, got.text
    want = an.patterns(
        cross=an.Cross(step=an.Sweep("base", 5, 15, points=3)),
        views=(an.Elevation(az=35), an.Azimuth(el=22), an.PatternTable()),
    )
    code = got.json()["code"]
    assert code == an.to_code(want) + "\n"
    assert "an.Elevation(az=35)" in code and "an.Azimuth(el=22)" in code
    assert eval(code, {"an": an}) == want


def test_a_family_at_its_own_angles_keeps_what_it_kept_before(client):
    with_views = _keep(client, {**FAMILY, "views": OWN})
    without = _keep(client, FAMILY)
    assert with_views.status_code == without.status_code == 200
    assert with_views.json()["code"] == without.json()["code"]
    assert "views=" not in with_views.json()["code"]


@pytest.mark.parametrize(
    ("views", "words"),
    [
        # an.Azimuth refuses the horizon: the page's box is 1-89 for this.
        ([{"view": "Azimuth", "el": 0}], "1..89"),
        ([{"view": "Elevation", "az": 12.5}], "whole number"),
        ([{"view": "Smith"}], "Elevation, Azimuth or PatternTable"),
        ([], "list of pattern views"),
        ("Elevation", "list of pattern views"),
    ],
)
def test_a_cut_the_keep_cannot_write_is_refused_by_name(client, views, words):
    r = _keep(client, {**FAMILY, "views": views})
    assert r.status_code == 422
    assert words in r.json()["detail"]
