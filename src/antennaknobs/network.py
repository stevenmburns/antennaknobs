"""The authoring HIERARCHY over `momwire.networks`, and the compatibility
shim for everything that moved down there.

The circuit spec this module used to hold — the port types, the eleven branch
dataclasses, the sources, the RLC helpers and the flat `Network` container —
now lives in `momwire.networks` (momwire#456 workstream 2, phase B; design
record: momwire ``docs/design/networks-move-into-the-engine.md``). Two of the
three drop-in seams momwire stands at emit ``TL``/``NT`` cards and both NEC-2
and NEC-5 serve networks natively, so the network solve belongs to the engine.
Everything moved is re-exported here verbatim, so every existing
``from antennaknobs.network import TL, Driven, PortOnWire, ...`` keeps
working and every re-exported name IS the momwire object (``antennaknobs.
network.TL is momwire.networks.TL``).

What is genuinely still first-party here is the design-AUTHORING hierarchy,
which momwire deliberately does not adopt:

* `Composite` — a reusable sub-network template (issue #489),
* `Instance` — one instantiation of one, with a formal/actual port map,
* `Network` — a SUBCLASS of `momwire.networks.Network` that flattens those
  instances (namespacing internals, resolving aliases, merging sources,
  filling ``branch_paths``/``composites``) and then hands the resulting FLAT
  spec to the parent for validation.

So antennaknobs flattens BEFORE momwire ever sees a network, and the private
``_branch_port_refs``/``_rewrite_branch`` reach-through that flattening needs
never crosses the boundary in the other direction.

Two constructors changed spelling in the move, because they need catalogs
momwire does not ship — both now live with the stock they resolve, in
`wire_catalog`, and are re-exported here:

* ``BalancedLine.from_geometry(...)`` → `balanced_line_from_geometry(...)`;
* ``TL.from_cable("RG-8X", ...)`` → ``TL.from_cable(cable_from_catalog(
  "RG-8X"), ...)`` — a bare name now raises an actionable `TypeError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# The circuit spec and the solve, re-exported (momwire#456 ws2 phase B). The
# `Network` name is claimed by the hierarchy subclass below, so the flat
# container arrives under a private alias.
from momwire.networks import (  # noqa: F401
    TL,
    Admittance,
    AdmittanceData,
    Autotransformer,
    BalancedLine,
    Branch,
    Cable,
    Driven,
    DrivenCurrent,
    FloatingBalun,
    Load,
    Port,
    PortAtEdge,
    PortAtEnd,
    PortAtVertex,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Shunt,
    Source,
    TouchstoneLoad,
    TouchstoneTwoPort,
    Transformer,
    TwoPort,
    load_impedance,
    load_series_admittance,
)
from momwire.networks import Network as _FlatNetwork

# Private helpers that were importable from here before the move: the two the
# flattening below actually calls, plus the two RLC primitives designs and
# tests reach for. Re-exported so nothing had to churn in the move PR.
from momwire.networks._reduce import _series_rlc_impedance  # noqa: F401
from momwire.networks._spec import (  # noqa: F401
    _branch_port_refs,
    _parallel_rlc_admittance,
    _rewrite_branch,
)

# Wire/cable stock split out in momwire#456 ws2 phase A, and joined in phase B
# by the two constructors that need a catalog (`cable_from_catalog`,
# `balanced_line_from_geometry`) plus the two-wire geometry they use.
# Re-exported here so every existing `from antennaknobs.network import Wire,
# CABLES, two_wire_params, ...` keeps working.
from .wire_catalog import (  # noqa: F401
    CABLES,
    COPPER_CONDUCTIVITY,
    ETA0,
    WIRES,
    GradedSegments,
    Wire,
    WireSpec,
    _conductor_geometry,
    as_wire,
    balanced_line_from_geometry,
    cable_from_catalog,
    graded_wire,
    two_wire_params,
    validate_named_wires_referenced,
    wire_from_catalog,
)


# ---------------------------------------------------------------------------
# Composite components (issue #489): reusable sub-networks with hierarchy
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Composite:
    """A reusable sub-network template: a formal port interface plus a body
    of branches (and, optionally, nested :class:`Instance` s) that reference
    either those formal ports or private internal nodes.

    Design record: issue #489. The model follows the convergent shape of
    the HCL survey there ("generators are code, modules are data", Hdl21):
    a Composite is plain data; *factory functions* like
    ``station.t_network_tuner(...)`` are the parameter mechanism, so there
    is no template registry and no formal-parameter machinery — Python
    call arguments are the parameter list.

    - ``ports`` are the formal external ports. At instantiation each formal
      is bound to a name in the parent's namespace (`Instance` kwargs — the
      Verilog named port map).
    - Any other name a body branch references is an internal node, private
      to the instance: expansion namespaces it as ``"<instance>.<name>"``
      and declares it as a `PortVirtual` automatically. Internals cannot be
      referenced from outside (boundary hygiene — the ROHD lesson).
    - ``aliases`` merge two of the composite's own names into one electrical
      node (union-find at expansion). This is how a body connects a formal
      directly to another formal (a pass-through such as ``station.bypass()``)
      or surfaces one internal node under several formal names — cases a
      branch body cannot express (see the #489 aliasing note). SPICE's
      0 V-source idiom is deliberately NOT the mechanism: aliasing is a
      naming fact, not an element.
    - Bodies contain only branches and nested instances. Sources (`Driven`)
      and geometry ports live at the top level of the design's `Network`.

    Hierarchy is antennaknobs' half of the momwire#456 ws2 split: momwire's
    `Network` is flat and knows nothing of composites.
    """

    ports: tuple[str, ...]
    branches: tuple = ()
    aliases: tuple[tuple[str, str], ...] = ()
    #: How this box DRAWS (issue #652): a tuple of `schematic.Element`, or a
    #: zero-argument callable returning one. Optional — a box without it falls
    #: back to per-branch default symbols, which is a picture but an anonymous
    #: one. Written with `schematic.series` / `shunt`, which are plain data, so
    #: declaring one costs this module no drawing-library import.
    schematic: object = None

    def __post_init__(self):
        if len(set(self.ports)) != len(self.ports):
            raise ValueError(f"duplicate formal port in {self.ports!r}")
        for item in self.branches:
            if not isinstance(item, (*Branch.__args__, Instance)):
                raise ValueError(
                    f"Composite bodies hold branches or Instances, got {item!r}"
                    " (sources and geometry ports belong in the Network)"
                )


class Instance:
    """One instantiation of a :class:`Composite` inside a `Network` (or
    inside another Composite): ``Instance("tuner1", t_network_tuner(...),
    rig="rig", out="li")``.

    - ``name`` becomes the namespace prefix for the composite's internal
      nodes (``"tuner1.m"``) and the power-budget attribution path.
    - Keyword arguments are the formal/actual port map: every formal port
      of the composite must be bound to a port name in the parent's
      namespace (binding one actual to several formals is legal and simply
      fuses them). Missing or extra formals raise immediately.
    """

    def __init__(self, name: str, of: Composite, **portmap: str):
        if not name or "." in name:
            raise ValueError(
                f"instance name {name!r} must be non-empty and contain no '.'"
                " (dots are the namespace separator)"
            )
        formals, bound = set(of.ports), set(portmap)
        if formals != bound:
            missing, extra = formals - bound, bound - formals
            raise ValueError(
                f"instance {name!r} port map mismatch:"
                + (f" missing formals {sorted(missing)}" if missing else "")
                + (f" unknown formals {sorted(extra)}" if extra else "")
                + f"; composite ports are {of.ports!r}"
            )
        self.name = name
        self.of = of
        self.portmap = dict(portmap)


def _expand_instance(
    inst, formal_to_final, prefix, flat, paths, aliases, internals, composites=None
):
    """Recursively flatten ``inst`` into ``flat``/``paths``, collecting alias
    pairs and auto-created internal node names. ``formal_to_final`` maps the
    composite's formals to FINAL (fully resolved) names; ``prefix`` is the
    instance path ("tuner1." / "sta.tuner1.")."""

    def resolve(n):
        if n in formal_to_final:
            return formal_to_final[n]
        final = prefix + n
        internals.add(final)
        return final

    if composites is not None:
        # Keep the Composite that produced these branches, keyed by the same
        # path `branch_paths` uses. Flattening otherwise erases every trace of
        # the box, which is exactly what a schematic (issue #652) needs: the
        # author's fragment lives on the Composite, not on its branches.
        composites[prefix] = inst.of
    for item in inst.of.branches:
        if isinstance(item, Instance):
            child_map = {f: resolve(a) for f, a in item.portmap.items()}
            _expand_instance(
                item, child_map, prefix + item.name + ".",
                flat, paths, aliases, internals, composites,
            )  # fmt: skip
        else:
            flat.append(_rewrite_branch(item, resolve))
            paths.append(prefix)
    for a, b in inst.of.aliases:
        aliases.append((resolve(a), resolve(b)))


def _resolve_aliases(pairs, ports):
    """Union-find over alias ``pairs``; returns a rename map name → canonical.

    Canonical preference (deterministic): a real `PortOnWire` name beats any
    virtual (its name is welded to geometry and must never be rewritten),
    then top-level names beat instance-internal ones (fewer dots), then the
    shorter / lexicographically-smaller name. Merging two real ports is an
    error — two distinct geometry locations cannot be fused by naming."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    classes = {}
    for n in parent:
        classes.setdefault(find(n), []).append(n)

    rename = {}
    for members in classes.values():
        real = [
            n
            for n in members
            if isinstance(ports.get(n), (PortOnWire, PortAtEnd, PortAtVertex))
        ]
        if len(real) > 1:
            raise ValueError(
                f"aliases merge distinct geometry ports {sorted(real)} — "
                "two real feed locations cannot be fused by naming"
            )
        canon = min(
            members,
            key=lambda n: (
                0 if n in real else 1,
                n.count("."),
                len(n),
                n,
            ),
        )
        for n in members:
            if n != canon:
                rename[n] = canon
    return rename


@dataclass
class Network(_FlatNetwork):
    """Complete network spec returned by `build_network()` — the HIERARCHY-
    aware `momwire.networks.Network`.

    ports:    dict mapping name → Port (real or virtual)
    branches: list of Branch (TL / Load / TwoPort / …) — may also contain
              `Instance` items (issue #489), which are flattened in
              ``__post_init__``: internal nodes become auto-declared
              `PortVirtual` s named "<instance>.<node>", composite aliases
              are resolved by node merging, and each flattened branch's
              instance path lands in ``branch_paths`` (same order as
              ``branches``; "" for top-level branches) for power-budget
              attribution. Engines and reducers only ever see plain
              branches.
    sources:  list of Source (currently just Driven)

    The engine's job: assemble the antenna Y matrix at the real ports,
    pad to include virtual ports, stamp every branch, then reduce to the
    driven-port impedances.

    Subclassing is the whole shape of the momwire#456 ws2 split. The parent
    is FLAT and validates a flat spec, taking ``branch_paths`` as an ordinary
    field; here ``branch_paths`` is DERIVED — passing it raises — because
    flattening is what computes it. So ``__post_init__`` expands instances
    first and calls the parent's validation second, on the flat result. An
    ``isinstance(x, momwire.networks.Network)`` therefore holds for every
    antennaknobs network, and momwire sees only what it was handed.
    """

    #: Instance path → the `Composite` it came from, filled by flattening
    #: (issue #652). Derived, like ``branch_paths``.
    composites: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.branch_paths:
            raise ValueError("branch_paths is derived — do not pass it")
        # Expansion FILLS branch_paths (and composites), so it must run before
        # the parent, whose validation reads branches/ports/sources flat and
        # cross-checks branch_paths' length against them.
        self._expand_instances()
        super().__post_init__()

    def _expand_instances(self):
        """Flatten `Instance` items (issue #489): namespace internals,
        resolve aliases, stamp per-branch instance paths."""
        flat, paths, alias_pairs, internals = [], [], [], set()
        composites: dict[str, Composite] = {}
        for item in self.branches:
            if isinstance(item, Instance):
                for actual in item.portmap.values():
                    if actual not in self.ports:
                        raise ValueError(
                            f"instance {item.name!r} binds to unknown port "
                            f"{actual!r} — actuals must be declared Network "
                            "ports"
                        )
                _expand_instance(
                    item, dict(item.portmap), item.name + ".",
                    flat, paths, alias_pairs, internals, composites,
                )  # fmt: skip
            else:
                flat.append(item)
                paths.append("")
        self.branches = flat
        self.branch_paths = paths
        self.composites = composites
        for n in sorted(internals):
            if n in self.ports:
                raise ValueError(f"internal node {n!r} collides with a port")
            self.ports[n] = PortVirtual(n)
        if not alias_pairs:
            return
        rename = _resolve_aliases(alias_pairs, self.ports)
        if not rename:
            return
        ren = lambda n: rename.get(n, n)  # noqa: E731
        self.branches = [_rewrite_branch(br, ren) for br in self.branches]
        self.ports = {n: p for n, p in self.ports.items() if n not in rename}
        merged_sources = []
        for src in self.sources:
            src = replace(src, port=ren(src.port))
            for prev in merged_sources:
                if prev.port == src.port:
                    if prev != src:
                        raise ValueError(
                            f"aliasing merged conflicting sources on port "
                            f"{src.port!r}: {prev!r} vs {src!r}"
                        )
                    break
            else:
                merged_sources.append(src)
        self.sources = merged_sources
