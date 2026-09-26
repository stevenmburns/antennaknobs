"""Elevated vertical with elevated radials over a DETACHED buried ground
screen — every conductor wholly above or wholly below the soil, nothing at
the interface (momwire#553, the buried serve).

The feed stands `base` clear of the surface. The radiator rises from the top
of the feed gap, and `n_elevated` flat radials leave its bottom at the same
height: an ordinary elevated ground-plane vertical, and the radials are its
counterpoise. Below the surface, a buried radial screen lies at `depth`,
joined at its own hub and touching nothing above. It carries no conducted
return current; what it can do is change the ground the radiator and the
elevated radials see, by coupling through the soil in their near field.

At the defaults that effect is SMALL, and the design does not pretend
otherwise: removing the screen moves momwire's Z from 38.17 + j0.81 to
37.56 + j0.82 ohm and the peak gain by 0.03 dB (measured 2026-09-25). A
four-radial screen at 0.6 lambda/4, 0.65 m below radials that are already
a working counterpoise, is not a ground system that matters much. More and
longer buried radials, or a lower `base`, give it more to do.

    z = base+height  T          radiator, ~lambda/4
                     |
    z = base    -----F-----     feed gap; `n_elevated` flat radials leave
                                its lower end, `elevated_factor` * lambda/4
    z = 0       ===========     air/soil interface — NOTHING touches it
    z = -depth      -H-         buried hub; `n_radials` radials fan out
                   /   \\        horizontally at `depth`, free at their tips

Every wire is wholly on one side of the interface: a `split` deck, which is
momwire's buried serve proper, and the reason the design exists. Contrast
`buried_radial_vertical`, which BONDS its radials to the radiator at z = 0
and therefore needs the much narrower crossing serve. Nothing here crosses,
so the scope is wide: the screen may be any count and any length, and the
deck carries no crossing junction at all.

WHY THE ELEVATED RADIALS. Until 2026-09-25 this deck had none. The gap's lower
end connected to nothing, so the source drove a quarter-wave against the
gap's own 25 mm half, and the driving point read about 40 - j68,000 ohm on
momwire and NEC-5 alike: a feed with no return path. A detached screen does
not give a feed one — it is not connected to either terminal. The design
came from momwire#553's serve-gate deck, which gated the fill (an elevated
monopole over a detached buried radial) and never needed a sensible
impedance. The elevated radials are the return path.

DEFAULTS, 7.1 MHz over eps_r 13 / sigma 0.005, measured 2026-09-25. Four
elevated radials at 0.95 lambda/4 bring the system to resonance with the
full-length radiator: momwire's B-spline reads 38.2 + j0.8 ohm at
nominal_nsegs 15 and at 21, and the
elevated length moves X by about +19 ohm per 0.1 of `elevated_factor`
(-28 ohm at 0.8, +20 ohm at 1.05). razor-2p and NEC-5 on the same nominal
21 mesh read 37.99 - j0.77 and 37.99 - j0.80 ohm. One elevated radial is
legal (58.5 + j2.6 ohm), eight read 36.7 + j4.5.

GEOMETRY CONVENTIONS. The radiator and the elevated radials live entirely at
z >= `base` > 0 and the screen entirely at z = -`depth` < 0; the only thing
the serve insists on is that neither reaches the plane. The elevated radials
meet the gap at its lower node (0, 0, base), which is an ordinary wholly-above
junction. The buried radials share a hub at (0, 0, -depth), an ordinary
wholly-below junction, and every radial's tip is free.

FEED. The house eps-gap idiom at the radiator's foot, as `raised_vertical`
and `vertical` spell it, with the elevated radials on the gap's lower end as
`vertical`'s are. There is no crossing junction to protect here.

MESH. The radiator and every elevated radial are graded from the feed
(AK#1455), as `buried_radial_vertical` grades its own: their first segments
match the 25 mm halves of the fed gap, neighbouring segments stay within 2x
of each other, and the far panels sit at the design's usual segment for
`nominal_nsegs` (`doubling_graded_wire`); once that segment is finer than
25 mm, a wire starts at it and comes out near-uniform. A uniform radiator at
the usual densities puts a half-metre segment against the 50 mm gap, and the
driving-point resistance then moves by several percent with
`nominal_nsegs`; graded, it holds still.

REQUIRES A FINITE GROUND. The buried screen only exists under a Sommerfeld
half-space, which antennaknobs chooses at SOLVE time, not in the design:
pass ``--ground finite:13,0.005`` (or another eps_r/sigma pair). Under
``free`` the screen is a floating wire in the air; under ``pec`` it is
shorted to a perfect plane above it. momwire and NEC-5 serve it; PyNEC and
the NEC-2 deck export refuse a wire below z = 0.
"""

