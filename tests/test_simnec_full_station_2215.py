"""A full-station SimNEC file opens alone (AK#2215).

A real ``.ssn`` modelling a whole station (an antenna in its NEC-portal
block, then an S-block unun, coax, an S-block choke and coax) refused to
open, though nothing in it was beyond the importer:

- its script carried a ``Button`` (a tune SimNEC runs only when clicked) and
  ``pl`` print lines, which the importer read as statements it could not
  apply;
- its S blocks' ``.s2p`` files were in the ``.ssn`` itself (SimNEC stores a
  copy of every file the circuit names), which only a folder beside it could
  supply;
- its Generator sweep listed single values in ``{3, 30}``.

And a design reading the circuit with ``read_ssn`` solved PEC wire, since
only the app's loader applied the file's wire material. Every fixture here
is synthetic; the real file stays private.
"""

from __future__ import annotations

import base64
import gzip
import xml.etree.ElementTree as ET
from types import MappingProxyType

import numpy as np
import pytest

from antennaknobs.builder import AntennaBuilder
from antennaknobs.cli import make_engine_factory
from antennaknobs.file_designs import builder_from_file
from antennaknobs.simnec_import import parse_ssn, parse_ssn_station
from antennaknobs.web.decks import DeckError, DeckSettings, decode_payload

FREQ = 7.0
DIPOLE = "GW 1,21,0,0,0,0,0,20.4,.001"


def _script(*after: str, before: tuple[str, ...] = ()) -> str:
    return "\n".join(
        [
            "//test",
            "P1 w1 gnd;",
            "P2 w2 gnd;",
            "NECUnits meters;",
            *before,
            "NEC2",
            DIPOLE,
            "EX 0 1 11 0 1 0",
            "NECEND",
            "$GW_1.JamSegments(21);",
            *after,
        ]
    )


S11, S21, S22 = 0.08 + 0.05j, 0.93 - 0.21j, -0.03 + 0.12j


def _s2p(s21=S21) -> str:
    return "\n".join(
        [
            "# MHz S RI R 50",
            *(
                f"{f} {S11.real} {S11.imag} {s21.real} {s21.imag} "
                f"{s21.real} {s21.imag} {S22.real} {S22.imag}"
                for f in (6.9, 7.0, 7.1)
            ),
        ]
    )


def _stored(name: str, text: str | bytes) -> tuple[str, str]:
    """A FILEARCHIVE entry as SimNEC writes one: gzip, then base64 broken
    into lines."""
    raw = text.encode() if isinstance(text, str) else text
    b64 = base64.b64encode(gzip.compress(raw)).decode()
    return name, "\n".join(b64[i : i + 76] for i in range(0, len(b64), 76))


def _ssn(script: str | None, *, archive=(), s_file="choke.s2p") -> str:
    """A circuit: the antenna (a NEC-portal block, or with ``script`` None a
    LOAD reading ``ant.txt``), an S block naming ``s_file``, the GENERATOR,
    and a FILEARCHIVE holding ``archive`` ((name, compressed) pairs)."""
    root = ET.Element("SimNEC1p0")
    top = ET.SubElement(root, "SmithChartCircuit")
    fa = ET.SubElement(top, "FILEARCHIVE")
    for name, blob in archive:
        el = ET.SubElement(fa, "element")
        ET.SubElement(el, "name").text = name
        ET.SubElement(el, "compressed").text = blob
    circuit = ET.SubElement(top, "CIRCUIT")

    def element(typ, label, params):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params:
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v

    if script is None:
        element("LOAD", "L", [("ohms", "50"), ("johms", "0"), ("file", ".\\ant.txt")])
    else:
        element("LOAD", "L", [("ohms", "1000000000")])
        element("NETWORK", "A", [("equ", script)])
    element(
        "SCATTERING",
        "S1",
        [("dir", "2 <> 1"), ("Zref", "50"), ("file", f".\\{s_file}")],
    )
    element("GENERATOR", "G", [("MHz", str(FREQ)), ("Zo", "50")])
    return ET.tostring(root, encoding="unicode")


