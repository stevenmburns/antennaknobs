"""Solving station-rail chains against an antenna solved once.

The antenna is the expensive part and the station never changes it: only the
circuit differs between rail A and rail B, between one gallery card and the
next, and between one junction and the next. So the antenna's multiport
short-circuit admittance Y is solved once per wavelength (`SolvedAntenna`),
and every chain, card and junction probe is a circuit reduction over that Y,
through the same reducer the engine itself uses (`auto_match.make_reducer`,
which also tunes a self-tuning tuner from that Y).

A JUNCTION PROBE is the impedance looking towards the antenna at one node of
the chain: the chain driven at that node with its rig side taken off, the
shunt items at the node staying (`station_rail.to_network`'s ``drive``),
which is what a VNA clipped on there would read. The last row, "antenna", is
the antenna alone at its feed, with no chain and no shunt there. This is the
design note's "one piece of solve work", done above the reducer rather than
inside it: the reducer stays the engine's, byte for byte (it is held equal to
momwire's own by tests/test_mw_networks_ab_2219.py).
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

from . import station_rail as sr
from .auto_match import (
    AutoMatchReducer,
    design_freq_mhz,
    make_reducer,
    tuner_advisories,
    tuner_rows,
)
from .network import PortVirtual


def swr(z: complex, z_ref: float) -> float | None:
    """SWR of ``z`` against a real reference ``z_ref``; None for a reflection
    of 1 or more (an open, a short, a reactance, a negative resistance)."""
    if not math.isfinite(abs(z)):
        return None
    gamma = abs((z - z_ref) / (z + z_ref))
    return (1 + gamma) / (1 - gamma) if gamma < 1 else None


class SolvedAntenna:
    """One momwire engine's antenna, solved once per wavelength.

    ``eng`` is a `MomwireEngine` built on the antenna alone
    (`station_rail.antenna_network`), so its real ports, their meshing and
    their order in Y are the antenna's own; every chain has the same real
    ports and differs only in virtual nodes and branches. ``solves`` counts
    the antenna solves (calls of the engine's Y), which is how a caller shows
    that switching rails or cards never re-solved it.
    """

    def __init__(self, eng):
        self.eng = eng
        self.solves = 0
        self._y: dict[float, np.ndarray] = {}
        self.wavelength = float(eng._wavelength_for(eng.builder.freq))
        red = eng._reducer
        p2i = red._port_to_idx if isinstance(red, AutoMatchReducer) else red.port_to_idx
        self._real = {
            n: p2i[n]
            for n, p in eng._network.ports.items()
            if not isinstance(p, PortVirtual)
        }
        self.y = self.y_at(self.wavelength)

    def y_at(self, wavelength: float) -> np.ndarray:
        wl = float(wavelength)
        if wl not in self._y:
            self._y[wl] = self.eng._compute_y_matrix(wl)
            self.solves += 1
        return self._y[wl]

    def reducer(self, net):
        """The engine's own kind of reducer over ``net``: its real ports at
        the antenna's indices in Y, its virtual nodes after them."""
        eng = self.eng
        meshed = eng._network_as_meshed(net)
        idx = dict(self._real)
        nxt = int(self.y.shape[0])
        for name, p in meshed.ports.items():
            if isinstance(p, PortVirtual):
                idx[name] = nxt
                nxt += 1
        return make_reducer(
            meshed,
            idx,
            nxt,
            y_at=self.y_at,
            design_freq_mhz=design_freq_mhz(eng.builder),
            wavelength_for=eng._wavelength_for,
            c_light_mhz_m=eng._reducer_c_light(),
        )

    def impedance(self, net) -> complex:
        red = self.reducer(net)
        return complex(np.atleast_1d(red.driven_impedance(self.y, self.wavelength))[0])


def _zrow(z: complex, z_ref: float) -> dict:
    finite = math.isfinite(z.real) and math.isfinite(z.imag)
    return {
        "z_re": z.real if finite else None,
        "z_im": z.imag if finite else None,
        "swr": swr(z, z_ref) if finite else None,
    }


def probes(sa: SolvedAntenna, chain: dict, att: sr.Attachment, z_ref: float):
    """Z and SWR (against ``z_ref``) at every node rig → feed, then the bare
    antenna. Node 0's network is the whole chain, so its row is the chain's
    own impedance at the rig."""
    nodes, _ = sr.layout(chain, att)
    rows = []
    for k, node in enumerate(nodes):
        z = sa.impedance(sr.to_network(chain, att, drive=k))
        rows.append({"node": node, "at": "rig" if k == 0 else node, **_zrow(z, z_ref)})
    z_ant = sa.impedance(sr.antenna_network(att))
    rows.append({"node": None, "at": "antenna", **_zrow(z_ant, z_ref)})
    return rows


def solve_chain(
    sa: SolvedAntenna,
    chain: dict,
    att: sr.Attachment,
    *,
    z_ref: float = 50.0,
    with_probes: bool = True,
) -> dict:
    """One chain on the solved antenna: the impedance and SWR at the rig, the
    station's loss and the share of the rig's power that reaches the antenna,
    the per-branch budget, a self-tuning tuner's readout, and (with
    ``with_probes``) the junction probes.

    The station's loss counts the chain's own branches only. Branches the
    antenna carries itself (a trap's resistance, form "cut") burn the
    antenna's power, not the station's, and are left out of it, as the
    antenna's conductor loss is."""
    net = sr.to_network(chain, att)
    red = sa.reducer(net)
    z = complex(np.atleast_1d(red.driven_impedance(sa.y, sa.wavelength))[0])
    _v, _eff, p_in, rows = red.excited_state(sa.y, sa.wavelength)
    p_in = float(p_in)
    n_ant = len(att.antenna.branches) if att.form == "cut" else 0
    budget = []
    for row in rows:
        label, watts = row[0], max(0.0, float(row[1]))
        key = getattr(row, "key", None)
        if key is not None and key[1] is not None and key[1] < n_ant:
            continue
        budget.append({"key": label, "watts": watts})
    burned = sum(r["watts"] for r in budget)
    frac = (p_in - burned) / p_in if p_in > 0 else 0.0
    shim = SimpleNamespace(_reducer=red)
    out = {
        **_zrow(z, z_ref),
        "z_ref": z_ref,
        "p_in_w": p_in,
        "loss_db": -10 * math.log10(frac) if frac > 0 else None,
        "antenna_share": frac,
        "budget": budget,
        "tuner": [
            {"label": r["label"], "value": r["value"], "unit": r["unit"]}
            for r in tuner_rows(shim)
        ],
        "tuner_advisories": [
            a.get("text") or a.get("message") or str(a) for a in tuner_advisories(shim)
        ],
        "network": red.tuned_network() if isinstance(red, AutoMatchReducer) else net,
    }
    if with_probes:
        out["probes"] = probes(sa, chain, att, z_ref)
    return out
