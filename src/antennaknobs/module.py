"""Paired geometry+network subassemblies — "Suggestion B" of the array
redesign, built on the :class:`~antennaknobs.cell.Cell` geometry hierarchy.

A :class:`Module` bundles an element's geometry face (a ``Cell``) with its
network face (feed ports + a branch body) behind ONE set of formal feed names.
A :class:`ModuleInstance` stamps it — placing the geometry with a ``Transform``
and binding the module's external network terminals — and a single expansion
namespaces the feed to ``"<instance>.<feed>"`` on *both* faces at once.

This is what kills the crux the current array designs suffer: today a feed
name is written in ``build_wires()`` (as a ``Wire`` name) and re-typed,
independently, in ``build_network()`` (as a ``PortOnWire``/``PortAtEnd``
target); the two loops must produce byte-identical strings or the port is a
silent open gap. With a ``Module`` the name is authored once and namespaced by
the same rule on both sides, so they cannot drift.

    circuit (network.py)     geometry (cell.py)     paired (this module)
    Composite / Instance     Cell / Placement       Module / ModuleInstance
    ports (formal nodes)     feeds (formal wires)    feeds (shared) + terminals

``terminals`` are the external network nodes (a shared driver, a phasing
manifold) the element connects to; they bind at instantiation via the keyword
port map, exactly like :class:`~antennaknobs.network.Instance`. The feed ports
are element-internal and auto-namespaced — never bound by hand.

:func:`lattice` is "Suggestion C": the ergonomic front-end that emits a grid of
``ModuleInstance`` s with pure-translation poses (which momwire's lattice-FFT
detection still recognizes), replacing the hand-unrolled offset loops.
"""

from dataclasses import dataclass, field

from .cell import Cell, Placement, flatten_placements
from .network import (
    PortAtEnd,
    PortOnWire,
    PortOnWireFloating,
    PortVirtual,
    Wire,
    _branch_port_refs,
    _rewrite_branch,
)
from .transform import Transform


@dataclass(frozen=True)
class Module:
    """A reusable element with a geometry face and a network face sharing one
    set of formal feed names.

    - ``cell`` is the geometry (its ``feeds`` are the feed wire names).
    - ``ports`` are the network ports keyed by FORMAL name: the feed ports
      (``PortOnWire``/``PortOnWireFloating`` on a feed wire, or ``PortAtEnd`` at
      one of its ends) plus any element-internal ``PortVirtual`` nodes. For a
      ``PortOnWire`` the key must equal its ``name`` (the ``Network`` rule); a
      feed port's geometry name/wire must be one of ``cell.feeds``.
    - ``terminals`` are external network nodes bound at instantiation.
    - ``branches`` are the network body; every port reference must be a port
      key or a terminal.
    """

    cell: Cell
    ports: dict = field(default_factory=dict)
    terminals: tuple[str, ...] = ()
    branches: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "terminals", tuple(self.terminals))
        object.__setattr__(self, "branches", tuple(self.branches))

        feeds = set(self.cell.feeds)
        for key, port in self.ports.items():
            if isinstance(port, PortOnWire):  # incl. PortOnWireFloating
                if key != port.name:
                    raise ValueError(
                        f"port key {key!r} must equal PortOnWire name {port.name!r}"
                    )
                if port.name not in feeds:
                    raise ValueError(
                        f"feed port {port.name!r} names no cell feed {self.cell.feeds!r}"
                    )
            elif isinstance(port, PortAtEnd):
                if port.wire not in feeds:
                    raise ValueError(
                        f"PortAtEnd wire {port.wire!r} names no cell feed "
                        f"{self.cell.feeds!r}"
                    )
            elif not isinstance(port, PortVirtual):
                raise ValueError(f"unsupported module port {port!r}")

        known = set(self.ports) | set(self.terminals)
        for br in self.branches:
            unknown = [r for r in _branch_port_refs(br) if r not in known]
            if unknown:
                raise ValueError(
                    f"branch {br!r} references {unknown} — not a module port or "
                    f"terminal (ports={sorted(self.ports)}, terminals="
                    f"{sorted(self.terminals)})"
                )


