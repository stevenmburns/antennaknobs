"""Touchstone (``.s1p`` / ``.s2p``) reader for measured / vendor-supplied
S-parameters (issue #593).

A Touchstone file describes an N-port's network parameters versus frequency:
``.s1p`` a 1-port (a single ``S11`` — an antenna feedpoint, a load, a
termination), ``.s2p`` a 2-port (``S11 S21 S12 S22`` — a balun, coax section,
filter, or tuner as a black box). Both share one header::

    # <HZ|KHZ|MHZ|GHZ> <S|Y|Z> <RI|MA|DB> R <z0>

This module parses that format into a :class:`Touchstone`, which interpolates
onto any solve frequency and converts to the admittance the network reducer
stamps. The circuit *elements* that consume it live in ``network.py``
(``TouchstoneLoad`` / ``TouchstoneTwoPort``); because they stamp into the
``NetworkReducer`` — post-MoM circuit math — they work on **both** momwire and
PyNEC, unlike a geometry-level feed such as ``PortAtEnd``.

Only 1- and 2-port ``S`` / ``Y`` / ``Z`` files are supported (the VNA case);
``G`` / ``H`` parameters and N > 2 raise a clear error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .design_data import read_data

__all__ = [
    "Touchstone",
    "parse_touchstone",
    "read_touchstone",
    "format_s1p",
]

# Touchstone frequency-unit keywords → multiplier to Hz.
_FUNIT = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}


@dataclass(frozen=True, eq=False)
class Touchstone:
    """Parsed Touchstone data: complex network parameters on a frequency grid.

    ``freqs`` is in Hz (ascending); ``params`` is ``(n_freq, nports, nports)``
    complex in the declared parameter type (``ptype`` ∈ {S, Y, Z}); ``z0`` is
    the real reference impedance from the header. ``eq=False`` so instances
    hash/compare by identity (the arrays make value-equality meaningless and
    unhashable), which keeps the frozen branch dataclasses that hold one usable.
    """

    freqs: np.ndarray
    params: np.ndarray
    ptype: str
    z0: float

    @property
    def nports(self) -> int:
        return self.params.shape[1]

    def _interp(self, f_hz: float) -> np.ndarray:
        """Linear-interpolate the parameter matrix onto ``f_hz`` (Hz).

        Raises ``ValueError`` when ``f_hz`` falls outside the data's frequency
        span — measured data must not be silently extrapolated.
        """
        f0, f1 = float(self.freqs[0]), float(self.freqs[-1])
        tol = 1e-6 * max(abs(f1), 1.0)
        if f_hz < f0 - tol or f_hz > f1 + tol:
            raise ValueError(
                f"solve frequency {f_hz / 1e6:.6g} MHz is outside the Touchstone "
                f"data range [{f0 / 1e6:.6g}, {f1 / 1e6:.6g}] MHz — measured data "
                "is not extrapolated; widen the sweep or the measurement"
            )
        n = self.nports
        m = np.empty((n, n), dtype=np.complex128)
        for i in range(n):
            for j in range(n):
                col = self.params[:, i, j]
                m[i, j] = np.interp(f_hz, self.freqs, col.real) + 1j * np.interp(
                    f_hz, self.freqs, col.imag
                )
        return m

    def s_at(self, f_hz: float) -> np.ndarray:
        """S-parameter matrix at ``f_hz`` (converting from Y/Z if needed)."""
        m = self._interp(f_hz)
        if self.ptype == "S":
            return m
        n = self.nports
        eye = np.eye(n)
        z = m if self.ptype == "Z" else np.linalg.inv(m)
        return (z - self.z0 * eye) @ np.linalg.inv(z + self.z0 * eye)

    def y_at(self, f_hz: float) -> np.ndarray:
        """Admittance matrix (siemens) at ``f_hz`` — what the reducer stamps."""
        m = self._interp(f_hz)
        if self.ptype == "Y":
            return m
        if self.ptype == "Z":
            return np.linalg.inv(m)
        n = self.nports
        eye = np.eye(n)
        # real reference z0:  Y = (1/z0)·(I − S)·(I + S)⁻¹
        return (1.0 / self.z0) * (eye - m) @ np.linalg.inv(eye + m)

    def z_at(self, f_hz: float) -> np.ndarray:
        """Impedance matrix (ohms) at ``f_hz``."""
        m = self._interp(f_hz)
        if self.ptype == "Z":
            return m
        if self.ptype == "Y":
            return np.linalg.inv(m)
        n = self.nports
        eye = np.eye(n)
        return self.z0 * (eye + m) @ np.linalg.inv(eye - m)


def _nports_from_name(name: str) -> int:
    low = name.lower()
    if low.endswith(".s1p"):
        return 1
    if low.endswith(".s2p"):
        return 2
    raise ValueError(
        f"{name!r}: expected a .s1p or .s2p Touchstone extension "
        "(only 1- and 2-port files are supported)"
    )


def parse_touchstone(text: str, *, nports: int | None = None) -> Touchstone:
    """Parse Touchstone ``text`` into a :class:`Touchstone`.

    ``nports`` is taken from the file extension by :func:`read_touchstone`; when
    omitted here it is inferred from the first data record's width
    (``1 + 2·nports²`` numbers per frequency). Honors the header's frequency
    unit (HZ/KHZ/MHZ/GHZ), parameter type (S/Y/Z), format (RI/MA/DB) and
    reference impedance (``R <z0>``); Touchstone's own defaults (GHz, S, MA,
    50 Ω) apply when the option line omits a field.
    """
    funit, ptype, fmt, z0 = _FUNIT["GHZ"], "S", "MA", 50.0
    rows: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.split("!", 1)[0].strip()  # drop ! comments
        if not line:
            continue
        if line.startswith("#"):
            toks = line[1:].upper().split()
            i = 0
            while i < len(toks):
                t = toks[i]
                if t in _FUNIT:
                    funit = _FUNIT[t]
                elif t in ("S", "Y", "Z", "G", "H"):
                    ptype = t
                elif t in ("RI", "MA", "DB"):
                    fmt = t
                elif t == "R" and i + 1 < len(toks):
                    z0 = float(toks[i + 1])
                    i += 1
                i += 1
            continue
        rows.append(line.split())

    if ptype in ("G", "H"):
        raise ValueError(f"{ptype}-parameter Touchstone files are not supported")
    if not rows:
        raise ValueError("Touchstone file has no data rows")

    if nports is None:
        width = len(rows[0])  # 1 freq + 2·nports² values, one record per line
        n2 = (width - 1) // 2
        nports = int(round(n2**0.5))
        if nports not in (1, 2) or 1 + 2 * nports * nports != width:
            raise ValueError(
                f"cannot infer port count from a {width}-column data row "
                "(expected 3 for .s1p or 9 for .s2p)"
            )
    if nports not in (1, 2):
        raise ValueError("only 1- and 2-port Touchstone files are supported")

    rec = 1 + 2 * nports * nports
    vals = np.array([float(x) for row in rows for x in row], dtype=float)
    if vals.size % rec != 0:
        raise ValueError(
            f"Touchstone data length {vals.size} is not a multiple of the "
            f"{rec}-number record for a {nports}-port file"
        )
    arr = vals.reshape(-1, rec)
    freqs = arr[:, 0] * funit
    pairs = arr[:, 1:].reshape(arr.shape[0], nports * nports, 2)

    a, b = pairs[:, :, 0], pairs[:, :, 1]
    if fmt == "RI":
        comp = a + 1j * b
    elif fmt == "MA":
        comp = a * np.exp(1j * np.deg2rad(b))
    else:  # DB
        comp = (10.0 ** (a / 20.0)) * np.exp(1j * np.deg2rad(b))

    nf = arr.shape[0]
    params = np.empty((nf, nports, nports), dtype=np.complex128)
    if nports == 1:
        params[:, 0, 0] = comp[:, 0]
    else:  # Touchstone 2-port column order is S11 S21 S12 S22
        params[:, 0, 0] = comp[:, 0]
        params[:, 1, 0] = comp[:, 1]
        params[:, 0, 1] = comp[:, 2]
        params[:, 1, 1] = comp[:, 3]

    order = np.argsort(freqs)
    return Touchstone(
        freqs=freqs[order], params=params[order], ptype=ptype, z0=float(z0)
    )


def format_s1p(
    freqs_hz, s11, *, z0: float = 50.0, comments: tuple[str, ...] = ()
) -> str:
    """Render a one-port sweep as Touchstone ``.s1p`` text (MHz, S, RI).

    The writing counterpart of :func:`parse_touchstone`, used by the VNA
    capture path (issue #597) so a captured sweep becomes an ordinary file that
    the overlay, ``fit``, and every other Touchstone-reading tool consume — the
    same format, not a private one. MHz keeps the numbers readable against the
    rest of antennaknobs; real/imaginary keeps them exact.
    """
    import numpy as _np

    f = _np.asarray(freqs_hz, dtype=float)
    g = _np.asarray(s11, dtype=complex)
    if f.shape != g.shape:
        raise ValueError(f"{f.size} frequencies but {g.size} S11 values")
    lines = [f"! {c}" for c in comments]
    lines.append(f"# MHZ S RI R {z0:g}")
    lines += [f"{a / 1e6:.6f} {v.real:+.9f} {v.imag:+.9f}" for a, v in zip(f, g)]
    return "\n".join(lines) + "\n"


def read_touchstone(builder, name: str) -> Touchstone:
    """Read a Touchstone file from the calling design's own folder.

    Confined exactly like :func:`antennaknobs.read_data` / ``read_json`` (no
    ``..`` escape, no symlink-out); the port count comes from the ``.s1p`` /
    ``.s2p`` extension. Use it in ``build_network()``::

        s = read_touchstone(self, "measured_antenna.s1p")
        return Network(..., branches=[TouchstoneLoad("ant", s), ...])
    """
    nports = _nports_from_name(name)  # validate extension before touching disk
    return parse_touchstone(read_data(builder, name), nports=nports)
