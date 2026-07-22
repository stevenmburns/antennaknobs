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
        TL.from_cable("openwire-600", "li", "feed", 20.0),
    ]

Swapping a box for `bypass()` (same two-port interface, wires straight
through) turns any "with/without the matchbox" comparison into a one-line
change.

Units are radio-work units — picofarads and microhenries, matching the
design-knob conventions (`series_c1_pF`, `lmag_uH`, …) — converted to the
branch classes' SI at construction. Ohms and Q are dimensionless-as-usual.
"""

from __future__ import annotations

from .network import Composite, Shunt, Transformer, TwoPort


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
    )


def unun(
    turns: float,
    lmag_uH: float | None = None,
    qlmag: float | None = None,
    comp_c_pF: float | None = None,
) -> Composite:
    """Step-down unun (the EFHW / OCF box): an ideal ``turns``:1
    transformer — the ``line`` side sees Z_ant/turns² — with the minimal
    loss model of `Transformer` (magnetizing inductance ``lmag_uH`` shunted
    across the line side, finite-Q core loss ``qlmag``), plus the optional
    compensation capacitor ``comp_c_pF`` across the line-side terminals
    that commercial 49:1 builds carry. Formals: ``line`` (rig/feedline
    side), ``ant`` (high-Z antenna side)."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    branches: tuple = (
        Transformer(a="line", b="ant", n=1.0 / turns, lmag=lmag, qlmag=qlmag),
    )
    if comp_c_pF:
        branches += (Shunt(port="line", c=comp_c_pF * 1e-12),)
    return Composite(ports=("line", "ant"), branches=branches)


def balun(
    n: float, lmag_uH: float | None = None, qlmag: float | None = None
) -> Composite:
    """Balun as an ideal ``a:b`` ratio transformer with the minimal loss
    model (magnetizing branch on the ``line`` side): ``n`` is the
    line:antenna voltage ratio, so a 4:1 impedance balun stepping a
    ~300 Ω feed down to ~75 Ω line is ``balun(n=0.5)`` — same convention
    as `Transformer` itself. Formals: ``line``, ``ant``."""
    lmag = lmag_uH * 1e-6 if lmag_uH is not None else None
    return Composite(
        ports=("line", "ant"),
        branches=(Transformer(a="line", b="ant", n=n, lmag=lmag, qlmag=qlmag),),
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
