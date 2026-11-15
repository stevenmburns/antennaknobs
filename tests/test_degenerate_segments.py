"""A wire whose segments no engine can mesh is refused by name, before any
engine sees it.

Measured on main 2026-11-15, before the refusal: a 2-segment wire 2.3e-162 m
long (its ends differ) over Sommerfeld ground ABORTED the process on OpenNEC
(SIGABRT on an assert in its ground integration, the segment length having come
out NaN) and HUNG PyNEC; over free space, PEC and reflection-coefficient ground
both returned NaN Z with no word. A wire from z = 1 to the next double above 1
did the same with nseg = 2 and 3 (a knot rounds onto an end). momwire refused
both, but only through its node quantum, which a longer wire cut finer passes.

The refusal is `wire_catalog.refuse_degenerate_segments`, run by
`SimulationEngine._coerce_wire_tuples`, which every engine builds its geometry
from; the importer refuses a coordinate that is not finite itself, by wire,
because its own snap arithmetic would fail on one first.

The engine cases run in a SUBPROCESS with a timeout, one per engine and case:
a regression here aborts or hangs, and must not take the test runner with it.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import textwrap

import pytest

from antennaknobs.engines import opennec as opennec_mod
from antennaknobs.engines import pynec as pynec_mod
from antennaknobs.wire_catalog import (
    SEGMENT_LENGTH_FLOOR_M,
    Wire,
    WireSpec,
    degenerate_wire_refusal,
    graded_wire,
    refuse_degenerate_segments,
)

_ONE_UP = math.nextafter(1.0, 2.0)

# name -> (p0, p1, n_seg, radius, the refusal's words)
CASES = {
    "subnormal": (
        (0.0, 0.0, 1.0),
        (2.3e-162, 0.0, 1.0),
        2,
        1e-170,
        r"its 2 segments would each be 1\.11e-162 m long, under the 1e-09 m",
    ),
    "nextafter2": (
        (0.0, 0.0, 1.0),
        (0.0, 0.0, _ONE_UP),
        2,
        1e-3,
        r"its 2 segments would each be 1\.11e-16 m long, under the 1e-09 m",
    ),
    "nextafter3": (
        (0.0, 0.0, 1.0),
        (0.0, 0.0, _ONE_UP),
        3,
        1e-3,
        r"its 3 segments would each be 7\.4e-17 m long, under the 1e-09 m",
    ),
    "nan": (
        (0.0, 0.0, 1.0),
        (float("nan"), 0.0, 6.0),
        3,
        1e-3,
        r"wire 1\b.*its end p1 is \(nan, 0, 6\); every coordinate must be a finite",
    ),
}

ENGINES = {
    "momwire": True,
    "pynec": pynec_mod.nec is not None,
    "opennec": opennec_mod.porty is not None,
}

# Runs in the child: every ground, through an opened deck and a Python design,
# one line per solve. A refusal prints REFUSED and the message; anything else
# (a result, NaN or not) prints RESULT, and an abort or a hang ends the child.
_CHILD = textwrap.dedent(
    """
    import json, sys, warnings
    from types import MappingProxyType

    warnings.simplefilter("ignore")
    engine, p0, p1, n, r = json.loads(sys.argv[1])
    p0 = tuple(float(c) for c in p0)
    p1 = tuple(float(c) for c in p1)

    from antennaknobs import AntennaBuilder
    from antennaknobs.file_designs import builder_from_text

    grounds = {
        "free": (None, "GE 0\\n"),
        "pec": ("pec", "GE 1\\nGN 1\\n"),
        "refl": (("finite-fast", 10.0, 0.01), "GE 1\\nGN 0 0 0 0 10 0.01\\n"),
        "somm": (("finite", 10.0, 0.01), "GE 1\\nGN 2 0 0 0 10 0.01\\n"),
    }

    class Design(AntennaBuilder):
        label = "degenerate"
        default_params = MappingProxyType({"freq": 14.0})

        def build_wires(self):
            return [(p0, p1, n, 1 + 0j)]

        def build_wire_material(self):
            from antennaknobs.wire_catalog import WireSpec

            return WireSpec(radius=r)

    if engine == "momwire":
        from antennaknobs.engines.momwire import MomwireEngine as Engine
    elif engine == "pynec":
        from antennaknobs.engines.pynec import PyNECEngine as Engine
    else:
        from antennaknobs.engines.opennec import OpenNECEngine as Engine

    def card(x):
        return "NAN" if x != x else repr(x)

    for gname, (ground, cards) in grounds.items():
        for path in ("deck", "py"):
            try:
                if path == "deck":
                    text = (
                        "CM degenerate\\nCE\\n"
                        f"GW 1 {n} {' '.join(card(c) for c in (*p0, *p1))} "
                        f"{card(r)}\\n{cards}EX 0 1 1 0 1 0\\nFR 0 1 0 0 14 0\\nEN\\n"
                    )
                    builder = builder_from_text("degenerate.nec", text)()
                else:
                    builder = Design()
                z = Engine(builder, ground=ground).impedance()
                print("ROW", gname, path, "RESULT", z, flush=True)
            except ValueError as e:
                print("ROW", gname, path, "REFUSED", e, flush=True)
    """
)


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_every_engine_refuses_by_name_and_survives(engine, case):
    if not ENGINES[engine]:
        pytest.skip(f"the {engine} engine is not installed")

    p0, p1, n, r, words = CASES[case]
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, json.dumps([engine, p0, p1, n, r])],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    rows = [
        line.split(" ", 4)
        for line in proc.stdout.splitlines()
        if line.startswith("ROW ")
    ]
    assert proc.returncode == 0, (
        f"{engine}/{case}: the child died with {proc.returncode} after "
        f"{len(rows)} of 8 solves\n{proc.stderr[-2000:]}"
    )
    assert len(rows) == 8, proc.stdout
    for _row, ground, path, status, message in rows:
        assert status == "REFUSED", f"{engine}/{case}/{ground}/{path}: {message}"
        assert re.search(words, message), message
        if path == "deck" and case != "nan":
            # The deck names the wire by its GW tag too.
            assert message.startswith("wire 1 (tag 1)"), message


# --------------------------------------------------------------------------
# the rule itself
# --------------------------------------------------------------------------


def test_a_segment_at_the_floor_passes_and_one_under_it_is_refused():
    p0 = (0.0, 0.0, 0.0)
    assert degenerate_wire_refusal("w", p0, (0.0, 0.0, 2e-9), 2) is None
    message = degenerate_wire_refusal("w", p0, (0.0, 0.0, 1.9e-9), 2)
    assert message.startswith("w: its 2 segments would each be 9.5e-10 m long")


def test_knots_floating_point_cannot_place_apart_are_refused():
    """Nominal segments above the floor, but at a coordinate of 1e8 m the
    knots of two ulps cut in three land on 0, 1, 1 and 2 ulps: the middle
    segment is zero long where the engines place it."""
    x = 1e8
    far = math.nextafter(math.nextafter(x, 2 * x), 2 * x)
    assert (far - x) / 3 > SEGMENT_LENGTH_FLOOR_M
    message = degenerate_wire_refusal("w", (x, 0.0, 0.0), (far, 0.0, 0.0), 3)
    assert message == (
        "w: segment 2 of 3 comes out 0 m long where its ends are placed, under "
        "the 1e-09 m a segment needs; at these coordinates floating point "
        "cannot place its ends apart"
    )
    # The same wire in two segments places its knots apart.
    assert degenerate_wire_refusal("w", (x, 0.0, 0.0), (far, 0.0, 0.0), 2) is None


def test_a_length_that_overflows_is_refused():
    message = degenerate_wire_refusal("w", (0.0, 0.0, 0.0), (1e200, 0.0, 0.0), 1)
    assert message == (
        "w: its length over 1 segment is not a finite number (inf m a segment); "
        "no engine can mesh it"
    )


def test_a_radius_that_is_not_finite_is_refused():
    wire = Wire((0, 0, 0), (0, 0, 5), 11, spec=WireSpec(radius=float("inf")))
    with pytest.raises(ValueError, match=r"^wire 1: its radius is inf; a radius"):
        refuse_degenerate_segments([wire])


def test_a_graded_wire_is_judged_panel_by_panel():
    ok = graded_wire((0, 0, 0), (0, 0, 10.0), toward="p0")
    refuse_degenerate_segments([ok])
    short = graded_wire((0, 0, 0), (0, 0, 10.0), toward="p0", h_node=1e-12)
    with pytest.raises(ValueError, match=r"^wire 1: its \d+ segments? would each be"):
        refuse_degenerate_segments([short])


def test_an_opened_deck_with_a_nan_coordinate_is_refused_by_wire():
    from antennaknobs.file_designs import builder_from_text

    text = (
        "CM t\nCE\nGW 1 3 0 0 1 0 0 6 1E-3\nGW 2 3 0 1 1 0 1 NAN 1E-3\n"
        "GE 0\nEX 0 1 2 0 1 0\nFR 0 1 0 0 14 0\nEN\n"
    )
    with pytest.raises(ValueError, match=r"^t\.nec: wire 2 \(tag 2\): its end p1 is"):
        builder_from_text("t.nec", text)


def test_the_catalog_is_far_above_the_floor():
    """The floor's justification, held: the shortest segment of any catalog
    design at its defaults (3.3 mm, the ELT whip, when this was written)."""
    from antennaknobs.engine import graded_panels
    from antennaknobs.web import server  # noqa: F401 — registers the catalog
    from antennaknobs.web.examples import REGISTRY
    from antennaknobs.wire_catalog import as_wire

    shortest = math.inf
    for name in REGISTRY:
        for t in REGISTRY.get(name).builder_cls().build_wires():
            for q0, q1, n in graded_panels(as_wire(t)):
                shortest = min(shortest, math.dist(q0, q1) / n)
    assert shortest > 1e6 * SEGMENT_LENGTH_FLOOR_M, shortest


def test_every_engine_class_builds_through_the_refusal(monkeypatch):
    """Instrumented: each engine's construction reaches
    `refuse_degenerate_segments` (through `_coerce_wire_tuples`) on an ordinary
    design. The external-binary engines are built without their binary."""
    from antennaknobs import engine as engine_mod
    from antennaknobs.designs.dipoles.invvee import Builder
    from antennaknobs.engines import nec2, nec5, nec42
    from antennaknobs.engines.momwire import MomwireEngine
    from antennaknobs.engines.opennec import OpenNECEngine
    from antennaknobs.engines.pynec import PyNECEngine

    calls = []
    real = engine_mod.refuse_degenerate_segments

    def counted(tups, labels=None):
        calls.append(len(tups))
        return real(tups, labels)

    monkeypatch.setattr(engine_mod, "refuse_degenerate_segments", counted)
    monkeypatch.setattr(nec2.NEC2Engine, "_resolve_exe", lambda self, exe: "nec2")
    monkeypatch.setattr(nec42.NEC42Engine, "_resolve_exe", lambda self, exe: "nec42")
    builds = {
        "momwire": lambda b: MomwireEngine(b),
        "pynec": lambda b: PyNECEngine(b),
        "opennec": lambda b: OpenNECEngine(b),
        "nec2": lambda b: nec2.NEC2Engine(b),
        "nec42": lambda b: nec42.NEC42Engine(b),
        "nec5": lambda b: nec5.NEC5Engine(b, require_exe=False),
    }
    for name, build in builds.items():
        before = len(calls)
        build(Builder())
        assert len(calls) > before, f"{name} built around the refusal"
