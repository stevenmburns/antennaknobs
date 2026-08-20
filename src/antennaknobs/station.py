"""Standard library of station building blocks (issue #489): matchboxes,
transformers, and pass-throughs as reusable `Composite` components.

Each factory is an ordinary Python function returning a `Composite` — the
function arguments ARE the component's parameter list ("generators are
code, modules are data"). Designs instantiate them by name with a
formal/actual port map:

    from antennaknobs.network import Instance
    from antennaknobs.station import t_network_tuner, bypass

    branches = [
        Instance("tuner", t_network_tuner(c1_pF=..., c2_pF=..., l_uH=...),
                 rig="rig", out="li"),
        TL.from_cable(cable_from_catalog("openwire-600"), "li", "feed", 20.0),
    ]

Swapping a box for `bypass()` (same two-port interface, wires straight
through) turns any "with/without the matchbox" comparison into a one-line
change.

Units are radio-work units — picofarads and microhenries, matching the
design-knob conventions (`series_c1_pF`, `lmag_uH`, …) — converted to the
branch classes' SI at construction. Ohms and Q are dimensionless-as-usual.
"""

from __future__ import annotations

import math

from .builder import C_LIGHT_MHZ_M
from .schematic import series, shunt
from .network import (
    Autotransformer,
    TL,
    BalancedLine,
    Composite,
    FloatingBalun,
    Instance,
    Shunt,
    Transformer,
    TwoPort,
    cable_from_catalog,
)


def bypass() -> Composite:
    """A two-port that wires its input straight to its output — the
    pass-through with a matchbox's interface (formals ``a``/``b``).
    Implemented as a pure alias (node merge), not a 0 Ω element: no extra
    MNA unknown, no budget row, electrically *identical* to not being
    there. Use it to A/B a station with and without its tuner/balun
    without touching anything else."""
    return Composite(ports=("a", "b"), aliases=(("a", "b"),))


def t_network_tuner(
    c1_pF: float, c2_pF: float, l_uH: float, ql: float | None = None
) -> Composite:
    """The classic T-network ("high-pass tee") antenna tuner: series C1
    from ``rig`` to an internal tee midpoint, shunt L to common at the
    midpoint, series C2 on to ``out``. `ql` gives the coil a finite Q
    (R = ωL/Q, issue #298) — the coil is where a real T-network burns
    its watts. Formals: ``rig`` (transmitter side), ``out`` (line side)."""
    return Composite(
        ports=("rig", "out"),
        branches=(
            TwoPort(a="rig", b="m", c=c1_pF * 1e-12),
            Shunt(port="m", l=l_uH * 1e-6, ql=ql),
            TwoPort(a="m", b="out", c=c2_pF * 1e-12),
        ),
        # Draws as the tee it is (issue #652). Without this the shunt coil
        # lands after both capacitors, because "the coil goes in the middle"
        # is not recoverable from the branch list.
        schematic=(
            series("capacitor", f"{c1_pF:g} pF"),
            shunt("inductor", f"{l_uH:g} µH"),
            series("capacitor", f"{c2_pF:g} pF"),
        ),
    )


def l_network_tuner(
    series_l_uH: float, shunt_c_pF: float, ql: float | None = None
) -> Composite:
    """L-match: series L from ``rig`` to ``out``, shunt C across ``out``
    (the load side — the arrangement that steps a higher load R down to
    the rig). Degenerate values are physics, not errors (issue #285): a
    0 H series arm is an ideal short and a 0 F shunt is an open, so both
    arms at zero make this an inert pass-through. Formals: ``rig``,
    ``out``."""
    return Composite(
        ports=("rig", "out"),
        branches=(
            TwoPort(a="rig", b="out", l=series_l_uH * 1e-6, ql=ql),
            Shunt(port="out", c=shunt_c_pF * 1e-12),
        ),
        schematic=(
            series("inductor", f"{series_l_uH:g} µH"),
            shunt("capacitor", f"{shunt_c_pF:g} pF"),
        ),
    )


