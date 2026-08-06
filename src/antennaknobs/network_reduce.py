"""Engine-agnostic reduction of a port-based `Network` spec to driven-port
impedances, on top of a raw multiport antenna admittance matrix.

Both MomwireEngine and PyNECEngine assemble the antenna's short-circuit Y at
the real (`PortOnWire`) ports, then hand it here with a port-name -> matrix-
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
import math
import warnings
from dataclasses import dataclass

import numpy as np

from .network import (
    TL,
    Admittance,
    Autotransformer,
    BalancedLine,
    Driven,
    DrivenCurrent,
    FloatingBalun,
    Load,
    PortOnWire,
    PortOnWireFloating,
    Shunt,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    _parallel_rlc_admittance,
    _series_rlc_impedance,
    load_impedance,
    load_series_admittance,
)

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


def _tl_gamma_l(length, wavelength, vf, k1, k2):
    """Complex propagation γ·length = (α + jβ)·length.

    β = 2π/(vf·λ); α comes from the cable-table matched-loss model
    k1·√f_MHz + k2·f_MHz in dB per 100 ft (see `network.TL`). Shared by the
    admittance and chain-matrix forms so the two can never disagree about
    what line they describe.
    """
    beta = 2.0 * np.pi / (vf * wavelength)
    f_mhz = C_LIGHT / wavelength / 1e6
    loss_db_per_100ft = k1 * np.sqrt(f_mhz) + k2 * f_mhz
    alpha = loss_db_per_100ft * NEPER_PER_DB * FEET_PER_M / 100.0  # nepers/m
    return (alpha + 1j * beta) * length


def tl_abcd(z0, length, wavelength, vf=1.0, k1=0.0, k2=0.0):
    """Ideal-TL chain (ABCD) matrix ``(A, B, C, D)`` — the reducer's stamp
    (issue #746).

        [v_a; i_a] = [[cosh γl, Z0 sinh γl], [sinh γl / Z0, cosh γl]] · [v_b; i_b]

    with i_a into port A and i_b out of port B. Every entry is an entire
    function of γl, so unlike `tl_admittance_2x2` — the same line, written as
    the ratio 1/(Z0 sinh γl) — this has no pole anywhere: at the lossless
    k·λ/2 point it is exactly [[±1, 0], [0, ±1]], the through-line the
    admittance description cannot spell because its currents are unconstrained
    by its voltages there. That is the whole reason the reducer carries two
    Group-2 currents per line instead of a 2×2 Group-1 block.

    A crossed ("half-twist") line is NOT a flag here: it is port B's weights
    negated where the pair is stamped, which is what a polarity inversion is.
    """
    gl = _tl_gamma_l(length, wavelength, vf, k1, k2)
    sh, ch = np.sinh(gl), np.cosh(gl)
    return ch, z0 * sh, sh / z0, ch


def tl_admittance_2x2(z0, length, wavelength, transposed=False, vf=1.0, k1=0.0, k2=0.0):
    """Ideal-TL nodal admittance between its two terminals — lossless or
    lossy (issue #297).

    No longer what the reducer stamps (issue #746 moved that to `tl_abcd`);
    kept as the closed-form 2×2 that composition oracles and the balanced
    4×4's even/odd decomposition are written against.

    For complex propagation γl = (α + jβ)·length with β = 2π/(vf·λ):
        Y_TL = 1/(Z0 sinh γl) · [[cosh γl, -1], [-1, cosh γl]]
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
    gl = _tl_gamma_l(length, wavelength, vf, k1, k2)
    sh, ch = np.sinh(gl), np.cosh(gl)
    if abs(sh) < 1e-12:
        f_mhz = C_LIGHT / wavelength / 1e6
        raise SingularNetworkError(
            f"lossless TL length {length} is ~k·vf·λ/2 at "
            f"f={f_mhz:.4f} MHz (sinh γl ≈ 0); the admittance is singular "
            "there because the line has no admittance matrix at all — ask for "
            "its chain matrix (`tl_abcd`) instead, which is what the reducer "
            "stamps and which stays finite"
        )
    scale = 1.0 / (z0 * sh)
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
    zdiff, length, wavelength, vf=1.0, k1=0.0, k2=0.0, zcomm=None
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
    y2 = tl_admittance_2x2(zdiff, length, wavelength, vf=vf, k1=k1, k2=k2)
    y4 = np.kron(y2, _DIFF_INCIDENCE)
    if zcomm is not None:
        yc = tl_admittance_2x2(zcomm, length, wavelength, vf=vf, k1=k1, k2=k2)
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


def _series_group2(a, b, r, l, c, omega, emf=0j, ql=None, qc=None):
    """Group-2 stamp of a series R + jωL + 1/(jωC) (+ optional EMF) between
    nodes a and b. A 0 F capacitor is an open in the series path (infinite
    reactance) → admittance form with y = 0 (the branch carries no current).
    Every other value combination has finite z — including the ideal short
    z = 0 (0 Ω, 0 H, all-omitted, or exact series-LC resonance), which the
    old admittance-only stamps had to raise on. `ql`/`qc` add the finite-Q
    component losses (issue #298, see `network._series_rlc_impedance`)."""
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
        # payload node index (dissipation = the Load part of the branch).
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
        instead — the drop across the chain at the forced current."""
        v, j = self.solve()
        label, kind, payload = label_kind_payload
        if kind == "group1":
            nodes, y_block = payload
            vb = v[nodes]
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


class NetworkReducer:
    """Stamps a `Network`'s branches and sources into an MNA system on top
    of the raw real-port antenna Y and reads out driven-port impedances,
    physical port voltages, and the power bookkeeping.

    Construct with the network spec, a ``port_to_idx`` mapping every port
    name (real and virtual) to its row/column in the node space, and
    ``n_total_ports`` (real feeds + virtual ports). Real ports must occupy
    indices ``0..n_real-1`` in the same order as the raw Y handed to
    :meth:`apply_branches`; virtual ports come after.
    """

    def __init__(self, network, port_to_idx, n_total_ports):
        self.network = network
        self.port_to_idx = dict(port_to_idx)
        self.n_total_ports = n_total_ports

        # Floating gap ports: the antenna Y row still lives at the port's
        # existing index (that node becomes the "+" terminal), and the "-"
        # terminal gets a freshly appended node instead of being bonded to the
        # datum. Both are exposed as dotted sub-nodes, so every branch keeps
        # resolving through port_to_idx unchanged.
        self._floating = {}
        next_node = n_total_ports
        for name, port in network.ports.items():
            if isinstance(port, PortOnWireFloating):
                p_idx = self.port_to_idx[name]
                self._floating[name] = (p_idx, next_node)
                self.port_to_idx[f"{name}.p"] = p_idx
                self.port_to_idx[f"{name}.n"] = next_node
                next_node += 1
        self.n_nodes = next_node
        for src in network.sources:
            if src.port in self._floating:
                raise NotImplementedError(
                    f"source on floating gap port {src.port!r}: drive it through "
                    f"the network instead (a branch across {src.port}.p / "
                    f"{src.port}.n), or use a plain PortOnWire"
                )

        # 0-based driven port indices, with per-source kind: "v" for a
        # Driven voltage source (value = EMF), "i" for a DrivenCurrent
        # forced-current source (value = amps into the node, issue #442).
        self.driven_port_idx = []
        self.driven_voltages = []  # voltage sources only (legacy view)
        self._source_kinds = []
        self._source_values = []
        for src in network.sources:
            if isinstance(src, Driven):
                kind, value = "v", complex(src.voltage)
                self.driven_voltages.append(value)
            elif isinstance(src, DrivenCurrent):
                kind, value = "i", complex(src.current)
            else:
                raise NotImplementedError(f"unknown source type: {src!r}")
            self.driven_port_idx.append(port_to_idx[src.port])
            self._source_kinds.append(kind)
            self._source_values.append(value)

    @property
    def n_driven(self):
        return len(self.driven_port_idx)

    def _open_ended_nodes(self):
        """Node indices that only one branch terminal touches.

        An open stub is spelled as the *absence* of a termination — a `TL`
        into a private node nothing else uses (see ``station.shunt_open_stub``)
        — so "TL with a dangling far end" is how an open stub is recognised
        here, and the same walk finds any accidentally-unterminated line.
        """
        degree = {}
        for br in self.network.branches:
            for name in getattr(br, "__dataclass_fields__", {}):
                if name in ("a", "b", "c", "a1", "a2", "b1", "b2", "port", "line"):
                    node = getattr(br, name, None)
                    if isinstance(node, str) and node in self.port_to_idx:
                        idx = self.port_to_idx[node]
                        degree[idx] = degree.get(idx, 0) + 1
        # A real feed node is never "open" however few branches touch it: the
        # antenna's own dense Y ties it to every other feed. Only a virtual
        # node can dangle, so real ports and driven ports are excluded.
        real = {
            self.port_to_idx[name]
            for name, port in self.network.ports.items()
            if isinstance(port, PortOnWire) and name in self.port_to_idx
        }
        driven = set(self.driven_port_idx)
        return {
            idx
            for idx, deg in degree.items()
            if deg == 1 and idx not in driven and idx not in real
        }

    def _singularity_report(self, wavelength):
        """Which branch drove the system singular at this wavelength (#647).

        Attribution rather than a bare "matrix is singular": a lossless line
        is singular at a *specific* electrical length, so the walk asks each
        lossless line how close it sits to its own pole — an odd λ/4 for one
        hanging open (Z_in = 0, a dead short across the port it hangs on).
        Anything with real loss is skipped, because loss is what regularises
        it, and that is also the remedy the message recommends.

        Issue #746 narrowed this to one caller and one branch. The k·λ/2 half
        of the walk is gone: a line between two live nodes is stamped as its
        chain matrix now, finite at every length. The odd-λ/4 half survives
        because the EXCITED path keeps the ideal generator, which still cannot
        drive the dead short an open stub puts across the feed — so when this
        text appears it is a far-field / power-budget solve talking, and the
        impedance of that same design is a perfectly good Z = 0.
        """
        f_mhz = C_LIGHT / wavelength / 1e6
        open_nodes = self._open_ended_nodes()
        suspects = []
        for br, path in zip(
            self.network.branches,
            self.network.branch_paths or [""] * len(self.network.branches),
        ):
            if isinstance(br, TL):
                z0, vf, k1, k2 = br.z0, br.vf, br.k1, br.k2
                ends = (br.a, br.b)
            elif isinstance(br, BalancedLine):
                z0, vf, k1, k2 = br.zdiff, br.vf, br.k1, br.k2
                ends = (br.a1, br.b1)
            else:
                continue
            if k1 or k2:
                continue  # a lossy line has no pole to sit on
            hanging = any(
                self.port_to_idx.get(e) in open_nodes
                for e in ends
                if isinstance(e, str)
            )
            if not hanging:
                continue
            wl_line = wavelength * vf
            n_half = br.length / (0.5 * wl_line)  # length in half-wavelengths
            # Odd quarter-waves: n_half at an odd multiple of 0.5.
            if abs(n_half % 1.0 - 0.5) < 0.02:
                name = f"{path[:-1]}: " if path else ""
                suspects.append(
                    f"  {name}open-ended line {'→'.join(str(e) for e in ends)} "
                    f"is {n_half / 2:.4f} λ at {f_mhz:.4f} MHz — an odd "
                    "multiple of λ/4, where an open stub's Z_in = 0 shorts "
                    f"the port it hangs on (z0 = {z0:g} Ω), which no IDEAL "
                    "source can drive — the impedance of this same design is "
                    "a perfectly ordinary Z = 0"
                )
        if not suspects:
            return (
                "No lossless line sits on a pole at this frequency, so the "
                "cause is elsewhere in the topology — a node reachable only "
                "through open-circuited branches, or two ideal sources in "
                "contradiction."
            )
        return (
            "Suspect:\n"
            + "\n".join(suspects)
            + "\nGive the line the loss it really has (k1/k2, or cable=...): "
            "any real attenuation moves the pole off the real axis and the "
            "excitation becomes well-posed."
        )

    def _reference_node(self):
        """The one port node a ``z_ref`` may be stamped behind, or ``None``.

        A reference plane is a one-port idea: it needs the rest of the network,
        seen from this port, to be PASSIVE. Then moving the generator behind an
        impedance changes the operating point but not the ratio, and
        Z = E/j − z_ref is exactly the ideal generator's answer.

        A second *active* source breaks that, and not subtly. With two voltage
        generators, port 0's mutual term y01·E1 is a current injection fixed
        independently of v0, so any source impedance at port 0 changes v0/i0
        itself — measured 23 % on the two-source fixture in test_network_mna.
        A `DrivenCurrent` elsewhere does the same. This package's contract is
        the classical driven-array Z_k = V_k/I_k at the ideal operating point,
        so a network with more than one active source keeps the ideal stamp
        and converts Γ from Z the way `sweep` already does.

        A source at exactly 0 V is not active: `Driven(port, 0)` is the datum
        trick, a hard V = 0 pin, and it leaves the rest passive. It also never
        gets the reference itself — with no EMF there is no incident wave, so
        its Γ is undefined rather than badly conditioned.
        """
        active = [
            (k, kind)
            for k, kind, val in zip(
                self.driven_port_idx, self._source_kinds, self._source_values
            )
            if val != 0
        ]
        if len(active) != 1 or active[0][1] != "v":
            return None
        return active[0][0]

    def apply_branches(self, Y_real, wavelength, *, z_ref=0j):
        """Stamp the antenna Y and every network branch into one MNA system.

        ``z_ref`` is the source impedance the driven port's EMF sits behind
        (issue #746). The default 0 is the historical ideal generator, which
        the excited / far-field path keeps because its port voltages ARE the
        excitation; the impedance and Γ paths pass ``Z_REF_DEFAULT``. See
        :meth:`excited_state` for why the two solves are separate and
        :meth:`_reference_node` for the one network shape it applies to — a
        request to reference a network that has no reference plane is honored
        as "quote Γ against this z0", not stamped.

        Group 1 (node-admittance block G):
          - the antenna's dense multiport short-circuit Y at the real-feed
            nodes vs. datum;
          - parallel-mode Shunt (the tank admittance is the natural finite
            quantity, → 0 at trap resonance).

        Group 2 (auxiliary branch currents):
          - TwoPort and series-mode Shunt — series elements, exact for the
            ideal short z = 0 and the 0 F open;
          - TL and BalancedLine as chain-matrix 2-ports, two currents each
            (issue #746): every entry of an ABCD matrix is entire, so the
            k·λ/2 line that has no admittance matrix at all stamps as the
            ordinary through-line it is;
          - one TERMINATION branch per port that is driven and/or loaded:
            an EMF (0 if undriven) in series with the port's Load impedance
            (0 if unloaded) from the datum into the node. Its constitutive
            row v_k + (z_ref + Z_L)·j = E is the Thevenin boundary condition,
            and its current j is the delivered port current — so the
            driven-point impedance E/j − z_ref and the load dissipation
            (E − v_k − z_ref·j)·j* both read off the solution. With the
            ideal-generator z_ref = 0 a driven-only port (Z_L = 0) degenerates
            to the voltage-source pin v_k = E; loaded-only ports (E = 0) to
            the series load termination v_k = −Z_L·j. A `Load` is thus a
            series impedance between the antenna gap and the common return,
            matching NEC2's ld_card physics.

        Ports that are neither driven, loaded, nor touched by a branch keep
        plain KCL with zero injection (the floating I_ext = 0 condition).
        """
        omega = 2.0 * np.pi * C_LIGHT / wavelength
        couplings: list[tuple[int, int, complex]] = []
        n = self.n_nodes
        G = np.zeros((n, n), dtype=np.complex128)
        n_real = Y_real.shape[0]
        if self._floating:
            # Port incidence: gap row i drives node i positively, and a
            # floating port also drives its "-" node negatively. The stamp is
            # the congruence AᵀYA — the same [[1,-1],[-1,1]] structure
            # BalancedLine uses, generalized over the whole multiport. With no
            # floating ports A is the identity block and this reduces exactly
            # to the historical G[:n_real, :n_real] = Y_real.
            A = np.zeros((n_real, n), dtype=np.complex128)
            A[np.arange(n_real), np.arange(n_real)] = 1.0
            for p_idx, n_idx in self._floating.values():
                A[p_idx, n_idx] = -1.0
            G += A.T @ Y_real @ A
        else:
            G[:n_real, :n_real] = Y_real

        elements = []
        loads_by_node = {}
        probes = []
        # Instance paths (issue #489): branch_paths aligns with branches
        # ("" for top-level). Budget labels get a "tuner1: " prefix and the
        # instance's own namespace stripped from its port names, so a
        # composite's rows group under its instance name.
        branch_paths = getattr(self.network, "branch_paths", None) or [""] * len(
            self.network.branches
        )
        for br, _bpath in zip(self.network.branches, branch_paths):
            _short = lambda n, p=_bpath: n[len(p) :] if p and n.startswith(p) else n  # noqa: E731
            lab = lambda s, p=_bpath: f"{p[:-1]}: {s}" if p else s  # noqa: E731
            if isinstance(br, TL):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                leg = _stamp_abcd(
                    elements,
                    couplings,
                    [(a, 1.0 + 0j)],
                    [(b, -1.0 + 0j if br.transposed else 1.0 + 0j)],
                    tl_abcd(br.z0, br.length, wavelength, vf=br.vf, k1=br.k1, k2=br.k2),
                )
                probes.append(
                    (lab(f"TL {_short(br.a)}→{_short(br.b)}"), "group2abcd", (leg,))
                )
            elif isinstance(br, BalancedLine):
                # Balanced 4-terminal line (issues #575/#576/#746): the same
                # even/odd decomposition `balanced_admittance_4x4` writes as a
                # 4×4 Group-1 block, stamped instead as one chain-matrix
                # 2-port per mode. The differential mode's port weights
                # (+1, −1) force I(a1) = −I(a2) at each end, so with
                # `zcomm=None` the common mode remains STRUCTURALLY open
                # (rank 2) exactly as before — that is a topological property
                # of the incidence, not of which description carries it.
                a1, a2, b1, b2 = (
                    self.port_to_idx[p] for p in (br.a1, br.a2, br.b1, br.b2)
                )
                kw = dict(vf=br.vf, k1=br.k1, k2=br.k2)
                legs = [
                    _stamp_abcd(
                        elements,
                        couplings,
                        [(a1, 1.0 + 0j), (a2, -1.0 + 0j)],
                        [(b1, 1.0 + 0j), (b2, -1.0 + 0j)],
                        tl_abcd(br.zdiff, br.length, wavelength, **kw),
                    )
                ]
                if br.zcomm is not None:
                    # The pair driven as ONE conductor: voltage the pair
                    # average, current the total, splitting equally. Its
                    # ½-weights annihilate differential vectors, so the two
                    # legs never cross-couple.
                    legs.append(
                        _stamp_abcd(
                            elements,
                            couplings,
                            [(a1, 0.5 + 0j), (a2, 0.5 + 0j)],
                            [(b1, 0.5 + 0j), (b2, 0.5 + 0j)],
                            tl_abcd(br.zcomm, br.length, wavelength, **kw),
                        )
                    )
                probes.append(
                    (
                        lab(
                            f"BalancedLine {_short(br.a1)},{_short(br.a2)}"
                            f"→{_short(br.b1)},{_short(br.b2)}"
                        ),
                        "group2abcd",
                        tuple(legs),
                    )
                )
            elif isinstance(br, Admittance):
                # Fixed complex Y stamped verbatim — no ω scaling, no auxiliary
                # current (issue #416). A pure node-admittance block, exactly
                # like TL's 2×2 and the parallel Shunt's 1×1.
                idxs = [self.port_to_idx[p] for p in br.ports]
                yb = np.array(br.y, dtype=np.complex128)
                G[np.ix_(idxs, idxs)] += yb
                probes.append(
                    (
                        lab(f"Admittance {'→'.join(map(_short, br.ports))}"),
                        "group1",
                        (idxs, yb),
                    )
                )
            elif isinstance(br, TouchstoneLoad):
                # Measured 1-port (.s2p→.s1p) as a node-to-datum admittance
                # (issue #593): y = 1/Z(f) interpolated from the file, stamped
                # verbatim like a 1-port Admittance / parallel Shunt.
                k = self.port_to_idx[br.port]
                yb = br.data.y_at(C_LIGHT / wavelength)
                G[k, k] += yb[0, 0]
                probes.append(
                    (
                        lab(f"Touchstone {_short(br.port)}"),
                        "group1",
                        ([k], np.array([[yb[0, 0]]])),
                    )
                )
            elif isinstance(br, TouchstoneTwoPort):
                # Measured 2-port (.s2p) as an in-line 2×2 admittance block
                # (issue #593): [S](f)→[Y](f) interpolated from the file, stamped
                # like TL's 2×2 — a characterized balun / coax / filter black box.
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                yb = br.data.y_at(C_LIGHT / wavelength)
                G[np.ix_([a, b], [a, b])] += yb
                probes.append(
                    (
                        lab(f"Touchstone {_short(br.a)}→{_short(br.b)}"),
                        "group1",
                        ([a, b], yb),
                    )
                )
            elif isinstance(br, TwoPort):
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                probes.append(
                    (
                        lab(f"TwoPort {_short(br.a)}→{_short(br.b)}"),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _series_group2(a, b, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc)
                )
            elif isinstance(br, Shunt):
                k = self.port_to_idx[br.port]
                if br.parallel:
                    y_sh = _parallel_rlc_admittance(
                        br.r, br.l, br.c, omega, br.ql, br.qc
                    )
                    G[k, k] += y_sh
                    probes.append(
                        (
                            lab(f"Shunt {_short(br.port)}"),
                            "group1",
                            ([k], np.array([[y_sh]])),
                        )
                    )
                else:
                    probes.append(
                        (lab(f"Shunt {_short(br.port)}"), "group2", len(elements))
                    )
                    elements.append(
                        _series_group2(
                            k, None, br.r, br.l, br.c, omega, ql=br.ql, qc=br.qc
                        )
                    )
            elif isinstance(br, Transformer):
                if br.n == 0:
                    raise ValueError(
                        f"Transformer {br.a!r}→{br.b!r} has turns ratio n = 0; "
                        "no physical transformer pins one winding at 0 V while "
                        "open-circuiting the other"
                    )
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                nr = complex(br.n)
                z_w = complex(br.r) if br.r is not None else 0j
                # Ideal ratio + winding R referred to side a: the auxiliary
                # current j is i_a (into winding A); KCL carries j out of a
                # and n·j into b; constitutive row v_a − n·v_b − r_w·j = 0.
                probes.append(
                    (
                        lab(f"Transformer {_short(br.a)}→{_short(br.b)}"),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _Group2Element(
                        a,
                        b,
                        c_v=0j,
                        c_j=-z_w,
                        e=0j,
                        ka=1.0 + 0j,
                        kb=nr,
                        c_va=1.0 + 0j,
                        c_vb=-nr,
                    )
                )
                zl = magnetizing_impedance(br, omega)
                if zl is not None:
                    y_mag = 1.0 / zl
                    G[a, a] += y_mag
                    probes.append(
                        (
                            lab(f"Transformer {_short(br.a)}→{_short(br.b)} (mag)"),
                            "group1",
                            ([a], np.array([[y_mag]])),
                        )
                    )
            elif isinstance(br, Autotransformer):
                if not 0.0 <= br.k <= 1.0:
                    raise ValueError(
                        f"Autotransformer {br.a!r}→{br.b!r} has k = {br.k}; "
                        "coupling must be 0 ≤ k ≤ 1. Above 1 the inductance "
                        "matrix is not positive semi-definite (M² > L₁L₂) and "
                        "the winding pair would deliver more energy than it "
                        "stores — the power budget would stop balancing"
                    )
                if br.l_lower <= 0 or br.l_upper <= 0:
                    raise ValueError(
                        f"Autotransformer {br.a!r}→{br.b!r} needs positive "
                        f"section inductances; got {br.l_lower} / {br.l_upper} H"
                    )
                a_i, b_i = self.port_to_idx[br.a], self.port_to_idx[br.b]
                # Series r per section from the shared finite-Q convention.
                r1 = omega * br.l_lower / br.ql if br.ql else 0.0
                r2 = omega * br.l_upper / br.ql if br.ql else 0.0
                z1 = r1 + 1j * omega * br.l_lower
                z2 = r2 + 1j * omega * br.l_upper
                zm = 1j * omega * br.k * math.sqrt(br.l_lower * br.l_upper)
                # Both branch currents are referenced UP the winding: j1 runs
                # datum → tap (its "a side" is the datum, absent from the node
                # space), j2 runs tap → top. Each therefore enters its section
                # at the lower terminal, so the passive-sign voltage is
                #   (v_datum − v_tap) = z1·j1 + zm·j2
                #   (v_tap   − v_top) = zm·j1 + z2·j2
                # — the node potential is the NEGATIVE of the voltage across
                # the element for j1, which is where a sign slip would hide.
                # Same reference direction up the coil ⇒ flux adds ⇒ +zm.
                i1, i2 = len(elements), len(elements) + 1
                lo = lab(f"Autotransformer {_short(br.a)}→{_short(br.b)} (lower)")
                hi = lab(f"Autotransformer {_short(br.a)}→{_short(br.b)} (upper)")
                probes.append((lo, "group2r", (i1, r1)))
                probes.append((hi, "group2r", (i2, r2)))
                elements.append(_Group2Element(None, a_i, c_v=1.0 + 0j, c_j=z1, e=0j))
                elements.append(_Group2Element(a_i, b_i, c_v=1.0 + 0j, c_j=z2, e=0j))
                # v_a = z1·j1 + zm·j2 and v_b − v_a = zm·j1 + z2·j2: the
                # off-diagonal pair that makes this one winding, not two.
                couplings.append((i1, i2, zm))
                couplings.append((i2, i1, zm))
            elif isinstance(br, FloatingBalun):
                if br.n == 0:
                    raise ValueError(
                        f"FloatingBalun {br.primary!r}→({br.a!r},{br.b!r}) has "
                        "turns ratio n = 0; no physical balun pins the secondary "
                        "differential voltage at 0 V"
                    )
                p = self.port_to_idx[br.primary]
                a, b = self.port_to_idx[br.a], self.port_to_idx[br.b]
                nr = complex(br.n)
                z_w = complex(br.r) if br.r is not None else 0j
                # Floating secondary (a, b) + single-ended primary p. The
                # auxiliary current j is the secondary current (into a, out of
                # b): KCL carries j out of a, j into b, and −n·j out of the
                # primary p (reciprocity pins the primary coeff = c_vc, so the
                # ideal element absorbs zero net power for any n). The
                # constitutive row v_a − v_b − n·v_p = r_w·j refers the winding
                # R to the secondary; the ideal element is lossless.
                probes.append(
                    (
                        lab(
                            f"FloatingBalun {_short(br.primary)}→"
                            f"({_short(br.a)},{_short(br.b)})"
                        ),
                        "group2",
                        len(elements),
                    )
                )
                elements.append(
                    _Group2Element(
                        a,
                        b,
                        c_v=0j,
                        c_j=-z_w,
                        e=0j,
                        ka=1.0 + 0j,
                        kb=1.0 + 0j,
                        c_va=1.0 + 0j,
                        c_vb=-1.0 + 0j,
                        c=p,
                        kc=-nr,
                        c_vc=-nr,
                    )
                )
                zl = magnetizing_impedance(br, omega)
                if zl is not None:
                    y_mag = 1.0 / zl
                    G[p, p] += y_mag
                    probes.append(
                        (
                            lab(
                                f"FloatingBalun {_short(br.primary)}→"
                                f"({_short(br.a)},{_short(br.b)}) (mag)"
                            ),
                            "group1",
                            ([p], np.array([[y_mag]])),
                        )
                    )
            elif isinstance(br, Load):
                if not isinstance(self.network.ports[br.port], PortOnWire):
                    raise ValueError(
                        f"Load on virtual port {br.port!r}: a Load is a series "
                        "impedance on an antenna segment, which only PortOnWire has"
                    )
                loads_by_node.setdefault(self.port_to_idx[br.port], []).append(br)
            else:
                raise NotImplementedError(f"branch type {type(br).__name__}")

        # Per-port termination branches. A port may carry BOTH a source and
        # a series load (the centre-loaded driven short dipole); they chain
        # into one branch: datum —EMF—Z_L→ node. Termination tuples are
        # (column, source value, kind, z_chain): kind "v" is the Thevenin
        # branch below, kind "i" a forced-current branch (issue #442).
        emf, forced = {}, {}
        for k, kind, val in zip(
            self.driven_port_idx, self._source_kinds, self._source_values
        ):
            if kind == "v":
                emf[k] = val
            else:
                # Parallel current sources into one node sum (KCL).
                forced[k] = forced.get(k, 0j) + val
        clash = set(emf) & set(forced)
        if clash:
            raise ValueError(
                "a voltage source and a current source share port node(s) "
                f"{sorted(clash)}: an ideal voltage source across an ideal "
                "current source is contradictory — drive the port one way"
            )
        terminations = {}
        z_ref_at = {}
        z_ref_node = self._reference_node() if z_ref else None
        for k in sorted(set(emf) | set(forced) | set(loads_by_node)):
            loads = loads_by_node.get(k, [])
            zs = [load_impedance(br, omega) for br in loads]
            if k in forced:
                # Forced-current termination (DrivenCurrent, issue #442):
                # constitutive row j = I, independent of any series loads —
                # they drop voltage inside the source loop without altering
                # the current, exactly NEC's LD-in-driven-segment physics.
                if not all(np.isfinite(z) for z in zs):
                    raise ValueError(
                        f"current source at port node {k} drives an open "
                        "load chain (parallel-LC trap at resonance): forcing "
                        "a current through an open is unphysical"
                    )
                terminations[k] = (len(elements), forced[k], "i", sum(zs, 0j))
                elements.append(
                    _Group2Element(None, k, c_v=0j, c_j=1.0 + 0j, e=forced[k])
                )
                if loads:
                    names = [br.port for br in loads]
                    probes.append((f"Load {'+'.join(names)}", "termination", k))
                continue
            e = emf.get(k, 0j)
            # Γ-referenced source (issue #746): a DRIVEN port's EMF sits behind
            # z_ref instead of pinning its node, which is the difference
            # between an ideal generator and a real one on a real feedline. The
            # answer Z = E/j − z_ref is algebraically independent of z_ref;
            # what changes is the conditioning, because Z_s = 0 is what made a
            # dead short across the port (a lossless λ/4 open stub, a k·λ/2
            # shorted one) unsolvable rather than simply Γ = −1. Undriven,
            # load-only terminations get NO z_ref — a fictitious 50 Ω inside a
            # real load chain would be a modelling error, not a reference —
            # and neither does any port but the one reference node.
            zr = complex(z_ref) if k == z_ref_node else 0j
            if zr:
                z_ref_at[k] = zr
            if len(loads) == 1 and loads[0].parallel:
                # Parallel-LC trap: the tank admittance is the finite
                # quantity (→ 0 at resonance, the intended open circuit);
                # the impedance form would blow up there. Putting z_ref in
                # series is y → y/(1 + z_ref·y), which stays finite at both
                # ends (→ 0 at resonance, → 1/z_ref for a shorted tank).
                y = load_series_admittance(loads[0], omega)
                y = y / (1.0 + zr * y)
                el = _Group2Element(None, k, c_v=y, c_j=1.0 + 0j, e=y * e)
            elif all(np.isfinite(z) for z in zs):
                # Series composition of every load (plus the EMF). Includes
                # the no-load case z = 0: an ideal voltage-source pin.
                el = _Group2Element(None, k, c_v=1.0 + 0j, c_j=sum(zs, zr), e=e)
            else:
                # A chain containing an at-resonance trap is an open — z_ref in
                # series with an open is still an open, and its Γ is +1.
                el = _Group2Element(None, k, c_v=0j, c_j=1.0 + 0j, e=0j)
            terminations[k] = (len(elements), e, "v", 0j)
            elements.append(el)
            if loads:
                names = [br.port for br in loads]
                probes.append((f"Load {'+'.join(names)}", "termination", k))

        return MNASystem(
            G,
            elements,
            terminations,
            probes=probes,
            diagnose=lambda wl=wavelength: self._singularity_report(wl),
            couplings=couplings,
            z_ref=z_ref,
            z_ref_at=z_ref_at,
        )

    def _physical_port_voltages(self, v):
        """Node voltages -> PHYSICAL port voltages. They differ only for a
        floating gap port, whose voltage is the drop ACROSS the gap,
        ``v[p] - v[n]``, not the "+" node's voltage against a datum it is
        deliberately not bonded to. The excited far-field/current solve forces
        these at the real feeds, so getting it wrong under-drives the antenna
        (and silently: the driven-point impedance reads off the termination
        branch and stays correct)."""
        if not self._floating:
            return v.copy()
        out = v.copy()
        for p_idx, n_idx in self._floating.values():
            out[p_idx] = v[p_idx] - v[n_idx]
        return out

    def resolve_voltages(self, system):
        """Return the (n_total,) physical port-voltage vector of the solved
        network: voltage-driven ports at their applied voltages, current-
        driven ports at whatever gap voltage the forced current produced,
        loaded ports at the gap voltage V_k = V_src − Z_L·I_k (the load
        shapes the current the way NEC2's ld_card does), every other port
        floating with I_ext = 0.
        These are the voltages the excited far-field/current solver forces
        at the real feeds."""
        v, _j = system.solve()
        return self._physical_port_voltages(v)

    def excited_state(self, Y_real, wavelength):
        """Physical port voltages + radiation efficiency + per-branch power
        budget for the CURRENT-DISTRIBUTION / far-field solve — the same
        MNA solve as the impedance path, read out for power bookkeeping.

        Returns ``(V_full, efficiency, p_in, budget)``:
          V_full      -- (n_total,) port voltages to force in the excited solver
          efficiency  -- P_radiated / P_input = 1 - P_dissipated / P_input, the
                         fraction of input power radiated rather than burned in
                         the network. A load-free / lossless network
                         returns 1.0.
          p_in        -- input power 1/2 Re(Σ V_src · I*) in watts, the gain
                         normaliser (gain = 4π·U/P_in); it already includes the
                         power burned in the network.
          budget      -- list of ``(label, watts)`` per network branch, in
                         branch order (issue #299): TL and parallel-Shunt
                         stamps via ½·Re(v†·Y_br·v), TwoPort/series-Shunt
                         via their explicit branch currents, Loads via the
                         termination drop. Lossless branches report ~0.
                         Power delivered to the antenna (radiated + any
                         wire/ground loss inside the MoM solve) is
                         p_in − Σ watts.

        The termination branches carry the physical port currents, so the
        source power reads directly off the solution vector:

            p_in   = ½ Σ Re(E_k · j_k*)          (E = 0 terms vanish)

        This path deliberately keeps the IDEAL-generator stamp (``z_ref = 0``)
        while the impedance/Γ path uses `Z_REF_DEFAULT` — a second solve, not
        an rcond-triggered fallback (issue #746). Two reasons. The port
        voltages here *are* the excitation forced into the MoM solver and the
        normaliser p_in = ½ΣRe(E·j*) is defined at the source terminals, so a
        source impedance would divide the drive and rescale every gain in the
        package. And a fallback would make those numbers depend on a
        conditioning threshold — the same design at two frequencies either
        side of it would report gains normalised differently, silently. The
        cost is one extra (n_ports + n_branches)-sized zgesvx per solve, which
        is nothing beside the MoM factorisation that produced Y, and the two
        systems were already assembled separately anyway.

        The consequence to know: a topology that shorts the driven port (a
        lossless λ/4 open stub across the feed) now has a perfectly good
        impedance answer, Z = 0 / Γ = −1, and still has no far field — the
        current an ideal source drives into a dead short is unbounded, so
        there is nothing to normalise against. That asymmetry is physical.

        Reactive elements burn nothing and report ~0 in the budget.
        Efficiency counts EVERY dissipative network branch — resistive
        TwoPort/Shunt elements and lossy TLs included (issue #299; the
        pre-#299 accounting counted Load terminations only, so designs
        with resistive coupling/matching branches now report a lower,
        physically consistent efficiency).
        """
        system = self.apply_branches(Y_real, wavelength)
        v, j = system.solve()
        p_in = 0.0
        for k, (col, e, tkind, z_chain) in system.terminations.items():
            if tkind == "i":
                # Current source: its terminal voltage sits behind the load
                # chain, v_src = v_k + z_chain·j; p = ½·Re(v_src·j*).
                v_src = v[k] + z_chain * j[col]
                p_in += 0.5 * float(np.real(v_src * np.conj(j[col])))
            else:
                p_in += 0.5 * float(np.real(e * np.conj(j[col])))
        budget = [
            (label, system.branch_power((label, kind, payload)))
            for label, kind, payload in system.probes
        ]
        p_diss = sum(w for _label, w in budget)
        # A lossless network's probes read pure float noise (|w| ~ 1e-17·p_in
        # from the reactive TL stamp); snap that to exactly 1.0 so lossless
        # designs keep reporting unity efficiency.
        if p_in > 0.0 and abs(p_diss) <= 1e-9 * p_in:
            p_diss = 0.0
        efficiency = 1.0 if p_in <= 0.0 else max(0.0, min(1.0, 1.0 - p_diss / p_in))
        return self._physical_port_voltages(v), efficiency, p_in, budget

    def impedance_from_y(self, system):
        """Driven-point impedance per Driven source from an `apply_branches`
        result: Z = E / j_term − z_ref, the termination EMF over its delivered
        current less the source impedance it was stamped behind — read
        straight off the solution vector, no Y·V post-multiply. ``z_ref`` is 0
        for the ideal-generator stamp, so this is the historical E/j there."""
        v, j = system.solve()
        out = []
        for k, kind in zip(self.driven_port_idx, self._source_kinds):
            col, e, _tkind, z_chain = system.terminations[k]
            if kind == "i":
                # Forced-current port (issue #442): the source impedance is
                # the gap voltage over the forced current, plus the series
                # load chain it drives through — mirroring how the voltage
                # form's E/j includes its series loads. A current source is
                # its own reference (Z_s = ∞), so z_ref never applies here.
                if j[col] == 0:
                    out.append(complex(float("inf"), 0.0))
                else:
                    out.append(complex(v[k] / j[col] + z_chain))
                continue
            if j[col] == 0:
                # Open-circuited source — no current path from the port
                # (e.g. a matching-network series capacitor slider at 0 F,
                # which is an open, not an absent element). The physical
                # driving-point impedance is ∞; report it as a clean real
                # infinity instead of dividing by zero (numpy would warn
                # and produce inf+nanj). Issue #289. Its Γ is a finite +1,
                # which is the whole argument for emitting Γ as well.
                out.append(complex(float("inf"), 0.0))
            else:
                out.append(complex(e / j[col] - system.z_ref_at.get(k, 0j)))
        return out

    def reflection_from_y(self, system):
        """Driven-port reflection coefficient Γ, referenced to the ``z_ref``
        the system was stamped with (issue #746).

        Γ = (2·v_ref − E)/E with v_ref = E − z_ref·j the voltage at the
        reference plane — the junction between the source impedance and
        whatever the port drives. For an unloaded port that plane IS the port
        node, so this is literally (2·v_k − E)/E; with a series `Load` the
        plane sits ahead of the load, matching `impedance_from_y`'s contract
        that Z includes the load chain.

        Read this way Γ never has a pole. The two cases that break Z break it
        by dividing: a shorted port (a lossless λ/4 open stub, a k·λ/2 shorted
        one) is Γ = −1, and an open port — where j is exactly 0 and Z is
        reported as ∞ — is Γ = +1 exactly, no sentinel and no clamp.

        A forced-current port has no z_ref (Z_s = ∞ is its reference), so its
        Γ is converted from Z; that conversion is the one that can still meet
        an infinity, and it maps to Γ = +1 by the same limit.
        """
        z_ref = system.z_ref
        if z_ref == 0:
            raise ValueError(
                "Γ is undefined for an ideal-generator solve (z_ref = 0): the "
                "reference plane has no impedance to reflect against. Stamp "
                "with apply_branches(..., z_ref=...) — driven_reflection() does"
            )
        _v, j = system.solve()
        out = []
        for k, kind, z in zip(
            self.driven_port_idx, self._source_kinds, self.impedance_from_y(system)
        ):
            col, e, _tkind, _z_chain = system.terminations[k]
            zr = system.z_ref_at.get(k)
            if kind == "i" or zr is None:
                # No reference plane at this port: a forced-current source is
                # its own reference (Z_s = ∞), and a 0 V pin has no incident
                # wave. Fall back to the definition, which meets an infinity
                # only at a true open — Γ = +1 by the same limit.
                out.append(
                    complex(1.0, 0.0)
                    if not np.isfinite(z)
                    else complex((z - z_ref) / (z + z_ref))
                )
                continue
            out.append(complex((2.0 * (e - zr * j[col]) - e) / e))
        return out

    def driven_impedance(self, Y_real, wavelength, *, z_ref=None):
        """Convenience: stamp branches onto the raw real-port Y and reduce
        to the driven-port impedance(s) in one call.

        Uses the Γ-referenced source stamp by default (issue #746). Z is
        algebraically independent of ``z_ref`` — what it buys is a system that
        stays well-conditioned when the port is shorted or opened, which the
        ideal generator does not.
        """
        z_ref = Z_REF_DEFAULT if z_ref is None else z_ref
        return self.impedance_from_y(
            self.apply_branches(Y_real, wavelength, z_ref=z_ref)
        )

    def driven_reflection(self, Y_real, wavelength, *, z_ref=None):
        """Convenience: driven-port Γ referenced to ``z_ref`` in one call."""
        z_ref = Z_REF_DEFAULT if z_ref is None else z_ref
        return self.reflection_from_y(
            self.apply_branches(Y_real, wavelength, z_ref=z_ref)
        )
