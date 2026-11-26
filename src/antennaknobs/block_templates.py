"""Starting points for the block builder: block programs (plain JSON data)
written to generate code close to their catalog twins
(docs/design/block-builder.md, "Round trip"), not imports of the catalog.

=========  =================================  ===============================
template   catalog twin                       how close
=========  =================================  ===============================
dipole     ``dipoles.invvee:dipole``          same wires to an ulp; the arms
                                              are one arm and its mirror, so
                                              one runs the other way
invvee     ``dipoles.invvee``                 the twin's own arithmetic, bit
                                              for bit
hentenna   ``specialty.hentenna``             the twin's own arithmetic, bit
                                              for bit
=========  =================================  ===============================

``tests/test_block_templates.py`` holds each to its twin's impedance.
"""

from __future__ import annotations

import copy

_DIPOLE = {
    "block": "design",
    "schema": 1,
    "name": "Dipole",
    "freq_mhz": 28.47,
    "params": [
        {"name": "base", "value": 7.0, "unit": "m", "min": 1.0, "max": 16.0},
        {"name": "length_factor", "value": 0.967, "unit": "", "min": 0.8, "max": 1.25},
    ],
    "body": [
        {"block": "let", "id": "gap", "name": "eps", "value": 0.05},
        {
            "block": "let",
            "id": "arm",
            "name": "arm",
            "value": "0.25 * λ * length_factor",
        },
        {
            "block": "move",
            "id": "mast",
            "by": [0, 0, {"ref": "base"}],
            "body": [
                {
                    "block": "both_sides",
                    "id": "arms",
                    "across": "xz",
                    "body": [{"block": "wire_y", "from": "eps", "to": "arm"}],
                },
                {
                    "block": "wire_y",
                    "id": "feed",
                    "from": "-eps",
                    "to": "eps",
                    "feed": "centre",
                },
            ],
        },
    ],
}

_INVVEE = {
    "block": "design",
    "schema": 1,
    "name": "Inverted vee",
    "freq_mhz": 28.47,
    "params": [
        {"name": "base", "value": 7.0, "unit": "m", "min": 1.0, "max": 16.0},
        {"name": "length_factor", "value": 0.9719, "unit": "", "min": 0.8, "max": 1.25},
        {"name": "angle_deg", "value": 31.6846, "unit": "°", "min": 0.0, "max": 60.0},
    ],
    "body": [
        {"block": "let", "name": "eps", "value": 0.05},
        {"block": "let", "name": "driver_y", "value": "0.25 * λ * length_factor"},
        {"block": "let", "name": "z_sin", "value": "sin(angle_deg)"},
        {"block": "let", "name": "y_cos", "value": "cos(angle_deg)"},
        {"block": "point", "name": "S", "at": [0, "eps", "base"]},
        {
            "block": "point",
            "name": "A",
            "at": [
                0,
                "eps + (driver_y - eps) * y_cos",
                "base - (driver_y - eps) * z_sin",
            ],
        },
        {"block": "mirror_point", "name": "D", "of": "A", "across": "xz"},
        {"block": "mirror_point", "name": "T", "of": "S", "across": "xz"},
        {"block": "wire", "id": "arm+", "from": "S", "to": "A"},
        {"block": "wire", "id": "arm-", "from": "D", "to": "T"},
        {"block": "wire", "id": "feed", "from": "T", "to": "S", "feed": "centre"},
    ],
}

_HENTENNA = {
    "block": "design",
    "schema": 1,
    "name": "Hentenna",
    "freq_mhz": 28.47,
    "params": [
        {"name": "base", "value": 10.0, "unit": "m"},
        {"name": "top_height_factor", "value": 0.5081, "unit": "λ"},
        {"name": "mid_height_factor", "value": 0.1094, "unit": "λ"},
        {"name": "width_factor", "value": 0.1378, "unit": "λ"},
    ],
    "body": [
        {
            "block": "move",
            "id": "mast",
            "by": [0, 0, {"ref": "base"}],
            "body": [
                {
                    "block": "point",
                    "name": "B",
                    "at": [
                        0,
                        "λ * width_factor / 2",
                        "λ * (mid_height_factor - top_height_factor)",
                    ],
                },
                {"block": "point", "name": "A", "at": [0, "λ * width_factor / 2", 0]},
                {
                    "block": "point",
                    "name": "F",
                    "at": [0, "λ * width_factor / 2", "λ * -top_height_factor"],
                },
                {"block": "mirror_point", "name": "C", "of": "A", "across": "xz"},
                {"block": "mirror_point", "name": "D", "of": "B", "across": "xz"},
                {"block": "mirror_point", "name": "E", "of": "F", "across": "xz"},
                {"block": "path", "id": "top", "points": ["B", "A", "C", "D"]},
                {"block": "path", "id": "bottom", "points": ["B", "F", "E", "D"]},
                {
                    "block": "path",
                    "id": "feed",
                    "points": ["D", "B"],
                    "feed_segment": 0,
                },
            ],
        }
    ],
}

_TEMPLATES = {"dipole": _DIPOLE, "invvee": _INVVEE, "hentenna": _HENTENNA}

NAMES = tuple(_TEMPLATES)


def template(name) -> dict:
    """A fresh copy of the named template's block program."""
    if name not in _TEMPLATES:
        raise KeyError(f"no block template {name!r}; there are {', '.join(NAMES)}")
    return copy.deepcopy(_TEMPLATES[name])
