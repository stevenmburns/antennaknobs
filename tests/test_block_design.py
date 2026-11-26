"""The block interpreter: structured errors, the Q2 frame rule, the run
bounds, and the hand-off to the normal pipeline."""

from __future__ import annotations

import copy

import pytest

from antennaknobs import Wire
from antennaknobs.block_design import (
    MAX_REPEAT_COUNT,
    MAX_NESTING,
    MAX_REPEAT_NESTING,
    MAX_STEPS,
    MAX_WIRES,
    BlockError,
    BlockProgramError,
    blocks_builder,
    compile_program,
)
from antennaknobs.block_templates import template
from antennaknobs.wire_catalog import WIRES


def design(*body, params=()):
    return {
        "block": "design",
        "name": "test",
        "freq_mhz": 14.2,
        "params": list(params),
        "body": list(body),
    }


def errors(tree):
    with pytest.raises(BlockProgramError) as info:
        compile_program(tree)
    return info.value.as_dicts()


def run_error(tree):
    with pytest.raises(BlockError) as info:
        blocks_builder(tree)().build_wires()
    return info.value.as_dict()


def wires(tree, **params):
    cls = blocks_builder(tree)
    return cls({**cls.default_params, **params}).build_wires()


def test_output_is_the_build_wires_contract():
    ws = wires(template("dipole"))
    assert all(isinstance(w, Wire) for w in ws)
    # auto_mesh ran: counts resolved at the design density.
    assert all(isinstance(w.n_seg, int) and w.n_seg >= 1 for w in ws)
    assert sum(w.ex is not None for w in ws) == 1


def test_knobs_are_the_params_with_their_ranges():
    cls = blocks_builder(template("invvee"))
    d = cls.default_params
    assert d["design_freq"] == d["freq"] == 28.47
    assert d["length_factor"] == 0.9719
    assert dict(d["ui_params"]["angle_deg"]) == {"min": 0.0, "max": 60.0}
    # A knob moves the geometry.
    a = wires(template("invvee"))
    b = wires(template("invvee"), angle_deg=0.0)
    assert a[0].p1 != b[0].p1


def test_errors_name_their_block_by_id_or_pointer():
    tree = design(
        {"block": "let", "id": "mine", "name": "x", "value": "nope + 1"},
        {"block": "move", "by": [0, 0, 1], "body": [{"block": "spiral"}]},
        {"block": "wire_x", "from": 0, "to": 1, "feed": "end"},
    )
    errs = errors(tree)
    assert errs == [
        {"block_id": "mine", "message": "value: no param or let is named 'nope'"},
        {
            "block_id": "/body/1/body/0",
            "message": "'spiral' is not a block; the blocks are design, both_sides, "
            "let, loop, mirror, mirror_point, move, path, point, repeat, rotate, "
            "wire, wire_x, wire_y, wire_z, with_wire",
        },
        {
            "block_id": "/body/2",
            "message": "feed: 'centre' is the only feed position in v1",
        },
    ]


def test_unknown_and_missing_fields_are_refused():
    errs = errors(design({"block": "wire_x", "from": 0, "colour": "red"}))
    assert {"block_id": "/body/0", "message": "missing 'to'"} in errs
    assert {
        "block_id": "/body/0",
        "message": "'colour' is not a field of this block",
    } in errs


def test_names_are_checked_once_for_the_whole_program():
    errs = errors(
        design(
            {"block": "let", "name": "x", "value": 1},
            {"block": "let", "name": "x", "value": 2},
            {"block": "let", "name": "range", "value": 1},
            {"block": "let", "name": "st", "value": 1},
            {"block": "let", "name": "self", "value": 1},
            {"block": "let", "name": "freq", "value": 1},
            {"block": "let", "name": "draw", "value": 1},
            {"block": "let", "name": "_x", "value": 1},
            {"block": "let", "name": "a.b", "value": 1},
            params=[{"name": "class", "value": 1}],
        )
    )
    msgs = [e["message"] for e in errs]
    assert "'class' is a reserved name; choose another" in msgs
    assert any("already the name of block /body/0" in m for m in msgs)
    for reserved in ("range", "st", "self", "freq", "draw"):
        assert f"{reserved!r} is a reserved name; choose another" in msgs
    assert sum("is not a let name" in m for m in msgs) == 2


