"""Centre-fed doublet on window line, through a balun into a REMOTE L-NETWORK
TUNER — WA7ARK's station on QRZ.

The station: a flat doublet `length_ft` long, `height_ft` up, fed at its
centre with `line_ft` of window line that comes down to a balun at a remote
tuner, whose 50 Ω side goes to the rig on coax (not modelled: the coax sees
50 Ω whenever the tuner matches). Every length is in FEET, the user's units.
Signal path, from the rig:

    rig (50 Ω) → L-network tuner → balun 1:1 or 1:4
               → BalancedLine (window line) → doublet centre gap

The tuner is an L network you set: a series coil ``tuner_l_uH``, a shunt
capacitor ``tuner_c_pF``, and ``tuner_c_side``, which side the capacitor
sits on — across the balun ("balun", for a load resistance above 50 Ω,
stepped down) or across the rig ("rig", for one below 50 Ω, stepped up),
the choice a switched-L auto-tuner's relay makes. The two parts range over
the MFJ-926B remote auto-tuner's published nominal ranges, 0–24.86 µH and
0–3961 pF (manual, "Specifications"), so whatever you or the optimizer set
is a setting that tuner can reach. The stock setting matches the stock
station at 7.15 MHz (SWR 1.005 on bs2, momwire's B-spline solver).

The workflow, as with a manual tuner:

- Pick the measurement frequency and run Optimize there (objective SWR,
  vary ``tuner_l_uH`` and ``tuner_c_pF``; the bands default to the
  measurement frequency). Optimize cannot flip ``tuner_c_side``: if the run
  ends far from SWR 1, the capacitor is on the wrong side for this load —
  switch it and run again. On the stock antenna the capacitor goes across
  the balun on 80, 20 and 10 m and across the rig on 40 m. From the 40 m
  setting the first run on 80 m (3.6 MHz) stops at SWR 4.9; a second run
  from there reaches 1.00 (on the command line, ``--mode root`` with a z0
  objective gets there in one).
- The frequency sweep then shows THAT setting's SWR across the band you are
  on, edge to edge: the parts are fixed, so the curve is how far you can
  QSY before you retune.
- Change band and the parts stay where they were, as on the real box; run
  Optimize again on the new band.

The graphical tune, on the Smith chart, as you would do it by hand: look at
the load, turn the part CLOSEST to the antenna until the point lands on the
circle along which the other part moves it (a circle through Z0), then turn
the other part to slide along that circle to the centre. The measurement
plane ``lc`` (manual mode only) is the node between the two parts, and at it
the chart highlights that circle:

1. Pick the plane ``lc``. What it reads is the load with only the closest
   part applied. With the capacitor across the balun that part is the
   capacitor, and the remaining series coil moves the point along a circle of
   constant resistance: the chart highlights R = 50 Ω (r = 1). With it across
   the rig the closest part is the coil, and the remaining shunt capacitor
   moves the point along a circle of constant conductance: G = 20 mS (g = 1).
   The chart's "Y" button adds the admittance grid that circle belongs to.
2. Turn the closest part (``tuner_c_pF`` across the balun, ``tuner_l_uH``
   across the rig) until the point sits on the highlighted circle. "Sweep
   this knob…" in the knob's menu traces its whole locus, to see where it
   crosses.
3. Pick the plane ``rig`` and turn the other part until the point reaches the
   centre: SWR 1.

The picker names the planes source to antenna: "rig (tuner input)",
"inside tuner (L–C)" (``lc``), "tuner output / balun input" (``tuner``).
On 20 m (14.3 MHz), capacitor across the balun, on the workbench's default
ground (bs2, Sommerfeld average): 39.2 pF puts ``lc`` on the circle
(49.9 − j387 Ω), and 4.31 µH then reads SWR 1.04 at the rig (the coil's Q
leaves R at 51.8 Ω).

From the command line, the same (``--set`` holds a knob that the run does
not vary):

    antennaknobs optimize --builder wire.doublet_remote_tuner --bands 14.2 \
        --params tuner_l_uH tuner_c_pF --set tuner_c_side=balun

What the tuner SEES is the impedance at its antenna jack, after the balun:
the doublet's feed impedance carried down the line and divided by the
balun's ratio (``balun_ratio`` "1:4" divides it by 4). The measurement plane
``tuner`` reads that load as a VNA on the tuner's output jack, whichever side
the capacitor is on; ``lc``, between the tuner's parts, is the graphical
tune's (above).

Where the power goes. The power budget (issue #299) itemizes every lossy
branch from the same solve: the window line (its matched loss plus the extra
the SWR on it costs: the line is a lossy `BalancedLine`, so the mismatch loss
is in the solve, not a correction), the balun, and the tuner's coil, and what
is left reaches the antenna — the power its port accepts, of which a real
ground then absorbs some (that third ledger is the far field's). The loss
assumptions, all knobs (hidden on the workbench, ``--set`` on the command
line):

- antenna wire: ideal by default (``wire_type`` "ideal", as Mike's
  comparison is modelled); a catalog wire adds its ohmic loss as a row of
  its own, on every engine;
- line: ``window-450``'s matched loss, k1 0.035 / k2 0.0002 (dB per 100 ft
  = k1·√f + k2·f), DRY; wet window line loses several times that;
- tuner coil Q 200 (``tuner_ql``), as the other tuner designs here; the
  capacitors ideal (``tuner_qc`` 0: relay-switched fixed capacitors, Q in
  the thousands);
- balun: a CURRENT balun, whose windings are a short transmission line that
  the differential current does not flux the core through, so its loss is
  winding resistance, 0.3 Ω referred to the line side (``balun_r_ohm``:
  about 3 m of #14 copper at the 7 MHz skin depth, held constant over the
  bands); no magnetizing branch (``balun_lmag_uH`` 0). Give it one, with
  ``balun_qlmag`` for its core loss, to model a voltage balun.

Mesh: the geometry is in feet, so the design has no design frequency (the
workbench shows no band row). The wire meshes at the density of the top of
10 m, 29.7 MHz (``MESH_MHZ``), on every band, so a band change never
remeshes and every band solves on a mesh fine enough for the highest.

Band by band: what would an AUTO-tuner do? Mike's question is whether a
remote auto-tuner at the bottom of this line, with this balun, matches every
band, and where the power goes. The hidden knob ``tuner_mode`` "auto" puts
the tuner in its auto mode: at the frequency it is solved at it picks its
own parts within ``tuner_l_max_uH`` / ``tuner_c_max_pF`` (the same MFJ-926B
ranges; `station.l_network_tuner(tune_to=50, shunt_at="auto")`, AK#1646),
capacitor side included. A band whose exact match needs more than those
ranges is FLAGGED: the tuner tunes for the lowest SWR its parts reach, says
so in an advisory, and the SWR at the rig is no longer 1. (That manual also
states a 6–1600 Ω matching range; the parts range is the physics of it, so
the parts are what is checked.)

The design's analysis ``tuner per band`` solves at each of Mike's
frequencies in the auto mode, for both balun ratios, and its Table prints,
per frequency, the load at the tuner, the coil and capacitor the auto-tuner
picks and the side the capacitor sits on, the SWR at the rig, each share of
the power the 50 Ω rig makes AVAILABLE (reflected, each loss, reaching the
antenna; a row adds to 100 %), and a "!!" line for any band it cannot match,
beside the impedance at the rig and at the tuner's jack:

    antennaknobs analyze --builder wire.doublet_remote_tuner --analysis "tuner per band"

The same per-band table at any knob setting (``band-loss`` puts the tuner in
its auto mode, the design's ``band_loss_params``):

    antennaknobs band-loss --builder wire.doublet_remote_tuner

Both are over Sommerfeld average ground (13 / 0.005 S/m, the command line's
default ground).

Mike's example is the stock design: 130 ft at 30 ft, 30 ft of Wireman #552
window line with his measured velocity factor 0.97 and the nominal ~400 Ω
he gives for it. (The catalog's ``window-450`` entry is 450 Ω, VF 0.91; #552
gets no catalog entry of its own because no citable source for its Z0 and
loss turned up, so the line's loss coefficients are ``window-450``'s, and
Z0 / VF are his.) What the auto-tuner picks, on bs2 (extended kernel off),
Sommerfeld 13 / 0.005, 1:1 balun:

    MHz     load at the tuner   C across   coil       capacitor  reaches antenna
    3.6      73.9 + j293.9 Ω    balun      10.7 µH    317.5 pF   95.3 %
    7.0      27.2 −  j79.8 Ω    rig        2.38 µH    408.3 pF   92.1 %
    14.0    211.8 + j712.7 Ω    balun      4.00 µH     46.4 pF   92.6 %
    28.0     98.1 + j186.8 Ω    balun      0.803 µH    59.7 pF   94.9 %

Mike's own EZNEC/AutoEZ table has 75.60 + j289.84 Ω at 3.6 MHz, where the two
agree (and so do the parts: his 10.37 µH / 323.4 pF); at 7, 14 and 28 MHz
his loads differ (62.75 − j26.89, 561.21 + j443.56, 195.33 − j3.91 Ω), and
with them his parts. Fed HIS loads, the lossless tuner arithmetic chooses his
parts to within 2 %, so the tuner agrees; the loads are what differ. PyNEC
solves this same design to within 1.2 % of these bs2 loads. None of the
changes tried reproduces his upper bands (line Z0 250-700 Ω and its length
fitted freely, wire radius 0.5-2 mm, three grounds, doublet 130-142 ft), so
the difference is in the antenna model (his ground, wire and any insulation
are not stated), not in the line or the tuner. One consequence: on 40 m the
load here is below 50 Ω, so even with the 1:1 balun the capacitor belongs on
the rig side there, where Mike's never switches. With a 1:4 balun every load
is a quarter of the 1:1 load, as in his table (the balun's winding
resistance is on its line side, so the ratio stays exact).

Choosing the line (and the balun): with an auto-tuner every band matches, so
the figure of merit is the WORST band's share reaching the antenna. The
multi-band optimizer cannot ask that (its objectives are impedance
objectives, which a retuning tuner meets on every band whatever the knobs
do), so ``band-loss --search`` runs an outer search: every band at each line
length, the tuner retuned at each, a grid then a bounded refinement
(`antennaknobs.band_loss`). The line has to reach the tuner on the ground,
so the search starts at 30 ft:

    antennaknobs band-loss --builder wire.doublet_remote_tuner \
        --each balun_ratio=1:1,1:4 --search line_ft=30:100:1

For Mike's antenna (bs2, the stock losses): with the 1:1 balun, 30 ft is
already the best line (worst band 25 MHz, 91.9 % reaches the antenna; longer
lines only add loss there); with the 1:4 balun, 30 ft gives 91.4 % (worst
7 MHz) and 35.2 ft gives 92.2 % (worst then 25 MHz), the best of the four.
The differences are under a percentage point — a tenth of a dB — which is
the answer: on this antenna an auto-tuner at the bottom of 30 ft of window
line is within a whisker of the best this line and these baluns can do.

Caveats:

- The balun has no magnetizing inductance by default (a current balun, see
  above), so the 1:4 load is exactly the 1:1 load over 4. A voltage balun's
  magnetizing inductance shunts the load at the low bands.
- With the coil's Q, a load whose resistance sits within a few ohms of 50
  can be out of an L network's exact reach from either side; the auto mode
  then tunes for best effort (SWR 1.00-something), which the table says.
- The line's common-mode return ``line_zcomm`` is required by the solve (the
  balun's secondary floats), and it does not move the result: the doublet is
  symmetric about its feed, so no common-mode current flows.
- In the auto mode the optimizer refuses a match objective at the tuner's
  own frequency: the tuner meets it there whatever the knobs do (AK#1664).
  The manual tuner has no such refusal: its parts are what Optimize varies.
- Engines: bs2 and PyNEC (they agree to 1.2 % on the tuner's load).
  NEC-5 refuses it by name: its reducer route cannot address the floating
  centre gap.
"""

