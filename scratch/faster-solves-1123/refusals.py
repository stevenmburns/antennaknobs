"""What the rotational-symmetry box says on catalog designs it refuses,
through the app's engine path; the sentence as the Fill view shows it
(`reword_rotational_symmetry_refusal`)."""

import warnings

import antennaknobs.web.server  # noqa: F401  (resolves the adapter import cycle)
from antennaknobs.cli import resolve_class
from antennaknobs.web.adapter import (
    _build_builder,
    _make_momwire_engine,
    reword_rotational_symmetry_refusal,
)

CASES = [
    ("verticals.vertical", {"n_radials": 1}, False),
    ("verticals.vertical", {"n_radials": 4}, True),
    ("verticals.inverted_l", {}, True),
    ("verticals.buried_radial_vertical", {}, True),
    ("verticals.elevated_buried_counterpoise", {}, True),
    ("verticals.elevated_buried_counterpoise", {"n_elevated": 3}, True),
    ("verticals.raised_vertical", {}, True),
    ("broadband.discone", {}, False),
    ("dipoles.dipole_turnstile", {}, False),
]

for design, params, ground in CASES:
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": "bs2",
        "model_options": {"rotational_symmetry": True},
        "n_per_wire": 21,
        "ground": ground,
        "ground_model": "sommerfeld",
        **params,
    }
    try:
        b = _build_builder(resolve_class(design), req)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eng = _make_momwire_engine(req, b)
            eng.impedance()
        rep = eng.fill_report() or {}
        sec = rep.get("sector") or {}
        print(
            f"{design} {params} ground={ground}: route={rep.get('route')} "
            f"sectors={sec.get('n_sectors')} axial={sec.get('axial')}"
        )
    except Exception as exc:  # noqa: BLE001 — a probe: print whatever refuses
        print(
            f"{design} {params} ground={ground}: {type(exc).__name__}: "
            f"{reword_rotational_symmetry_refusal(str(exc))}"
        )
