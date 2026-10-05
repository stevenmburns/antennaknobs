"""AK#1895: keeping a cell that turned off a deck's default-on kernel says so.

A deck read as NEC-4 or NEC-5 (AK#1891), or a NEC-2 deck with an EK card
(AK#1893), solves with the extended kernel unless told otherwise, on the web
and in a run alike. A kept request with ``extended_kernel: false`` has no
``--engine`` spelling for that, so `keep` used to drop it and the run solved
EK-on: a different Z from the one kept. Now the keep notes
``--no-extended-kernel``, and the gate follows the note: the run reproduces
the web's Z, and without the flag it does not.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from test_ek_by_dialect_1891 import (
    _cell,
    _payload,
    _text,
    _z_table,
    client,  # noqa: F401 — the fixture, used by name below
)

import antennaknobs as ant
from antennaknobs import keep

_FLAG = "--no-extended-kernel"


def _kept(client, text: str, model_options: dict | None):  # noqa: F811 — the imported fixture
    opened = client.post("/deck", json=_payload(text)).json()
    assert opened["example"]["extended_kernel_default"] is True
    body = {
        "geometry": opened["key"],
        "solver": "momwire",
        "momwire_model": "bspline",
        "n_per_wire": 40,
        "ground": False,
        "design_freq_mhz": 28.0,
        "measurement_freq_mhz": 28.0,
    }
    if model_options is not None:
        body["model_options"] = model_options
    solve = _cell(client, opened["key"], **body)
    z = complex(solve["z_in_re"], solve["z_in_im"])
    pin = {"req": body}
    _a, _form, _origin, notes = keep.build({"origin": "pattern pins", "pins": [pin]})
    cell = keep.pin_cell(pin, swept=None, who="pin 1", notes=[])
    return z, cell, notes


def _run_z(tmp_path, capsys, text: str, cell, *extra) -> complex:
    path = tmp_path / "d.nec"
    path.write_text(text)
    try:
        ant.cli(
            ["sweep", "--builder", f"@{path}", "--engine", cell.engine,
             "--ground", cell.ground, "--npoints", "1", "--range", "28", "28",
             "--fn", "/dev/null", *extra]
        )  # fmt: skip
    finally:
        plt.close("all")
    return _z_table(capsys.readouterr().out)


def test_a_kept_nec5_deck_with_ek_off_says_so_and_the_run_reproduces_it(
    client,  # noqa: F811 — the imported fixture
    tmp_path,
    capsys,
):
    # The fat NEC-5 dipole (Δ/a ≈ 4.5), where the two kernels part by ohms.
    text = _text("nec5", a=0.05)
    z_web, cell, notes = _kept(client, text, {"extended_kernel": False})
    (note,) = [n for n in notes if _FLAG in n]
    assert "extended kernel off" in note
    assert cell.engine == "momwire:bspline"
    followed = _run_z(tmp_path, capsys, text, cell, _FLAG)
    # To the sweep table's printed precision (two to three decimals).
    assert abs(followed - z_web) < 5e-3, (followed, z_web)
    # Adversarial: the run left alone takes the deck's default, another Z.
    ignored = _run_z(tmp_path, capsys, text, cell)
    assert abs(ignored - z_web) > 0.1, (ignored, z_web)


@pytest.mark.parametrize(
    ("dialect", "ek", "model_options"),
    [
        ("nec5", "", None),
        ("nec5", "", {"extended_kernel": True}),
        ("nec2", "EK\n", None),
    ],
    ids=["nec5-default", "nec5-on", "nec2-ek-card-default"],
)
def test_a_kept_default_kernel_needs_no_note(
    dialect,
    ek,
    model_options,
    client,  # noqa: F811 — the imported fixture
):
    _z, _cell, notes = _kept(client, _text(dialect, ek=ek), model_options)
    assert not [n for n in notes if "kernel" in n], notes


def test_a_kept_nec2_ek_card_turned_off_says_so(client):  # noqa: F811 — the imported fixture
    _z, _cell, notes = _kept(
        client, _text("nec2", ek="EK\n"), {"extended_kernel": False}
    )
    assert [n for n in notes if _FLAG in n], notes
