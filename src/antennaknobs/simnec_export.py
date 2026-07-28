"""Emit a SimNEC (``.ssn``) circuit for an antenna-only design (issue #600).

SimNEC (AE6TY) is a Java Smith-chart / station tool that embeds NEC2 behind an
in-house MNA solver. Its native circuit file is ``.ssn`` (XML). This module
lets any *antenna-only* antennaknobs design be round-tripped into SimNEC for
cross-validation, without the fiddly UI step of hand-entering geometry.

How it works — the escape-hatch route
-------------------------------------
A SimNEC ``.ssn`` is a list of circuit ``<element>``s. For an antenna model the
canonical shape is three elements — ``LOAD`` / ``NETWORK`` / ``GENERATOR`` —
where the antenna lives inside the ``NETWORK`` element's escape-hatch ``<equ>``
script, expressed in SimNEC's NEC-portal daemon language:

    P1 w1 gnd;                         // the two circuit ports; EX drives P2
    P2 w2 gnd;
    NECUnits meters, meters;
    SommerfeldGround(0.0303, 20);      // (mhos, dielectric) == (sigma, eps_r)
    NECOptions.mhosPerMeter = 0;       // 0 = PEC
    NECOptions.segmentsPerWavelength = 120;
    NEC2                               // NEC cards go between NEC2 and NECEND
    GW 1 ...
    EX 0 1 6 0 1. 0.
    NECEND

We reuse :func:`antennaknobs.nec_export.export_nec` for the geometry, then keep
the ``GW`` / ``FR`` / ``EX`` / lumped-``LD`` cards and translate the rest into
daemon directives: the Generator's ``MHz`` carries the (sweepable) solve
frequency; ``GN`` → the ground call; the deck's segment counts are *advisory
only* — SimNEC re-meshes at ``NECOptions.segmentsPerWavelength``, which is why
that knob is exposed. ``FR`` is left in the deck too: a SimNEC 5.1a1-saved
``.ssn`` carries ``FR`` alongside a live ``G.MHz`` sweep, so it is harmless
(advisory) and matches SimNEC's own output.

Scope
-----
**Antenna-only** designs (no ``build_network`` TL/virtual-driver station), matching
issue #600. ``export_nec`` already raises ``NotImplementedError`` for reducer
networks, and this module surfaces that. Emitting the *station network* too
(via SimNEC's ``N`` / RUSE blocks) is a possible phase 2.

Licensing
---------
SimNEC is proprietary freeware. This module emits SimNEC's *open file format*
for interoperability (like emitting a NEC deck or a Touchstone file); it does
**not** copy SimNEC's bundled circuit files or assets. The daemon directives are
the documented NEC-portal API. The surrounding XML scaffold in
:data:`_SSN_TEMPLATE` is authored here (clean-room) from the format's structure.

.. note::
   Reconciled against a SimNEC 5.1a1-saved ``.ssn``: the root ``SimNEC1p0``,
   the ``SimNEC:<version>`` ``XMLVersionControl`` string, the Generator's ``Zo``
   impedance tag, and the retained ``FR`` card all match SimNEC's own output.
   The scaffold here is deliberately *minimal* (it omits SimNEC's display state
   — ``SPREADSHEET`` / charts / band menus — which SimNEC regenerates on load);
   a Windows load-test confirms SimNEC accepts that minimal subset. The Generator
   frequency sweep is off by default (SimNEC supplies its own range); pass
   ``sweep=(lo, hi)`` / ``--sweep`` to emit an enabled band.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _xml_escape

from .engines.pynec import DEFAULT_GROUND
from .nec_export import export_nec

__all__ = ["export_ssn", "build_nec_portal_script"]


def _fmt(x: float) -> str:
    """Compact real for daemon directives (trim trailing zeros)."""
    return f"{float(x):g}"


def _ground_directive(ground) -> tuple[str | None, float]:
    """Map an antennaknobs ground spec to a SimNEC daemon ground call and the
    wire conductivity (mhos/m) to set on ``NECOptions.mhosPerMeter``.

    Returns ``(call_or_None, mhos_per_meter)``. Free space → no ground call.
    Note SimNEC's ``SommerfeldGround(mhos, dielectric)`` takes (sigma, eps_r) —
    the reverse of our ``("finite", eps_r, sigma)`` tuple.
    """
    if ground is None or ground == "free":
        return None, 0.0
    if ground == "pec":
        return "PerfectGround();", 0.0
    if (
        isinstance(ground, tuple)
        and len(ground) == 3
        and ground[0] in ("finite", "finite-fast")
    ):
        _, eps_r, sigma = ground
        # SimNEC has no distinct reflection-coefficient ("finite-fast") ground;
        # both map to its Sommerfeld solve — the accurate model — which is also
        # what a validation run should compare against.
        return f"SommerfeldGround({_fmt(sigma)}, {_fmt(eps_r)});", 0.0
    raise ValueError(f"unrecognised ground spec: {ground!r}")


def _nec_cards_for_portal(deck: str) -> list[str]:
    """Keep the cards SimNEC's NEC block wants: geometry (``GW``), frequency
    (``FR``), excitation (``EX``), and lumped loads (``LD 0`` / ``LD 1``).

    ``FR`` is kept because SimNEC's own NEC-portal decks carry it — even while
    the Generator sweeps ``G.MHz`` (the deck's ``FR`` is advisory; the solve
    frequency comes from the Generator). Confirmed against a SimNEC 5.1a1-saved
    ``.ssn`` (``FR 0 1 0 0 <f> 0`` present alongside a live G.MHz sweep).

    Dropped: ``CM``/``CE``/``GE``/``RP``/``XQ``/``EN`` (structural), ``GN`` (→
    ground call), ``LD 5`` global conductivity (→ ``NECOptions.mhosPerMeter``)
    and ``LD 2`` insulation (not representable in the NEC block).
    """
    # Group into canonical NEC order — geometry+loads, then FR, then EX — to
    # match a SimNEC 5.1a1-saved deck (GW … FR … EX) rather than export_nec's
    # emission order, which puts EX before FR.
    geom: list[str] = []
    fr: list[str] = []
    ex: list[str] = []
    for raw in deck.splitlines():
        s = raw.strip()
        if s.startswith("GW "):
            geom.append(s)
        elif s.startswith("FR "):
            fr.append(s)
        elif s.startswith("EX "):
            ex.append(s)
        elif s.startswith("LD "):
            parts = s.split()
            ldtyp = parts[1] if len(parts) > 1 else ""
            if ldtyp in ("0", "1"):  # series / parallel lumped RLC load
                geom.append(s)
            # LD 5 (conductivity) and LD 2 (insulation) are handled elsewhere
            # or unsupported; skip here.
    return geom + fr + ex


def build_nec_portal_script(
    builder,
    *,
    freq_mhz: float,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    name: str | None = None,
) -> str:
    """Build the SimNEC NEC-portal daemon script (the ``<equ>`` body) for an
    antenna-only ``builder``. Reuses :func:`export_nec` for the geometry.
    """
    deck = export_nec(builder, ground=ground, freq=freq_mhz, include_rp=False)
    cards = _nec_cards_for_portal(deck)

    if name is None:
        mod = type(builder).__module__
        qual = type(builder).__qualname__
        # SimNEC shows this first //comment as the block's display name, which
        # only fits ~12 chars before the font shrinks to unreadable. So use the
        # SHORT leaf name: the design's module leaf (e.g. "invvee") for a real
        # design, or the class qualname for a script-defined (__main__) builder.
        if mod != "__main__" and qual == "Builder":
            name = mod.rsplit(".", 1)[-1]
        else:
            name = qual
    ground_call, mhos = _ground_directive(ground)

    lines = [
        f"//{name}",
        "// generated by antennaknobs.simnec_export",
        "P1 w1 gnd;",
        "P2 w2 gnd;",
        "NECUnits meters, meters;",
    ]
    if ground_call:
        lines.append(ground_call)
    lines.append(f"NECOptions.mhosPerMeter = {_fmt(mhos)};")
    if seg_per_wl is not None:
        lines.append(f"NECOptions.segmentsPerWavelength = {int(seg_per_wl)};")
    lines.append("NEC2")
    lines.extend(cards)
    lines.append("NECEND")
    return "\n".join(lines)


# --- minimal .ssn XML scaffold (see module note) ----------------------------
# Three-element cascade: LOAD (open, right end) — NETWORK (the antenna, in the
# escape-hatch script) — GENERATOR (50 Ohm source, left end). Deliberately minimal
# — SimNEC regenerates the display state (SPREADSHEET / charts / band menus) it
# omits. The Generator's MHz carries an optional {gen_sweep} <sweepParam>.
_SSN_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <XMLVersionControl>SimNEC:5.1a1</XMLVersionControl>
        <CIRCUIT>
            <element>
                <type>LOAD</type>
                <sweeperLabel>L</sweeperLabel>
                <p><n>ohms</n><v>1000000000</v></p>
            </element>
            <element>
                <type>NETWORK</type>
                <sweeperLabel>A</sweeperLabel>
                <escapeHatch/>
                <p><n>equ</n><v>{equ}</v></p>
            </element>
            <element>
                <type>GENERATOR</type>
                <sweeperLabel>G</sweeperLabel>
                <p><n>MHz</n><v>{mhz}</v>{gen_sweep}</p>
                <p><n>Zo</n><v>50</v></p>
            </element>
        </CIRCUIT>{sweep_state}
    </SmithChartCircuit>
</SimNEC1p0>
"""

