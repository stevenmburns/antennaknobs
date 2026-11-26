"""The station rail (docs/design/block-builder.md, "The station rail"): a chain
model of the station between the rig and an antenna's feed, rendered to a
`Network` and to house-style ``build_network()`` source, read back from that
source, and enumerated for the placement gallery.

A CHAIN is plain JSON-shaped data, so a page can hold it and post it back:

    {"rig": "rig", "items": [{"kind": "t_tuner", ...}, {"kind": "cable", ...}]}

``items`` run from the rig towards the antenna. A SERIES item (a line, a
tuner, a balun, an unun) is a two-port; a SHUNT item (a stub) hangs on the
node where it sits in the list, between the series items either side of it.
So the nodes are the gaps between series items: the first is the rig, the
last is the antenna's feed, and each one in between is named after the
series item on its antenna side, the convention the catalog stations follow
(``li`` a line's input, ``bal`` a balun's line side, ``pri`` an unun's
primary). An item may carry the names it resolved to (``name`` for its
instance, ``node`` for the node on its rig side), so that adding or moving
one box renames nothing else; `freeze` writes them.

The chain does not say which antenna it feeds. That is an `Attachment`, made
by `attach` from a built design: which port the chain ends on, and how the
generated file reaches it. Nothing here solves; `antennaknobs.station_rail_solve`
does.
"""

from __future__ import annotations

import ast
import copy
import json
import math
from dataclasses import dataclass

from .network import (
    TL,
    Driven,
    Instance,
    Network,
    PortOnWire,
    PortVirtual,
    as_wire,
    cable_from_catalog,
)
from .station import (
    balun,
    l_network_tuner,
    shunt_open_stub,
    shunt_shorted_stub,
    t_network_tuner,
    unun,
)
from .wire_catalog import CABLES

CHAIN_VERSION = 1


class RailRefusal(ValueError):
    """The rail cannot take this design, chain or file; the message says why."""


# --- components ----------------------------------------------------------------


@dataclass(frozen=True)
class Kind:
    """One component the rail offers. ``params`` are the record's value keys
    in the order the generated call writes them, each with its type (float or
    str). A series kind is a two-port between ``formals``; a shunt kind binds
    ``port``. ``factory`` is the `station` function an `Instance` of it calls;
    the two line kinds have none (they are top-level `TL` branches)."""

    key: str
    series: bool
    params: tuple[tuple[str, type], ...]
    required: tuple[str, ...]
    factory: str | None = None
    formals: tuple[str, str] | None = None
    node_stem: str | None = None
    instance_stem: str | None = None


KINDS = {
    k.key: k
    for k in (
        Kind("cable", True, (("cable", str), ("length_m", float)),
             ("cable", "length_m"), node_stem="li"),
        Kind("line", True, (("z0", float), ("length_m", float), ("vf", float)),
             ("z0", "length_m", "vf"), node_stem="li"),
        Kind("l_tuner", True,
             (("series_l_uH", float), ("shunt_c_pF", float), ("ql", float),
              ("tune_to", float), ("shunt_at", str), ("mode", str)),
             (), "l_network_tuner", ("rig", "out"), "ti", "tuner"),
        Kind("t_tuner", True,
             (("c1_pF", float), ("c2_pF", float), ("l_uH", float), ("ql", float),
              ("tune_to", float), ("c_max_pF", float)),
             (), "t_network_tuner", ("rig", "out"), "ti", "tuner"),
        Kind("balun", True, (("n", float), ("lmag_uH", float), ("qlmag", float)),
             ("n",), "balun", ("line", "ant"), "bal", "balun"),
        Kind("unun", True,
             (("turns", float), ("lmag_uH", float), ("qlmag", float),
              ("comp_c_pF", float)),
             ("turns",), "unun", ("line", "ant"), "pri", "unun"),
        Kind("shorted_stub", False,
             (("freq_mhz", float), ("length_wl", float), ("z0", float),
              ("vf", float), ("cable", str)),
             ("freq_mhz", "length_wl"), "shunt_shorted_stub",
             instance_stem="stub"),
        Kind("open_stub", False,
             (("freq_mhz", float), ("length_wl", float), ("z0", float),
              ("vf", float), ("cable", str)),
             ("freq_mhz", "length_wl"), "shunt_open_stub", instance_stem="stub"),
    )
}  # fmt: skip
_FACTORY_FN = {
    "l_network_tuner": l_network_tuner,
    "t_network_tuner": t_network_tuner,
    "balun": balun,
    "unun": unun,
    "shunt_shorted_stub": shunt_shorted_stub,
    "shunt_open_stub": shunt_open_stub,
}
_KIND_OF_FACTORY = {k.factory: k for k in KINDS.values() if k.factory}
_NODE_NOTE = {
    "li": "line input",
    "ti": "tuner input",
    "bal": "balun line-side terminals",
    "pri": "unun line-side terminals",
}
# The text values that are not names from a catalog: `station.l_network_tuner`
# takes these and nothing else.
_CHOICES = {"shunt_at": ("out", "rig", "auto"), "mode": ("low", "high", "ll", "cc")}
# Keys an item may carry besides its kind's values.
_NAME_KEYS = ("kind", "name", "node")


def kind_of(item: dict) -> Kind:
    try:
        return KINDS[item["kind"]]
    except (KeyError, TypeError):
        raise RailRefusal(
            f"unknown component kind {item.get('kind') if isinstance(item, dict) else item!r}; "
            f"the rail offers {sorted(KINDS)}"
        ) from None


def is_series(item: dict) -> bool:
    return kind_of(item).series


def self_tuning(item: dict) -> bool:
    return item["kind"] in ("l_tuner", "t_tuner") and item.get("tune_to") is not None


