"""Crossed dipoles fed in phase quadrature (turnstile)."""

from antennaknobs import AntennaBuilder
import math

from types import MappingProxyType


class Builder(AntennaBuilder):
    default_params = MappingProxyType(
        {
            "design_freq": 28.47,
            "freq": 28.47,
            "base": 7.0,
            # Half-wave dipole in free space resonates near 0.48*lambda; tuned
            # slightly short to land closer to resonance with the finite wire
            # radius assumed elsewhere.
            "length_factor": 0.48,
            # Vertical separation between the two crossed dipoles (metres).
            "gap_z": 0.10,
        }
    )

    def build_wires(self):
        eps = 0.05

        wavelength = 299.792458 / self.design_freq
        length = wavelength * self.length_factor
        x = 0.5 * length

        n_seg0 = self.nominal_nsegs

        # Two crossed half-wave dipoles, lower along x at z=base and upper
        # along y at z=base+gap_z. The 1+0j / 0+1j drive is the 90° turnstile
        # phasing that produces (near-)circular polarisation broadside.
        tups = []

        z_lo = self.base
        n_seg1 = self.segs_for(
            math.dist((-eps, 0, z_lo), (eps, 0, z_lo)),
            math.dist((-x, 0, z_lo), (-eps, 0, z_lo)),
        )
        tups.extend([((-x, 0, z_lo), (-eps, 0, z_lo), n_seg0, None)])
        tups.extend([((eps, 0, z_lo), (x, 0, z_lo), n_seg0, None)])
        tups.extend([((-eps, 0, z_lo), (eps, 0, z_lo), n_seg1, 1 + 0j)])

        z_hi = self.base + self.gap_z
        tups.extend([((0, -x, z_hi), (0, -eps, z_hi), n_seg0, None)])
        tups.extend([((0, eps, z_hi), (0, x, z_hi), n_seg0, None)])
        tups.extend([((0, -eps, z_hi), (0, eps, z_hi), n_seg1, 0 + 1j)])

        return tups
