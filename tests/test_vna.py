"""Live VNA capture (issue #597), tested without a VNA.

The drivers talk to a *transport* — two methods, ``write`` and ``read_until`` —
rather than to pyserial directly, so the console protocol can be exercised
against a scripted device. That covers what actually breaks in the field: a
firmware that speaks the other dialect, a device that answers with junk, a port
that opens but has nothing on the far end.
"""

import numpy as np
import pytest

import antennaknobs as ant
from antennaknobs.touchstone import format_s1p, parse_touchstone
from antennaknobs.vna import (
    DRIVERS,
    Driver,
    NanoVNADriver,
    VNAError,
    capture,
)

PROMPT = b"ch>"


class FakeNanoVNA:
    """A scripted NanoVNA console.

    ``dialect="scan"`` is modern firmware (frequency axis included);
    ``dialect="data"`` is the original (``scan`` unrecognised, ``data 0``
    returns S11 with no frequencies). ``max_points`` models the 101-point cap
    older builds enforce.
    """

    def __init__(
        self, *, dialect="scan", max_points=None, gamma=None, junk=False,
        descending=False,
    ):  # fmt: skip
        self.descending = descending
        self.dialect = dialect
        self.max_points = max_points
        self.gamma = gamma
        self.junk = junk
        self.commands: list[str] = []
        self._pending = b""
        self._span = (1e6, 2e6, 11)

    # -- transport interface ------------------------------------------------
    def write(self, data: bytes) -> None:
        cmd = data.decode().strip()
        self.commands.append(cmd)
        self._pending = (cmd + "\r\n" + self._respond(cmd) + PROMPT.decode()).encode()

    def read_until(self, expected: bytes) -> bytes:
        out, self._pending = self._pending, b""
        return out

    def close(self) -> None:
        self.closed = True

    # -- the scripted device ------------------------------------------------
    def _points(self, start, stop, n):
        n = min(n, self.max_points) if self.max_points else n
        f = np.linspace(start, stop, n)
        if self.gamma is not None:
            g = np.asarray(self.gamma)[:n]
        else:  # a plausible resonance so the numbers aren't all identical
            g = (f / f[-1] - 0.5) + 0.25j
        return f, g

    def _respond(self, cmd: str) -> str:
        if self.junk:
            return "hello there\r\n"
        head = cmd.split()
        if head[0] == "scan":
            if self.dialect != "scan":
                return "usage: scan {start(Hz)} {stop(Hz)} [points] [outmask]\r\n"
            start, stop, n = float(head[1]), float(head[2]), int(head[3])
            f, g = self._points(start, stop, n)
            if self.descending:  # some firmware/segments report high → low
                f, g = f[::-1], g[::-1]
            return "".join(f"{a:.0f} {v.real} {v.imag}\r\n" for a, v in zip(f, g))
        if head[0] == "sweep":
            self._span = (float(head[1]), float(head[2]), int(head[3]))
            return ""
        if head[0] == "data":
            f, g = self._points(*self._span)
            return "".join(f"{v.real} {v.imag}\r\n" for v in g)
        return "?\r\n"


# ---------------------------------------------------------------------------
# the two firmware dialects
# ---------------------------------------------------------------------------
def test_captures_over_the_scan_dialect():
    dev = FakeNanoVNA(dialect="scan")
    trace = capture(14.0, 14.35, points=11, transport=dev)

    assert any(c.startswith("scan ") for c in dev.commands)
    assert trace.freqs.size == 11
    # Hz on the wire, MHz in the trace.
    assert trace.freqs[0] == pytest.approx(14.0)
    assert trace.freqs[-1] == pytest.approx(14.35)
    assert trace.z0 == 50.0


def test_falls_back_to_the_older_sweep_dialect():
    dev = FakeNanoVNA(dialect="data")
    trace = capture(14.0, 14.35, points=11, transport=dev)

    assert dev.commands == [
        "scan 14000000 14350000 11 3",  # tried first...
        "sweep 14000000 14350000 11",  # ...then the old pair
        "data 0",
    ]
    assert trace.freqs.size == 11
    assert trace.freqs[0] == pytest.approx(14.0)


def test_short_sweep_is_reported_not_padded():
    """Older firmware caps at 101 points; return what the device measured."""
    dev = FakeNanoVNA(dialect="scan", max_points=101)
    trace = capture(14.0, 14.35, points=301, transport=dev)
    assert trace.freqs.size == 101


def test_a_device_that_answers_junk_is_an_error_not_a_trace():
    dev = FakeNanoVNA(junk=True)
    with pytest.raises(VNAError, match="neither"):
        capture(14.0, 14.35, points=11, transport=dev)


def test_capture_sorts_by_frequency():
    """A device reporting high→low still yields an ascending trace.

    Everything downstream — align(), the fit grid, np.interp — assumes ascending
    frequencies, so the capture normalises rather than trusting the instrument.
    """
    dev = FakeNanoVNA(dialect="scan", descending=True)
    trace = capture(14.0, 14.35, points=11, transport=dev)
    assert np.all(np.diff(trace.freqs) > 0)
    assert trace.freqs[0] == pytest.approx(14.0)


# ---------------------------------------------------------------------------
# argument validation — none of these should reach the hardware
# ---------------------------------------------------------------------------
def test_rejects_an_inverted_or_degenerate_span():
    dev = FakeNanoVNA()
    with pytest.raises(VNAError, match="must be above"):
        capture(14.0, 14.0, points=11, transport=dev)
    with pytest.raises(VNAError, match="at least 2 points"):
        capture(14.0, 14.35, points=1, transport=dev)
    assert dev.commands == []