def is_balanced_line(item: dict) -> bool:
    if item["kind"] == "cable":
        return CABLES[item["cable"]].z0 >= 300.0
    return item["kind"] == "line" and item["z0"] >= 300.0


def is_coax(item: dict) -> bool:
    return item["kind"] in ("cable", "line") and not is_balanced_line(item)


def describe(item: dict) -> str:
    """A short chip label: "RG-8X 30.5 m", "auto L", "4:1 balun"."""
    k = item["kind"]
    if k == "cable":
        return f"{item['cable']} {item['length_m']:g} m"
    if k == "line":
        return f"{item['z0']:g} Ω line {item['length_m']:g} m"
    if k in ("l_tuner", "t_tuner"):
        letter = "L" if k == "l_tuner" else "T"
        return f"auto {letter}" if self_tuning(item) else f"{letter} tuner"
    if k == "balun":
        return f"{1 / item['n'] ** 2:g}:1 balun"
    if k == "unun":
        return f"{item['turns'] ** 2:g}:1 unun"
    shape = "shorted" if k == "shorted_stub" else "open"
    return f"{shape} stub {item['length_wl']:g} λ"


def _check_item(item, where: str) -> dict:
    """``item`` as a clean record, or RailRefusal naming what is wrong. Values
    are floats or strings by the kind's table; a name the page set must be a
    Python identifier, since it becomes a name in the generated source."""
    if not isinstance(item, dict):
        raise RailRefusal(f"{where}: a component is an object, got {item!r}")
    kind = kind_of(item)
    types = dict(kind.params)
    out = {"kind": kind.key}
    for key, v in item.items():
        if key == "kind" or v is None:
            continue
        if key in ("name", "node"):
            if not isinstance(v, str) or not v.isidentifier():
                raise RailRefusal(f"{where}: {key} {v!r} is not a Python identifier")
            out[key] = v
            continue
        if key not in types:
            raise RailRefusal(
                f"{where}: {kind.key} has no value {key!r}; it takes {sorted(types)}"
            )
        if types[key] is float:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise RailRefusal(f"{where}: {key} must be a number, got {v!r}")
            if not math.isfinite(v):
                raise RailRefusal(f"{where}: {key} must be finite, got {v!r}")
            out[key] = float(v)
        else:
            if not isinstance(v, str):
                raise RailRefusal(f"{where}: {key} must be text, got {v!r}")
            if key in _CHOICES and v not in _CHOICES[key]:
                raise RailRefusal(
                    f"{where}: {key} is one of {', '.join(_CHOICES[key])}, got {v!r}"
                )
            out[key] = v
    missing = [p for p in kind.required if p not in out]
    if missing:
        raise RailRefusal(f"{where}: {kind.key} needs {', '.join(missing)}")
    if "cable" in out and out["cable"] not in CABLES:
        raise RailRefusal(
            f"{where}: unknown cable {out['cable']!r}; have {sorted(CABLES)}"
        )
    if "length_m" in out and out["length_m"] <= 0.0:
        raise RailRefusal(f"{where}: length_m must be positive")
    return out


def check_chain(chain) -> dict:
    """``chain`` validated and normalised (floats, known keys, identifier
    names), or RailRefusal. A page's chain arrives as JSON, so every field is
    checked here before anything is built from it."""
    if not isinstance(chain, dict):
        raise RailRefusal(f"a chain is an object, got {chain!r}")
    extra = set(chain) - {"version", "rig", "items"}
    if extra:
        raise RailRefusal(f"a chain has no field {sorted(extra)[0]!r}")
    version = chain.get("version", CHAIN_VERSION)
    if version != CHAIN_VERSION:
        raise RailRefusal(f"chain version {version!r}; this rail reads {CHAIN_VERSION}")
    rig = chain.get("rig") or "rig"
    if not isinstance(rig, str) or not rig.isidentifier():
        raise RailRefusal(f"rig {rig!r} is not a Python identifier")
    items = chain.get("items", [])
    if not isinstance(items, list):
        raise RailRefusal("a chain's items are a list")
    return {
        "version": CHAIN_VERSION,
        "rig": rig,
        "items": [_check_item(it, f"item {i}") for i, it in enumerate(items)],
    }


# The palette: one template per offered component. Stub frequencies are
# filled from the design at use (`palette_item`).
PALETTE = {
    "coax": {"kind": "cable", "cable": "RG-8X", "length_m": 30.48},
    "ladder": {"kind": "cable", "cable": "openwire-600", "length_m": 20.0},
    "line": {"kind": "line", "z0": 75.0, "length_m": 5.0, "vf": 0.66},
    "auto_l": {"kind": "l_tuner", "tune_to": 50.0, "shunt_at": "auto", "ql": 200.0},
    "auto_t": {"kind": "t_tuner", "tune_to": 50.0, "ql": 200.0, "c_max_pF": 500.0},
    "t_tuner": {
        "kind": "t_tuner",
        "c1_pF": 81.2,
        "c2_pF": 500.0,
        "l_uH": 4.218,
        "ql": 200.0,
    },
    "balun_1_1": {"kind": "balun", "n": 1.0, "lmag_uH": 10.0, "qlmag": 100.0},
    "balun_4_1": {"kind": "balun", "n": 0.5, "lmag_uH": 10.0, "qlmag": 100.0},
    "unun_49_1": {
        "kind": "unun",
        "turns": 7.0,
        "lmag_uH": 8.0,
        "qlmag": 10.0,
        "comp_c_pF": 47.0,
    },
    "shorted_stub": {"kind": "shorted_stub", "length_wl": 0.125, "cable": "RG-8X"},
    "open_stub": {"kind": "open_stub", "length_wl": 0.125, "cable": "RG-8X"},
}


def palette_item(key: str, freq_mhz: float) -> dict:
    if key not in PALETTE:
        raise RailRefusal(f"unknown palette entry {key!r}; have {sorted(PALETTE)}")
    item = copy.deepcopy(PALETTE[key])
    if not KINDS[item["kind"]].series:
        item["freq_mhz"] = float(freq_mhz)
    return item


