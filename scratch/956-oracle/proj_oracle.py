"""An independent `proj_fn` for momwire's field-form Galerkin assembly.

momwire's buried fill contracts a PROJECTED PAIR TABLE against its basis:

    proj[i*q+u, j*q+v] = t_obs(i,u) . E( observer at obs[i,u],
                                         unit dipole at src[j,v] along t_src(j,v) )

`_field_galerkin_block` does everything else — the moment weights, the wing
sums, the chunking. So replacing ONLY `proj_fn` changes the Green's function
and nothing else, and a block difference is attributable to the kernel rather
than to a basis convention I might have misread. That is the whole reason this
file is a projector and not an assembler.

The kernel here is the momwire#524 phase-0 prototype's direct evaluation
(`scratch/524-phase0/proto/buried_proto.py`), whose warrant is that suite's
G4: empymod 2.6.0 at ht='quad' ppd=600, agreeing to 3.0e-04 on well-conditioned
grids. Re-run 2026-09-11 in a scratch venv, live and cached, identical.

Conventions are the prototype's, which are momwire's: SI, e^{+j omega t},
interface at z = 0, ground below, unit current moment I*l = 1.
"""

from __future__ import annotations

import os
import sys
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

_PROTO = Path(__file__).resolve().parents[1] / "524-phase0" / "proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import buried_proto as bp  # noqa: E402

_HS = None
_ERRCHECK = True
_VERBOSE = True


def set_medium(freq_hz, eps_r, sigma):
    global _HS
    _HS = bp.HalfSpace(freq=freq_hz, eps_r=eps_r, sigma=sigma)
    _HS.assert_decay()
    return _HS


def _e_transmitted(hs, obs, src, t_src):
    """E at `obs` (above) of a unit dipole at `src` (below) along `t_src`.

    The prototype evaluates about the SOURCE's ground projection, so the
    observer is shifted; and it offers HED (+x) and VED (+z) only, so an
    arbitrary tangent is decomposed. The horizontal part is done by ROTATING
    the frame rather than by superposing two HED calls: one call, and the
    rotation is exact for a horizontal dipole in an axisymmetric half-space.
    """
    dx = obs[0] - src[0]
    dy = obs[1] - src[1]
    zp = src[2]
    th, tz = np.hypot(t_src[0], t_src[1]), t_src[2]
    e = np.zeros(3, dtype=np.complex128)
    if th > 1e-14:
        ca, sa = t_src[0] / th, t_src[1] / th
        # rotate so the horizontal dipole lies along +x
        xr = dx * ca + dy * sa
        yr = -dx * sa + dy * ca
        er, _rel, _q = bp.field_transmitted(
            hs, (xr, yr, obs[2]), zp, "HED", err=_ERRCHECK
        )
        # rotate the field back
        e[0] += th * (er[0] * ca - er[1] * sa)
        e[1] += th * (er[0] * sa + er[1] * ca)
        e[2] += th * er[2]
    if abs(tz) > 1e-14:
        ev, _rel, _q = bp.field_transmitted(
            hs, (dx, dy, obs[2]), zp, "VED", err=_ERRCHECK
        )
        e += tz * np.asarray(ev)
    return e


def _one(args):
    (ox, oy, oz, tox, toy, toz, sx, sy, sz, tsx, tsy, tsz) = args
    if sz > 0.0 >= oz:
        # ABOVE source, BELOW observer. `field_transmitted` is written for a
        # buried source and an elevated observer, and feeding it the reverse
        # returns a DIFFERENT number quickly rather than refusing — measured
        # -4.17e-01-2.81e-01j against the reciprocal +2.31e-01-3.58e-01j on the
        # same physical pair. Reciprocity is the right route and it is gated:
        # V_T(b->a)(rho, z, z') = V_T(a->b)(rho, z', z) is the prototype's G1,
        # which reads 0.000e+00 over 18 combinations.
        e = _e_transmitted(_HS, (sx, sy, sz), (ox, oy, oz), (tox, toy, toz))
        return complex(tsx * e[0] + tsy * e[1] + tsz * e[2])
    e = _e_transmitted(_HS, (ox, oy, oz), (sx, sy, sz), (tsx, tsy, tsz))
    return complex(tox * e[0] + toy * e[1] + toz * e[2])


def _init(freq_hz, eps_r, sigma):
    set_medium(freq_hz, eps_r, sigma)


def make_proj(freq_hz, eps_r, sigma, workers=None):
    """A `proj_fn(obs, t_obs, src, t_src) -> (n_obs, n_src)` over the
    prototype's transmitted kernel, parallel over pairs."""
    return _make(freq_hz, eps_r, sigma, workers, _one)


