"""The corpus bench's nec5 lane (#872 phase 0): engine roster, dialect
scoping (designed refusals count as out-of-scope, not failures), and the
worker-level tagging that carries the classification into the census JSON.

None of these tests need the licensed binary: scope refusals fire at
NEC5Engine construction, before any subprocess."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from bench_nec_corpus import (
    DEFAULT_ENGINE_KEYS,
    ENGINE_KEYS,
    ENGINE_LABEL,
    engine_error_kind,
    fmt_dg,
    nec5_out_of_scope,
    worker_main,
)


def test_nec5_is_dispatchable_but_not_default():
    # Same treatment as "sing": silently adding a column to every historical
    # sweep would change what those runs cost and mean — ask for it.
    assert "nec5" in ENGINE_KEYS
    assert "nec5" not in DEFAULT_ENGINE_KEYS
    assert ENGINE_LABEL["nec5"] == "NEC-5"


def test_scope_classification():
    # NotImplementedError is the engine's designed refusal channel.
    assert nec5_out_of_scope(NotImplementedError("no TL on this path"))
    # The two hard NEC-5 dialect rules enforced as ValueError at construction.
    assert nec5_out_of_scope(
        ValueError("wire 3 lies in the ground plane (z=0), which ...")
    )
    assert nec5_out_of_scope(
        ValueError(
            "eps_r=1.0 is too close to free space for NEC-5's Sommerfeld "
            "tables (degenerate limit); ..."
        )
    )
    # Anything else is a real failure.
    assert not nec5_out_of_scope(ValueError("design has no excitation"))
    assert not nec5_out_of_scope(RuntimeError("NEC-5 timed out after 120s"))


def test_error_kind_and_report_cell():
    res = {"error": "NotImplementedError: ...", "out_of_scope": True}
    assert engine_error_kind(res) == "scope"
    assert fmt_dg(res) == "OOS"
    # out_of_scope wins over the error-message regexes (a refusal mentioning
    # "memory" or "timeout" in prose must still count as scope).
    res = {"error": "NotImplementedError: timeout memory", "out_of_scope": True}
    assert engine_error_kind(res) == "scope"
    # And plain errors are untouched.
    assert engine_error_kind({"error": "NEC5Error: boom"}) == "err"


def _run_worker(capsys, deck_text, tmp_path, ground="free"):
    deck = tmp_path / "deck.nec"
    deck.write_text(deck_text)
    worker_main("nec5", str(deck), 28.5, json.dumps(ground))
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_worker_tags_tl_deck_out_of_scope(capsys, monkeypatch, tmp_path):
    """A TL deck refuses at NEC5Engine construction (stage-1 dialect) and
    the worker tags the row out_of_scope — the census counts it OOS, not
    as an engine failure. NEC5_EXE is python: never invoked, any
    executable satisfies the constructor's gate."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    res = _run_worker(
        capsys,
        "CM tl deck\nCE\n"
        "GW 1 9 0 0 1 0 0 11 .001\n"
        "GW 2 9 5 0 1 5 0 11 .001\n"
        "TL 1 5 2 5 50. 5.\n"
        "EX 0 1 5 0 1 0\n"
        "XQ\nEN\n",
        tmp_path,
    )
    assert res["out_of_scope"] is True
    assert "NotImplementedError" in res["error"]
    assert engine_error_kind(res) == "scope"


def test_worker_tags_refl_coef_ground_out_of_scope(capsys, monkeypatch, tmp_path):
    """GN 0 maps to ("finite-fast", ...) which NEC-5 cannot express (its
    IPERF 0 is full Sommerfeld — no refl-coef option exists)."""
    monkeypatch.setenv("NEC5_EXE", sys.executable)
    res = _run_worker(
        capsys,
        "CM gn0\nCE\nGW 1 10 0 -2.5 5 0 2.5 5 .001\nGN 0 0 0 0 13 .005\n"
        "EX 0 1 5 0 1 0\nXQ\nEN\n",
        tmp_path,
        ground=["finite-fast", 13.0, 0.005],
    )
    assert res["out_of_scope"] is True
    assert engine_error_kind(res) == "scope"


def test_worker_real_failure_is_not_scope(capsys, monkeypatch, tmp_path):
    """A missing binary is a failure, not dialect scope."""
    monkeypatch.delenv("NEC5_EXE", raising=False)
    res = _run_worker(
        capsys,
        "CM d\nCE\nGW 1 10 0 -2.5 5 0 2.5 5 .001\nEX 0 1 5 0 1 0\nXQ\nEN\n",
        tmp_path,
    )
    assert res.get("out_of_scope") is None
    assert engine_error_kind(res) == "err"


def test_worker_wires_capture_dir_through_env(capsys, monkeypatch, tmp_path):
    """NEC5_CAPTURE_DIR (how run_engine passes --nec5-capture-dir with the
    --worker argv arity fixed at 4) reaches the engine: the run's deck and
    printout land in the capture dir. The stub 'binary' copies a fixture
    printout whose feed rows don't match this model — the worker therefore
    reports the row-mismatch NEC5Error (a real failure, not scope), but the
    capture is written regardless, because _run captures before parsing."""
    fixtures = Path(__file__).parent / "fixtures" / "nec5"
    stub = tmp_path / "nec5-stub.sh"
    stub.write_text(
        "#!/bin/sh\nread inp\nread outp\n"
        f'cp "{(fixtures / "invvee_dipole_single.out").resolve()}" "$outp"\n'
    )
    stub.chmod(0o755)
    captures = tmp_path / "captures"
    monkeypatch.setenv("NEC5_EXE", str(stub))
    monkeypatch.setenv("NEC5_CAPTURE_DIR", str(captures))
    res = _run_worker(
        capsys,
        "CM d\nCE\nGW 1 10 0 -2.5 5 0 2.5 5 .001\nEX 0 1 5 0 1 0\nXQ\nEN\n",
        tmp_path,
    )
    assert res["error"] and "NEC5Error" in res["error"]
    assert res.get("out_of_scope") is None
    assert sorted(p.suffix for p in captures.iterdir()) == [".nec", ".out"]


def test_solve_design_dispatches_nec5():
    """#872 phase 2: nec5 rides bench_converge's ladder machinery as just
    another engine key — its knot source is the same feed class as bs1's
    tent basis (both segment_parity="even"), so no special-casing beyond
    the dispatch branch. Skips without the licensed binary."""
    import pytest

    import bench_converge as bc
    from antennaknobs.engines.nec5 import find_nec5

    if find_nec5() is None:
        pytest.skip("no licensed NEC-5 binary")
    res = bc.solve_design(bc.load_design("dipoles.invvee"), 21, "nec5", "free")
    assert res["error"] is None
    z = complex(res["z"][0][0], res["z"][0][1])
    # Loose physics bar: the invvee dipole variant feeds ~55 ohm.
    assert 30 < z.real < 90 and abs(z.imag) < 60