# --- the antenna a chain ends on --------------------------------------------------


@dataclass(frozen=True)
class Attachment:
    """How a chain reaches one design's antenna.

    ``form`` is how the generated file reaches the feed:

    - ``"wire"``: the design has no network and feeds one wire with ``ex``;
      the file's ``build_wires`` turns that wire into the named port ``feed``
      (the `wire.doublet_ladder_tuner` idiom) and the chain ends on it.
    - ``"port"``: the design's network, its station taken off, is just
      ``PortOnWire(feed)``; the file writes that port itself.
    - ``"cut"``: anything else (a port off the wire's middle, an end port, a
      trap or a phasing line the antenna carries): the file keeps the
      design's own network through `plane.antenna_side` and adds the chain.

    ``antenna`` is that antenna-side network at the knobs it was built with
    (form "cut" only). ``replaced`` counts the branches of the design's own
    station the rail stands in for; ``at_feed`` how many of those hang on the
    feed alone (an L network's shunt arm across the feed), which the
    workbench's own measurement plane at the feed keeps and the rail does
    not, so the two read differently there. ``balanced`` is whether the feed is a
    balanced one, None where the rail does not know (the advisories that
    need it stay quiet then).
    """

    design: str
    module: str
    form: str
    feed: str
    balanced: bool | None = None
    antenna: Network | None = None
    replaced: int = 0
    at_feed: int = 0
    reserved: frozenset = frozenset()


# Feeds the rail knows the balance of: the catalog stations its codegen
# targets. Elsewhere it does not guess.
BALANCED = {
    "wire.doublet_ladder_tuner": True,
    "dipoles.invvee_coax_station": True,
    "dipoles.folded_invvee_balun": True,
    "wire.efhw_sloper": False,
    "loops.skyloop_lmatch": True,
}


def attach(design: str, builder, module: str | None = None) -> Attachment:
    """The `Attachment` for a built design, or RailRefusal saying why the
    rail cannot feed it. ``module`` is what the generated file imports the
    antenna from: the catalog path for a catalog design."""
    from .plane import antenna_side, planes_of
    from .schematic import _datum_nodes, terminals_of

    module = module or f"antennaknobs.designs.{design}"
    net = builder.build_network()
    if net is None:
        wires = [as_wire(w) for w in builder.build_wires()]
        fed = [w for w in wires if w.ex is not None]
        if not fed:
            raise RailRefusal("this design has no feed: no wire carries ex")
        if len(fed) > 1:
            raise RailRefusal(
                f"this design is fed at {len(fed)} wires; the rail feeds one"
            )
        names = {w.name for w in wires if w.name}
        feed = fed[0].name or _unique("feed", set(names))
        return Attachment(
            design,
            module,
            "wire",
            feed,
            BALANCED.get(design),
            reserved=frozenset(names),
        )
    if len(net.sources) != 1:
        raise RailRefusal(
            f"this design drives {len(net.sources)} sources; the rail feeds one"
        )
    real = [
        p
        for p in planes_of(net)
        if not isinstance(net.ports[p], PortVirtual) and "." not in p
    ]
    if not real:
        raise RailRefusal(
            "this design's feed is a floating (balanced) port with no reference "
            "terminal; the rail feeds a port it can drive against the datum"
        )
    feed = real[0]
    side = antenna_side(net, feed)
    _station_meets_antenna_at_feed(net, side, feed)
    names = frozenset(side.ports)
    replaced = len(net.branches) - len(side.branches)
    kept = {id(br) for br in side.branches}
    bonded = _datum_nodes(net)
    at_feed = sum(
        1
        for br in net.branches
        if id(br) not in kept
        and feed in terminals_of(br)
        and all(t == feed or t in bonded for t in terminals_of(br))
    )
    plain = (
        not side.branches
        and set(side.ports) == {feed}
        and side.ports[feed] == PortOnWire(feed)
    )
    if plain:
        return Attachment(
            design, module, "port", feed, BALANCED.get(design),
            replaced=replaced, at_feed=at_feed, reserved=names,
        )  # fmt: skip
    return Attachment(
        design, module, "cut", feed, BALANCED.get(design),
        antenna=side, replaced=replaced, at_feed=at_feed, reserved=names,
    )  # fmt: skip


def _station_meets_antenna_at_feed(net: Network, side: Network, feed: str):
    """RailRefusal unless the design's station (what `antenna_side` took off)
    touches the antenna at ``feed`` and the datum only. Otherwise taking it
    off is not taking off a station: a balun into both ends of an end-port
    pair leaves the antenna driven single-ended, and a phasing harness cut at
    one element leaves its other lines on an undriven junction. Both are
    multi-feed designs, which the design note keeps for the free-schematic
    mode."""
    from .schematic import _datum_nodes, terminals_of

    kept = {id(br) for br in side.branches}
    bonded = _datum_nodes(net)
    station_nodes, antenna_nodes = set(), set()
    for br in net.branches:
        ts = {t for t in terminals_of(br) if t not in bonded}
        (antenna_nodes if id(br) in kept else station_nodes).update(ts)
    others = {
        n
        for n in station_nodes - {feed}
        if n in net.ports and not isinstance(net.ports[n], PortVirtual)
    }
    shared = (station_nodes & antenna_nodes) - {feed}
    if others or shared:
        where = sorted(others | shared)
        raise RailRefusal(
            f"this design's own feed network reaches the antenna at {feed} and "
            f"also at {', '.join(where)} (a balun into an end-port pair, or a "
            "phasing harness): it is a multi-feed design, and the rail feeds "
            "one port; taking that network off would change the antenna"
        )


