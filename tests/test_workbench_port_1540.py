"""The packaged workbench serves on a fixed port by default (AK#1540).

What the browser remembers about the workbench — the view rail's pins, the
stage layout, the theme — is kept in ``localStorage``, which every browser keys
to the ORIGIN, and the origin of a loopback server is ``http://127.0.0.1:<port>``.
The launcher used to take an ephemeral port on every start, so every cold start
opened a browser at an origin that had never been visited: a rail set up one
evening was gone the next, and no file on disk showed anything missing.

So the default is a fixed port, and a free one only when that is busy — in
which case the launcher says so, because that window does start with the
defaults.
"""

import socket
import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "scripts" / "freeze_workbench")
)
import entry


def _busy_socket():
    """A bound, listening loopback socket, and the port it holds."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    return s, int(s.getsockname()[1])


def _known_free_port() -> int:
    """A port bound only long enough to learn its number, then released."""
    with _busy_socket()[0] as s:
        return int(s.getsockname()[1])


def test_the_default_port_does_not_move_between_launches(monkeypatch):
    """The regression: with an ephemeral port, launch two is a new origin and
    an empty localStorage. The default stands in for 8000, which a machine
    running this suite may well have something on."""
    monkeypatch.setattr(entry, "DEFAULT_PORT", _known_free_port())
    assert {entry.choose_port(None)[0] for _ in range(5)} == {entry.DEFAULT_PORT}


def test_a_free_default_port_is_taken_as_is(monkeypatch):
    free = _known_free_port()
    monkeypatch.setattr(entry, "DEFAULT_PORT", free)
    assert entry.choose_port(None) == (free, False)


def test_a_busy_default_port_falls_back_to_a_free_one(monkeypatch):
    s, busy = _busy_socket()
    with s:
        monkeypatch.setattr(entry, "DEFAULT_PORT", busy)
        port, moved = entry.choose_port(None)
        assert moved
        assert port != busy
        # Whatever it moved to has to be bindable, or the launch fails.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))


def test_an_explicit_port_wins_even_over_a_busy_one(monkeypatch):
    """``--port`` is an instruction, not a preference: a busy port is the
    user's problem to see (uvicorn says so), not ours to silently route
    around — that would put them on an origin they did not ask for."""
    s, busy = _busy_socket()
    with s:
        assert entry.choose_port(busy) == (busy, False)


def test_the_notice_names_the_port_and_what_is_kept_per_port():
    assert entry.port_notice(entry.DEFAULT_PORT, moved=False) is None
    note = entry.port_notice(12345, moved=True)
    assert note is not None
    assert str(entry.DEFAULT_PORT) in note
    # The point of the notice: why the window looks new.
    assert "rail" in note
    assert f"--port {entry.DEFAULT_PORT}" in note


def test_the_default_port_is_the_one_the_pip_install_serves_on():
    """One origin for the workbench however it was started, so the browser's
    memory of it carries across. Pinned so a change is deliberate: moving it
    resets every user's rail once."""
    assert entry.DEFAULT_PORT == 8000
