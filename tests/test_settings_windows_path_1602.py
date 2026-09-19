"""A Windows engine path in DOUBLE quotes is a TOML error (AK#1602).

Reported by Dan AC6LA (QRZ 1003328). The natural thing on Windows — paste the
path from Explorer between double quotes — does not work, because TOML reads a
backslash in a BASIC string as the start of an escape and `\\E`, `\\D`, `\\4`
are not valid ones. TOML's LITERAL string (single quotes) takes the path
exactly as given.

Two things made that expensive to diagnose rather than merely annoying:

- a parse failure rejects the WHOLE file, so the symptom is every engine AND
  the capture dir vanishing at once, which reads as "the exe is missing";
- the raw decode message names a line and column but never connects
  "unescaped backslash" to "the path you just pasted".
"""

import pathlib

import pytest

from antennaknobs import settings_file

WIN = "C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """A settings file at a path we control, with the module cache cleared so
    each body is actually re-read (the cache keys on mtime/size, which a test
    writing twice in the same tick can collide on)."""
    path = tmp_path / "settings.toml"
    monkeypatch.setenv(settings_file.SETTINGS_ENV, str(path))

    def write(body):
        path.write_text(body, encoding="utf-8")
        settings_file._cache.update(key=None, data=None, error=None)
        return settings_file.read_settings()

    yield write
    settings_file._cache.update(key=None, data=None, error=None)


def test_single_quotes_take_the_path_exactly_as_explorer_gives_it(settings):
    """The documented form, and the point of the issue: no doubling."""
    data, error = settings(f"[engines]\nnec5_exe = '{WIN}'\n")
    assert error is None
    assert data["engines"]["nec5_exe"] == WIN


def test_double_quotes_fail_and_the_message_says_what_to_do(settings):
    data, error = settings(f'[engines]\nnec5_exe = "{WIN}"\n')
    assert data is None
    assert "not valid TOML" in error
    # The fix, not just the diagnosis.
    assert "SINGLE quotes" in error
    assert "'C:\\EZNEC 7.0\\Docs\\NEC5CL_x13.exe'" in error


def test_the_hint_does_not_fire_on_an_unrelated_toml_error(settings):
    """The hint is a guess about CAUSE, so it must stay quiet when the cause is
    something else — otherwise it is noise on every malformed file."""
    data, error = settings("[engines\nnec5_exe = 1\n")
    assert data is None
    assert "not valid TOML" in error
    assert "SINGLE quotes" not in error


def test_a_doubled_backslash_double_quoted_path_still_works(settings):
    """The other correct spelling. It was the documented one before AK#1602
    and must keep working — the issue is that nobody types it."""
    doubled = WIN.replace("\\", "\\\\")
    data, error = settings(f'[engines]\nnec5_exe = "{doubled}"\n')
    assert error is None
    assert data["engines"]["nec5_exe"] == WIN


def test_the_hint_is_keyed_on_the_text_not_the_exception_wording(settings):
    """`tomllib`'s message is a CPython implementation detail. Keying the hint
    on it would make this quietly stop working at some future Python. Pinned by
    asserting the hint survives when the wording is replaced wholesale."""
    text = f'[engines]\nnec5_exe = "{WIN}"\n'
    msg = settings_file._toml_error(
        pathlib.Path("settings.toml"), text, ValueError("something else entirely")
    )
    assert "SINGLE quotes" in msg


def test_the_documented_example_actually_parses():
    """The module docstring is the only instruction most people get, so the
    block in it is executed rather than trusted."""
    import tomllib

    block = "\n".join(
        ln
        for ln in (settings_file.__doc__ or "").splitlines()
        if "exe =" in ln or "dir =" in ln or ln.strip().startswith("[")
    )
    parsed = tomllib.loads(block)
    assert parsed["engines"]["nec5_exe"] == WIN
    assert "\\\\" not in block  # single-quoted: no doubling in the example
