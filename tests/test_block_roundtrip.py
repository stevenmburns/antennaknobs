"""Round trip (docs/design/block-builder.md): generate, save, reopen gives
the same tree; a hand-edited file is detected and never parsed as Python."""

from __future__ import annotations

import base64
import json

import pytest

from antennaknobs import block_codegen as cg
from antennaknobs.block_templates import NAMES, template


@pytest.mark.parametrize("name", NAMES)
def test_generate_save_reopen_is_the_same_tree(name, tmp_path):
    tree = template(name)
    path = tmp_path / f"{name}.py"
    path.write_text(cg.generate(tree), encoding="utf-8")
    assert cg.reopen(path.read_text(encoding="utf-8")) == tree


def test_the_trailer_is_the_last_line_and_holds_canonical_json():
    tree = template("hentenna")
    text = cg.generate(tree)
    last = text.rstrip("\n").rsplit("\n", 1)[1]
    assert last.startswith("# antennaknobs-blocks: v1 ")
    payload = base64.b64decode(last.split()[-1])
    assert json.loads(payload) == tree
    assert payload.decode("utf-8") == cg.canonical_json(tree)


def test_windows_line_endings_are_not_a_hand_edit():
    tree = template("dipole")
    assert cg.reopen(cg.generate(tree).replace("\n", "\r\n")) == tree


@pytest.mark.parametrize(
    "edit",
    [
        # A changed number in the code.
        lambda t: t.replace("eps = 0.05", "eps = 0.06"),
        # An added line.
        lambda t: t.replace(
            "        return st.wires", "        print(1)\n        return st.wires"
        ),
        # A comment, even.
        lambda t: t.replace("class Builder", "# mine\nclass Builder"),
        # Whitespace at the end of the code.
        lambda t: t.replace("return st.wires", "return st.wires "),
    ],
)
def test_a_hand_edit_is_detected_and_the_saved_blocks_offered(edit):
    tree = template("dipole")
    text = cg.generate(tree)
    edited = edit(text)
    assert edited != text
    with pytest.raises(cg.HandEditedError) as info:
        cg.reopen(edited)
    # The editor can offer "open the blocks as they were saved".
    assert info.value.tree == tree


def test_an_edited_trailer_is_a_hand_edit_too():
    tree = template("dipole")
    text = cg.generate(tree)
    other = template("dipole")
    other["params"][1]["value"] = 0.95
    forged = text.rsplit("\n", 2)[0] + "\n" + cg.trailer(other) + "\n"
    with pytest.raises(cg.HandEditedError):
        cg.reopen(forged)


def test_reopen_never_runs_the_file(monkeypatch):
    """Only the trailer is decoded; the code is compared as text."""
    import builtins

    def refuse(*_a, **_k):
        raise AssertionError("reopen executed or compiled the file")

    tree = template("hentenna")
    text = cg.generate(tree)
    for name in ("exec", "eval", "compile"):
        monkeypatch.setattr(builtins, name, refuse)
    assert cg.reopen(text) == tree
    with pytest.raises(cg.HandEditedError):
        cg.reopen(text.replace("st = TransformStack()", "import os"))


@pytest.mark.parametrize(
    "text",
    [
        "print('hello')\n",
        "",
        "x = 1\n# antennaknobs-blocks: v1 !!!not-base64!!!\n",
        "x = 1\n# antennaknobs-blocks: v1 "
        + base64.b64encode(b"not json").decode()
        + "\n",
        "x = 1\n# antennaknobs-blocks: v1 "
        + base64.b64encode(b'{"block": "design"}').decode()
        + "\n",
    ],
)
def test_a_file_without_a_good_trailer_is_not_a_blocks_file(text):
    with pytest.raises(cg.NotABlocksFileError):
        cg.reopen(text)


def test_the_generated_file_is_house_style_python():
    text = cg.generate_code(template("hentenna"))
    assert "with st.push_pop_tr(Transform.translate(0, 0, self.base)):" in text
    assert "A = (0, wavelength * self.width_factor / 2, 0)" in text
    assert (
        "B = (\n                0,\n                wavelength * self.width_factor / 2,\n"
        in text
    )
    assert "C = (A[0], -A[1], A[2])" in text
    assert "st.path([D, B], ex=1 + 0j)" in text
    assert "eval" not in text and "exec" not in text
    dipole = cg.generate_code(template("dipole"))
    assert "for side in (Transform(), Transform.mirrorXZ()):" in dipole
    assert "st.wire_y(-eps, eps, ex=1 + 0j)" in dipole