def _make(freq_hz, eps_r, sigma, workers, worker_fn):
    set_medium(freq_hz, eps_r, sigma)
    nw = workers if workers is not None else max(1, (os.cpu_count() or 2) - 1)

    def proj(obs, t_obs, src, t_src):
        obs = np.asarray(obs, float)
        t_obs = np.asarray(t_obs, float)
        src = np.asarray(src, float)
        t_src = np.asarray(t_src, float)
        n_o, n_s = len(obs), len(src)
        _t0 = time.time()
        jobs = [
            (
                obs[i, 0],
                obs[i, 1],
                obs[i, 2],
                t_obs[i, 0],
                t_obs[i, 1],
                t_obs[i, 2],
                src[j, 0],
                src[j, 1],
                src[j, 2],
                t_src[j, 0],
                t_src[j, 1],
                t_src[j, 2],
            )
            for i in range(n_o)
            for j in range(n_s)
        ]
        if nw <= 1:
            out = [worker_fn(a) for a in jobs]
        else:
            with ProcessPoolExecutor(
                max_workers=nw, initializer=_init, initargs=(freq_hz, eps_r, sigma)
            ) as ex:
                out = list(
                    ex.map(worker_fn, jobs, chunksize=max(1, len(jobs) // (nw * 8)))
                )
        if _VERBOSE:
            print(
                f"    [proj] {n_o}x{n_s} = {len(jobs)} pairs in "
                f"{time.time() - _t0:.1f}s",
                flush=True,
            )
        return np.asarray(out, dtype=np.complex128).reshape(n_o, n_s)

    return proj


# ---------------------------------------------------------------------------
# below/below: the REMAINDER only, which is what momwire's projector returns
# ---------------------------------------------------------------------------


def _e_remainder_below(hs, obs, src, t_src):
    """Remainder E at `obs` (below) of a unit dipole at `src` (below) along
    `t_src` — the prototype's regime-2 R family, `shared="m"`.

    momwire's `remainder_field_proj_below` is the twin of THIS, not of the
    total in-medium field: its below/below block is direct at k_m plus the
    image minus this remainder, and the three are assembled separately. Pairing
    the total against it would be a silent decade of error.

    Same rotation treatment as the transmitted twin above, and for the same
    reason: the prototype offers HED (+x) and VED (+z), and the half-space is
    axisymmetric about the source's vertical.
    """
    dx = obs[0] - src[0]
    dy = obs[1] - src[1]
    zp = src[2]
    th, tz = np.hypot(t_src[0], t_src[1]), t_src[2]
    e = np.zeros(3, dtype=np.complex128)
    if th > 1e-14:
        ca, sa = t_src[0] / th, t_src[1] / th
        xr = dx * ca + dy * sa
        yr = -dx * sa + dy * ca
        er, _rel, _q = bp.field_remainder(
            hs, (xr, yr, obs[2]), zp, "HED", shared="m", err=_ERRCHECK
        )
        e[0] += th * (er[0] * ca - er[1] * sa)
        e[1] += th * (er[0] * sa + er[1] * ca)
        e[2] += th * er[2]
    if abs(tz) > 1e-14:
        ev, _rel, _q = bp.field_remainder(
            hs, (dx, dy, obs[2]), zp, "VED", shared="m", err=_ERRCHECK
        )
        e += tz * np.asarray(ev)
    return e


def _one_below(args):
    (ox, oy, oz, tox, toy, toz, sx, sy, sz, tsx, tsy, tsz) = args
    e = _e_remainder_below(_HS, (ox, oy, oz), (sx, sy, sz), (tsx, tsy, tsz))
    return complex(tox * e[0] + toy * e[1] + toz * e[2])


def make_proj_below(freq_hz, eps_r, sigma, workers=None):
    """`proj_fn` over the prototype's below/below REMAINDER."""
    return _make(freq_hz, eps_r, sigma, workers, _one_below)


# ---------------------------------------------------------------------------
# TOTAL fields, for comparison against momwire's ASSEMBLED Z
# ---------------------------------------------------------------------------
#
# The near-node unit compares assembled entries, not block entries. An assembled
# entry IS the EFIE Galerkin quantity -<f_m, E(f_n)> and stands alone; a block
# entry's meaning depends on compensating content elsewhere in the fill, which
# is what made cross-block substitution fail. So these compose the WHOLE field
# of each pair class, where the projectors above return single pieces.


def _e_total_below(hs, obs, src, t_src):
    """Total in-medium E: direct at k_m + A_m * image + remainder."""
    return _decompose(hs, obs, src, t_src, bp.field_in_medium, {})


def _e_total_above(hs, obs, src, t_src):
    """Total above/above E: free space at k_p + C2 * image + remainder."""
    return _decompose(hs, obs, src, t_src, _above_total, {})


def _above_total(hs, obs, zp, kind, err=True):
    """The +-=+ composition, written the way the prototype writes regime 2.

    `zp` is the SOURCE HEIGHT here (positive, above the plane), matching the
    prototype's sign handling for the shared-medium-p family.
    """
    p_hat = np.array([1.0, 0.0, 0.0]) if kind == "HED" else np.array([0.0, 0.0, 1.0])
    C1, kp, km = hs.C1, hs.kp, hs.km
    d = np.asarray(obs, dtype=float) - np.array([0.0, 0.0, zp])
    e_dir = bp.fs_field(C1, kp, p_hat, d)
    e_img = bp.image_field(C1, kp, p_hat, obs, zp, convention="mirror")
    c2 = (km * km - kp * kp) / (km * km + kp * kp)
    e_rem, rel, q = bp.field_remainder(hs, obs, zp, kind, shared="p", err=err)
    return e_dir + c2 * e_img + e_rem, rel, q


# Thin-wire stand-off. The closed forms in the prototype's direct and image
# terms are POINT-dipole fields and diverge at coincidence, which a same-medium
# self or touching pair reaches exactly. The physical model does not: an
# observer on the wire SURFACE is never nearer than one radius to a source on
# the axis. So the observer is pushed out radially to that radius when a pair
# would otherwise come closer — which is the thin-wire treatment, not a fudge,
# and it is the knob the radius ladder (a, 2a, 4a) varies to test whether an
# answer depends on it.
_R_MIN = 5e-4


def set_stand_off(a):
    global _R_MIN
    _R_MIN = float(a)


def _stand_off(dx, dy, dz):
    """Push (dx, dy) out radially until the separation is at least `_R_MIN`."""
    r = math.sqrt(dx * dx + dy * dy + dz * dz)
    if r >= _R_MIN:
        return dx, dy
    rho = math.hypot(dx, dy)
    want = math.sqrt(max(_R_MIN * _R_MIN - dz * dz, 0.0))
    if rho < 1e-15:
        return want, 0.0
    k = want / rho
    return dx * k, dy * k


def _decompose(hs, obs, src, t_src, fn, kw):
    """Arbitrary source tangent -> the prototype's HED (+x) / VED (+z) pair,
    by rotation. Identical treatment to the two projectors above."""
    dx = obs[0] - src[0]
    dy = obs[1] - src[1]
    dx, dy = _stand_off(dx, dy, obs[2] - src[2])
    zp = src[2]
    th, tz = np.hypot(t_src[0], t_src[1]), t_src[2]
    e = np.zeros(3, dtype=np.complex128)
    if th > 1e-14:
        ca, sa = t_src[0] / th, t_src[1] / th
        xr = dx * ca + dy * sa
        yr = -dx * sa + dy * ca
        er, _rel, _q = fn(hs, (xr, yr, obs[2]), zp, "HED", err=_ERRCHECK, **kw)
        er = np.asarray(er)
        e[0] += th * (er[0] * ca - er[1] * sa)
        e[1] += th * (er[0] * sa + er[1] * ca)
        e[2] += th * er[2]
    if abs(tz) > 1e-14:
        ev, _rel, _q = fn(hs, (dx, dy, obs[2]), zp, "VED", err=_ERRCHECK, **kw)
        e += tz * np.asarray(ev)
    return e


def _one_total_below(args):
    (ox, oy, oz, tox, toy, toz, sx, sy, sz, tsx, tsy, tsz) = args
    e = _e_total_below(_HS, (ox, oy, oz), (sx, sy, sz), (tsx, tsy, tsz))
    return complex(tox * e[0] + toy * e[1] + toz * e[2])


def _one_total_above(args):
    (ox, oy, oz, tox, toy, toz, sx, sy, sz, tsx, tsy, tsz) = args
    e = _e_total_above(_HS, (ox, oy, oz), (sx, sy, sz), (tsx, tsy, tsz))
    return complex(tox * e[0] + toy * e[1] + toz * e[2])


def make_proj_total_below(freq_hz, eps_r, sigma, workers=None):
    return _make(freq_hz, eps_r, sigma, workers, _one_total_below)


def make_proj_total_above(freq_hz, eps_r, sigma, workers=None):
    return _make(freq_hz, eps_r, sigma, workers, _one_total_above)
