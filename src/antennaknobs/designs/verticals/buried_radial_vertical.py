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
default knobs over eps_r 13 / sigma 0.005 soil the pair reads
75.94 + 77.24j ohm (connected, momwire) against 50.24 + 22.14j ohm
(detached, NEC-5), ~61 ohm apart before either engine's mesh envelope is
even counted. That gap is adjudicated physics (momwire#524 phase 2),
never a bug to gate away.

MESH CONVERGENCE, read before trusting a number. The N-member crossing
node carries a slow, measured convergence class in the node mesh
(momwire#674): momwire's own 4-radial adjudication deck moved ~7.5 ohm
between an ungraded and a node-graded mesh over eps_r 13 / sigma 0.005
soil. The default mesh here is a starting point for the knobs, not a
converged answer — sweep the density upward (and expect the solve time to
climb with it) before quoting an impedance to anyone.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # 40 m: the band the ground-mounted vertical over buried radials
            # is the standard answer on.
            "freq": 7.1,
            "design_freq": 7.1,
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

            tups.append(Wire((x, y, -depth), hub))
            if not detached:
                # This radial's rise to the node. Coincident with every
                # other radial's rise by construction — see the module
                # docstring. The detached variant has no rises at all:
                # that absence IS the stake convention.
                tups.append(Wire(hub, node))

        # Driven gap at the radiator foot; the radiator stacks on top of it.
        # In the detached variant the gap's lower end stands in the plane as
        # a legal ground CONTACT end, touching nothing below.
        tups.append(Wire(node, (0.0, 0.0, eps), ex=1 + 0j))
        tups.append(Wire((0.0, 0.0, eps), (0.0, 0.0, height)))

        return tups