def wires_for(att: Attachment, wires) -> list:
    """The design's wires with the fed wire as the named port (form "wire"):
    what the generated ``build_wires`` returns."""
    out = []
    for w in map(as_wire, wires):
        if w.ex is not None:
            out.append(w._replace(ex=None, name=att.feed))
        else:
            out.append(w)
    return out


# --- naming --------------------------------------------------------------------


def _unique(stem: str, taken: set) -> str:
    name, i = stem, 2
    while name in taken:
        name, i = f"{stem}{i}", i + 1
    taken.add(name)
    return name


def layout(chain: dict, att: Attachment):
    """Resolve the chain's names: ``(nodes, placed)``.

    ``nodes`` lists the node names rig → feed (just the feed when there is no
    series item, the rig and the feed being one node then). ``placed`` holds,
    per item in order, ``(item, instance_name_or_None, a, b)``: a series item
    sits between nodes ``a`` (rig side) and ``b``; a shunt item at ``a``
    (``b`` None). A generated name keeps clear of every name the antenna's
    own network already uses."""
    rig, feed = chain.get("rig") or "rig", att.feed
    items = chain["items"]
    series_idx = [i for i, it in enumerate(items) if is_series(it)]
    inner = series_idx[1:]  # the series items whose rig side is a new node
    taken = {rig, feed} | set(att.reserved)
    taken |= {items[i]["node"] for i in inner if items[i].get("node")}
    nodes = [rig] if series_idx else [feed]
    for i in inner:
        nodes.append(
            items[i].get("node") or _unique(KINDS[items[i]["kind"]].node_stem, taken)
        )
    if series_idx:
        nodes.append(feed)
    if len(set(nodes)) != len(nodes):
        dup = sorted({n for n in nodes if nodes.count(n) > 1})[0]
        raise RailRefusal(f"two nodes are named {dup!r}")
    if rig in att.reserved and series_idx:
        raise RailRefusal(f"the rig node {rig!r} is a name the antenna already uses")
    inst_taken = {it["name"] for it in items if it.get("name")}
    placed, k = [], 0  # k: index of the node the walk is at
    for it in items:
        kind = KINDS[it["kind"]]
        name = None
        if kind.instance_stem:
            name = it.get("name") or _unique(kind.instance_stem, inst_taken)
        if kind.series:
            placed.append((it, name, nodes[k], nodes[k + 1]))
            k += 1
        else:
            placed.append((it, name, nodes[k], None))
    names = [n for _it, n, _a, _b in placed if n]
    if len(set(names)) != len(names):
        dup = sorted({n for n in names if names.count(n) > 1})[0]
        raise RailRefusal(f"two components are named {dup!r}")
    return nodes, placed


def freeze(chain: dict, att: Attachment, extra: dict | None = None):
    """``(chain, extra)``: a copy of ``chain`` whose items carry the names
    they resolve to now, and a copy of ``extra`` (an item about to be added)
    with a fresh instance name clear of them, so the edit that follows renames
    nothing else. The first series item has no node of its own yet (its rig
    side is the rig) and gets one generated if something is put in front."""
    chain = copy.deepcopy(chain)
    nodes, placed = layout(chain, att)
    taken_names = {name for _it, name, _a, _b in placed if name}
    for it, name, a, _b in placed:
        if name:
            it["name"] = name
        if is_series(it) and a != nodes[0]:
            it["node"] = a
    if extra is not None:
        extra = copy.deepcopy(extra)
        stem = KINDS[extra["kind"]].instance_stem
        if stem and not extra.get("name"):
            extra["name"] = _unique(stem, taken_names)
    return chain, extra


def _kwargs(item: dict) -> list[tuple[str, object]]:
    return [(p, item[p]) for p, _t in KINDS[item["kind"]].params if p in item]


# --- to a Network ----------------------------------------------------------------


def _branch(it: dict, name, a, b):
    kind = KINDS[it["kind"]]
    if it["kind"] == "cable":
        return TL.from_cable(cable_from_catalog(it["cable"]), a, b, it["length_m"])
    if it["kind"] == "line":
        return TL(a, b, z0=it["z0"], length=it["length_m"], vf=it["vf"])
    comp = _FACTORY_FN[kind.factory](**dict(_kwargs(it)))
    if b is None:
        return Instance(name, comp, port=a)
    f_rig, f_ant = kind.formals
    return Instance(name, comp, **{f_rig: a, f_ant: b})


def to_network(chain: dict, att: Attachment, *, drive: int = 0) -> Network:
    """The chain's network on the antenna, driven at node ``drive`` (0 the
    rig). Driving a later node leaves out every item on its rig side, the
    shunts AT that node staying: the network a VNA clipped on there, with the
    rig side unscrewed, would measure. Built the way the generated file
    builds it, so solving this is solving the file."""
    nodes, placed = layout(chain, att)
    if not 0 <= drive < len(nodes):
        raise RailRefusal(f"no node {drive} on a chain of {len(nodes)} nodes")
    keep_from, k = 0, 0
    for i, (it, _n, _a, _b) in enumerate(placed):
        if k == drive:
            keep_from = i
            break
        if is_series(it):
            k += 1
    else:
        keep_from = len(placed)
    placed = placed[keep_from:]
    nodes = nodes[drive:]
    branches = [_branch(it, name, a, b) for it, name, a, b in placed]
    ports = {}
    if att.form == "cut":
        ports.update(att.antenna.ports)
        branches = [*att.antenna.branches, *branches]
    else:
        ports[att.feed] = PortOnWire(att.feed)
    for n in reversed(nodes):
        if n != att.feed:
            ports[n] = PortVirtual(n)
    return Network(
        ports=ports,
        branches=branches,
        sources=[Driven(port=nodes[0], voltage=1 + 0j)],
    )


