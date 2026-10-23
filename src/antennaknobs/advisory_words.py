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

_EK_ABOVE = re.compile(r"On this deck (\d+) of (\d+) wires are below the plane")


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


def _ek_above_ground(text: str, _locate) -> str | None:
    """B-spline (momwire 0.78, momwire#1170) and razor-2p (momwire 0.82,
    momwire#1614) serve the extended kernel on a deck with buried wires in
    part: the pairs above the ground take it, the buried wires keep the
    standard kernel. One summary for both ways of getting there, an explicit
    request and a deck whose dialect asks."""
    m = _EK_ABOVE.search(text)
    if m is None:
        return None
    n, total = int(m.group(1)), int(m.group(2))
    buried = "The 1 wire" if n == 1 else f"The {n} wires"
    return (
        f"The extended (fat-wire) kernel was used on the wires above the "
        f"ground. {buried} below the ground (of {total}) used the standard "
        f"thin-wire kernel, because the extended kernel is not available "
        f"there. The difference matters for fat wires on short segments, so "
        f"on ordinary buried radials it is small."
    )


_SUMMARISERS: dict[str, Callable] = {
    "CoarseCrossingNode": _coarse_crossing,
    "SurfaceRadialHeight": _surface_height,
    "RazorFarMeshClass": _far_mesh,
    "ExtendedKernelAboveGround": _ek_above_ground,
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


# --------------------------------------------------------------------------
# AK's own "ExtendedKernel" advisory (AK#1996)
# --------------------------------------------------------------------------
# The extended kernel as a DEFAULT that this solve could not take. Unlike the
# advisories above this one is composed here, from what the engine knows, and
# never from momwire's refusal sentence: that sentence is written for
# momwire's maintainers (issue numbers, a Python argument) and blamed nobody
# in particular, where the summary used to blame the deck (G8HUL,
# antenna-research #1620: no EK card, read as NEC-4).
#
# Four pieces, each its own function so one can change without the others:
# WHY the kernel was on, WHAT refused it, WHAT WAS AFFECTED, and what the
# user can do. The B-spline basis (since momwire 0.78) and razor-2p (since
# momwire 0.82) serve a buried deck in part (extended kernel above the
# ground, standard kernel on the buried wires), so on those two nothing falls
# back and this advisory is not composed; momwire's own
# `ExtendedKernelAboveGround` says what happened, summarised by
# `_ek_above_ground` above.

_DIALECT_WORD = {"nec4": "NEC-4", "nec5": "NEC-5"}

# Why the extended kernel could not be used, completing "It is ...".
EK_CAUSE_WORDS = {
    "basis": "This solver does not have it",
    "enrichment": "This solver does not have it together with singular enrichment",
    "buried": "It is not available for wires below the ground",
    "stepped": "It is not available where wires of different radii meet",
}

EK_SOURCES = ("dialect", "ez_engine", "ez_reading", "card", "default")


def _ek_why_on(source: str, dialect: str | None) -> str:
    """Why this solve was to use the extended kernel. ``source`` is what the
    engine could establish: the deck's reading ("dialect"), an EZNEC model's
    engine setting ("ez_engine") or the reading chosen for it ("ez_reading"),
    a NEC-2 deck's own EK card ("card"), or none of these ("default": a
    caller turned the default on for a design that does not say why)."""
    nec = _DIALECT_WORD.get(dialect)
    solved = "solved with the extended (fat-wire) kernel"
    if source == "dialect" and nec:
        return f"This deck is read as {nec}, which is {solved}."
    if source == "ez_reading" and nec:
        return f"This EZNEC model is read as {nec}, which is {solved}."
    if source == "ez_engine" and nec:
        return f"This EZNEC model is set to the {nec} engine, so it is {solved}."
    if source == "card":
        return "This deck's EK card asks for the extended (fat-wire) kernel."
    return "This design is solved with the extended (fat-wire) kernel by default."


def _ek_affected(cause: str) -> tuple[str, str]:
    """What the fallback touched, as (the summary's clause, the details'
    sentence). Today it is always the whole solve, whatever the cause."""
    also = {
        "buried": ", not only the wires below the ground",
        "stepped": ", not only the wires at that joint",
    }.get(cause, "")
    return (
        "this whole solve used the standard thin-wire kernel",
        "What was affected: the whole solve. Every wire used the standard "
        f"thin-wire kernel{also}.",
    )


def _metres(v: float) -> str:
    return f"{v:.3g} m"


def _ek_caused_by(cause: str, facts: dict) -> str:
    """Which part of the model or the setup the refusal is about, with the
    deck's own numbers where the engine supplied them in ``facts``."""
    if cause == "buried":
        depth = facts.get("depth_m")
        down = f", down to {_metres(depth)} deep" if depth else ""
        return f"What caused it: this model has wire below the ground{down}."
    if cause == "stepped":
        joints = facts.get("joints") or ()
        if not joints:
            return "What caused it: wires of different radii meet at a joint."
        x, y, z = joints[0]
        more = len(joints) - 1
        others = (
            ""
            if more == 0
            else " and at 1 other joint"
            if more == 1
            else f" and at {more} other joints"
        )
        return (
            "What caused it: wires of different radii meet at "
            f"x = {x:.3g} m, y = {y:.3g} m, z = {z:.3g} m{others}."
        )
    if cause == "enrichment":
        return (
            "What caused it: singular enrichment is switched on for this "
            "solver, and the two cannot be used together."
        )
    return "What caused it: the solver chosen for this slot has no extended kernel."


_EK_HOW_MUCH = (
    "How much it matters: the two kernels differ where a wire is fat for its "
    "segments. Expect a fraction of a percent where the segments are more "
    "than about 10 wire radii long, and several percent where they are "
    "shorter than about 3. A thin wire on ordinary segments is hardly "
    "affected."
)

_EK_WHAT_TO_DO = {
    "basis": (
        "What you can do: to solve with the extended kernel, open the slot's "
        "options (the gear beside the solver slot) and choose a solver that "
        'shows the "extended kernel (EK)" switch.'
    ),
    "enrichment": (
        "What you can do: to solve with the extended kernel, open the slot's "
        "options (the gear beside the solver slot) and switch off "
        '"K≥3 junction singular enrichment".'
    ),
    # Only the B-spline basis (bs2, the default), razor-2p and the sinusoidal
    # Galerkin basis (momwire 0.83, momwire#1626) serve the extended kernel
    # beside a buried wire, and only on the wires above the ground;
    # `test_ek_advisory_wording_1996.py` holds that claim to momwire.
    "buried": (
        "What you can do: to use the extended kernel on the wires above the "
        "ground, open the slot's options (the gear beside the solver slot) "
        "and choose B-spline (the default), Razor (2-point) or Sin-Galerkin. "
        "The wires below the ground keep the standard kernel on every solver."
    ),
    # Only some solvers have this limit (in the pinned momwire, the
    # sinusoidal Galerkin one), so another solver is real advice here too.
    "stepped": (
        "What you can do: to solve with the extended kernel, open the slot's "
        "options (the gear beside the solver slot) and choose another "
        "solver. Not every solver has this limit."
    ),
}


def extended_kernel_fallback(
    cause: str,
    source: str = "default",
    dialect: str | None = None,
    facts: dict | None = None,
) -> tuple[str, str]:
    """The "ExtendedKernel" advisory's ``(summary, details)`` in plain words.

    ``cause`` is a key of `EK_CAUSE_WORDS`; ``source`` one of `EK_SOURCES`
    with ``dialect`` ("nec4" / "nec5") for every source that names one; ``facts``
    the deck's own numbers for the cause: ``depth_m`` (how far the deepest
    wire goes below the ground) and ``joints`` (the (x, y, z) of each joint
    where wires of different radii meet)."""
    facts = facts or {}
    clause, affected = _ek_affected(cause)
    summary = (
        f"{_ek_why_on(source, dialect)} {EK_CAUSE_WORDS[cause]}, so {clause}. "
        "The difference matters for fat wires on short segments."
    )
    details = " ".join(
        [affected, _ek_caused_by(cause, facts), _EK_HOW_MUCH, _EK_WHAT_TO_DO[cause]]
    )
    return summary, details