import math
from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire, doubling_graded_wire


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
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
            # Feed height above the surface. Small enough to be a real
            # installation (the radiator's foot on an insulator on a post),
            # large enough that no basis function reaches the plane.
            "base": 0.5,
            # Buried screen, as in `buried_radial_vertical` — including the
            # truncated 0.6 default, which keeps opposite radial tips inside
            # the 2-lambda_m below/below range momwire tabulates (full-size
            # tips refuse by name over eps_r 13 soil).
            "n_radials": 4,
            "radial_factor": 0.6,
            "depth": 0.15,
            # The counterpoise: flat radials at `base` on the gap's lower end.
            # 0.95 of the design quarter-wave resonates the system with the
            # full-length radiator over the nominal soil (X +0.8 ohm; see
            # DEFAULTS in the module docstring for the slope).
            "n_elevated": 4,
            "elevated_factor": 0.95,
            "ui_params": MappingProxyType(
                {
                    # The buried screen exists only under a Sommerfeld
                    # half-space: the web app auto-selects finite + Sommerfeld
                    # on load.
                    "ground_requirement": "sommerfeld",
                    # Elevated and buried radials spread in x/y around a
                    # vertical radiator — no single 2D projection shows both
                    # clearances, so iso.
                    "default_view": "iso",
                    # Unlike the bonded design there is no degree-2 node to
                    # avoid, so a single radial is a legal (and instructive)
                    # screen — it is momwire#553's own serve-gate deck.
                    "n_radials": {"min": 1, "max": 4, "step": 1},
                    # One elevated radial is a bent-feed L and still a
                    # return path (~58 ohm); eight is plenty.
                    "n_elevated": {"min": 1, "max": 8, "step": 1},
                    "elevated_factor": {"min": 0.5, "max": 1.3},
                    "base": {"min": 0.2, "max": 3.0, "unit": "m"},
                    "depth": {"min": 0.05, "max": 0.5, "unit": "m"},
                    "length_factor": {"min": 0.8, "max": 1.2},
                    "radial_factor": {"min": 0.3, "max": 1.5},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05

        quarter = 0.25 * self.design_wavelength
        height = quarter * self.length_factor
        radial = height * self.radial_factor
        elevated = quarter * self.elevated_factor
        base = self.base
        depth = self.depth
        n_radials = max(1, round(self.n_radials))
        n_elevated = max(1, round(self.n_elevated))

        feed = (0.0, 0.0, base)
        hub = (0.0, 0.0, -depth)

        tups = []
        # Driven gap at the radiator foot; the radiator stacks on top of it.
        tups.append(Wire(feed, (0.0, 0.0, base + eps), ex=1 + 0j))
        # The radiator is GRADED away from the gap (AK#1455); see MESH above.
        # Its far panels keep the design's usual radiator segment. Its first
        # segments match the gap's 25 mm halves, unless that usual segment is
        # already shorter, when there is nothing to grade.
        radiator_length = height - eps
        max_h = radiator_length / self.segs_for(radiator_length, quarter)
        tups.append(
            doubling_graded_wire(
                (0.0, 0.0, base + eps),
                (0.0, 0.0, base + height),
                h0=min(eps / 2.0, max_h),
                max_h=max_h,
            )
        )

        # The counterpoise: `n_elevated` flat radials leaving the gap's LOWER
        # end, so the feed drives the radiator against them (see FEED). Each
        # is authored feed-first and graded from the feed exactly as the
        # radiator is, so both sides of the source see 25 mm segments.
        elevated_h = elevated / self.segs_for(elevated, quarter)
        for i in range(n_elevated):
            theta = 2 * math.pi / n_elevated * i
            tip = (elevated * math.cos(theta), elevated * math.sin(theta), base)
            tups.append(
                doubling_graded_wire(
                    feed, tip, h0=min(eps / 2.0, elevated_h), max_h=elevated_h
                )
            )

        for i in range(n_radials):
            theta = 2 * math.pi / n_radials * i
            c, s = math.cos(theta), math.sin(theta)
            # Exact zeros on axis, so every radial lands on the SAME hub node.
            x = radial * (0.0 if abs(c) < 1e-15 else c)
            y = radial * (0.0 if abs(s) < 1e-15 else s)

            tups.append(Wire((x, y, -depth), hub))

        return tups
