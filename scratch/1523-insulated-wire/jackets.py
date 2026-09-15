"""AK#1523: the jackets on the ladder, shared by tm0_mode.py and study_1523.py.

The two catalog rows are checked against `antennaknobs.wire_catalog.WIRES` by
study_1523.py; they are written out here so the mode solver needs no
antennaknobs import.
"""

FREQ_MHZ = 14.2
A22 = 0.321e-3
A18 = 0.512e-3

# name -> (conductor radius a [m], jacket outer radius b [m], eps_r)
JACKETS = {
    **{
        f"ba{ratio}-er{eps}": (A22, ratio * A22, eps)
        for ratio in (1.5, 2, 3)
        for eps in (2.3, 3.5, 5)
    },
    "22-awg-pvc": (A22, 0.80e-3, 3.5),
    "18-awg-pvc": (A18, 1.05e-3, 3.5),
}

# name -> conductor radius [m]
BARE = {"bare-22": A22, "bare-18": A18}


def bare_of(name):
    """The bare conductor a jacket sits on."""
    a = JACKETS[name][0]
    return next(k for k, v in BARE.items() if v == a)