def _z(c) -> complex:
    class Circuit(AntennaBuilder):
        default_params = MappingProxyType({"freq": FREQ})

        def build_wires(self):
            return c.deck.wire_tuples(specs=True)

        def build_network(self):
            return c.network()

    return complex(
        make_engine_factory("momwire:bspline", None)(Circuit()).impedance()[0]
    )


def _antenna_only(script: str) -> str:
    root = ET.Element("SimNEC1p0")
    circuit = ET.SubElement(ET.SubElement(root, "SmithChartCircuit"), "CIRCUIT")
    for typ, label, params in (
        ("LOAD", "L", [("ohms", "1000000000")]),
        ("NETWORK", "A", [("equ", script)]),
        ("GENERATOR", "G", [("MHz", str(FREQ)), ("Zo", "50")]),
    ):
        el = ET.SubElement(circuit, "element")
        ET.SubElement(el, "type").text = typ
        ET.SubElement(el, "sweeperLabel").text = label
        for n, v in params:
            p = ET.SubElement(el, "p")
            ET.SubElement(p, "n").text = n
            ET.SubElement(p, "v").text = v
    return ET.tostring(root, encoding="unicode")


# --- a button and print lines leave the model alone --------------------------

BUTTON = [
    "at(epilog) pl len SWR(A.Z, 50) G.MHz;",
    "Button TuneMinSWR() {",
    "    $NM = NelderMead",
    "        (POSITIVES, TOLERANCE=0.001, COUNT=100, len) {",
    "            InCircuitWith(G.MHz = atMHz) { SWR(A.Z, 50); }",
    "    }",
    "    pl $NM.elapsed / 1000;   // seconds",
    "    pl $NM;",
    "}",
    "atMHz;",
]


def test_a_button_and_print_lines_open_and_leave_the_model_alone():
    with_ui = parse_ssn(_antenna_only(_script(*BUTTON)), name="t.ssn", network=True)
    plain = parse_ssn(_antenna_only(_script()), name="t.ssn", network=True)
    assert "Button TuneMinSWR() { … }" in with_ui.ignored_directives
    assert "pl len SWR(A.Z, 50) G.MHz" in with_ui.ignored_directives
    assert "Button TuneMinSWR" in with_ui.skipped_note()
    assert _z(with_ui) == _z(plain)


def test_a_button_is_never_run_even_when_its_body_builds_the_antenna():
    """What a click changes, SimNEC saves in the file's values; the body is
    not part of a solve."""
    c = parse_ssn(
        _antenna_only(
            _script("Button AddLoad() {", "$ld = NECSource(R(50), $GW_1, 50);", "}")
        ),
        name="t.ssn",
        network=True,
    )
    assert not c.deck.loads
    assert "Button AddLoad() { … }" in c.ignored_directives


def test_a_block_after_a_call_outside_a_button_is_read_as_a_guarded_block():
    """`InCircuitWith(...) { ... }` runs its body only inside that call: a
    model statement there is not applied, so the file is refused by name."""
    text = _antenna_only(
        _script("InCircuitWith(G.MHz = 7) { $ld = NECSource(R(50), $GW_1, 50); }")
    )
    with pytest.raises(ValueError, match=r"line \d+: \$ld = NECSource.*InCircuitWith"):
        parse_ssn(text, name="t.ssn", network=True)


def test_an_unclosed_button_does_not_swallow_the_rest_silently():
    """The tokenizer stays lexical: an unclosed body closes at the end of the
    script, and what follows the button is inside it, never applied."""
    c = parse_ssn(
        _antenna_only(_script("Button Open() {", "pl 1;")), name="t.ssn", network=True
    )
    assert "Button Open() { … }" in c.ignored_directives


# --- files SimNEC stores in the .ssn -----------------------------------------


def _s_y(c):
    (ts,) = [b for b in c.network().branches if type(b).__name__ == "TouchstoneTwoPort"]
    return np.asarray(ts.data.y_at(FREQ * 1e6))


