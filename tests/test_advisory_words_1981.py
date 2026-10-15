"""Plain-words summaries of momwire's advisories (AK#1981).

Every advisory here is composed by momwire's OWN code, never a copied
literal, so a rewording on the momwire side fails these tests instead of
quietly losing its summary.

Jeff G8HUL (groups.io antenna-research #1605) met the crossing advisory on a
vertical with a ground stake and could not read it. His deck is the
end-to-end case.
"""

from __future__ import annotations

import warnings

import pytest
from momwire import _crossing_fill, _razor_class, _surface_height
from momwire.razor import _RAZOR_NODE_LEVERS, _RAZOR_NODE_WORTH

from antennaknobs import advisory_words
from antennaknobs.cli import _GROUND_UNSET, make_engine_factory, resolve_ground
from antennaknobs.file_designs import builder_from_text

JARGON = ("n_qp_pair", "n_per_edge_per_wire", "momwire#", "wire 0", "VERTICES")

# Jeff's deck as posted, SY symbols and all.
G8HUL = """\
CM
CE
SY Len=20.1
SY Cp=2
GW 1 40 0 0 0 0 0 Len 0.001
GW 2 10 0 0 0 0 0 0-Cp 0.001
GW 99 1 10 10 10 10 10 10.1 0.001
GE -1
GN 3 0 0 0 13 0.005
EK
EX 0 99 1 0 1 0 0 'Source on the dummy line
NT 1 1 99 1 0.2 0 -1.4 0 9.8 0 '49:1 transformer
FR 0 0 0 0 7.2 0
EN
"""


def _crossing_text(arm, **kw) -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _crossing_fill.warn_coarse_node([arm], **kw)
    (w,) = [w for w in caught if w.category is _crossing_fill.CoarseCrossingNode]
    return str(w.message)


LEVEL = _crossing_fill.NodeArm(0.5025, 0.5025, 0, "start", "above")


@pytest.mark.parametrize(
    "kw",
    [{}, {"worth": _RAZOR_NODE_WORTH, "levers": _RAZOR_NODE_LEVERS}],
    ids=["bspline", "razor"],
)
def test_the_crossing_summary_says_where_how_long_and_what_to_do(kw):
    text = _crossing_text(LEVEL, **kw)
    got = advisory_words.summary(
        "CoarseCrossingNode", text, lambda w, e: (0.0, 0.0, 0.0)
    )
    assert got is not None
    assert "meets the ground at x = 0 m, y = 0 m" in got
    assert "wire above the ground" in got
    assert "0.50 m long" in got
    assert "Add segments" in got
    assert not any(j in got for j in JARGON)


def test_the_crossing_summary_does_not_offer_the_quadrature_lever():
    # On Jeff's deck the order moves X by 0.002 ohm and the mesh by 3.5 ohm
    # (AK#1981), so the plain advice is segments only.
    got = advisory_words.summary("CoarseCrossingNode", _crossing_text(LEVEL))
    assert "order" not in got.lower()
    assert "quadrature" not in got.lower()


def test_a_crossing_with_no_location_still_reads():
    got = advisory_words.summary("CoarseCrossingNode", _crossing_text(LEVEL))
    assert got.startswith("A wire meets the ground at a joint")


def test_a_short_mesh_reads_in_millimetres():
    arm = LEVEL._replace(h_resolved=0.04, h_adjacent=0.04)
    got = advisory_words.summary("CoarseCrossingNode", _crossing_text(arm))
    assert "40 mm long" in got


def test_a_sloping_arm_says_how_short_its_segments_may_go():
    # momwire#926: the stand-off floor forbids panels shorter than L_min.
    arm = LEVEL._replace(slope=0.2, h_floor=0.01)
    text = _crossing_text(arm)
    assert "L_min = 50.0 mm" in text
    got = advisory_words.summary("CoarseCrossingNode", text)
    assert "no segment there can be shorter than 50 mm" in got


@pytest.mark.parametrize(("n", "lead"), [(1, "A wire lies"), (4, "4 wires lie")])
def test_the_surface_height_summary(n, lead):
    text = _surface_height.surface_height_message(0.00105, 0.0005, n)
    got = advisory_words.summary("SurfaceRadialHeight", text)
    assert got.startswith(f"{lead} only 1.05 mm above the ground (2.1 wire radii)")
    assert "momwire" not in got


def test_the_far_mesh_summary():
    got = advisory_words.summary(
        "RazorFarMeshClass", _razor_class.far_mesh_class_message()
    )
    assert "median 3.3 %" in got
    assert "Doubling the segments roughly halves" in got


