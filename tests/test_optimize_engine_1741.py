"""AK#1741 (AC6LA, QRZ 1003328 #157): Optimize -> Resonance on a NEC-5 slot
stopped ~2.4 ohm of jX short of resonance.

The cause was not NEC-5. `/optimize` evaluated every point on momwire's
B-spline whatever engine the slot was on, so a NEC-5 slot was handed
B-spline's resonance and then re-solved on NEC-5 there. The run now
optimises on the slot's own engine, as the drag tracker always did.
"""

from __future__ import annotations

import types

import pytest
from fastapi.testclient import TestClient

from antennaknobs.web import server

from conftest import needs_nec5

# A root the B-spline invvee does not share, so an answer at it can only have
# come from the stub engine.
_STUB_ROOT = 0.9731


def _opt_body(**extra) -> dict:
    return {
        "geometry": "dipoles.invvee",
        "n_per_wire": 7,
        "length_factor": 1.0,
        "optimize": {
            "free": [{"name": "length_factor", "min": 0.9, "max": 1.1}],
            "objective": "resonance",
        },
        **extra,
    }


@pytest.fixture
def stub_nec5(monkeypatch):
    """A stand-in NEC-5 backend whose X is linear in length_factor with its
    root at _STUB_ROOT, and which counts the solves it was asked for."""
    calls: list[float] = []

    def solve(req: dict) -> dict:
        lf = float(req["length_factor"])
        calls.append(lf)
        return {
            "z_in_re": 50.0,
            "z_in_im": 400.0 * (lf - _STUB_ROOT),
            "z0_ohms": 50.0,
            "solve_ms": 1.0,
            "_engine_runs": [("deck", "printout")],
        }

    mod = types.ModuleType("stub_nec5_backend")
    mod.solve = solve
    monkeypatch.setitem(server._EXTERNAL_BACKENDS, "nec5", (mod, lambda: True))
    monkeypatch.setitem(server._BACKEND_NAME, mod, "nec5")
    return calls


def test_a_nec5_slot_optimises_on_nec5(stub_nec5):
    body = TestClient(server.app).post("/optimize", json=_opt_body(solver="nec5"))
    out = body.json()
    assert "error" not in out, out
    # Every solve of the run went to the slot's engine, none to momwire.
    assert len(stub_nec5) == out["n_solves"] > 0
    assert out["params"]["length_factor"] == pytest.approx(_STUB_ROOT, abs=1e-4)
    assert abs(out["metrics_after"]["z_in_im"]) < 0.05
    assert out["solver"] == "nec5"


def test_the_streamed_run_names_its_engine_too(stub_nec5):
    import json

    text = (
        TestClient(server.app)
        .post(
            "/optimize",
            json=_opt_body(solver="nec5"),
            headers={"Accept": "text/event-stream"},
        )
        .text
    )
    frames = [f for f in text.split("\n\n") if f.startswith("event: result")]
    assert len(frames) == 1
    result = json.loads(frames[0].split("data: ", 1)[1])
    assert result["solver"] == "nec5"
    assert result["params"]["length_factor"] == pytest.approx(_STUB_ROOT, abs=1e-4)


def test_a_momwire_slot_still_optimises_on_momwire(stub_nec5):
    out = TestClient(server.app).post("/optimize", json=_opt_body()).json()
    assert out["solver"] == "momwire"
    assert stub_nec5 == []
    assert out["params"]["length_factor"] != pytest.approx(_STUB_ROOT, abs=1e-3)


def test_an_unavailable_engine_falls_back_and_says_so(monkeypatch):
    """The live-solve contract: a requested engine the machine cannot run is
    served by momwire, and the answer names momwire rather than the slot."""
    monkeypatch.delenv("NEC5_EXE", raising=False)
    out = TestClient(server.app).post("/optimize", json=_opt_body(solver="nec5")).json()
    assert "error" not in out, out
    assert out["solver"] == "momwire"


# AC6LA's three-wire inverted V (scratch/dan-1714-examples/invvee3.nec).
_INVVEE3 = """CM Three-wire inverted V for 20 m: a short feed wire at the apex, two drooping legs.
CE
SY gap=0.2
SY length_factor=0.96
SY angle=30
SY leg=length_factor*299.792458/14.2/4-gap/2
SY dy=leg*cos(angle), dz=leg*sin(angle)
GW 1 1  0 -gap/2 12  0 gap/2 12  0.001
GW 2 25 0 gap/2 12  0 gap/2+dy 12-dz  0.001
GW 3 25 0 -gap/2 12  0 -gap/2-dy 12-dz  0.001
GE 1
GN 2 0 0 0 13 0.005
EX 0 1 1 0 1 0
FR 0 1 0 0 14.2 0
EN
"""


@needs_nec5
def test_live_nec5_resonance_is_resonant_on_nec5(tmp_path, monkeypatch):
    """The report itself, end to end on the licensed binary: the optimised
    point, re-solved on NEC-5 the way the slot re-solves it, is at jX ~ 0.
    Before the fix it read -2.37 ohm (length_factor 0.98178, B-spline's root;
    NEC-5's own is ~0.9832). This also proves the knob reaches the NEC-5 deck:
    a stale deck could not move X to zero."""
    (tmp_path / "invvee3.nec").write_text(_INVVEE3)
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    req = {
        "geometry": "user.invvee3",
        "solver": "nec5",
        "design_freq_mhz": 14.2,
        "measurement_freq_mhz": 14.2,
        "wire_radius": 0.001,
        "ground": True,
        "ground_model": "sommerfeld",
        "sy_gap": 0.2,
        "sy_length_factor": 0.96,
        "sy_angle": 30.0,
    }
    with TestClient(server.app) as c:
        c.get("/examples")  # registers the folder's designs, as the app does
        out = c.post(
            "/optimize",
            json={
                **req,
                "optimize": {
                    "free": [{"name": "sy_length_factor", "min": 0.48, "max": 1.44}],
                    "objective": "resonance",
                    "max_evals": 40,
                },
            },
        ).json()
        assert "error" not in out, out
        lf = out["params"]["sy_length_factor"]
        again = server.solve({**req, "sy_length_factor": lf})
    assert again["solver"] == "nec5"
    assert abs(again["z_in_im"]) < 0.05, (lf, again["z_in_im"])
    assert lf == pytest.approx(0.9832, abs=5e-4)
    assert out["solver"] == "nec5"
