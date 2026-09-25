"""momwire#1131: the above-ground radial screen, spelled in plain momwire.

Severns' 2009 N6LF vertical (`tests/test_surface_radials_865.py`): a 33.5 ft
mast over N radials of 33 ft at height `h`, at 7.2 MHz. `h = 2a` is the
SURFACE convention (the validity floor); anything larger is ELEVATED.
"""

from __future__ import annotations

import warnings

import numpy as np

from momwire.bspline import BSplineSolver

FT = 0.3048
F_HZ = 7.2e6
WAVELENGTH = 299792458.0 / F_HZ
MAST = 33.5 * FT
RADIAL = 33.0 * FT
A = 0.51e-3
SOIL = (30.0, 0.020)
H_SURFACE = 2.0 * A

GROUNDS = {
    "sommerfeld": dict(ground_z=0.0, ground_eps=SOIL, ground_model="sommerfeld"),
    "refl-coef": dict(ground_z=0.0, ground_eps=SOIL, ground_model="refl-coef"),
    "pec": dict(ground_z=0.0, ground_eps=None),
    "free": dict(ground_z=None, ground_eps=None),
}


def deck(n, *, ground="sommerfeld", h=H_SURFACE, n_rad=10, rot=False, **kw):
    ang = 2.0 * np.pi * np.arange(n) / n
    wires = [
        np.array([(RADIAL * np.cos(t), RADIAL * np.sin(t), h), (0.0, 0.0, h)])
        for t in ang
    ]
    npe = [[n_rad] for _ in ang]
    mast = len(wires)
    wires.append(np.array([(0.0, 0.0, z) for z in (MAST + h, 0.5 + h, 0.05 + h, h)]))
    npe.append([19, 2, 3])
    kwargs = dict(
        wires=wires,
        n_per_edge_per_wire=npe,
        junctions=[[(i, "end") for i in range(n)] + [(mast, "end")]],
        feeds=[(mast, MAST - 0.05, 1 + 0j)],
        wavelength=WAVELENGTH,
        wire_radius=A,
        degree=2,
        rotational_symmetry=rot,
        **GROUNDS[ground],
    )
    kwargs.update(kw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return BSplineSolver(**kwargs)
