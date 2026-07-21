"""Standard library of station building blocks (issue #489): matchboxes,
transformers, and pass-throughs as reusable `Composite` components.

Each factory is an ordinary Python function returning a `Composite` — the
function arguments ARE the component's parameter list ("generators are
code, modules are data"). Designs instantiate them by name with a
formal/actual port map:

    from antennaknobs.network import Instance
    from antennaknobs.station import t_network_tuner, bypass

    branches = [
        Instance("tuner", t_network_tuner(c1_F=..., c2_F=..., l_H=...),
                 rig="rig", out="li"),
        TL.from_cable("openwire-600", "li", "feed", 20.0),
    ]

Swapping a box for `bypass()` (same two-port interface, wires straight
through) turns any "with/without the matchbox" comparison into a one-line
change.

Units are SI throughout (farads, henries, ohms) — matching the branch
classes, NOT the pF/µH conventions design knobs use; convert at the call
site where the knob's unit is visible.
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
    c1_F: float, c2_F: float, l_H: float, ql: float | None = None
) -> Composite:
    """The classic T-network ("high-pass tee") antenna tuner: series C1
    from ``rig`` to an internal tee midpoint, shunt L to common at the
    midpoint, series C2 on to ``out``. `ql` gives the coil a finite Q
    (R = ωL/Q, issue #298) — the coil is where a real T-network burns
    its watts. Formals: ``rig`` (transmitter side), ``out`` (line side)."""
    return Composite(
        ports=("rig", "out"),
        branches=(
            TwoPort(a="rig", b="m", c=c1_F),
            Shunt(port="m", l=l_H, ql=ql),
            TwoPort(a="m", b="out", c=c2_F),
        ),
    )


def l_network_tuner(
    series_l_H: float, shunt_c_F: float, ql: float | None = None
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
            TwoPort(a="rig", b="out", l=series_l_H, ql=ql),
            Shunt(port="out", c=shunt_c_F),
        ),
    )


def unun(
    turns: float,
    lmag_H: float | None = None,
    qlmag: float | None = None,
    comp_c_F: float | None = None,
) -> Composite:
    """Step-down unun (the EFHW / OCF box): an ideal ``turns``:1
    transformer — the ``line`` side sees Z_ant/turns² — with the minimal
    loss model of `Transformer` (magnetizing inductance ``lmag_H`` shunted
    across the line side, finite-Q core loss ``qlmag``), plus the optional
    compensation capacitor ``comp_c_F`` across the line-side terminals
    that commercial 49:1 builds carry. Formals: ``line`` (rig/feedline
    side), ``ant`` (high-Z antenna side)."""
    branches: tuple = (
        Transformer(a="line", b="ant", n=1.0 / turns, lmag=lmag_H, qlmag=qlmag),
    )
    if comp_c_F:
        branches += (Shunt(port="line", c=comp_c_F),)
    return Composite(ports=("line", "ant"), branches=branches)


def balun(
    n: float, lmag_H: float | None = None, qlmag: float | None = None
) -> Composite:
    """Balun as an ideal ``a:b`` ratio transformer with the minimal loss
    model (magnetizing branch on the ``line`` side): ``n`` is the
    line:antenna voltage ratio, so a 4:1 impedance balun stepping a
    ~300 Ω feed down to ~75 Ω line is ``balun(n=0.5)`` — same convention
    as `Transformer` itself. Formals: ``line``, ``ant``."""
    return Composite(
        ports=("line", "ant"),
        branches=(Transformer(a="line", b="ant", n=n, lmag=lmag_H, qlmag=qlmag),),
    )