@pytest.mark.parametrize(
    ("flags", "lead"),
    [((True, False), "The 1 wire below the ground (of 2)"),
     ((True, False, False, True), "The 2 wires below the ground (of 4)")],
)  # fmt: skip
def test_the_extended_kernel_above_ground_summary(flags, lead):
    from momwire._below_interface import extended_kernel_above_advisory

    got = advisory_words.summary(
        "ExtendedKernelAboveGround", extended_kernel_above_advisory(flags)
    )
    assert got.startswith(
        "The extended (fat-wire) kernel was used on the wires above the ground. "
        f"{lead} used the standard thin-wire kernel"
    )
    assert "momwire" not in got and "reduced" not in got


def test_unknown_and_unreadable_advisories_get_no_summary():
    assert advisory_words.summary("SomethingNew", "anything") is None
    assert advisory_words.summary("CoarseCrossingNode", "reworded text") is None


def _jeff_engine(spec):
    builder = builder_from_text("g8hul.nec", G8HUL)()
    return make_engine_factory(spec, resolve_ground(_GROUND_UNSET, builder))(builder)


def test_jeffs_deck_serves_the_summary_beside_momwires_text():
    eng = _jeff_engine("momwire:bspline")
    eng.impedance()
    (adv,) = [a for a in eng.advisories if a["category"] == "CoarseCrossingNode"]
    assert adv["text"].startswith("crossing node: wire 0's start")
    assert adv["summary"].startswith(
        "A wire meets the ground at x = 0 m, y = 0 m, and the segments of the "
        "wire above the ground next to that joint are 0.50 m long"
    )
    # AK's own notes carry no summary and keep their shape.
    assert all(
        "summary" not in a for a in eng.advisories if a["category"] == "FeedPlacement"
    )


class _Noted:
    """An engine stand-in carrying advisories, as the CLI's echo reads them."""

    def __init__(self, advisories):
        self.advisories = advisories


def test_the_cli_echoes_the_summary_once_and_never_the_far_mesh_one(capsys):
    from antennaknobs.cli import _FeedPlacementEcho

    crossing = {"category": "CoarseCrossingNode", "text": "long", "summary": "plain"}
    far = {"category": "RazorFarMeshClass", "text": "long", "summary": "every solve"}
    unread = {"category": "SurfaceRadialHeight", "text": "reworded"}
    echo = _FeedPlacementEcho()
    for _ in range(2):
        echo.watch(lambda: _Noted([crossing, far, unread]))()
    echo.flush(final=True)
    assert capsys.readouterr().err == "advisory: plain\n"


def test_jeffs_deck_keeps_the_extended_kernel_above_ground_on_bspline():
    # His deck carries EK and a buried stake. Since momwire 0.78 B-spline
    # serves the kernel on the wires above the ground (momwire#1170), so
    # nothing falls back and no fallback note is composed.
    from momwire.bspline import BSplineSolver

    from antennaknobs.engines.momwire import MomwireEngine

    builder = builder_from_text("g8hul.nec", G8HUL)()
    eng = MomwireEngine(
        builder,
        solver=BSplineSolver,
        ground=resolve_ground(_GROUND_UNSET, builder),
        extended_kernel_default=True,
    )
    assert eng._extended_kernel is True
    assert not [a for a in eng.advisories if a["category"] == "ExtendedKernel"]


def test_jeffs_deck_says_in_plain_words_why_the_kernel_fell_back():
    # On razor-2p, which still refuses the kernel beside a buried wire, the
    # note used to say so in the solver's own words, issue numbers and all.
    from momwire import RazorSolver

    from antennaknobs.engines.momwire import MomwireEngine

    builder = builder_from_text("g8hul.nec", G8HUL)()
    eng = MomwireEngine(
        builder,
        solver=RazorSolver,
        ground=resolve_ground(_GROUND_UNSET, builder),
        extended_kernel_default=True,
    )
    (adv,) = [a for a in eng.advisories if a["category"] == "ExtendedKernel"]
    # AK#1996: the details are plain words too, and the summary says whose
    # choice the kernel was. This deck is read as NEC-4, which ignores its EK
    # card, so the reading is the reason and not the card.
    assert "momwire#" not in adv["text"]
    assert adv["summary"] == (
        "This deck is read as NEC-4, which is solved with the extended "
        "(fat-wire) kernel. It is not available for wires below the ground, "
        "so this whole solve used the standard thin-wire kernel. The "
        "difference matters for fat wires on short segments."
    )
