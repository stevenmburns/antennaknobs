"""AK#1854: the roster's `ground_applied` is what a solve reports.

Each roster entry serves `{requested method: what the impedance solve runs}`
so a ground-slot tab can say what a solver makes of a ground before anything
solves (Dan AC6LA, QRZ 1003328 #183), and since AK#1856 `{method: sentence}`
for the methods it refuses. Both are computed from the same rules the solve
applies; this file holds every served row equal to the `ground_model_applied`
an actual solve returns, or to its refusal, on every backend this machine can
run.
"""

from __future__ import annotations

import re

import pytest

from antennaknobs.web import server
from antennaknobs.web.adapter import backend_roster

DESIGN = {"geometry": "dipoles.invvee", "measurement_freq_mhz": 28.47}
METHODS = ("fast", "sommerfeld")


def _request(entry: dict, method: str) -> dict:
    req = {**DESIGN, "ground": True, "ground_model": method}
    if entry["kind"] == "momwire":
        return {**req, "solver": "momwire", "momwire_model": entry["name"]}
    return {**req, "solver": entry["kind"]}


def _served():
    have = {
        "have_pynec": server.pynec_backend.HAVE_PYNEC,
        "have_nec5": server.nec5_backend.have_nec5(),
        "have_nec2": server.nec2_backend.have_nec2(),
        "have_nec42": server.nec42_backend.have_nec42(),
    }
    return backend_roster(**have)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("name", [e["name"] for e in _served()])
def test_the_served_row_is_what_the_solve_reports(name, method):
    """A served method solves as served; a refused one (AK#1856) refuses
    with the served sentence."""
    entry = next(e for e in _served() if e["name"] == name)
    refusal = entry["ground_refusals"].get(method)
    if refusal is not None:
        with pytest.raises(NotImplementedError, match=re.escape(refusal)):
            server.solve(_request(entry, method))
        return
    solved = server.solve(_request(entry, method))
    assert entry["ground_applied"][method] == solved["ground_model_applied"]


def test_nec5_refuses_refl_coef_rather_than_serving_it_as_sommerfeld():
    """AK#1856 replaced the one difference #1854 served (NEC-5 ran refl-coef
    as Sommerfeld) with a refusal, served whether or not NEC-5 is installed.
    tests/test_nec5_refuses_refl_coef_1856.py holds the rest."""
    roster = backend_roster(have_pynec=False, have_nec5=True)
    nec5 = next(e for e in roster if e["name"] == "nec5")
    assert "fast" not in nec5["ground_applied"]
    assert "fast" in nec5["ground_refusals"]
