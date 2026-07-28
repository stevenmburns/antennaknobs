"""PROTOTYPE: AntennaKNoBs antenna-only design -> SimNEC .ssn (issue #600).

Validated: SimNEC 5.1a1 loaded a generated .ssn and solved it, tracking the
AntennaKNoBs/PyNEC segment-convergence curve exactly (segPerWl 40 -> 181+j573,
120 -> 188+j583).

HOW IT WORKS
  A .ssn is XML with three circuit <element>s (LOAD / NETWORK / GENERATOR); the
  antenna lives inside the NETWORK element's escape-hatch <equ> script, as a NEC
  deck between `NEC2` and `NECEND`. Recipe:
    1. export_nec(builder)  -> pull GW*/GN?/FR/EX lines
    2. splice them between NEC2/NECEND in a template .ssn
    3. set generator MHz
    4. uncomment SommerfeldGround(sigma, eps_r)   for finite ground
    5. uncomment NECOptions.segmentsPerWavelength = N  to control the auto-mesh

TEMPLATE DEPENDENCY (fresh environment!)
  This prototype reuses a SimNEC-saved .ssn as the template (originally
  ~/.SimNEC/5/1/lastCircuit.ssn). That file is NOT in the repo. To run this you
  need ANY antenna-only .ssn saved from SimNEC to point TEMPLATE at. Issue #600
  is to promote this into antennaknobs.simnec_export with a clean BUNDLED
  minimal template (no dependency on a user's saved file) + a CLI.

  Network element XML types already reverse-engineered for a phase-2 (full
  networked export): SERIES_TLINE (Zo/VFnom/ft/~deg/k0..k2/'/100f' loss),
  SERIES_CAP (F/Q/@MHz), SHUNT_IND (H/Q/@MHz).
"""

import re

from antennaknobs.nec_export import export_nec

TEMPLATE = None  # set to a SimNEC-saved antenna-only .ssn path before running


def _cards(builder, ground):
    """GW*/GN?/FR/EX lines SimNEC honors, in deck order, from export_nec."""
    buckets = {"GW": [], "GN": [], "FR": [], "EX": []}
    for ln in export_nec(builder, ground=ground, include_rp=False).splitlines():
        s = ln.strip()
        for key in buckets:
            if s.startswith(key):
                buckets[key].append(s)
    return "\n".join(buckets["GW"] + buckets["GN"] + buckets["FR"] + buckets["EX"])


def export_ssn(
    builder, out_path, *, freq_mhz, ground="free", seg_per_wl=None, template=None
):
    template = template or TEMPLATE
    if not template:
        raise ValueError("Set TEMPLATE to a SimNEC-saved antenna-only .ssn (see #600).")
    xml = open(template, encoding="utf-8").read()
    cards = _cards(builder, ground)
    xml = re.sub(
        r"(NEC2\n).*?(\nNECEND)",
        lambda m: m.group(1) + cards + m.group(2),
        xml,
        count=1,
        flags=re.S,
    )
    if isinstance(ground, tuple) and len(ground) == 3:
        _, eps_r, sigma = ground
        xml = xml.replace(
            "//SommerfeldGround(0.005, 13);", f"SommerfeldGround({sigma}, {eps_r});"
        )
    if seg_per_wl is not None:
        xml = xml.replace(
            "//NECOptions.segmentsPerWavelength = 20;",
            f"NECOptions.segmentsPerWavelength = {seg_per_wl};",
        )
    xml = re.sub(r"(<n>MHz</n><v>)[^<]*(</v>)", rf"\g<1>{freq_mhz}\g<2>", xml, count=1)
    open(out_path, "w", encoding="utf-8").write(xml)
    return cards


if __name__ == "__main__":
    from antennaknobs.designs.wire.doublet_ladder_tuner import Builder
    from antennaknobs.network import Driven, Network, PortOnWire, Wire

    YT = 13.400300629701409

    class DipoleOnly(Builder):
        def build_wires(self):
            return [Wire((0, -YT, 10.0), (0, YT, 10.0), n_seg=None, name="feed")]

        def build_network(self):
            return Network(
                ports={"feed": PortOnWire("feed")},
                branches=[],
                sources=[Driven(port="feed")],
            )

    if not TEMPLATE:
        print(
            "Set TEMPLATE to a SimNEC-saved .ssn first (see module docstring / #600)."
        )
    else:
        b = DipoleOnly(dict(Builder.default_params))
        b.nominal_nsegs = 120
        cards = export_ssn(b, "out.ssn", freq_mhz=7.1, ground="free", seg_per_wl=120)
        print("wrote out.ssn with NEC cards:\n" + cards)