class ModuleInstance:
    """One stamp of a :class:`Module`: ``ModuleInstance("e0", elem, pose,
    drv="drv")``. ``transform`` places the geometry; keyword args bind every
    external terminal to a node name in the parent (all terminals must be
    bound — an unbound terminal is a floating connection)."""

    def __init__(self, name, of: Module, transform: Transform | None = None, **portmap):
        if not name or "." in name:
            raise ValueError(
                f"module instance name {name!r} must be non-empty and contain no"
                " '.' (dots are the namespace separator)"
            )
        formals, bound = set(of.terminals), set(portmap)
        if formals != bound:
            missing, extra = formals - bound, bound - formals
            raise ValueError(
                f"instance {name!r} terminal map mismatch:"
                + (f" missing {sorted(missing)}" if missing else "")
                + (f" unknown {sorted(extra)}" if extra else "")
                + f"; module terminals are {of.terminals!r}"
            )
        self.name = name
        self.of = of
        self.transform = transform if transform is not None else Transform()
        self.portmap = dict(portmap)


@dataclass
class Assembly:
    """The combined expansion of a list of :class:`ModuleInstance` s: the flat
    ``Wire`` list for ``build_wires()``, plus the network ``ports`` dict and
    ``branches`` list for ``build_network()``. ``feeds`` lists the namespaced
    feed-port keys in instance order, so a design can drive them
    (``Driven(port=f) for f in assembly.feeds``) without ever typing a
    per-element name."""

    wires: list
    ports: dict
    branches: list
    feeds: list


def _rewrite_port(port, prefix):
    if isinstance(port, PortOnWireFloating):  # subclass — must precede PortOnWire
        return PortOnWireFloating(prefix + port.name, port.distributed)
    if isinstance(port, PortOnWire):
        return PortOnWire(prefix + port.name, port.distributed)
    if isinstance(port, PortAtEnd):
        return PortAtEnd(prefix + port.wire, port.end)
    return PortVirtual(prefix + port.name)  # PortVirtual


def expand_modules(instances) -> Assembly:
    """Flatten :class:`ModuleInstance` s into a combined :class:`Assembly`.

    The geometry is expanded through :func:`flatten_placements` (feeds default
    to ``"<instance>.<feed>"``); the network ports/branches are namespaced by
    the SAME rule, so a feed's wire name and its port name are guaranteed
    equal by construction — the property the hand-written designs can only hope
    holds."""
    placements = [
        Placement(inst.name, inst.of.cell, inst.transform) for inst in instances
    ]
    wires: list[Wire] = flatten_placements(placements)

    ports: dict = {}
    branches: list = []
    feeds: list[str] = []
    for inst in instances:
        prefix = inst.name + "."

        def resolve(ref, inst=inst, prefix=prefix):
            if ref in inst.of.terminals:
                return inst.portmap[ref]
            return prefix + ref

        for key, port in inst.of.ports.items():
            final = _rewrite_port(port, prefix)
            final_key = prefix + key
            if final_key in ports:
                raise ValueError(
                    f"module expansion produced duplicate port {final_key!r}"
                )
            ports[final_key] = final
            if isinstance(port, (PortOnWire, PortAtEnd)):  # geometry-touching feed
                feeds.append(final_key)
        for br in inst.of.branches:
            branches.append(_rewrite_branch(br, resolve))

    return Assembly(wires=wires, ports=ports, branches=branches, feeds=feeds)


def lattice(module, *, nx, nz, dy, dz, name="e", bind=None):
    """A grid of :class:`ModuleInstance` s, centroid-centered, with
    pure-translation poses.

    ``nx``/``nz`` are the element counts along y/z; ``dy``/``dz`` the spacings.
    Instances are named ``f"{name}{i}_{j}"`` in i-major/j-minor order (so
    ``Assembly.feeds`` comes back in that order). ``bind(i, j)`` returns the
    terminal port map for element (i, j) — omit it for elements with no
    external terminals (each feed driven on its own). The poses are pure
    translations, so momwire's lattice-FFT block detection still engages.
    """
    insts = []
    for i in range(int(nx)):
        for j in range(int(nz)):
            t = Transform.translate(0, (i - (nx - 1) / 2) * dy, (j - (nz - 1) / 2) * dz)
            portmap = bind(i, j) if bind is not None else {}
            insts.append(ModuleInstance(f"{name}{i}_{j}", module, t, **portmap))
    return insts
