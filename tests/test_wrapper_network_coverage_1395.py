"""antennaknobs#1395: the coverage grid asks the wrappers about the network too.

`design_backend_coverage` (#1286) answered exactly one question for the wrapper
backends — `buried` — because that was the only measured row they had. So a design
whose network is a transmission line, a transformer or a virtual driver showed an
OFFERED NEC-2 tab and met the refusal after a click: the experience #1286 exists to
remove, surviving in the one corner it never reached. #1354 made it visible by
adding a third wrapper; it did not create it.

The three wrappers genuinely differ, which is why this is a per-kind row and not
one sentence for the design:

    pynec   SERVES — a multiport-Y reduction outside the field solve.
    nec5    SERVES — the same route since #1280.
    nec2    REFUSES — `export_nec` writes ONE deck, and a reduction has no
            faithful single-deck spelling.

THE GATE, and it needs no binary. `#1286`'s model is that a fast derivation needs
checking against something that constructs. `NEC2Engine.__init__` cannot be that
here: it raises for a missing `$NEC2_EXE` before it reaches any refusal, which is an
availability question and not a capability one. But the thing that actually refuses
a TL network on the NEC-2 lane is the DECK WRITER, `nec_export.export_nec`, and that
needs no engine at all since #1387. So the probe is the writer, over the whole
catalog, and it is authoritative for the same reason `_make_solver` is: it raises
the refusal and solves nothing.
"""

from __future__ import annotations

import pytest

import antennaknobs.web.examples  # noqa: F401 — import for registration order
from antennaknobs.web import adapter
from antennaknobs.web.examples import REGISTRY

_NEED = "network_reduction"


def _design_cls(name):
    ex = REGISTRY.get(name)
    return getattr(ex, "builder_cls", None) if ex is not None else None


def _writer_refuses(cls) -> bool:
    """Does the NEC-2 deck writer refuse this design's network? The probe.

    A builder that will not build, or a geometry refusal (buried, graded), is not
    an answer to the NETWORK question and is reported as "no network refusal" —
    the coverage grid answers those through their own rows.
    """
    from antennaknobs.nec_export import export_nec

    try:
        builder = cls()
    except Exception:  # noqa: BLE001 — a design that will not build answers nothing here
        return False
    try:
        export_nec(builder, ground="free")
    except NotImplementedError as e:
        return "transmission line" in str(e) or "TL/virtual-driver" in str(e)
    except Exception:  # noqa: BLE001 — geometry refusals and build failures are other rows
        return False
    return False


# Designs the NETWORK probe cannot answer for, because the writer refuses them on
# an EARLIER capability and never reaches the network. `wire.sterba_bl` needs the
# reduction AND carries `PortAtEnd` ports, and `export_nec` refuses the ports first
# (#579). Both answers are right about their own question; the probe is only
# authoritative where nothing earlier fires, and naming the exception is better
# than widening the probe until it agrees.
_EARLIER_CAPABILITY = {"junction_ports", "node_gaps", "buried"}


@pytest.mark.antenna_computation_check
def test_the_derivation_agrees_with_the_deck_writer_over_the_catalog():
    """Every design, both directions: the grid greys the NEC-2 tab exactly when the
    writer refuses the network — over the designs where the network is the first
    thing that could refuse."""
    disagree, skipped = [], []
    for name in sorted(REGISTRY):
        cls = _design_cls(name)
        if cls is None:
            continue
        needs = adapter._design_capability_needs(cls)
        derived = adapter._NETWORK_NEED in needs
        if needs & _EARLIER_CAPABILITY:
            skipped.append(name)
            continue
        probed = _writer_refuses(cls)
        if derived != probed:
            disagree.append((name, derived, probed))
    assert not disagree, f"derivation vs deck writer disagree on {disagree[:8]}"
    # The exception set is small and named, so a change in it is visible here
    # rather than absorbed: one design carries junction ports, one carries a
    # vertex port, and the buried ones are answered by their own row.
    assert len(skipped) <= 12, skipped


def test_the_probe_answered_a_useful_number_of_designs():
    """Guards the test above from passing vacuously: a probe that answered nothing
    would agree with any derivation. The corpus of designs is ~100; the network
    question must be asked of most of them."""
    asked = 0
    for name in sorted(REGISTRY):
        cls = _design_cls(name)
        if cls is None:
            continue
        if not (adapter._design_capability_needs(cls) & _EARLIER_CAPABILITY):
            asked += 1
    assert asked >= 80, asked


def test_a_tl_design_greys_nec2_and_only_nec2_among_the_wrappers():
    """The user story. `broadband.lpda` is a log-periodic fed through a TL."""
    cov = adapter.design_backend_coverage("broadband.lpda")
    assert _NEED in cov["needs"], cov
    refusals = cov["refusals"]
    assert refusals.get("nec2", {}).get("capability") == _NEED, refusals
    assert "nec2" not in (refusals.get("pynec") or {}), refusals
    assert "pynec" not in refusals and "nec5" not in refusals, refusals


def test_the_nec2_sentence_names_the_tabs_that_do_serve_it():
    """A greyed tab with no way forward is a dead end; the sentence a user hovers
    to read has to say where to go."""
    reason = adapter.design_backend_coverage("broadband.lpda")["refusals"]["nec2"][
        "reason"
    ]
    assert "momwire" in reason and "NEC-5" in reason and "PyNEC" in reason, reason
    assert "multiport-Y" in reason, reason


def test_a_momwire_backend_is_not_greyed_by_a_network():
    """The reducer is momwire's own, and a TL network is what `build_network()` is
    for — so no momwire row belongs in this table at all."""
    cov = adapter.design_backend_coverage("broadband.lpda")
    momwire_names = {b.name for b in adapter._BACKENDS if b.kind == "momwire"}
    assert not (momwire_names & set(cov["refusals"])), cov["refusals"]


def test_a_plain_design_needs_nothing_and_refuses_nowhere():
    cov = adapter.design_backend_coverage("dipoles.invvee")
    assert _NEED not in cov["needs"], cov
    assert "nec2" not in cov["refusals"], cov


def test_geometry_is_answered_before_the_network():
    """A backend that cannot take the deck's GEOMETRY should say that rather than
    a narrower reason that is also true — the order the client's `designRefusal`
    uses. `verticals.buried_radial_vertical` is buried AND graded, and NEC-2
    refuses it on both counts."""
    cov = adapter.design_backend_coverage("verticals.buried_radial_vertical")
    assert cov["refusals"]["nec2"]["capability"] == "buried", cov["refusals"]["nec2"]


def test_the_need_comes_from_the_engines_own_predicate_not_a_second_list():
    """A copy of the branch-type list here would drift, and the drift would grey a
    tab that solves or offer one that does not. Asserted on the source."""
    from pathlib import Path

    src = Path(adapter.__file__).read_text()
    assert "_network_needs_reducer" in src, "the predicate is not being reused"
    assert "isinstance(br, Load)" not in src, "the branch-type test is copied here"


@pytest.mark.parametrize("kind", ["pynec", "nec5", "nec2"])
def test_every_wrapper_kind_has_a_row(kind):
    """Three states, not two (#1103's rule): a wrapper absent from the table
    would read as SERVES, which is the one answer that must never be inferred."""
    assert kind in adapter._WRAPPER_NETWORK_SCOPE
    serves, reason, issue = adapter._WRAPPER_NETWORK_SCOPE[kind]
    assert isinstance(serves, bool)
    if serves is False:
        assert reason and issue, (kind, reason, issue)
