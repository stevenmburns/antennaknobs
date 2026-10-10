"""The exact ring kernel as an option (momwire#1408): "auto" by default on the
B-spline basis, CAPABILITY-GATED on the installed momwire.

The submodule pointer and the PyPI pin (momwire 0.75.0) predate
``exact_kernel="auto"``, so on them this file proves the option is inert:
nothing is offered, nothing is sent, and an explicit request is refused by
name. On a momwire that declares ``BSplineSolver.EXACT_KERNEL_CHOICES`` (dev
mode, or a release that carries it) the ``served`` tests run instead and prove
the default engages on a fat wire, stays out of a thin one bit for bit, and
reports what ran.
"""

import argparse
import importlib
import warnings
from types import MappingProxyType

import numpy as np
import pytest
from momwire import BSplineSolver, HMatrixSolver, SinusoidalSolver

from antennaknobs import AntennaBuilder
from antennaknobs.engines.momwire import (
    MomwireEngine,
    exact_kernel_served,
    normalize_exact_kernel,
)
from antennaknobs.network import Driven, Network, PortOnWire, Wire

cli = importlib.import_module("antennaknobs.cli")

SERVED = exact_kernel_served(BSplineSolver)
served = pytest.mark.skipif(
    not SERVED, reason="the installed momwire has no exact_kernel='auto'"
)
unserved = pytest.mark.skipif(
    SERVED, reason="the installed momwire serves exact_kernel='auto'"
)

FREQ = 28.47
ARM = 0.25 * 299.792458 / FREQ


class _Dipole(AntennaBuilder):
    default_params = MappingProxyType({"freq": FREQ, "design_freq": FREQ, "n_seg": 21})

    def build_wires(self):
        return [Wire((0.0, -ARM, 10.0), (0.0, ARM, 10.0), n_seg=self.n_seg, name="w")]

    def build_network(self):
        return Network(
            ports={"feed": PortOnWire("feed", wire="w", at=None)},
            sources=[Driven(port="feed")],
        )


FAT = 0.1  # h = 0.25 m: 2.5 radii per segment
THIN = 0.001  # 250 radii


def _engine(radius, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return MomwireEngine(
            _Dipole(dict(_Dipole.default_params)), wire_radius=radius, **kw
        )


def _z(eng):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.asarray(eng.impedance())


def _kwargs(eng):
    return eng._kernel_solver_kwargs()


# --------------------------------------------------------------------------
# both modes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "want"),
    [
        (None, None),
        ("auto", "auto"),
        ("on", True),
        ("ON", True),
        ("off", False),
        (True, True),
        (False, False),
    ],
)
def test_spellings(given, want):
    assert (
        normalize_exact_kernel(given) is want or normalize_exact_kernel(given) == want
    )


def test_a_bad_spelling_refuses():
    with pytest.raises(ValueError, match="auto, on, off"):
        normalize_exact_kernel("exact")


@pytest.mark.parametrize("asked", ["on", "auto"])
def test_another_basis_refuses_by_name(asked):
    with pytest.raises(NotImplementedError, match="1408"):
        _engine(THIN, solver=SinusoidalSolver, exact_kernel=asked)
    with pytest.raises(NotImplementedError, match="1408"):
        _engine(THIN, solver=HMatrixSolver, exact_kernel=asked)


def test_off_is_satisfied_everywhere():
    for solver in (SinusoidalSolver, HMatrixSolver, BSplineSolver):
        eng = _engine(THIN, solver=solver, exact_kernel="off")
        assert "exact_kernel" not in _kwargs(eng)


def test_another_basis_takes_nothing_by_default():
    eng = _engine(FAT, solver=SinusoidalSolver)
    assert "exact_kernel" not in _kwargs(eng)
    assert eng.exact_kernel_ran is None


@pytest.mark.parametrize("asked", ["on", "auto"])
def test_cli_refuses_it_on_other_engines(asked):
    # PyNEC: the one other engine whose spec parses without a binary.
    pytest.importorskip("PyNEC")
    with pytest.raises(argparse.ArgumentTypeError, match="1408"):
        cli.make_engine_factory("pynec", "free", exact_kernel=asked)


def test_cli_off_on_other_engines_is_fine():
    pytest.importorskip("PyNEC")
    cli.make_engine_factory("pynec", "free", exact_kernel="off")


def test_the_option_spec_is_served_with_auto_as_its_default():
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.adapter import model_option_specs

    spec = model_option_specs()["exact_kernel"]
    assert spec["default"] == "auto"
    assert tuple(spec["values"]) == ("auto", "on", "off")


def test_the_roster_offers_it_on_bspline_only_and_only_when_served():
    from antennaknobs.web import server  # noqa: F401
    from antennaknobs.web.adapter import backend_roster

    offered = {
        b["name"]
        for b in backend_roster(have_pynec=True, have_nec5=True, have_nec2=True)
        if "exact_kernel" in b["model_kwargs"]
    }
    assert offered == ({"bspline"} if SERVED else set())


# --------------------------------------------------------------------------
# a momwire without the option: inert
# --------------------------------------------------------------------------


@unserved
def test_unserved_default_passes_nothing():
    eng = _engine(FAT)
    assert "exact_kernel" not in _kwargs(eng)
    _z(eng)
    assert eng.exact_kernel_ran is None
    assert eng.kernel_ran == "reduced"


@unserved
@pytest.mark.parametrize("asked", ["on", "auto"])
def test_unserved_request_names_the_missing_release(asked):
    with pytest.raises(NotImplementedError, match="momwire release"):
        _engine(FAT, exact_kernel=asked)


# --------------------------------------------------------------------------
# a momwire with the option
# --------------------------------------------------------------------------


@served
def test_default_is_auto_and_engages_on_a_fat_wire():
    eng = _engine(FAT)
    assert _kwargs(eng)["exact_kernel"] == "auto"
    z = _z(eng)
    assert eng.exact_kernel_ran is True
    assert eng.kernel_ran == "exact"
    on = _engine(FAT, exact_kernel="on")
    assert np.array_equal(z, _z(on))
    off = _engine(FAT, exact_kernel="off")
    z_off = _z(off)
    assert off.exact_kernel_ran is None
    assert off.kernel_ran == "reduced"
    assert not np.array_equal(z, z_off)


@served
def test_auto_stays_out_of_a_thin_wire_bit_for_bit():
    eng = _engine(THIN)
    z = _z(eng)
    assert eng.exact_kernel_ran is False
    assert eng.kernel_ran == "reduced"
    assert np.array_equal(z, _z(_engine(THIN, exact_kernel="off")))


@served
def test_auto_reports_extended_when_ek_runs_and_exact_does_not():
    eng = _engine(THIN, extended_kernel=True)
    _z(eng)
    assert eng.kernel_ran == "extended"


@served
def test_solver_kwargs_spelling_is_folded():
    eng = _engine(FAT, solver_kwargs={"exact_kernel": "off"})
    assert "exact_kernel" not in _kwargs(eng)
    assert "exact_kernel" not in eng._solver_kwargs


@served
def test_cli_factory_carries_it():
    f = cli.make_engine_factory("momwire", "free", exact_kernel="on")
    assert f.keywords["exact_kernel"] is True


@served
def test_the_web_adapter_passes_the_choice_through():
    from antennaknobs.web import server  # noqa: F401
    from antennaknobs.web import adapter

    eng = adapter._make_momwire_engine(
        {"momwire_model": "bspline", "model_options": {"exact_kernel": "off"}},
        _Dipole(dict(_Dipole.default_params)),
    )
    assert "exact_kernel" not in eng._kernel_solver_kwargs()