def antenna_network(att: Attachment) -> Network:
    """The antenna alone, driven at its feed: no chain, no shunt at the feed."""
    if att.form == "cut":
        return Network(
            ports=dict(att.antenna.ports),
            branches=list(att.antenna.branches),
            sources=[Driven(port=att.feed, voltage=1 + 0j)],
        )
    return Network(
        ports={att.feed: PortOnWire(att.feed)},
        branches=[],
        sources=[Driven(port=att.feed, voltage=1 + 0j)],
    )


# --- to Python -------------------------------------------------------------------

_LINE = 88


def _lit(v) -> str:
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, (int, float)):
        return repr(float(v))
    # JSON's string escapes are a subset of Python's, and it escapes every
    # control character, so any text is one valid double-quoted literal.
    return json.dumps(str(v), ensure_ascii=False)


@dataclass
class _Call:
    head: str
    args: list  # of (prefix, str | _Call)

    def flat(self) -> str:
        return f"{self.head}(" + ", ".join(_flat(p, v) for p, v in self.args) + ")"


def _flat(prefix, v) -> str:
    return prefix + (v.flat() if isinstance(v, _Call) else v)


def _render(prefix: str, v, indent: int, tail: str = ",") -> list[str]:
    """Lay out ``prefix + v`` the way ruff format would: one line if it fits,
    else the arguments together on one indented line, else one per line."""
    pad = " " * indent
    one = pad + _flat(prefix, v) + tail
    if not isinstance(v, _Call) or len(one) <= _LINE:
        return [one]
    inner = " " * (indent + 4) + ", ".join(_flat(p, a) for p, a in v.args)
    if len(inner) <= _LINE:
        return [pad + prefix + v.head + "(", inner, pad + ")" + tail]
    lines = [pad + prefix + v.head + "("]
    for p, a in v.args:
        lines += _render(p, a, indent + 4)
    return lines + [pad + ")" + tail]


def _imports(names, module) -> list[str]:
    order = sorted(
        set(names), key=lambda n: (0 if n.isupper() else 1 if n[0].isupper() else 2, n)
    )
    one = f"from {module} import " + ", ".join(order)
    if len(one) <= _LINE:
        return [one]
    return [f"from {module} import ("] + [f"    {n}," for n in order] + [")"]


def _branch_call(it: dict, name, a, b) -> _Call:
    kind = KINDS[it["kind"]]
    if it["kind"] == "cable":
        return _Call(
            "TL.from_cable",
            [
                ("", _Call("cable_from_catalog", [("", _lit(it["cable"]))])),
                ("", _lit(a)),
                ("", _lit(b)),
                ("", _lit(it["length_m"])),
            ],
        )
    if it["kind"] == "line":
        return _Call(
            "TL",
            [("", _lit(a)), ("", _lit(b))]
            + [(f"{k}=", _lit(it[p])) for k, p in _LINE_KW],
        )
    comp = _Call(kind.factory, [(f"{p}=", _lit(v)) for p, v in _kwargs(it)])
    if b is None:
        binds = [("port=", _lit(a))]
    else:
        f_rig, f_ant = kind.formals
        binds = [(f"{f_rig}=", _lit(a)), (f"{f_ant}=", _lit(b))]
    return _Call("Instance", [("", _lit(name)), ("", comp)] + binds)


# `TL(...)` keywords for an ideal line, in the order the file writes them.
_LINE_KW = (("z0", "z0"), ("length", "length_m"), ("vf", "vf"))

_WIRES_BODY = """\
    def build_wires(self):
        # The fed wire becomes the named port {feed}; the source moves to
        # the rig, at the other end of the station.
        wires = []
        for w in map(as_wire, super().build_wires()):
            if w.ex is not None:
                wires.append(w._replace(ex=None, name={feed}))
            else:
                wires.append(w)
        return wires
"""
_CUT_LINES = """\
        # The antenna's own network with its station taken off: whatever it
        # carries itself (traps, loads, phasing lines) stays.
        antenna = antenna_side(super().build_network(), {feed})"""


def to_python(chain: dict, att: Attachment) -> str:
    """The chain as a house-style design file: the antenna's class imported,
    subclassed, and its ``build_network()`` written out."""
    nodes, placed = layout(chain, att)
    feed = att.feed
    net_names = {"Driven", "Network"}
    station_names = set()
    branch_lines = []
    if att.form == "cut":
        branch_lines.append(" " * 16 + "*antenna.branches,")
    for it, name, a, b in placed:
        if it["kind"] == "cable":
            net_names |= {"TL", "cable_from_catalog"}
        elif it["kind"] == "line":
            net_names.add("TL")
        else:
            net_names.add("Instance")
            station_names.add(KINDS[it["kind"]].factory)
        branch_lines += _render("", _branch_call(it, name, a, b), 16)

    virtual = [n for n in reversed(nodes) if n != feed]
    if virtual:
        net_names.add("PortVirtual")
    if att.form == "cut":
        entries = [("**", "antenna.ports")]
    else:
        net_names.add("PortOnWire")
        entries = [(f"{_lit(feed)}: ", f"PortOnWire({_lit(feed)})")]
    entries += [(f"{_lit(n)}: ", f"PortVirtual({_lit(n)})") for n in virtual]
    if att.form == "wire":
        net_names.add("as_wire")

    def note(n):
        return _NODE_NOTE.get(n.rstrip("0123456789"))

    one = " " * 12 + "ports={" + ", ".join(k + v for k, v in entries) + "},"
    noted = [n for n in virtual if note(n)]
    if len(one) <= _LINE and not noted:
        port_lines = [one]
    else:
        port_lines = [" " * 12 + "ports={"]
        # The first entry is the feed (or the antenna's own ports), never noted.
        for (k, v), n in zip(entries, [None, *virtual], strict=True):
            tail = f"  # {note(n)}" if n and note(n) else ""
            port_lines.append(" " * 16 + f"{k}{v}," + tail)
        port_lines.append(" " * 12 + "},")

    lines = [f"from {att.module} import Builder as Antenna"]
    lines += _imports(net_names, "antennaknobs.network")
    if att.form == "cut":
        lines.append("from antennaknobs.plane import antenna_side")
    if station_names:
        lines += _imports(station_names, "antennaknobs.station")
    lines += ["", "", "class Builder(Antenna):"]
    if att.form == "wire":
        lines += _WIRES_BODY.format(feed=_lit(feed)).splitlines() + [""]
    lines.append("    def build_network(self):")
    if att.form == "cut":
        lines += _CUT_LINES.format(feed=_lit(feed)).splitlines()
    lines += [
        "        return Network(",
        *port_lines,
        " " * 12 + "branches=[",
        *branch_lines,
        " " * 12 + "],",
        " " * 12 + f"sources=[Driven(port={_lit(nodes[0])}, voltage=1 + 0j)],",
        "        )",
    ]
    return "\n".join(lines) + "\n"


