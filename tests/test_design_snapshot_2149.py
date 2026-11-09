"""A built design as plain data, and back (AK#2149 unit 1).

Every catalog design's hooks must survive `snapshot` -> JSON -> `decode` as
exactly what they returned (types, dtypes, tuple-ness and values), and
`decode` must construct nothing outside the allowlist.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import math
import types
import warnings

import numpy as np
import pytest

from antennaknobs import design_snapshot as dd
from antennaknobs.builder import resolve_variant_params

cli = importlib.import_module("antennaknobs.cli")


def same(a, b) -> bool:
    """Structural equality that also checks exact types (a tuple is not a
    list, numpy float64 is not float) and treats NaN as equal to NaN."""
    if type(a) is not type(b):
        return False
    if isinstance(a, np.ndarray):
        return (
            a.dtype == b.dtype
            and a.shape == b.shape
            and np.array_equal(a, b, equal_nan=True)
        )
    if isinstance(a, (float, np.floating)):
        return (math.isnan(a) and math.isnan(b)) or a == b
    if isinstance(a, (complex, np.complexfloating)):
        return same(float(a.real), float(b.real)) and same(float(a.imag), float(b.imag))
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, (dict, types.MappingProxyType)):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if dataclasses.is_dataclass(a):
        return all(
            same(getattr(a, f.name), getattr(b, f.name)) for f in dataclasses.fields(a)
        )
    if hasattr(a, "portmap"):  # network.Instance
        return a.name == b.name and same(a.of, b.of) and a.portmap == b.portmap
    return a == b


def _builds():
    out = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name in cli.list_builtin_designs():
            cls = type(cli.get_builder(name)())
            variants = [v for v in cli.list_variants(cls) if v != "default"]
            out += [(name, cls, v) for v in ["default", *variants]]
    return out


BUILDS = _builds()


@pytest.mark.parametrize(
    "name, cls, variant", BUILDS, ids=[f"{n}:{v}" for n, _, v in BUILDS]
)
def test_every_catalog_design_round_trips_as_data(name, cls, variant):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        b = cls(resolve_variant_params(cls, variant))
        snap = dd.snapshot(b)
        wire = json.loads(json.dumps(snap, allow_nan=False))
        for hook, data in wire.items():
            assert "__error__" not in (data if isinstance(data, dict) else {}), (
                hook,
                data,
            )
            back = dd.decode(data)
            assert same(back, getattr(b, hook)()), hook
            assert dd.encode(back) == data, hook  # and it re-encodes to the same data


@pytest.mark.parametrize(
    "name, cls", sorted({(n, c) for n, c, _ in BUILDS}, key=lambda x: x[0])[:40]
)
def test_a_designs_static_part_round_trips(name, cls):
    s = json.loads(json.dumps(dd.static(cls), allow_nan=False))
    assert same(dd.decode(s["default_params"]), cls.default_params)
    for v, data in s["variants"].items():
        assert same(dd.decode(data), getattr(cls, f"{v}_params"))


def test_a_touchstone_block_round_trips():
    from antennaknobs.network import TouchstoneTwoPort
    from antennaknobs.touchstone import parse_touchstone

    text = "# MHz S RI R 50\n" + "".join(
        f"{f} 0.1 0.02 0.9 -0.1 0.9 -0.1 0.2 0.01\n" for f in (3.0, 7.0, 14.0, 30.0)
    )
    block = TouchstoneTwoPort("a", "b", parse_touchstone(text, nports=2))
    data = json.loads(json.dumps(dd.encode([block]), allow_nan=False))
    assert same(dd.decode(data), [block])


def test_non_finite_floats_and_odd_keys_survive():
    o = {
        "x": (float("inf"), float("-inf"), float("nan")),
        3: np.float32(1.5),
        ("a", 1): np.array([[1 + 2j, np.nan]]),
        "__looks_like_a_tag": 1,
    }
    data = json.loads(json.dumps(dd.encode(o), allow_nan=False))
    assert same(dd.decode(data), o)


@pytest.mark.parametrize(
    "bad",
    [
        {"__dc__": "subprocess:Popen", "fields": {}},  # not an allowed module
        {"__dc__": "builtins:eval", "fields": {}},
        {"__nt__": "os:system", "values": ["true"]},
        {
            "__dc__": "antennaknobs.cli:main",
            "fields": {},
        },  # allowed package, not an allowed module
        {"__ndarray__": "|O", "shape": [1], "data": [None]},  # object dtype
        {"__npscalar__": "|O", "v": 1},
        {
            "__dc__": "antennaknobs.mw.networks._spec:TL",
            "fields": {"a": "x", "b": "y", "z0": 50, "length": 1.0, "evil": 1},
        },
        {"__float__": "1e999"},
        {"__mystery__": 1},
        {"__ndarray__": "<f8", "shape": [3], "data": [1.0]},  # does not fill its shape
    ],
)
def test_decode_refuses_what_is_not_design_data(bad):
    with pytest.raises(dd.DesignDataError):
        dd.decode(bad)


def test_decode_refuses_runaway_nesting():
    d = 1
    for _ in range(dd._MAX_DEPTH + 5):
        d = [d]
    with pytest.raises(dd.DesignDataError):
        dd.decode(d)


def test_the_allowlist_holds_only_spec_types():
    allowed = dd.allowed_types()
    assert allowed, "no allowed types"
    for key, cls in allowed.items():
        mod = key.split(":")[0]
        assert mod in dd.ALLOWED_MODULES, key
    assert "antennaknobs.mw.networks._spec:TL" in allowed
    assert "antennaknobs.network:Instance" in allowed


def test_encode_refuses_what_it_cannot_describe():
    with pytest.raises(TypeError, match="is not design data"):
        dd.encode(object())
    with pytest.raises(TypeError, match="is not design data"):
        dd.encode(lambda: 1)


@pytest.mark.parametrize(
    "name",
    ["dipoles.folded_invvee_balun", "loops.skyloop_lmatch", "arrays.bowtie1x2_bl"],
)
def test_a_decoded_design_solves_bit_for_bit_like_the_original(name):
    """What crosses the boundary is what the engine needs: the decoded wires
    and network give exactly the original's impedance."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cls = type(cli.get_builder(name)())
        snap = json.loads(json.dumps(dd.snapshot(cls()), allow_nan=False))
        wires, net = dd.decode(snap["build_wires"]), dd.decode(snap["build_network"])

        class FromData(cls):
            def build_wires(self):
                return wires

            def build_network(self):
                return net

        engine = cli.make_engine_factory("momwire:bspline", "free")
        f = float(cls.default_params["freq"])
        z_orig = engine(cls()).impedance_sweep([f])
        z_data = engine(FromData()).impedance_sweep([f])
    assert np.array_equal(np.asarray(z_orig), np.asarray(z_data)), (z_orig, z_data)
