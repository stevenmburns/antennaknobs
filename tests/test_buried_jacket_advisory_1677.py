"""AK#1677: a jacketed wire BELOW the ground plane needs a deck comment.

momwire#1154 adds a charge-side elastance dS' = ln(b/a)/(2*pi*eps0*epsr)*
(1 - 1/eps~) for an insulated wire IN SOIL, on top of the free-space a'+L'
pair AK's deck writers already mirror (AK#1523, `LD 5` / the SimNEC
conductor). No NEC card can carry a charge-side term, so once the pinned
momwire carries the fix, a deck download of a jacketed BURIED wire is
silently the wrong antenna by tens of ohms at the feed.

Scope, established by reading the three writers before touching any of
them: only `engines.nec5.NEC5Engine.deck` can EVER emit a buried wire's
deck at all. `nec_export.export_nec`'s `refuse_nec2_geometry` refuses any
wire dipping below z=0 under a real ground before a deck is assembled
(jacketed or bare), and `simnec_export.build_nec_portal_script` calls
`export_nec` directly for its geometry, so it inherits the identical
refusal. That makes the NEC-2 and SimNEC writers untestable for this
feature by construction, not by omission — this file's NEC-2/SimNEC tests
assert exactly that refusal, on the same design and wire, so the claim is
pinned rather than merely stated.

`verticals.buried_radial_vertical` is the catalog's buried design with a
`wire_type` knob: its default (`connected`) convention buries the radials
and rise below z=0 with `wire_type=None` (bare) by default, and the
`surface` variant is jacketed (`wire_type="18-awg-pvc"`) by default but
lies ON the plane — the exact ambiguity the issue calls out ("the
catalog's surface variant lays radials ON the soil ... and must NOT
trigger it"). Switching the default convention's `wire_type` to an
insulated catalog wire is what "the buried catalog design with its wire
type switched to an insulated one" means in the issue's own words.

Response-level advisory: NONE of the three export endpoints has a channel
this can use. `/export_nec` (both `nec2` and `nec5` dialects) returns a
raw `Response(content=deck, ...)` with no JSON envelope at all — see
`web/server.py`'s `export_nec_endpoint` — and it is the ONLY endpoint that
can ever emit a buried deck. `/design_ssn` does have a JSON envelope
(`available`/`reason`/`text`), but `ssn_export` can never reach the
buried+jacketed state either, for the reason above, so there is nothing
for it to advise about. Inventing a header or a field on an endpoint nobody
reads for this purpose would fail the same test this file's docstring
argues for: a channel that reaches no consumer is not a channel, it is
dead code — so none is added. The CM comment in the deck itself is the
only advisory this issue can actually ship.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PyNEC")

from fastapi.testclient import TestClient

from antennaknobs import resolve_variant_params
from antennaknobs.designs.verticals.buried_radial_vertical import Builder
from antennaknobs.engines._nec_wire import (
    BURIED_JACKET_ADVISORY_CARDS,
    BURIED_JACKET_ADVISORY_TEXT,
    JACKET_COMMENT_CARDS,
    has_buried_jacketed_wire,
)
from antennaknobs.nec5_export import export_nec5
from antennaknobs.nec_export import export_nec
from antennaknobs.simnec_export import export_ssn
from antennaknobs.wire_catalog import Wire, WireSpec

GROUND = ("finite", 13.0, 0.005)


def _params(variant="default", **over):
    p = dict(resolve_variant_params(Builder, variant))
    p.update(over)
    return p


def _builder(variant="default", **over):
    return Builder(params=_params(variant, **over))


# ---------------------------------------------------------------------------
# the wording itself (requirement 4: plain, states current truth)
# ---------------------------------------------------------------------------


def test_the_advisory_text_names_the_mechanism_and_the_consequence():
    assert "in-soil charge correction" in BURIED_JACKET_ADVISORY_TEXT
    assert "momwire" in BURIED_JACKET_ADVISORY_TEXT
    assert "no NEC card" in BURIED_JACKET_ADVISORY_TEXT
    assert "as if in air" in BURIED_JACKET_ADVISORY_TEXT
    assert "will differ from antennaknobs" in BURIED_JACKET_ADVISORY_TEXT


def test_the_deck_comment_cards_are_all_CM_lines_within_80_columns():
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln.startswith("CM ")
        assert len(ln) <= 80, ln


# ---------------------------------------------------------------------------
# the helper directly: below/above, jacketed/bare, per-wire vs design default
# ---------------------------------------------------------------------------

_JACKET = WireSpec(radius=0.0004064, insulation_radius=0.0005, insulation_eps_r=3.5)
_BARE = WireSpec(radius=0.0004064)


def test_helper_true_only_for_a_jacketed_wire_with_an_end_below_the_plane():
    below_bare = Wire((0, 0, -0.1), (1, 0, -0.1), spec=_BARE)
    below_jacket = Wire((0, 0, -0.1), (1, 0, -0.1), spec=_JACKET)
    above_jacket = Wire((0, 0, 0.1), (1, 0, 0.1), spec=_JACKET)
    on_plane_jacket = Wire((0, 0, 0.0), (1, 0, 0.0), spec=_JACKET)

    assert not has_buried_jacketed_wire([below_bare], None)
    assert has_buried_jacketed_wire([below_jacket], None)
    assert not has_buried_jacketed_wire([above_jacket], None)
    assert not has_buried_jacketed_wire([on_plane_jacket], None)


def test_helper_falls_back_to_the_design_default_spec_like_the_LD_cards_do():
    """A wire with no `spec` of its own inherits the design-level material —
    the same fallback `_build_material_lines` uses for the LD cards — so a
    spec-less buried radial under a jacketed `wire_type` is still caught."""
    spec_less_buried = Wire((0, 0, -0.1), (1, 0, -0.1))
    assert has_buried_jacketed_wire([spec_less_buried], _JACKET)
    assert not has_buried_jacketed_wire([spec_less_buried], _BARE)
    assert not has_buried_jacketed_wire([spec_less_buried], None)


def test_helper_ignores_a_wire_that_only_touches_the_plane_at_one_end():
    """A crossing junction (rise from a buried hub up to z=0) has one end
    below and one end AT the plane; the wire is still genuinely buried."""
    rise = Wire((0, 0, -0.15), (0, 0, 0.0), spec=_JACKET)
    assert has_buried_jacketed_wire([rise], None)


# ---------------------------------------------------------------------------
# NEC-5: the one writer that can ever emit this deck at all
# ---------------------------------------------------------------------------


def _nec5(builder):
    return export_nec5(
        builder,
        ground=GROUND,
        design="verticals.buried_radial_vertical",
        rung="default",
        ground_name="somm13",
    )


def test_bare_buried_nec5_deck_carries_neither_comment():
    deck = _nec5(_builder())  # default convention, wire_type=None
    assert not any(ln.startswith("CM jacketed wire") for ln in deck.splitlines())
    assert BURIED_JACKET_ADVISORY_TEXT not in deck
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln not in deck


def test_jacketed_buried_nec5_deck_carries_both_comments():
    """Both AK#1523's existing a'+L' comment (the wire IS jacketed) and
    AK#1677's new one (the jacket is IN SOIL, which a'+L' cannot fix)."""
    deck = _nec5(_builder(wire_type="18-awg-pvc"))
    lines = deck.splitlines()
    for ln in JACKET_COMMENT_CARDS:
        assert ln in lines, deck
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln in lines, deck
    # The deck actually carries a wire below z=0 — the design's whole point —
    # so the comment is not decorating a design that never buries anything.
    assert any(
        ln.startswith("GW") and float(ln.split()[5]) < 0.0
        for ln in lines
        if ln.startswith("GW")
    )


