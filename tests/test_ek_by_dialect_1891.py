"""AK#1891 (Steve, 2026-10-04): a deck read as NEC-4 or NEC-5 solves with the
extended kernel ON by default.

NEC-5's kernel behaves as EK-on and has no EK card; NEC-4.2's single
thin-wire model is the extended one, and it prints that an EK card has no
effect. So the kernel follows the dialect: NEC-2 takes the card's word, NEC-4
and NEC-5 default to EK and ignore an EK card (a NEC-4 VC card is noted as
not modelled). The user's switch wins both ways, a "Read as" change
re-resolves the default, and a basis or deck that refuses the extended kernel
falls back to the reduced one with an advisory instead of refusing, since
the default is ours.

The default is proved where it matters, at the momwire solver CONSTRUCTOR,
reached through the CLI (`antennaknobs analyze --builder @deck.nec`) and
the web (`/deck`, then a solve) — never through an engine a test builds
itself, which would bypass the wiring this issue is about.
"""

from __future__ import annotations

import base64
import re
import zlib

import matplotlib.pyplot as plt
import pytest
from fastapi.testclient import TestClient
from momwire import BSplineSolver, HarringtonSolver, RazorSolver

import antennaknobs as ant
from antennaknobs.engines import MomwireEngine
from antennaknobs.file_designs import builder_from_text
from antennaknobs.nec_import import parse_nec
from antennaknobs.web import decks, server

# A centre-fed 5 m dipole at 28 MHz: thin, and fat (Δ/a ≈ 4.5).
_DIPOLE = """CM {cm}
CE
GW 1 {n} 0 0 -2.5 0 0 2.5 {a}
{ek}GE 0
EX 0 1 11 {i4} 1 0
FR 0 1 0 0 28.0
EN
"""


def _text(dialect: str, *, a: float = 0.001, ek: str = "") -> str:
    """The dipole as each dialect's program writes it: NEC-5 feeds the 22-
    segment wire at the knot between segments 11 and 12 (I4 = 2), NEC-4 and
    NEC-2 the centre of segment 11 of 21."""
    cm = {"nec5": "NEC-5", "nec4": "NEC-4.2", "nec2": "dipole"}[dialect]
    n, i4 = (22, 2) if dialect == "nec5" else (21, 0)
    return _DIPOLE.format(cm=cm, n=n, a=a, i4=i4, ek=ek)


def _deck(text: str, **kw):
    return parse_nec(text, name="d.nec", network=True, **kw)


# --------------------------------------------------------------------------
# the importer: the kernel follows the reading
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("dialect", "by_dialect"), [("nec5", True), ("nec4", True), ("nec2", False)]
)
def test_the_reading_decides_the_default(dialect, by_dialect):
    d = _deck(_text(dialect))
    assert d.dialect == dialect
    assert d.extended_kernel_by_dialect is by_dialect
    assert d.extended_kernel is False and d.ek_card_ignored is False


def test_nec2_keeps_the_cards_word():
    assert _deck(_text("nec2", ek="EK\n")).extended_kernel is True
    assert _deck(_text("nec2", ek="EK -1\n")).extended_kernel is False


@pytest.mark.parametrize(
    ("dialect", "sentence"),
    [
        ("nec4", "NEC-4 ignores EK; the extended kernel is used."),
        ("nec5", "NEC-5 has no EK card; the extended kernel is used."),
    ],
)
def test_an_ek_card_under_nec4_or_nec5_is_ignored_with_a_note(dialect, sentence):
    d = _deck(_text(dialect, ek="EK\n"))
    assert d.extended_kernel is False and d.ek_card_ignored is True
    assert d.dialect_note().endswith(sentence)
    # `EK -1` is ignored the same way: the dialect decides, not the card.
    assert _deck(_text(dialect, ek="EK -1\n")).ek_card_ignored is True


def test_a_nec4_vc_card_reads_and_is_noted_as_not_modelled():
    d = _deck(_text("nec4", ek="VC 0\n"))
    assert "VC" in d.ignored
    assert "VC (NEC-4's source and end-cap option, not modelled)" in d.skipped_note()


def test_read_as_re_resolves_the_default():
    text = _text("nec5")
    assert builder_from_text("d.nec", text).file_extended_kernel_default is True
    as2 = builder_from_text(
        "d.nec", text.replace("EX 0 1 11 2", "EX 0 1 11 0"), dialect="nec2"
    )
    assert as2.file_extended_kernel_default is False
    as4 = builder_from_text("d.nec", _text("nec2"), dialect="nec4")
    assert as4.file_extended_kernel_default is True
    ui = dict(dict(as4.default_params)["ui_params"])
    assert ui["extended_kernel_default"] is True
    assert "extended_kernel_default" not in dict(dict(as2.default_params)["ui_params"])


