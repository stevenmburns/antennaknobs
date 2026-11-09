"""The momwire names antennaknobs uses that momwire keeps private.

The only module in antennaknobs that imports a private momwire name
(tests/test_momwire_private_imports.py holds that). Each import is made
on use, as its callers made it before they moved here, so importing
antennaknobs still loads no part of momwire it does not need. Each entry
is retired when momwire publishes the name (AK#2219 phase 2).
"""

from __future__ import annotations

from momwire.networks._reduce import _series_rlc_impedance as series_rlc_impedance
from momwire.networks._spec import (
    _branch_port_refs as branch_port_refs,
)
from momwire.networks._spec import (
    _parallel_rlc_admittance as parallel_rlc_admittance,
)
from momwire.networks._spec import (
    _rewrite_branch as rewrite_branch,
)

__all__ = [
    "branch_port_refs",
    "couplings",
    "eps_tilde",
    "feature_certified",
    "feature_registry",
    "k_medium",
    "lambda_medium",
    "parallel_rlc_admittance",
    "rewrite_branch",
    "series_rlc_impedance",
]


def eps_tilde(medium, omega, eps0):
    """A soil's complex relative permittivity at `omega`."""
    from momwire._ground_refl import eps_tilde as _eps_tilde  # noqa: PLC0415 — on use

    return _eps_tilde(medium, omega, eps0)


def lambda_medium(eps_t, k0):
    """The wavelength in a medium of relative permittivity `eps_t`."""
    from momwire._sommerfeld_below import lambda_medium as _f  # noqa: PLC0415 — on use

    return _f(eps_t, k0)


def k_medium(eps_t, k_p):
    """k_m = k_p·√ε̃ on the branch the buried fill takes."""
    from momwire._sommerfeld_below import k_medium as _f  # noqa: PLC0415 — on use

    return _f(eps_t, k_p)


def couplings():
    """momwire's served option couplings (momwire#885), or None when the
    installed momwire predates them."""
    try:
        from momwire._couplings import COUPLINGS  # noqa: PLC0415 — on use
    except ImportError:
        return None
    return COUPLINGS


def feature_registry():
    """momwire's opt-in feature registry (`FEATURES`), or None when the
    installed momwire has none."""
    try:
        from momwire import _features  # noqa: PLC0415 — on use
    except ImportError:
        return None
    return getattr(_features, "FEATURES", None)


def feature_certified(name) -> bool:
    """Whether momwire certifies feature `name` where this process runs.
    Raises as momwire does for an unknown name; ImportError when the
    installed momwire has no registry."""
    from momwire import _features  # noqa: PLC0415 — on use

    return _features.certified(name)