# --- reading the house style back --------------------------------------------------


def _refuse_at(node, why: str):
    line = getattr(node, "lineno", None)
    raise RailRefusal(f"line {line}: {why}" if line else why)


def _literal(node, text: str):
    """A number or a string literal, or RailRefusal: the rail reads only
    values it can put on a box, never an expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        if isinstance(node.value, bool):
            _refuse_at(node, f"{node.value!r} is not a value the rail reads")
        return float(node.value) if not isinstance(node.value, str) else node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) in (int, float)
    ):
        return -float(node.operand.value)
    src = ast.get_source_segment(text, node) or ast.dump(node)
    _refuse_at(
        node,
        f"{src} is not a literal value; the rail reads numbers and strings, "
        "not expressions or knob references",
    )


def _call_name(node) -> str | None:
    f = node.func if isinstance(node, ast.Call) else None
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f"{f.value.id}.{f.attr}"
    return None


def _read_branch(node, text: str):
    """One generated branch as ``(item, name, a, b)``."""
    head = _call_name(node)
    if head == "TL.from_cable":
        if node.keywords or len(node.args) != 4:
            _refuse_at(node, "TL.from_cable takes (cable, a, b, length) here")
        cab = node.args[0]
        if _call_name(cab) != "cable_from_catalog" or len(cab.args) != 1:
            _refuse_at(cab, "a cable is cable_from_catalog(<name>) here")
        a, b = (_literal(x, text) for x in node.args[1:3])
        item = {
            "kind": "cable",
            "cable": _literal(cab.args[0], text),
            "length_m": _literal(node.args[3], text),
        }
        return item, None, a, b
    if head == "TL":
        if len(node.args) != 2:
            _refuse_at(node, "an ideal line is TL(a, b, z0=, length=, vf=) here")
        a, b = (_literal(x, text) for x in node.args)
        kw = {k.arg: _literal(k.value, text) for k in node.keywords}
        back = {k: p for k, p in _LINE_KW}
        if set(kw) != set(back):
            _refuse_at(node, f"an ideal line gives exactly {sorted(back)}")
        item = {"kind": "line", **{back[k]: v for k, v in kw.items()}}
        return item, None, a, b
    if head == "Instance":
        if len(node.args) != 2:
            _refuse_at(node, 'an Instance is Instance("name", factory(...), ...) here')
        name = _literal(node.args[0], text)
        comp = node.args[1]
        kind = _KIND_OF_FACTORY.get(_call_name(comp))
        if kind is None:
            _refuse_at(
                comp,
                f"{_call_name(comp) or 'this'} is not a component the rail offers; "
                f"it reads {sorted(_KIND_OF_FACTORY)}",
            )
        if comp.args:
            _refuse_at(comp, f"{kind.factory} takes keyword values here")
        item = {"kind": kind.key}
        for k in comp.keywords:
            if k.arg is None:
                _refuse_at(comp, f"{kind.factory}(**...) is not read")
            item[k.arg] = _literal(k.value, text)
        binds = {k.arg: _literal(k.value, text) for k in node.keywords}
        if kind.series:
            if set(binds) != set(kind.formals):
                _refuse_at(node, f"{kind.factory} binds {list(kind.formals)}")
            return item, name, binds[kind.formals[0]], binds[kind.formals[1]]
        if set(binds) != {"port"}:
            _refuse_at(node, f"{kind.factory} binds port=")
        return item, name, binds["port"], None
    _refuse_at(node, "this branch is not one the rail writes")


def _norm_dump(tree) -> list:
    """The tree's nodes in walk order, with numbers as floats: what two files
    must share to say the same thing (layout and comments drop out)."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            out.append(("Constant", float(n.value), getattr(n, "lineno", None)))
            continue
        fields = tuple(
            (f, v)
            for f, v in ast.iter_fields(n)
            if not isinstance(v, (ast.AST, list)) and f not in ("ctx", "kind")
        )
        out.append((type(n).__name__, fields, getattr(n, "lineno", None)))
    return out