def test_surface_variant_is_jacketed_but_never_buried_so_no_advisory():
    """The exact case the issue calls out by name: the `surface` convention
    is jacketed by default (its radials need the jacket as their stand-off)
    but lies ON the soil, never below it."""
    deck = _nec5(_builder("surface"))
    lines = deck.splitlines()
    # It IS a jacketed deck (the existing #1523 comment fires) ...
    for ln in JACKET_COMMENT_CARDS:
        assert ln in lines, deck
    # ... but nothing in it is below the plane (GW fields: tag n_seg x1 y1
    # z1 x2 y2 z2 rad, so z1/z2 are split()[5]/split()[8]).
    assert all(
        float(ln.split()[5]) >= 0.0 and float(ln.split()[8]) >= 0.0
        for ln in lines
        if ln.startswith("GW")
    )
    # ... so the new advisory must not fire.
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln not in lines, deck
    assert BURIED_JACKET_ADVISORY_TEXT not in deck


def test_free_space_never_carries_the_advisory_even_with_a_below_z0_wire():
    """No ground plane, nothing to be "below" — the design's own knobs put a
    bare jacketed wire under z=0 in free space (no soil correction applies:
    momwire's ordinary free-space a'+L' pair is exact there)."""
    deck = export_nec5(
        _builder(wire_type="18-awg-pvc"),
        ground=None,
        design="verticals.buried_radial_vertical",
        rung="default",
        ground_name="free",
    )
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln not in deck.splitlines(), deck