# When a sweep is requested, arm it: SCATTERGUN names the swept parameter (without
# it, doSweep=y on the param does nothing) and ROUNDCHART puts the chart in
# swept-trace mode. Confirmed against a SimNEC 5.1a1-saved, actively-sweeping file.
_SWEEP_STATE = (
    "\n        <SCATTERGUN><n>G.MHz</n></SCATTERGUN>"
    "\n        <ROUNDCHART><displayMode>Sweep</displayMode></ROUNDCHART>"
)


def _gen_sweep_block(lo: float, hi: float) -> str:
    """SimNEC ``<sweepParam>`` for the Generator's ``MHz``, enabled (``doSweep
    y``). Mirrors the structure of a SimNEC 5.1a1-saved file (confirmed to load);
    without it SimNEC falls back to its default (disabled) sweep range."""
    return (
        "<sweepParam><name>G.MHz</name><listed>true</listed>"
        "<p><n>points</n><v>100</v></p>"
        f"<p><n>from</n><v>{_fmt(lo)}</v></p>"
        f"<p><n>to</n><v>{_fmt(hi)}</v></p>"
        "<p><n>log</n><v>lin</v></p>"
        "<p><n>doSweep</n><v>y</v></p>"
        "<p><n>expr</n><v>Vary</v><fontScale>1</fontScale><w>640</w><h>360</h>"
        "<relx>0</relx><rely>360</rely><ProgrammingDialog><ThreeSplitPane>"
        "<errDiv>0.3</errDiv><outDiv>0.7</outDiv></ThreeSplitPane>"
        "</ProgrammingDialog></p></sweepParam>"
    )


