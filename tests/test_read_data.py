"""antennaknobs.read_data / read_json — the blessed, folder-confined way for a
data-driven design to load a co-located data file without importing open/pathlib.

The read is confined to the *calling design's own folder* (found via the builder
passed as the first arg): it can never be turned into an arbitrary-file read
(absolute paths, ``..`` traversal, and symlinks that point outside the design
folder are all rejected), is read-only, and is size-capped.
"""

import os

import pytest

from antennaknobs import design_data
from antennaknobs import read_data as read_data_fn
from antennaknobs import user_designs

# A data-driven design that loads its geometry from a sidecar JSON via the
# blessed helper. Imports only from antennaknobs + the stdlib types module.
DATA_DESIGN = """
from types import MappingProxyType
from antennaknobs import AntennaBuilder, read_json

class Builder(AntennaBuilder):
    default_params = MappingProxyType({"freq": 14.0})

    def build_wires(self):
        spec = read_json(self, "wires.json")
        out = []
        for w in spec["wires"]:
            out.append((tuple(w["start"]), tuple(w["end"]),
                        w.get("n", self.nominal_nsegs),
                        (1 + 0j) if w.get("feed") else None))
        return out
"""

SIDECAR = """
{"wires": [
  {"start": [0, -5, 0], "end": [0, -0.01, 0]},
  {"start": [0, 0.01, 0], "end": [0, 5, 0]},
  {"start": [0, -0.01, 0], "end": [0, 0.01, 0], "n": 1, "feed": true}
]}
"""


@pytest.fixture
def design(tmp_path, monkeypatch):
    """A loaded data-driven Builder instance, with its sidecar in place."""
    monkeypatch.setenv("ANTENNAKNOBS_USER_DIR", str(tmp_path))
    (tmp_path / "data_design.py").write_text(DATA_DESIGN)
    (tmp_path / "wires.json").write_text(SIDECAR)
    cls = user_designs.resolve_user_design("data_design")
    return tmp_path, cls()


def test_read_json_loads_sidecar_and_builds(design):
    _, b = design
    wires = b.build_wires()
    assert len(wires) == 3
    assert sum(1 for w in wires if w[3] is not None) == 1  # exactly one feed


def test_read_data_returns_text(design):
    _, b = design
    assert '"wires"' in read_data_fn(b, "wires.json")


def test_absolute_path_rejected(design):
    _, b = design
    with pytest.raises(ValueError, match="absolute"):
        read_data_fn(b, "/etc/passwd")


def test_parent_traversal_rejected(tmp_path, design):
    dir_, b = design
    # Plant a secret one level up from the design folder.
    secret = dir_.parent / "secret.txt"
    secret.write_text("TOP SECRET")
    with pytest.raises(ValueError, match="outside the design"):
        read_data_fn(b, "../secret.txt")


def test_symlink_escape_rejected(design):
    dir_, b = design
    secret = dir_.parent / "secret.txt"
    secret.write_text("TOP SECRET")
    link = dir_ / "innocent.json"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    # The name lives in the design folder, but resolve() follows the symlink
    # out; confinement must catch the real target.
    with pytest.raises(ValueError, match="outside the design"):
        read_data_fn(b, "innocent.json")


def test_missing_file_raises_filenotfound(design):
    _, b = design
    with pytest.raises(FileNotFoundError):
        read_data_fn(b, "nope.json")


def test_size_cap_enforced(design, monkeypatch):
    dir_, b = design
    monkeypatch.setattr(design_data, "_MAX_SIDECAR_BYTES", 8)
    (dir_ / "big.json").write_text("x" * 64)
    with pytest.raises(ValueError, match="over the"):
        read_data_fn(b, "big.json")


def test_empty_name_rejected(design):
    _, b = design
    with pytest.raises(ValueError):
        read_data_fn(b, "")
