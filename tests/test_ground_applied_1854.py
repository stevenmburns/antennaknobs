"""AK#1854: the roster's `ground_applied` is what a solve reports.

Each roster entry serves `{requested method: what the impedance solve runs}`
so a ground-slot tab can say "refl-coef -> Sommerfeld" under NEC-5 before
anything solves (Dan AC6LA, QRZ 1003328 #183). It is computed from the same
rules the solve applies; this file holds every served row equal to the
`ground_model_applied` an actual solve returns, on every backend this machine
can run.
"""

from __future__ import annotations

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
    entry = next(e for e in _served() if e["name"] == name)
    solved = server.solve(_request(entry, method))
    assert entry["ground_applied"][method] == solved["ground_model_applied"]


def test_nec5_serves_refl_coef_as_sommerfeld():
    """The one difference today, served whether or not NEC-5 is installed."""
    roster = backend_roster(have_pynec=False, have_nec5=True)
    nec5 = next(e for e in roster if e["name"] == "nec5")
    assert nec5["ground_applied"]["fast"] == "sommerfeld"