def export_ssn(
    builder,
    *,
    freq_mhz: float | None = None,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
    sweep: tuple[float, float] | None = None,
    name: str | None = None,
) -> str:
    """Return a SimNEC ``.ssn`` (str) for an antenna-only ``builder``.

    freq_mhz   : Generator frequency in MHz; defaults to ``builder.freq``.
    ground     : same spec as ``export_nec`` / PyNECEngine — None/"free",
                 "pec", ("finite", eps_r, sigma), ("finite-fast", eps_r, sigma).
    seg_per_wl : SimNEC auto-mesh density (segments per wavelength). None leaves
                 SimNEC's default; set it to pin SimNEC's mesh for a convergence
                 comparison (SimNEC re-segments regardless of the deck).
    sweep      : ``(lo_mhz, hi_mhz)`` to enable the Generator's frequency sweep
                 over that band. ``None`` (default) leaves it minimal, so SimNEC
                 uses its own default (disabled) range — the single-point solve
                 at ``freq_mhz`` is still correct.
    name       : block display name (SimNEC's first ``//`` comment). Defaults to
                 the design's short leaf name; keep it ≤ ~12 chars — SimNEC
                 shrinks the font for longer names.

    Raises ``NotImplementedError`` (via ``export_nec``) for networked designs.
    """
    freq_mhz = builder.freq if freq_mhz is None else float(freq_mhz)
    script = build_nec_portal_script(
        builder, freq_mhz=freq_mhz, ground=ground, seg_per_wl=seg_per_wl, name=name
    )
    gen_sweep = (
        "" if sweep is None else _gen_sweep_block(float(sweep[0]), float(sweep[1]))
    )
    sweep_state = "" if sweep is None else _SWEEP_STATE
    return _SSN_TEMPLATE.format(
        equ=_xml_escape(script),
        mhz=_fmt(freq_mhz),
        gen_sweep=gen_sweep,
        sweep_state=sweep_state,
    )


