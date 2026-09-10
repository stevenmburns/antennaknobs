"""Backend coverage for a design the user brought (#1309).

`design_backend_coverage` used to resolve the design with
`importlib.import_module(f"{DESIGNS_PKG}.{name}")`. That form can only name a
design shipped inside the package, so every `user.*` name raised
ModuleNotFoundError into the broad except and the payload came back
`{"needs": [], "refusals": {}}` — indistinguishable from a design that nothing
refuses. No tab greyed, and the user met momwire's refusal at solve time: the
experience #1286 was built to remove, arriving on the designs a user is most
likely to bring.

The fixture is the catalog's own buried dipole copied BYTE FOR BYTE into the
user folder, which is what makes the gate airtight — same source, same class,
so any difference in the answer is the resolution path and nothing else. It
also cannot drift: there is no second copy of the geometry to maintain here.
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest

import antennaknobs.web.examples  # noqa: F401 — bootstraps the adapter + REGISTRY
from antennaknobs.web import adapter, user_designs
from antennaknobs.web.examples import REGISTRY

# Wholly below z = 0 and no end in the plane, so it needs `buried` and NOT
# `crossing_junction` — the simplest buried design in the catalog, and the one
# the issue measured against.
CATALOG_TWIN = "specialty.buried_dipole"
_CATALOG_FILE = adapter.DESIGNS_DIR / "specialty" / "buried_dipole.py"
_STEM = "buried_twin_1309"
USER_TWIN = f"{user_designs.USER_NS}.{_STEM}"


@pytest.fixture
def user_twin(tmp_path, monkeypatch):
    """`user.buried_twin_1309`: the catalog design, in the user folder.

    Trust is blanket-granted for the suite (see conftest), so `refresh()`
    loads it the way a trusted file loads in the running app. The teardown
    drops the `user.*` keys this added rather than leaving the process-wide
    REGISTRY holding a design whose folder is gone.
    """
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    shutil.copyfile(_CATALOG_FILE, tmp_path / f"{_STEM}.py")
    errors = user_designs.refresh()
    assert [e for e in errors if e["name"] == USER_TWIN] == [], errors
    assert USER_TWIN in REGISTRY, sorted(REGISTRY)[:5]
    yield USER_TWIN
    for key in [k for k in REGISTRY if k.startswith(f"{user_designs.USER_NS}.")]:
        del REGISTRY[key]


def test_the_hole_was_real(user_twin):
    """The old derivation could not have answered, by construction.

    Not a paraphrase of the bug: the import the previous implementation ran is
    run here and must still fail. If `antennaknobs.designs.user` ever becomes
    importable, the package-path form would start half-working and this test
    is the place that says so.
    """
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"{adapter.DESIGNS_PKG}.{user_twin}")


def test_a_user_design_reports_what_its_catalog_twin_reports(user_twin):
    """The gate: same file, same answer, whichever folder it sits in."""
    mine = adapter.design_backend_coverage(user_twin)
    theirs = adapter.design_backend_coverage(CATALOG_TWIN)
    assert mine == theirs
    # Named explicitly as well as compared, so a regression that empties BOTH
    # sides cannot pass this by making two nothings equal.
    assert "buried" in mine["needs"]
    assert mine["refusals"], "a buried design refuses somewhere"
    for backend in ("hmatrix", "arrayblock", "sinusoidal", "razor-2p", "pulse"):
        assert mine["refusals"][backend]["capability"] == "buried"
    assert "bspline" not in mine["refusals"]


def test_the_refusal_carries_momwires_own_sentence(user_twin):
    """#1264's rule holds on the user side too — a refusal without prose is
    the bug, not the refusal."""
    for backend, row in adapter.design_backend_coverage(user_twin)["refusals"].items():
        assert row.get("reason"), f"{user_twin} x {backend} has no sentence"


def test_the_examples_payload_carries_it(user_twin):
    """Through the endpoint, not just the helper: the mark has to reach the
    LIST the user picks from, which is the whole point of serving it there."""
    from antennaknobs.web import server

    # The endpoint refreshes user designs itself; the fixture's env var is
    # still in force, so it re-finds the same file.
    payload = server.examples_endpoint()
    rows = {e["name"]: e for e in payload["examples"]}
    assert user_twin in rows, sorted(rows)[:5]
    assert rows[user_twin]["backend_coverage"] == rows[CATALOG_TWIN]["backend_coverage"]
    assert "buried" in rows[user_twin]["backend_coverage"]["needs"]


# The shape the issue actually measured (`user.plumb_vertical_slope`): a stub
# whose geometry comes from a NEC deck sitting beside it, not from Python. It
# reaches the coverage derivation through `read_nec` -> `read_data`, whose
# folder confinement resolves the design's OWN directory — a different path
# from the copied-catalog fixture above, and the one a user is most likely to
# have, since importing a deck is how a design arrives from 4nec2 or xnec2c.
_DECK = """CM ground-mounted vertical with four sloping buried radials
CE
GW 1 21 0 0 0 0 0 10.0 0.002
GW 2 9 0 0 0 5.0 0 -0.3 0.002
GW 3 9 0 0 0 -5.0 0 -0.3 0.002
GW 4 9 0 0 0 0 5.0 -0.3 0.002
GW 5 9 0 0 0 0 -5.0 -0.3 0.002
GE 0
EX 0 1 1 0 1.0 0.0
FR 0 1 0 0 7.1 0
EN
"""

_DECK_STUB = """
from types import MappingProxyType