def test_the_design_name_cannot_break_out_of_its_comment():
    # The name is the only free text in the generated file, as a comment.
    for name in ("x\nimport os", "x\rimport os", "x y", "x\x00", ""):
        tree = design()
        tree["name"] = name
        assert any(e["message"].startswith("name:") for e in errors(tree))


def test_joins_stay_inside_one_transform_block():
    """Q2 (Steve, 2026-11-24): a point is a position in its own block's
    frame, so a wire in another transform block cannot use it."""
    outer = {"block": "point", "name": "A", "at": [0, 0, 0]}
    errs = errors(
        design(
            outer,
            {
                "block": "move",
                "id": "lift",
                "by": [0, 0, 1],
                "body": [{"block": "wire", "id": "w", "from": "A", "to": [1, 0, 0]}],
            },
        )
    )
    assert errs == [
        {
            "block_id": "w",
            "message": "from: point 'A' was made in another transform block "
            "(/body/0); a wire joins only points made in its own block",
        }
    ]
    # with_wire and a repeat with no `each` keep the frame, so they may.
    ok = design(
        outer,
        {
            "block": "with_wire",
            "spec": "14-awg",
            "body": [
                {
                    "block": "repeat",
                    "count": 2,
                    "body": [{"block": "wire", "from": "A", "to": [1, 0, "i + 1"]}],
                }
            ],
        },
    )
    ws = wires(ok)
    assert [w.p1 for w in ws] == [(1, 0, 1), (1, 0, 2)]
    assert all(w.spec is WIRES["14-awg"] for w in ws)
    # A point made inside a block is not seen after it.
    errs = errors(
        design(
            {
                "block": "move",
                "by": [0, 0, 1],
                "body": [{"block": "point", "name": "B", "at": [0, 0, 0]}],
            },
            {"block": "wire", "from": "B", "to": [1, 0, 0]},
        )
    )
    assert errs[0]["message"] == "from: no point is named 'B' here"


def test_lets_are_values_and_cross_transform_blocks():
    tree = design(
        {"block": "let", "name": "h", "value": "2 * top"},
        {
            "block": "move",
            "by": [0, 0, "h"],
            "body": [{"block": "wire_x", "from": 0, "to": "h"}],
        },
        params=[{"name": "top", "value": 3}],
    )
    (w,) = wires(tree)
    assert w.p0 == (0, 0, 6) and w.p1 == (6, 0, 6)


def test_both_sides_and_mirror_point_reflect_across_the_named_plane():
    tree = design(
        {"block": "point", "name": "P", "at": [1, 2, 3]},
        {"block": "mirror_point", "name": "Q", "of": "P", "across": "yz"},
        {"block": "wire", "from": "P", "to": "Q"},
        {
            "block": "both_sides",
            "across": "xy",
            "body": [{"block": "wire_z", "from": 1, "to": 2}],
        },
    )
    a, b, c = wires(tree)
    assert a.p1 == (-1, 2, 3)
    assert (b.p0[2], b.p1[2]) == (1, 2)
    assert (c.p0[2], c.p1[2]) == (-1, -2)


def test_repeat_each_rotates_per_pass():
    tree = design(
        {
            "block": "repeat",
            "count": 4,
            "var": "k",
            "each": {"rotate": {"axis": "z", "deg": "90 * k"}},
            "body": [{"block": "wire_x", "from": 0, "to": 1}],
        }
    )
    ends = [tuple(round(float(c), 12) for c in w.p1) for w in wires(tree)]
    assert ends == [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)]


def test_loop_counts_and_nesting_are_bounded():
    big = design({"block": "repeat", "count": MAX_REPEAT_COUNT + 1, "body": []})
    assert "count: a whole number" in errors(big)[0]["message"]
    frac = design({"block": "repeat", "count": 2.5, "body": []})
    assert "count: a whole number" in errors(frac)[0]["message"]
    # A count from a knob is checked when it runs.
    knob = design(
        {"block": "repeat", "id": "r", "count": "n", "body": []},
        params=[{"name": "n", "value": 3}],
    )
    cls = blocks_builder(knob)
    cls({**cls.default_params, "n": 3}).build_wires()
    with pytest.raises(BlockError, match="count is 3.5"):
        cls({**cls.default_params, "n": 3.5}).build_wires()
    with pytest.raises(BlockError, match="count is 1000"):
        cls({**cls.default_params, "n": 1000}).build_wires()

    nested = {"block": "wire_x", "from": 0, "to": 1}
    for depth in range(MAX_REPEAT_NESTING + 1):
        nested = {"block": "repeat", "var": f"i{depth}", "count": 1, "body": [nested]}
    assert any("nest at most" in e["message"] for e in errors(design(nested)))


