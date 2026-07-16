"""One cost model for every solve-producing job (issue #382).

Admission used to be three parallel inventions: the hosted matrix caps
(``_check_solve_size``), the hosted point-count caps (inline in ``/sweep``
and ``/converge``), and the frontend's poor-match withhold gate
(``comboInappropriate`` in App.tsx, keyed off the server's recommended
backend). This module is the single mapping they all consult:

    admit(req, kind=..., points=..., use_pynec=..., hosted=..., example=...)
        -> Admission(verdict = "run" | "warn" | "refuse", reason, est_basis)

- **refuse**: hosted only — the matrix wouldn't fit the live box (per-engine
  basis caps) or the batch multiplies cost past the point cap. The caller
  turns this into a 413 / ``SolveTooLargeError``.
- **warn**: a dense-matrix solver on a benchmark-class mesh (the same
  ``est_basis > 3000`` condition behind the ``"sinusoidal"`` backend
  recommendation). The frontend withholds and asks "Solve anyway"; batch
  endpoints enforce it server-side — a warned batch runs only when the
  request carries ``_approved: true`` (set exactly when the user clicks
  through the gate). Applies hosted and local alike: it protects whatever
  machine is doing the computing.
- **run**: everything else, including anything whose size can't be estimated
  (no ``count_basis`` hook / geometry won't build) — the solve path surfaces
  the real error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


# Hosted live-engine matrix caps (see the sizing notes in issue #345): dense
# momwire and PyNEC form the full N×N complex matrix; the compressed engines
# (array-block / H-matrix) don't, so they get more headroom.
MAX_BASIS = _env_int("ANTENNAKNOBS_MAX_BASIS", 7000)  # dense momwire (~800 MB)
MAX_BASIS_COMPRESSED = _env_int("ANTENNAKNOBS_MAX_BASIS_COMPRESSED", 9000)
MAX_BASIS_PYNEC = _env_int("ANTENNAKNOBS_MAX_BASIS_PYNEC", 7000)
COMPRESSED_MODELS = frozenset({"arrayblock", "hmatrix"})

# Hosted compute levers beyond the matrix cap (issue #346): a client-chosen
# list length multiplies whole solves. Both sit far above what the UI sends
# (41-point sweeps, ≤200 optimizer evals).
MAX_SWEEP_POINTS = _env_int("ANTENNAKNOBS_MAX_SWEEP_POINTS", 500)
MAX_OPT_EVALS = _env_int("ANTENNAKNOBS_MAX_OPT_EVALS", 500)

# Above this estimated basis count the adapter recommends the sinusoidal
# backend (`_recommended_backend`); a dense-family solver here is minutes per
# solve where sinusoidal is seconds. Single source for the "warn" verdict —
# keep in sync with adapter._SINUSOIDAL_RECOMMEND_MIN_BASIS.
WARN_MIN_BASIS = 3000

# Job kinds whose "warn" the server enforces (batches of the very solves the
# gate exists to prevent). The live solve's warn stays a client-side prompt;
# /pattern is PyNEC-only (never warned); /pattern_metrics solves *other*
# designs for the compare table at their defaults, which the gate's
# this-design approval flow doesn't model — lane admission still bounds it.
ENFORCED_WARN_KINDS = frozenset({"sweep", "converge", "norm_check"})


@dataclass(frozen=True)
class Admission:
    verdict: str  # "run" | "warn" | "refuse"
    reason: str | None = None
    est_basis: int | None = None


def estimate_basis(req: dict, example) -> int | None:
    """Basis-count estimate via the example's geometry-only ``count_basis``
    hook (cheap — no solve). None when it can't be judged."""
    if example is None or example.count_basis is None:
        return None
    return example.count_basis(req)


def admit(
    req: dict,
    *,
    kind: str,
    use_pynec: bool,
    hosted: bool,
    example,
    points: int = 1,
) -> Admission:
    est = estimate_basis(req, example)

    if hosted and points > MAX_SWEEP_POINTS:
        return Admission(
            "refuse",
            f"A {'convergence sweep' if kind == 'converge' else 'sweep'} of "
            f"{points} points is over the live limit of {MAX_SWEEP_POINTS}. "
            f"Reduce the {'N' if kind == 'converge' else 'frequency'} count.",
            est,
        )

    if hosted and est is not None:
        if use_pynec:
            cap, engine, compressed = MAX_BASIS_PYNEC, "PyNEC", False
        elif req.get("momwire_model") in COMPRESSED_MODELS:
            cap = MAX_BASIS_COMPRESSED
            engine, compressed = str(req.get("momwire_model")), True
        else:
            cap, engine, compressed = MAX_BASIS, "momwire", False
        if est > cap:
            # Dense momwire and PyNEC both form the full N×N matrix; point
            # users at the compressed engines (which don't) for big arrays.
            hint = (
                ""
                if compressed
                else " — or switch to the array-block / H-matrix engine, which "
                "handles larger arrays without a dense matrix"
            )
            return Admission(
                "refuse",
                f"This solve needs ~{est} wire segments, over the live {engine} "
                f"limit of {cap}. Reduce 'segments / wire (N)' or pick a smaller "
                f"design{hint}.",
                est,
            )

    # Poor-match combo on a benchmark-class mesh: every b-spline-family
    # solver (dense or accelerated) is minutes per solve there. Mirrors the
    # frontend's comboInappropriate() for the "sinusoidal" recommendation;
    # PyNEC is exempt (native fill, admission-capped above).
    if (
        est is not None
        and est > WARN_MIN_BASIS
        and not use_pynec
        and req.get("momwire_model", "bspline") != "sinusoidal"
    ):
        noun = f"a batch of {points} solves" if points > 1 else "a solve"
        return Admission(
            "warn",
            f"This design needs ~{est} basis functions — {noun} with the "
            f"'{req.get('momwire_model', 'bspline')}' solver here can take "
            "minutes each. Switch to the Sinusoidal solver (recommended), or "
            "re-send with _approved: true to run anyway.",
            est,
        )

    return Admission("run", None, est)
