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
knobs. Inside soil the wave slows by roughly 1/sqrt(eps_r) — at the usual
eps_r ~ 13 that is about 0.28 — so a wire cut to a free-space half-wave is
electrically some THREE AND A HALF half-waves long once it is buried, and
it behaves nothing like a dipole. `velocity_factor` is therefore applied
directly: the default 0.28 sizes the wire to a half-wave IN THE SOIL, which
is the length that actually resonates down there. Raise it toward 1.0 to
see the free-space-cut wire's multi-lobed mess for yourself. The soil
constants that set the true value are chosen at solve time, not here, so
this knob is the design's stated ASSUMPTION about them, and a solve over
different dirt will not land where the default assumed.

The same asymmetry catches the mesh: ``auto_mesh``'s density counts
segments per FREE-SPACE quarter-wave, so a buried wire is meshed about
1/sqrt(eps_r) as finely in medium wavelengths as the nominal count
suggests. Raise ``nominal_nsegs`` before trusting a converged number.

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
            # Velocity factor of the surrounding medium, ~1/sqrt(eps_r).
            # 0.28 is eps_r ~ 13, the soil the buried anchors were measured
            # over; 1.0 sizes the wire as if it were in free space.
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