def test_unknown_driver_names_the_available_ones():
    with pytest.raises(VNAError, match="nanovna"):
        capture(14.0, 14.35, driver="dg8saq", transport=FakeNanoVNA())


def test_driver_registry_is_the_extension_point():
    """A new analyzer is a registry entry, not a change to capture()."""

    class Fake(NanoVNADriver):
        name = "fake"

        def sweep(self, start_hz, stop_hz, points):
            f = np.linspace(start_hz, stop_hz, points)
            return f, np.full(points, 0.25 + 0j)

    DRIVERS["_test_fake"] = Fake
    try:
        trace = capture(7.0, 7.3, points=5, driver="_test_fake", transport=object())
        assert np.allclose(trace.gamma, 0.25)
    finally:
        del DRIVERS["_test_fake"]


def test_missing_device_message_is_actionable(monkeypatch):
    """The no-hardware path is the one every new user hits first."""
    monkeypatch.setattr("antennaknobs.vna.list_candidate_ports", lambda: [])
    with pytest.raises(VNAError) as exc:
        capture(14.0, 14.35, points=11)
    msg = str(exc.value)
    assert "no VNA found" in msg
    assert "--port" in msg and "dialout" in msg


def test_several_devices_ask_which(monkeypatch):
    monkeypatch.setattr(
        "antennaknobs.vna.list_candidate_ports",
        lambda: [("/dev/ttyACM0", "NanoVNA"), ("/dev/ttyACM1", "NanoVNA-H")],
    )
    with pytest.raises(VNAError, match="--port"):
        capture(14.0, 14.35, points=11)


# ---------------------------------------------------------------------------
# capture → file → overlay, the whole point of the feature
# ---------------------------------------------------------------------------
def test_captured_sweep_round_trips_through_touchstone(tmp_path):
    dev = FakeNanoVNA(dialect="scan")
    trace = capture(28.0, 29.0, points=21, transport=dev)
    p = tmp_path / "bench.s1p"
    p.write_text(format_s1p(trace.freqs * 1e6, trace.gamma, z0=trace.z0))

    ts = parse_touchstone(p.read_text(), nports=1)
    np.testing.assert_allclose(ts.freqs / 1e6, trace.freqs, rtol=1e-9)
    np.testing.assert_allclose(ts.params[:, 0, 0], trace.gamma, atol=1e-9)

    # ...and the file the capture wrote is one the overlay accepts.
    from antennaknobs.measured import read_measured

    again = read_measured(p)
    np.testing.assert_allclose(again.gamma, trace.gamma, atol=1e-9)


def test_format_s1p_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="frequencies"):
        format_s1p(np.array([1e6, 2e6]), np.array([0.1 + 0j]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_cli_capture_writes_a_file(tmp_path, monkeypatch):
    dev = FakeNanoVNA(dialect="scan")
    monkeypatch.setattr("antennaknobs.vna.SerialTransport", lambda *a, **k: dev)
    monkeypatch.setattr(
        "antennaknobs.vna.list_candidate_ports", lambda: [("/dev/fake", "NanoVNA")]
    )
    out = tmp_path / "bench.s1p"
    ant.cli(f"capture --out {out} --start 28 --stop 29 --points 11".split())

    text = out.read_text()
    assert text.startswith("! captured by antennaknobs")
    assert parse_touchstone(text, nports=1).freqs.size == 11


def test_cli_capture_writes_utf8_even_under_a_non_utf8_default(
    tmp_path, monkeypatch, cp1252_default_open
):
    """The Touchstone header comment interpolates ``--driver`` verbatim; a
    driver name outside cp1252 reproduces the Windows failure mode here on
    Linux (issue #772). Real driver-registry dispatch, no live hardware —
    only the transport (SerialTransport) is stubbed, exactly as
    test_cli_capture_writes_a_file does."""

    class Fake(Driver):
        def __init__(self, transport):
            pass

        def sweep(self, start_hz, stop_hz, points):
            f = np.linspace(start_hz, stop_hz, points)
            return f, np.full(points, 0.25 + 0j)

    monkeypatch.setitem(DRIVERS, "fakeΩ", Fake)
    monkeypatch.setattr("antennaknobs.vna.SerialTransport", lambda *a, **k: object())
    out = tmp_path / "bench.s1p"
    ant.cli(
        f"capture --out {out} --start 28 --stop 29 --points 11 "
        "--driver fakeΩ --port /dev/fake".split()
    )

    text = out.read_text(encoding="utf-8")
    assert "fakeΩ" in text


def test_cli_capture_needs_a_span():
    with pytest.raises(SystemExit, match="--start and --stop"):
        ant.cli("capture --out /dev/null".split())


def test_cli_capture_reports_a_missing_device_cleanly(monkeypatch):
    """No hardware is a message and a non-zero exit, never a traceback."""
    monkeypatch.setattr("antennaknobs.vna.list_candidate_ports", lambda: [])
    with pytest.raises(SystemExit, match="no VNA found"):
        ant.cli("capture --start 28 --stop 29".split())


def test_cli_capture_list_is_quiet_with_no_hardware(monkeypatch, capsys):
    monkeypatch.setattr("antennaknobs.vna.list_candidate_ports", lambda: [])
    ant.cli("capture --list".split())
    assert "no analyzer found" in capsys.readouterr().out


def test_web_server_exposes_no_capture_route():
    """Hardware access must stay CLI-local: the server has no serial capability.

    A remote backend's serial ports are not the operator's, and on the hosted
    instance they are not anyone's business. The capture path is deliberately
    unreachable from the web app.
    """
    from antennaknobs.web import server

    paths = {getattr(r, "path", "") for r in server.app.routes}
    assert not any("capture" in p or "vna" in p for p in paths)
