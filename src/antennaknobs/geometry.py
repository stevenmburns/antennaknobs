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


def _round_point(p, eps):
    # Quantize endpoints onto an eps-spaced grid so 1e-14 floating-point
    # noise doesn't fragment what is logically a shared node.
    return tuple(round(float(c) / eps) * eps for c in p)


def flat_wires_to_polylines(tups, *, eps=1e-6):
    """Convert flat wire tuples to momwire polyline form.

    Returns a dict with keys:
        polylines       : list of (M, 3) np.ndarray
        edge_segments   : list of list[int] — n_seg per edge per polyline
        feeds           : list of (polyline_idx, arclength, voltage) —
                          one entry per excited tuple, in registration
                          order. Suitable to pass directly to a
                          momwire solver's feeds=... kwarg.
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

    # Names are an optional 5th tuple field. None (or absent) means
    # "unnamed"; otherwise a string identifying this edge as a network
    # port in `build_network()`.
    tup_names = []
    for i, t in enumerate(tups):
        if len(t) == 4:
            p0, p1, n_seg, ev = t
            name = None
        elif len(t) == 5:
            p0, p1, n_seg, ev, name = t
        else:
            raise ValueError(f"tuple {i}: expected 4- or 5-tuple, got {len(t)}")
        a = node_id(p0)
        b = node_id(p1)
        if a == b:
            raise ValueError(f"tuple {i}: degenerate edge (p0==p1 within eps)")
        edges.append((a, b, int(n_seg), ev, i))
        tup_names.append(name)

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
    edge_seen = [False] * len(edges)

    polylines = []
    edge_segments = []
    # junction_ends[node_id] -> list of (polyline_index, "start"|"end").
    # Filled as we walk; only meaningful for degree>=3 nodes, but we
    # collect it for all boundary nodes and filter later.
    junction_ends = {nid: [] for nid in range(len(nodes)) if is_boundary[nid]}
    # tup_index -> (polyline_index, edge_index_within)
    edge_to_polyline = {}

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

            polyline_idx = len(polylines)
            polylines.append(np.stack([nodes[n] for n in path_nodes], axis=0))
            edge_segments.append([edges[e][2] for e in path_edges])
            for k, e in enumerate(path_edges):
                edge_to_polyline[edges[e][4]] = (polyline_idx, k)
            junction_ends[path_nodes[0]].append((polyline_idx, "start"))
            junction_ends[path_nodes[-1]].append((polyline_idx, "end"))

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
        cut_a, cut_b, cut_n_seg, _, cut_tup_idx = edges[cut_ei]

        # Polyline 0: the cut edge alone, A → B. It hosts the delta-gap feed
        # when the cut was a port edge; for a parasitic loop it is just passive.
        cut_pl_idx = len(polylines)
        polylines.append(np.stack([nodes[cut_a], nodes[cut_b]], axis=0))
        edge_segments.append([cut_n_seg])
        edge_to_polyline[cut_tup_idx] = (cut_pl_idx, 0)

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
        loop_pl_idx = len(polylines)
        polylines.append(np.stack([nodes[n] for n in path_nodes], axis=0))
        edge_segments.append([edges[e][2] for e in path_edges])
        for k, e in enumerate(path_edges):
            edge_to_polyline[edges[e][4]] = (loop_pl_idx, k)

        # Register the cut endpoints as junctions: the cut polyline has
        # path [A, B] so its start=A, end=B; loop polyline was walked
        # B → A so its start=B, end=A.
        junction_ends[cut_a].append((cut_pl_idx, "start"))
        junction_ends[cut_a].append((loop_pl_idx, "end"))
        junction_ends[cut_b].append((cut_pl_idx, "end"))
        junction_ends[cut_b].append((loop_pl_idx, "start"))

    # Junctions = nodes where >= 2 polylines meet. Single-end records
    # (degree-1 free ends) and lone polyline starts aren't junctions.
    junctions = [ends for ends in junction_ends.values() if len(ends) >= 2]

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
    for tup_index, edge in enumerate(edges):
        voltage = edge[3]
        name = tup_names[tup_index]
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

    if not feeds:
        raise ValueError("no excitation found in wire list")

    return {
        "polylines": polylines,
        "edge_segments": edge_segments,
        "feeds": feeds,
        "feed_names": feed_names,
        # Back-compat scalars — first feed.
        "feed_wire_index": feeds[0][0],
        "feed_arclength": feeds[0][1],
        "feed_voltage": feeds[0][2],
        "junctions": junctions,
    }
