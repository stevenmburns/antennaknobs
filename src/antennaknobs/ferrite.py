"""Ferrite cores by material and geometry (issue #599).

`Transformer` and `FloatingBalun` model core loss with one number: a
frequency-independent Q on the magnetizing branch (`qlmag`). Real ferrite has a
strongly frequency-dependent **complex permeability** ``μ = μ′ − jμ″``, and
that frequency dependence is the whole story of a choke: a 43-mix balun burns
its watts in one part of the spectrum and is nearly lossless elsewhere. A flat
Q cannot express "loses most here, little there", which is precisely the
question someone modelling a choke is asking.

The magnetizing impedance of ``turns`` turns on a core of effective
cross-section ``ae`` and magnetic path length ``le`` is

    Z_mag(f) = jω · N²·μ₀·A_e/l_e · (μ′(f) − j·μ″(f))
             = ω·k·μ″(f)  +  jω·k·μ′(f)          [k = N²μ₀A_e/l_e]

— so ``μ′`` sets the inductance and ``μ″`` sets the loss, and the effective Q
is just ``μ′/μ″``. That last identity is the bridge to the old model: a
material with flat ``μ′`` and ``μ″ = μ′/Q`` reproduces scalar ``qlmag``
exactly, which is asserted by a test.

## Where the numbers come from, and what they are not

The catalog below does **not** ship digitized vendor curves — neither ours to
redistribute nor honest to present as measurements we made. Each mix is a
**single-pole (Debye) relaxation fit**

    μ(f) = μ_i / (1 + j·f/f_r)   ⇒   μ′ = μ_i/(1+x²),  μ″ = μ_i·x/(1+x²)

parameterized by an initial permeability ``μ_i`` and a relaxation frequency
``f_r`` where ``μ″`` peaks. The *shape* is the one every ferrite datasheet
shows — μ′ rolling off, μ″ peaking at ``f_r`` at half of μ_i, loss falling away
either side.

**The catalog's per-mix numbers are UNVERIFIED.** They were chosen from
recollection of the usual headline specs, not read off a datasheet and not
fitted to a measurement. Use them to compare mixes, turns counts and bands —
the ordering and the shape are right — and do **not** quote an absolute loss
figure from them. Every entry's ``source`` says so and a test enforces it.

Even with good parameters it is **not** the datasheet curve: near the
relaxation knee a real mix departs from a single pole, and mixes with more than
one loss mechanism (31 in particular) are two-pole animals.

Two ways to do better, both supported today. If you have the real ``μ′``/``μ″``
table, :meth:`FerriteMaterial.from_table` takes it. If you have a VNA, sweep a
known choke and fit ``μ_i``/``f_r``/``c_stray`` to it — that makes the
provenance a measurement you can reproduce, which beats a datasheet read
because it is *your* core rather than a vendor nominal.

Treat catalog values as representative, in exactly the same spirit as the
``CABLES`` matched-loss coefficients.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "CORES",
    "MATERIALS",
    "FerriteCore",
    "FerriteMaterial",
    "core_from_catalog",
    "material_from_catalog",
]

MU0 = 4.0e-7 * math.pi  # H/m


@dataclass(frozen=True, eq=False)
class FerriteMaterial:
    """Complex permeability ``μ′ − jμ″`` versus frequency for one ferrite mix.

    ``freqs`` is MHz ascending; ``mu_prime`` and ``mu_double`` are the real and
    (positive) imaginary parts. ``source`` records where the numbers came from
    — every catalog entry says so, because "which curve is this?" is the first
    question anyone comparing against a measurement will ask.
    """

    name: str
    freqs: np.ndarray
    mu_prime: np.ndarray
    mu_double: np.ndarray
    source: str = ""

    @classmethod
    def from_table(cls, name, freqs_mhz, mu_prime, mu_double, *, source=""):
        """Build from a real ``μ′``/``μ″`` table (your data beats our fit)."""
        f = np.asarray(freqs_mhz, dtype=float)
        mp = np.asarray(mu_prime, dtype=float)
        md = np.asarray(mu_double, dtype=float)
        if not (f.shape == mp.shape == md.shape) or f.ndim != 1 or f.size < 2:
            raise ValueError(
                "freqs, mu_prime and mu_double must be 1-D and equal length"
            )
        if np.any(np.diff(f) <= 0):
            order = np.argsort(f)
            f, mp, md = f[order], mp[order], md[order]
        if np.any(mp <= 0) or np.any(md < 0):
            raise ValueError("μ′ must be positive and μ″ non-negative")
        return cls(name=name, freqs=f, mu_prime=mp, mu_double=md, source=source)

    @classmethod
    def debye(cls, name, mu_i, f_relax_mhz, *, source="", decades=(-2.0, 3.0), n=241):
        """Single-pole relaxation fit — see the module docstring for its limits.

        ``mu_i`` is the initial permeability, ``f_relax_mhz`` the frequency
        where ``μ″`` peaks (at ``mu_i/2``). Sampled over five decades so the
        table interpolates smoothly across anything HF/VHF.
        """
        f = np.logspace(
            math.log10(f_relax_mhz) + decades[0],
            math.log10(f_relax_mhz) + decades[1],
            n,
        )
        x = f / f_relax_mhz
        denom = 1.0 + x * x
        return cls(
            name=name,
            freqs=f,
            mu_prime=mu_i / denom,
            mu_double=mu_i * x / denom,
            source=source,
        )

    def at(self, f_mhz: float) -> complex:
        """``μ′ − jμ″`` at ``f_mhz``, interpolated in log-frequency.

        Log-f because permeability curves are published on log axes and vary
        over decades; interpolating linearly in f would badly undercut μ″
        between sparse low-frequency points.

        Outside the tabulated span this raises rather than extrapolating. A
        loss curve invented past its data is most wrong exactly where the user
        is most likely to be mistaken about the material.
        """
        f0, f1 = float(self.freqs[0]), float(self.freqs[-1])
        if not f0 * (1 - 1e-9) <= f_mhz <= f1 * (1 + 1e-9):
            raise ValueError(
                f"{self.name}: {f_mhz:.6g} MHz is outside the material data "
                f"[{f0:.4g}, {f1:.4g}] MHz — permeability is not extrapolated"
            )
        lf = np.log10(np.maximum(self.freqs, 1e-30))
        x = math.log10(max(f_mhz, 1e-30))
        mp = float(np.interp(x, lf, self.mu_prime))
        md = float(np.interp(x, lf, self.mu_double))
        return complex(mp, -md)

    def q_at(self, f_mhz: float) -> float:
        """Effective magnetizing Q, ``μ′/μ″`` — the scalar this replaces."""
        mu = self.at(f_mhz)
        return float("inf") if -mu.imag == 0.0 else mu.real / -mu.imag


@dataclass(frozen=True, eq=False)
class FerriteCore:
    """A wound core: a material, a size, and a turns count.

    ``ae`` (effective cross-section, m²) and ``le`` (effective magnetic path
    length, m) are the core's geometry; ``turns`` is what the builder wound.
    Use :func:`core_from_catalog` for the common sizes.
    """

    material: FerriteMaterial
    turns: float
    ae: float
    le: float
    #: Winding self-capacitance in farads, in parallel with the magnetizing
    #: branch. Small (a few pF) and easy to dismiss, but it is what makes a
    #: real choke's |Z| PEAK and then fall instead of climbing forever: the
    #: winding parallel-resonates with it. Without it a single-relaxation
    #: material gives a monotonically saturating |Z| — and, across an ideal
    #: voltage source, an exactly frequency-flat conductance (the μ″ growth and
    #: the |μ|² growth cancel), which is a property of the one-pole model, not
    #: of ferrite. Default 0 leaves the pure magnetizing branch.
    c_stray: float = 0.0

    @property
    def al_factor(self) -> float:
        """``N²·μ₀·A_e/l_e`` — the geometry constant, henries per unit μ."""
        return self.turns**2 * MU0 * self.ae / self.le

    def inductance(self, f_mhz: float) -> float:
        """Magnetizing inductance (H) at ``f_mhz``, from ``μ′``."""
        return self.al_factor * self.material.at(f_mhz).real

    def impedance(self, f_mhz: float) -> complex:
        """Magnetizing impedance ``jω·k·(μ′ − jμ″)`` — the branch the reducer
        stamps. Its real part *is* the core loss, and it peaks near the
        material's relaxation frequency rather than tracking ω forever.
        """
        omega = 2.0 * math.pi * f_mhz * 1e6
        mu = self.material.at(f_mhz)
        z = 1j * omega * self.al_factor * mu
        if self.c_stray:
            y = 1.0 / z + 1j * omega * self.c_stray
            return 1.0 / y
        return z


# --- catalogs --------------------------------------------------------------
# Mixes as single-pole fits. Each is parameterized by an initial permeability
# and a relaxation frequency, and BOTH NUMBERS ARE UNVERIFIED: they were chosen
# from recollection of the usual headline specs and have not been checked
# against a datasheet or a measurement. They give the right shape and the right
# ordering between mixes — which is what "compare 31 against 43 on 20 m" needs
# — and they are NOT a basis for an absolute watts figure.
#
# The fix is issue #599's follow-up: sweep a known choke per mix and fit
# (mu_i, f_relax, c_stray) to it, which makes the provenance a measurement you
# can reproduce rather than a number someone remembered. Until then every entry
# says UNVERIFIED, and a test enforces that it does.
MATERIALS = {
    "31": FerriteMaterial.debye(
        "31",
        1500.0,
        8.0,
        source="UNVERIFIED one-pole fit (μi≈1500, μ″ peak ≈8 MHz) — not checked against a datasheet; calibrate before trusting absolute loss",
    ),
    "43": FerriteMaterial.debye(
        "43",
        800.0,
        35.0,
        source="UNVERIFIED one-pole fit (μi≈800, μ″ peak ≈35 MHz) — not checked against a datasheet; calibrate before trusting absolute loss",
    ),
    "52": FerriteMaterial.debye(
        "52",
        250.0,
        60.0,
        source="UNVERIFIED one-pole fit (μi≈250, μ″ peak ≈60 MHz) — not checked against a datasheet; calibrate before trusting absolute loss",
    ),
    "61": FerriteMaterial.debye(
        "61",
        125.0,
        180.0,
        source="UNVERIFIED one-pole fit (μi≈125, μ″ peak ≈180 MHz) — not checked against a datasheet; calibrate before trusting absolute loss",
    ),
    "77": FerriteMaterial.debye(
        "77",
        2000.0,
        3.0,
        source="UNVERIFIED one-pole fit (μi≈2000, μ″ peak ≈3 MHz) — not checked against a datasheet; calibrate before trusting absolute loss",
    ),
}

# Toroid geometry in metres/m², from published nominal dimensions. Ae and le
# are the effective values manufacturers quote for the size, not derived from
# the OD/ID/height, so a core wound to the same turns count matches the
# vendor's own A_L within its tolerance.
CORES = {
    "FT-240": (3.79e-4, 0.1424),
    "FT-140": (1.44e-4, 0.0891),
    "FT-114": (0.749e-4, 0.0718),
    "FT-82": (0.246e-4, 0.0521),
    "FT-50": (0.133e-4, 0.0318),
}


def material_from_catalog(name: str) -> FerriteMaterial:
    """The `MATERIALS` entry for a mix, with `TL.from_cable`'s ergonomics."""
    if name not in MATERIALS:
        raise KeyError(
            f"unknown ferrite mix {name!r}; available: {', '.join(sorted(MATERIALS))}"
        )
    return MATERIALS[name]


def core_from_catalog(
    size: str, mix: str, turns: float, c_stray_pF: float = 0.0
) -> FerriteCore:
    """``core_from_catalog("FT-240", "43", 11)`` — the ham spelling of a core.

    ``c_stray_pF`` is the winding's self-capacitance; give it a couple of pF to
    reproduce the impedance peak a real choke shows (see `FerriteCore`).
    """
    if size not in CORES:
        raise KeyError(
            f"unknown core size {size!r}; available: {', '.join(sorted(CORES))}"
        )
    ae, le = CORES[size]
    if turns <= 0:
        raise ValueError(f"turns must be positive; got {turns}")
    return FerriteCore(
        material=material_from_catalog(mix),
        turns=float(turns),
        ae=ae,
        le=le,
        c_stray=c_stray_pF * 1e-12,
    )