def unun(
    turns: float,
    lmag_uH: float | None = None,
    qlmag: float | None = None,
    comp_c_pF: float | None = None,
    core=None,
) -> Composite:
    """Step-down unun (the EFHW / OCF box): an ideal ``turns``:1
    transformer — the ``line`` side sees Z_ant/turns² — with the minimal
    loss model of `Transformer` (magnetizing inductance ``lmag_uH`` shunted
    across the line side, finite-Q core loss ``qlmag``), plus the optional
    compensation capacitor ``comp_c_pF`` across the line-side terminals
    that commercial 49:1 builds carry.

    ``core`` (a `ferrite.FerriteCore`, issue #599) replaces the scalar
    ``lmag_uH``/``qlmag`` pair with the mix's actual complex permeability, so
    the magnetizing inductance AND the core loss both follow frequency:

        unun(49 ** 0.5, core=core_from_catalog("FT-240", "43", 11))

    (that call fetches the mix's published permeability once and caches it —
    the package ships no vendor data.)

    Formals: ``line`` (rig/feedline side), ``ant`` (high-Z antenna side)."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    branches: tuple = (
        Transformer(
            a="line", b="ant", n=1.0 / turns, lmag=lmag, qlmag=qlmag, core=core
        ),
    )
    if comp_c_pF:
        branches += (Shunt(port="line", c=comp_c_pF * 1e-12),)
    return Composite(ports=("line", "ant"), branches=branches)


def balun(
    n: float,
    lmag_uH: float | None = None,
    qlmag: float | None = None,
    core=None,
) -> Composite:
    """Balun as an ideal ``a:b`` ratio transformer with the minimal loss
    model (magnetizing branch on the ``line`` side): ``n`` is the
    line:antenna voltage ratio, so a 4:1 impedance balun stepping a
    ~300 Ω feed down to ~75 Ω line is ``balun(n=0.5)`` — same convention
    as `Transformer` itself. ``core`` takes a `ferrite.FerriteCore` in place of
    the scalar loss pair (issue #599). Formals: ``line``, ``ant``."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    return Composite(
        ports=("line", "ant"),
        branches=(
            Transformer(a="line", b="ant", n=n, lmag=lmag, qlmag=qlmag, core=core),
        ),
    )


def autotransformer_ratio(lower_uH: float, upper_uH: float) -> float:
    """Ideal tapped-autotransformer voltage ratio ``n = 1 + √(upper/lower)``.

    Turns go as √L on one core, so a tap at ``lower`` on a winding whose
    remainder is ``upper`` steps the tap voltage up by ``n`` — and the
    impedance at the tap is the load at the top over ``n²``. This is the ``k``
    → 1 limit that the coupled-inductor model in
    :class:`~antennaknobs.network.Autotransformer` reproduces rather than
    assumes; at realistic coupling (0.95–0.99) the achieved ratio falls a
    little short of it, which is exactly the difference the model exists to
    show.

    SimSmith surfaces the two section inductances as ``Lwr`` / ``Upr``; they
    are the arguments here, so a design can label its readout with
    ``autotransformer_ratio(lwr, upr)`` alongside them.
    """
    if lower_uH <= 0 or upper_uH <= 0:
        raise ValueError(
            f"section inductances must be positive; got {lower_uH} / {upper_uH} µH"
        )
    return 1.0 + math.sqrt(upper_uH / lower_uH)


def autotransformer(
    lower_uH: float,
    upper_uH: float,
    k: float = 0.98,
    ql: float | None = None,
) -> Composite:
    """Tapped single winding — the auto-transformer (issue #594).

    The matching element in many unun and L-network builds: *one* coil with a
    tap, so the sections are galvanically connected and the common section
    carries the difference of the input and output currents. `unun` / `balun`
    model the *isolated* two-winding case; this is the other one, and the
    difference is constitutive, not cosmetic.

    ``lower_uH`` is the common section (datum to the tap), ``upper_uH`` the
    remainder (tap to the top). Step-up: feed ``tap``, load ``top``, and the
    tap sees roughly the load over ``autotransformer_ratio(lower, upper)²``.
    ``k`` is the coupling coefficient — the default 0.98 is a realistic
    close-wound air-core value, and 1.0 is the ideal limit; ``ql`` gives both
    sections a finite Q whose *resistive* dissipation lands in the power
    budget. Formals: ``tap`` (low-Z side), ``top`` (high-Z side).
    """
    return Composite(
        ports=("tap", "top"),
        branches=(
            Autotransformer(
                a="tap",
                b="top",
                l_lower=lower_uH * 1e-6,
                l_upper=upper_uH * 1e-6,
                k=k,
                ql=ql,
            ),
        ),
    )


