"""The measurement plane as a thing you can pick (issue #652, option c).

A station design declares both ends of its chain — ``Driven(port="rig")`` and
the antenna's ``feed`` — and the whole chart is drawn at whichever port the
source sits on. That plane used to be a convention to remember; with the
schematic on screen it becomes a thing to point at, and this module makes
pointing at it *mean* something: solve the design as a VNA clipped on at that
port would see it.

## Why picking a plane prunes, rather than just moving the source

The issue sketches "re-solve with ``Driven(port='feed')``" — but moving the
source alone leaves the feed chain wired to the node, now ending at an
undriven, unterminated ``rig``: a length of open-ended coax hanging in
parallel with the antenna. That is "VNA at the feedpoint with the coax still
dangling on it", and it is not what anyone means by measuring at the
feedpoint. What they mean is the upstream *unscrewed*: so ``driven_at``
cuts the chain at the picked port, drops everything on the source side of the
cut, and drives what remains. Attachments — traps, stubs wired into the
structure — are not upstream of anything and always stay.

The cut is found with the same (signal, return) pair-walk the schematic uses,
because "which side of this node is upstream" is exactly the question the
chain drawing already answers.
"""

from __future__ import annotations

from dataclasses import replace

from .network import Driven, Network, PortOnWireFloating, PortVirtual
from .schematic import DATUM, _antenna_nodes, _datum_nodes, _walk, terminals_of

__all__ = ["antenna_side", "driven_at", "planes_of"]


def _chain(net: Network):
    """The design's feed chain, walked from its natural source."""
    src = net.sources[0]
    return _walk(
        list(net.branches),
        src.port,
        _antenna_nodes(net),
        _datum_nodes(net),
    )


def _cut_at(chain, node: str):
    """Index of the first chain step the plane node sits in front of.

    ``k`` means: steps ``0..k-1`` are upstream (source side) of the plane;
    ``len(chain)`` means the plane is the chain's end. None: not on the chain.
    """
    for k, st in enumerate(chain):
        if node in st.pair_in:
            return k
    if chain and node in chain[-1].pair_out:
        return len(chain)
    return None


def driven_at(net: Network, plane: str) -> Network:
    """Re-source ``net`` at the named port, upstream disconnected.

    Returns ``net`` itself when ``plane`` is already the driven port.
    Everything on the source side of the cut is dropped — the chain branches
    before the plane, any branch hanging entirely on their internal nodes,
    and any `PortVirtual` nothing references anymore (an orphaned virtual
    node would be a floating MNA row). The original source's drive value is
    kept; only its port moves.
    """
    if len(net.sources) != 1:
        raise ValueError(
            f"{len(net.sources)} sources — a multi-feed drive has no single "
            "plane to move"
        )
    src = net.sources[0]
    if plane == src.port:
        return net
    port = net.ports.get(plane)
    if port is None:
        raise ValueError(f"no port named {plane!r} to measure at")
    if isinstance(port, PortOnWireFloating):
        raise ValueError(
            f"{plane!r} is a floating gap — it has no reference terminal to "
            "drive against"
        )

    chain = _chain(net)
    cut = _cut_at(chain, plane)
    if cut is None:
        raise ValueError(f"{plane!r} is not on the feed chain from {src.port!r}")

    upstream = {st.idx for st in chain[:cut]}
    # Nodes that exist only on the source side: everything the upstream steps
    # touch, minus the pair the cut leaves live. A rib AT the plane node stays
    # — the wiring cannot say whether it unscrews with the upstream, and
    # keeping it is the claim the drawing already makes.
    live = set(chain[cut].pair_in if cut < len(chain) else chain[-1].pair_out)
    gone = set()
    for st in chain[:cut]:
        gone |= set(st.pair_in) | set(st.pair_out)
    gone -= live
    gone.discard(DATUM)

    is_datum = _datum_nodes(net)
    branches, paths = [], []
    all_paths = net.branch_paths or [""] * len(net.branches)
    for i, br in enumerate(net.branches):
        if i in upstream:
            continue
        ts = [t for t in terminals_of(br) if t not in is_datum]
        if ts and all(t in gone for t in ts):
            continue
        branches.append(br)
        paths.append(all_paths[i])

    # An orphaned PortVirtual is a floating matrix row; wire ports are
    # geometry and keep their antenna-Y grounding regardless.
    referenced = set()
    for br in branches:
        referenced |= set(terminals_of(br))
    ports = {
        name: p
        for name, p in net.ports.items()
        if name == plane or not isinstance(p, PortVirtual) or name in referenced
    }

    out = Network(ports=ports, branches=branches, sources=[replace(src, port=plane)])
    # branch_paths is derived-only in __post_init__ (and these branches are
    # already flat), so the surviving instance attribution is restored here —
    # the power budget and the schematic group by it.
    out.branch_paths = paths
    out.composites = dict(net.composites or {})
    return out


