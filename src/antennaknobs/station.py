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
