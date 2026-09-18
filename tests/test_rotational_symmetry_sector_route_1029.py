"""The #1029 sector (block-circulant) solve route, exercised for real.

Companion to `test_rotational_symmetry_checkbox_1029.py`, which holds every
assertion that is true regardless of which momwire is on the path. This file
needs the ROUTE ITSELF — a real sector solve, a real geometry refusal — so it
SKIPS on the capability (never on a version number) when momwire has not
landed momwire#1029, the same shape `tests/*_1299.py` uses for a fixture a
lane does not install: a deselection prints nothing even under `-rs`, so the
skip is a real `pytest.mark.skipif` with a stated reason, checked at
collection time against `_offers_rotational_symmetry`, never a version
compare.

Design: `verticals.buried_radial_vertical` at its default 4 radials, over
soil A (the served default finite ground, eps_r 13 / sigma 0.005 — the same
`DEFAULT_GROUND` triple the module quotes as "ARRL average"). The correctness
claim is that turning the checkbox on moves NO number on a design the route
actually serves — bit-for-bit is too strong a bar here (the sector and dense
paths are different linear-algebra routes through the same physics, not the
same arithmetic in a different order), so the bar is the one the momwire#1029
PR itself measured: agreement to a relative 1e-9, an order of magnitude
looser than the ≤6e-14 that PR reports, leaving headroom for a different BLAS
build or thread count on whatever box runs this.
"""

from __future__ import annotations

import time
import tomllib
import warnings

import numpy as np
import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.cli import resolve_class
from antennaknobs.web import settings as ui_settings
from antennaknobs.web import user_designs
from antennaknobs.web.adapter import (
    _BACKENDS_BY_NAME,
    _build_builder,
    _make_momwire_engine,
    _offers_rotational_symmetry,
    backend_roster,
)

HAVE_SECTOR_ROUTE = _offers_rotational_symmetry(_BACKENDS_BY_NAME["bspline"])

pytestmark = pytest.mark.skipif(
    not HAVE_SECTOR_ROUTE,
    reason=(
        "momwire on this path does not declare the #1029 sector route "
        "(BSplineSolver.capabilities.axes['solve_strategy'] lacks 'sector') "
        "-- skip on the capability, not a version number"
    ),
)

DESIGN = "verticals.buried_radial_vertical"
RTOL = 1e-9


def _z(result) -> complex:
    return complex(np.asarray(result, dtype=complex).ravel()[0])


def _engine(design, *, rotational_symmetry, backend="bspline", **overrides):
    cls = resolve_class(design)
    req = {
        "geometry": design,
        "solver": "momwire",
        "momwire_model": backend,
        "n_per_wire": overrides.pop("n_per_wire", 9),
        "ground": True,
        "ground_model": "sommerfeld",
        "model_options": {"degree": 2, "rotational_symmetry": rotational_symmetry},
    }
    builder = _build_builder(cls, req)
    builder.freq = overrides.pop("freq", 7.1)
    for k, v in overrides.items():
        setattr(builder, k, v)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _make_momwire_engine(req, builder)


def test_the_roster_offers_it_on_bspline_only():
    rows = {r["name"]: r for r in backend_roster(have_pynec=True, have_nec5=True)}
    assert "rotational_symmetry" in rows["bspline"]["model_kwargs"]
    for name in (
        "hmatrix",
        "arrayblock",
        "sinusoidal",
        "sinusoidal-galerkin",
        "razor-2p",
        "pulse",
    ):
        assert "rotational_symmetry" not in rows[name]["model_kwargs"], name


