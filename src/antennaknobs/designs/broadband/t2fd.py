"""T2FD -- Terminated Tilted Folded Dipole (G2BCX; modeled per L. B. Cebik,
W4RNL, "broadband wire antennas").

A folded dipole (two close-spaced parallel wires, shorted at both ends) fed at
the centre of one wire, with a non-inductive TERMINATING RESISTOR at the centre
of the other wire -- diametrically opposite the feed. The resistor damps the
folded dipole's resonances, so instead of one sharp resonance the antenna
presents a moderate, slowly-varying impedance over a very wide frequency range
(several octaves): a deliberately BROADBAND, low-Q antenna. The price, as with
the rhombic, is efficiency -- a good fraction of the input power is burned in
the resistor, especially where the antenna is electrically short -- so gain is
below a resonant dipole's. The "tilted" of the name is a deployment choice (the
wire is slung at a slope) that mixes polarisation and smooths the azimuth
pattern; it does not change the broadband impedance behaviour.

This fills the broadband / low-Q gap: every other antenna in the catalog is
either resonant or a sharply-tuned traveling-wave type optimised for gain;
the T2FD trades gain for a flat SWR curve and no-tuner multiband use.

Geometry, in the framework's (x, y, z) convention:
  - y : the long axis (folded-dipole length), tilted up by `tilt_deg`
  - x : the small fold spacing (kept horizontal)
  - z : height; the centre sits at `base`
Feed at the centre of the near wire; terminating resistor at the centre of the
far wire.

    short |==================|==================| short   <- far wire (term R)
          |       feed                          |
    short |========= F =======|================| short    <- near wire (feed)
"""

from ... import AntennaBuilder
from ...network import Driven, Load, Network, PortAtEdge
import math
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 10.0,
            # Overall length as a fraction of a wavelength at design_freq.
            # ~0.6 wl puts design_freq inside the flat region; the antenna
            # stays broadband well above and somewhat below it.
            "length_frac": 0.6,
            # Fold spacing as a fraction of a wavelength (close-spaced pair).
            "spacing_frac": 0.008,
            # Deployment tilt of the long axis from horizontal, degrees.
            "tilt_deg": 30.0,
            # Terminating resistance (ohm) at the far-wire centre. Tuned with
            # the geometry for a flat SWR curve; fed through a balun.
            "term_r": 820.0,
            "ui_params": MappingProxyType(
                {
                    # The terminated geometry settles near ~850 ohm across
                    # the band; reference SWR there (fed via a balun).
                    "target_z0": 850.0,
                    "default_view": "yz",
                    "length_frac": {
                        "min": 0.3,
                        "max": 0.8,
                        "step": 0.005,
                        "precision": 3,
                    },
                    "spacing_frac": {
                        "min": 0.004,
                        "max": 0.03,
                    },
                    "tilt_deg": {"min": 0.0, "max": 45.0, "step": 1.0, "precision": 1},
                    "term_r": {"min": 200.0, "max": 1000.0, "step": 10.0},
                }
            ),
        }
    )

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength

        D = self.length_frac * wavelength
        s = self.spacing_frac * wavelength
        half = D / 2
        tilt = math.radians(self.tilt_deg)

        def P(x, y):
            # Place in a plane tilted about the x-axis: the long axis (y)
            # slopes up by `tilt`; the fold spacing (x) stays horizontal.
            return (x, y * math.cos(tilt), y * math.sin(tilt) + self.base)

        arm = self.segs_for(half - eps, quarter)
        short = self.segs_for(s, quarter)

        # near wire (feed) at x=0; far wire (termination) at x=s
        nL, nR = P(0.0, -half), P(0.0, half)
        nF0, nF1 = P(0.0, -eps), P(0.0, eps)
        fL, fR = P(s, -half), P(s, half)
        fT0, fT1 = P(s, -eps), P(s, eps)

        return [
            # near (feed) wire: left arm, feed gap, right arm
            (nL, nF0, arm, None, None),
            (nF0, nF1, 1, None, "feed"),
            (nF1, nR, arm, None, None),
            # far (termination) wire: left arm, load gap, right arm
            (fL, fT0, arm, None, None),
            (fT0, fT1, 1, None, "term"),
            (fT1, fR, arm, None, None),
            # end shorts joining the two wires
            (nL, fL, short, None, None),
            (nR, fR, short, None, None),
        ]

    def build_network(self):
        return Network(
            ports={"feed": PortAtEdge("feed"), "term": PortAtEdge("term")},
            branches=[Load(port="term", r=self.term_r)],
            sources=[Driven(port="feed", voltage=1 + 0j)],
        )
