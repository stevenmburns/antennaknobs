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
    above member (the radiator) and N below members (the rises). A second
    above member is an above-tent x above-tent corner, which is refused.
  * The radial tips stay free — nothing else touches or crosses z = 0.

``n_radials`` FLOOR OF 2, which is not a physics limit. antennaknobs
derives momwire's junction list from wire-endpoint degree, so a node where
only two wires meet is threaded THROUGH as an interior polyline vertex
rather than becoming a junction. With one radial the rise and the radiator
are collinear neighbours at z = 0, the node is degree 2, and the deck
reaches momwire as a single polyline crossing the interface mid-span — the
refusal. Two or more radials put >= 3 wire ends at the node, which is what
makes it a junction. The upper bound of 4 is the fan widening's own
adjudicated bank.

The screen is spelled as N coincident rises (one per radial) rather than
one shared rise, because a shared rise would again leave the node at
degree 2. The two spellings are NOT interchangeable: a bundle of N
coincident thin wires is a different conductor than one wire of the same
radius (momwire's fan-widening adjudication measured the two spellings
several ohms apart on the same screen — they are two structures, never
gated against each other), so this design is the N-rise structure
specifically: the model of N radials each brought up to the base plate.

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

TWO CONVENTIONS, TWO ENGINES — the ``detached`` variant. The screen can be
spelled two ways, and they are TWO DIFFERENT STRUCTURES, not two meshes of
one:

  * The DEFAULT (connected) convention above: radials rise to the surface
    and junction-join the monopole at z = 0 — the crossing junction.
    momwire serves it (the #524 phase-2 crossing serve); the NEC-5 wrapper
    REFUSES it, because the N-coincident-rise bundle is momwire's exactly-
    regularized spelling and the NEC-5 binary silently prints garbage for
    coincident wires (measured on this design: 3271-3374j ohm with a
    2e+25 % radiated power).
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

Each engine serves exactly one convention and refuses the other, and each
refusal names the spelling that engine DOES serve. Comparing the default
through momwire against ``detached`` through NEC-5 compares the two
JUNCTION CONVENTIONS, not two solvers on one antenna — at this design's
default knobs over eps_r 13 / sigma 0.005 soil the converged pair reads
75.86 + 47.46j ohm (connected, momwire, ±0.10 mesh envelope) against
~50.6 + 24.0j ohm (detached, NEC-5 at 252 segments per quarter-wave,
still settling by ~0.1 ohm per density step), ~35 ohm apart. That gap is
adjudicated physics (momwire#524 phase 2), never a bug to gate away.

MESH CONVERGENCE — the default mesh IS the converged rung. The N-member
crossing node carries a slow, measured convergence class in the node
mesh (momwire#674, first order in the node-adjacent segment length).
The original auto-meshed default put ONE segment on each 15 cm rise
(the density floor: 0.15 m against a 40 m quarter-wave) and sat 29 ohm
of reactance off the converged answer on a FALSE PLATEAU — global
density sweeps to 4x moved it < 0.2 ohm (node mesh frozen by the
floor), then N=126 jumped 20 ohm in one rung. Since the graded-mesh
default (the `graded_wire` rises + radiator below), the design loads at
the h_node = 6.25 mm rung: the next grading rung moves it 0.019 ohm and
a doubled far mesh 0.043 ohm. Sweeping the density still only refines
the FAR mesh — the graded node panels are fixed by the recipe — so a
convergence sweep here now measures the axis it actually refines.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire, graded_wire


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
            # screen uses equal-length radials, but the DEFAULT is a truncated
            # 0.6 (~21 ft on 40 m) because momwire tabulates the below/below
            # remainder to 2 in-medium wavelengths: full-size opposite radials
            # span 2.13 lambda_m over eps_r 13 soil and REFUSE by name. Long
            # radials over dense/conductive soil hit the same cap — shrink
            # this knob when they do.
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
                    "n_radials": {"min": 2, "max": 4, "step": 1},
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

    def build_wires(self):
        eps = 0.05

        height = 0.25 * self.design_wavelength * self.length_factor
        radial = height * self.radial_factor
        depth = self.depth
        n_radials = max(2, round(self.n_radials))
        detached = self.convention == "detached"

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
            if not detached:
                # This radial's rise to the node. Coincident with every
                # other radial's rise by construction — see the module
                # docstring. The detached variant has no rises at all:
                # that absence IS the stake convention.
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
