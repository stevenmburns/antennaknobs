"""antennaknobs#1389: the gear menu's Download offers the NEC-5 dialect too.

AC6LA, QRZ Windows thread, 2026-09-10 1:52 PM: opened
`verticals.buried_radial_vertical`, set all three engine slots to NEC-5, clicked
Download .nec, and got a 422 reading

    PyNEC: wire 4 uses the graded-mesh spelling (GradedSegments), which only the
    momwire engine consumes today ...

Two of our faults in one message. The download wrote the NEC-2 dialect only,
whatever engine was selected — and `NEC5Engine.deck()` writes exactly that design,
the corpus tool's zip already ships it as
`verticals.buried_radial_vertical.default.somm13.nec`. And the refusal named
PyNEC, which the user had not selected and had no reason to connect to a deck
writer.

Both downloads are offered ALWAYS (decision 1 on the issue): neither writer needs
an engine, and the person who most needs the file is the one without the engine on
that machine. What varies is whether the DESIGN can be said in that dialect.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import antennaknobs.web.server as _server

ROOT = Path(__file__).resolve().parents[1]
BURIED = "verticals.buried_radial_vertical"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_server.app)


def _post(client, geometry, dialect=None, **extra):
    req = {"geometry": geometry, **extra}
    if dialect is not None:
        req["dialect"] = dialect
    return client.post("/export_nec", json=req)


# --------------------------------------------------------------------------
# the user story
# --------------------------------------------------------------------------


def test_the_nec2_download_of_a_graded_design_refuses_without_naming_pynec(client):
    r = _post(client, BURIED, "nec2", ground=True)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "PyNEC" not in detail, detail
    assert detail.startswith("a NEC-2 deck cannot express"), detail
    assert "download the NEC-5 deck instead" in detail, detail


def test_the_nec5_download_of_that_design_succeeds(client):
    """The file the user wanted, and the whole point of the issue."""
    r = _post(client, BURIED, "nec5", ground=True)
    assert r.status_code == 200, r.text
    deck = r.text
    assert deck.startswith(f"CM antennaknobs catalog design {BURIED} "), deck[:120]
    assert "\nEN" in deck
    assert any(
        ln.startswith("GW") and float(ln.split()[5]) < 0.0
        for ln in deck.splitlines()
        if ln.startswith("GW")
    ), "no buried wire in a buried design's deck"


def test_the_two_downloads_have_different_filenames(client):
    """Otherwise the second overwrites the first in a download folder."""
    n2 = _post(client, "dipoles.invvee", "nec2").headers["Content-Disposition"]
    n5 = _post(client, "dipoles.invvee", "nec5").headers["Content-Disposition"]
    assert 'filename="dipoles_invvee.nec"' in n2, n2
    assert 'filename="dipoles_invvee.nec5.nec"' in n5, n5


def test_an_ordinary_design_serves_both_dialects(client):
    for dialect in ("nec2", "nec5"):
        r = _post(client, "dipoles.invvee", dialect)
        assert r.status_code == 200, (dialect, r.text)
        assert r.text.rstrip().endswith("EN"), dialect


def test_the_default_dialect_is_nec2_so_an_old_client_is_unchanged(client):
    """A frontend that sends no `dialect` must get the file it always got."""
    old = _post(client, "dipoles.invvee")
    new = _post(client, "dipoles.invvee", "nec2")
    assert old.status_code == new.status_code == 200
    assert old.text == new.text
    assert old.headers["Content-Disposition"] == new.headers["Content-Disposition"]


def test_an_unknown_dialect_is_a_422_that_names_the_two(client):
    r = _post(client, "dipoles.invvee", "nec4")
    assert r.status_code == 422
    assert "nec2 or nec5" in r.json()["detail"]


def test_a_tl_network_refuses_in_both_dialects(client):
    """Neither dialect has a single-deck spelling: the app solves those by a
    multiport-Y reduction over one deck per driven port."""
    for dialect in ("nec2", "nec5"):
        r = _post(client, "broadband.lpda", dialect)
        assert r.status_code == 422, (dialect, r.status_code)
        detail = r.json()["detail"]
        assert "TL/virtual-driver networks" in detail, (dialect, detail)
        assert "PyNEC" not in detail, (dialect, detail)


# --------------------------------------------------------------------------
# byte-equality with the catalog export the corpus tool's zip ships
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("geometry", "ground_req", "gname"),
    [
        (BURIED, {"ground": True}, "somm13"),
        (BURIED, {}, "free"),
        ("dipoles.invvee", {}, "free"),
        ("dipoles.invvee", {"ground": True}, "somm13"),
    ],
)
def test_the_download_is_byte_equal_to_the_catalog_export(
    client, tmp_path, geometry, ground_req, gname
):
    """The gate on this feature, and the reason the header lives in
    `antennaknobs.nec5_export` rather than in the export script.

    The corpus tool's zip ships `catalog-nec5/<design>.<rung>.<ground>.nec`. A
    user who downloads the same design at the same mesh and ground must get the
    same file — otherwise the two disagree about one design and the disagreement
    looks like an engine bug rather than a comment. Run the SCRIPT for this one
    design (`--only`) and compare bytes.
    """
    out = tmp_path / "cat"
    r = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "nec5_corpus" / "export_catalog_nec5.py"),
            "--out",
            str(out),
            "--only",
            geometry,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    name = re.sub(r"[^\w.]", "_", geometry) + f".default.{gname}.nec"
    ref = out / name
    assert ref.is_file(), sorted(p.name for p in out.glob("*.nec"))
    served = _post(client, geometry, "nec5", **ground_req)
    assert served.status_code == 200, served.text
    assert served.text == ref.read_text(), (
        f"{name}: the download and the shipped catalog deck differ"
    )


def test_the_script_and_the_download_share_one_header_writer():
    """Asserted on the source, because the failure mode is a second copy of the
    text rather than a wrong value — and a second copy passes every test that
    only checks one of the two."""
    script = (ROOT / "scripts" / "nec5_corpus" / "export_catalog_nec5.py").read_text()
    assert "from antennaknobs.nec5_export import catalog_header" in script
    assert "CM antennaknobs catalog design {" not in script, (
        "the header is spelled a second time in the script"
    )


# --------------------------------------------------------------------------
# neither writer needs an engine
# --------------------------------------------------------------------------

_BLOCK = (
    "import sys, os; sys.modules['PyNEC'] = None; os.environ.pop('NEC5_EXE', None)\n"
)


def _run_blocked(code: str) -> str:
    r = subprocess.run(
        [sys.executable, "-c", _BLOCK + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def test_the_nec5_writer_needs_neither_pynec_nor_a_nec5_binary():
    """The decision this feature rests on: offering the download only where
    $NEC5_EXE resolves would withhold the file from exactly the person who needs
    it. A subprocess, because this venv has PyNEC installed and usually no
    NEC5_EXE — an in-process test would prove only half of it."""
    out = _run_blocked("""
        import importlib
        from antennaknobs.nec5_export import export_nec5
        B = importlib.import_module("antennaknobs.designs.verticals.buried_radial_vertical").Builder
        deck = export_nec5(B(), ground=("finite", 13.0, 0.005),
                           design="verticals.buried_radial_vertical",
                           rung="default", ground_name="somm13")
        assert deck.startswith("CM antennaknobs catalog design"), deck[:80]
        assert deck.rstrip().endswith("EN"), deck[-80:]
        print("ok", len(deck.splitlines()))
    """)
    assert out.startswith("ok")


def test_the_endpoint_serves_the_nec5_deck_with_pynec_blocked():
    """End to end through the server, not just the writer."""
    out = _run_blocked("""
        from fastapi.testclient import TestClient
        import antennaknobs.web.server as server
        c = TestClient(server.app)
        r = c.post("/export_nec", json={"geometry": "verticals.buried_radial_vertical",
                                        "ground": True, "dialect": "nec5"})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        assert r.text.startswith("CM antennaknobs catalog design"), r.text[:80]
        print("ok", len(r.text.splitlines()))
    """)
    assert out.startswith("ok")


def test_the_manifest_of_the_one_design_export_is_json():
    """Guards the `--only` path the byte-equality test above depends on: a run
    that wrote nothing would make that test vacuous."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "nec5_corpus" / "export_catalog_nec5.py"),
                "--out",
                td,
                "--only",
                BURIED,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert r.returncode == 0, r.stderr[-2000:]
        manifest = json.loads((Path(td) / "manifest.json").read_text())
        assert manifest["written"], manifest
        assert all(w["design"] == BURIED for w in manifest["written"]), manifest