# ---------------------------------------------------------------------------
# NEC-2 and SimNEC: refused before either could reach the advisory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wire_type", [None, "18-awg-pvc"])
def test_nec2_refuses_the_buried_design_whether_or_not_it_is_jacketed(wire_type):
    with pytest.raises((NotImplementedError, ValueError)):
        export_nec(_builder(wire_type=wire_type), ground=GROUND)


@pytest.mark.parametrize("wire_type", [None, "18-awg-pvc"])
def test_simnec_refuses_the_buried_design_whether_or_not_it_is_jacketed(wire_type):
    with pytest.raises((NotImplementedError, ValueError)):
        export_ssn(_builder(wire_type=wire_type), freq_mhz=7.1, ground=GROUND)


def test_nec2_and_simnec_serve_the_jacketed_surface_variant_with_no_advisory():
    """Confirms the NEC-2/SimNEC refusal above is about BURIAL, not about
    jackets in general: the surface variant is jacketed and both writers
    happily serve it, carrying no buried-jacket comment (they have none)."""
    deck2 = export_nec(_builder("surface"), ground=GROUND)
    assert deck2  # served
    ssn = export_ssn(_builder("surface"), freq_mhz=7.1, ground=GROUND)
    assert ssn  # served


# ---------------------------------------------------------------------------
# response-level advisory: no channel exists, and this pins that fact
# ---------------------------------------------------------------------------


def _post_export_nec(client, **over):
    req = {"geometry": "verticals.buried_radial_vertical", "ground": True, **over}
    return client.post("/export_nec", json=req)


def test_export_nec_endpoint_has_no_json_envelope_to_carry_an_advisory_in():
    """`/export_nec` is a raw file download (Content-Disposition attachment),
    for BOTH dialects, with no JSON body at all — so there is no field this
    issue could add an "advisories" list to without inventing a channel the
    frontend has never read (`sessionActions.ts`'s `downloadNec` only reads
    the blob and the Content-Disposition header)."""
    import antennaknobs.web.server as server

    client = TestClient(server.app)
    r = _post_export_nec(client, dialect="nec5", wire_type="18-awg-pvc")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    with pytest.raises(Exception):
        r.json()
    # The deck itself DOES carry the advisory end to end, through the server.
    for ln in BURIED_JACKET_ADVISORY_CARDS:
        assert ln in r.text.splitlines(), r.text


def test_design_ssn_endpoint_json_envelope_never_reaches_the_buried_state():
    """`/design_ssn` DOES return JSON, but `ssn_export` can never emit a
    buried deck (it reuses `export_nec`'s refusal) — so its envelope has
    nothing to carry for this issue either; it reports `available: False`
    with the SAME refusal reason for the bare and the jacketed wire."""
    import antennaknobs.web.server as server

    client = TestClient(server.app)
    bare = client.post(
        "/design_ssn",
        json={"geometry": "verticals.buried_radial_vertical", "ground": True},
    ).json()
    jacketed = client.post(
        "/design_ssn",
        json={
            "geometry": "verticals.buried_radial_vertical",
            "ground": True,
            "wire_type": "18-awg-pvc",
        },
    ).json()
    assert bare["available"] is False, bare
    assert jacketed["available"] is False, jacketed
    assert "reason" in bare and "reason" in jacketed
