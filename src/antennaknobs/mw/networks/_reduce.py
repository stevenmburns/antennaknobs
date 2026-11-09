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
    """

    def __init__(
        self,
        G,
        elements,
        terminations,
        probes=None,
        diagnose=None,
        couplings=(),
        z_ref=0j,
        z_ref_at=None,
    ):
        n = G.shape[0]
        m = len(elements)
        A = np.zeros((n + m, n + m), dtype=np.complex128)
        A[:n, :n] = G
        rhs = np.zeros(n + m, dtype=np.complex128)
        for x, el in enumerate(elements):
            col = n + x
            if el.terms is not None:
                # Arbitrary-arity form (issue #746): the a/b/c fields are not
                # consulted at all.
                for node, k, c_v in el.terms:
                    A[node, col] += k  # k·j leaves this node
                    A[col, node] += c_v
            else:
                if el.a is not None:
                    A[el.a, col] += el.ka  # ka·j leaves node a
                    A[col, el.a] += -el.c_v if el.c_va is None else el.c_va
                if el.b is not None:
                    A[el.b, col] -= el.kb  # kb·j enters node b
                    A[col, el.b] += el.c_v if el.c_vb is None else el.c_vb
                if el.c is not None:
                    A[el.c, col] += el.kc  # kc·j leaves node c (third terminal)
                    A[col, el.c] += el.c_vc
            A[col, col] = el.c_j
            rhs[col] = el.e
        # Mutual coupling between two Group-2 rows (issue #594): an
        # autotransformer's two winding sections share flux, so one branch
        # current appears in the OTHER's constitutive row. Every other element
        # here is diagonal in the branch-current block; this is the only term
        # that is not.
        for i, k, z in couplings:
            A[n + i, n + k] += z
        self.n_nodes = n
        self.A = A
        self.rhs = rhs
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
        """
        if self._solution is None:
            from scipy.linalg.lapack import zgesvx

            with warnings.catch_warnings():
                # An exactly-singular factorization warns; we are about to
                # raise a message that actually explains it.
                warnings.simplefilter("ignore")
                out = zgesvx(self.A, self.rhs.reshape(-1, 1))
            x, rcond, info = out[7], float(out[8]), int(out[11])
            n = self.A.shape[0]
            if (0 < info <= n) or not np.isfinite(rcond) or rcond < RCOND_SINGULAR:
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