def link_coupling(
    n: float = 1.0, lmag_uH: float | None = None, qlmag: float | None = None
) -> Composite:
    """Link-coupling / floating balun — the differential twin of `balun()`
    (issue #589). A single-ended ``primary`` (to the datum, e.g. the rig) and
    a genuinely floating differential secondary pair ``a``/``b``: the balanced
    output is above the datum on both legs, so it hands a `BalancedLine` / a
    balanced tuner a datum-free feed. ``n`` is the primary→secondary voltage
    ratio (``v_a − v_b = n·v_primary``), so the secondary differential load is
    referred to the primary as ``Z_primary = Z_secondary / n²`` — ``n=1`` is a
    1:1 current balun (the Palstar BT1500A's input choke), ``n=2`` a 4:1
    step-down. ``lmag_uH``/``qlmag`` are the choke's magnetizing branch (the
    balun's own common-mode choking, distinct from `BalancedLine.zcomm`).
    Formals: ``primary`` (rig/coax side), ``a``/``b`` (balanced pair)."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    return Composite(
        ports=("primary", "a", "b"),
        branches=(
            FloatingBalun(primary="primary", a="a", b="b", n=n, lmag=lmag, qlmag=qlmag),
        ),
    )


def balanced_l_tuner(
    l_uH: float,
    c_pF: float,
    n: float = 1.0,
    ql: float | None = None,
    lmag_uH: float | None = None,
    qlmag: float | None = None,
) -> Composite:
    """The Palstar BT1500A "double roller balanced tuner" idiom (issue #589):
    a 1:1 (``n``) floating balun at the single-ended ``rig`` input, then a
    balanced L-network whose whole tuning section floats above the datum —
    the series roller inductance split symmetrically into both legs
    (``l_uH``/2 per leg) and a differential resonating capacitor ``c_pF``
    across the balanced output. Only the balun's primary is datum-referenced;
    the L-network legs are both above ground, so no common-mode current is
    injected at the rig. ``ql`` gives the roller coil a finite Q (the tuner's
    dominant loss); ``lmag_uH``/``qlmag`` the balun choke. Formals: ``rig``
    (transmitter/coax side), ``outL``/``outR`` (balanced line side)."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    return Composite(
        ports=("rig", "outL", "outR"),
        branches=(
            # 1:1 choke balun at the 50 Ω input → floating secondary (sL, sR)
            FloatingBalun(
                primary="rig", a="sL", b="sR", n=n, lmag=lmag, qlmag=qlmag
            ),  # fmt: skip
            # roller inductance split into both legs, one half per leg
            TwoPort(a="sL", b="outL", l=0.5 * l_uH * 1e-6, ql=ql),
            TwoPort(a="sR", b="outR", l=0.5 * l_uH * 1e-6, ql=ql),
            # differential resonating cap across the balanced output legs
            TwoPort(a="outL", b="outR", c=c_pF * 1e-12),
        ),
    )


# ---------------------------------------------------------------------------
# Transmission-line stubs (issue #598) — composition sugar over `TL` /
# `BalancedLine`, no new reducer math.
#
# LENGTH CONVENTION, once, for everything below: ``length_wl`` is the stub's
# ELECTRICAL length in wavelengths ON THE LINE at ``freq_mhz`` — i.e. βl =
# 2π·length_wl at the design frequency, the number you read off a Smith chart
# ("a 0.125 λ shorted stub"). The physical line that gets cut is
#
#     length_m = length_wl · vf · (C_LIGHT_MHZ_M / freq_mhz)
#
# so the velocity factor is applied FOR you and a 0.125 λ stub is 0.125 λ
# electrically whatever it is made of. That physical length is what lands in
# the `TL`, so a frequency sweep re-derives βl from the solve wavelength the
# usual way: away from ``freq_mhz`` the stub is exactly as detuned as the real
# piece of coax would be. (Contrast the raw `TL`, whose ``length`` is metres
# and whose ``vf`` you must apply yourself.)
#
# LOSS: ``k1``/``k2`` are the cable-table matched-loss coefficients of `TL`
# (dB per 100 ft = k1·√f_MHz + k2·f_MHz); ``cable="RG-213"`` fills z0/vf/k1/k2
# from the `CABLES` catalog in one word — the honest spelling for a stub cut
# from real coax, and the escape hatch from the lossless singularities below.
# ---------------------------------------------------------------------------
def _stub_line(freq_mhz, length_wl, z0, vf, k1, k2, cable):
    """Resolve a stub's line parameters to ``(z0, length_m, vf, k1, k2)``.

    ``cable`` (a `CABLES` key) supersedes z0/vf/k1/k2 wholesale — it is the
    cable, not a default — and reuses `cable_from_catalog`'s unknown-name
    ergonomics. Then the one length conversion of the module section header,
    in one place."""
    if cable is not None:
        spec = cable_from_catalog(cable)
        z0, vf, k1, k2 = spec.z0, spec.vf, spec.k1, spec.k2
    if freq_mhz <= 0.0:
        raise ValueError(f"stub freq_mhz must be positive, got {freq_mhz!r}")
    return z0, length_wl * vf * C_LIGHT_MHZ_M / freq_mhz, vf, k1, k2


