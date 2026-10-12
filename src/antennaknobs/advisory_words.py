"""Plain-words summaries of momwire's solver advisories (AK#1981).

momwire composes its advisories for the people who maintain it: issue
numbers, solver internals (`n_qp_pair`, `n_per_edge_per_wire`), and its own
0-based wire indices, which name no wire in the user's deck. Jeff G8HUL met
`CoarseCrossingNode` on a vertical with a ground stake and called it "totally
incomprehensible" (groups.io antenna-research #1605). He was right about the
wording, and the advisory was right in substance.

So each KNOWN category gets one plain sentence or three, led by what the
advisory is about in the deck's own terms, roughly what it is worth, and
what to do. momwire's text is kept untouched as the detail behind it.

Read, never rewritten: the numbers come out of momwire's own sentence, so a
summary can only say what the advisory said. A sentence this module cannot
read gets no summary, and the UI shows momwire's text in full as before.
The tests build each advisory with momwire's own composer, so a rewording on
the momwire side fails here rather than going quietly unsummarised.

The quadrature lever momwire's crossing advisory names is deliberately NOT
repeated. On Jeff's deck (buried, so bs2 already runs at order 32) forcing
the order anywhere from 8 to 128 moves X by 0.002 ohm while the mesh moves
it 3.5 ohm (AK#1981); the #760 figure it quotes is the soil-A fan at order 8.
Adding segments is the advice that holds.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_NUM = r"([0-9]+(?:\.[0-9]+)?)"

_CROSSING = re.compile(
    r"crossing node: wire (\d+)'s (start|end) is the (above|below) member, and the "
    rf"finest mesh within {_NUM} mm of the node is {_NUM} mm"
)
_CROSSING_FLOOR = re.compile(rf"from L_min = {_NUM} mm at the node")

_SURFACE = re.compile(
    rf"(\d+) near-ground wire\(s\) at h = {_NUM} mm, h/a = ({_NUM[1:-1]}|inf)"
)

_FAR_MESH = re.compile(rf"a median {_NUM} % from converged, with a tail to {_NUM} %")


def _length(mm: float) -> str:
    """A segment length as a modeller reads it: millimetres when short."""
    return f"{mm:.0f} mm" if mm < 100 else f"{mm / 1000:.2f} m"


def _coarse_crossing(text: str, locate) -> str | None:
    m = _CROSSING.search(text)
    if m is None:
        return None
    wire, end, side, h = int(m.group(1)), m.group(2), m.group(3), float(m.group(5))
    point = locate(wire, end) if locate is not None else None
    where = (
        f"at x = {point[0]:.3g} m, y = {point[1]:.3g} m"
        if point is not None
        else "at a joint"
    )
    floor = ""
    f = _CROSSING_FLOOR.search(text)
    if f is not None:
        floor = (
            f" This wire meets the ground at a slope, so no segment there can "
            f"be shorter than {_length(float(f.group(1)))}."
        )
    return (
        f"A wire meets the ground {where}, and the segments of the wire "
        f"{side} the ground next to that "
        f"joint are {_length(h)} long: too long for the impedance there to "
        f"have settled. Expect the reactance to move by up to a few ohms as "
        f"you refine. Add segments to the wires at the joint (or to the whole "
        f"model) until the readout stops changing.{floor}"
    )


def _surface_height(text: str, _locate) -> str | None:
    m = _SURFACE.search(text)
    if m is None:
        return None
    n, h, ratio = int(m.group(1)), float(m.group(2)), m.group(3)
    wires = "A wire lies" if n == 1 else f"{n} wires lie"
    radii = "" if ratio == "inf" else f" ({float(ratio):.3g} wire radii)"
    return (
        f"{wires} only {h:.3g} mm above the ground{radii}. That close, the "
        f"impedance depends strongly on the exact height, so model the "
        f"height the wire really has: the same wire lying deeper in the grass "
        f"is a measurably different antenna."
    )


def _far_mesh(text: str, _locate) -> str | None:
    m = _FAR_MESH.search(text)
    if m is None:
        return None
    return (
        f"razor-2p's answer keeps moving as segments are added: on typical "
        f"models it sits a few percent from converged (median {m.group(1)} %). "
        f"Doubling the segments roughly halves that, and bs2 is already "
        f"converged at the same segment counts."
    )


_SUMMARISERS: dict[str, Callable] = {
    "CoarseCrossingNode": _coarse_crossing,
    "SurfaceRadialHeight": _surface_height,
    "RazorFarMeshClass": _far_mesh,
}


def summary(category: str, text: str, locate=None) -> str | None:
    """The plain-words summary of one momwire advisory, or None.

    ``locate(wire, end)`` maps momwire's 0-based wire index and ``"start"`` /
    ``"end"`` to that end's (x, y, z) in metres, or None when it cannot; it
    lets the crossing summary name the joint by where it is rather than by an
    index the deck never shows. None for an unknown category, and for a known
    one whose sentence this module cannot read.
    """
    fn = _SUMMARISERS.get(category)
    return fn(text, locate) if fn is not None else None
