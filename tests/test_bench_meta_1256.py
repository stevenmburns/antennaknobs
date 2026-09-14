"""The bench's ``_meta`` records the builds it measured, and refuses a wrong nec2c (#1256).

The 2026-09-07 wild-corpus sweep found 272 regressions against a July baseline
whose ``_meta`` named the nec2c reference to the md5 and the engines under test
not at all, so attributing them meant inferring a momwire version from a date.
The same run started on the wrong nec2c binary and threw away 154 rows: the md5
was printed and never compared.

Two traps shape these tests:

- **Installed metadata is not the version that ran.** An editable install's
  egg-info goes stale, and on a developer box today it reads antennaknobs
  0.69.0 and momwire 0.51.0 against 0.77.0 and 0.55.0. So the version is read
  from the source tree the module was imported from, and the tests make the
  metadata lie to prove that.
- **No solve may start before the reference check.** The main-level tests use
  a stub nec2c whose md5 is not the pinned one, and replace ``bench_deck``, so
  a check that ran too late would show up as a recorded call.
"""

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bench_nec_corpus as bench

REPO = Path(__file__).resolve().parents[1]


def _imported_from(module_name, tree):
    import importlib.util

    spec = importlib.util.find_spec(module_name)
    return spec is not None and Path(spec.origin).resolve().is_relative_to(
        tree.resolve()
    )


def _lying_metadata(monkeypatch, dist_name, fake):
    real = importlib.metadata.version
    monkeypatch.setattr(
        importlib.metadata,
        "version",
        lambda name: fake if name == dist_name else real(name),
    )


# --- package_fingerprint -----------------------------------------------------


@pytest.mark.skipif(
    not _imported_from("antennaknobs", REPO / "src"),
    reason="antennaknobs is not imported from this checkout's source tree",
)
def test_the_version_is_the_source_trees_even_when_the_metadata_lies(monkeypatch):
    declared = tomllib.loads((REPO / "pyproject.toml").read_text())["project"][
        "version"
    ]
    _lying_metadata(monkeypatch, "antennaknobs", "0.0.1")

    fp = bench.package_fingerprint("antennaknobs", "antennaknobs")

    assert fp["version"] == declared
    assert fp["version_from"] == "pyproject"
    assert fp["metadata_version"] == "0.0.1"
    assert "installed metadata says 0.0.1" in bench.describe_fingerprint(
        "antennaknobs", fp
    )


@pytest.mark.skipif(
    not (REPO / ".git").exists() or not _imported_from("antennaknobs", REPO / "src"),
    reason="needs this checkout as a git work tree",
)
def test_a_source_tree_records_its_head_and_a_dirty_flag():
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    git = bench.package_fingerprint("antennaknobs", "antennaknobs")["git"]

    assert git["sha"] == head
    assert isinstance(git["dirty"], bool)


@pytest.mark.skipif(
    not _imported_from("momwire", REPO / "momwire"),
    reason="momwire is not imported from the submodule",
)
def test_momwire_is_read_from_the_submodule_with_its_accelerator():
    declared = tomllib.loads((REPO / "momwire" / "pyproject.toml").read_text())
    import momwire

    fp = bench.engine_fingerprints(["bs2"])["momwire"]

    assert fp["version"] == declared["project"]["version"]
    assert fp["version_from"] == "pyproject"
    assert fp["accelerated"] is bool(momwire.accelerated)
    assert fp["accelerator_variant"] == momwire.accelerator_variant


