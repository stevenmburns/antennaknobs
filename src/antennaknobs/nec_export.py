"""Export an antennaknobs builder to a NEC2 card deck (``.nec``).

NEC tools (xnec2c, 4nec2, EZNEC, nec2c, …) all speak the NEC ``.nec`` card
format, but antennaknobs has only ever *consumed* NEC cards (via PyNEC's
card API) — it could not emit them. This module closes that gap.

The deck is built by reusing :class:`PyNECEngine`'s already-resolved geometry:
the segment-parity-coerced wire tuples (``eng.tups``), the resolved feed
locations (``eng.excitation_pairs``), the ground spec, and any ``Load`` network
branches. That makes the emitted deck a faithful text twin of exactly what
PyNECEngine hands to PyNEC's in-memory card API — so a NEC engine reading the
deck (``nec2c``) reproduces PyNECEngine's impedance.

Not supported: TL/virtual-driver networks. PyNECEngine solves those by a
multiport-Y reduction (a circuit post-process on the field solution), not by
native NEC ``tl_card``s, so there is no faithful single-deck representation.
``export_nec`` raises ``NotImplementedError`` for them.
"""

from __future__ import annotations

from .engines.pynec import DEFAULT_GROUND, WIRE_CONDUCTIVITY, PyNECEngine
from .network import Load


def _num(x):
    """NEC free-format real. 6 significant digits round-trips wire coordinates
    and component values without NEC's fixed-column ambiguity."""
    return f"{float(x): .6E}"


def _gw(tag, n_seg, p0, p1, radius):
    return (
        f"GW {tag} {n_seg} "
        f"{_num(p0[0])} {_num(p0[1])} {_num(p0[2])} "
        f"{_num(p1[0])} {_num(p1[1])} {_num(p1[2])} {_num(radius)}"
    )


def _gn(ground):
    """Ground card matching PyNECEngine._apply_ground_card. Returns None for
    free space (no GN card)."""
    if ground is None or ground == "free":
        return None
    if ground == "pec":
        return "GN 1 0 0 0 0 0"
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0]
        in (
            "finite",
            "finite-fast",
        )
    ):
        _, eps_r, sigma = ground
        # IPERF 2 = Sommerfeld-Norton, 0 = reflection-coefficient approximation.
        iperf = 2 if ground[0] == "finite" else 0
        return f"GN {iperf} 0 0 0 {_num(eps_r)} {_num(sigma)}"
    raise ValueError(f"unrecognised ground spec: {ground!r}")


def export_nec(
    builder,
    *,
    ground=DEFAULT_GROUND,
    freq=None,
    df=0.0,
    npoints=1,
    include_rp=True,
    title=None,
):
    """Return a NEC2 card deck (str) for ``builder``.

    ground   : same spec as PyNECEngine — None/"free", "pec",
               ("finite", eps_r, sigma) (Sommerfeld-Norton), or
               ("finite-fast", eps_r, sigma) (reflection-coefficient).
    freq     : design frequency in MHz; defaults to ``builder.freq``.
    df       : FR-card frequency step in MHz (for a sweep).
    npoints  : FR-card frequency count.
    include_rp: append an RP card so the deck also computes a far-field pattern.
    title    : CM comment text; defaults to the builder's qualified name.
    """
    eng = PyNECEngine(builder, ground=ground)
    if eng._use_reducer:
        raise NotImplementedError(
            "NEC export of TL/virtual-driver networks is not supported: "
            "PyNECEngine solves those by a multiport-Y reduction, not native "
            "NEC cards, so there is no faithful single-deck representation."
        )
    freq = builder.freq if freq is None else float(freq)

    title = title or f"{type(builder).__module__}.{type(builder).__qualname__}"
    lines = [f"CM {title}", "CM exported by antennaknobs.nec_export", "CE"]

    # --- geometry: one GW per resolved wire tuple, then GE ---
    for tag, t in enumerate(eng.tups, start=1):
        lines.append(_gw(tag, t[2], t[0], t[1], eng._wire_radius))
    lines.append("GE 0")

    # --- Load branches -> LD cards (type 0 series / 1 parallel RLC) ---
    if eng._network is not None:
        for br in eng._network.branches:
            if not isinstance(br, Load):
                continue
            tag, seg = eng._network_port_loc[br.port]
            r = float(br.r) if br.r is not None else 0.0
            l = float(br.l) if br.l is not None else 0.0
            c = float(br.c) if br.c is not None else 0.0
            if r == 0.0 and l == 0.0 and c == 0.0:
                continue
            ldtyp = 1 if br.parallel else 0
            lines.append(f"LD {ldtyp} {tag} {seg} {seg} {_num(r)} {_num(l)} {_num(c)}")

    # Wire material (issue #316): the same global LD cards the engine
    # emits — conductor loss as LD 5 (spec conductivity from the design,
    # else the module-level oracle constant; normally None → card omitted,
    # PEC) and the insulation jacket's series inductance as LD 2 (H/m).
    sigma = (
        eng._wire_spec.conductivity if eng._wire_spec is not None else WIRE_CONDUCTIVITY
    )
    if sigma is not None:
        lines.append(f"LD 5 0 0 0 {_num(sigma)} 0. 0.")
    l_ins = eng._insulation_l_per_m()
    if l_ins is not None:
        lines.append(f"LD 2 0 0 0 0. {_num(l_ins)} 0.")

    # Legacy build_tls() path -> native NEC TL cards. (The build_network() TL
    # path uses the multiport-Y reducer and is rejected above.)
    for idx1, seg1, idx2, seg2, impedance, length in eng.tls:
        lines.append(
            f"TL {idx1} {seg1} {idx2} {seg2} {_num(impedance)} {_num(length)} 0 0 0 0"
        )

    gn = _gn(eng.ground)
    if gn:
        lines.append(gn)

    # --- excitations (EX), frequency (FR), optional pattern (RP) ---
    for tag, seg, v in eng.excitation_pairs:
        v = complex(v)
        lines.append(f"EX 0 {tag} {seg} 0 {_num(v.real)} {_num(v.imag)}")

    lines.append(f"FR 0 {npoints} 0 0 {_num(freq)} {_num(df)}")
    if include_rp:
        # RP triggers the solve and prints input parameters + the pattern.
        # Hemisphere cut matching PyNECEngine._collect_pattern defaults.
        lines.append("RP 0 19 37 1000 0 0 10 10")
    else:
        # No pattern requested: an explicit XQ still triggers the solve so the
        # deck reports ANTENNA INPUT PARAMETERS (impedance). Without an XQ/RP
        # card NEC reads the geometry but never executes.
        lines.append("XQ 0")
    lines.append("EN")
    return "\n".join(lines) + "\n"