def read_python(text: str):
    """``(chain, antenna)`` from a file in the rail's house style, where
    ``antenna`` is ``{"module", "form", "feed"}``; RailRefusal with the reason
    for anything else. Read through `ast` only, never run. The rule is the
    block builder's round trip: a file reads back only if the rail, given the
    chain it reads, writes the same program (layout and comments aside), so a
    hand edit outside the style is refused, never guessed at."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise RailRefusal(f"line {e.lineno}: not Python ({e.msg})") from None
    imports = [s for s in tree.body if isinstance(s, ast.ImportFrom)]
    classes = [s for s in tree.body if isinstance(s, ast.ClassDef)]
    for s in tree.body:
        if not isinstance(s, (ast.ImportFrom, ast.ClassDef)):
            _refuse_at(s, "the rail's files hold imports and one class, nothing else")
    first = imports[0] if imports else None
    if (
        first is None
        or [(a.name, a.asname) for a in first.names] != [("Builder", "Antenna")]
        or not first.module
    ):
        raise RailRefusal(
            "the file must start by importing the antenna: "
            "from <design> import Builder as Antenna"
        )
    module = first.module
    if len(classes) != 1 or classes[0].name != "Builder":
        raise RailRefusal("the rail's files hold one class, Builder(Antenna)")
    cls = classes[0]
    if [_name_of(b) for b in cls.bases] != ["Antenna"] or cls.keywords:
        _refuse_at(cls, "the class is Builder(Antenna)")
    methods = {}
    for s in cls.body:
        if not isinstance(s, ast.FunctionDef) or s.name not in (
            "build_wires",
            "build_network",
        ):
            _refuse_at(s, "the rail writes build_network (and build_wires) only")
        methods[s.name] = s
    if "build_network" not in methods:
        raise RailRefusal("the class has no build_network")
    body = methods["build_network"].body
    form = "wire" if "build_wires" in methods else "port"
    feed = None
    if len(body) == 2 and isinstance(body[0], ast.Assign):
        form = "cut"
        call = body[0].value
        if _call_name(call) != "antenna_side" or len(call.args) != 2:
            _refuse_at(
                body[0], "the antenna is antenna_side(super().build_network(), feed)"
            )
        feed = _literal(call.args[1], text)
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        _refuse_at(methods["build_network"], "build_network returns one Network(...)")
    net = body[0].value
    if _call_name(net) != "Network" or net.args:
        _refuse_at(net, "build_network returns Network(ports=, branches=, sources=)")
    kw = {k.arg: k.value for k in net.keywords}
    if set(kw) != {"ports", "branches", "sources"}:
        _refuse_at(net, "Network takes ports=, branches= and sources= here")
    if not isinstance(kw["ports"], ast.Dict):
        _refuse_at(kw["ports"], "ports is a dict literal")
    if feed is None:
        for k, v in zip(kw["ports"].keys, kw["ports"].values, strict=True):
            if k is not None and _call_name(v) == "PortOnWire":
                feed = _literal(k, text)
                break
        else:
            _refuse_at(kw["ports"], "no PortOnWire for the feed")
    if not isinstance(kw["branches"], ast.List):
        _refuse_at(kw["branches"], "branches is a list literal")
    src = kw["sources"]
    if (
        not isinstance(src, ast.List)
        or len(src.elts) != 1
        or _call_name(src.elts[0]) != "Driven"
    ):
        _refuse_at(src, "sources is [Driven(port=..., voltage=1 + 0j)]")
    drive = {k.arg: k.value for k in src.elts[0].keywords}
    if "port" not in drive:
        _refuse_at(src, "Driven names its port=")
    rig = _literal(drive["port"], text)
    items = []
    for el in kw["branches"].elts:
        if isinstance(el, ast.Starred):
            continue  # *antenna.branches; the compare below checks its place
        item, name, a, b = _read_branch(el, text)
        if name is not None:
            item["name"] = name
        if b is not None and a != rig:
            item["node"] = a
        items.append(item)
    if not any(KINDS.get(it["kind"]) and KINDS[it["kind"]].series for it in items):
        rig = "rig"  # no series item: the rig is the feed, and its name unused
    chain = check_chain({"rig": rig, "items": items})
    att = Attachment("", module, form, feed)
    try:
        again = to_python(chain, att)
    except RailRefusal as e:
        raise RailRefusal(f"the chain this file spells is not one: {e}") from None
    mine, theirs = _norm_dump(ast.parse(again)), _norm_dump(tree)
    for m, t in zip(mine, theirs, strict=False):
        if m[:2] != t[:2]:
            line = t[2] or "?"
            raise RailRefusal(
                f"line {line}: not the rail's house style (it writes "
                f"{m[0]} where this file has {t[0]}); the rail reads back only "
                "the files it writes, so this one is shown, not put on the rail"
            )
    if len(mine) != len(theirs):
        raise RailRefusal(
            "not the rail's house style: the file has "
            f"{'more' if len(theirs) > len(mine) else 'less'} than the rail writes"
        )
    return chain, {"module": module, "form": form, "feed": feed}


def _name_of(node) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


# --- placements --------------------------------------------------------------------


def _node_label(chain: dict, att: Attachment, pos: int) -> str:
    """Where list position ``pos`` (an insertion point) sits, in words."""
    nodes, _placed = layout(chain, att)
    k = sum(1 for it in chain["items"][:pos] if is_series(it))
    if k == 0:
        return "at the rig" if len(nodes) > 1 else "at the feed"
    if k == len(nodes) - 1:
        return "at the feed"
    return f"at {nodes[k]}"


def _between_label(chain: dict, pos: int) -> str:
    # The nearest neighbours, a stub included: either side of a stub is a
    # different card, and the label has to tell them apart.
    items = chain["items"]
    before = items[pos - 1] if pos > 0 else None
    after = items[pos] if pos < len(items) else None
    if before is None and after is None:
        return "between the rig and the antenna"
    if before is None:
        return f"at the rig, before {describe(after)}"
    if after is None:
        return f"at the antenna, after {describe(before)}"
    return f"between {describe(before)} and {describe(after)}"


def advisories(chain: dict, att: Attachment) -> list[str]:
    """The small rule set for valid-but-questionable stations. The ones that
    need the feed's balance stay quiet where the rail does not know it."""
    series = [it for it in chain["items"] if is_series(it)]
    out = []
    if att.balanced and series and is_coax(series[-1]):
        out.append(
            "coax straight onto a balanced feed: feedline (common-mode) "
            "currents are not modelled"
        )
    for i, it in enumerate(series):
        if is_balanced_line(it) and (i == 0 or is_coax(series[i - 1])):
            out.append(
                f"{describe(it)} driven from an unbalanced port with no balun "
                "or tuner between: common-mode currents are not modelled"
            )
            break
    if att.balanced is True and series and series[-1]["kind"] == "unun":
        out.append("an unun on a balanced feed: a balun is the usual box here")
    if att.balanced is False and series and series[-1]["kind"] == "balun":
        out.append("a balun on an end-fed wire: an unun is the usual box here")
    return out


