"""Capture a sweep straight off a VNA (issue #597).

``measured.py`` overlays a ``.s1p`` someone else's software wrote. This module
produces that file: connect to an analyzer over USB serial, run a one-port
sweep, and write the Touchstone the overlay and ``fit`` already read. The
workflow is deliberately **file-mediated** —

    python -m antennaknobs capture --out bench.s1p --start 27 --stop 30
    python -m antennaknobs sweep --builder ... --measured bench.s1p --swr

— rather than a live socket into the plotting code. Two reasons, one practical
and one about trust:

*Practical.* The web backend commonly runs on another machine while the VNA is
plugged in here (see the workbench docs). A local capture writing a local file,
uploaded through the browser, works in every topology; a server-side capture
would open *the server's* serial ports, which on a shared instance is both
wrong and a hazard. Nothing here is reachable from ``web/server.py``, and that
is deliberate.

*Trust.* Talking to hardware is a capability the rest of antennaknobs doesn't
need. Keeping it in one CLI command, invoked explicitly, with the device named
or auto-detected and reported, means it never happens as a side effect of
something else.

Drivers are pluggable: a driver is any object with :meth:`Driver.sweep`, and
:data:`DRIVERS` maps CLI names to them. ``nanovna`` speaks the console protocol
that NanoVNA-H / NanoVNA-Saver firmware exposes; a DG8SAQ (or anything else
with a documented protocol) drops in beside it without touching the CLI.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

__all__ = [
    "DRIVERS",
    "Driver",
    "NanoVNADriver",
    "SerialTransport",
    "VNAError",
    "capture",
    "list_candidate_ports",
]

logger = logging.getLogger(__name__)

# USB VID/PID pairs that identify a NanoVNA-class device. The STM32 virtual COM
# port (0483:5740) covers the original NanoVNA and the -H/-H4; 16c0:0483 is the
# Objective Development shared VID some clones ship with.
NANOVNA_USB_IDS = ((0x0483, 0x5740), (0x16C0, 0x0483))

# NanoVNA firmware answers a command with its output followed by this prompt.
_PROMPT = b"ch>"


class VNAError(RuntimeError):
    """Any failure talking to an analyzer — no device, wrong device, bad reply."""


class Driver:
    """What a VNA driver has to provide.

    Not an ABC on purpose: a driver is duck-typed, so a user with an
    unsupported analyzer can pass their own object to :func:`capture` without
    importing anything from here.
    """

    name = "driver"

    def sweep(
        self, start_hz: float, stop_hz: float, points: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run a one-port sweep; return ``(freqs_hz, s11)`` as numpy arrays.

        Implementations should return whatever the instrument actually
        measured — if it clamps the point count or the span, report the clamped
        result rather than padding it out to what was asked for.
        """
        raise NotImplementedError


class SerialTransport:
    """Line-oriented serial link to an analyzer.

    Wraps pyserial so the drivers depend on a two-method interface
    (``write`` / ``read_until``) instead of on pyserial itself — which is what
    lets the protocol be tested without hardware, and keeps pyserial an
    optional extra (``pip install antennaknobs[vna]``).
    """

    def __init__(self, port: str, *, baudrate: int = 115200, timeout: float = 5.0):
        try:
            import serial  # noqa: PLC0415 — optional extra, imported on use
        except ImportError as e:  # pragma: no cover — depends on the install
            raise VNAError(
                "capturing from a VNA needs pyserial: pip install 'antennaknobs[vna]'"
            ) from e
        try:
            self._ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        except Exception as e:  # serial.SerialException and OS-level errors
            raise VNAError(f"cannot open {port}: {e}") from e

    def write(self, data: bytes) -> None:
        self._ser.write(data)

    def read_until(self, expected: bytes) -> bytes:
        """Read through ``expected``, or return what arrived before the timeout."""
        return self._ser.read_until(expected)

    def close(self) -> None:
        self._ser.close()


def list_candidate_ports() -> list[tuple[str, str]]:
    """``(device, description)`` for every port that looks like a NanoVNA.

    Returns an empty list when pyserial is missing, so the "no device" path
    reads the same whether the cause is no hardware or no driver package —
    :func:`capture` reports which.
    """
    try:
        from serial.tools import list_ports  # noqa: PLC0415 — optional extra
    except ImportError:
        return []
    out = []
    for p in list_ports.comports():
        ids = (p.vid, p.pid)
        if ids in NANOVNA_USB_IDS or "nanovna" in (p.description or "").lower():
            out.append((p.device, p.description or ""))
    return out