def test_a_stored_s2p_stands_in_for_the_folder():
    archive = [_stored("C:\\SimNEC_lite\\choke.s2p", _s2p())]
    alone = parse_ssn(_ssn(_script(), archive=archive), name="t.ssn", network=True)
    beside = parse_ssn(
        _ssn(_script()), name="t.ssn", network=True, files=lambda p: _s2p()
    )
    assert np.array_equal(_s_y(alone), _s_y(beside))
    assert "S1's 'choke.s2p' is read from the copy SimNEC stored in the .ssn" in (
        alone.skipped_note()
    )
    assert "stored" not in (beside.skipped_note() or "")


def test_a_file_beside_the_ssn_wins_over_the_stored_copy():
    archive = [_stored("choke.s2p", _s2p(s21=0.5 + 0j))]
    c = parse_ssn(
        _ssn(_script(), archive=archive),
        name="t.ssn",
        network=True,
        files=lambda p: _s2p(),
    )
    want = parse_ssn(
        _ssn(_script()), name="t.ssn", network=True, files=lambda p: _s2p()
    )
    assert np.array_equal(_s_y(c), _s_y(want))
    assert "stored" not in (c.skipped_note() or "")


def test_a_station_reads_its_stored_files_too():
    table = "Generic 1 1e6 2 3\n6.9 41.0 -18.0\n7.0 44.0 -9.0\n7.1 47.5 2.5\n"
    archive = [_stored("choke.s2p", _s2p()), _stored("ant.txt", table)]
    st = parse_ssn_station(_ssn(None, archive=archive), name="t.ssn")
    assert st.antenna_table() is not None
    assert "read from the copy SimNEC stored" in st.skipped_note()


def test_a_name_not_stored_and_no_folder_refuses_by_name():
    with pytest.raises(ValueError, match="'choke.s2p' is not stored in the file"):
        parse_ssn(
            _ssn(_script(), archive=[_stored("other.s2p", _s2p())]),
            name="t.ssn",
            network=True,
        ).network()


def test_a_corrupt_stored_copy_refuses_by_name():
    with pytest.raises(ValueError, match="copy of 'choke.s2p' stored in the file"):
        parse_ssn(
            _ssn(_script(), archive=[("choke.s2p", "not*base64!")]),
            name="t.ssn",
            network=True,
        )


def test_stored_copies_cannot_inflate_past_the_cap():
    bomb = _stored("choke.s2p", b"0" * (5 * 1024 * 1024))
    with pytest.raises(ValueError, match="over 4194304 bytes"):
        parse_ssn(_ssn(_script(), archive=[bomb]), name="t.ssn", network=True)


def test_the_app_opens_a_full_station_file_alone(tmp_path):
    p = tmp_path / "station.ssn"
    p.write_text(_ssn(_script(), archive=[_stored("choke.s2p", _s2p())]))
    builder = builder_from_file(str(p))
    ui = builder.default_params["ui_params"]
    assert "read from the copy SimNEC stored in the .ssn" in ui["notes"]
    b = builder()
    assert {"rig", "feed", "S1"} <= set(b.build_network().ports)


# --- the wire material, the sweep, the mesh note -----------------------------


def test_parse_ssn_applies_the_files_wire_material():
    c = parse_ssn(
        _antenna_only(_script(before=("NECOptions.mhosPerMeter = 5.8e7;",))),
        name="t.ssn",
        network=True,
    )
    assert c.deck.conductivity == pytest.approx(5.8e7)
    (w,) = c.deck.wire_tuples(specs=True)
    assert w.spec.conductivity == pytest.approx(5.8e7)


def test_every_wire_jammed_means_one_mesh():
    c = parse_ssn(_antenna_only(_script()), name="t.ssn", network=True)
    assert c.mesh_note().startswith("Every wire's segment count is held by JamSegments")


def test_an_opened_ssn_has_room_for_its_stored_files():
    st = DeckSettings(hosted=True)
    name, text = decode_payload({"name": "s.ssn", "text": "x" * 100_000}, st)
    assert name == "s.ssn" and len(text) == 100_000
    with pytest.raises(DeckError, match="256 KB"):
        decode_payload({"name": "s.ssn", "text": "x" * 300_000}, st)
    with pytest.raises(DeckError, match="64 KB"):
        decode_payload({"name": "d.nec", "text": "x" * 100_000}, st)
