"""Log-periodic dipole array (LPDA) (L. B. Cebik, W4RNL; ARRL Antenna Book
LPDA chapter).

A frequency-INDEPENDENT array: a row of parallel dipoles whose lengths and
spacings shrink geometrically toward the front by a constant ratio tau, fed
by a TRANSPOSED (phase-alternating) feeder boom. At any frequency in the
design band only the two or three dipoles near a half-wavelength form the
"active region" and radiate as a small driver/reflector/director group; the
active region slides along the array with frequency, so gain, pattern, and
feed impedance stay roughly constant over a very wide band. The beam fires
toward the SHORT (apex) end. This is a completely different design law from
every resonant antenna in the catalog.

Two constants describe the array (with the band edges):
  tau   = l(n+1)/l(n) = d(n+1)/d(n)        element scaling ratio (< 1)
  sigma = d(n) / (2 * l(n))                relative spacing constant
with the optimum sigma_opt = 0.243*tau - 0.051. The half apex angle follows
from cot(alpha) = 4*sigma/(1 - tau).

The transposed feeder is modeled with ideal transmission lines joining
adjacent element centres, every one CROSSED (the TL `transposed` flag -- a
port-B polarity inversion) to supply the 180-degree section-to-section
phase reversal. The array is driven at the front (shortest) element.

CAVEAT -- feedpoint impedance: the feeder is modeled as a cascade of IDEAL,
LOSSLESS crossed transmission lines. That cascade has internal resonances
that NEC2's tl_card does not damp, so the computed driving-point impedance is
unreliable (it can swing wildly and even show a negative real part at
scattered in-band frequencies). A real LPDA's feeder loss plus a termination
stub behind the longest element suppress this. The robust, physically
meaningful outputs of this model are the GAIN and the forward PATTERN, which
stay LPDA-like (~6-9 dBi, fires toward the apex) across the whole band; treat
the SWR/impedance readout as indicative only.

Geometry, in the framework's (x, y, z) convention:
  - x : boom axis; longest element at the back (x=0), shortest at the
        front (max x); the beam fires toward +x
  - y : the dipole length axis (all elements horizontal, centre at y=0)
  - z : constant height `base`
Horizontally polarised.

      d0      d1   d2  d3 ...                          (lengths shrink by tau)
    |         |        |    |   <- crossed feeder ->  F (driven, front)
   back (low freq)                              front (high freq), beam --> +x
"""

from ... import AntennaBuilder
from ...network import Driven, Network, PortOnWire, TL
from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            # Operating/test frequency. The band runs from `freq_low_factor`
            # * design_freq upward; design_freq sits inside the active region.
            "design_freq": 28.57,
            "freq": 28.57,
            "base": 10.0,
            # Highest band edge as a fraction of design_freq: the shortest
            # (front) element is a half wave here. >1 so design_freq sits
            # just inside the top of the band, at the front of the active
            # region where the feed is -- the longer elements extend the
            # band downward.
            "freq_high_factor": 1.15,
            # Element scaling ratio and relative spacing constant. sigma near
            # the optimum sigma_opt = 0.243*tau - 0.051 (~0.168 for tau=0.9)
            # for good gain; lower sigma compresses the array and drops gain.
            "tau": 0.9,
            "sigma": 0.14,
            # Number of dipole elements.
            "n_elements": 10,
            # Feeder (boom) characteristic impedance in ohms; modeled crossed.
            "z0": 100.0,
            # Overall length trim of the active region.
            "length_factor": 1.0,
            "ui_params": MappingProxyType(
                {
                    "target_z0": 50.0,
                    "default_view": "xy",
                    "n_elements": {"min": 4, "max": 16, "step": 1},
                    "tau": {"min": 0.8, "max": 0.95},
                    "sigma": {"min": 0.03, "max": 0.18},
                    "length_factor": {
                        "min": 0.85,
                        "max": 1.05,
                    },
                }
            ),
        }
    )

    def _layout(self):
        """Element half-lengths h[n] and boom positions x[n], longest (n=0)
        at the back. Shared by build_wires and build_network."""
        c = 299.792458
        n = int(self.n_elements)
        tau = self.tau
        sigma = self.sigma

        lam_high = c / (self.freq_high_factor * self.design_freq)
        l_min = 0.5 * lam_high * self.length_factor  # shortest (front) element

        # k = 0 longest (back) ... k = n-1 shortest (front).
        lengths = [l_min / tau ** (n - 1 - k) for k in range(n)]
        half = [le / 2 for le in lengths]
        # spacing d_k = 2*sigma*l_k between element k and k+1
        x = [0.0]
        for k in range(n - 1):
            x.append(x[-1] + 2 * sigma * lengths[k])
        return half, x

    def build_wires(self):
        eps = 0.05
        wavelength = 299.792458 / self.design_freq
        quarter = 0.25 * wavelength
        half, x = self._layout()
        n = int(self.n_elements)
        z = self.base

        tups = []
        for k in range(n):
            h = half[k]
            xk = x[k]
            L = (xk, -h, z)
            C0 = (xk, -eps, z)
            C1 = (xk, eps, z)
            R = (xk, h, z)
            arm = self.segs_for(h - eps, quarter)
            # left arm, named centre gap (a feeder port), right arm
            tups.append((L, C0, arm, None, None))
            tups.append((C0, C1, 1, None, f"d{k}"))
            tups.append((C1, R, arm, None, None))
        return tups

    def build_network(self):
        half, x = self._layout()
        n = int(self.n_elements)
        z0 = self.z0

        ports = {f"d{k}": PortOnWire(f"d{k}") for k in range(n)}
        branches = []
        # Crossed feeder section between adjacent element centres. Length =
        # physical boom spacing; transposed=True gives the 180-degree
        # section-to-section phase reversal of the transposed feeder.
        for k in range(n - 1):
            branches.append(
                TL(
                    a=f"d{k}",
                    b=f"d{k + 1}",
                    z0=z0,
                    length=x[k + 1] - x[k],
                    transposed=True,
                )
            )
        # Driven at the front (shortest) element.
        return Network(
            ports=ports,
            branches=branches,
            sources=[Driven(port=f"d{n - 1}", voltage=1 + 0j)],
        )