# Retired 2026-08-06 (issue #746): `_guard_open_stub` refused a lossless open
# stub at an odd multiple of λ/4 at construction, because Z_in = 0 there puts a
# dead short across the port and NO IDEAL SOURCE CAN DRIVE A SHORT. That was
# always a statement about the source model, not about the stub — the reducer
# now stamps the driven port as an EMF behind `Z_REF_DEFAULT`, so the same stub
# solves with the equilibrated condition it has at every other length (measured
# flat at 0.065 across 30–40 MHz on the test_singular_network fixture, against
# 1e-17 for the ideal generator at the pole) and reports the answer: Z = 0,
# Γ = −1. The quarter-wave open stub is a short, and a short is a perfectly
# ordinary thing for a network to be.
#
# What does NOT follow it: the FAR-FIELD path, which keeps the ideal generator
# because its port voltages are the excitation (see
# `network_reduce.excited_state`). Driving a dead short with an ideal source
# takes unbounded current, so a design that shorts its own feed has an
# impedance and no pattern — reported by the solve, with attribution.


def shunt_open_stub(
    freq_mhz: float,
    length_wl: float,
    z0: float = 50.0,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """Open-circuited stub hung ACROSS the line (issue #598): a `TL` from the
    formal port into a private internal node that nothing else touches — an
    open is the *absence* of a termination, so it is spelled as one, with no
    element to stand for it. The port sees the classic

        Z_in = −j·Z₀·cot(βl)      (lossless; Z₀·coth(γl) in general)

    — capacitive below λ/4, inductive between λ/4 and λ/2, and repeating: the
    quarter-wave open stub is a short (the harmonic-notch trap), the half-wave
    open stub an open. Lengths in wavelengths at ``freq_mhz``; see this
    section's header for the convention, and the note above it for why an
    exactly-λ/4 LOSSLESS open stub used to be refused and no longer is.
    Formal: ``port``."""
    z0, length, vf, k1, k2 = _stub_line(freq_mhz, length_wl, z0, vf, k1, k2, cable)
    return Composite(
        ports=("port",),
        branches=(TL(a="port", b="far", z0=z0, length=length, vf=vf, k1=k1, k2=k2),),
    )


def shunt_shorted_stub(
    freq_mhz: float,
    length_wl: float,
    z0: float = 50.0,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """Short-circuited stub hung ACROSS the line (issue #598): a `TL` from the
    formal port into a private node bonded to the datum by a 0 Ω `Shunt` —
    the reducer's exact ideal short (issue #285), not a small resistor. The
    port sees

        Z_in = +j·Z₀·tan(βl)      (lossless; Z₀·tanh(γl) in general)

    — inductive below λ/4, capacitive between λ/4 and λ/2: the dual of
    `shunt_open_stub`, and the flavor real installations prefer (DC-grounded,
    weatherable, adjustable with a shorting bar). The quarter-wave shorted
    stub is an open — the "metal insulator" / RF choke — and needs no guard,
    being a plain zero admittance; the half-wave one really is a dead short
    across the port, which an ideal voltage source cannot drive, so the SOLVE
    reports it (issue #746 retired the stamp-time half-wave guard that used
    to fire first, on every half-wave line whether shorted or not). Lengths in
    wavelengths at ``freq_mhz`` (section header). Formal: ``port``."""
    z0, length, vf, k1, k2 = _stub_line(freq_mhz, length_wl, z0, vf, k1, k2, cable)
    return Composite(
        ports=("port",),
        branches=(
            TL(a="port", b="far", z0=z0, length=length, vf=vf, k1=k1, k2=k2),
            Shunt(port="far", r=0.0),  # the shorting strap, as an ideal short
        ),
    )


def series_open_stub(
    freq_mhz: float,
    length_wl: float,
    z0: float = 50.0,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """Open-circuited stub inserted IN SERIES with the line (issue #598) —
    the line is broken and the stub's ``Z_in = −j·Z₀·cot(βl)`` appears
    between ``a`` and ``b``.

    Built on `BalancedLine`, not `TL`, and that is forced: a `TL`'s two
    terminals are each referenced to the network datum, so a `TL` stub's
    input impedance is unavoidably a node-to-DATUM (shunt) quantity. A
    series element must float between two nodes, which is precisely what
    `BalancedLine`'s differential stamp gives — it forces I(a1) = −I(a2)
    with no datum path (``zcomm=None``), so the pair IS a floating
    two-terminal impedance of value ``zdiff·coth(γl)``. ``z0`` is therefore
    the stub's differential Z₀ (`BalancedLine.zdiff`).

    The far end: ``far1`` open (a 0 F `Shunt` — the reducer's exact open,
    here spelling out "nothing is attached" so the node is not rejected as
    common-mode floating), ``far2`` bonded to the datum. That bond carries
    ZERO current — the differential stamp forces I(far2) = −I(far1) and
    ``far1`` is open — so it is a common-mode reference pin, not a
    termination, and the element stays genuinely floating at ``a``/``b``.
    A lossless odd-λ/4 length shorts the element's two terminals together
    rather than the port to the datum, and — like `shunt_open_stub`'s — is now
    an ordinary answer rather than a refusal (issue #746). Formals: ``a``,
    ``b``."""
    z0, length, vf, k1, k2 = _stub_line(freq_mhz, length_wl, z0, vf, k1, k2, cable)
    return Composite(
        ports=("a", "b"),
        branches=(
            BalancedLine(
                a1="a",
                a2="b",
                b1="far1",
                b2="far2",
                zdiff=z0,
                length=length,
                vf=vf,
                k1=k1,
                k2=k2,
            ),
            Shunt(port="far1", c=0.0),  # open end: 0 F = no element
            Shunt(port="far2", r=0.0),  # common-mode reference pin (0 A)
        ),
    )


def series_shorted_stub(
    freq_mhz: float,
    length_wl: float,
    z0: float = 50.0,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """Short-circuited stub inserted IN SERIES with the line (issue #598) —
    the line is broken and the stub's ``Z_in = +j·Z₀·tan(βl)`` appears
    between ``a`` and ``b``. The floating-element argument, the ``zdiff``
    reading of ``z0``, and the zero-current reference pin are all as in
    `series_open_stub`; the difference is the far end, where a 0 Ω `TwoPort`
    straps ``far1`` to ``far2`` — the shorting strap itself, exactly where
    the physical one goes. Formals: ``a``, ``b``."""
    z0, length, vf, k1, k2 = _stub_line(freq_mhz, length_wl, z0, vf, k1, k2, cable)
    return Composite(
        ports=("a", "b"),
        branches=(
            BalancedLine(
                a1="a",
                a2="b",
                b1="far1",
                b2="far2",
                zdiff=z0,
                length=length,
                vf=vf,
                k1=k1,
                k2=k2,
            ),
            TwoPort(a="far1", b="far2", r=0.0),  # the shorting strap
            Shunt(port="far2", r=0.0),  # common-mode reference pin (0 A)
        ),
    )


def single_stub_tuner(
    freq_mhz: float,
    line_wl: float,
    stub_wl: float,
    z0: float = 50.0,
    shorted: bool = True,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """The classic single-stub match (issue #598): a section of line of
    length ``line_wl`` from the load up to a tap, and a shunt stub of length
    ``stub_wl`` hung at that tap. Walk ``line_wl`` from the load until the
    admittance there has the right real part (Y = Y₀ + jB), then pick
    ``stub_wl`` so the stub's susceptance cancels the jB — a match with no
    lumped parts, just two lengths of the same cable.

    ``shorted`` picks the stub flavor (`shunt_shorted_stub` by default,
    `shunt_open_stub` when False); the section and the stub share one set of
    line parameters, which is what cutting both from the same reel means. For
    a stub of a *different* cable, compose the pieces by hand — that is all
    this factory does. Both lengths are in wavelengths at ``freq_mhz``
    (section header). Formals: ``rig`` (source side — this IS the tap), ``ant``
    (load side)."""
    lz0, length, lvf, lk1, lk2 = _stub_line(freq_mhz, line_wl, z0, vf, k1, k2, cable)
    make = shunt_shorted_stub if shorted else shunt_open_stub
    stub = make(freq_mhz, stub_wl, z0=z0, vf=vf, k1=k1, k2=k2, cable=cable)
    return Composite(
        ports=("rig", "ant"),
        branches=(
            TL(a="rig", b="ant", z0=lz0, length=length, vf=lvf, k1=lk1, k2=lk2),
            Instance("stub", stub, port="rig"),
        ),
        schematic=(
            # Both lines are the same cable — `_stub_line` resolves the stub's
            # z0/vf from the same arguments — so they annotate alike: what it
            # is, then how long. The stub's far end is `term`, not prose.
            shunt(
                "coax",
                f"{lz0:g} Ω",
                f"{stub_wl:g} λ",
                term="short" if shorted else "open",
            ),
            series("coax", f"{lz0:g} Ω", f"{line_wl:g} λ"),
        ),
    )


def double_stub_tuner(
    freq_mhz: float,
    spacing_wl: float,
    stub1_wl: float,
    stub2_wl: float,
    z0: float = 50.0,
    shorted: bool = True,
    vf: float = 1.0,
    k1: float = 0.0,
    k2: float = 0.0,
    cable: str | None = None,
) -> Composite:
    """The double-stub tuner (issue #598): stubs at two FIXED positions —
    ``stub1`` at the load end, ``stub2`` a fixed ``spacing_wl`` up the line at
    the rig end — matched by adjusting the two lengths instead of sliding a
    tap. The trombone-free tuner of the real world (both stubs can be
    telescoping sections at fixed tees), at the price of a forbidden region:
    loads whose admittance lands inside the spacing's dead circle cannot be
    matched at all, and that is the tuner's fault, not the solver's. λ/8 and
    3λ/8 spacings are the usual choices.

    Same parameter conventions as `single_stub_tuner`, one stub length per
    stub. Formals: ``rig`` (stub2 side), ``ant`` (stub1/load side)."""
    lz0, length, lvf, lk1, lk2 = _stub_line(freq_mhz, spacing_wl, z0, vf, k1, k2, cable)
    make = shunt_shorted_stub if shorted else shunt_open_stub
    return Composite(
        ports=("rig", "ant"),
        branches=(
            Instance(
                "stub1",
                make(freq_mhz, stub1_wl, z0=z0, vf=vf, k1=k1, k2=k2, cable=cable),
                port="ant",
            ),
            TL(a="rig", b="ant", z0=lz0, length=length, vf=lvf, k1=lk1, k2=lk2),
            Instance(
                "stub2",
                make(freq_mhz, stub2_wl, z0=z0, vf=vf, k1=k1, k2=k2, cable=cable),
                port="rig",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Calibrated presets — measured boxes as named values (issue #489).
#
# Each preset wraps a factory above with parameters CALIBRATED to a published
# measurement rather than derived from core datasheets (the `Transformer`
# loss model's intended use). The catalog designs that source these numbers
# keep their own knobs (so users can re-tune them); the presets are the same
# stock values as importable, reusable components for station authors —
# tests pin preset == design-stock so the two cannot drift apart.
# ---------------------------------------------------------------------------
def kj6er_unun_4_1(plus: bool = False) -> Composite:
    """KJ6ER Challenger's 4:1 unun (2:1 turns), calibrated to his measured
    insertion loss at 21.35 MHz: stock build −0.34 dB; ``plus=True`` is the
    upgraded build at −0.24 dB. Source: the Challenger plans' measured
    table (see ``verticals.challenger``)."""
    return unun(turns=2.0, lmag_uH=1.75 if plus else 1.22, qlmag=3.0)


def kj6er_unun_49_1() -> Composite:
    """KJ6ER Dominator's stock 49:1 unun (7:1 turns), calibrated to the
    measured −0.96 dB at 21.35 MHz — the loss figure interrogated in the
    docs' end-fed pages (see ``verticals.dominator``)."""
    return unun(turns=7.0, lmag_uH=0.33, qlmag=3.0)


def kj6er_unun_56_1() -> Composite:
    """The Dominator-plus 56:1 unun (7.5:1 turns, MyAntennas-class build),
    calibrated to the measured −0.40 dB at 21.35 MHz (see
    ``verticals.dominator``'s ``plus`` variant)."""
    return unun(turns=7.5, lmag_uH=0.74, qlmag=3.0)


def ft240_43_unun_49_1(comp_c_pF: float | None = 100.0) -> Composite:
    """The generic FT240-43-class 49:1 EFHW unun (7:1 turns, ~3 primary
    turns → 8 µH magnetizing, core Q ≈ 10), landing in the 85–90 %
    efficiency range bench-measured for such builds, with the customary
    100 pF compensation capacitor across the primary (pass ``None`` to
    omit it). The stock box of ``wire.efhw_sloper``."""
    return unun(turns=7.0, lmag_uH=8.0, qlmag=10.0, comp_c_pF=comp_c_pF)
