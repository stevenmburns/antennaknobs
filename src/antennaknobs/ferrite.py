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

## Where the numbers come from

Fair-Rite publishes each material's **measured** complex permeability as a CSV,
for exactly this purpose. :func:`fetch_material` downloads one on first use and
caches it under ``~/.antennaknobs/ferrite``; nothing vendor-supplied is
redistributed with this package, and after the first call everything is
offline. :meth:`FerriteMaterial.from_table` takes your own data — measured
cores beat vendor nominals, since the vendor never wound *your* toroid.

An earlier version of this module shipped one-pole (Debye) fits from
remembered headline specs instead, and it is worth recording why that was
abandoned rather than corrected. Checked against the published files, the
assumed relaxation frequencies were wrong by up to **8×** (mix 43's μ″ peaks at
4.4 MHz, not the 35 assumed). Worse, refitting does not save the idea: against
the real curves over 0.1–100 MHz, the best one-pole fit is 30–60% out, and the
best *two*-pole fit still misses by 22–60% for every mix except 31. These NiZn
ferrites have a distribution of relaxation times, so no small parametric
catalog can be honest about their loss — the table is the data.

:meth:`FerriteMaterial.debye` remains, clearly as a *synthetic* material: handy
for tests and for reasoning about an idealized single relaxation, not a stand-in
for a real mix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = [
    "CORES",
    "MATERIAL_URLS",
    "FerriteCore",
    "FerriteMaterial",
    "cache_dir",
    "core",
    "core_from_catalog",
    "fetch_material",
    "parse_permeability_csv",
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


# --- vendor data -----------------------------------------------------------
# Fair-Rite publishes measured complex permeability per material as a CSV, for
# exactly this purpose. Those files are NOT redistributed here — they are
# fetched on first use and cached locally, so the package ships no vendor data
# while the user still gets the vendor's own measurements rather than someone's
# approximation of them.
#
# An earlier version of this module shipped one-pole Debye fits instead. They
# were wrong: measured against these files, the assumed relaxation frequencies
# were off by up to 8x (mix 43 peaks at 4.4 MHz, not 35), and even a
# best-fit 2-pole model lands 22-60% out over 0.1-100 MHz for every mix except
# 31. A distribution of relaxation times is what these NiZn ferrites actually
# have, so no small parametric catalog can be honest here — the table is the
# data.
MATERIAL_URLS = {
    "31": "https://www.fair-rite.com/wp-content/uploads/2015/03/31-Material-Fair-Rite.csv",
    "43": "https://www.fair-rite.com/wp-content/uploads/2020/11/43-Material-publish.csv",
    "52": "https://www.fair-rite.com/wp-content/uploads/2015/04/52-Material-Fair-Rite.csv",
    "61": "https://www.fair-rite.com/wp-content/uploads/2021/11/61-Material-Fair-Rite.csv",
    "77": "https://www.fair-rite.com/wp-content/uploads/2015/04/77-Material-Fair-Rite.csv",
}


def cache_dir():
    """Where fetched material files live (``~/.antennaknobs/ferrite``)."""
    import os

    root = os.environ.get("ANTENNAKNOBS_USER_DIR")
    base = Path(root) if root else Path.home() / ".antennaknobs"
    return base / "ferrite"


def parse_permeability_csv(text: str, name: str = "", source: str = ""):
    """Parse a vendor complex-permeability CSV into a `FerriteMaterial`.

    Deliberately forgiving, because these files are hand-maintained: title
    rows, blank lines, an "Equipment Used:" note, a mis-encoded ``µ`` in the
    header, and Hz frequencies all appear across the five Fair-Rite files.
    Any line whose first three comma-separated fields parse as numbers is a
    data row; everything else is ignored.
    """
    freqs, mp, md = [], [], []
    for line in text.replace("\r", "\n").split("\n"):
        parts = [c.strip() for c in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            f, a, b = float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            continue
        if f > 0 and a > 0:
            freqs.append(f / 1e6)  # the files are in Hz; we work in MHz
            mp.append(a)
            md.append(max(b, 0.0))
    if len(freqs) < 2:
        raise ValueError(
            f"{name or 'material'}: no usable rows in the permeability data "
            "(expected 'frequency,mu-prime,mu-double' lines)"
        )
    return FerriteMaterial.from_table(name, freqs, mp, md, source=source)


def fetch_material(mix: str, *, refresh: bool = False) -> FerriteMaterial:
    """The vendor's measured permeability for ``mix``, fetched once and cached.

    Downloads to :func:`cache_dir` on first use and reads the cache thereafter,
    so this is a one-time network call and everything afterwards is offline.
    ``refresh=True`` re-downloads.

    No network and no cache is a clear error naming the URL, because copying
    that file into the cache directory by hand is a perfectly good substitute
    and the message should say so.
    """
    if mix not in MATERIAL_URLS:
        raise KeyError(
            f"no published data URL for mix {mix!r}; known: "
            f"{', '.join(sorted(MATERIAL_URLS))}. Use "
            "FerriteMaterial.from_table() for a material you have data for."
        )
    url = MATERIAL_URLS[mix]
    path = cache_dir() / f"{mix}.csv"
    if refresh or not path.exists():
        try:
            from urllib.request import Request, urlopen

            req = Request(url, headers={"User-Agent": "antennaknobs"})
            with urlopen(req, timeout=30) as fh:  # noqa: S310 — fixed https URL
                data = fh.read()
        except Exception as e:
            if path.exists():
                pass  # a stale cache beats no material
            else:
                raise RuntimeError(
                    f"could not fetch the permeability data for mix {mix}: {e}\n"
                    f"Download {url} to {path} and re-run — the file is only "
                    "read locally after the first fetch."
                ) from e
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return parse_permeability_csv(
        path.read_text(encoding="latin-1"),
        name=mix,
        source=f"measured complex permeability, {url}",
    )


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


def core(size: str, material: FerriteMaterial, turns: float, c_stray_pF: float = 0.0):
    """A wound core from a catalog SIZE and a material you already hold.

    The offline half of :func:`core_from_catalog`: pass a material from
    :func:`fetch_material`, :meth:`FerriteMaterial.from_table` (your own
    measurements), or :meth:`FerriteMaterial.debye` (a synthetic one).
    """
    if size not in CORES:
        raise KeyError(
            f"unknown core size {size!r}; available: {', '.join(sorted(CORES))}"
        )
    if turns <= 0:
        raise ValueError(f"turns must be positive; got {turns}")
    ae, le = CORES[size]
    return FerriteCore(
        material=material,
        turns=float(turns),
        ae=ae,
        le=le,
        c_stray=c_stray_pF * 1e-12,
    )


def core_from_catalog(
    size: str, mix: str, turns: float, c_stray_pF: float = 0.0
) -> FerriteCore:
    """``core_from_catalog("FT-240", "43", 11)`` — the ham spelling of a core.

    Fetches the mix's published permeability on first use (see
    :func:`fetch_material`), so the first call needs network and later ones do
    not. ``c_stray_pF`` is the winding's self-capacitance; give it a couple of
    pF to reproduce the impedance peak a real choke shows.
    """
    return core(size, fetch_material(mix), turns, c_stray_pF)