def test_an_installed_package_under_another_projects_pyproject_uses_metadata(
    tmp_path, monkeypatch
):
    """A venv inside some other project's checkout: the nearest pyproject.toml
    names a different project, so it must not be read as this package's."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "someone-else"\nversion = "9.9.9"\n'
    )
    site = tmp_path / "venv" / "site-packages"
    (site / "fakepkg_1256").mkdir(parents=True)
    (site / "fakepkg_1256" / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(site))
    _lying_metadata(monkeypatch, "fakepkg-1256", "1.2.3")

    fp = bench.package_fingerprint("fakepkg_1256", "fakepkg-1256")

    assert fp["version"] == "1.2.3"
    assert fp["version_from"] == "metadata"
    assert fp["git"] is None


def test_a_source_tree_that_is_not_a_repo_top_level_claims_no_git(
    tmp_path, monkeypatch
):
    """The tree declares the package (name normalised: _ and - agree), but it is
    vendored inside another repo, so that repo's HEAD is not its identity."""
    outer = tmp_path / "outer"
    tree = outer / "vendored"
    (tree / "src" / "fakepkg_1256b").mkdir(parents=True)
    (tree / "src" / "fakepkg_1256b" / "__init__.py").write_text("")
    (tree / "pyproject.toml").write_text(
        '[project]\nname = "fakepkg_1256b"\nversion = "4.5.6"\n'
    )
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    monkeypatch.syspath_prepend(str(tree / "src"))

    fp = bench.package_fingerprint("fakepkg_1256b", "fakepkg-1256b")

    assert fp["version"] == "4.5.6"
    assert fp["version_from"] == "pyproject"
    assert fp["metadata_version"] is None
    assert fp["git"] is None


def test_a_package_that_is_not_importable_is_none():
    assert bench.package_fingerprint("no_such_module_1256", "no-such-dist-1256") is None


def test_the_optional_lanes_appear_only_when_they_run(tmp_path):
    exe = tmp_path / "nec5cl"
    exe.write_bytes(b"not really nec5")

    bare = bench.engine_fingerprints(["bs2"])
    full = bench.engine_fingerprints(["pynec", "bs2", "nec5"], nec5_exe=str(exe))

    assert set(bare) == {"antennaknobs", "momwire"}
    assert set(full) == {"antennaknobs", "momwire", "pynec-accel", "nec5"}
    assert full["nec5"] == {
        "path": str(exe),
        "md5": hashlib.md5(b"not really nec5").hexdigest(),
    }


# --- nec2c check and drift ---------------------------------------------------


def test_the_nec2c_check_passes_the_reference_and_names_both_hashes_otherwise():
    ours = {
        "path": "/usr/bin/nec2c",
        "version": "nec2c 1.3.1",
        "md5": bench.PINNED_NEC2C_MD5,
    }
    jammy = dict(ours, version="nec2c 1.3", md5="989ece20053ba73535a739172452c1f2")

    assert bench.nec2c_refusal(ours, bench.PINNED_NEC2C_MD5) is None
    assert bench.nec2c_refusal(jammy, None) is None  # --nec2c-md5 any
    msg = bench.nec2c_refusal(jammy, bench.PINNED_NEC2C_MD5)
    assert jammy["md5"] in msg
    assert bench.PINNED_NEC2C_MD5 in msg
    assert "--nec2c-md5" in msg


def test_drift_names_each_changed_field_and_an_unrecorded_file():
    old = {"momwire": {"version": "0.54.0", "git": {"sha": "a", "dirty": False}}}
    new = {
        "momwire": {"version": "0.55.0", "git": {"sha": "b", "dirty": False}},
        "pynec-accel": {"version": "1.7.6", "git": None},
    }

    notes = bench.fingerprint_drift(old, new)

    assert any(n.startswith("momwire version") for n in notes)
    assert any(n.startswith("momwire git") for n in notes)
    assert any(n.startswith("pynec-accel") for n in notes)
    assert bench.fingerprint_drift(new, new) == []
    assert "predates" in bench.fingerprint_drift(None, new)[0]


# --- main(): the check comes before any solve --------------------------------

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="the stub nec2c is a shell script"
)


@pytest.fixture
def stub_nec2c(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "nec2c"
    exe.write_text('#!/bin/sh\necho "nec2c 1.3.1"\n')
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    return hashlib.md5(exe.read_bytes()).hexdigest()


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "dipole.nec").write_text(
        "GW 1 11 0 0 -0.25 0 0 0.25 0.001\nGE 0\nEX 0 1 6 0 1 0\nFR 0 1 0 0 299.8 0\nEN\n"
    )
    return d


