"""Bruce array: a series-fed vertically-polarised curtain (L. B. Cebik, W4RNL).

One continuous wire folded into a square wave: quarter-wave VERTICAL risers
joined by quarter-wave HORIZONTAL jogs that alternate top and bottom. The trick
of the Bruce is the phasing it forces for free. Going around the meander, the
standing wave puts a current MAXIMUM on every vertical riser all pointing the
same way, while the horizontal jogs sit at the current minima and carry equal,
opposed currents that cancel in the far field. The result is a row of co-phased
vertical radiators on ~half-wave centres -- a VERTICALLY POLARISED broadside
curtain (bidirectional off +/-x), gain growing with the number of risers
(~6.5 dBi at five risers here, climbing past 7 with more).

This is the catalog's first SERIES-fed curtain. The half-square/bobtail/bisquare
VP family are parallel/standing-wave structures fed at one element; the Bruce
threads a single standing wave through the entire meander, so the feedpoint
location sets the phase progression of the whole array (moving the feed to the
centre, as one can on the bobtail, instead DETUNES the Bruce). Geometrically it
is a long chain of right-angle junctions, a good stress on the engines'
junction handling.

FEEDPOINT. Like the classic Bruce, the natural feed is near the bottom of an
END riser, in the region of a current MINIMUM: the driving point is HIGH and
strongly REACTIVE (here a few hundred ohms real over ~ -1.2 kohm). A real Bruce
resonates that out with a tuned matching network, NOT a coax-direct connection;
unlike the bobtail there is no clean current-maximum tap that keeps the phasing
(moving the feed detunes the array), so we model the honest high-Z feed and
treat gain/pattern -- not a 50 ohm match -- as the design target (cf.
`bisquare`, `lazy_h`). Note this is NOT as pathological as the bobtail's
ORIGINAL base feed: because the tap sits a little way up the riser
(`feed_height_frac`), off the exact current null, the four solver bases agree on
it to within a few percent -- high-Z but well-conditioned, not the basis-
dependent runaway a feed placed exactly on a current zero produces.
`feed_height_frac` slides the tap up the end riser to trade feed resistance
against a small pattern change.

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis of the curtain (risers march along y)
  - z : riser height; the square wave oscillates between `base` and `base+vert`
  - x : firing axis; VP radiation broadside off +/- x (planar in x = 0)

    __        __        __        z = base + vert  (top jogs)
   |  |      |  |      |  |
   |  |      |  |      |  |       five quarter-wave risers (current maxima)
   F  |__|      |__|      |       z = base        (bottom jogs); F = end feed
"""

from antennaknobs import AntennaBuilder
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            # Height of the bottom jogs above ground.
            "base": 4.0,
            # Vertical riser length as a fraction of a wavelength (~0.25 wl).
            "vert_frac": 0.25,
            # Horizontal jog length as a fraction of a wavelength (~0.25 wl);
            # successive risers end up on ~half-wave centres.
            "horiz_frac": 0.25,
            # Number of vertical risers (radiators).
            "n_vert": 5,
            # Tap height of the feed on the END riser, as a fraction of its
            # length from the bottom. Small values sit near the current-minimum
            # end (very high reactance); larger values raise feed R but nudge
            # the pattern. ~0.3 is a usable compromise.
            "feed_height_frac": 0.3,
            # Overall scale knob (gain/pattern is the design target; the feed
            # is a high-Z current-minimum point, so this does not resonate it).
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    # Series-fed current-minimum feed -> high, reactive Z; a
                    # tuned matching network feeds it in practice.
                    "target_z0": 600.0,
                    "default_view": "yz",
                    "n_vert": {
                        "min": 3,
                        "max": 9,
                        "step": 1,
                        "precision": 0,
                    },
                    "feed_height_frac": {
                        "min": 0.1,
                        "max": 0.7,
                    },
                    "length_factor": {
                        "min": 0.9,
                        "max": 1.1,
                    },
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        vert = self.vert_frac * wavelength * self.length_factor
        horiz = self.horiz_frac * wavelength * self.length_factor
        z0 = self.base
        M = int(self.n_vert)

        # Walk the square wave, recording the (y, z) node path. Each riser
        # alternates direction; horizontal jogs connect successive risers.
        nodes = [(0.0, z0)]
        riser_edge0 = []  # index of the lower node of each riser
        up = True
        for i in range(M):
            ycur, zcur = nodes[-1]
            riser_edge0.append(len(nodes) - 1)
            znew = zcur + vert if up else zcur - vert
            nodes.append((ycur, znew))
            if i < M - 1:
                nodes.append((ycur + horiz, znew))
            up = not up

        # Feed sits on the first (end) riser at feed_height_frac up from its
        # bottom. The first riser always runs upward from z0.
        fa = riser_edge0[0]
        y_feed, z_riser_bot = nodes[fa]
        zf = z_riser_bot + self.feed_height_frac * vert

        tups = []
        for k, ((ya, za), (yb, zb)) in enumerate(zip(nodes[:-1], nodes[1:])):
            seg = math.hypot(yb - ya, zb - za)
            if k == fa:
                # Split the end riser: passive below, 1-seg driven gap, passive
                # above (a current-maximum-style tap, but on a current minimum).
                tups.append(
                    (
                        (0.0, ya, za),
                        (0.0, ya, zf),
                        self.segs_for(zf - za, quarter),
                        None,
                    )
                )
                tups.append(((0.0, ya, zf), (0.0, ya, zf + 2 * eps), 1, 1 + 0j))
                tups.append(
                    (
                        (0.0, ya, zf + 2 * eps),
                        (0.0, yb, zb),
                        self.segs_for(zb - (zf + 2 * eps), quarter),
                        None,
                    )
                )
            else:
                tups.append(
                    ((0.0, ya, za), (0.0, yb, zb), self.segs_for(seg, quarter), None)
                )

        return tups
