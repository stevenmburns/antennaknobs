"""momwire#545 U4: re-measure #510 with the point evaluator in hand.

Probe A — grid-vs-direct: at 0033's own (R1, theta) query population (deep
grazing, theta ~ 1e-3 rad), how far is `SommerfeldGrid.eval` from
`iv_surfaces_direct`?  The fill's answers ride the grid; if the interpolation
is off at grazing, the divergence is a TABULATION statement, not a
formulation one.

Probe B — the evaluator's height profile: E_z at a point over the ground,
height laddered through the radial height (1.778 cm = 1.09e-4 lambda), from
0033's solved currents.  Non-smooth structure at the radial height would
localize the strain to the near-interface surfaces.
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/smburns/antennas/antennaknobs/momwire/tests")

from momwire import _field_point, _ground_spec, _sommerfeld
from momwire.deck._nec5 import parse_nec5
from momwire.eznec._serve import (
    SPEED_OF_LIGHT_MHZ_M,
    _NEAR_FIELD_SUBDIV,
    _cards,
    _medium,
    _port_state,
    _solver_for,
    _transform,
    build_mesh,
    structure_of,
)
from momwire.portal._portal import _element_fields, _image_moments

DECKS = Path("/home/smburns/antennas/antennaknobs/momwire/tests/fixtures/eznec/decks")


def solved(cid):
    deck = parse_nec5(next(DECKS.glob(f"{cid}_*.nec")).read_text())
    structure = structure_of(deck)
    mesh = build_mesh(deck, structure)
    for source in deck.sources:
        for site in mesh.sites:
            if site.at == source.at:
                site.driven = True
    wavelength = SPEED_OF_LIGHT_MHZ_M / float(deck.frequency_mhz)
    medium = _medium(deck.ground, wavelength)
    cards = _cards(deck, structure, mesh)
    solver = _solver_for(deck, mesh, wavelength, medium)
    solution = solver.compute_port_solution()
    state = _port_state(deck, mesh, cards, solution.y, wavelength)
    coeffs = solution.coeffs @ (_transform(mesh) @ state.v_gap)
    return deck, mesh, solver, coeffs, wavelength, medium


def probe_a(cid="0033"):
    deck, mesh, solver, coeffs, wavelength, medium = solved(cid)
    lam = wavelength
    k = solver.k
    eps_t = _ground_spec.ground_config(solver, solver.omega).eps_tilde
    mid, moment, nodes, delta = solver.element_currents(coeffs, subdiv=1)

    ex = np.concatenate([mid, mid])
    r1_max = _sommerfeld.max_image_distance(ex, ex, 0.0)
    grid = _sommerfeld.get_grid(eps_t, k, r1_max, solver.omega)

    dx = mid[:, 0][:, None] - mid[None, :, 0]
    dy = mid[:, 1][:, None] - mid[None, :, 1]
    rho = np.hypot(dx, dy).ravel()
    hh = (mid[:, 2][:, None] + mid[None, :, 2]).ravel()
    r1 = np.sqrt(rho * rho + hh * hh)
    th = np.arctan2(hh, rho)
    keep = r1 > 0
    r1, th = r1[keep], th[keep]
    print(
        f"{cid}: {r1.size} pair queries; R1 in [{r1.min():.4g}, {r1.max():.4g}] m "
        f"({r1.min() / lam:.2e}..{r1.max() / lam:.3f} lambda); "
        f"theta in [{np.degrees(th.min()):.4g}, {np.degrees(th.max()):.4g}] deg"
    )

    # subsample for the direct evaluation (expensive), covering the range and
    # emphasizing the grazing tail
    order = np.argsort(th)
    idx = np.unique(
        np.concatenate(
            [
                order[:120],  # most-grazing 120
                order[np.linspace(0, order.size - 1, 180, dtype=int)],
            ]
        )
    )
    r1s, ths = r1[idx], th[idx]
    direct = _sommerfeld.iv_surfaces_direct(eps_t, k, r1s, ths, omega=solver.omega)
    interp = grid.eval(r1s, ths)

    for key in ("IrhoV", "IzV", "IrhoH", "IphiH"):
        d = np.asarray(direct[key])
        g = np.asarray(interp[key])
        scale = np.abs(d).max()
        err = np.abs(g - d) / scale
        j = int(np.argmax(err))
        print(
            f"  {key}: max |grid-direct| = {err.max():.3e} of surface scale "
            f"(median {np.median(err):.1e}) at R1={r1s[j]:.4g} m, "
            f"theta={np.degrees(ths[j]):.4g} deg"
        )


def probe_b(cid="0033"):
    deck, mesh, solver, coeffs, wavelength, medium = solved(cid)
    k = solver.k
    eps_t = _ground_spec.ground_config(solver, solver.omega).eps_tilde
    c2 = (eps_t - 1.0) / (eps_t + 1.0)
    radius = min(p.radius for p in mesh.pieces)
    mid, moment, nodes, delta = solver.element_currents(
        coeffs, subdiv=_NEAR_FIELD_SUBDIV
    )
    heights = np.array([0.005, 0.01, 0.01778, 0.03, 0.06, 0.125, 0.25, 0.5, 1.0, 2.0])
    points = np.column_stack(
        [np.full_like(heights, 10.0), np.zeros_like(heights), heights]
    )
    direct = _element_fields(points, (mid, moment, nodes, delta), k, radius, False)
    mid_i, mom_i = _image_moments(mid, moment, 0.0)
    nodes_i = nodes.copy()
    nodes_i[:, 2] = -nodes[:, 2]
    img = _element_fields(points, (mid_i, mom_i, nodes_i, -delta), k, radius, False)
    rem = _field_point.reflected_field_at(
        points, mid, moment, eps_t, 0.0, k, solver.omega
    )
    total = direct + (c2 * img + rem)
    print(f"{cid}: E at (10, 0, z) per component, radial height 0.01778 m marked")
    for h, row in zip(heights, total):
        mark = "  <-- radial height" if abs(h - 0.01778) < 1e-9 else ""
        print(
            f"  z={h:7.4f} m  Ex={abs(row[0]):9.4f}  Ez={abs(row[2]):9.4f} "
            f"V/m  argEz={math.degrees(math.atan2(row[2].imag, row[2].real)):8.2f}{mark}"
        )


if __name__ == "__main__":
    probe_a("0033")
    probe_b("0033")