@dataclass
class NanoVNADriver:
    """NanoVNA over its USB serial console.

    The firmware family has two dialects and this speaks both, because which
    one a given device answers to depends on its build, not its label:

    ``scan <start> <stop> <points> <mask>``
        The modern one (NanoVNA-H, the protocol NanoVNA-Saver drives). Mask 3
        selects frequency + S11, so each output line is ``freq re im`` — the
        frequency axis comes from the instrument rather than being assumed.

    ``sweep <start> <stop> <points>`` then ``data 0``
        The original firmware. ``data 0`` emits ``re im`` per point with no
        frequencies, so the axis is reconstructed from the requested span —
        correct only because the device just accepted that exact span.

    Older firmware also caps a sweep at 101 points. Whatever comes back is
    returned as-is; a short sweep is reported, not padded.
    """

    transport: object
    name: str = "nanovna"

    def _command(self, text: str) -> str:
        """Send one command, return its output with echo and prompt stripped."""
        self.transport.write((text + "\r\n").encode())
        raw = self.transport.read_until(_PROMPT).decode("ascii", errors="replace")
        body = raw.split(_PROMPT.decode())[0]
        lines = body.replace("\r", "").split("\n")
        # The console echoes the command it just received; drop that and any
        # blank padding around the payload.
        if lines and lines[0].strip() == text.strip():
            lines = lines[1:]
        return "\n".join(line for line in lines if line.strip())

    @staticmethod
    def _numbers(out: str, width: int) -> list[list[float]]:
        rows = []
        for line in out.split("\n"):
            parts = line.split()
            if len(parts) != width:
                continue
            try:
                rows.append([float(p) for p in parts])
            except ValueError:
                continue
        return rows

    def sweep(self, start_hz, stop_hz, points):
        start, stop = int(round(start_hz)), int(round(stop_hz))
        out = self._command(f"scan {start} {stop} {points} 3")
        rows = self._numbers(out, 3)
        if rows:
            a = np.array(rows, dtype=float)
            return a[:, 0], a[:, 1] + 1j * a[:, 2]

        # Older firmware: set the sweep, then read the S11 table back.
        logger.info("device did not answer `scan`; falling back to `sweep`/`data 0`")
        self._command(f"sweep {start} {stop} {points}")
        rows = self._numbers(self._command("data 0"), 2)
        if not rows:
            raise VNAError(
                "the device answered neither `scan` nor `data 0` with sweep data — "
                "is this a NanoVNA, and is another program (NanoVNA-Saver, a "
                "serial monitor) holding the port?"
            )
        a = np.array(rows, dtype=float)
        # No frequency axis in this dialect; the device just accepted this span,
        # so reconstruct it linearly across however many points came back.
        freqs = np.linspace(start, stop, a.shape[0])
        return freqs, a[:, 0] + 1j * a[:, 1]


#: CLI driver names → factories taking a transport. Add an analyzer here and it
#: is immediately available as ``capture --driver <name>``.
DRIVERS = {"nanovna": NanoVNADriver}


def capture(
    start_mhz: float,
    stop_mhz: float,
    *,
    points: int = 101,
    port: str | None = None,
    driver: str = "nanovna",
    transport=None,
    z0: float = 50.0,
    label: str | None = None,
):
    """Sweep the attached analyzer and return the result as a `MeasuredTrace`.

    ``port`` names the serial device; omitted, the only NanoVNA-looking port is
    used and an ambiguous or empty result is an error naming what was found.
    ``transport`` injects an already-open link (what the tests use, and the
    escape hatch for a device this module doesn't know how to find).
    """
    from .measured import MeasuredTrace

    if stop_mhz <= start_mhz:
        raise VNAError(f"stop ({stop_mhz} MHz) must be above start ({start_mhz} MHz)")
    if points < 2:
        raise VNAError("a sweep needs at least 2 points")
    if driver not in DRIVERS:
        raise VNAError(
            f"unknown VNA driver {driver!r}; available: {', '.join(sorted(DRIVERS))}"
        )

    owned = transport is None
    if owned:
        transport = SerialTransport(port or _sole_port())
    try:
        dev = DRIVERS[driver](transport)
        freqs_hz, s11 = dev.sweep(start_mhz * 1e6, stop_mhz * 1e6, points)
    finally:
        if owned:
            close = getattr(transport, "close", None)
            if close:
                close()

    freqs_hz = np.asarray(freqs_hz, dtype=float)
    s11 = np.asarray(s11, dtype=complex)
    if freqs_hz.size == 0:
        raise VNAError("the device returned an empty sweep")
    if freqs_hz.size != points:
        logger.info(
            "device returned %d of the %d points requested", freqs_hz.size, points
        )
    order = np.argsort(freqs_hz)
    return MeasuredTrace(
        freqs=freqs_hz[order] / 1e6,
        gamma=s11[order],
        z0=float(z0),
        label=label or f"{driver} {start_mhz:g}-{stop_mhz:g} MHz",
    )


def _sole_port() -> str:
    """The one attached analyzer, or an error that says what to do next."""
    found = list_candidate_ports()
    if not found:
        raise VNAError(
            "no VNA found. Check that the analyzer is plugged in and powered, that "
            "you can read its serial port (on Linux, membership of the `dialout` "
            "group), and that pyserial is installed "
            "(pip install 'antennaknobs[vna]'). Pass --port to name the device "
            "explicitly."
        )
    if len(found) > 1:
        listing = ", ".join(f"{d} ({desc})" for d, desc in found)
        raise VNAError(f"several analyzers found — name one with --port: {listing}")
    return found[0][0]
