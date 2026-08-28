"""Translate the flat (p0, p1, n_seg, excitation) wire list used by
AntennaBuilder.build_wires() into the polyline + feed-arclength shape
that momwire's solver classes consume.

The flat list expresses connectivity implicitly: two tuples are part of
the same electrical wire when they share an endpoint (within `eps`).
momwire wants each electrical wire as one (M, 3) polyline with junction
information (KCL at shared nodes) explicit; this module recovers the
graph, decomposes it into maximal chains between junction/endpoint
nodes, and emits the junction list.

Supported topologies:
  * Open chains and any number of junctions of any degree (tees, X's,
    hentenna-style multi-junction, fandipole-style multi-spoke feeds).
  * Pure cycles (closed loops). A cycle is cut at one edge into two
    polylines joined by a junction at each cut node, so momwire's KCL
    carries the current around the loop. The cut edge is the loop's port
    edge when it has one (driven loops); for a PARASITIC loop, which
    radiates only through mutual coupling, the cut edge is arbitrary.
    A cycle with two or more port edges is not yet handled.
  * One or more excited segments per geometry (each becomes a delta-gap
    feed in the returned `feeds` list). The geometry as a whole must
    carry at least one excitation, but individual loop components need
    not (a parasitic loop is excited only by coupling).
"""

from __future__ import annotations

import numpy as np

from .network import as_wire
from .wire_catalog import GradedSegments


def _round_point(p, eps):
    # Quantize endpoints onto an eps-spaced grid so 1e-14 floating-point
    # noise doesn't fragment what is logically a shared node.
    return tuple(round(float(c) / eps) * eps for c in p)