def refusal(chain: dict, item: dict) -> str | None:
    """Why ``item`` has no valid place in ``chain`` at all, or None."""
    if self_tuning(item) and any(self_tuning(it) for it in chain["items"]):
        return "a network holds one self-tuning tuner; remove the other first"
    return None


def _circuit(chain: dict) -> tuple:
    """What a chain IS electrically, for spotting two placements that build
    the same circuit: names dropped, and runs of one cable merged into one
    length (a coax put just before or just after the same coax is one
    longer coax either way)."""
    out: list = []
    for it in chain["items"]:
        rec = {k: v for k, v in it.items() if k not in ("name", "node")}
        if rec["kind"] == "line":
            key = ("ideal", rec["z0"], rec["vf"])
        elif rec["kind"] == "cable":
            key = ("cable", rec["cable"])
        else:
            out.append(("part", tuple(sorted(rec.items()))))
            continue
        if out and out[-1][:2] == ("line", key):
            out[-1] = ("line", key, out[-1][2] + rec["length_m"])
        else:
            out.append(("line", key, rec["length_m"]))
    return tuple(out)


def placements(chain: dict, att: Attachment, item: dict) -> list[dict]:
    """Every valid place ``item`` can go in ``chain``, as cards without
    numbers: ``{"pos", "where", "chain", "advisories"}``. A series item goes
    at every list position (beside a shunt, either side of it is a different
    circuit); a shunt item at every node once (stubs on one node commute, so
    a position right after another shunt repeats the one before it). Two
    positions that build the same circuit are offered once."""
    if refusal(chain, item) is not None:
        return []
    chain, item = freeze(chain, att, item)
    items = chain["items"]
    before = set(advisories(chain, att))
    cards = []
    seen = set()
    for pos in range(len(items) + 1):
        if not is_series(item) and pos > 0 and not is_series(items[pos - 1]):
            continue
        new = dict(chain, items=items[:pos] + [copy.deepcopy(item)] + items[pos:])
        circuit = _circuit(new)
        if circuit in seen:
            continue  # the same circuit as a card already offered
        seen.add(circuit)
        where = (
            _between_label(chain, pos)
            if is_series(item)
            else _node_label(chain, att, pos)
        )
        cards.append(
            {
                "pos": pos,
                "where": where,
                "chain": new,
                "advisories": [a for a in advisories(new, att) if a not in before],
            }
        )
    return cards


# --- the chains a design starts with ------------------------------------------------


def _q(v):
    return float(v) if v and v > 0 else None


def _catalog_items(design: str, b) -> tuple[str, list[dict]] | None:
    """``(rig, items)`` reproducing a catalog design's own station, read off
    the builder's knobs; None for a design the rail has no reading of."""
    if design == "dipoles.invvee_coax_station":
        return "rig", [{"kind": "cable", "cable": b.cable, "length_m": b.line_len_m}]
    if design == "dipoles.folded_invvee_balun":
        return "rig", [
            {"kind": "cable", "cable": b.cable, "length_m": b.line_len_m},
            {"kind": "balun", "n": b.balun_n, "lmag_uH": b.lmag_uH, "qlmag": _q(b.qlmag)},
        ]  # fmt: skip
    if design == "wire.efhw_sloper":
        from .designs.wire.efhw_sloper import UNUN_TURNS

        return "rig", [
            {"kind": "cable", "cable": b.cable, "length_m": b.line_len_m},
            {
                "kind": "unun",
                "turns": UNUN_TURNS[b.unun_ratio],
                "lmag_uH": b.lmag_uH,
                "qlmag": _q(b.qlmag),
                "comp_c_pF": _q(b.comp_c_pF),
            },
        ]
    if design == "wire.doublet_ladder_tuner":
        return "rig", [
            {
                "kind": "t_tuner",
                "c1_pF": b.series_c1_pF,
                "c2_pF": b.series_c2_pF,
                "l_uH": b.shunt_l_uH,
                "ql": _q(b.coil_q),
            },
            {"kind": "cable", "cable": "openwire-600", "length_m": b.line_len_m},
        ]
    if design == "loops.skyloop_lmatch":
        return "in", [
            {
                "kind": "l_tuner",
                "name": "match",
                "series_l_uH": b.series_L_uH,
                "shunt_c_pF": b.shunt_C_pF,
                "ql": _q(b.coil_q),
            }
        ]
    return None


CATALOG_STATIONS = (
    "dipoles.invvee_coax_station",
    "dipoles.folded_invvee_balun",
    "wire.efhw_sloper",
    "wire.doublet_ladder_tuner",
    "loops.skyloop_lmatch",
)
# A design without a station of its own the rail can read starts on the
# design note's first station template, "Dipole on coax": 100 ft of RG-8X.
DEFAULT_ITEMS = ({"kind": "cable", "cable": "RG-8X", "length_m": 30.48},)


def starting_chain(att: Attachment, builder) -> tuple[dict, str]:
    """``(chain, origin)``: the design's own station as a chain where the rail
    can read it ("design"), else the default chain ("default")."""
    got = _catalog_items(att.design, builder)
    if got is not None:
        rig, items = got
        return check_chain({"rig": rig, "items": items}), "design"
    return check_chain({"rig": "rig", "items": list(copy.deepcopy(DEFAULT_ITEMS))}), (
        "default"
    )
