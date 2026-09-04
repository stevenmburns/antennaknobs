"""The axis-derived controls, gated where the frontend cannot gate them (#1006 G2-5).

`lib/backends.ts::axisControls` decides which axes become CONTROLS on a tab:
multi-valued in `axes`, not pinned by the preset's `bound`, not a derived axis.
Host policy is a fourth thing it deliberately does not test, because no hosted
flag reaches the browser — so the invariant lives here, on the side that knows.

THE INVARIANT: every axis that becomes a control must map to a kwarg the hosted
sanitiser will actually accept. Today it holds for a reason that is easy to
lose: the one axis kwarg that is NOT allowlisted (`nec5_quadrature`) is dropped
anyway, because `razor-2p` is the only tab whose class offers two quadratures
and its preset pins the axis. Remove that pin — or add an axis whose kwarg
nobody allowlisted — and the hosted deployment renders a control whose value
the sanitiser silently discards, which looks to a user like a knob that does
nothing.

WHY NOT A CLAUSE IN THE FRONTEND. It could not be evaluated there (no hosted
flag) and it would be untestable-by-construction today (nothing for it to
reject). A clause that cannot fire is not protection; this test can fail.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import antennaknobs.web.server  # noqa: F401 — resolves the adapter import cycle
from antennaknobs.web.adapter import _HOSTED_MODEL_OPTIONS, backend_roster

_TS = (
    Path(__file__).resolve().parents[1]
    / "src/antennaknobs/web/frontend/src/lib/backends.ts"
)

DERIVED_AXES = ("ground_model", "wire_position")


def _rows():
    rows = backend_roster(have_pynec=True, have_nec5=True)
    assert rows, "empty roster — this file would pass by measuring nothing"
    return rows


def _axis_kwarg_from_typescript() -> dict[str, str]:
    """Read the mapping out of the TS module rather than restating it.

    A copy here would be a second source of truth for exactly the fact under
    test: if the frontend remapped `quadrature` to some other kwarg, a local
    copy would keep asserting the old pair and stay green while the real
    control went unchecked.
    """
    src = _TS.read_text()
    body = re.search(
        r"AXIS_KWARG:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}", src, re.S
    )
    assert body, f"AXIS_KWARG not found in {_TS} — the parse, not the rule, broke"
    pairs = re.findall(r"(\w+)\s*:\s*\"([^\"]+)\"", body.group(1))
    assert pairs, "AXIS_KWARG parsed as empty"
    return dict(pairs)


def _controls(row) -> set[str]:
    """`axisControls`, restated — the ONE duplication this file accepts.

    It is here because the question ("would this control survive hosting?")
    cannot be asked in the browser at all. The per-tab lists it produces are
    pinned against the TS implementation in backendAxisControls.test.ts, so a
    divergence between the two shows up there as a changed list rather than
    hiding here.
    """
    axes = row["axes"]
    if not axes:
        return set()
    bound = row.get("bound") or {}
    kw = _axis_kwarg_from_typescript()
    return {
        a
        for a, vals in axes.items()
        if a not in DERIVED_AXES and len(vals) > 1 and kw.get(a) not in bound
    }


def test_every_axis_control_kwarg_is_hosted_allowed():
    """The gate the frontend comment points at."""
    kw = _axis_kwarg_from_typescript()
    offenders = []
    for row in _rows():
        for axis in _controls(row):
            kwarg = kw.get(axis)
            if kwarg is None:
                offenders.append(f"{row['name']}: axis {axis!r} maps to no kwarg")
            elif kwarg not in _HOSTED_MODEL_OPTIONS:
                offenders.append(f"{row['name']}: {axis} -> {kwarg} not allowlisted")
    assert not offenders, (
        "an axis becomes a control but the hosted sanitiser will drop it:\n"
        + "\n".join(offenders)
        + "\n\nEither allowlist the kwarg in _HOSTED_MODEL_OPTIONS, or pin the "
        "axis in the preset's `bound`, or decide the control is local-only and "
        "give the frontend a hosted flag to filter on."
    )


def test_the_gate_can_actually_fail():
    """Mutate the DATA the gate reads, not the code that reads it.

    `razor-2p`'s quadrature axis is the live example: unpin it and the gate
    must go red, because `nec5_quadrature` is not allowlisted. Without this,
    the test above would be green on a roster where every axis happened to be
    single-valued, and nobody would know.
    """
    razor = next(r for r in _rows() if r["name"] == "razor-2p")
    assert razor["bound"] == {"nec5_quadrature": True}, razor["bound"]
    assert "quadrature" not in _controls(razor)

    unpinned = {**razor, "bound": {}}
    assert "quadrature" in _controls(unpinned)
    kwarg = _axis_kwarg_from_typescript()["quadrature"]
    assert kwarg == "nec5_quadrature"
    assert kwarg not in _HOSTED_MODEL_OPTIONS, (
        "nec5_quadrature became allowlisted — this test's premise is gone and "
        "the gate above now has no negative case; find another or delete this"
    )


@pytest.mark.parametrize("axis", DERIVED_AXES)
def test_the_derived_axes_would_fail_the_gate_if_they_became_controls(axis):
    """Why the fourth clause is load-bearing rather than cosmetic.

    Neither derived axis maps to a model-option kwarg at all — ground is its
    own panel and wire position is the design's geometry. If they leaked into
    the control set they would be controls the sanitiser has never heard of,
    so the frontend's exclusion and this allowlist agree about them.
    """
    kw = _axis_kwarg_from_typescript()
    assert axis not in kw
    row = next(r for r in _rows() if r["name"] == "bspline")
    assert len(row["axes"][axis]) > 1, "not multi-valued — the clause is untested"
    assert axis not in _controls(row)


def test_the_served_axis_payload_is_json_and_reaches_every_momwire_tab():
    """A gate over an empty payload proves nothing (the recurring failure)."""
    rows = _rows()
    with_axes = [r for r in rows if r["axes"]]
    assert len(with_axes) == 6, [r["name"] for r in with_axes]
    assert json.loads(json.dumps(rows))
    # ...and the non-momwire tabs say "cannot be asked" rather than "nothing".
    assert {r["name"] for r in rows if r["axes"] is None} == {"pynec", "nec5"}