def flat_wires_to_polylines(tups, *, eps=1e-6, end_ports=None):
    """Convert flat wire tuples to momwire polyline form.

    ``end_ports`` (issue #579): iterable of ``(wire_name, "p0"|"p1")`` pairs
    naming wire ENDPOINTS that must become junction-node ports. Each such
    node is forced to be a polyline boundary (so momwire gives it junction
    directional bases) and its shared-node group is emitted in `junctions`
    even when only one polyline end lives there (a lone conductor end — the
    1-entry groups momwire#172 made legal). A name that appears in
    ``end_ports`` is NOT registered as a gap-feed port edge (no delta gap is
    cut in it); it identifies the wire only. The returned
    ``end_port_junctions`` maps each ``(wire_name, end)`` to its junction
    index — pass those straight to a momwire solver's ``junction_ports=``.

    Returns a dict with keys:
        polylines       : list of (M, 3) np.ndarray
        edge_segments   : list of list[int] — n_seg per edge per polyline
        feeds           : list of (polyline_idx, arclength, voltage) —
                          one entry per excited tuple, in registration
                          order. Suitable to pass directly to a
                          momwire solver's feeds=... kwarg.
        feed_dirs       : list of int — +1/-1 per feed: whether the walk
                          traversed the authored tuple p0->p1 (+1) or
                          p1->p0 (-1); engines use it to normalize each
                          port's sign convention to the authored
                          direction (issue #580).
        feed_wire_index : int — polyline holding the first excited
                          segment (back-compat: feeds[0][0])
        feed_arclength  : float — arclength of the first feed
                          (back-compat: feeds[0][1])
        feed_voltage    : complex — voltage of the first feed
                          (back-compat: feeds[0][2])
        junctions       : list of list[(wire_idx, "start"|"end")] —
                          shared-node groups, suitable to pass directly
                          to a momwire solver's junctions=... kwarg. Empty list
                          if every component is a simple path.
        end_port_junctions : dict (wire_name, "p0"|"p1") -> junction index
                          for every requested end port (issue #579).
        end_port_members : dict (wire_name, "p0"|"p1") ->
                          (polyline_idx, "start"|"end") — the momwire
                          member each named end became; what a series
                          node gap addresses (momwire#305, issue #898).
    """
    if not tups:
        raise ValueError("no wires to translate")

    # Build endpoint->node map and per-tuple edge list.
    node_of = {}
    nodes = []  # list of np.ndarray(3,)
    edges = []  # list of (a, b, n_seg, ev, tup_index)

    def node_id(p):
        key = _round_point(p, eps)
        if key not in node_of:
            node_of[key] = len(nodes)
            nodes.append(np.asarray(p, dtype=float))
        return node_of[key]

    # Names are an optional 5th field, per-wire specs an optional 6th
    # (issue #388); entries may be plain 4/5-tuples or `Wire` named tuples,
    # normalized here at the single choke point.
    tup_names = []
    tup_specs = []
    for i, t in enumerate(tups):
        try:
            p0, p1, n_seg, ev, name, spec = as_wire(t)
        except ValueError as e:
            raise ValueError(f"tuple {i}: {e}") from None
        a = node_id(p0)
        b = node_id(p1)
        if a == b:
            raise ValueError(f"tuple {i}: degenerate edge (p0==p1 within eps)")
        if isinstance(n_seg, GradedSegments):
            # A graded wire is structural only: a delta gap or port inside
            # a graded chain would re-mesh the feed model, and the graded
            # spelling exists precisely so the mesh can refine without
            # touching topology or ports.
            if ev is not None or name is not None:
                raise ValueError(
                    f"tuple {i}: a graded wire cannot carry an excitation "
                    "or a port name — put the port on its own (plain) wire"
                )
            edges.append((a, b, n_seg, ev, i))
        else:
            edges.append((a, b, int(n_seg), ev, i))
        tup_names.append(name)
        tup_specs.append(spec)

    # End ports (issue #579): resolve each (wire_name, "p0"|"p1") to its
    # node id. These names identify wires only — they are excluded from
    # gap-feed registration below, and their nodes are forced to be
    # polyline boundaries so momwire can host a junction port there.
    end_ports = list(end_ports or [])
    end_port_names = set()
    end_port_nodes = []  # (name, which, node_id)
    if end_ports:
        name_to_tup = {}
        for i, nm in enumerate(tup_names):
            if nm is not None:
                name_to_tup.setdefault(nm, []).append(i)
        for nm, which in end_ports:
            if which not in ("p0", "p1"):
                raise ValueError(
                    f"end port on {nm!r}: end must be 'p0' or 'p1', got {which!r}"
                )
            idxs = name_to_tup.get(nm)
            if not idxs:
                raise ValueError(
                    f"end port references wire name {nm!r} but no build_wires() "
                    f"tuple carries that name"
                )
            if len(idxs) > 1:
                raise ValueError(
                    f"end port references wire name {nm!r} which is carried by "
                    f"{len(idxs)} tuples — end-port wire names must be unique"
                )
            a, b, *_ = edges[idxs[0]]
            end_port_names.add(nm)
            end_port_nodes.append((nm, which, a if which == "p0" else b))

    # adj[nid] = list of (other_node, edge_index), in registration order.
    adj = [[] for _ in nodes]
    for ei, (a, b, _, _, _) in enumerate(edges):
        adj[a].append((b, ei))
        adj[b].append((a, ei))

    for nid, neigh in enumerate(adj):
        if len(neigh) == 0:
            raise ValueError(f"node {nid} is isolated")

    # Polyline boundaries are exactly the non-degree-2 nodes: degree-1
    # ends an open polyline, degree>=3 is a junction that ends one
    # polyline and starts another. Walk every edge out of every boundary
    # node, threading through degree-2 nodes until the next boundary.
    is_boundary = [len(a) != 2 for a in adj]

    # A wire-spec change is a polyline boundary too (issue #388): momwire
    # consumes one spec per wire, so a degree-2 node whose two edges carry
    # different specs must end one polyline and start another. The node is
    # then registered as a 2-entry junction below — exactly like a cycle
    # cut — so KCL still carries the current through it.
    for nid, neigh in enumerate(adj):
        if not is_boundary[nid]:
            e0, e1 = neigh[0][1], neigh[1][1]
            if tup_specs[edges[e0][4]] != tup_specs[edges[e1][4]]:
                is_boundary[nid] = True

    # An end-port node is a boundary too (issue #579): the port must land on
    # a junction node, so a degree-2 node splits its chain here (registered
    # as a 2-entry junction below — KCL still carries the current through,
    # and the port injects into the shared node). Degree-1 nodes become
    # 1-entry junction groups (legal since momwire#172).
    for _nm, _which, nid in end_port_nodes:
        is_boundary[nid] = True

    edge_seen = [False] * len(edges)

    polylines = []
    edge_segments = []
    # One spec per polyline: uniform by construction, since a spec change
    # at a degree-2 node was marked as a boundary above and any other
    # meeting point is a junction (a boundary already).
    polyline_specs = []
    # junction_ends[node_id] -> list of (polyline_index, "start"|"end").
    # Filled as we walk; only meaningful for degree>=3 nodes, but we
    # collect it for all boundary nodes and filter later.
    junction_ends = {nid: [] for nid in range(len(nodes)) if is_boundary[nid]}
    # tup_index -> (polyline_index, edge_index_within)
    edge_to_polyline = {}
    # tup_index -> +1 when the walk traversed the tuple in its authored
    # p0 -> p1 direction, -1 when reversed. A port edge's delta-gap sign
    # convention (EMF direction / positive-current direction) follows the
    # POLYLINE direction, i.e. the walk — so this factor is what an engine
    # needs to normalize each port to the authored direction (issue #580:
    # "the port's + terminal is toward p1" is the design-visible contract).
    edge_walk_dir = {}

    def emit_polyline(path_nodes, path_edges, register_junctions):
        """Append one polyline from a walked path, expanding any graded
        edge (`GradedSegments`) into interior vertices + per-sub-edge
        counts INSIDE the polyline — the graded spelling's whole point:
        mesh grading that cannot change junction topology (hand-split
        wires on a coincident bundle mint spurious KCL rows at every
        shared split point). `edge_to_polyline` records each tuple's
        FIRST expanded edge index; feed arclengths sum sub-edge lengths
        (identical total), and a graded edge itself is never a feed/port
        edge (rejected at intake)."""
        polyline_idx = len(polylines)
        verts = [nodes[path_nodes[0]]]
        counts = []
        for k, e in enumerate(path_edges):
            ea, _eb, n_seg, _ev, tup_i = edges[e]
            walked_fwd = ea == path_nodes[k]
            edge_to_polyline[tup_i] = (polyline_idx, len(counts))
            edge_walk_dir[tup_i] = 1 if walked_fwd else -1
            p_from = nodes[path_nodes[k]]
            p_to = nodes[path_nodes[k + 1]]
            if isinstance(n_seg, GradedSegments):
                fr = (
                    n_seg.fracs
                    if walked_fwd
                    else tuple(1.0 - f for f in reversed(n_seg.fracs))
                )
                cts = n_seg.counts if walked_fwd else tuple(reversed(n_seg.counts))
                for f in fr:
                    verts.append(p_from + f * (p_to - p_from))
                verts.append(p_to)
                counts.extend(int(c) for c in cts)
            else:
                verts.append(p_to)
                counts.append(int(n_seg))
        polylines.append(np.stack(verts, axis=0))
        edge_segments.append(counts)
        polyline_specs.append(tup_specs[edges[path_edges[0]][4]])
        if register_junctions:
            junction_ends[path_nodes[0]].append((polyline_idx, "start"))
            junction_ends[path_nodes[-1]].append((polyline_idx, "end"))
        return polyline_idx

    def walk_from(start_nid, first_edge):
        path_nodes = [start_nid]
        path_edges = []
        prev_edge = None
        cur = start_nid
        next_edge = first_edge
        while True:
            edge_seen[next_edge] = True
            path_edges.append(next_edge)
            a, b, _, _, _ = edges[next_edge]
            nxt = b if a == cur else a
            path_nodes.append(nxt)
            cur = nxt
            if is_boundary[cur]:
                return path_nodes, path_edges
            prev_edge = next_edge
            # Degree-2 interior: take the unique outgoing edge.
            next_edge = None
            for _nb, ei in adj[cur]:
                if ei != prev_edge:
                    next_edge = ei
                    break
            assert next_edge is not None, f"degree-2 node {cur} had no continuation"

    for start in range(len(nodes)):
        if not is_boundary[start]:
            continue
        for _nb, ei in adj[start]:
            if edge_seen[ei]:
                continue
            path_nodes, path_edges = walk_from(start, ei)
            emit_polyline(path_nodes, path_edges, register_junctions=True)

    # Pure-cycle components — every node degree 2, no boundary to start
    # the walk from — are left untouched by the loop above. Cut each at
    # its excited edge: the excited edge becomes one polyline (A→B), the
    # rest of the cycle becomes a second polyline walked B→A the long
    # way. The two cut nodes A and B are each registered as 2-entry
    # junctions so momwire's KCL enforces current continuity around the
    # loop.
    while not all(edge_seen):
        seed = next(i for i, seen in enumerate(edge_seen) if not seen)
        # Flood the component reachable from `seed` through unseen edges.
        comp_edges = []
        stack = [seed]
        in_comp = {seed}
        while stack:
            ei = stack.pop()
            comp_edges.append(ei)
            edge_seen[ei] = True
            a, b, _, _, _ = edges[ei]
            for endpoint in (a, b):
                for _nb, eo in adj[endpoint]:
                    if eo not in in_comp and not edge_seen[eo]:
                        in_comp.add(eo)
                        stack.append(eo)

        # A "port edge" carries either a voltage (legacy build_tls path) or a
        # network-spec name. To open the cycle we cut ONE edge into its own
        # polyline and register the two cut nodes as junctions, so momwire's KCL
        # enforces current continuity around the loop. We PREFER to cut at a
        # port edge: it has to become its own polyline anyway, to host the
        # delta-gap feed. A PARASITIC loop has no port edge, so the cut point
        # is arbitrary (any edge breaks the cycle) -- we cut the first one, and
        # since it carries no voltage/name it simply stays a passive polyline
        # whose only role is to anchor the two cut-node junctions. Any extra
        # port edges (a feed + a termination, as in a terminated rhombic/T2FD)
        # stay inside the long-way polyline and are registered as feeds by
        # arclength below, so a multi-port loop is handled too.
        excited_in_comp = [
            ei
            for ei in comp_edges
            if edges[ei][3] is not None or tup_names[edges[ei][4]] is not None
        ]
        cut_ei = excited_in_comp[0] if excited_in_comp else comp_edges[0]
        cut_a, cut_b, _cut_n_seg, _, cut_tup_idx = edges[cut_ei]

        # Polyline 0: the cut edge alone, A → B. It hosts the delta-gap feed
        # when the cut was a port edge; for a parasitic loop it is just passive.
        # ([A, B] = authored p0 -> p1, so emit_polyline records walk dir +1.)
        cut_pl_idx = emit_polyline([cut_a, cut_b], [cut_ei], register_junctions=False)

        # Polyline 1 (long way): walk B → ... → A via the remaining edges.
        # The cut nodes are now polyline boundaries; the walker stops there.
        is_boundary[cut_a] = True
        is_boundary[cut_b] = True
        junction_ends.setdefault(cut_a, [])
        junction_ends.setdefault(cut_b, [])

        # Undo the flood-fill's seen marks on the cycle remainder so the
        # walker can traverse them. Keep the cut edge marked since it's
        # already become polyline 0.
        for ei in comp_edges:
            if ei != cut_ei:
                edge_seen[ei] = False

        first = next(
            (eo for _nb, eo in adj[cut_b] if eo != cut_ei and not edge_seen[eo]),
            None,
        )
        # In a pure cycle every node has degree 2, so there's exactly one
        # remaining edge at cut_b after consuming the cut edge.
        assert first is not None, "cycle cut left no continuation"
        path_nodes, path_edges = walk_from(cut_b, first)
        loop_pl_idx = emit_polyline(path_nodes, path_edges, register_junctions=False)

        # Register the cut endpoints as junctions: the cut polyline has
        # path [A, B] so its start=A, end=B; loop polyline was walked
        # B → A so its start=B, end=A.
        junction_ends[cut_a].append((cut_pl_idx, "start"))
        junction_ends[cut_a].append((loop_pl_idx, "end"))
        junction_ends[cut_b].append((cut_pl_idx, "end"))
        junction_ends[cut_b].append((loop_pl_idx, "start"))

    # Junctions = nodes where >= 2 polylines meet. Single-end records
    # (degree-1 free ends) and lone polyline starts aren't junctions —
    # EXCEPT end-port nodes (issue #579), whose group is emitted even with a
    # single member so a momwire junction port can live there.
    end_port_nids = {nid for _nm, _w, nid in end_port_nodes}
    junctions = []
    junction_index_of_node = {}
    for nid, ends in junction_ends.items():
        if len(ends) >= 2 or (nid in end_port_nids and len(ends) >= 1):
            junction_index_of_node[nid] = len(junctions)
            junctions.append(ends)
    end_port_junctions = {
        (nm, which): junction_index_of_node[nid] for nm, which, nid in end_port_nodes
    }
    # The MEMBER each named end became: (polyline_idx, "start"|"end") in
    # momwire's numbering — what a series node gap (momwire#305, issue
    # #898's PortAtVertex) addresses, where a junction PORT (#579) needs
    # only the junction index above. Derivation: the named endpoint sits at
    # node position edge_pos or edge_pos+1 of its polyline's walk depending
    # on whether the walk traversed the authored tuple p0→p1; a forced
    # boundary means that position is the walk's first or last node.
    end_port_members = {}
    if end_port_nodes:
        name_to_tup = {}
        for i, nm in enumerate(tup_names):
            if nm is not None:
                name_to_tup.setdefault(nm, []).append(i)
        for nm, which, _nid in end_port_nodes:
            tup_index = name_to_tup[nm][0]
            pl_idx, edge_pos = edge_to_polyline[tup_index]
            walk_dir = edge_walk_dir[tup_index]
            pos = edge_pos + (0 if (which == "p0") == (walk_dir == 1) else 1)
            n_edges_pl = len(edge_segments[pl_idx])
            assert pos in (0, n_edges_pl), (nm, which, pos, n_edges_pl)
            end_port_members[(nm, which)] = (
                pl_idx,
                "start" if pos == 0 else "end",
            )

    # Locate the excitation(s) and convert each to (polyline_idx,
    # arclength, voltage). PyNEC feeds at segment `(n_seg+1)//2` of the
    # excited tuple — the middle segment 1-indexed, i.e. the physical
    # midpoint of the wire. The excited tuple is one edge of its
    # polyline; feed at that edge's midpoint.
    #
    # A tuple is a feed if either (a) it has a non-None ex value (legacy
    # voltage-driven feed) or (b) it has a non-None name (network-port
    # placeholder, voltage gets set later by `build_network()`).
    feeds = []
    feed_names = []
    feed_edges = []
    feed_dirs = []
    for tup_index, edge in enumerate(edges):
        voltage = edge[3]
        name = tup_names[tup_index]
        # An end-port name identifies its wire for the junction port only —
        # no gap is cut in the wire (issue #579), so it is not a port edge.
        if name in end_port_names:
            name = None
        if voltage is None and name is None:
            continue
        feed_pl, feed_edge_idx = edge_to_polyline[tup_index]
        polyline = polylines[feed_pl]
        edge_lengths = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
        feed_arclength = float(
            edge_lengths[:feed_edge_idx].sum() + 0.5 * edge_lengths[feed_edge_idx]
        )
        feeds.append(
            (feed_pl, feed_arclength, complex(voltage if voltage is not None else 0))
        )
        feed_names.append(name)
        feed_edges.append((feed_pl, feed_edge_idx))
        feed_dirs.append(edge_walk_dir[tup_index])

    if not feeds and not end_port_nodes:
        raise ValueError("no excitation found in wire list")

    return {
        "polylines": polylines,
        "edge_segments": edge_segments,
        "polyline_specs": polyline_specs,
        "feeds": feeds,
        "feed_names": feed_names,
        # Which (polyline, edge) each feed sits on — a distributed port
        # (issue #477) needs the whole edge's extent, not just its midpoint.
        "feed_edges": feed_edges,
        # +1/-1 per feed: whether the walk traversed the authored tuple
        # p0 -> p1 (+1) or p1 -> p0 (-1). A feed's solver-side sign
        # convention follows the walk; engines multiply by this factor to
        # normalize every port to the AUTHORED direction (issue #580).
        "feed_dirs": feed_dirs,
        # Back-compat scalars — first feed (None when the design is driven
        # entirely through end ports, issue #579).
        "feed_wire_index": feeds[0][0] if feeds else None,
        "feed_arclength": feeds[0][1] if feeds else None,
        "feed_voltage": feeds[0][2] if feeds else None,
        "junctions": junctions,
        "end_port_junctions": end_port_junctions,
        "end_port_members": end_port_members,
    }