import math
from types import MappingProxyType

import antennaknobs.analyses as an
from antennaknobs import AntennaBuilder
from antennaknobs.network import (
    BalancedLine,
    Composite,
    Driven,
    FloatingBalun,
    Instance,
    Network,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    TwoPort,
    Wire,
)
from antennaknobs.schematic import series, shunt
from antennaknobs.station import l_network_tuner
from antennaknobs.wire_catalog import WIRES, cable_from_catalog, wire_from_catalog

#: One foot, in metres.
FT = 0.3048

#: The impedance a ``balun_ratio`` divides the tuner's load by: the line side
#: to the tuner side, as Mike writes it.
BALUN_RATIOS = {"1:1": 1.0, "1:4": 4.0}

#: ``tuner_c_side``: where the capacitor sits, as `l_network_tuner`'s
#: ``shunt_at`` spells it. "balun" is across the tuner's antenna jack (the
#: balun side: steps a load resistance above 50 Ω down), "rig" across its
#: 50 Ω input (steps a load below 50 Ω up) — the choice a switched-L
#: auto-tuner's relay makes.
C_SIDES = {"balun": "out", "rig": "rig"}

#: The measurement plane between the manual tuner's two parts: the point
#: the graphical tune moves onto the Smith chart's highlighted circle.
LC_PLANE = "lc"