def test_positive_passthrough_populates_the_sector_map():
    """Requirement 2: the flag reaches `BSplineSolver(rotational_symmetry=True)`
    through `_make_momwire_engine`, not around it."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        eng = _engine(DESIGN, rotational_symmetry=True)
        eng.impedance()
    sim = eng._solved_cache[1][0]
    assert sim.rotational_symmetry is True
    assert sim._rotational_map is not None


def test_dense_and_sector_agree_on_impedance():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        z_off = _z(_engine(DESIGN, rotational_symmetry=False).impedance())
        z_on = _z(_engine(DESIGN, rotational_symmetry=True).impedance())
    rel = abs(z_on - z_off) / abs(z_off)
    assert rel < RTOL, (z_off, z_on, rel)
    # Not vacuous: a screen actually has SOME reactance/resistance to move.
    assert abs(z_off) > 1.0


def test_dense_and_sector_agree_on_a_swept_impedance():
    # Agreement is an ALGEBRAIC identity between two routes through the same
    # matrix, not a convergence claim, so a coarser mesh than the single-
    # point test above still asks the real question at a fraction of the
    # dense fill's cost (issue #393's time-budget guardrail).
    freqs = np.array([6.9, 7.1, 7.3])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        zs_off = np.asarray(
            _engine(DESIGN, rotational_symmetry=False, n_per_wire=4).impedance_sweep(
                freqs
            )
        ).ravel()
        zs_on = np.asarray(
            _engine(DESIGN, rotational_symmetry=True, n_per_wire=4).impedance_sweep(
                freqs
            )
        ).ravel()
    assert zs_off.shape == zs_on.shape == (3,)
    worst = max(abs(a - b) / abs(a) for a, b in zip(zs_off, zs_on, strict=True))
    assert worst < RTOL, (zs_off, zs_on, worst)


@pytest.mark.parametrize(
    "design",
    [
        "dipoles.invvee",  # a plain dipole
        "verticals.vertical",  # a vertical over ground, but not buried
        "specialty.buried_dipole",  # buried, but not rotationally symmetric at all
    ],
)
def test_a_disqualified_design_refuses_with_the_checkboxs_own_words(design):
    """Requirement 4: momwire's own sentence, its tail swapped for the
    checkbox's name, served the way every other NotImplementedError refusal
    already is (`user_designs.format_solve_error`) — never a 500, never a
    raw traceback. Also: the refusal costs no fill, because it fires at
    CONSTRUCTION, before any matrix is touched.
    """
    t0 = time.monotonic()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            eng = _engine(design, rotational_symmetry=True, n_per_wire=9)
            eng.impedance()
        except NotImplementedError as exc:
            dt = time.monotonic() - t0
            reworded = user_designs.format_solve_error(exc)
        else:
            pytest.fail(f"{design} was expected to refuse rotational_symmetry=True")
    assert "Untick 'rotational symmetry (radial screens)'" in reworded
    assert "solve this design densely." in reworded
    # momwire's own kwarg name must not leak to the workbench's user.
    assert "rotational_symmetry=True" not in reworded
    assert not reworded.lstrip().startswith("Traceback")
    # No fill happened: well under a second, generously, on a laptop.
    assert dt < 1.0, dt


def test_the_settings_toml_round_trip_carries_the_flag(tmp_path):
    """Requirement 6: a slot with `rotational_symmetry = true` LOADS, and a
    sparse SAVE writes it only when it differs from the served default
    (False) — every other knob at its stock value writes nothing."""
    # have_pynec=True so `cat.stock_slots`' own seeds (slot C is pynec by
    # default) all resolve against `cat.backends` below.
    cat = ui_settings.catalog(have_pynec=True, have_nec5=False, have_nec2=False)
    assert "rotational_symmetry" in cat.backends["bspline"]
    path = tmp_path / "settings.toml"

    # --- load: a hand-written file with the flag set -----------------
    path.write_text(
        """
[slots.A]
backend = "bspline"
model = { rotational_symmetry = true }
"""
    )
    payload = ui_settings.load(cat, hosted=False, path=path)
    assert payload["problems"] == []
    seeds = {
        s["slot"]: s
        for s in ui_settings.overlay_slots(list(cat.stock_slots), payload["slots"])
    }
    assert seeds["A"]["model"]["rotational_symmetry"] is True

    # --- save: the page posts an otherwise-stock slot A with the box
    # ticked; the file should carry only that one key. Body shape mirrors
    # what BackendConfigModal/App.tsx actually post: every switch, the
    # served soil/terrain, and each slot with every knob its solver takes
    # at the served default (`_untouched`'s recipe in
    # test_settings_toml_1492.py), with ONLY `rotational_symmetry` moved off
    # its default.
    switches = {k: d for k, _, d in ui_settings.SWITCHES}
    ground = {
        **{k: ui_settings.GROUND_BUILTIN[k] for k in ("enabled", "type", "method")},
        "eps_r": cat.soil_default[0],
        "sigma": cat.soil_default[1],
        "terrain_preset": cat.terrain_default,
    }
    slots = {}
    for seed in cat.stock_slots:
        backend = seed["backend"]
        model = {k: cat.knob_defaults[k] for k in cat.backends[backend]}
        model.update(seed["model"])
        n = seed["n_per_wire"] or cat.n_per_wire_defaults[backend]
        slots[seed["slot"]] = {"backend": backend, "n_per_wire": n, "model": model}
    assert slots["A"]["backend"] == "bspline"
    slots["A"]["model"]["rotational_symmetry"] = True
    body = {"switches": switches, "ground": ground, "slots": slots}

    ui_settings.save(body, cat, path=path)
    written = tomllib.loads(path.read_text())
    assert written["slots"]["A"]["model"] == {"rotational_symmetry": True}
    assert written.get("switches", {}) == {}
    assert written.get("ground", {}) == {}
