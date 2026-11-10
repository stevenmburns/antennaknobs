"""Engine-agnostic reduction of a port-based `Network` spec to driven-port
impedances, on top of a raw multiport antenna admittance matrix.

Arrived from antennaknobs per ``docs/design/networks-move-into-the-engine.md``
(momwire#456 workstream 2). This module is the TYPE-FREE half — the TL/chain
math and the MNA core, which never see a port name or a branch dataclass. The
spec layer landed alongside in `._spec` and `NetworkReducer` in `._reducer`
rather than appended here: `._spec` reuses `_series_rlc_impedance` below, so
keeping the three apart is what makes the arrows acyclic.

antennaknobs' MomwireEngine and PyNECEngine assemble the antenna's short-circuit
Y at the real (`PortOnWire`) ports, then hand it here with a port-name -> matrix-
index map. This module stamps the network branches and sources into one
Modified Nodal Analysis (MNA) system — the SPICE formulation, issue #285 —
and solves it once for everything: driven-port impedances, physical port
voltages for the excited far-field/current solve, and the source-power /
load-dissipation bookkeeping. The only engine-specific work is producing the
raw Y and the index map; the linear algebra here is identical regardless of
which MoM solver produced Y.

This is the EZNEC-style approach: model transmission lines and lumped
elements as a circuit post-process on top of the field solution, rather than
via NEC2's native `tl_card` / `nt_card` / `ld_card`.

The node space is the port space: one node per port (real feeds first,
virtual ports after), every node's voltage referenced to the common return
(the datum). The datum has no matrix row — every port's second terminal is
bonded to it, which is the same convention the antenna's short-circuit
multiport Y already assumes. Elements that a bare admittance matrix cannot
represent — ideal voltage sources, ideal shorts, 0 Ω / 0 H series elements —
become Group-2 unknowns: the branch current joins the solution vector with a
constitutive row, so no element value is ever inverted.

Issue #746 pushed that principle through the two places it was still being
violated. Transmission lines are stamped as their CHAIN matrix rather than
their admittance (two branch currents each), because a k·λ/2 line has no
admittance matrix at all while its ABCD is [[±1, 0], [0, ±1]]. And the
impedance/Γ solve stamps each driven port's EMF behind a reference impedance
rather than pinning the node, because Z_s = 0 is what made a short across the
port unsolvable — Z = E/j − z_ref is the same answer, Γ comes out natively,
and an open reads a finite +1 instead of ∞. The excited / far-field solve
keeps the ideal generator, deliberately: see `excited_state`.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

import numpy as np

# momwire's `_constants.C_LIGHT`, which this module imported upstream. Exact by
# the SI definition of the metre, so the literal cannot drift from momwire's.
C_LIGHT = 299_792_458.0

FEET_PER_M = 1.0 / 0.3048
NEPER_PER_DB = 1.0 / (20.0 / np.log(10.0))  # 1/8.6859: dB → nepers


class SingularNetworkError(ValueError):
    """The network has no finite solution at this frequency (issue #647).

    Raised by the solve, when the branches made the system singular even
    though every individual stamp was finite: a node reachable only through
    open-circuited branches, or a subnetwork with no return path. Also by the
    Touchstone conversions, whose poles are the same fact about a description
    rather than about a circuit.

    Addendum 2026-08-06 (issue #746): the two cases this type was WRITTEN for
    are gone. A lossless k·λ/2 line raised because the reducer stamped its
    admittance, which does not exist there; it now stamps the chain matrix,
    which does. A lossless λ/4 open stub raised because Z_in = 0 shorts the
    port and an IDEAL generator cannot drive a short; the driven port now sits
    behind `Z_REF_DEFAULT` and the short is simply the answer. What remains is
    genuine rank deficiency — and the far-field path, which keeps the ideal
    generator on purpose and so can still meet the second case.

    A `ValueError` subclass so the guards that predate it keep their contract;
    a distinct type so `impedance_sweep` can poison one sample and carry on
    instead of losing the whole sweep.
    """


# Reciprocal condition number below which the MNA solve is called singular.
# 1e-12 is the same threshold `tl_admittance_2x2` uses for |sinh γl| and the
# Touchstone conversions for their own inverses — one policy across the
# package for "this is a pole, not a stiff problem".
_logger = logging.getLogger(__name__)

RCOND_SINGULAR = 1e-12
# Between the two, the answer exists but its leading digits are being eaten by
# the pole; worth saying so, not worth refusing.
RCOND_SUSPECT = 1e-9

# Source impedance the impedance/Γ solve stamps behind each driven port
# (issue #746). Z is algebraically independent of it — the readout subtracts
# it back out — so this is not a physical constant of any design; it is the
# reference Γ is quoted against, and 50 Ω is the reference every VNA, every
# `.s1p` and every SWR number in this package already uses.
Z_REF_DEFAULT = 50.0


def frequency_mhz(wavelength, c_light_mhz_m=None):
    """The frequency, in MHz, a reducer evaluates a frequency-dependent
    branch at, from the wavelength it was handed (antennaknobs#1685).

    ``c_light_mhz_m`` is the DESIGN's metre-megahertz product: 299.8 for a
    deck-derived design, which solves at NEC's own wavelength 299.8/f while
    NEC still evaluates its lumped loads and line loss at the deck's own f.
    Converting that wavelength back with the SI c reads f 25 ppm low
    (14.17464 MHz for a 14.175 MHz deck), so a caller whose wavelength came
    from another c passes it here. ``None`` is the SI c, and that branch is
    the expression every caller used before the keyword existed, so a caller
    that does not pass it stays bit-identical.
    """
    if c_light_mhz_m is None:
        return C_LIGHT / wavelength / 1e6
    return c_light_mhz_m / wavelength


def _tl_gamma_l(length, wavelength, vf, k1, k2, c_light_mhz_m=None, k0=0.0):
    """Complex propagation γ·length = (α + jβ)·length.

    β = 2π/(vf·λ); α comes from the cable-table matched-loss model
    k1·√f_MHz + k2·f_MHz in dB per 100 ft (see `network.TL`). Shared by the
    admittance and chain-matrix forms so the two can never disagree about
    what line they describe.

    The PHASE reads the wavelength as given, which is NEC's rule: its line
    phase uses its own wavelength. Only the loss reads a frequency, at
    :func:`frequency_mhz` with the design's ``c_light_mhz_m``.
    """
    beta = 2.0 * np.pi / (vf * wavelength)
    f_mhz = frequency_mhz(wavelength, c_light_mhz_m)
    loss_db_per_100ft = k1 * np.sqrt(f_mhz) + k2 * f_mhz
    if k0:
        loss_db_per_100ft = loss_db_per_100ft + k0
    alpha = loss_db_per_100ft * NEPER_PER_DB * FEET_PER_M / 100.0  # nepers/m
    return (alpha + 1j * beta) * length


def _tl_zc(z0, gl):
    """The line's characteristic impedance: ``z0`` itself when lossless, and
    ``z0·(1 − jα/β)`` when lossy (momwire#1706).

    A lossy line's characteristic impedance is complex. With the loss in the
    series resistance, Zc = √((R + jωL)/(jωC)) = Z0·√(1 + R/(jωL)), which to
    first order in α/β = R/(2ωL) is Z0·(1 − jα/β): EZNEC's lossy line, and
    antennaknobs' ``.ez`` importer's. α/β is Re(γl)/Im(γl), the length
    cancelling. A lossless line (α exactly 0) returns ``z0`` untouched, so
    every lossless stamp is bit for bit what it was.
    """
    if gl.real == 0.0 or gl.imag == 0.0:
        return z0
    return z0 * (1.0 - 1j * (gl.real / gl.imag))


def _tl_line(
    z0, length, wavelength, vf, k1, k2, c_light_mhz_m=None, skin=False, k0=0.0
):
    """``(γ·length, Zc)`` of a `TL` — the one place both stamps read a line.

    Without ``skin`` it is `_tl_gamma_l` and `_tl_zc`, unchanged. With it,
    AC6LA's Johnson line (see `network.TL`), written in units of the lossless
    line's ωL and ωC: d = R_dc/(ωL) = 2α₀/β, r = R_hf/(ωL) = 2α₁/β and
    g = G/(ωC) = 2α₂/β, so Z′/(jωL) = 1 − j·√(d² + [r(1 + j)]²) and
    Y′/(jωC) = 1 − jg. Then γ = jβ·√(pq) and Zc = z0·√(p/q). β and the α's
    are `_tl_gamma_l`'s own, so the phase still reads the wavelength as given
    and the loss the frequency, as every line here does.
    """
    if not skin:
        gl = _tl_gamma_l(length, wavelength, vf, k1, k2, c_light_mhz_m, k0)
        return gl, _tl_zc(z0, gl)
    beta = 2.0 * np.pi / (vf * wavelength)
    f_mhz = frequency_mhz(wavelength, c_light_mhz_m)
    per_m = NEPER_PER_DB * FEET_PER_M / 100.0
    d = 2.0 * k0 * per_m / beta
    r = 2.0 * k1 * np.sqrt(f_mhz) * per_m / beta
    g = 2.0 * k2 * f_mhz * per_m / beta
    p = 1.0 - 1j * np.sqrt(d * d + (r * (1.0 + 1j)) ** 2)
    q = 1.0 - 1j * g
    return 1j * beta * np.sqrt(p * q) * length, z0 * np.sqrt(p / q)


def tl_abcd(
    z0,
    length,
    wavelength,
    vf=1.0,
    k1=0.0,
    k2=0.0,
    *,
    c_light_mhz_m=None,
    skin=False,
    k0=0.0,
):
    """Ideal-TL chain (ABCD) matrix ``(A, B, C, D)`` — the reducer's stamp
    (issue #746).

        [v_a; i_a] = [[cosh γl, Zc sinh γl], [sinh γl / Zc, cosh γl]] · [v_b; i_b]

    with Zc the line's characteristic impedance, complex when it is lossy
    (`_tl_zc`, momwire#1706), and i_a into port A and i_b out of port B. Every entry is an entire
    function of γl, so unlike `tl_admittance_2x2` — the same line, written as
    the ratio 1/(Z0 sinh γl) — this has no pole anywhere: at the lossless
    k·λ/2 point it is exactly [[±1, 0], [0, ±1]], the through-line the
    admittance description cannot spell because its currents are unconstrained
    by its voltages there. That is the whole reason the reducer carries two
    Group-2 currents per line instead of a 2×2 Group-1 block.

    A crossed ("half-twist") line is NOT a flag here: it is port B's weights
    negated where the pair is stamped, which is what a polarity inversion is.
    """
    gl, zc = _tl_line(z0, length, wavelength, vf, k1, k2, c_light_mhz_m, skin, k0)
    sh, ch = np.sinh(gl), np.cosh(gl)
    return ch, zc * sh, sh / zc, ch


def tl_admittance_2x2(
    z0,
    length,
    wavelength,
    transposed=False,
    vf=1.0,
    k1=0.0,
    k2=0.0,
    *,
    c_light_mhz_m=None,
    skin=False,
    k0=0.0,
):
    """Ideal-TL nodal admittance between its two terminals — lossless or
    lossy (issue #297).

    No longer what the reducer stamps (issue #746 moved that to `tl_abcd`);
    kept as the closed-form 2×2 that composition oracles and the balanced
    4×4's even/odd decomposition are written against.

    For complex propagation γl = (α + jβ)·length with β = 2π/(vf·λ):
        Y_TL = 1/(Zc sinh γl) · [[cosh γl, -1], [-1, cosh γl]]
    (Zc complex when the line is lossy, as in `tl_abcd`)
    which reduces exactly to the classic lossless form
        Y_TL = 1/(j Z0 sin θ) · [[cos θ, -1], [-1, cos θ]]
    at α = 0 (sinh jθ = j·sin θ). α comes from the cable-table matched-loss
    model k1·√f_MHz + k2·f_MHz in dB per 100 ft (see `network.TL`).

    Singular only for an exactly-lossless half-wavelength multiple
    (sinh γl = 0 requires α = 0), where the line HAS no admittance matrix;
    raise rather than return garbage. This is a statement about the
    description, not about the physics — the reducer solves that same line
    through `tl_abcd` without complaint.

    `transposed=True` models a crossed ("half-twist") line: port B's
    polarity is inverted, which flips the sign of the off-diagonal
    (transfer) terms only. This is the nodal-model equivalent of NEC2's
    negative-Z0 tl_card crossing, used by transposed-feeder arrays (LPDA,
    ZL-Special). Note it is NOT the same as a negative z0, which would
    (wrongly) negate the diagonal self terms too.
    """
    gl, zc = _tl_line(z0, length, wavelength, vf, k1, k2, c_light_mhz_m, skin, k0)
    sh, ch = np.sinh(gl), np.cosh(gl)
    if abs(sh) < 1e-12:
        f_mhz = frequency_mhz(wavelength, c_light_mhz_m)
        raise SingularNetworkError(
            f"lossless TL length {length} is ~k·vf·λ/2 at "
            f"f={f_mhz:.4f} MHz (sinh γl ≈ 0); the admittance is singular "
            "there because the line has no admittance matrix at all — ask for "
            "its chain matrix (`tl_abcd`) instead, which is what the reducer "
            "stamps and which stays finite"
        )
    scale = 1.0 / (zc * sh)
    off = 1.0 if transposed else -1.0
    return scale * np.array([[ch, off], [off, ch]], dtype=np.complex128)


# The pair incidence: a differential-mode current I into terminal 1 and −I out
# of terminal 2, driven by the pair voltage v1 − v2. Tensoring the 2×2 TL
# admittance with this rank-1 block expands each differential port to its two
# physical terminals (issue #575).
_DIFF_INCIDENCE = np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=np.complex128)

# The common-mode incidence: the pair driven as one conductor. CM current is
# the TOTAL I₁ + I₂ (splitting equally) and CM voltage the pair AVERAGE, so
# each terminal carries ¼ of the 2×2 CM entry: I(a1) = ¼·(y·(v_a1 + v_a2) + …).
# Orthogonal to _DIFF_INCIDENCE (it annihilates differential vectors), so the
# two blocks superpose without cross-terms — the even/odd decomposition.
_COMM_INCIDENCE = np.full((2, 2), 0.25, dtype=np.complex128)


def balanced_admittance_4x4(
    zdiff, length, wavelength, vf=1.0, k1=0.0, k2=0.0, zcomm=None, *, c_light_mhz_m=None
):
    """Balanced two-conductor TL nodal admittance (issues #575/#576) — a 4×4
    block over the terminal order ``(a1, a2, b1, b2)`` (port A = (a1, a2),
    port B = (b1, b2)).

    The closed form of the even/odd decomposition, and the oracle the
    reducer's per-mode chain-matrix stamp is checked against; it is no longer
    itself the stamp (issue #746).

    In differential variables the element is an ordinary 2-port TL with
    z0 = ``zdiff``, so the differential block is that 2×2 expanded through the
    pair incidence:

        Y_4 = kron(tl_admittance_2x2(zdiff, …), [[1, −1], [−1, 1]])

    i.e. each 2×2 entry ``y`` becomes the block ``y·[[1,−1],[−1,1]]`` over the
    terminal pair. With ``zcomm=None`` that is the whole stamp: the common
    mode is structurally open (rank 2) and ``I(a1) = −I(a2)`` is forced at
    each end — the ±I differential cancellation, enforced by wiring. There is
    no ``transposed`` flag: a crossover is wiring port B as ``(b2, b1)``.

    ``zcomm`` (issue #576's end-to-end finding) adds the orthogonal
    common-mode block — the pair driven as ONE conductor against the network
    common, an ordinary 2-port TL with z0 = ``zcomm`` over (I₁+I₂, ½(v₁+v₂)):

        Y_4 += kron(tl_admittance_2x2(zcomm, …), ¼·ones(2, 2))

    The ¼-ones incidence annihilates differential vectors, so the CM block
    never perturbs the differential behaviour — the exact even/odd
    decomposition of an ideal coupled pair. See `network.BalancedLine` for
    when (and how honestly) a CM path can be modelled at all.

    Inherits `tl_admittance_2x2`'s matched-loss model and its half-wave
    singularity — a lossless line at exactly k·vf·λ/2 has no admittance
    matrix, so this raises there while the reducer solves it. Grounding
    conductor 2 at both ends
    (dropping rows/cols a2, b2) collapses the ``zcomm=None`` stamp exactly
    back to that 2×2."""
    kw = dict(vf=vf, k1=k1, k2=k2, c_light_mhz_m=c_light_mhz_m)
    y2 = tl_admittance_2x2(zdiff, length, wavelength, **kw)
    y4 = np.kron(y2, _DIFF_INCIDENCE)
    if zcomm is not None:
        yc = tl_admittance_2x2(zcomm, length, wavelength, **kw)
        y4 = y4 + np.kron(yc, _COMM_INCIDENCE)
    return y4


# ---------------------------------------------------------------------------
# MNA (Modified Nodal Analysis) core — issue #285.
# ---------------------------------------------------------------------------


@dataclass
class _Group2Element:
    """One Group-2 (auxiliary-current) element of the MNA system.

    The element carries a branch current ``j`` flowing a → b *through* the
    element (``None`` = the datum, which has no matrix row). KCL: ``+j``
    leaves node a and enters node b. The constitutive row is

        c_v · (v_b − v_a) + c_j · j = e

    Two scalings describe the same physical series branch — an EMF ``emf``
    (oriented to raise the potential from a to b) in series with impedance
    ``z`` = 1/``y``:

      impedance form:  (v_b − v_a) + z·j = emf      (c_v=1, c_j=z, e=emf)
          exact for every finite z, including the ideal short z = 0;
      admittance form: y·(v_b − v_a) + j = y·emf    (c_v=y, c_j=1, e=y·emf)
          exact for every finite y, including the ideal open y = 0.

    Each branch picks whichever form keeps its coefficients finite, so no
    element value is ever inverted — the reason ideal shorts and trap-
    resonance opens need no special-case guards here.

    Generalization for coupled elements (issue #301, the Transformer):
    ``ka``/``kb`` scale the KCL currents (``ka·j`` leaves node a,
    ``kb·j`` enters node b — an ideal transformer's windings carry
    ratio-linked currents, so kb = n), and ``c_va``/``c_vb``, when set,
    replace the symmetric ``∓c_v`` voltage coefficients of the
    constitutive row with

        c_va · v_a + c_vb · v_b + c_j · j = e

    (the transformer's row is v_a − n·v_b − r_w·j = 0). Defaults keep
    every pre-existing series element bit-identical.

    Third terminal (issue #589, the FloatingBalun): an optional node ``c``
    with KCL scale ``kc`` (``kc·j`` leaves node c, same sign convention as
    node a) and voltage coefficient ``c_vc`` adds a third column/row so a
    single branch current can couple three distinct nodes — a
    floating-secondary transformer whose primary lives on its own node ``c``
    while the differential secondary spans ``a``/``b``. Its constitutive row
    is v_a − v_b − n·v_c = r·j (c_va=1, c_vb=−1, c_vc=−n), and reciprocity
    pins kc = c_vc = −n (the row equals the current column, as for a/b), so
    the ideal element is lossless. ``c=None`` (the default) is a plain
    two-terminal branch, bit-identical to before.

    Arbitrary arity (issue #746, the chain-matrix lines): ``terms`` — a
    sequence of ``(node, k, c_v)`` triples with the same meanings (``k·j``
    leaves ``node``; ``c_v·v_node`` appears in the constitutive row) —
    REPLACES a/b/c entirely when set. A `BalancedLine`'s differential
    chain-matrix row spans four terminals (a1, a2, b1, b2), one more than
    the a/b/c form can name, and a chain matrix also needs terminals whose
    voltage it senses without drawing current (k = 0) — neither fits the
    two-scaling shape above.
    """

    a: int | None
    b: int | None
    c_v: complex
    c_j: complex
    e: complex
    ka: complex = 1.0 + 0j
    kb: complex = 1.0 + 0j
    c_va: complex | None = None
    c_vb: complex | None = None
    c: int | None = None
    kc: complex = 0j
    c_vc: complex = 0j
    terms: tuple[tuple[int, complex, complex], ...] | None = None


def _stamp_abcd(elements, couplings, port_a, port_b, abcd):
    """Stamp a 2-port given by its chain matrix; return its power-probe leg.

    ``port_a`` / ``port_b`` are ``[(node, weight), ...]``: the port voltage is
    ``Σ w·v_node`` and the port current ``j`` leaves each node as ``w·j``. One
    weight list per port is a congruence, so the port pair carries exactly the
    power ``v·j`` however many terminals it spans — which is what lets the
    same routine stamp a coax (``[(a, 1)]`` / ``[(b, 1)]``), a crossed line
    (``[(b, −1)]`` — a polarity inversion IS a negated weight), and a balanced
    pair's differential (``[(a1, 1), (a2, −1)]``) and common (``[(a1, ½),
    (a2, ½)]``) modes, whose incidences are orthogonal.

    Two auxiliary currents, j₁ into port A and j₂ out of port B, with the
    chain relations as their constitutive rows::

        v_a − A·v_b − B·j₂ = 0
        j₁  − C·v_b − D·j₂ = 0

    Both rows stay finite for every line length, which the 2×2 admittance
    block they replace does not (issue #746). The j₂ terms are the only
    off-diagonal entries in the branch-current block, so they ride the
    ``couplings`` channel added for the Autotransformer (issue #594).
    """
    a_, b_, c_, d_ = abcd
    i1, i2 = len(elements), len(elements) + 1
    elements.append(
        _Group2Element(
            None,
            None,
            c_v=0j,
            c_j=0j,
            e=0j,
            # v_a with its own current's incidence; v_b sensed, no current.
            terms=tuple([(n, w, w) for n, w in port_a])
            + tuple((n, 0j, -a_ * w) for n, w in port_b),
        )
    )
    elements.append(
        _Group2Element(
            None,
            None,
            c_v=0j,
            c_j=-d_,
            e=0j,
            terms=tuple((n, -w, -c_ * w) for n, w in port_b),
        )
    )
    couplings.append((i1, i2, -b_))
    couplings.append((i2, i1, 1.0 + 0j))
    return (i1, i2, tuple(port_a), tuple(port_b))


def magnetizing_impedance(br, omega):
    """Magnetizing-branch impedance of a `Transformer` / `FloatingBalun`.

    ``core`` (a `ferrite.FerriteCore`, issue #599) supersedes ``lmag``/``qlmag``
    wholesale — it IS the core, the way ``TL.from_cable``'s cable is the cable —
    and the branch then follows the material's complex permeability at this
    frequency: μ′ gives the inductance, μ″ the loss. Falling back to
    ``lmag``/``qlmag`` keeps the scalar model available and unchanged, and the
    two agree exactly when the material is flat with μ″ = μ′/Q.

    Returns ``None`` when the element declares no magnetizing branch at all.
    """
    core = getattr(br, "core", None)
    if core is not None:
        return core.impedance(omega / (2.0 * np.pi) / 1e6)
    if br.lmag is None:
        return None
    z = 1j * omega * br.lmag
    if br.qlmag is not None:
        z += omega * br.lmag / br.qlmag
    return z


def _series_rlc_impedance(r, l, c, omega, ql=None, qc=None):
    """Series R + jωL + 1/(jωC). Any of r/l/c may be None (omitted term).

    Finite component Q (issue #298): `ql` adds the coil's series loss
    R_coil = ωL/Q_L; `qc` adds the capacitor's ESR = 1/(ωC·Q_C). Both are
    frequency-dependent by construction — a fixed `r` cannot express them
    across a sweep. None (default) = ideal component.

    Q is treated as frequency-INDEPENDENT: R = ωL/Q is re-derived at each
    solve frequency, so across a sweep R grows ∝ f. Physical truth for an
    air-core HF coil sits between the two expressible models — skin effect
    gives R ∝ √f (i.e. Q ∝ √f) — so constant Q overestimates loss above
    the frequency where the quoted Q is true and underestimates below it,
    while a fixed resistance (use plain `r` = ω_ref·L/Q for that) errs the
    opposite way. At a single operating frequency, with Q quoted at that
    frequency, all three agree. A √f reference-frequency model would slot
    in here if sweep fidelity ever warrants it.

    Moved down with the MNA core (momwire#456) rather than left behind with
    the spec layer: `_series_group2` is the only caller in this half, and it
    is the sole first-party dependency the extraction survey missed. Private
    here; `._spec` imports it rather than landing a second copy, which is the
    one arrow that fixes the module order (spec -> reduce, never back).
    """
    z = 0.0 + 0.0j
    if r is not None:
        z += r
    if l is not None:
        z += 1j * omega * l
        if ql is not None:
            z += omega * l / ql
    if c is not None:
        z += 1.0 / (1j * omega * c)
        if qc is not None:
            z += 1.0 / (omega * c * qc)
    return z


def _series_group2(a, b, r, l, c, omega, emf=0j, ql=None, qc=None):
    """Group-2 stamp of a series R + jωL + 1/(jωC) (+ optional EMF) between
    nodes a and b. A 0 F capacitor is an open in the series path (infinite
    reactance) → admittance form with y = 0 (the branch carries no current).
    Every other value combination has finite z — including the ideal short
    z = 0 (0 Ω, 0 H, all-omitted, or exact series-LC resonance), which the
    old admittance-only stamps had to raise on. `ql`/`qc` add the finite-Q
    component losses (issue #298, see `_series_rlc_impedance`)."""
    if c is not None and c == 0:
        return _Group2Element(a, b, c_v=0j, c_j=1.0 + 0j, e=0j)
    z = _series_rlc_impedance(r, l, c, omega, ql, qc)
    return _Group2Element(a, b, c_v=1.0 + 0j, c_j=z, e=emf)


# ---------------------------------------------------------------------------
# Sparse MNA (AK#2241): the path a large circuit-only network takes.
# ---------------------------------------------------------------------------

# The MNA dimension n + m (node voltages plus Group-2 branch currents) at and
# above which `apply_branches` assembles the system sparse and `solve` factors
# it with SuperLU instead of dense `zgesvx` (AK#2241).
#
# The unit is the matrix dimension, not the node count, because that is what
# both costs scale with: dense is O((n+m)³) time and O((n+m)²) storage, sparse
# about linear in the stamp count on a ladder-like network. A line is two
# Group-2 currents and a series part one, so n alone understates a network
# made mostly of them by up to 3x. It is known exactly once every branch has
# stamped, and it depends on topology only, so a design is on one path at
# every frequency of a sweep.
#
# Measured per frequency (`scratch/2241-sparse-mna/crossover.py`, apply_branches
# + solve, best of 5, laptop): the two paths cost the same at about 80
# unknowns, on the RLCG ladder (n+m 82: dense 0.97 ms, sparse 1.07 ms) and on
# a chain of station networks (n+m 79: 0.96 / 1.11 ms). Below that sparse
# carries a fixed ~0.6 ms of scipy overhead; above it dense grows as n³ (n+m
# 402: 15 / 2.2 ms; 1202: 125 / 5.4 ms). 200 sits 2.5x above the crossover,
# where dense still costs under 5 ms, and 6x above the largest network the
# catalog ships (n+m 34, `catalog_census.py`), so every existing design stays
# on the dense path and keeps its numbers bit for bit.
#
# Read at call time, so a test forces either path by monkeypatching it:
# 0 forces sparse everywhere, a huge value forces dense.
SPARSE_MIN_UNKNOWNS = 200


def use_sparse(n_unknowns):
    """Whether an MNA system of ``n_unknowns`` (= n + m) is assembled sparse."""
    return n_unknowns >= SPARSE_MIN_UNKNOWNS


class _MNAStamps:
    """The Group-1 (node-admittance) stamps of one `apply_branches` call, as
    COO triples in stamp order: the one assembly both solve paths read.

    The size decision needs the Group-2 count, which is only known once every
    branch has stamped, so nothing is laid out until `triples` runs. That
    emits the whole MNA matrix — the antenna block first, then every branch
    stamp below in call order, then the Group-2 columns, rows and couplings —
    and `MNASystem` either densifies it (`_densify`, accumulating in exactly
    that order, small) or sums it into CSC (`_csc`, large). A large network
    never allocates ``n × n``: the antenna's ``Y_real`` (and its floating-
    port congruence) is dense only over the real ports and the floating
    ports' "-" nodes, and every branch stamp is a small block.

    Duplicates SUM, on both paths. A multiport whose ports repeat a node (an
    `Admittance` on ``(a, a)``, a `TouchstoneTwoPort` with ``a == b``)
    therefore injects I1 + I2 = (y11 + y12 + y21 + y22)·V at that node, which
    is the physics and is what NEC-5 and NEC-4.2 do with an ``NT`` card whose
    two ends are one segment (momwire#1887). The dense stamp this replaced,
    ``G[np.ix_(idxs, idxs)] += yb``, is a buffered fancy-index add that kept
    ONE of the four entries instead.
    """

    def __init__(self, n, y_real, floating):
        self.n = n
        self.y_real = y_real
        # ((p_idx, n_idx), ...) for each floating gap port.
        self.floating = tuple(floating)
        self.rows: list[int] = []
        self.cols: list[int] = []
        self.vals: list[complex] = []

    def add_block(self, idxs, yb):
        """``G[idxs[i], idxs[j]] += yb[i, j]`` for every i, j, row by row."""
        k = len(idxs)
        for i in idxs:
            self.rows += [i] * k
            self.cols += idxs
        self.vals += np.asarray(yb, dtype=np.complex128).ravel().tolist()

    def add_diag(self, k, y):
        """``G[k, k] += y``."""
        self.rows.append(k)
        self.cols.append(k)
        self.vals.append(y)

    def _antenna_block(self, full_width):
        """``(nodes, block)``: the antenna's stamp over the nodes it reaches.

        Port incidence: gap row i drives node i positively, and a floating
        port also drives its "-" node negatively. The stamp is the congruence
        AᵀYA — the same [[1,-1],[-1,1]] structure BalancedLine uses,
        generalized over the whole multiport; with no floating ports it is
        ``Y_real`` itself. ``full_width`` computes the product with A at the
        full node width n, the dense path's historical arithmetic, and keeps
        only the reachable rows and columns (every other entry of that
        product is a signed zero, and 0 + ±0 is the +0 an unstamped entry
        already holds); otherwise A is only as wide as the reachable nodes, so
        a large network never forms n × n.
        """
        Y_real = self.y_real
        n_real = Y_real.shape[0]
        if not self.floating:
            return range(n_real), Y_real
        minus = [n_idx for _p, n_idx in self.floating]
        if full_width:
            A = np.zeros((n_real, self.n), dtype=np.complex128)
            A[np.arange(n_real), np.arange(n_real)] = 1.0
            for p_idx, n_idx in self.floating:
                A[p_idx, n_idx] = -1.0
            nodes = np.unique(np.concatenate([np.arange(n_real), minus]))
            return nodes, (A.T @ Y_real @ A)[np.ix_(nodes, nodes)]
        nodes = np.concatenate([np.arange(n_real), minus]).astype(np.int64)
        inc = np.zeros((n_real, len(nodes)), dtype=np.complex128)
        inc[np.arange(n_real), np.arange(n_real)] = 1.0
        for x, (p_idx, _n) in enumerate(self.floating):
            inc[p_idx, n_real + x] = -1.0
        return nodes, inc.T @ Y_real @ inc

    def triples(self, elements, couplings, *, full_width):
        """The whole MNA matrix in stamp order, as ``(antenna, keys, vals,
        rhs)``.

        ``antenna`` is ``(nodes, block)``, the antenna's stamp: a dense block
        of triples, first in the order, over distinct nodes on the full-width
        (dense) path. ``keys`` / ``vals`` are every other triple — the branch
        stamps, then `_group2_triples` — with each (row, col) carried as the
        flat index ``row·N + col`` of the ``N × N`` matrix (N = n + m), which
        is what both `_densify` and the CSC build need and saves the dense
        path an index conversion. ``rhs`` is the whole right-hand side.

        A network of a few dozen unknowns is all fixed cost, so the Python-
        level triples stay in one list per field and convert to arrays once.
        """
        N = self.n + len(elements)
        keys = [r * N + c for r, c in zip(self.rows, self.cols, strict=True)]
        vals = list(self.vals)
        rhs = _group2_triples(self.n, N, elements, couplings, keys, vals)
        return (
            self._antenna_block(full_width),
            np.array(keys, dtype=np.int64),
            np.array(vals, dtype=np.complex128),
            rhs,
        )


def _group2_triples(n, N, elements, couplings, keys, vals):
    """Append the Group-2 half of the MNA matrix to ``keys`` / ``vals`` as
    COO triples (flat index ``row·N + col``); return the right-hand side.

    Each element's KCL column and constitutive row (in the arbitrary-arity
    ``terms`` form or the a/b/c form), its diagonal ``c_j``, then every
    coupling, in the order the dense loop this replaced performed them; the
    right-hand side is zero at every node and ``e`` at each element. That
    loop subtracted ``kb`` where this emits ``-kb``; IEEE defines x − y as
    x + (−y), so the sums are the same bits.
    """
    rhs = np.zeros(N, dtype=np.complex128)
    for x, el in enumerate(elements):
        col = n + x
        row = col * N
        rhs[col] = el.e
        if el.terms is not None:
            # Arbitrary-arity form (issue #746): the a/b/c fields are not
            # consulted at all.
            for node, k, c_v in el.terms:
                keys += (node * N + col, row + node)
                vals += (k, c_v)  # k·j leaves this node
        else:
            if el.a is not None:
                keys += (el.a * N + col, row + el.a)
                vals += (el.ka, -el.c_v if el.c_va is None else el.c_va)
            if el.b is not None:
                keys += (el.b * N + col, row + el.b)
                vals += (-el.kb, el.c_v if el.c_vb is None else el.c_vb)
            if el.c is not None:
                keys += (el.c * N + col, row + el.c)
                vals += (el.kc, el.c_vc)
        keys.append(row + col)
        vals.append(el.c_j)
    # Mutual coupling between two Group-2 rows (issue #594): an
    # autotransformer's two winding sections share flux, so one branch
    # current appears in the OTHER's constitutive row; a chain-matrix line's
    # j₂ terms ride the same channel (issue #746).
    for i, k, z in couplings:
        keys.append((n + i) * N + n + k)
        vals.append(z)
    return rhs


def _densify(N, n, antenna, assign_antenna, keys, vals):
    """The ``N × N`` ndarray of the triples, summed in triple order.

    The antenna block goes first, as the first contribution to every entry it
    covers, over distinct nodes, so writing it as one block is its triples
    summed onto zero — except where the old dense code ASSIGNED it
    (``G[:n_real, :n_real] = Y_real``, no floating ports; ``assign_antenna``),
    which this repeats, because 0 + (−0) is +0 and an assignment keeps the −0.
    The same holds for each Group-2 diagonal, which the old code assigned
    (``A[col, col] = c_j``) as the first write to its entry: those start from
    −0, IEEE's exact additive identity (−0 + v is v for every v, signed zeros
    included). Measured to matter: without it 77 of the 257 byte-for-byte A/B
    cases against momwire move (a Transformer or FloatingBalun with no
    winding R, for one, has ``c_j = −0j``).

    Then every other triple: `np.add.at` is unbuffered and visits its indices
    in order, so each entry is ((s + v₁) + v₂) + …, the sequence of in-place
    adds the dense assembly used to perform (``tests/
    test_mna_unified_assembly.py`` holds that order: 1e16, 1, −1e16 on one
    entry sums to 0, not 1).
    """
    D = np.zeros((N, N), dtype=np.complex128)
    nodes, block = antenna
    if assign_antenna:
        k = len(nodes)
        D[:k, :k] = block
    elif len(nodes):
        D[np.ix_(nodes, nodes)] += block
    flat = D.reshape(-1)
    flat[n * N + n :: N + 1] = complex(-0.0, -0.0)
    np.add.at(flat, keys, vals)
    return D


def _csc(rows, cols, vals, N):
    """The ``N × N`` CSC matrix of COO triples, duplicates summed (AK#2241).
    The summation order here is SciPy's, not the triples'; nothing holds the
    sparse path to the dense one's bits, only to its answers."""
    import scipy.sparse as sp

    A = sp.coo_matrix((vals, (rows, cols)), shape=(N, N)).tocsc()
    A.sum_duplicates()
    A.eliminate_zeros()
    return A


def _refine(A, b, x, correct, itmax=5):
    """``zgerfs``'s iterative refinement of ``A x = b``: residual, correction
    through the existing factor, repeated while the componentwise backward
    error ``max_i |b − A x|_i / (|A| |x| + |b|)_i`` is above ε and still at
    least halving, at most ``itmax`` times (LAPACK's ITMAX). ``correct`` maps
    a residual to the correction, i.e. one solve with the factor."""
    eps = np.finfo(float).eps
    absA = abs(A)
    last = 3.0
    for _ in range(itmax):
        res = b - A @ x
        denom = absA @ np.abs(x) + np.abs(b)
        nz = denom > 0.0
        berr = float(np.max(np.abs(res[nz]) / denom[nz])) if np.any(nz) else 0.0
        if not (berr > eps and 2.0 * berr <= last):
            break
        x = x + correct(res)
        last = berr
    return x


# LAPACK's ``zlaqge`` thresholds: scale only when the factors spread by more
# than 10x, or the largest entry is near under- or overflow.
_EQU_THRESH = 0.1
_EQU_SMALL = np.finfo(float).tiny / np.finfo(float).eps
_EQU_LARGE = 1.0 / _EQU_SMALL


def _equilibrate(A):
    """Row and column scale factors of a CSC matrix, as ``zgesvx``'s
    ``fact="E"`` computes and applies them (``zgeequ`` then ``zlaqge``).

    ``zgeequ``: ``r_i = 1/max_j |a_ij|``, then ``c_j = 1/max_i r_i·|a_ij|``,
    with |·| the ``cabs1`` norm |Re| + |Im| LAPACK uses there. ``zlaqge``
    then applies the rows only if ``min r / max r`` (rowcnd) is below 0.1 or
    the largest entry is near under/overflow, and the columns only if colcnd
    is below 0.1; a factor not applied is returned as ones. That decision
    matters beyond speed: the reciprocal condition ``zgesvx`` reports is that
    of the system as scaled, so a path that always scaled both would report a
    different number (measured: up to 7x higher on the RLCG ladder, whose
    columns ``zlaqge`` leaves alone). ``None`` when a row or column is
    entirely zero, which is exact rank deficiency (``zgeequ``'s info > 0).
    """
    N = A.shape[0]
    mag = np.abs(A.data.real) + np.abs(A.data.imag)
    col_of = np.repeat(np.arange(N), np.diff(A.indptr))
    rmax = np.zeros(N)
    np.maximum.at(rmax, A.indices, mag)
    if N == 0 or not np.all(rmax > 0.0):
        return None
    rmax_c = np.minimum(np.maximum(rmax, _EQU_SMALL), _EQU_LARGE)
    r = 1.0 / rmax_c
    rowcnd = max(rmax.min(), _EQU_SMALL) / min(rmax.max(), _EQU_LARGE)
    amax = rmax.max()
    cmax = np.zeros(N)
    np.maximum.at(cmax, col_of, r[A.indices] * mag)
    if not np.all(cmax > 0.0):
        return None
    c = 1.0 / np.minimum(np.maximum(cmax, _EQU_SMALL), _EQU_LARGE)
    colcnd = max(cmax.min(), _EQU_SMALL) / min(cmax.max(), _EQU_LARGE)
    if rowcnd >= _EQU_THRESH and _EQU_SMALL <= amax <= _EQU_LARGE:
        r = np.ones(N)
    if colcnd >= _EQU_THRESH:
        c = np.ones(N)
    return r, c


def _inv_norm1_estimate(solve, solve_h, n):
    """Hager's estimate of ``‖A⁻¹‖₁`` as LAPACK's ``zlacn2`` computes it for
    ``zgecon`` (Higham's 1988 refinement, complex sign vectors, at most five
    iterations, then the alternating test vector), so a sparse solve reports
    the same quantity a dense ``zgesvx`` does. Deterministic, unlike
    ``scipy.sparse.linalg.onenormest``'s random starts: a threshold compared
    against it must give the same answer every run."""
    x = np.full(n, 1.0 / n, dtype=np.complex128)
    y = solve(x)
    if n == 1:
        return float(abs(y[0]))
    est = float(np.sum(np.abs(y)))

    def sign(v):
        a = np.abs(v)
        out = np.ones(n, dtype=np.complex128)
        nz = a > 0.0
        out[nz] = v[nz] / a[nz]
        return out

    z = solve_h(sign(y))
    j = int(np.argmax(np.abs(z)))
    for _it in range(2, 6):
        x = np.zeros(n, dtype=np.complex128)
        x[j] = 1.0
        y = solve(x)
        # LAPACK keeps the new (lower) value when it stops on cycling; so does
        # this, to report the number zgesvx would.
        est_old, est = est, float(np.sum(np.abs(y)))
        if est <= est_old:
            break
        z = solve_h(sign(y))
        j_last, j = j, int(np.argmax(np.abs(z)))
        if abs(z[j_last]) == abs(z[j]):
            break
    i = np.arange(n)
    x = ((-1.0) ** i * (1.0 + i / (n - 1))).astype(np.complex128)
    temp = 2.0 * float(np.sum(np.abs(solve(x)))) / (3.0 * n)
    return max(est, temp)


class MNASystem:
    """Assembled MNA system ``[[G, B], [Cᵀ, D]] · [v; j] = [i_ext; e]``.

    ``v`` — node voltages vs. the datum (one per port, real feeds first);
    ``j`` — Group-2 branch currents. ``i_ext`` is zero at every node (all
    external injections enter through Group-2 source branches).

    ``terminations`` maps a port node index → ``(column, value, kind,
    z_chain)`` for the per-port source/load termination branch (see
    ``NetworkReducer.apply_branches``); its current ``j[column]`` is the
    current the termination delivers INTO the node. Kind "v": value is
    the EMF and the driven impedance is ``emf / j[column] − z_ref_at[k]``;
    kind "i" (forced current, issue #442): value is the forced amps and the
    impedance is ``v_k / j[column] + z_chain``.

    ``A`` is a dense ndarray below `SPARSE_MIN_UNKNOWNS` and a
    ``scipy.sparse`` CSC matrix at and above it (AK#2241; ``sparse`` says
    which). Nothing in this package reads ``A`` but `solve`: the readouts,
    `branch_power` included, read the solution, ``terminations``,
    ``elements`` and ``probes``, all the same objects on either path.
    """

    def __init__(
        self,
        stamps,
        elements,
        terminations,
        probes=None,
        diagnose=None,
        couplings=(),
        z_ref=0j,
        z_ref_at=None,
    ):
        """``stamps`` is the `_MNAStamps` of the node block; the Group-2 half
        comes from ``elements`` and ``couplings``. Both paths assemble the
        same triples; only how they are summed differs."""
        self._init_common(elements, terminations, probes, diagnose, z_ref, z_ref_at)
        n = stamps.n
        N = n + len(elements)
        # Dense below the threshold, sparse at and above it; the unit is the
        # MNA dimension n + m.
        self.sparse = use_sparse(N)
        antenna, keys, vals, rhs = stamps.triples(
            elements, couplings, full_width=not self.sparse
        )
        if self.sparse:
            nd = np.asarray(antenna[0], dtype=np.int64)
            rows = np.concatenate([np.repeat(nd, len(nd)), keys // N])
            cols = np.concatenate([np.tile(nd, len(nd)), keys % N])
            avals = np.asarray(antenna[1], dtype=np.complex128).ravel()
            self.A = _csc(rows, cols, np.concatenate([avals, vals]), N)
        else:
            self.A = _densify(N, n, antenna, not stamps.floating, keys, vals)
        self.n_nodes = n
        self.rhs = rhs

    def _init_common(self, elements, terminations, probes, diagnose, z_ref, z_ref_at):
        self.terminations = terminations
        # The source impedance the DRIVEN terminations were stamped behind
        # (issue #746); 0 is the ideal generator. Readouts subtract it back
        # out, so nothing about the answers depends on the value. `z_ref_at`
        # is the per-node truth — an undriven, load-only termination gets
        # none, because a fictitious 50 Ω inside a real load chain would
        # change the design rather than reference it.
        self.z_ref = complex(z_ref)
        self.z_ref_at = dict(z_ref_at or {})
        self.elements = elements
        # (label, kind, payload) probes for the power budget (issue #299):
        # kind "group1" → payload (node_idx_list, stamped Y block);
        # kind "group2" → payload element index; kind "termination" →
        # payload node index (dissipation = the whole Load part of the
        # branch); kind "termination_share" → payload (node index, one
        # Load's impedance), that Load's share of the same branch.
        # `NetworkReducer` builds these as `_Probe`, a 3-tuple subclass that
        # also carries a structured `.key` (issue #956) — the arity stays 3
        # deliberately, because `branch_power` destructures all three
        # positions and antennaknobs' `tests/test_gamma_reference.py` reads
        # `system.probes[0]` and hands it straight back here. A hand-built
        # plain 3-tuple works everywhere `branch_power` is called directly;
        # only the budget readout wants the key.
        self.probes = probes or []
        # Called only when the solve goes singular, to name the branch that
        # did it (issue #647). A closure rather than stored state: the walk
        # costs nothing on the happy path, which is every path but one.
        self.diagnose = diagnose
        self._solution = None
        # The equilibrated system's reciprocal condition, once solved (either
        # path); read-only bookkeeping, nothing downstream depends on it.
        self.rcond = None

    def branch_power(self, label_kind_payload):
        """Time-average power in watts dissipated in one probed branch of
        the SOLVED system (issue #299). Group-1 stamps: ½·Re(v†·Y_br·v)
        over the branch's own stamped block (≈ 0 for a lossless TL, > 0
        for a lossy one). Group-2 elements: ½·Re((v_a − v_b)·j*), the drop
        across the element times its explicit branch current — exact in
        both impedance and admittance form, including shorts and opens.
        Terminations: ½·Re((E − v_k)·j*), the drop across the Load part
        (the EMF term is the port's input power, not dissipation); a
        forced-current termination's loads dissipate ½·Re(z_chain)·|j|²
        instead — the drop across the chain at the forced current.
        Termination shares: ½·Re(z_i)·|j|² for ONE Load of the chain
        (issue #956), at the current the whole chain carries. Series loads
        share one current, so the shares partition the chain's dissipation
        exactly — for a lone Load the share IS the drop above, since the
        stamp makes E − v_k = z_chain·j identically."""
        v, j = self.solve()
        label, kind, payload = label_kind_payload
        if kind == "group1":
            nodes, y_block = payload
            vb = v[nodes]
            # Upstream spells these products `_lapack.matmul`, momwire's seam
            # for a host process that publishes its own BLAS (the standalone
            # executables). With nothing published, which is every process
            # antennaknobs runs in, that seam IS `a @ b`; see the package
            # docstring.
            return 0.5 * float(np.real(np.conj(vb) @ (y_block @ vb)))
        if kind == "group2":
            el = self.elements[payload]
            va = 0j if el.a is None else v[el.a]
            vb = 0j if el.b is None else v[el.b]
            # Power absorbed = ½Re(v_a·(ka·j)* − v_b·(kb·j)* + v_c·(kc·j)*):
            # the element draws ka·j from node a, delivers kb·j into node b,
            # and draws kc·j from a third node c when present. Plain series
            # elements have ka = kb = 1 (the familiar (v_a − v_b)·j*); a
            # transformer's ratio-linked windings make it (v_a − n·v_b)·j*,
            # i.e. only the winding-resistance drop dissipates. A FloatingBalun
            # adds v_c·(−n·j)* on the primary node, so the ideal element's
            # absorbed power is exactly zero and only r·|j|² dissipates.
            i_a, i_b = el.ka * j[payload], el.kb * j[payload]
            p = va * np.conj(i_a) - vb * np.conj(i_b)
            if el.c is not None:
                p += v[el.c] * np.conj(el.kc * j[payload])
            return 0.5 * float(np.real(p))
        if kind == "group2abcd":
            # Chain-matrix 2-port (issue #746): power IN at port A minus power
            # OUT at port B, ½Re(v_a·j₁* − v_b·j₂*), with the port voltages
            # read through the same weights that distribute the port currents.
            # A lossless line reports ~0; a lossy one its attenuation. The
            # payload is a tuple of legs because a BalancedLine carrying a
            # common-mode path is TWO orthogonal 2-ports under one label.
            total = 0.0
            for i1, i2, port_a, port_b in payload:
                va = sum(w * v[node] for node, w in port_a)
                vb = sum(w * v[node] for node, w in port_b)
                total += 0.5 * float(np.real(va * np.conj(j[i1]) - vb * np.conj(j[i2])))
            return total
        if kind == "group2r":
            # Resistive dissipation ONLY (issue #594). The generic "group2"
            # probe reads ½Re((v_a − v_b)·j*), which for a mutually-coupled
            # winding also picks up the reactive power the two sections
            # exchange — real-valued, sloshing back and forth, and emphatically
            # not loss. Half of a lossless coupled pair would report positive
            # dissipation and the other half negative.
            idx, r = payload
            return 0.5 * float(r) * float(abs(j[idx])) ** 2
        if kind == "termination_share":
            # One Load's share of the termination branch it shares with the
            # source and any co-located Loads (issue #956). A non-finite z is
            # a trap at resonance: the chain is an open, the stamp forces
            # j = 0, and Re(inf)·0 is nan rather than the 0 W an open burns.
            node, z_load = payload
            col = self.terminations[node][0]
            if not np.isfinite(z_load):
                return 0.0
            return 0.5 * float(np.real(z_load)) * float(abs(j[col])) ** 2
        # termination: the Load part of the source/load branch at node k. The
        # z_ref the driven stamp sits behind is a modelling reference, not a
        # resistor in the design, so its share of the drop comes back out.
        col, e, tkind, z_chain = self.terminations[payload]
        if tkind == "i":
            return 0.5 * float(np.real(z_chain)) * float(abs(j[col])) ** 2
        drop = e - v[payload] - self.z_ref_at.get(payload, 0j) * j[col]
        return 0.5 * float(np.real(drop * np.conj(j[col])))

    def solve(self):
        """Solve once (cached); returns ``(v, j)``.

        Uses LAPACK's expert driver rather than a bare ``np.linalg.solve``,
        because the failure this guards against is usually not an exception
        (issue #647): a nearly-singular system answers with enormous,
        meaningless numbers and no complaint at all. That is worth catching
        for any cause — a floating subnetwork, contradictory sources, or the
        ideal-generator excitation the far-field path still uses.

        The subtlety is that a raw condition number is useless here. An MNA
        matrix mixes admittance rows with unit-valued constitutive rows, so a
        perfectly healthy network routinely spans twenty-plus orders of
        magnitude and "looks" singular to any unscaled estimate — the shipping
        `arrays.bowtie1x2_bl` reports 1e-16 that way while solving fine.
        ``zgesvx`` equilibrates first (``fact="E"``) and reports the condition
        of the *scaled* system, which is the number that means rank-deficient
        rather than badly-scaled: across every catalog design with a network,
        the worst healthy value measured is 2.4e-7, five orders above the
        threshold below.

        At and above `SPARSE_MIN_UNKNOWNS` the system is sparse and
        `_solve_sparse` does the same three things with SuperLU, to the same
        thresholds, the same message and the same `diagnose` (AK#2241).
        """
        if self._solution is None:
            if self.sparse:
                x, rcond, singular = self._solve_sparse()
            else:
                from scipy.linalg.lapack import zgesvx

                with warnings.catch_warnings():
                    # An exactly-singular factorization warns; we are about to
                    # raise a message that actually explains it.
                    warnings.simplefilter("ignore")
                    out = zgesvx(self.A, self.rhs.reshape(-1, 1))
                x, rcond, info = out[7], float(out[8]), int(out[11])
                n = self.A.shape[0]
                singular = 0 < info <= n
            self.rcond = rcond
            if singular or not np.isfinite(rcond) or rcond < RCOND_SINGULAR:
                detail = self.diagnose() if self.diagnose is not None else ""
                raise SingularNetworkError(
                    "the network has no finite solution at this frequency "
                    f"(reciprocal condition {rcond:.2e} after equilibration). "
                    "Every branch stamped fine on its own — the singularity is "
                    "in the assembled system." + (f"\n{detail}" if detail else "")
                )
            if rcond < RCOND_SUSPECT:
                _logger.warning(
                    "MNA solve is nearly singular (reciprocal condition %.2e): "
                    "the impedance is dominated by proximity to a pole and its "
                    "leading digits are unreliable.%s",
                    rcond,
                    ("\n" + self.diagnose()) if self.diagnose is not None else "",
                )
            x = np.asarray(x).reshape(-1)
            self._solution = (x[: self.n_nodes], x[self.n_nodes :])
        return self._solution

    def _solve_sparse(self):
        """``(x, rcond, singular)`` by SuperLU, keeping `solve`'s guarantees.

        The three steps ``zgesvx`` performs, on a CSC matrix:

        1. equilibrate as ``zgeequ`` computes the factors and ``zlaqge``
           decides which to apply (`_equilibrate`), so the condition below is
           that of the system ``zgesvx`` would have scaled;
        2. factor and solve the scaled system with ``splu`` (COLAMD column
           order, partial pivoting), and unscale: x = c · (As⁻¹ (r · rhs));
        3. estimate the scaled system's reciprocal condition as ``zgecon``
           does, 1/(‖As‖₁ · est ‖As⁻¹‖₁), with the same Hager iteration
           (`_inv_norm1_estimate`) over the factor's solves.

        Then ``zgerfs``'s iterative refinement (`_refine`), as ``zgesvx``
        follows its solve with, so the answer carries the same guarantee: a
        componentwise backward error at ε. It cannot make the two paths agree
        beyond the problem's own conditioning. On ``arrays.bowtie1x2_bl``
        (rcond 8e-7; its floating gaps' common mode is pinned only through
        1e8 Ω shunts) both answers have backward error 1.3-1.5e-16, and its
        excited node voltages still differ by 5.7e-11 of the largest: the
        dense answer happens to sit on a 40-digit solve, the sparse one κ·ε
        from it, before refinement and after. Its Z, Γ, p_in and budget meet
        the 1e-12 every other catalog row does (worst 1.2e-14 across them).

        An all-zero row or column, or a factor SuperLU calls exactly
        singular, is ``zgesvx``'s info > 0, reported with rcond 0.
        """
        import scipy.sparse as sp
        import scipy.sparse.linalg as spla

        A = self.A
        N = A.shape[0]
        nothing = np.zeros(N, dtype=np.complex128)
        scale = _equilibrate(A)
        if scale is None:
            return nothing, 0.0, True
        r, c = scale
        As = sp.csc_matrix(
            (
                A.data * r[A.indices] * np.repeat(c, np.diff(A.indptr)),
                A.indices,
                A.indptr,
            ),
            shape=A.shape,
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                lu = spla.splu(As)
        except RuntimeError:
            # "Factor is exactly singular".
            return nothing, 0.0, True
        with warnings.catch_warnings(), np.errstate(all="ignore"):
            warnings.simplefilter("ignore")
            x = c * lu.solve(r * self.rhs)
            x = _refine(A, self.rhs, x, lambda res: c * lu.solve(r * res))
            anorm = float(np.max(np.asarray(abs(As).sum(axis=0)).ravel()))
            ainv = _inv_norm1_estimate(lu.solve, lambda v: lu.solve(v, trans="H"), N)
            rcond = 0.0 if ainv == 0.0 or anorm == 0.0 else (1.0 / ainv) / anorm
        return x, float(rcond), False


def poison_singular_sample(fn, *args, where="", **kwargs):
    """Run a per-frequency reduction, returning NaNs if it is singular (#647).

    A sweep is a series of independent questions, and one of them landing on a
    topology with no solution is no reason to lose the answers to the other
    forty. (Issue #746 removed the lossless-line poles that used to be the
    common cause; what is left is genuine rank deficiency — a node reachable
    only through opens — which no frequency shift dissolves, so a whole sweep
    of a broken design now poisons every sample rather than one.) The bad
    sample becomes NaN — which the web adapter already
    converts to its ``Z_OPEN_OHMS`` JSON sentinel, and which every plotting
    path already skips — and the reason is logged once, with the same
    attribution a single-point solve would have raised.

    Deliberately NOT applied to a single-point ``impedance()``: someone who
    asked about one frequency should get the message, not a silent NaN.
    """
    try:
        return fn(*args, **kwargs)
    except SingularNetworkError as e:
        _logger.warning("singular network%s — this sample is NaN.\n%s", where, e)
        return None