# Each body block, its cost toward MAX_NESTING, and a one-level wrapper.
_WRAPS = {
    "move": (1, lambda b: {"block": "move", "by": [1, 0, 0], "body": b}),
    "rotate": (1, lambda b: {"block": "rotate", "axis": "z", "deg": 10, "body": b}),
    "mirror": (1, lambda b: {"block": "mirror", "across": "yz", "body": b}),
    "with_wire": (1, lambda b: {"block": "with_wire", "spec": "14-awg", "body": b}),
    "both_sides": (3, lambda b: {"block": "both_sides", "across": "xz", "body": b}),
    "repeat": (2, lambda b: {"block": "repeat", "count": 1, "body": b}),
    "repeat_each": (
        3,
        lambda b: {
            "block": "repeat",
            "count": 1,
            "each": {"move": [0, 0, 1]},
            "body": b,
        },
    ),
}


def _nest(kind, levels):
    cost, wrap = _WRAPS[kind]
    body = [{"block": "wire_z", "from": 0, "to": 1}]
    for i in range(levels):
        b = wrap(body)
        if b["block"] == "repeat":
            b["var"] = f"i{i}"
        body = [b]
    return design(*body), cost * levels


@pytest.mark.parametrize("kind", sorted(_WRAPS))
def test_nesting_is_capped_where_the_exported_python_still_compiles(kind):
    from antennaknobs.block_codegen import generate

    cost = _WRAPS[kind][0]
    deepest = MAX_NESTING // cost
    if kind.startswith("repeat"):
        deepest = min(deepest, MAX_REPEAT_NESTING)
    ok, _ = _nest(kind, deepest)
    blocks_builder(ok)().build_wires()
    compile(generate(ok), "<generated>", "exec")
    if kind.startswith("repeat") and deepest == MAX_REPEAT_NESTING:
        return  # the repeat cap is the one that binds; tested above
    over, total = _nest(kind, deepest + 1)
    assert total > MAX_NESTING
    assert any("blocks nest at most" in e["message"] for e in errors(over))


def test_a_mixed_nest_counts_every_level():
    body = [{"block": "wire_z", "from": 0, "to": 1}]
    # 3 + 1 + 3 + 1 + 3 = 11, then one move more is 12 (allowed), two is 13.
    for kind in ("both_sides", "move", "repeat_each", "rotate", "both_sides"):
        body = [_WRAPS[kind][1](body)]
    from antennaknobs.block_codegen import generate

    at_cap = design(_WRAPS["move"][1](body))
    compile(generate(at_cap), "<generated>", "exec")
    over = design(_WRAPS["move"][1]([_WRAPS["move"][1](body)]))
    assert any("blocks nest at most" in e["message"] for e in errors(over))


def test_a_very_deep_program_is_a_block_error_not_a_recursion_error():
    body = [{"block": "wire_z", "from": 0, "to": 1}]
    for _ in range(5000):
        body = [{"block": "move", "by": [0, 0, 0], "body": body}]
    errs = errors(design(*body))
    assert len(errs) == 1
    assert errs[0]["block_id"].count("/body/") == MAX_NESTING + 1


def test_a_file_too_deep_or_with_a_huge_literal_is_refused_by_name(tmp_path):
    from antennaknobs.block_design import load_tree

    deep = tmp_path / "deep.json"
    deep.write_text("[" * 100_000 + "]" * 100_000)
    with pytest.raises(SystemExit, match="nested too deep"):
        load_tree(deep)
    huge = tmp_path / "huge.json"
    huge.write_text('{"block": "design", "freq_mhz": ' + "1" * 5000 + "}")
    with pytest.raises(SystemExit, match="not JSON"):
        load_tree(huge)


