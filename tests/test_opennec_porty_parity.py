"""The porty OpenNECEngine against the pybind OpenNECEngine it replaced.

`tests/fixtures/opennec_porty_reference.json` holds what the engine at
dbabbe4f — PyNECEngine's cards on pyopennec's PyNEC-shaped ``nec_context`` —
answered over `scratch/porty-parity/cases.py`: test_opennec_parity.py's set,
network designs on every reducer feature (a lossy line, virtual ports,
self-tuning two-ports, distributed ports, a 10-port LPDA) and native
multi-feed arrays over each ground. ``record_reference.py`` beside it
regenerates the file from that commit; the pybind module it needs is due to
leave pyopennec, which is why the answers are recorded rather than re-run.

Same OpenNEC kernel both sides, so the bars are tight:

    impedance   |dZ| / |Z|          <= 1e-6  (each port, each sweep point)
    currents    max |dI| / max |I|  <= 1e-6
    pattern     |dG|                <= 1e-3 dB over the whole grid, and on
                                       max / min gain

Measured 2026-11-14 on the laptop build (OpenNEC 2.3.5, OpenBLAS): worst
4.8e-11 on Z, 4.3e-12 on currents, 1.8e-10 dB on gain. The card route is
bit-identical (one NEC solve either way); the multiport route differs only
by the order of the same arithmetic (one multi-RHS solve and a matrix
product, against one NEC run per port).

The MININEC-type ground is held on Z and currents only: its pattern needs a
cliff-mode RP that porty does not serve, and the engine refuses it.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from antennaknobs.engines import opennec as opennec_mod
from antennaknobs.engines.opennec import OpenNECEngine

pytestmark = pytest.mark.skipif(
    opennec_mod.porty is None, reason="pyopennec (porty) not installed"
)

REF = json.loads(
    (Path(__file__).parent / "fixtures" / "opennec_porty_reference.json").read_text()
)
PATTERN = REF["meta"]["pattern"]
Z_BAR = 1e-6
I_BAR = 1e-6
G_BAR_DB = 1e-3


def _c(rows):
    a = np.asarray(rows, float)
    return a[..., 0] + 1j * a[..., 1]


def _ground(g):
    return tuple(g) if isinstance(g, list) else g


def _engine(r):
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY

    builder = REGISTRY.get(r["design"]).builder_cls()
    return OpenNECEngine(builder, ground=_ground(r["ground"]), **r["kwargs"])


def test_the_reference_covers_both_routes_and_every_ground():
    assert {r["route"] for r in REF["cases"]} == {"native", "reducer"}
    grounds = {
        g if isinstance(g, str) else g[0] for g in (r["ground"] for r in REF["cases"])
    }
    assert grounds == {"free", "pec", "finite", "finite-fast", "mininec"}
    assert sum(r["route"] == "reducer" for r in REF["cases"]) >= 10


@pytest.mark.parametrize("r", REF["cases"], ids=[r["id"] for r in REF["cases"]])
def test_porty_matches_the_pybind_engine(r):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _engine(r)
        assert ("reducer" if eng._use_reducer else "native") == r["route"]
        z = np.asarray(eng.impedance(), complex).ravel()
        cur = eng.current_distribution()
        z0 = _c(r["z"])
        assert z.shape == z0.shape
        assert np.max(np.abs(z - z0) / np.abs(z0)) <= Z_BAR
        i = np.concatenate([np.asarray(w.knot_currents) for w in cur])
        i0 = _c(r["currents"])
        assert np.max(np.abs(i - i0)) / np.max(np.abs(i0)) <= I_BAR
        assert eng._excited_efficiency == pytest.approx(r["efficiency"], abs=1e-9)
        assert eng._excited_p_in == pytest.approx(r["p_in"], rel=1e-9)
        assert [k for k, _w in eng._excited_power_budget] == [
            k for k, _w in r["budget"]
        ]
        if "gain" in r:
            ff = eng.far_field(**PATTERN)
            g = np.asarray(ff.rings, float)
            assert np.max(np.abs(g - np.asarray(r["gain"], float))) <= G_BAR_DB
            assert abs(ff.max_gain - r["max_gain"]) <= G_BAR_DB
            assert abs(ff.min_gain - r["min_gain"]) <= G_BAR_DB
        else:
            with pytest.raises(NotImplementedError, match="MININEC"):
                eng.far_field(**PATTERN)
        # Every reading above from one porty solve at the builder's frequency
        # (a self-tuning tuner adds its tune frequency), none solved twice.
        solved = [f for call in eng.solve_log for f in call]
        assert len(solved) == len(set(solved)) <= 2
        assert opennec_mod._freq_key(eng.builder.freq) in solved

        sweeper = _engine(r)
        sweep = np.asarray(sweeper.impedance_sweep(np.asarray(r["sweep_freqs"])))
        s0 = _c(r["sweep"]).reshape(sweep.shape)
        assert np.max(np.abs(sweep - s0) / np.abs(s0)) <= Z_BAR
        # The whole sweep in one solve() call.
        keys = tuple(opennec_mod._freq_key(f) for f in r["sweep_freqs"])
        assert keys in sweeper.solve_log
