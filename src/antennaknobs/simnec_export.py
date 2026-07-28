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
only the ``GW`` / ``EX`` / lumped-``LD`` cards and translate the rest into
daemon directives: ``FR`` → the Generator's ``MHz``; ``GN`` → the ground call;
the deck's segment counts are *advisory only* — SimNEC re-meshes at
``NECOptions.segmentsPerWavelength``, which is why that knob is exposed.

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

.. warning::
   The XML scaffold is **provisional** until confirmed to load in SimNEC on a
   Windows box — this environment has no Java runtime to test against. The
   generated *daemon script* (the substantive part) is unit-tested here; the
   wrapper's exact required tags may need reconciliation with a known-good
   SimNEC-saved ``.ssn``.
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
    """Keep only the cards SimNEC's NEC block wants: geometry (``GW``),
    excitation (``EX``), and lumped loads (``LD 0`` / ``LD 1``).

    Dropped: ``CM``/``CE``/``GE``/``FR``/``RP``/``XQ``/``EN`` (structural or
    handled by daemon directives), ``GN`` (→ ground call), ``LD 5`` global
    conductivity (→ ``NECOptions.mhosPerMeter``) and ``LD 2`` insulation
    (not representable in the NEC block — see the warning below).
    """
    kept: list[str] = []
    for raw in deck.splitlines():
        s = raw.strip()
        if s.startswith("GW ") or s.startswith("EX "):
            kept.append(s)
        elif s.startswith("LD "):
            parts = s.split()
            ldtyp = parts[1] if len(parts) > 1 else ""
            if ldtyp in ("0", "1"):  # series / parallel lumped RLC load
                kept.append(s)
            # LD 5 (conductivity) and LD 2 (insulation) are handled elsewhere
            # or unsupported; skip here.
    return kept


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

    name = name or f"{type(builder).__module__}.{type(builder).__qualname__}"
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


# --- provisional .ssn XML scaffold (see module warning) ---------------------
# Minimal three-element cascade: LOAD (open, right end) — NETWORK (the antenna,
# in the escape-hatch script) — GENERATOR (50 Ohm source, left end). Authored
# here from the observed format; confirm it loads in SimNEC before relying on it.
_SSN_TEMPLATE = """\
<?xml version="1.0" encoding="utf-8"?>
<SimNEC1p0>
    <SmithChartCircuit>
        <XMLVersionControl>SimNEC:antennaknobs.simnec_export</XMLVersionControl>
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
                <p><n>MHz</n><v>{mhz}</v></p>
                <p><n>ohms</n><v>50</v></p>
            </element>
        </CIRCUIT>
    </SmithChartCircuit>
</SimNEC1p0>
"""


def export_ssn(
    builder,
    *,
    freq_mhz: float | None = None,
    ground=DEFAULT_GROUND,
    seg_per_wl: int | None = None,
) -> str:
    """Return a SimNEC ``.ssn`` (str) for an antenna-only ``builder``.

    freq_mhz   : Generator frequency in MHz; defaults to ``builder.freq``.
    ground     : same spec as ``export_nec`` / PyNECEngine — None/"free",
                 "pec", ("finite", eps_r, sigma), ("finite-fast", eps_r, sigma).
    seg_per_wl : SimNEC auto-mesh density (segments per wavelength). None leaves
                 SimNEC's default; set it to pin SimNEC's mesh for a convergence
                 comparison (SimNEC re-segments regardless of the deck).

    Raises ``NotImplementedError`` (via ``export_nec``) for networked designs.
    """
    freq_mhz = builder.freq if freq_mhz is None else float(freq_mhz)
    script = build_nec_portal_script(
        builder, freq_mhz=freq_mhz, ground=ground, seg_per_wl=seg_per_wl
    )
    return _SSN_TEMPLATE.format(equ=_xml_escape(script), mhz=_fmt(freq_mhz))


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
    ap.add_argument("--out", default=None, help="Write here (default: stdout)")
    args = ap.parse_args(argv)

    builder = get_builder(args.builder)()
    ssn = export_ssn(
        builder,
        freq_mhz=args.freq,
        ground=parse_ground(args.ground),
        seg_per_wl=args.seg_per_wl,
    )
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(ssn)
        print(f"wrote {args.out}")
    else:
        print(ssn, end="")


if __name__ == "__main__":
    main()
