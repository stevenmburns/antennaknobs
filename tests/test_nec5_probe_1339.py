"""`$NEC5_EXE` must name a working NEC-5, not merely an executable — #1339.

`find_nec5` answered "is there an executable file there", which is a question
about the filesystem rather than about NEC-5. Measured on the Windows box
2026-09-09: the variable pointed at an 18 KB C# spy shim, `have_nec5()` said
yes, the app showed a NEC-5 tab, and the failure arrived at the first solve as
the shim's own error text. Any wrong file does that — the EZNEC GUI exe, a copy
in the wrong folder.

`probe_nec5` runs a one-wire deck through the engine's own protocol and
requires a parsable printout, so a wrong binary is ABSENT from the roster with
a logged sentence naming the file.

WHY THE PROBE DECK CARRIES `XQ 0`, and why this module pins it. The first draft
of that deck ended at `EN`, was syntactically fine, and made the probe reject
the REAL binary: NEC-5 read every card, echoed them, printed `RUN TIME = 0.000`
and exited having solved nothing. A probe built on it would have removed a
working NEC-5 tab from the roster — worse than the bug #1339 describes, and
convincing, because the log named the file and quoted a genuine NEC-5 banner.
The deck's shape is taken from `tests/fixtures/nec5/*.nec`, which is what the
engine itself emits.

These tests never need the real binary: the fakes are the interesting half, and
the real-binary case is covered by a test that skips without one.
"""

from __future__ import annotations

import os
import stat
import textwrap

import pytest

from antennaknobs.engines import nec5 as nec5_mod
from antennaknobs.engines.nec5 import find_nec5, probe_nec5


@pytest.fixture(autouse=True)
def _clear_cache():
    nec5_mod._PROBE_CACHE.clear()
    yield
    nec5_mod._PROBE_CACHE.clear()


def _fake(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(textwrap.dedent(body))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


def test_a_silent_executable_is_refused(tmp_path, caplog):
    """The shape of the bug: something that runs, exits 0 and writes nothing.
    `find_nec5` accepts it because it is an executable file."""
    fake = _fake(tmp_path, "nec5cl", "#!/bin/sh\nexit 0\n")
    assert find_nec5(str(fake)) == str(fake), "the old check accepts it"
    with caplog.at_level("WARNING"):
        assert probe_nec5(str(fake)) is None
    assert str(fake) in caplog.text, "the log must name the actual file"


def test_the_spy_shim_shape_is_refused(tmp_path, caplog):
    """What was actually on the Windows box: a shim that prints its own error
    and exits non-zero. Its message must reach the log, since that is what
    tells the user which file to fix."""
    spy = _fake(
        tmp_path,
        "NEC5CL_x13.exe",
        "#!/bin/sh\necho 'cannot locate the real engine' >&2\nexit 1\n",
    )
    with caplog.at_level("WARNING"):
        assert probe_nec5(str(spy)) is None
    assert "NEC5CL_x13.exe" in caplog.text


def test_a_binary_that_writes_an_unparsable_printout_is_refused(tmp_path, caplog):
    """Produces the output FILE but not a solve. Exit codes are not trusted
    here (Fortran STOP), so the printout's content is the only signal."""
    liar = _fake(
        tmp_path,
        "nec5cl",
        """\
        #!/bin/sh
        read inp; read out
        echo 'NUMERICAL ELECTROMAGNETICS CODE (NEC-5)' > "$out"
        echo 'RUN TIME = 0.000' >> "$out"
        exit 0
        """,
    )
    with caplog.at_level("WARNING"):
        assert probe_nec5(str(liar)) is None
    assert "ANTENNA INPUT PARAMETERS" in caplog.text, (
        "the reason should say what was missing, not just that it failed"
    )


def test_an_unset_variable_is_absence_not_failure(monkeypatch, caplog):
    monkeypatch.delenv("NEC5_EXE", raising=False)
    with caplog.at_level("WARNING"):
        assert probe_nec5() is None
    assert caplog.text == "", "nothing configured is not an error to log"


def test_the_verdict_is_cached_per_file_identity(tmp_path):
    """The probe costs a process launch and `have_nec5()` runs per request."""
    fake = _fake(tmp_path, "nec5cl", "#!/bin/sh\nexit 0\n")
    assert probe_nec5(str(fake)) is None
    assert str(fake) in nec5_mod._PROBE_CACHE
    # Replacing the file in place must re-probe: the key is (mtime, size).
    before = nec5_mod._PROBE_CACHE[str(fake)][:2]
    os.utime(fake, (0, 0))
    assert nec5_mod._PROBE_CACHE[str(fake)][:2] == before
    assert probe_nec5(str(fake)) is None  # re-probed, same verdict
    assert nec5_mod._PROBE_CACHE[str(fake)][:2] != before, (
        "a file replaced in place must not keep its old verdict"
    )


def test_the_probe_deck_executes_rather_than_only_parsing():
    """`XQ 0` is load-bearing. Without it NEC-5 reads every card and solves
    nothing, and the probe rejects the genuine binary — measured while writing
    this. Pinned so a tidy-up cannot drop it."""
    assert "XQ 0" in nec5_mod._PROBE_DECK
    assert nec5_mod._PROBE_DECK.rstrip().endswith("EN")


@pytest.mark.skipif(
    find_nec5() is None, reason="no licensed NEC-5 binary configured on this machine"
)
def test_a_real_nec5_binary_passes():
    """The half that matters most: the probe must not reject a working engine."""
    assert probe_nec5() == find_nec5()