#: The rig's coax, and what the tuner matches to.
TUNE_TO_OHMS = 50.0

#: The MFJ-926B remote auto-tuner's published nominal parts ranges (manual,
#: "Specifications"): the manual knobs' ranges, so Optimize only finds a
#: setting this tuner can be set to, and the auto mode's ranges.
MFJ_L_MAX_UH = 24.86
MFJ_C_MAX_PF = 3961.0

#: The wire meshes at this frequency's density (`segs_for` against its
#: quarter wave): the top of 10 m, the highest band the station is used on,
#: so one mesh serves every band and a band change never remeshes.
MESH_MHZ = 29.7

#: Mike's frequencies (MHz), the rows of his table: every HF band from 80 m
#: to 10 m, the wide bands at their edges and middle.
BAND_FREQS = (
    3.6, 3.8, 4.0, 5.3, 7.0, 7.15, 7.3, 10.12, 14.0, 14.15, 14.3,
    18.15, 21.0, 21.2, 21.4, 25.0, 28.0, 28.25, 28.5,
)  # fmt: skip

#: The window line's loss: the catalog's representative window line.
_WINDOW = cable_from_catalog("window-450")


def manual_l_tuner(l_uH, c_pF, c_side, *, ql=None, qc=None) -> Composite:
    """The manual L network, with the node BETWEEN its parts as a formal,
    ``lc``, so the design can name it a measurement plane. Formals ``rig``,
    ``lc``, ``out``; electrically `station.l_network_tuner` with fixed parts.

    Picking a plane drops everything on the source side and keeps a shunt
    AT the plane node (`plane.driven_at`), so each part sits where the cut
    does the right thing, and an ideal short (a `TwoPort` with no element,
    Z = 0) carries the node to the other end of the box:

    - ``c_side`` "balun": rig —coil— lc (capacitor across it) —short— out.
      At ``lc`` the coil is gone and the capacitor stays: the load with the
      part closest to the antenna applied. At ``out`` the capacitor goes with
      the upstream, so the ``tuner`` plane is the bare load.
    - ``c_side`` "rig": rig (capacitor across it) —short— lc —coil— out. At
      ``lc`` the capacitor goes with the upstream and the coil stays.
    """
    # The short is written toward ``lc`` on both sides, so each of the four
    # branches has a power-budget label of its own (``budget_labels``).
    coil = TwoPort(a="lc", b="out", l=l_uH * 1e-6, ql=ql)
    short = TwoPort(a="lc", b="rig")
    if c_side == "balun":
        coil = TwoPort(a="rig", b="lc", l=l_uH * 1e-6, ql=ql)
        short = TwoPort(a="out", b="lc")
    cap = Shunt(port="lc" if c_side == "balun" else "rig", c=c_pF * 1e-12, qc=qc)
    draw_l = series("inductor", f"{l_uH:g} µH")
    draw_c = shunt("capacitor", f"{c_pF:g} pF")
    return Composite(
        ports=("rig", "lc", "out"),
        branches=(coil, cap, short),
        # Drawn from the rig side: the shunt comes first when it sits there.
        schematic=(draw_l, draw_c) if c_side == "balun" else (draw_c, draw_l),
    )