def planes_of(net: Network) -> list[str]:
    """The ports a VNA could be clipped to, natural plane first.

    Chain order after that, so a picker reads source → antenna. Only named,
    drivable, top-level ports count: a floating pair has no reference to
    drive against, and a flattening-invented interior ("tuner.o") is an
    implementation detail nobody calibrates to. Each candidate is proven by
    actually building its pruned network — a plane the solve would reject is
    not offered.
    """
    if len(net.sources) != 1:
        return []
    natural = net.sources[0].port
    out = [natural]
    for st in _chain(net):
        for node in (st.pair_in[0], st.pair_out[0]):
            if node in out or node == DATUM or "." in node:
                continue
            p = net.ports.get(node)
            if p is None or isinstance(p, PortOnWireFloating):
                continue
            try:
                driven_at(net, node)
            except ValueError:
                continue
            out.append(node)
    return out


def antenna_side(net: Network, feed: str) -> Network:
    """The parts of ``net`` the antenna carries itself, driven at ``feed``.

    Where the design's source already sits on ``feed`` it has no station, and
    every branch is the antenna's: a loading coil in series at the feed, a
    bond shorting an idle stub. Otherwise the design's station comes off:
    everything upstream of ``feed`` (`driven_at`'s cut), and also whatever
    hangs on ``feed`` alone, such as an L network's shunt part or a matching
    stub there, since from the feed back to the rig is the station's side.
    What stays is every branch that reaches a real port other than ``feed``
    (a trap on its own wire, an LPDA's phasing line from the feed to the next
    element, a bond on another port), so an antenna built partly from circuit
    elements is still that antenna. The station rail
    (`antennaknobs.station_rail`) puts its chain on what this returns, and
    refuses a design whose station meets the antenna anywhere but ``feed``.
    """
    src = net.sources[0] if len(net.sources) == 1 else None
    if src is not None and src.port == feed:
        out = Network(
            ports=dict(net.ports),
            branches=list(net.branches),
            sources=[Driven(port=feed, voltage=1 + 0j)],
        )
        out.branch_paths = list(net.branch_paths or [""] * len(net.branches))
        out.composites = dict(net.composites or {})
        return out
    cut = driven_at(net, feed)
    real = {n for n, p in cut.ports.items() if not isinstance(p, PortVirtual)}
    # A node bonded to the datum is the datum, except a real port: a bond on
    # an antenna port is wired to that port, and the branch is the antenna's.
    is_datum = _datum_nodes(cut) - real

    # Components over the nodes other than the datum and the feed: a branch
    # stays when its component holds a real port that is not the feed.
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    inner = []
    for br in cut.branches:
        ts = [t for t in terminals_of(br) if t not in is_datum and t != feed]
        inner.append(ts)
        for t in ts[1:]:
            parent[find(t)] = find(ts[0])
    anchored = {find(n) for n in real if n != feed}
    branches, paths = [], []
    all_paths = cut.branch_paths or [""] * len(cut.branches)
    for br, ts, path in zip(cut.branches, inner, all_paths, strict=True):
        if ts and find(ts[0]) in anchored:
            branches.append(br)
            paths.append(path)
    referenced = {feed}
    for br in branches:
        referenced |= set(terminals_of(br))
    ports = {
        name: p
        for name, p in cut.ports.items()
        if not isinstance(p, PortVirtual) or name in referenced
    }
    out = Network(
        ports=ports, branches=branches, sources=[Driven(port=feed, voltage=1 + 0j)]
    )
    out.branch_paths = paths
    # Composite keys and branch paths end in the instance dot ("trap1.",
    # "sta.tuner1."), so this prefix test cannot take "trap1." for "trap10.".
    out.composites = {
        k: v
        for k, v in (cut.composites or {}).items()
        if any(p.startswith(k) for p in paths)
    }
    return out