@pytest.mark.parametrize("dialect", ["nec5", "nec4"])
def test_a_nec_export_re_reads_ek_on(dialect, tmp_path, capsys):
    """`CM NEC-5` / `CM NEC-4.2`, which `antennaknobs export` stamps, re-read
    as their dialect, so a round trip keeps the kernel the deck had."""
    src = tmp_path / "d.nec"
    src.write_text(_text("nec2"))
    out = tmp_path / "e.nec"
    ant.cli(
        ["export", "--builder", f"@{src}", "--dialect", dialect,
         "--ground", "free", "--out", str(out)]
    )  # fmt: skip
    capsys.readouterr()
    cls = builder_from_text("e.nec", out.read_text())
    assert cls.file_deck_parsed.dialect == dialect
    assert cls.file_extended_kernel_default is True


# --------------------------------------------------------------------------
# the engine: a default falls back, a request refuses
# --------------------------------------------------------------------------
def _ek_constructions(monkeypatch, *classes):
    """Each solver construction's `extended_kernel`, in order, for `classes`."""
    seen: list[bool] = []
    for cls in classes:
        inner = cls.__init__

        def wrapped(self, *args, _inner=inner, **kwargs):
            seen.append(bool(kwargs.get("extended_kernel", False)))
            _inner(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", wrapped)
    return seen


def test_a_refusing_basis_falls_back_with_an_advisory():
    # NEC-4's centre feed: the pulse basis serves centre feeds only.
    cls = builder_from_text("d.nec", _text("nec4"))
    eng = MomwireEngine(cls(), solver=HarringtonSolver, extended_kernel_default=True)
    eng.impedance()
    notes = [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    assert len(notes) == 1 and "reduced kernel" in notes[0]["text"]
    # The same basis REFUSES the kernel when it is asked for, as before.
    with pytest.raises(NotImplementedError):
        MomwireEngine(cls(), solver=HarringtonSolver, extended_kernel=True)


def test_a_buried_wire_falls_back_with_an_advisory():
    text = (
        "CM NEC-4.2\nCE\nGW 1 11 0 -2 -0.5 0 2 -0.5 0.001\nGE 1\n"
        "GN 2 0 0 0 13 0.005\nEX 0 1 6 0 1 0\nFR 0 1 0 0 14.0\nEN\n"
    )
    cls = builder_from_text("b.nec", text)
    assert cls.file_extended_kernel_default is True
    eng = MomwireEngine(
        cls(),
        solver=BSplineSolver,
        ground=cls.file_ground,
        extended_kernel_default=True,
    )
    assert eng._extended_kernel is False
    (note,) = [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    assert "below" in note["text"] or "buried" in note["text"]


def test_an_accepting_basis_takes_the_default_silently():
    cls = builder_from_text("d.nec", _text("nec5"))
    eng = MomwireEngine(cls(), solver=RazorSolver, extended_kernel_default=True)
    assert eng._extended_kernel is True
    assert not [a for a in eng.advisories if a["category"] == "ExtendedKernel"]


# --------------------------------------------------------------------------
# the CLI: `antennaknobs analyze --builder @deck.nec`
# --------------------------------------------------------------------------
def _analyze(path, *extra):
    try:
        ant.cli(
            ["analyze", "--builder", f"@{path}", "--analysis", "band SWR",
             "--engine", "momwire:razor-2p", "--fn", "/dev/null", *extra]
        )  # fmt: skip
    finally:
        plt.close("all")


@pytest.mark.parametrize(
    ("dialect", "ek", "extra", "want"),
    [
        ("nec5", "", (), True),
        ("nec4", "EK\n", (), True),
        ("nec5", "", ("--no-extended-kernel",), False),
        ("nec2", "", (), False),
        ("nec2", "EK\n", (), True),
        ("nec2", "", ("--extended-kernel",), True),
    ],
    ids=[
        "nec5",
        "nec4-ek-card",
        "nec5-switched-off",
        "nec2",
        "nec2-ek-card",
        "nec2-switched-on",
    ],
)
def test_the_cli_solves_with_the_resolved_kernel(
    dialect, ek, extra, want, tmp_path, monkeypatch, capsys
):
    path = tmp_path / "d.nec"
    path.write_text(_text(dialect, ek=ek))
    seen = _ek_constructions(monkeypatch, RazorSolver)
    _analyze(path, *extra)
    capsys.readouterr()
    assert seen and set(seen) == {want}, seen


def test_the_cli_echoes_a_fallback_advisory(tmp_path, monkeypatch, capsys):
    path = tmp_path / "d.nec"
    path.write_text(_text("nec4"))
    try:
        ant.cli(
            ["sweep", "--builder", f"@{path}", "--engine", "momwire:pulse",
             "--npoints", "1", "--range", "28", "28", "--fn", "/dev/null"]
        )  # fmt: skip
    finally:
        plt.close("all")
    err = capsys.readouterr().err
    assert "advisory: This deck solves with the extended kernel by default" in err


def _z_table(out: str) -> complex:
    m = re.search(r"^\s*28\s+(\S+)\s+(\S+)$", out, re.M)
    assert m, out
    return complex(float(m[1]), float(m[2]))


def test_a_fat_nec5_deck_moves_toward_nec5(tmp_path, capsys):
    """The issue's evidence, one rung of it: the fat dipole (Δ/a ≈ 4.5) as
    NEC-5 itself solved it, x13, 2026-10-04 (`ek-nec42/d5_0.05.out`):
    71.186 − j3.290 Ω. The dialect's default kernel lands closer than the
    reduced one."""
    path = tmp_path / "fat.nec"
    path.write_text(_text("nec5", a=0.05))
    nec5 = complex(71.186, -3.290)
    zs = {}
    for label, extra in (("default", ()), ("reduced", ("--no-extended-kernel",))):
        try:
            ant.cli(
                ["sweep", "--builder", f"@{path}", "--engine", "momwire:razor-2p",
                 "--npoints", "1", "--range", "28", "28", "--fn", "/dev/null",
                 *extra]
            )  # fmt: skip
        finally:
            plt.close("all")
        zs[label] = _z_table(capsys.readouterr().out)
    assert abs(zs["default"] - nec5) < abs(zs["reduced"] - nec5), zs


# --------------------------------------------------------------------------
# the web: /deck, then a solve
# --------------------------------------------------------------------------
def _payload(text: str, **kw) -> dict:
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = c.compress(text.encode()) + c.flush()
    return {
        "name": "d.nec",
        "z": base64.urlsafe_b64encode(packed).decode().rstrip("="),
        **kw,
    }


@pytest.fixture()
def client(monkeypatch):
    st = server._DECK_SETTINGS
    monkeypatch.setattr(server, "_DECK_OPENS", decks.RateLimiter(0))
    monkeypatch.setattr(server, "_DECK_GATE", decks.DeckGate(st))
    store = decks.DeckStore(st, server._register_deck, server._unregister_deck)
    monkeypatch.setattr(server, "_DECK_STORE", store)
    yield TestClient(server.app)
    for key in list(server.EXAMPLES):
        if decks.is_deck(key):
            del server.EXAMPLES[key]


def _cell(client, key, **kw):
    body = {
        "geometry": key,
        "solver": "momwire",
        "momwire_model": "razor-2p",
        "n_per_wire": 40,
        "ground": False,
        "design_freq_mhz": 28.0,
        "measurement_freq_mhz": 28.0,
        **kw,
    }
    r = client.post("/pattern_cell", json=body)
    assert r.status_code == 200 and r.json()["available"], r.text
    return r.json()["solve"]


def test_an_opened_nec5_deck_is_served_with_the_default(client):
    opened = client.post("/deck", json=_payload(_text("nec5"))).json()
    assert opened["dialect"]["read_as"] == "nec5"
    assert opened["example"]["extended_kernel_default"] is True


# NEC-4's centre feed in the solves below: the web withholds razor-2p from a
# segment-end (vertex) port (`adapter._VERTEX_PORT_WITHHELD`), which a NEC-5
# deck's knot feed is.
@pytest.mark.parametrize(
    ("dialect", "model_options", "want"),
    [
        ("nec4", None, True),
        ("nec4", {"extended_kernel": True}, True),
        ("nec4", {"extended_kernel": False}, False),
        ("nec2", None, False),
        ("nec2", {"extended_kernel": True}, True),
    ],
    ids=["nec4", "nec4-on", "nec4-off", "nec2", "nec2-on"],
)
def test_an_opened_deck_solves_with_the_resolved_kernel(
    dialect, model_options, want, client, monkeypatch
):
    opened = client.post("/deck", json=_payload(_text(dialect))).json()
    assert opened["example"]["extended_kernel_default"] is (dialect != "nec2")
    seen = _ek_constructions(monkeypatch, RazorSolver)
    kw = {} if model_options is None else {"model_options": model_options}
    _cell(client, opened["key"], **kw)
    assert seen and set(seen) == {want}, seen


def test_read_as_nec2_turns_an_opened_decks_default_off(client, monkeypatch):
    text = _text("nec4")
    as4 = client.post("/deck", json=_payload(text)).json()
    as2 = client.post("/deck", json=_payload(text, dialect="nec2")).json()
    assert as4["example"]["extended_kernel_default"] is True
    assert as2["example"]["extended_kernel_default"] is False
    seen = _ek_constructions(monkeypatch, RazorSolver)
    _cell(client, as2["key"])
    assert seen and set(seen) == {False}, seen


def test_an_opened_deck_on_a_refusing_tab_falls_back_and_says_so(client):
    opened = client.post("/deck", json=_payload(_text("nec4"))).json()
    out = _cell(client, opened["key"], momwire_model="pulse", n_per_wire=41)
    notes = [
        a for a in out.get("advisories") or () if a["category"] == "ExtendedKernel"
    ]
    assert len(notes) == 1, out.get("advisories")
