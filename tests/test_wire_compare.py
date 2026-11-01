"""`wire_compare` and the CLI's `compare_wires`: two wire lists are the same
metal when only order, direction, segmentation or how a run is split differ."""

import pytest

from antennaknobs.cli import cli
from antennaknobs.wire_catalog import Wire
from antennaknobs.wire_compare import compare_wires, format_diff, with_params

L = [Wire((0, 0, 0), (2, 0, 0), ex=1 + 0j), Wire((2, 0, 0), (2, 1, 0))]


def test_order_direction_segments_and_tuples_are_ignored():
    right = [((2, 1, 0), (2, 0, 0), 7, None), Wire((2, 0, 0), (0, 0, 0), 31, 1 + 0j)]
    assert compare_wires(L, right).same


def test_a_run_split_into_pieces_is_the_same_metal():
    # The feed moves with the split, to the piece whose midpoint is the run's.
    right = [
        Wire((0, 0, 0), (0.9, 0, 0)),
        Wire((0.9, 0, 0), (1.1, 0, 0), ex=1 + 0j),
        Wire((1.1, 0, 0), (2, 0, 0)),
        Wire((2, 1, 0), (2, 0.4, 0)),
        Wire((2, 0.4, 0), (2, 0, 0)),
    ]
    assert compare_wires(L, right).same


def test_an_extra_wire_and_a_duplicate_are_reported():
    diff = compare_wires(
        L, [*L, Wire((2, 0, 0), (2, 1, 0)), Wire((2, 1, 0), (3, 1, 0))]
    )
    assert not diff.same
    assert sorted(diff.only_right) == [((2, 0, 0), (2, 1, 0)), ((2, 1, 0), (3, 1, 0))]
    assert diff.only_left == []


def test_a_moved_feed_is_reported_on_both_sides():
    right = [Wire((0, 0, 0), (2, 0, 0)), Wire((2, 0, 0), (2, 1, 0), ex=1 + 0j)]
    diff = compare_wires(L, right)
    assert diff.only_left == diff.only_right == []
    assert diff.feeds_left == [(1.0, 0.0, 0.0)]
    assert diff.feeds_right == [(2.0, 0.5, 0.0)]


def test_a_near_miss_differs_and_is_named_and_tol_absorbs_it():
    right = [L[0], Wire((2, 0, 0), (2, 1.00005, 0))]
    diff = compare_wires(L, right)
    assert not diff.same
    assert [round(d, 9) for *_, d in diff.near_misses] == [5e-5]
    assert any("close but not the same" in line for line in format_diff(diff))
    assert compare_wires(L, right, tol=1e-4).same


def test_with_params_starts_from_the_defaults():
    from antennaknobs.designs.dipoles.invvee import Builder

    b = with_params(Builder, angle_deg=40.0)
    assert b.angle_deg == 40.0
    assert b.base == Builder.default_params["base"]


def _run(argv):
    try:
        cli(argv)
    except SystemExit as e:
        return e.code
    return 0


def test_cli_exit_codes(capsys):
    assert _run(["compare_wires", "dipoles.invvee", "dipoles.invvee"]) == 0
    assert "(left) and dipoles.invvee (right): same" in capsys.readouterr().out

    # The bridge-fed vee against the apex-fed one: different metal.
    assert _run(["compare_wires", "dipoles.invvee", "dipoles.invvee_apex"]) == 1
    out = capsys.readouterr().out
    assert "only in dipoles.invvee:" in out and "only in dipoles.invvee_apex:" in out

    argv = ["compare_wires", "dipoles.invvee", "dipoles.invvee"]
    assert _run([*argv, "--set-right", "angle_deg=40"]) == 1
    assert _run([*argv, "--set", "angle_deg=40"]) == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["compare_wires", "dipoles.invvee", "dipoles.invvee", "--set", "bogus=1"],
        ["compare_wires", "nosuch.design", "dipoles.invvee"],
    ],
)
def test_cli_a_usage_error_exits_2_not_1(argv, capsys):
    assert _run(argv) == 2
