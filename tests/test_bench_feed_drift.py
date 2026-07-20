"""Feed-drift census tool (scripts/bench_feed_drift.py, issue #459).

Cheap unit pins: the network-port classifier, the suspect predicate, and one
end-to-end census row on a small design. The full 91-design sweep is a manual
diagnostic, not a per-PR test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BFD = Path(__file__).resolve().parent.parent / "scripts" / "bench_feed_drift.py"
_spec = importlib.util.spec_from_file_location("bench_feed_drift", _BFD)
bfd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bfd)


def test_feed_is_network_port_true_for_tl_port_feed():
    """A design whose feed shares a TL/NT/transformer port is flagged; a plain
    driven dipole is not."""
    from antennaknobs.designs.wire.zepp import Builder as Zepp
    from antennaknobs.designs.dipoles.invvee import Builder as Invvee

    assert bfd.feed_is_network_port(Zepp) is True  # ladder-line TL port feed
    assert bfd.feed_is_network_port(Invvee) is False  # plain delta-gap dipole


def test_feed_is_network_port_ignores_lumped_load_on_feed():
    """A lumped Load/Shunt on the feed is not a TL/NT port — terminated_longwire
    feeds a plain wire (its Load sits on the *term* port, not the feed)."""
    from antennaknobs.designs.wire.terminated_longwire import Builder

    assert bfd.feed_is_network_port(Builder) is False


def test_is_suspect_requires_drift_and_mesh_unstable_feed():
    """Suspect = still moving at the finest mesh AND (near-open |Z| or TL port).
    A converged row, or a drifting-but-benign (low |Z|, no port) row, is not."""
    near_open_drift = {
        "error": None,
        "drift": 0.15,
        "converged_at": None,
        "z_fine": complex(400.0, -5000.0),
        "net_port": False,
    }
    assert bfd.is_suspect(near_open_drift) is True

    converged = {**near_open_drift, "converged_at": 61}
    assert bfd.is_suspect(converged) is False

    benign = {**near_open_drift, "z_fine": complex(50.0, 5.0), "net_port": False}
    assert bfd.is_suspect(benign) is False

    port_drift = {**benign, "net_port": True}
    assert bfd.is_suspect(port_drift) is True


def test_census_row_converges_on_a_clean_dipole():
    """End-to-end on one small, well-behaved design: a plain dipole converges on
    the ladder and is not a suspect."""
    row = bfd.census_row(
        "dipoles.invvee", ladder=(21, 61), engine="pynec", ground="free", seg_cap=3000
    )
    assert row["error"] is None
    assert len(row["series"]) == 2
    assert row["converged_at"] is not None  # plateaus
    assert bfd.is_suspect(row) is False


def test_census_row_skips_rungs_over_the_seg_cap():
    """A seg-cap below the design's coarse mesh skips every rung — recorded, not
    silently dropped — leaving no usable series."""
    row = bfd.census_row(
        "dipoles.invvee", ladder=(21, 61), engine="pynec", ground="free", seg_cap=1
    )
    assert row["skipped"] == [21, 61]
    assert row["series"] == []
    assert "drift" not in row
