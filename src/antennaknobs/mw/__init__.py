"""antennaknobs' one boundary with momwire's internals (AK#2219).

Everything antennaknobs needs from momwire that momwire does not publish,
and everything AK-only that would otherwise need a momwire release, lives
behind this package. It imports nothing else from antennaknobs (a test
enforces that), so momwire's CI can import and test it without AK's web
or engine dependencies.

The contract with momwire core is small and written down here:

- `swept_y`: the swept multi-port admittance, assembled from core's
  per-frequency `PortSolution` stream. Each Y's shape is the solution's
  own, so no second copy of a port count can drift from the first
  (momwire#1861).
- The re-exported helpers in `_private`: momwire names antennaknobs uses
  that momwire keeps private today. Each is a debt with a named payoff, a
  public momwire name (#2219 phase 2), and `_private` is the only module
  in antennaknobs allowed to import a private momwire name
  (tests/test_momwire_private_imports.py).
"""

from __future__ import annotations

from ._private import (
    branch_port_refs,
    couplings,
    eps_tilde,
    feature_certified,
    feature_registry,
    k_medium,
    lambda_medium,
    parallel_rlc_admittance,
    rewrite_branch,
    series_rlc_impedance,
)
from ._swept import swept_y

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
    "swept_y",
]
