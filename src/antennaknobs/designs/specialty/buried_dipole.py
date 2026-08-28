"""Wholly-buried horizontal dipole — the underground cousin of the
beverage-on-ground, and the simplest thing momwire's buried serve can be
asked (momwire#553 phase 0).

Nothing about this antenna is above the surface. It is a receiving
curiosity rather than a transmitting antenna: soil is a lossy dielectric,
so most of what the wire is given goes into heating the dirt, and the
efficiency is dreadful. What it buys is a low, quiet, invisible, and
mechanically indestructible receive aperture — the same trade a BOG makes,
pushed one spade deeper.

    z = 0       ==================   air/soil interface
    z = -depth   ------F------       one wire, centre-fed, all of it below

WAVELENGTH IN THE MEDIUM, which is the whole point of the design's sizing
knobs. Inside soil the wave slows by 1/|n|, the reciprocal refractive-index
magnitude |n| = |sqrt(eps_r - j*sigma/(omega*eps_0))| — 0.234 over the
declared eps_r 13 / sigma 0.005 soil at 7.1 MHz — so a wire cut to a
free-space half-wave is electrically some FOUR half-waves long once it is
buried, and it behaves nothing like a dipole.

MIND THE TWO SPELLINGS. `velocity_factor` (0.28) is the LOSSLESS
1/sqrt(eps_r), and it is a SIZING knob: it sets how long the wire is cut,
it is a user-facing slider, and changing its value changes what antenna
this design models. The MESH is sized separately, off the declared
`design_eps_r`/`design_sigma` and through momwire's own |n| (0.234, not
0.28) — the lossy value, because dropping the conduction term
under-resolves in the direction that looks fine. The two differ by ~18%
here and are deliberately not wired together; reconciling them is
antennaknobs#1026, and it moves the default geometry, so it is not a mesh
fix. `velocity_factor` remains the design's stated ASSUMPTION about the
dirt for SIZING; raise it toward 1.0 to see the free-space-cut wire's
multi-lobed mess for yourself.

The mesh asymmetry itself is FIXED (issue #983): `auto_mesh` now counts a
below-interface wire's segments per IN-MEDIUM quarter-wave, so the nominal
count means what it says down there. It was ~4.3x under-resolved before,
and the old advice here — raise `nominal_nsegs` before trusting a
converged number — no longer applies to the burial as such. The soil the
SOLVE uses still comes from `--ground` and may differ from the declared
one; the mesh deliberately does not track it, so sweeping soil never
remeshes.

GEOMETRY CONVENTIONS. One straight horizontal wire along x at z =
-`depth`, strictly below the interface — no end reaches z = 0, so there is
no ground contact and no crossing junction anywhere. That is the widest
part of the buried serve's scope; the house eps-gap centre feed is legal
here precisely because there is no crossing node for the gap's extra
polyline vertex to disturb.

REQUIRES A FINITE GROUND, and momwire. A buried conductor only means
anything under a Sommerfeld half-space, which antennaknobs chooses at
SOLVE time, not in the design: pass ``--ground finite:13,0.005`` (or
another eps_r/sigma pair). Under ``free`` this is just a dipole hanging in
space, and every number the design is interesting for disappears. The
NEC-5 and PyNEC engine wrappers both refuse a wire below z = 0 outright,
so this is a momwire-only design.
"""

from types import MappingProxyType

from antennaknobs import AntennaBuilder
from antennaknobs.network import Wire


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
            # SIZING ONLY — how long the wire is cut, not how it is meshed.
            # The LOSSLESS 1/sqrt(eps_r): 0.28 is eps_r ~ 13, the soil the
            # buried anchors were measured over; 1.0 sizes the wire as if it
            # were in free space. The mesh uses the lossy |n| off
            # design_eps_r/design_sigma instead (0.234 here, not 0.28) — see
            # the module docstring's "MIND THE TWO SPELLINGS" and #1026.
            "velocity_factor": 0.28,
            # Overall scale on top of the medium half-wave.
            "length_factor": 1.0,
            # Burial depth, metres — deep enough to be genuinely buried,
            # shallow enough to stay inside the measured envelope of the
            # transmitted-field ladder momwire integrates across the seam.
            "depth": 0.15,
            "ui_params": MappingProxyType(
                {
                    # A buried wire exists only under a Sommerfeld half-space:
                    # the web app auto-selects finite + Sommerfeld on load.
                    "ground_requirement": "sommerfeld",
                    # The wire runs along x at a fixed depth, so x-z is the
                    # only view that shows both the wire and how far under
                    # the surface it is.
                    "default_view": "xz",
                    "velocity_factor": {"min": 0.15, "max": 1.0},
                    "length_factor": {"min": 0.5, "max": 1.5},
                    "depth": {"min": 0.05, "max": 0.5, "unit": "m"},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.025

        half = 0.25 * self.design_wavelength * self.velocity_factor * self.length_factor
        z = -self.depth

        return [
            Wire((-half, 0.0, z), (-eps, 0.0, z)),
            # Centre-fed gap; both arms stack onto it.
            Wire((-eps, 0.0, z), (eps, 0.0, z), ex=1 + 0j),
            Wire((eps, 0.0, z), (half, 0.0, z)),
        ]