def main(argv=None):
    """CLI: ``python -m antennaknobs.simnec_export <design> [opts]``."""
    import argparse

    from .cli import get_builder, parse_ground

    ap = argparse.ArgumentParser(
        prog="antennaknobs.simnec_export",
        description="Emit a SimNEC (.ssn) circuit for an antenna-only design.",
    )
    ap.add_argument("builder", help="Design name, e.g. dipoles.invvee[:variant]")
    ap.add_argument(
        "--freq", type=float, default=None, help="MHz (default: builder.freq)"
    )
    ap.add_argument(
        "--ground",
        default="free",
        help="free | pec | finite | finite:<eps_r>,<sigma> (default: free)",
    )
    ap.add_argument(
        "--seg-per-wl",
        type=int,
        default=None,
        help="SimNEC auto-mesh density (segments/wavelength)",
    )
    ap.add_argument(
        "--sweep",
        nargs="?",
        const="auto",
        default=None,
        metavar="LO,HI",
        help="Enable the Generator frequency sweep: bare '--sweep' for an auto "
        "band (+/-10%% around --freq), or '--sweep LO,HI' for an explicit MHz range.",
    )
    ap.add_argument(
        "--name",
        default=None,
        help="Block display name (default: design's short leaf name). SimNEC "
        "shrinks the font past ~12 chars, so keep it short.",
    )
    ap.add_argument("--out", default=None, help="Write here (default: stdout)")
    args = ap.parse_args(argv)

    builder = get_builder(args.builder)()
    freq = builder.freq if args.freq is None else args.freq
    sweep = None
    if args.sweep is not None:
        if args.sweep == "auto":
            sweep = (round(freq * 0.9, 6), round(freq * 1.1, 6))
        else:
            parts = args.sweep.split(",")
            if len(parts) != 2:
                ap.error("--sweep expects LO,HI (two MHz values), or bare for auto")
            sweep = (float(parts[0]), float(parts[1]))
    ssn = export_ssn(
        builder,
        freq_mhz=args.freq,
        ground=parse_ground(args.ground),
        seg_per_wl=args.seg_per_wl,
        sweep=sweep,
        name=args.name,
    )
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(ssn)
        print(f"wrote {args.out}")
    else:
        print(ssn, end="")


if __name__ == "__main__":
    main()
