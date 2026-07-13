"""Content-pinned trust gate for user designs (antennaknobs.design_trust).

The model: nothing in the user namespace executes until the user trusts it,
trust is keyed on the file's *contents* (so a new or silently-changed file
re-prompts), and there are two modes — ``pinned`` (this version) and ``always``
(this file + future edits, for a design you author). These tests pin the gate
behavior, the store, and the trust/untrust CLI.
"""

import pytest

import antennaknobs as ant
from antennaknobs import design_trust as dt
from antennaknobs import user_designs
from antennaknobs.design_trust import DesignNotTrustedError

CLEAN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0})

    def build_wires(self):
        return [((0, -5, 0), (0, 5, 0), 1, 1 + 0j)]
"""

EVIL = CLEAN.replace(
    "from antennaknobs import AntennaBuilder",
    "from antennaknobs import AntennaBuilder\nimport socket",
)


@pytest.fixture
def userdir(tmp_path, monkeypatch):
    """A temp user dir with the trust gate ACTIVE (blanket-trust off), and an
    isolated trust store inside it."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", raising=False)
    monkeypatch.delenv("ANTENNAKNOBS_TRUST_FILE", raising=False)
    return tmp_path


# --- the gate ---------------------------------------------------------------


def test_untrusted_design_does_not_run(userdir):
    (userdir / "d.py").write_text(CLEAN)
    with pytest.raises(DesignNotTrustedError) as ei:
        user_designs.resolve_user_design("d")
    # Guidance points at the trust command, not a raw traceback.
    assert "trust" in str(ei.value)


def test_untrusted_error_carries_advisory(userdir):
    (userdir / "d.py").write_text(EVIL)
    with pytest.raises(DesignNotTrustedError) as ei:
        user_designs.resolve_user_design("d")
    assert any("socket" in f.message for f in ei.value.report.findings)


def test_pinned_trust_lets_it_run(userdir):
    p = userdir / "d.py"
    p.write_text(CLEAN)
    dt.trust(p)  # pinned by default
    cls = user_designs.resolve_user_design("d")
    assert cls is not None and cls.__name__ == "Builder"


def test_new_file_is_a_fresh_decision(userdir):
    # Trusting one design must NOT bless a different file dropped in later —
    # this is the whole reason trust is per-file, not per-folder.
    (userdir / "a.py").write_text(CLEAN)
    dt.trust(userdir / "a.py")
    (userdir / "b.py").write_text(CLEAN)  # arrives afterward
    assert user_designs.resolve_user_design("a") is not None
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("b")


def test_pinned_reprompts_after_edit(userdir):
    p = userdir / "d.py"
    p.write_text(CLEAN)
    dt.trust(p)
    assert user_designs.resolve_user_design("d") is not None
    # A silent rewrite (or the author's own edit) changes the hash → re-gated.
    p.write_text(CLEAN + "# changed\n")
    assert dt.trust_status(p) == "stale"
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("d")


def test_always_trust_survives_edits(userdir):
    p = userdir / "mine.py"
    p.write_text(CLEAN)
    dt.trust(p, mode="always")
    p.write_text(CLEAN + "# edit 1\n")
    assert user_designs.resolve_user_design("mine") is not None
    p.write_text(CLEAN + "# edit 2\n")
    assert user_designs.resolve_user_design("mine") is not None
    assert dt.trust_status(p) == "always"


def test_per_call_trust_bypasses_gate(userdir):
    p = userdir / "d.py"
    p.write_text(EVIL)
    with pytest.raises(DesignNotTrustedError):
        user_designs.load_builder(p)
    assert user_designs.load_builder(p, trust=True).__name__ == "Builder"


def test_env_blanket_trust_bypasses_gate(userdir, monkeypatch):
    (userdir / "d.py").write_text(EVIL)
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("d")
    monkeypatch.setenv("ANTENNAKNOBS_TRUST_USER_DESIGNS", "1")
    assert user_designs.resolve_user_design("d") is not None


# --- the store ---------------------------------------------------------------


def test_untrust_revokes(userdir):
    p = userdir / "d.py"
    p.write_text(CLEAN)
    dt.trust(p)
    assert user_designs.resolve_user_design("d") is not None
    assert dt.untrust(p) is True
    assert dt.trust_status(p) == "none"
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("d")


def test_untrust_missing_returns_false(userdir):
    (userdir / "d.py").write_text(CLEAN)
    assert dt.untrust(userdir / "d.py") is False


def test_corrupt_store_is_ignored(userdir):
    dt.store_path().write_text("{ not valid json")
    (userdir / "d.py").write_text(CLEAN)
    # A garbage store must not crash — it just means nothing is trusted yet.
    assert dt.trust_status(userdir / "d.py") == "none"
    with pytest.raises(DesignNotTrustedError):
        user_designs.resolve_user_design("d")


def test_bad_mode_rejected(userdir):
    (userdir / "d.py").write_text(CLEAN)
    with pytest.raises(ValueError):
        dt.trust(userdir / "d.py", mode="sometimes")


# --- trust / untrust CLI -----------------------------------------------------


def test_cli_trust_then_load(userdir, capsys):
    (userdir / "d.py").write_text(EVIL)
    ant.cli(["trust", "user.d"])
    out = capsys.readouterr().out
    assert "socket" in out  # advisory shown before trusting
    assert "trusted d.py" in out
    assert user_designs.resolve_user_design("d") is not None


def test_cli_trust_edits_mode(userdir):
    p = userdir / "mine.py"
    p.write_text(CLEAN)
    ant.cli(["trust", "mine", "--edits"])
    assert dt.trust_status(p) == "always"


def test_cli_untrust(userdir, capsys):
    p = userdir / "d.py"
    p.write_text(CLEAN)
    dt.trust(p)
    ant.cli(["untrust", "d"])
    assert "untrusted d.py" in capsys.readouterr().out
    assert dt.trust_status(p) == "none"


def test_cli_trust_unknown_design_exits_two(userdir):
    with pytest.raises(SystemExit) as ei:
        ant.cli(["trust", "does_not_exist"])
    assert ei.value.code == 2


def test_cli_draw_untrusted_shows_guidance(userdir, capsys):
    (userdir / "d.py").write_text(CLEAN)
    with pytest.raises(SystemExit) as ei:
        ant.cli(["draw", "--builder", "user.d", "--fn", "/dev/null"])
    assert ei.value.code == 1
    assert "trust" in capsys.readouterr().out