class Builder(AntennaBuilder):
    #: The bands ``antennaknobs band-loss`` evaluates when given none.
    band_freqs = BAND_FREQS
    #: Knobs ``antennaknobs band-loss`` sets before its own ``--set``: it asks
    #: what an AUTO-tuner would do on every band, so the tuner tunes itself.
    band_loss_params = MappingProxyType({"tuner_mode": "auto"})

    default_params = MappingProxyType(
        {
            "freq": 7.15,
            # Mike's example: a 130 ft doublet 30 ft up.
            "length_ft": 130.0,
            "height_ft": 30.0,
            # The antenna wire: "ideal" (PEC, the 0.5 mm idealization, as
            # Mike's comparison is modelled), or a catalog wire, whose ohmic
            # loss is then its own row of the power budget.
            "wire_type": "ideal",
            # 30 ft of Wireman #552 window line: his measured VF and the
            # nominal Z0 he gives; the loss is the catalog window line's.
            "line_ft": 30.0,
            "line_zdiff": 400.0,
            "line_vf": 0.97,
            "line_k1": _WINDOW.k1,
            "line_k2": _WINDOW.k2,
            # The line's common-mode return (issue #576): the balun's
            # secondary floats, so the solve needs it; the symmetric doublet
            # draws no common-mode current, so its value does not matter.
            "line_zcomm": 250.0,
            "balun_ratio": "1:1",
            # The tuner, set by hand: its coil, its capacitor, and the side
            # the capacitor sits on. Stock: the stock station matched at
            # 7.15 MHz, SWR 1.005 (bs2, Sommerfeld 13 / 0.005). Source: the
            # parts the auto mode's L-match arithmetic chooses there, with
            # the coil's Q (``tuner_mode`` "auto", read off
            # `auto_match.tuner_design`: 1.867 µH, 413.4 pF), rounded to the
            # knobs' steps. 40 m's load is below 50 Ω (26.4 − j59.0 Ω), so
            # the capacitor is on the rig side.
            "tuner_l_uH": 1.87,
            "tuner_c_pF": 413.0,
            "tuner_c_side": "rig",
            # "manual": the parts above. "auto": the tuner tunes itself at
            # the frequency it is solved at (`l_network_tuner(tune_to=50,
            # shunt_at="auto")`, AK#1646) within the ranges below, as the
            # remote auto-tuner does when keyed; the per-band analysis and
            # `band-loss` set it. Hidden: on the workbench you tune by hand
            # (or with Optimize).
            "tuner_mode": "manual",
            # The auto mode's parts ranges (the manual knobs' ranges are the
            # same MFJ-926B limits, in ui_params). Knobs, so band-loss can ask
            # about an auto-tuner with less reach (--set tuner_c_max_pF=...).
            "tuner_l_max_uH": MFJ_L_MAX_UH,
            "tuner_c_max_pF": MFJ_C_MAX_PF,
            # Coil and capacitor Q; 0 is an ideal part. The coil at Q 200, as
            # the other tuner designs here; the capacitors ideal (relay-
            # switched fixed capacitors, whose Q runs to the thousands).
            "tuner_ql": 200.0,
            "tuner_qc": 0.0,
            # The balun (`FloatingBalun`): a current balun, whose windings
            # are a short transmission line the differential current does
            # not flux the core through, so its loss is the winding
            # resistance, referred to the line side: about 3 m of #14
            # copper at the 7 MHz skin depth (≈ 0.3 Ω), held constant over
            # the bands. A magnetizing branch (a voltage balun's core loss)
            # is off: 0 µH is none.
            "balun_r_ohm": 0.3,
            "balun_lmag_uH": 0.0,
            "balun_qlmag": 0.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": TUNE_TO_OHMS,
                    # The manual tuner's power-budget rows, by part: the
                    # structural labels of `manual_l_tuner`'s branches on
                    # either capacitor side (the jack is the ``tuner`` node).
                    "budget_labels": {
                        "tuner: TwoPort rig→lc": "coil",
                        "tuner: TwoPort lc→tuner": "coil",
                        "tuner: Shunt lc": "capacitor",
                        "tuner: Shunt rig": "capacitor",
                        "tuner: TwoPort tuner→lc": "wire to the lc plane",
                        "tuner: TwoPort lc→rig": "wire to the lc plane",
                    },
                    # The sweep runs edge to edge of the band you are on: the
                    # parts are fixed, so the curve is how far you can QSY in
                    # the band before you retune (doublet_ladder_tuner's
                    # policy).
                    "sweep_policy": {"anchor": "meas_freq", "band_locked": True},
                    # On the workbench: the antenna and its wire, the line's
                    # length, the balun and the tuner's three controls. Every
                    # other assumption stays a knob (the CLI's --set,
                    # band-loss), pinned at its default here.
                    "length_ft": {"min": 30.0, "max": 300.0, "unit": "ft"},
                    "height_ft": {"min": 10.0, "max": 120.0, "unit": "ft"},
                    "line_ft": {"min": 1.0, "max": 200.0, "unit": "ft"},
                    "line_zdiff": {
                        "hidden": True,
                        "min": 200.0,
                        "max": 700.0,
                        "step": 10.0,
                    },
                    "line_vf": {"hidden": True, "min": 0.80, "max": 1.0, "step": 0.01},
                    "line_k1": {"hidden": True, "min": 0.0, "max": 0.2},
                    "line_k2": {"hidden": True, "min": 0.0, "max": 0.01},
                    "line_zcomm": {
                        "hidden": True,
                        "min": 0.0,
                        "max": 400.0,
                        "step": 25.0,
                    },
                    "balun_ratio": {"enum_options": tuple(BALUN_RATIOS)},
                    "wire_type": {"enum_options": ("ideal", *sorted(WIRES))},
                    # The MFJ-926B's ranges: Optimize searches inside them.
                    "tuner_l_uH": {
                        "min": 0.0,
                        "max": MFJ_L_MAX_UH,
                        "step": 0.01,
                        "unit": "µH",
                    },
                    "tuner_c_pF": {
                        "min": 0.0,
                        "max": MFJ_C_MAX_PF,
                        "step": 1.0,
                        "unit": "pF",
                    },
                    "tuner_c_side": {"enum_options": tuple(C_SIDES)},
                    "tuner_mode": {
                        "hidden": True,
                        "enum_options": ("manual", "auto"),
                    },
                    "tuner_l_max_uH": {
                        "hidden": True,
                        "min": 1.0,
                        "max": 100.0,
                        "unit": "µH",
                    },
                    "tuner_c_max_pF": {
                        "hidden": True,
                        "min": 100.0,
                        "max": 10000.0,
                        "unit": "pF",
                    },
                    "tuner_ql": {"hidden": True, "min": 0.0, "max": 400.0},
                    "tuner_qc": {"hidden": True, "min": 0.0, "max": 5000.0},
                    "balun_r_ohm": {
                        "hidden": True,
                        "min": 0.0,
                        "max": 5.0,
                        "unit": "Ω",
                    },
                    "balun_lmag_uH": {
                        "hidden": True,
                        "min": 0.0,
                        "max": 500.0,
                        "unit": "µH",
                    },
                    "balun_qlmag": {"hidden": True, "min": 0.0, "max": 200.0},
                }
            ),
        }
    )

    def build_analyses(self):
        """Mike's table: what an auto-tuner picks at each of his
        frequencies, both balun ratios, read at the rig and at the tuner's
        antenna jack. The tuner is in its auto mode and the frequency is
        swept as the ``freq`` KNOB, so every point is its own build and the
        tuner tunes there; on the command line the Table also prints, per
        rig curve, the load the tuner saw, the parts it chose and where the
        power went (`analysis_run`)."""
        auto = {"tuner_mode": "auto"}
        return [
            an.Analysis(
                "tuner per band",
                an.Sweep("freq", values=BAND_FREQS),
                cross=(
                    an.Cross(
                        states=(
                            an.State("1:1 balun", balun_ratio="1:1", **auto),
                            an.State("1:4 balun", balun_ratio="1:4", **auto),
                        )
                    ),
                    # At the rig (50 Ω where the tuner matches) and at the
                    # tuner's antenna jack (the load it sees): the second is
                    # the per-band load in the workbench's Table too.
                    an.Cross(planes=("rig", "tuner")),
                ),
                views=(an.Table(),),
                ground="finite:13,0.005",
            ),
        ]

    def build_wire_material(self):
        return None if self.wire_type == "ideal" else wire_from_catalog(self.wire_type)

    # ---- geometry -------------------------------------------------------
    def build_wires(self):
        arm = 0.5 * self.length_ft * FT
        z = self.height_ft * FT
        # The geometry is in feet, so there is no design frequency: the wire
        # meshes at 10 m's density (MESH_MHZ) whatever band it is used on.
        quarter_wave = 0.25 * self.c_light_mhz_m / MESH_MHZ
        n = self.segs_for(2.0 * arm, quarter_wave)
        # One flat wire along y; the feed is a floating gap at its centre,
        # both terminals exposed for the balanced line.
        return [Wire((0.0, -arm, z), (0.0, arm, z), n, name="feed")]

    # ---- feed network ---------------------------------------------------
    def balun_n(self) -> float:
        """The balun's VOLTAGE ratio, `FloatingBalun`'s ``n``: the square
        root of its impedance ratio, so the tuner sees Z_line / ratio."""
        return math.sqrt(BALUN_RATIOS[self.balun_ratio])

    def tuner(self):
        """The L network: the knobs' parts, or (``tuner_mode`` "auto") the
        auto-tuner that picks its own at the frequency it is solved at."""
        ql, qc = self.tuner_ql or None, self.tuner_qc or None
        if self.tuner_mode == "auto":
            return l_network_tuner(
                tune_to=TUNE_TO_OHMS,
                tune_at_mhz=float(self.freq),
                mode="low",
                shunt_at="auto",
                ql=ql,
                qc=qc,
                l_max_uH=self.tuner_l_max_uH,
                c_max_pF=self.tuner_c_max_pF,
            )
        if self.tuner_mode != "manual":
            raise ValueError(
                f"tuner_mode={self.tuner_mode!r}: 'manual' (the knobs' parts) "
                "or 'auto' (the tuner tunes itself)"
            )
        if self.tuner_c_side not in C_SIDES:
            raise ValueError(
                f"tuner_c_side={self.tuner_c_side!r}: one of {tuple(C_SIDES)}"
            )
        return manual_l_tuner(
            self.tuner_l_uH, self.tuner_c_pF, self.tuner_c_side, ql=ql, qc=qc
        )

    def plane_labels(self) -> dict[str, str]:
        """What the measurement-plane picker shows for each plane, source to
        antenna: the rig, the node inside the tuner between its two parts,
        and the tuner's antenna jack (the balun's tuner-side terminals)."""
        return {
            "rig": "rig (tuner input)",
            LC_PLANE: "inside tuner (L–C)",
            "tuner": "tuner output / balun input",
        }

    def smith_targets(self) -> dict[str, str]:
        """The circle the Smith chart highlights at each measurement plane:
        at ``lc`` (manual mode), the circle the tuner's REMAINING part moves
        the point along, which passes through Z0. With the capacitor across
        the balun the remaining part is the series coil, which moves along a
        constant-R circle: "r", R = Z0. With it across the rig the remaining
        part is the shunt capacitor, which moves along a constant-G circle:
        "g", G = 1/Z0. Served per solve (``smith_target``), so it follows
        ``tuner_c_side``. The auto mode has no ``lc`` plane."""
        if self.tuner_mode != "manual":
            return {}
        return {LC_PLANE: "r" if self.tuner_c_side == "balun" else "g"}

    def build_network(self):
        ports = {
            "feed": PortOnWireFloating("feed"),
            "rig": PortVirtual("rig"),
            # The tuner's antenna jack: the balun's unbalanced side.
            "tuner": PortVirtual("tuner"),
            "liL": PortVirtual("liL"),  # balun's balanced side → line
            "liR": PortVirtual("liR"),
        }
        tuner = self.tuner()
        bind = {"rig": "rig", "out": "tuner"}
        if "lc" in tuner.ports:
            # The node between the manual tuner's two parts, a measurement
            # plane of its own (see `manual_l_tuner`). The auto-tuner owns
            # its own topology, so it has none.
            ports[LC_PLANE] = PortVirtual(LC_PLANE)
            bind["lc"] = LC_PLANE
        return Network(
            ports=ports,
            branches=[
                Instance("tuner", tuner, **bind),
                FloatingBalun(
                    primary="tuner",
                    a="liL",
                    b="liR",
                    n=self.balun_n(),
                    r=self.balun_r_ohm or None,
                    lmag=self.balun_lmag_uH * 1e-6 or None,
                    qlmag=self.balun_qlmag or None,
                ),
                BalancedLine(
                    a1="liL",
                    a2="liR",
                    b1="feed.p",
                    b2="feed.n",
                    zdiff=self.line_zdiff,
                    length=self.line_ft * FT,
                    vf=self.line_vf,
                    k1=self.line_k1,
                    k2=self.line_k2,
                    zcomm=self.line_zcomm or None,
                ),  # fmt: skip
            ],
            sources=[Driven(port="rig", voltage=1 + 0j)],
        )