from antennaknobs import AntennaBuilder, read_nec


class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 7.1})

    def build_wires(self):
        return read_nec(self, "slope_radials.nec", network=True).wire_tuples(specs=True)

    def build_network(self):
        return read_nec(self, "slope_radials.nec", network=True).network()
"""


def test_a_deck_backed_user_design_reports_its_buried_radials(tmp_path, monkeypatch):
    """The reported case, end to end.

    Four radials sloping below z = 0 off a vertical whose base sits IN the
    plane: `buried` plus the declared-crossing node, which is what
    `verticals.buried_radial_vertical` reports too. Before the fix this
    answered nothing at all, so the user picked a solver tab that could not run
    their antenna and found out at the solve.
    """
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "slope_radials.nec").write_text(_DECK)
    (tmp_path / "slope_stub_1309.py").write_text(_DECK_STUB)
    errors = user_designs.refresh()
    try:
        name = f"{user_designs.USER_NS}.slope_stub_1309"
        assert [e for e in errors if e["name"] == name] == [], errors
        cov = adapter.design_backend_coverage(name)
        assert cov["needs"] == ["buried", adapter._CROSSING_NEED]
        assert (
            cov["needs"]
            == adapter.design_backend_coverage("verticals.buried_radial_vertical")[
                "needs"
            ]
        )
        # Every refusal is about the burial, and none of them is bspline.
        assert cov["refusals"]
        for backend, row in cov["refusals"].items():
            assert row["capability"].startswith("buried"), backend
            assert row.get("reason"), backend
        assert "bspline" not in cov["refusals"]
    finally:
        for key in [k for k in REGISTRY if k.startswith(f"{user_designs.USER_NS}.")]:
            del REGISTRY[key]


def test_a_name_the_registry_does_not_hold_answers_empty():
    """The contract that replaced the import: coverage is asked only of a
    design that has LOADED. An unknown name, a user design that failed to
    load, and one the user has not trusted are all the same answer — and none
    of them causes this function to load anything."""
    assert adapter.design_backend_coverage("user.no_such_design") == {
        "needs": [],
        "refusals": {},
    }
    assert adapter.design_backend_coverage("not.a.design") == {
        "needs": [],
        "refusals": {},
    }


def test_every_registered_design_carries_the_class_it_was_made_from():
    """`builder_cls` is what makes the two kinds resolve alike; an example
    missing it answers empty, so a registration path that forgets it would
    reintroduce the bug silently for whatever it registers."""
    missing = [name for name, ex in REGISTRY.items() if ex.builder_cls is None]
    assert missing == []


def test_the_class_is_the_one_that_registered(user_twin):
    """Not merely non-None: the same object the loader returned.

    A `builder_cls` that pointed at the catalog module's class would make the
    twin test pass while user designs still reported their neighbour's
    coverage.
    """
    path = Path(user_designs.default_user_dir()) / f"{_STEM}.py"
    loaded = user_designs.load_builder(path)
    registered = REGISTRY[user_twin].builder_cls
    # Re-executed per load (that is what picks up live edits), so they are
    # distinct class OBJECTS from the same file — identity of the file is what
    # matters here, not identity of the class.
    assert registered.__module__ == loaded.__module__
    assert registered.__qualname__ == loaded.__qualname__
    assert REGISTRY[CATALOG_TWIN].builder_cls is not registered