@pytest.fixture
def solves(monkeypatch):
    """Records every deck the sweep would have solved, and solves none."""
    calls = []

    def fake_bench_deck(deck, *args, rel_name, **kwargs):
        calls.append(rel_name)
        return {"deck": rel_name}

    monkeypatch.setattr(bench, "bench_deck", fake_bench_deck)
    monkeypatch.setattr(bench, "print_report", lambda rows, engines: None)
    return calls


def _run(corpus, out, *extra):
    bench.main(["--corpus", str(corpus), "--engines", "bs2", "--out", str(out), *extra])


@posix_only
def test_a_sweep_refuses_the_wrong_nec2c_before_any_solve(
    stub_nec2c, corpus, solves, tmp_path
):
    assert stub_nec2c != bench.PINNED_NEC2C_MD5
    out = tmp_path / "run.jsonl"

    with pytest.raises(SystemExit) as exc:
        _run(corpus, out)

    assert stub_nec2c in str(exc.value)
    assert bench.PINNED_NEC2C_MD5 in str(exc.value)
    assert solves == []
    assert not out.exists()


@posix_only
def test_the_meta_line_records_the_builds_and_the_checked_reference(
    stub_nec2c, corpus, solves, tmp_path
):
    out = tmp_path / "run.jsonl"

    _run(corpus, out, "--nec2c-md5", stub_nec2c.upper())

    meta = json.loads(out.read_text().splitlines()[0])["_meta"]
    assert meta["nec2c"]["md5"] == stub_nec2c
    assert meta["nec2c"]["md5_expected"] == stub_nec2c
    assert set(meta["packages"]) == {"antennaknobs", "momwire"}
    assert meta["packages"]["momwire"]["version"]
    assert solves == ["dipole.nec"]


@posix_only
def test_any_records_the_binary_without_checking_it(
    stub_nec2c, corpus, solves, tmp_path
):
    out = tmp_path / "run.jsonl"

    _run(corpus, out, "--nec2c-md5", "any")

    meta = json.loads(out.read_text().splitlines()[0])["_meta"]
    assert meta["nec2c"]["md5"] == stub_nec2c
    assert meta["nec2c"]["md5_expected"] is None


def test_a_malformed_md5_is_an_argument_error(corpus, tmp_path):
    with pytest.raises(SystemExit) as exc:
        _run(corpus, tmp_path / "run.jsonl", "--nec2c-md5", "050927")
    assert exc.value.code == 2


@posix_only
def test_a_resume_refuses_a_file_scored_against_another_nec2c(
    stub_nec2c, corpus, solves, tmp_path
):
    out = tmp_path / "run.jsonl"
    other = "0" * 32
    out.write_text(json.dumps({"_meta": {"nec2c": {"md5": other}}}) + "\n")

    with pytest.raises(SystemExit) as exc:
        _run(corpus, out, "--nec2c-md5", stub_nec2c)

    assert other in str(exc.value)
    assert stub_nec2c in str(exc.value)
    assert solves == []


@posix_only
def test_a_resume_on_other_builds_warns_and_continues(
    stub_nec2c, corpus, solves, tmp_path, capsys
):
    out = tmp_path / "run.jsonl"
    old_packages = {
        "antennaknobs": {"version": "0.0.1"},
        "momwire": {"version": "0.0.1"},
    }
    out.write_text(
        json.dumps({"_meta": {"nec2c": {"md5": stub_nec2c}, "packages": old_packages}})
        + "\n"
    )

    _run(corpus, out, "--nec2c-md5", stub_nec2c)

    printed = capsys.readouterr().out
    assert "resume WARNING: momwire version: '0.0.1' then" in printed
    assert solves == ["dipole.nec"]
