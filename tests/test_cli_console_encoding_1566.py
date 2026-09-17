"""#1566, Windows canary gate 8: the CLI's tables carry Ω, Δ and Γ, and a
redirected stdout on Windows is cp1252, so `sweep --param nominal_nsegs`
printed its header and died on the first row with UnicodeEncodeError. The
console itself was never the problem (Python writes a Windows console as
UTF-16); pipes and files were. `_tolerant_console` re-encodes a stream that
cannot take the characters: a pipe becomes UTF-8, a terminal keeps its
encoding and prints ? instead of dying."""

from __future__ import annotations

import io
import subprocess
import sys

import importlib

# `antennaknobs.cli` the MODULE: the package re-exports the `cli` function under
# the same name, so `from antennaknobs import cli` would bind that instead.
cli_module = importlib.import_module("antennaknobs.cli")

SAMPLE = "   1     6 1   78.740   +46.009  R (Ω)  |ΔΓ|"


def _cp1252_pipe() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_a_cp1252_pipe_is_re_encoded_to_utf8(monkeypatch):
    out = _cp1252_pipe()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", _cp1252_pipe())
    cli_module._tolerant_console()
    print(SAMPLE)
    sys.stdout.flush()
    raw = sys.stdout.buffer.getvalue()
    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"
    assert raw.decode("utf-8").rstrip("\n") == SAMPLE


def test_a_utf8_stream_is_left_alone(monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    cli_module._tolerant_console()
    assert sys.stdout is out
    assert out.errors == "strict"


def test_the_real_cli_survives_a_cp1252_pipe():
    """End to end through a child interpreter, the way the Windows smoke and
    a PowerShell redirect reach it: PYTHONIOENCODING forces the child's
    stdout to cp1252 and the pipe is not a tty."""
    proc = subprocess.run(
        [sys.executable, "-m", "antennaknobs", "list", "dipole"],
        capture_output=True,
        env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252"},
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-800:]
    assert b"dipole" in proc.stdout
