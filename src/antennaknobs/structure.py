"""A design's repeated geometry, as the fill sees it (AK#2165, momwire#1555).

Repeated geometry gives repeated entries in the MoM matrix. The expensive part
of momwire's bs2 fill is a set of scalar moment integrals on segment pairs
that depend only on the distances between the segments, so two pairs of
straight edges related by one isometry have the same block of them. Over
ground the image and remainder terms keep that only for moves that keep every
point's height: horizontal translation, rotation about z, and mirrors in
vertical planes.

This module finds that structure from a design's meshed wires and reports what
it could save. It is read-only: nothing here changes a solve.

- :func:`edges_of`: the straight, uniformly meshed edges (a graded wire
  becomes its uniform sub-wires, as the NEC exporter writes it).
- :func:`mirror_planes`: planes that map the whole structure onto itself.
- :func:`edge_pair_classes`: unordered edge pairs grouped by relative pose,
  each member with the isometry from its class's representative, fitted and
  checked. This is the reuse momwire#1809 would make.
- :func:`segment_pair_counts`: distinct segment pairs under the mirrors and
  under any repeat, the upper bound with no block structure.
- :func:`analyze` / :func:`report`: all of it, for ``antennaknobs structure``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

#: Coordinates are compared at this length (metres): far below any segment,
#: far above the floating-point noise a chain of transforms leaves.
TOL = 1e-4


@dataclass(frozen=True)
class Edge:
    """One straight edge with a uniform mesh: ``n`` segments from ``p0`` to
    ``p1``. ``wire`` is the index in ``build_wires()``; ``sub`` the piece of a
    graded wire (0 for an ordinary wire)."""

    wire: int
    sub: int
    p0: tuple
    p1: tuple
    n: int
    radius: float

    @property
    def length(self) -> float:
        return float(np.linalg.norm(np.subtract(self.p1, self.p0)))

    def segments(self):
        a, b = np.asarray(self.p0, float), np.asarray(self.p1, float)
        return [
            (a + (b - a) * k / self.n, a + (b - a) * (k + 1) / self.n)
            for k in range(self.n)
        ]


@dataclass(frozen=True)
class Isometry:
    """``x ↦ R x + t``, R orthogonal (det −1 for a reflection)."""

    R: np.ndarray
    t: np.ndarray

    def __call__(self, p):
        return self.R @ np.asarray(p, float) + self.t

    @property
    def keeps_heights(self) -> bool:
        """Every point keeps its z: the moves a ground plane allows."""
        return bool(
            np.allclose(self.R[2], (0.0, 0.0, 1.0), atol=1e-9) and abs(self.t[2]) < TOL
        )

    @property
    def is_identity(self) -> bool:
        return bool(
            np.allclose(self.R, np.eye(3), atol=1e-9)
            and np.allclose(self.t, 0.0, atol=TOL)
        )


@dataclass(frozen=True)
class Plane:
    """The plane ``normal · x = offset`` (unit normal)."""

    normal: tuple
    offset: float

    def reflect(self, p):
        n = np.asarray(self.normal, float)
        p = np.asarray(p, float)
        return p - 2.0 * (n @ p - self.offset) * n

    @property
    def vertical(self) -> bool:
        return abs(self.normal[2]) < 1e-9

    def describe(self) -> str:
        n = np.asarray(self.normal, float)
        off = 0.0 if abs(self.offset) < TOL else self.offset
        for axis, name in enumerate("xyz"):
            if abs(abs(n[axis]) - 1.0) < 1e-9:
                return f"{name} = {off * n[axis] + 0.0:.4g} m"
        return f"({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f}) · x = {off:.4g} m"


@dataclass
class PairClass:
    """Edge pairs with one relative pose. ``members`` are ``(i, j, iso, flip_i,
    flip_j)``: the edges, the isometry carrying the representative's first and
    second edge onto them, and whether each runs against its image."""

    rep: tuple
    members: list = field(default_factory=list)
    entries: int = 0  # segment pairs in one block of this class


def edges_of(builder) -> list[Edge]:
    """The straight, uniformly meshed edges of a built design."""
    from .wire_catalog import GradedSegments, as_wire

    default = (
        getattr(builder.build_wire_material(), "radius", None)
        if hasattr(builder, "build_wire_material")
        else None
    )
    out = []
    for i, raw in enumerate(builder.build_wires()):
        w = as_wire(raw)
        radius = float(getattr(w.spec, "radius", None) or default or 0.0)
        if isinstance(w.n_seg, GradedSegments):
            pieces = w.n_seg.subdivide(w.p0, w.p1)
        else:
            if w.n_seg is None:
                raise ValueError(f"wire {i} has no segment count: build it with n_seg")
            pieces = [(w.p0, w.p1, int(w.n_seg))]
        for k, (q0, q1, n) in enumerate(pieces):
            out.append(
                Edge(i, k, tuple(map(float, q0)), tuple(map(float, q1)), int(n), radius)
            )
    return out


def _key(p) -> tuple:
    return tuple(np.round(np.asarray(p, float) / TOL).astype(np.int64))


def _segment_index(edges):
    idx = {}
    for e, edge in enumerate(edges):
        for s, (a, b) in enumerate(edge.segments()):
            idx[tuple(sorted((_key(a), _key(b))))] = (e, s)
    return idx


def _maps_onto_itself(edges, fn, idx=None) -> bool:
    idx = _segment_index(edges) if idx is None else idx
    for edge in edges:
        for a, b in edge.segments():
            hit = idx.get(tuple(sorted((_key(fn(a)), _key(fn(b))))))
            if hit is None or edges[hit[0]].radius != edge.radius:
                return False
    return True


def mirror_planes(edges) -> list[Plane]:
    """Planes that map every segment onto a segment of the same radius. The
    candidates are the planes through the centroid of the segment midpoints
    normal to x, y, z and to the cloud's principal axes, which covers the
    designs AK builds from mirrors."""
    mids = np.array([(a + b) / 2 for e in edges for a, b in e.segments()])
    if len(mids) == 0:
        return []
    c = mids.mean(axis=0)
    normals = [np.eye(3)[k] for k in range(3)]
    if len(mids) > 2:
        _, _, vt = np.linalg.svd(mids - c, full_matrices=False)
        normals += [v / np.linalg.norm(v) for v in vt]
    idx, found = _segment_index(edges), []
    for n in normals:
        n = n if n[np.argmax(np.abs(n))] > 0 else -n
        if any(abs(abs(n @ np.asarray(p.normal)) - 1.0) < 1e-9 for p in found):
            continue
        plane = Plane(tuple(float(v) for v in n), float(n @ c))
        # A plane holding the whole structure (a flat Yagi's own plane) maps
        # every segment onto itself and shares nothing: not a symmetry worth naming.
        if np.all(np.abs(mids @ n - plane.offset) < TOL):
            continue
        if _maps_onto_itself(edges, plane.reflect, idx):
            found.append(plane)
    return found


def _fit(src, dst) -> Isometry | None:
    """The isometry carrying points ``src`` onto ``dst`` (reflections allowed),
    or None when none does within TOL."""
    P, Q = np.asarray(src, float), np.asarray(dst, float)
    pc, qc = P.mean(axis=0), Q.mean(axis=0)
    H = (P - pc).T @ (Q - qc)
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    # Collinear points leave R free about their line: any proper fit will do,
    # because only these points' images matter.
    iso = Isometry(R, qc - R @ pc)
    if np.max(np.linalg.norm(np.array([iso(p) for p in P]) - Q, axis=1)) <= TOL:
        return iso
    # Try the other handedness (SVD's choice can miss a reflection or a rotation).
    D = np.diag([1.0, 1.0, -1.0])
    R2 = Vt.T @ D @ U.T
    iso = Isometry(R2, qc - R2 @ pc)
    if np.max(np.linalg.norm(np.array([iso(p) for p in P]) - Q, axis=1)) <= TOL:
        return iso
    return None


def _ends(edge, flip):
    return (edge.p1, edge.p0) if flip else (edge.p0, edge.p1)


def _signature(ei, ej, over_ground) -> tuple:
    """A pose key for the unordered pair: the six distances among the four end
    points, in the order (and edge orientation) that sorts lowest, plus the
    segment counts and radii, plus the heights over ground."""
    best = None
    for A, B in ((ei, ej), (ej, ei)):
        for fa, fb in itertools.product((False, True), repeat=2):
            pts = [*map(np.asarray, _ends(A, fa)), *map(np.asarray, _ends(B, fb))]
            d = tuple(
                round(float(np.linalg.norm(u - v)) / TOL)
                for u, v in itertools.combinations(pts, 2)
            )
            sig = (A.n, B.n, A.radius, B.radius, d)
            if over_ground:
                sig += (tuple(round(float(p[2]) / TOL) for p in pts),)
            if best is None or sig < best[0]:
                best = (sig, (A is ej), fa, fb)
    return best


def edge_pair_classes(edges, over_ground=False) -> list[PairClass]:
    """Unordered edge pairs (a pair with itself included) grouped by relative
    pose; every member carries a checked isometry from the representative."""
    groups: dict = {}
    for i in range(len(edges)):
        for j in range(i, len(edges)):
            sig, swapped, fa, fb = _signature(edges[i], edges[j], over_ground)
            first, second = (j, i) if swapped else (i, j)
            groups.setdefault(sig, []).append((first, second, fa, fb))
    classes = []
    for members in groups.values():
        r1, r2, rfa, rfb = members[0]
        rep_pts = [*_ends(edges[r1], rfa), *_ends(edges[r2], rfb)]
        cls = PairClass(rep=(r1, r2))
        a, b = edges[r1], edges[r2]
        cls.entries = a.n * (a.n + 1) // 2 if r1 == r2 else a.n * b.n
        for i, j, fa, fb in members:
            pts = [*_ends(edges[i], fa), *_ends(edges[j], fb)]
            iso = _fit(rep_pts, pts)
            if iso is None or (over_ground and not iso.keeps_heights):
                # A key collision or a pose the ground does not allow: its own class.
                classes.append(
                    PairClass(
                        rep=(i, j),
                        members=[(i, j, None, False, False)],
                        entries=(
                            edges[i].n * (edges[i].n + 1) // 2
                            if i == j
                            else edges[i].n * edges[j].n
                        ),
                    )
                )
                continue
            # Orientation against the representative: the fit maps the
            # representative's ends, in its own order, onto these ends in this order.
            cls.members.append((i, j, iso, fa != rfa, fb != rfb))
        if cls.members:
            classes.append(cls)
    return classes


def segment_pair_counts(edges, planes=(), over_ground=False) -> dict:
    """Distinct segment pairs, unordered: all of them, under the mirror
    ``planes`` (the group they generate), and under any repeat."""
    segs = [s for e in edges for s in e.segments()]
    n = len(segs)
    out = {"segments": n, "pairs": n * (n + 1) // 2}
    idx = {tuple(sorted((_key(a), _key(b)))): k for k, (a, b) in enumerate(segs)}
    if planes:
        perms = []
        for p in planes:
            perms.append(
                [
                    idx[tuple(sorted((_key(p.reflect(a)), _key(p.reflect(b)))))]
                    for a, b in segs
                ]
            )
        group = [list(range(n))]
        while True:
            new = [[m[g[k]] for k in range(n)] for g in group for m in perms]
            add = [h for h in new if h not in group]
            if not add:
                break
            group += [h for i, h in enumerate(add) if h not in add[:i]]
        seen, distinct = set(), 0
        for i in range(n):
            for j in range(i, n):
                if (i, j) in seen:
                    continue
                distinct += 1
                for g in group:
                    a, b = g[i], g[j]
                    seen.add((min(a, b), max(a, b)))
        out["mirrors"] = distinct
    keys = set()
    for i in range(n):
        for j in range(i, n):
            best = None
            for (p, q), (r, s) in ((segs[i], segs[j]), (segs[j], segs[i])):
                for P, Q in ((p, q), (q, p)):
                    for R_, S_ in ((r, s), (s, r)):
                        pts = (P, Q, R_, S_)
                        d = tuple(
                            round(float(np.linalg.norm(u - v)) / TOL)
                            for u, v in itertools.combinations(pts, 2)
                        )
                        if over_ground:
                            d += tuple(round(float(u[2]) / TOL) for u in pts)
                        if best is None or d < best:
                            best = d
            keys.add(best)
    out["repeat"] = len(keys)
    return out


@dataclass
class Structure:
    edges: list
    planes: list
    classes_free: list
    classes_ground: list
    counts: dict | None = None
    counts_ground: dict | None = None

    def block_entries(self, over_ground=False) -> tuple[int, int]:
        """(segment-pair entries in all edge-pair blocks, entries in one block
        per class): the fill a block-level reuse would compute."""
        classes = self.classes_ground if over_ground else self.classes_free
        total = sum(c.entries * len(c.members) for c in classes)
        return total, sum(c.entries for c in classes)


def analyze(builder, pairs=False) -> Structure:
    """Everything :func:`report` prints. ``pairs`` adds the segment-level
    counts, which are quadratic in segments (about a second at 300)."""
    edges = edges_of(builder)
    planes = mirror_planes(edges)
    s = Structure(
        edges, planes, edge_pair_classes(edges, False), edge_pair_classes(edges, True)
    )
    if pairs:
        s.counts = segment_pair_counts(edges, planes, False)
        s.counts_ground = segment_pair_counts(
            edges, [p for p in planes if p.vertical], True
        )
    return s


def report(s: Structure) -> str:
    n_seg = sum(e.n for e in s.edges)
    lines = [f"{len(s.edges)} straight edges, {n_seg} segments"]
    if s.planes:
        lines.append(
            "mirror planes: "
            + "; ".join(
                p.describe()
                + ("" if p.vertical else " (not vertical: lost over ground)")
                for p in s.planes
            )
        )
    else:
        lines.append("mirror planes: none")
    for label, ground in (("free space", False), ("over ground", True)):
        total, needed = s.block_entries(ground)
        classes = s.classes_ground if ground else s.classes_free
        shared = sum(1 for c in classes if len(c.members) > 1)
        lines.append(
            f"edge-pair blocks, {label}: {sum(len(c.members) for c in classes)} blocks in "
            f"{len(classes)} poses ({shared} shared); one block per pose fills "
            f"{needed} of {total} segment pairs ({total / max(needed, 1):.2f}x fewer)"
        )
    for label, c in (("free space", s.counts), ("over ground", s.counts_ground)):
        if c is None:
            continue
        txt = f"segment pairs, {label}: {c['pairs']} unordered"
        if "mirrors" in c:
            txt += (
                f"; {c['mirrors']} under the mirrors ({c['pairs'] / c['mirrors']:.2f}x)"
            )
        txt += f"; {c['repeat']} under any repeat ({c['pairs'] / c['repeat']:.2f}x)"
        lines.append(txt)
    lines.append(
        "Read-only: nothing here changes a solve (AK#2165; the reuse itself is momwire#1809)."
    )
    return "\n".join(lines)