def test_both_sides_and_repeat_share_their_seams_exactly():
    # Four sides by a rotation each pass: cos(90°) is not exactly 0, so the
    # raw corners differ in the last bits. Q2: the repeat shares them.
    square = design(
        {
            "block": "repeat",
            "var": "k",
            "count": 4,
            "each": {"rotate": {"axis": "z", "deg": "90 * k"}},
            "body": [{"block": "wire_y", "from": -1.37, "to": 1.37, "x": 1.37}],
        }
    )
    ws = wires(square)
    # The seams were real: some corner is off ±1.37 in its last bits.
    assert {abs(float(c)) for w in ws for c in w.p1[:2]} != {1.37}
    for a, b in zip(ws, ws[1:] + ws[:1], strict=True):
        assert a.p1 == b.p0
    # A rotated half, mirrored across YZ: its inner end (1, 0, 0) lands at
    # x = cos(90°), about 6e-17, and its mirror at -6e-17. Both sides make
    # them one point; the outer end lands at x = -1 and stays apart.
    half = design(
        {
            "block": "both_sides",
            "across": "yz",
            "body": [
                {
                    "block": "rotate",
                    "axis": "z",
                    "deg": 90,
                    "body": [{"block": "wire_y", "from": 0, "to": 1, "x": 1}],
                }
            ],
        }
    )
    first, mirrored = wires(half)
    assert float(first.p0[0]) != 0.0
    assert mirrored.p0 == first.p0
    assert mirrored.p1 != first.p1  # the far ends stay apart


def test_a_run_is_bounded_in_wires_and_steps():
    many = design(
        {
            "block": "repeat",
            "var": "i",
            "count": MAX_REPEAT_COUNT,
            "body": [
                {
                    "block": "repeat",
                    "var": "j",
                    "count": MAX_REPEAT_COUNT,
                    "body": [
                        {
                            "block": "wire_x",
                            "id": "w",
                            "from": "j",
                            "to": "j + 1",
                            "y": "i",
                        }
                    ],
                }
            ],
        }
    )
    assert run_error(many) == {
        "block_id": "w",
        "message": f"the design has more than {MAX_WIRES} wires",
    }
    # Nothing emitted, but 256**3 passes: the step cap stops it.
    idle = {"block": "let", "name": "z", "value": 1}
    for name in ("a", "b", "c"):
        idle = {
            "block": "repeat",
            "var": name,
            "count": MAX_REPEAT_COUNT,
            "body": [idle],
        }
    assert (
        run_error(design(idle))["message"]
        == f"the design runs more than {MAX_STEPS} steps"
    )


def test_runtime_refusals_name_the_block():
    tree = design(
        {"block": "wire_x", "id": "flat", "from": "a", "to": "a"},
        params=[{"name": "a", "value": 1.0}],
    )
    assert run_error(tree) == {
        "block_id": "flat",
        "message": "the wire starts and ends at the same point",
    }
    sq = design(
        {"block": "wire_x", "id": "s", "from": 0, "to": "sqrt(a)"},
        params=[{"name": "a", "value": -1.0}],
    )
    assert run_error(sq) == {
        "block_id": "s",
        "message": "sqrt of a negative number (-1)",
    }


def test_the_pipeline_refuses_a_degenerate_wire_after_the_interpreter():
    # The interpreter hands its wires to the same engine checks as any design.
    from antennaknobs.engines.momwire import MomwireEngine

    tree = design({"block": "wire_x", "from": 0, "to": 1e-12, "feed": "centre"})
    with pytest.raises(ValueError, match="segment"):
        MomwireEngine(blocks_builder(tree)(), ground="free").impedance()


def test_a_program_is_data_the_tree_is_not_mutated():
    tree = template("hentenna")
    before = copy.deepcopy(tree)
    wires(tree)
    assert tree == before


def test_ids_and_schema_are_checked():
    tree = design({"block": "let", "id": 7, "name": "x", "value": 1})
    tree["schema"] = 2
    msgs = [e["message"] for e in errors(tree)]
    assert "schema 2 is not 1, the one this reads" in msgs
    assert "id: a string of 1 to 64 characters" in msgs
