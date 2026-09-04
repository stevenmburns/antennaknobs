"""Ground-mounted quarter-wave vertical over a BURIED radial screen — the
classic 40 m base-fed vertical, modelled with the radials where they
actually are: in the dirt (momwire#524 phase 2, the crossing serve).

Every other vertical in this catalog either stands on an idealised ground
plane or lifts its radials into the air, because a wire that CROSSES the
air/soil interface is the hard case: the current is continuous through the
node, but the Green's function is not. momwire's crossing serve solves that
node directly, so this design is the one that models what a real ham
actually builds — a radiator bonded at the feedpoint to radials lying a
spade's depth down.

    z = +height    T          radiator, ~lambda/4, base-fed
                   |
    z = 0          N          THE NODE — the crossing junction
                   |          (rise, `depth` long)
    z = -depth  ---H---       buried hub; `n_radials` radials fan out
                 /   \\        horizontally at `depth`, free at their tips

GEOMETRY CONVENTIONS, and why every one of them is load-bearing. The
crossing serve's scope is narrow, and a deck outside it is REFUSED by name
rather than silently approximated:

  * Every segment is purely horizontal or purely vertical. The radial-to-
    rise transition is a right-angle bend at the hub, never a slant: a
    tilted segment would carry current across the interface at an angle
    the corner regularization has no measured convention for.
  * ONE wire radius across the whole deck (so no per-wire ``spec``, and
    no ``build_wire_material`` override) — the corner's rho_eff =
    sqrt(rho^2 + a^2) regularization is defined for a single radius.
  * Exactly ONE crossing junction, the node at z = 0, with exactly ONE
    above member (the radiator) and ONE below member (the rise) — the
    simplest shape the crossing serve has. A second above member is an
    above-tent x above-tent corner, which is refused.
  * The radial tips stay free — nothing else touches or crosses z = 0.

``n_radials`` GOES DOWN TO 1. It used to floor at 2, and the reason was
never physics: antennaknobs derived momwire's junction list from
wire-endpoint degree, so a single shared rise left the node at degree 2, the
polyline walk threaded straight through it, and momwire received one polyline
crossing the interface mid-span — the refusal. Issue #1109 ends a polyline at
every wire end lying in the ground plane, so the node is a declared junction
at any radial count. The upper bound of 4 is the fan widening's own
adjudicated bank.

THE SCREEN IS ONE RISE TO A BURIED HUB (issue #1108). Radials meet at
(0, 0, -depth), and a single graded rise carries their combined current to
the node. That is a conductor someone actually builds, and it is the spelling
every engine here can take: NEC-5 accepts it (it refuses coincident wires),
razor's tent basis sees one column rather than N identical ones
(momwire#846), and momwire's crossing serve reads the node as a 1-above x
1-below junction.

The pre-#1108 spelling — N COINCIDENT rises, one per radial — survives as the
``bundle`` variant, and it is a DIFFERENT CONDUCTOR rather than a different
mesh: a bundle of N coincident thin wires is not one wire of the same radius,
which is momwire's fan-widening adjudication (momwire#524 phase 2). The two
are never gated against each other. Every number this design banked before
2026-09-03 was measured on the bundle and is attributed to it below; the size
of the difference is smaller than it looks, and QUADRATURE says why.

FEED. The house eps-gap idiom, verbatim: a short driven wire at the foot
of the radiator with the radiator stacked on top. That is the physically
right place — a ground-mounted vertical IS fed at its base — and it
survives the crossing scope, because the gap's upper node is degree 2 and
merges into the radiator's polyline instead of becoming a second above-side
junction. Do NOT reach for ``ex=`` on the full-length radiator as a way to
avoid a stub: a whole-wire excitation lands at that wire's MIDPOINT, which
would silently model a mid-element shunt tap (a different, much higher-Z
antenna) rather than a base feed.

REQUIRES A FINITE GROUND. Buried conductors only exist under a Sommerfeld
half-space, which antennaknobs chooses at SOLVE time, not in the design:
pass ``--ground finite:13,0.005`` (or another eps_r/sigma pair). Under
``free`` or ``pec`` the radials are just wires in the air or shorted to
the image plane, and the answer is meaningless. Expect a long momwire
solve (the mixed-medium fill takes seconds warm, minutes cold); a local
NEC-5 (``--engine nec5``, needs ``$NEC5_EXE``) solves its convention in
under a second.

THREE SPELLINGS, AND WHAT EACH ENGINE DOES WITH THEM. The screen can be
spelled three ways, and they are DIFFERENT STRUCTURES, not meshes of one:

  * The DEFAULT (connected, hub) convention above: N radials to a buried hub,
    ONE rise to the node, junction-joined to the monopole at z = 0 — the
    crossing junction. **Every engine here takes the geometry.** momwire's
    B-spline serves it (the #524 phase-2 crossing serve), NEC-5 builds the
    same conductor (issue #1108; the graded wires reach it as consecutive GW
    cards, issue #1110), and razor-2p constructs it and REFUSES it by name:
    by decision (2026-09-03, momwire#813/#814) razor-2p is the above-ground
    twin of licensed NEC-5 and B-spline is the buried and contact engine —
    the underground reference is measurement (Brown-Lewis-Epstein 1937,
    momwire#838), not the binary. What momwire and NEC-5 then DISAGREE about
    is the node model, not the geometry — see below.
  * The ``bundle`` variant: the pre-#1108 connected spelling, N coincident
    rises. momwire's B-spline crossing serve is the only thing that solves
    it — the NEC-5 binary silently prints garbage for coincident wires
    (measured on this design: 3271-3374j ohm with a 2e+25 % radiated power)
    and razor's tent basis gets N identical columns and a singular matrix
    (momwire#846). It is kept because the fan-widening record and every
    number banked here before 2026-09-03 belong to it.
  * The ``detached`` variant: the STAKE convention — the monopole stands
    its end in the ground plane (ground contact) and the N radials lie at
    ``depth``, joined to each other at a common centre point but touching
    neither the surface nor the monopole. No rises, no crossing node. This
    is the momwire#567 anchor-class geometry: NEC-5 serves it natively
    (its point-electrode junction fiction carries the contact current into
    the soil; the banked binary print for the four-radial anchor mesh is
    90.051 - 70.731j ohm over eps_r 13 / sigma 0.005 at 7 MHz), while
    momwire REFUSES it by name — its contact image fiction has no
    conductor for the spreading soil current a buried observer sees
    (momwire#567), and its refusal message points back at the connected
    spelling it does serve.

The ``detached`` and ``bundle`` spellings each have exactly one engine, and
each refusal names a spelling that engine DOES serve. The DEFAULT has all of
them — that is what issue #1108 bought — and the spellings were never why the
engines disagree anyway. Measured 2026-09-02 on the licensed
NEC-5 binary at this design's default knobs over eps_r 13 / sigma 0.005
(scratch/ble-1937/RESULTS.md, momwire#838, #1104): NEC-5 reads
49.78 + 20.95j ohm with the radials CONNECTED to the base through one
15 cm rise — which is now this design's DEFAULT geometry — and
50.11 + 21.46j ohm detached. The same answer either way: NEC-5's
interface node injects the base current into the soil as a point
electrode (momwire#524 phase 2, momwire#567), so a screen bonded to the
mast and a screen lying loose underneath cost it the same. momwire's
connected serve reads 75.85 + 40.45j ohm on the same geometry at
converged quadrature, 32.5 ohm away, and that gap is NEC-5's node, not
a convention. Both engines now run the SAME deck, which is what makes
the comparison a node-model measurement instead of a spelling one.

The measurement decides whose radial-count law is physical. Brown,
Lewis and Epstein (Proc. IRE, June 1937, Fig. 36; buried radials at
3 MHz) measured base resistance falling from >= 50 ohm at 2 radials to
24 ohm at 113; N6LF (QEX, 2009) measured 137 / 86 / 56 / 43 / 40 ohm
at 4 / 8 / 16 / 32 / 64 surface radials. NEC-5 on BLE's exact geometry
spans only 36 -> 28 ohm; momwire's crossing serve falls 114 / 81 / 62 /
50 ohm at N = 2 / 4 / 8 / 16 on a deep screen both engines serve. So
quote momwire's number as the connected answer, and do NOT quote the
NEC-5 ``detached`` print as "the other convention's" answer to the same
antenna: it is a different node model, and its flat law is the wrong
shape.

Read QUADRATURE below before quoting the momwire number. The gap has been
quoted at three sizes here as the quadrature moved and the spelling changed
("~35 ohm" was the bundle at n_qp_pair = 4, "~30 ohm" the bundle at 8);
32.5 ohm is the hub at n_qp_pair = 32, and it is the first one measured on
the deck BOTH engines run.

QUADRATURE — and the spelling change moved this axis more than it moved
the answer. This deck is momwire#760's class: ONE crossing junction at a
lossy-soil interface. That issue long recorded the class as losing its
convergence RATE — "the cross-edge quadrature error falls only as C/q,
FIRST order in n_qp_pair" — and this file was where that claim was
measured. **It does not survive a converged reference.** Both ladders
below are re-referenced to q=256 (they used to be referenced to q=32,
which the old text itself noted was "still moving ~0.25 ohm at 24->32";
an unconverged reference flattens the tail of a ladder). Fixed mesh, this
design's default knobs, eps_r 13 / sigma 0.005 at 7.1 MHz, momwire
9eda56f — the commit this repo pins.

The DEFAULT (hub) spelling — the shipped one, and the ladder to quote:

    n_qp_pair   Z                     from q=256    local slope
        4       75.8015 + 39.7820j    0.6752
        8       75.8371 + 40.2843j    0.1717        1.98   <- the default today
       16       75.8475 + 40.4189j    0.0367        2.23
       32       75.8502 + 40.4507j    0.0047        3.36
       64       75.8507 + 40.4555j    0.0001        6.75
                                      fit q^-3.11

The ``bundle`` variant, the RETIRED spelling (pre-#1108). Kept as the
record it is: every headline figure this file carried before 2026-09-03
was measured on it, and none of them belongs to the default.

    n_qp_pair   Z                     from q=256    local slope
        4       75.8604 + 47.4594j    7.0040               <- shipped before momwire 0.45.0
        8       75.8619 + 43.5763j    3.1209        1.17
       16       75.8562 + 41.5914j    1.1360        1.46
       32       75.8525 + 40.7584j    0.3030        2.08
       64       75.8510 + 40.5007j    0.0453        3.09
                                      fit q^-1.78

THE RATE IS NOT FIRST ORDER, and the bundle is where the claim came from.
Its local slope RISES monotonically, 1.17 at q=4->8 to 3.09 by q=64 —
superalgebraic, not the constant slope an unsubtracted singularity pins.
Sampled only at the bottom of the ladder, which is where q=4/8/16 sits and
all anyone could reach before momwire#762 lifted the accelerator's n_qp<=8
ceiling, a bundle reads as C/q. It is a large quadrature CONSTANT on the
worst spelling, not a lost rate; the remedy is order, and momwire#760
closed on this record.

So the reactive-floor caveat this file used to carry is the BUNDLE's, and
it is quadrature error rather than anything structural. The hub at the
shipped n_qp_pair=8 sits 0.17 ohm from its own converged answer, and at
q=32 it is 0.0047 ohm — on the plateau. The bundle needs ~64 to get there.

**The N coincident rises were most of the quadrature problem.** At the
shipped n_qp_pair = 8 the hub sits 0.172 ohm from its own converged answer
where the bundle sat 3.12 — a factor of 18 — and the old "~2.8 ohm reactive
floor on anything quoted from this design" simply does not apply to the
default any more. The error is still almost purely REACTIVE (R is converged
to 0.02 ohm across both ladders) on a design whose entire purpose is tuning,
so the ladder stays here; it is just no longer the dominant term.

TWO STRUCTURES, AND HOW FAR APART THEY REALLY ARE. At n_qp_pair = 8 the hub
and the bundle read 3.29 ohm apart, which is the number a casual comparison
would quote. At n_qp_pair = 32 they are 0.31 ohm apart — which is where this
file used to stop, and calling that residue structural was wrong. Carried to
converged quadrature they agree to **5.2e-06 ohm**:

    n_qp_pair   |Z_bundle - Z_hub|
       32       0.31 ohm       <- what this file used to quote as structural
      128       1.9e-03 ohm
      256       5.2e-06 ohm

So it was not "nearly all" of the apparent difference that was the bundle's
own quadrature error — it was essentially ALL of it. They are genuinely
different decks (10 wires against 7, and 7 ohm apart at q=4), so this is two
structures converging to one answer rather than one deck measured twice;
if anything it reads as momwire#524's fan widening doing its job.

That still does NOT license gating one against the other. They remain two
structures under momwire#524's fan-widening adjudication, and one deck at one
soil, mesh and frequency is a measurement rather than an equivalence theorem.
What it does settle is that any claim about "how different the two spellings
are" has to be made at converged quadrature or it is measuring quadrature.

MESH CONVERGENCE — the default mesh IS the converged rung IN MESH, at
fixed quadrature. Mesh convergence at fixed quadrature converges to the
wrong limit (momwire#760: the two axes interact, so a global density sweep
reports converged while the quadrature axis is still moving); this paragraph bounds the mesh axis and no other.
The crossing node carries a slow, measured convergence class in the node
mesh (momwire#674, first order in the node-adjacent segment length).

On the DEFAULT (hub) spelling, measured 2026-09-03 at n_qp_pair = 8:
doubling the far mesh moves the answer **0.050 ohm** (75.8475 + 40.3334j
against 75.8371 + 40.2843j). The graded node panels are fixed by the recipe,
so sweeping the density only refines the FAR mesh — which is the axis that
sweep actually measures.

The history below belongs to the ``bundle`` spelling and was measured at
n_qp_pair = 4, where the quadrature axis it does not carry is 7.00 ohm
against a converged reference — 162x the largest term in it. The original auto-meshed default put ONE segment
on each 15 cm rise (the density floor: 0.15 m against a 40 m quarter-wave)
and sat 29 ohm of reactance off the converged answer on a FALSE PLATEAU:
global density sweeps to 4x moved it < 0.2 ohm with the node mesh frozen by
the floor, then N=126 jumped 20 ohm in one rung. The graded-mesh default
(the `graded_wire` rise + radiator below) is what retired that, at the
h_node = 6.25 mm rung, where the next grading rung moved it 0.019 ohm and a
doubled far mesh 0.043 ohm.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire, graded_wire, wire_from_catalog


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 40 m: the band the ground-mounted vertical over buried radials
            # is the standard answer on.
            "freq": 7.1,
            "design_freq": 7.1,
            # NOMINAL SOIL — the mesh's stated assumption about the dirt,
            # not the solve's. `auto_mesh` sizes below-interface wires
            # against the IN-MEDIUM quarter-wave, which is shorter than the
            # free-space one by |n| = |sqrt(eps_r - j*sigma/(omega*eps_0))|
            # (~4.26x here); without a declaration a buried wire meshes
            # against lambda_0 and is under-resolved by exactly that factor
            # (issue #983). These are the constants the numbers quoted in
            # the module docstring were measured over. The half-space the
            # solve actually uses still comes from `--ground` and may
            # differ — the mesh deliberately does not track it, so sweeping
            # or fitting soil never remeshes the geometry.
            "design_eps_r": 13.0,
            "design_sigma": 0.005,
            # Radiator height as a fraction of the design quarter-wave.
            "length_factor": 1.0,
            # Radials, and their length relative to the radiator. The textbook
            # screen uses equal-length radials; the DEFAULT is a truncated 0.6
            # (~21 ft on 40 m).
            #
            # The reason that default was chosen has since LAPSED, and the
            # number is left alone here rather than quietly changed. The
            # original comment read: momwire tabulates the below/below
            # remainder to 2 in-medium wavelengths, so full-size opposite
            # radials span 2.13 lambda_m over eps_r 13 soil and refuse by
            # name. **momwire#847 moved that cap from 2 to 4 lambda_m**, and
            # full-size radials now serve over the nominal soil. Measured
            # 2026-09-03 (issue #1131), radial_factor 1.0 / 1.2 / 1.5 all
            # solve over eps_r 13, sigma 0.005.
            #
            # The cap is still real, and it is a SOIL question rather than a
            # length one. Two opposite tips sit 2*radial_factor*length_factor
            # *(lambda_0/4) apart and must stay inside 4*lambda_m, so the deck
            # serves iff radial_factor*length_factor <= 8/|n|. At 7.1 MHz:
            #
            #   eps_r 13, sigma 0.005  |n| 4.26  ->  <= 1.88   full size SERVES
            #   eps_r 20, sigma 0.03   |n| 8.86  ->  <= 0.90   full size REFUSES
            #   eps_r  5, sigma 0.001  |n| 2.37  ->  <= 3.38   full size SERVES
            #
            # (Boundary verified by solving across it: over eps_r 20 soil,
            # 0.85 serves and 0.95 refuses.) So the knob that has to shrink is
            # the one over dense, conductive ground — where 0.6 is still
            # right — and not the one over average dirt. Whether the default
            # should move is a design call, not a docs one; see #1131.
            "n_radials": 4,
            "radial_factor": 0.6,
            # Burial depth, metres. 0.15 m is a spade's depth, the depth the
            # phase-0/phase-2 anchors were measured at. Keep it shallow: the
            # transmitted-field ladder momwire integrates across the interface
            # is priced for a screen near the surface, and a deep screen walks
            # off the measured envelope.
            "depth": 0.15,
            # Junction convention — see "TWO CONVENTIONS, TWO ENGINES" in the
            # module docstring. "connected" rises the radials to a crossing
            # junction at z = 0 (momwire's serve); "detached" is the stake
            # convention, radials lying at depth touching nothing (NEC-5's
            # serve). A bare string with no enum_options renders no knob:
            # the convention is chosen by the variant picker, not a slider.
            "convention": "connected",
            # SURFACE convention only (momwire#865). The radials do not go
            # under the soil at all: they LIE ON it, which momwire serves as
            # the elevated family at an explicit small height. `None` means
            # "the jacket resting on the ground" — h = b, the insulation's
            # OUTER radius — which is where a real insulated wire's conductor
            # actually sits and is exactly momwire#875's jacketed floor.
            "surface_h_m": None,
            # The wire, for the surface convention. The other conventions run
            # the design's bare default; only the surface one needs a jacket,
            # because on the surface the jacket IS the stand-off.
            "wire_type": None,
            "ui_params": MappingProxyType(
                {
                    # Buried conductors exist only under a Sommerfeld
                    # half-space: the web app auto-selects finite ground +
                    # the Sommerfeld method on load (with a notice) instead
                    # of letting the refl-coef default hit the refusal wall.
                    "ground_requirement": "sommerfeld",
                    # Radial 0 always runs along +x, so the x-z plane always
                    # shows one radial full-length beside the radiator and the
                    # buried hub below the surface — the elevation profile
                    # that makes the depth knob legible.
                    "default_view": "xz",
                    "n_radials": {"min": 1, "max": 4, "step": 1},
                    "depth": {"min": 0.05, "max": 0.5, "unit": "m"},
                    "length_factor": {"min": 0.8, "max": 1.2},
                    "radial_factor": {"min": 0.3, "max": 1.5},
                }
            ),
        }
    )

    # The stake convention (momwire#567 anchor class): same knobs, no rise
    # wires — the monopole stands its end in the plane, the radials lie at
    # depth. NEC-5 serves this spelling and refuses the default's bundle;
    # momwire mirrors it exactly the other way. See the module docstring.
    detached_params = MappingProxyType({"convention": "detached"})

    # The pre-#1108 connected spelling: N coincident rises, one per radial.
    # Kept as a named variant because it is a DIFFERENT CONDUCTOR from the
    # default hub (a bundle of N coincident thin wires is not one wire of the
    # same radius) and because every number banked on this design before
    # 2026-09-03 was measured on it. NEC-5 refuses it (coincident wires) and
    # razor's tent basis is singular on it (momwire#846); momwire's B-spline
    # crossing serve is the only thing that solves it.
    bundle_params = MappingProxyType({"convention": "bundle"})

    # The SURFACE convention (momwire#865): radials lying ON the ground, the
    # way most amateurs actually build a screen, rather than plowed under it.
    #
    # momwire refuses a wire IN the plane and always will — a conductor on the
    # interface is not a physical configuration. What a surface radial IS, is
    # the ELEVATED family at the conductor's own centre height, and for an
    # insulated wire lying on soil that height is b, the jacket's outer
    # radius: the jacket rests on the ground and the copper sits a jacket
    # thickness above it.
    #
    # 18 AWG PVC is the default because both of momwire's floors agree there:
    # b/a = 2.05, so h = b sits at h/a = 2.05, just above the BARE bound of 2a.
    #
    # In fact EVERY insulated wire in the catalog clears that bare bound —
    # 18/22/28 AWG PVC are b/a 2.05 / 2.49 / 3.12, and a thinner conductor
    # under the same jacket has a LARGER ratio, not a smaller one. So this
    # variant never actually needs momwire#875's jacketed relaxation today;
    # it would take an enamel-class jacket (b/a ~ 1.05) to go under h/a = 2,
    # and the catalog has none. That is a robustness property worth knowing
    # rather than a gap: the variant is served by the older, stricter bound,
    # and #875 is what will keep it served if a thin-jacket wire is ever
    # added.
    _SURFACE_NOTE = (
        "Radials lying ON the ground. The height IS the model here: the "
        "conductor sits one jacket thickness above the soil, and the answer "
        "is a strong function of that stand-off. A millimetre of grass is "
        "worth about 41 \u03a9 at 4 radials and about 10 \u03a9 at 16 "
        "(momwire#865), so with a sparse screen treat the impedance as "
        "INDICATIVE RATHER THAN PREDICTIVE \u2014 the same wire laid in "
        "deeper grass is a measurably different antenna. At 16 radials and "
        "above the class is quotable. Note that momwire raises its own "
        "per-solve advisory for this, carrying the deck's actual h/a, and "
        "the app does not surface solver advisories yet (antennaknobs "
        "follow-up); this note is the static stand-in."
    )

    surface_params = MappingProxyType(
        {
            "convention": "surface",
            "wire_type": "18-awg-pvc",
            "ui_params": MappingProxyType(
                {**default_params["ui_params"], "notes": _SURFACE_NOTE}
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        height = 0.25 * self.design_wavelength * self.length_factor
        radial = height * self.radial_factor
        depth = self.depth
        n_radials = max(1, round(self.n_radials))
        detached = self.convention == "detached"
        bundle = self.convention == "bundle"
        surface = self.convention == "surface"

        if surface:
            return self._surface_wires(height, radial, n_radials)

        node = (0.0, 0.0, 0.0)
        hub = (0.0, 0.0, -depth)

        tups = []
        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            c, s = math.cos(theta), math.sin(theta)
            # Snap the on-axis components to exact zeros: wires are joined
            # only where endpoint coordinates match, and every radial must
            # land on the SAME hub point for the screen to be one node.
            x = radial * (0.0 if abs(c) < 1e-15 else c)
            y = radial * (0.0 if abs(s) < 1e-15 else s)

            # HUB FIRST, deliberately. The polyline walk starts new walks
            # at boundary nodes in registration order; a tip-first FIRST
            # radial registers its tip as node 0 and gets walked tip->hub
            # while the siblings walk hub->tip — and mesh interpolation is
            # not direction-symmetric in the last bits, so the screen's
            # fourfold mirror breaks and the crossing fill's exact-triple
            # memo loses its ~4x dedup (momwire#688's census measured the
            # miss on this very deck). Hub-first makes every radial leave
            # the hub, so the +/-x and +/-y meshes are exact negations.
            tups.append(Wire(hub, (x, y, -depth)))
            if bundle:
                # The `bundle` variant's per-radial rise, coincident with
                # every other radial's by construction — the pre-#1108
                # default, kept because the fan-widening record and every
                # number banked before 2026-09-03 were measured on it. The
                # DEFAULT now puts one shared rise below this loop, and the
                # detached variant has no rise at all.
                #
                # The rise is GRADED toward the node (momwire#674's
                # recipe, promoted to the `graded_wire` spelling by this
                # design's default-mesh fix and validated to 1 m depth by
                # the #692 deep-deck ladder): geometric panels toward
                # (0,0,0), node segment 6.25 mm at every depth. A plain
                # auto-meshed rise is pinned to ONE segment by the
                # density floor (0.15 m against a 40 m quarter-wave),
                # which froze the crossing node's convergence class into
                # the default answer — measured 29 Ω of reactance on
                # this design, a false plateau a uniform density sweep
                # cannot escape below ~5× density (and then only via a
                # 20 Ω single-rung jump). The graded spelling stays ONE
                # wire and ONE polyline — hand-split wires on the
                # coincident bundle mint spurious 8-member junctions at
                # every shared split point.
                tups.append(graded_wire(hub, node, toward="p1"))

        if not detached and not bundle:
            # THE HUB SPELLING (issue #1108), and the default connected
            # convention: ONE rise from the buried hub to the node. Graded
            # toward the node on the same momwire#674 recipe the bundle's
            # rises used.
            #
            # A single rise leaves the node at degree 2 — one rise below, the
            # feed gap above — which the polyline walk used to thread THROUGH,
            # handing momwire one polyline crossing the interface mid-span
            # (the refusal). `MomwireEngine` now ends a polyline at every wire
            # end lying in the plane (issue #1109), so the node is a declared
            # junction with no bundle needed, and the screen is a conductor
            # someone actually builds: NEC-5 takes it, and razor's tent basis
            # no longer sees N identical columns (momwire#846).
            tups.append(graded_wire(hub, node, toward="p1"))

        # Driven gap at the radiator foot; the radiator stacks on top of it.
        # In the detached variant the gap's lower end stands in the plane as
        # a legal ground CONTACT end, touching nothing below.
        tups.append(Wire(node, (0.0, 0.0, eps), ex=1 + 0j))
        if not detached and height > 1.0:
            # The radiator's node end is graded too (#674: the above
            # arm's interface-adjacent h is the dominant term of the
            # crossing node's convergence class), with the far panel at
            # the design's own segment length. The 5 cm feed-gap wire
            # above stays exactly as it is — re-meshing it would change
            # the FEED MODEL, not the mesh. The detached variant keeps
            # the plain radiator: its mesh is banked against the NEC-5
            # print and its contact node is a different (served-by-NEC-5)
            # convention with no crossing junction to grade for.
            tups.append(
                graded_wire(
                    (0.0, 0.0, eps),
                    (0.0, 0.0, height),
                    toward="p0",
                    rest_h=0.25 * self.design_wavelength / self.nominal_nsegs,
                )
            )
        else:
            tups.append(Wire((0.0, 0.0, eps), (0.0, 0.0, height)))

        return tups

    # ------------------------------------------------------------------
    # The SURFACE convention (momwire#865)
    # ------------------------------------------------------------------

    def _surface_wires(self, height, radial, n_radials):
        """Radials lying ON the ground, jacket resting on the soil.

        The radials and the radiator's foot sit together at `h`, so this is
        one elevated deck with no crossing junction and no rise — the
        interface is never pierced. The JACKET IS THE STAND-OFF, which is why
        `h` defaults to the wire's own `b`.
        """
        spec = wire_from_catalog(self.wire_type) if self.wire_type else None
        if spec is None or not spec.insulation_radius:
            raise ValueError(
                "the `surface` convention needs an INSULATED wire_type: the "
                "jacket is what holds the conductor off the soil, and a bare "
                "wire lying in the plane is refused by momwire (momwire#865). "
                f"Got wire_type={self.wire_type!r}."
            )
        h = self.surface_h_m if self.surface_h_m else spec.insulation_radius

        tups = []
        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            c, s = math.cos(theta), math.sin(theta)
            x = radial * (0.0 if abs(c) < 1e-15 else c)
            y = radial * (0.0 if abs(s) < 1e-15 else s)
            # Foot-first, for the same reason the buried conventions are
            # hub-first: every radial must leave the shared node so the
            # screen's mirror symmetry survives the polyline walk.
            #
            # THE SPEC RIDES THE RADIALS ONLY. The mast below carries none
            # and inherits the design's bare default. A SCALAR insulation
            # would jacket the mast too, which is not the antenna anyone
            # builds and is worth ~15-30 ohm of spurious reactance — the
            # trap that sent momwire#874's first reading the wrong way.
            tups.append(Wire((0.0, 0.0, h), (x, y, h), spec=spec))

        tups.append(Wire((0.0, 0.0, h), (0.0, 0.0, h + 0.05), ex=1 + 0j))
        tups.append(Wire((0.0, 0.0, h + 0.05), (0.0, 0.0, h + height)))
        return tups
