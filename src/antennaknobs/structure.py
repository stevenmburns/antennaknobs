"""A design's repeated geometry, as the fill sees it (AK#2165, momwire#1555).

Repeated geometry gives repeated entries in the MoM matrix. The expensive part
of momwire's bs2 fill is a set of scalar moment integrals on segment pairs
that depend only on the distances between the segments, so two pairs of
straight edges related by one isometry have the same block of them. Over a
ground that is the same everywhere horizontally, the image and remainder terms
keep that only for moves that keep every point's height: horizontal
translation, rotation about z, and mirrors in vertical planes. (A radial
screen or a second ground medium allows less; this module does not model
either.)

This module finds that structure in the mesh the momwire engine would solve
and reports what it could save. It is read-only: nothing here changes a solve.

- :func:`edges_of`: the straight, uniformly meshed edges momwire fills by,
  read from the engine's own wire translation (feed parity, port splits and
  the ground-plane split included).
- :func:`mirror_planes`: planes that map the whole structure onto itself.
- :func:`edge_pair_classes`: unordered edge pairs grouped by relative pose,
  each member with the isometry from its class's representative, fitted and
  checked. This is the block reuse momwire#1809 describes.
- :func:`segment_pair_counts`: distinct segment pairs under the mirrors and
  under any repeat, the upper bound that also shares entries inside a block.
- :func:`analyze` / :func:`report`: all of it, for ``antennaknobs structure``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

#: Coordinates are compared at this length (metres): far below any segment,
#: far above the floating-point noise a chain of transforms leaves, and above
#: the 6 significant digits a NEC deck carries for a structure of tens of metres.
TOL = 1e-4

#: Pose keys round distances to this coarser grid; members that share a key are
#: then told apart (or joined) by an actual fit, so the rounding cannot split a
#: pose or merge two.
_KEY = 1e-2


@dataclass(frozen=True)
class Edge:
    """One straight edge with a uniform mesh: ``n`` segments from ``p0`` to
    ``p1``, on polyline ``wire`` (its ``sub``-th edge). ``material`` is a key
    for the whole wire spec (radius, conductor, jacket); ``radius`` is shown."""

    wire: int
    sub: int
    p0: tuple
    p1: tuple
    n: int
    radius: float
    material: str = ""

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
            np.allclose(self.R[2], (0.0, 0.0, 1.0), atol=1e-6) and abs(self.t[2]) < TOL
        )


#: The isometry `edge_pair_classes(isometries=False)` gives every member.
_IDENTITY = Isometry(np.eye(3), np.zeros(3))


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
        return abs(self.normal[2]) < 1e-6

    def describe(self) -> str:
        n = np.asarray(self.normal, float)
        off = 0.0 if abs(self.offset) < TOL else self.offset
        for axis, name in enumerate("xyz"):
            if abs(abs(n[axis]) - 1.0) < 1e-6:
                return f"{name} = {off * np.sign(n[axis]) + 0.0:.4g} m"
        n = np.where(np.abs(n) < 5e-4, 0.0, n) + 0.0
        return f"({n[0]:.3f}, {n[1]:.3f}, {n[2]:.3f}) · x = {off:.4g} m"


@dataclass
class PairClass:
    """Edge pairs with one relative pose. ``members`` are ``(i, j, iso, flip_i,
    flip_j)``: the edges, the isometry carrying the representative's first and
    second edge onto them, and whether each runs against its image."""

    rep: tuple
    members: list = field(default_factory=list)
    entries: int = 0  # segment pairs in one block of this class


def _block_entries(ei: Edge, ej: Edge, same: bool) -> int:
    return ei.n * (ei.n + 1) // 2 if same else ei.n * ej.n


# --- the mesh ---------------------------------------------------------------


def _material_key(spec) -> str:
    return "default" if spec is None else repr(spec)


def edges_from_wires(builder) -> list[Edge]:
    """The authored wires, as written (a graded wire as its uniform pieces).
    :func:`edges_of` uses the engine's mesh instead; this is its fallback."""
    from .wire_catalog import GradedSegments, as_wire

    material = (
        builder.build_wire_material()
        if hasattr(builder, "build_wire_material")
        else None
    )
    out = []
    for i, raw in enumerate(builder.build_wires()):
        w = as_wire(raw)
        spec = w.spec or material
        radius = float(getattr(spec, "radius", None) or 0.0)
        if isinstance(w.n_seg, GradedSegments):
            pieces = w.n_seg.subdivide(w.p0, w.p1)
        else:
            if w.n_seg is None:
                raise ValueError(f"wire {i} has no segment count: build it with n_seg")
            pieces = [(w.p0, w.p1, int(w.n_seg))]
        for k, (q0, q1, n) in enumerate(pieces):
            out.append(
                Edge(
                    i,
                    k,
                    tuple(map(float, q0)),
                    tuple(map(float, q1)),
                    int(n),
                    radius,
                    _material_key(spec),
                )
            )
    return out


def edges_of(
    builder, engine: str = "momwire:bspline", ground=None
) -> tuple[list[Edge], str | None]:
    """The straight edges ``engine`` would fill, read from its own wire
    translation: the feed-parity coercion, the splits at ports and at the
    ground plane, and each polyline's wire spec. ``(edges, note)``; the note is
    None, or says the authored wires were used because the engine would not
    build this design."""
    try:
        from .cli import make_engine_factory

        e = make_engine_factory(engine, ground)(builder)
    except Exception as exc:  # noqa: BLE001 — any refusal falls back to the wires as written
        return edges_from_wires(
            builder
        ), f"authored wires ({engine} would not build this design: {exc})"
    return edges_of_engine(e), None


def edges_of_engine(e) -> list[Edge]:
    """The straight edges of a built momwire engine's own wire translation."""
    polylines, counts, specs = e._polylines, e._edge_segments, e._polyline_specs
    builder = e.builder
    material = (
        builder.build_wire_material()
        if hasattr(builder, "build_wire_material")
        else None
    )
    out = []
    for p, (verts, ns) in enumerate(zip(polylines, counts, strict=True)):
        spec = specs[p] if specs[p] is not None else material
        radius = float(getattr(spec, "radius", None) or 0.0)
        v = np.asarray(verts, float)
        for k, n in enumerate(ns):
            out.append(
                Edge(
                    p,
                    k,
                    tuple(map(float, v[k])),
                    tuple(map(float, v[k + 1])),
                    int(n),
                    radius,
                    _material_key(spec),
                )
            )
    return out


def pair_reuse_hint(edges) -> list:
    """momwire's ``pair_reuse`` hint (momwire#1809): per pose class of two or
    more members, ``[((wire, edge), (wire, edge)), ...]`` with the
    representative first. Free-space classes, so a pair repeated at another
    height is still offered; momwire checks every member against its own
    geometry and copies only what that geometry repeats (the Sommerfeld
    remainder only where heights are kept). A member running against its
    representative's direction is left out: the copy maps segment k to
    segment k."""
    hint = []
    for c in edge_pair_classes(edges, over_ground=False, isometries=False):
        members = [
            ((edges[i].wire, edges[i].sub), (edges[j].wire, edges[j].sub))
            for i, j, _iso, fi, fj in c.members
            if not fi and not fj
        ]
        if len(members) > 1:
            hint.append(members)
    return hint


# --- tolerant lookup ----------------------------------------------------------


class _PointIndex:
    """Points within TOL of one another are one point, wherever the grid cuts:
    a lookup probes the neighbouring cells as well as its own."""

    def __init__(self):
        self.cells: dict = {}

    @staticmethod
    def _cell(p):
        return tuple(np.floor(np.asarray(p, float) / TOL).astype(np.int64))

    def add(self, p, value):
        self.cells.setdefault(self._cell(p), []).append((np.asarray(p, float), value))

    def find(self, p):
        p = np.asarray(p, float)
        c = self._cell(p)
        for d in itertools.product((-1, 0, 1), repeat=3):
            for q, v in self.cells.get((c[0] + d[0], c[1] + d[1], c[2] + d[2]), ()):
                if np.linalg.norm(q - p) <= TOL:
                    yield v


def _segment_index(edges):
    """Segments by midpoint, for an orientation-free match within TOL."""
    idx = _PointIndex()
    for e, edge in enumerate(edges):
        for s, (a, b) in enumerate(edge.segments()):
            idx.add((a + b) / 2, (e, s, a, b))
    return idx


def _find_segment(idx, a, b):
    for e, s, p, q in idx.find((a + b) / 2):
        if (np.linalg.norm(p - a) <= TOL and np.linalg.norm(q - b) <= TOL) or (
            np.linalg.norm(p - b) <= TOL and np.linalg.norm(q - a) <= TOL
        ):
            return e, s
    return None


def _maps_onto_itself(edges, fn, idx) -> bool:
    for edge in edges:
        for a, b in edge.segments():
            hit = _find_segment(idx, fn(a), fn(b))
            if hit is None or edges[hit[0]].material != edge.material:
                return False
    return True


# --- mirror planes ------------------------------------------------------------


def mirror_planes(edges) -> list[Plane]:
    """Planes that map every segment onto a segment of the same material.

    Any such plane passes through the centroid of the segment midpoints, and
    swaps or fixes the points of each shell of midpoints at one distance from
    it. The candidates are the planes normal to x, y, z and the principal axes,
    plus, for the smallest shell with more than one point, the perpendicular
    bisector of every pair of its points (which is how a vertical's radials,
    or any n-fold arrangement, show their planes)."""
    mids = np.array([(a + b) / 2 for e in edges for a, b in e.segments()])
    if len(mids) == 0:
        return []
    c = mids.mean(axis=0)
    normals = [np.eye(3)[k] for k in range(3)]
    if len(mids) > 2:
        _, _, vt = np.linalg.svd(mids - c, full_matrices=False)
        normals += list(vt)
    # Shells of midpoints at one distance from the centroid, clustered within
    # TOL (no rounding grid to cut a shell in two). A coincidental shell gives
    # candidates that fail the test below; a few shells make a real one likely.
    r = np.linalg.norm(mids - c, axis=1)
    order = np.argsort(r)
    shells, cur = [], [order[0]]
    for k in order[1:]:
        if r[k] - r[cur[-1]] <= TOL:
            cur.append(k)
        else:
            shells.append(cur)
            cur = [k]
    shells.append(cur)
    seen_normals = set()
    for shell in sorted((v for v in shells if len(v) > 1), key=len)[:8]:
        for a, b in itertools.combinations(mids[shell[:16]], 2):
            d = a - b
            if np.linalg.norm(d) <= TOL:
                continue
            d = d / np.linalg.norm(d)
            d = d if d[np.argmax(np.abs(d))] > 0 else -d
            key = tuple(np.round(d, 6))
            if key not in seen_normals:
                seen_normals.add(key)
                normals.append(d)
    idx, found = _segment_index(edges), []
    for n in normals:
        n = np.asarray(n, float) / np.linalg.norm(n)
        n = n if n[np.argmax(np.abs(n))] > 0 else -n
        if any(abs(abs(n @ np.asarray(p.normal)) - 1.0) < 1e-6 for p in found):
            continue
        plane = Plane(tuple(float(v) for v in n), float(n @ c))
        # A plane holding the whole structure (a flat Yagi's own plane) maps
        # every segment onto itself and shares nothing: not a symmetry worth naming.
        if np.all(np.abs(mids @ n - plane.offset) < TOL):
            continue
        if _maps_onto_itself(edges, plane.reflect, idx):
            found.append(plane)
    return found


# --- edge-pair classes ----------------------------------------------------------


def _check(iso, P, Q) -> bool:
    return bool(
        np.max(np.linalg.norm(np.array([iso(p) for p in P]) - Q, axis=1)) <= TOL
    )


def _fit(src, dst) -> Isometry | None:
    """An isometry carrying points ``src`` onto ``dst`` (reflections allowed),
    or None when none does within TOL. Both handednesses are tried."""
    P, Q = np.asarray(src, float), np.asarray(dst, float)
    pc, qc = P.mean(axis=0), Q.mean(axis=0)
    U, _, Vt = np.linalg.svd((P - pc).T @ (Q - qc))
    for D in (np.eye(3), np.diag([1.0, 1.0, -1.0])):
        R = Vt.T @ D @ U.T
        iso = Isometry(R, qc - R @ pc)
        if _check(iso, P, Q):
            return iso
    return None


def _fit_keeping_heights(src, dst) -> Isometry | None:
    """An isometry that keeps every height (R = [[R2, 0], [0, 1]], t_z = 0),
    carrying ``src`` onto ``dst``: the fit in the horizontal plane alone, so a
    collinear set's free turn about its line can't tip it."""
    P, Q = np.asarray(src, float), np.asarray(dst, float)
    if np.max(np.abs(P[:, 2] - Q[:, 2])) > TOL:
        return None
    p2, q2 = P[:, :2], Q[:, :2]
    pc, qc = p2.mean(axis=0), q2.mean(axis=0)
    U, _, Vt = np.linalg.svd((p2 - pc).T @ (q2 - qc))
    for D in (np.eye(2), np.diag([1.0, -1.0])):
        R2 = Vt.T @ D @ U.T
        R = np.eye(3)
        R[:2, :2] = R2
        t = np.zeros(3)
        t[:2] = qc - R2 @ pc
        iso = Isometry(R, t)
        if _check(iso, P, Q):
            return iso
    return None


def _ends(edge, flip):
    return (edge.p1, edge.p0) if flip else (edge.p0, edge.p1)


class _PoseKeys:
    """Every end point's rounded distance to every other, and its rounded
    height, computed once: a pair's pose key is then integer lookups, not six
    vector norms per orientation (the search ran 25 ms on a 15-edge CED)."""

    def __init__(self, edges):
        X = np.array([p for e in edges for p in (e.p0, e.p1)], dtype=float)
        X = X.reshape(-1, 3)
        D = np.sqrt(np.sum((X[:, None, :] - X[None, :, :]) ** 2, axis=-1))
        self.X, self.D = X, D
        # np.rint rounds half to even, as round() does.
        self.d = np.rint(D / _KEY).astype(np.int64).tolist()
        self.z = np.rint(X[:, 2] / _KEY).astype(np.int64).tolist()


def _signature(keys, edges, i, j, over_ground) -> tuple:
    """A coarse pose key for the unordered pair (whether it is an edge with
    itself, segment counts, materials, the six end-point distances, and the
    heights over ground), in the order and orientation that sorts lowest, plus
    that order and orientation."""
    d, z = keys.d, keys.z
    best = None
    for A, B in ((i, j), (j, i)):
        ea, eb = edges[A], edges[B]
        for fa, fb in itertools.product((False, True), repeat=2):
            a0, a1 = 2 * A + fa, 2 * A + (not fa)
            b0, b1 = 2 * B + fb, 2 * B + (not fb)
            dist = (d[a0][a1], d[a0][b0], d[a0][b1], d[a1][b0], d[a1][b1], d[b0][b1])
            sig = (i == j, ea.n, eb.n, ea.material, eb.material, dist)
            if over_ground:
                sig += ((z[a0], z[a1], z[b0], z[b1]),)
            if best is None or sig < best[0]:
                best = (sig, A == j and A != i, fa, fb)
    return best


def _congruent(keys, over_ground):
    """`_fit`'s question without the isometry: do two ordered end-point
    quadruples have the same six distances within TOL (and, over ground, the
    same heights)? Equal distances are exactly when an isometry, reflections
    allowed, carries one onto the other; with equal heights too, one that
    keeps every height does."""
    D, X = keys.D, keys.X
    pairs = tuple(itertools.combinations(range(4), 2))

    def check(rep_idx, idx):
        for a, b in pairs:
            if abs(D[rep_idx[a], rep_idx[b]] - D[idx[a], idx[b]]) > TOL:
                return False
        return not (
            over_ground and np.max(np.abs(X[list(rep_idx), 2] - X[list(idx), 2])) > TOL
        )

    return check


def edge_pair_classes(edges, over_ground=False, isometries=True) -> list[PairClass]:
    """Unordered edge pairs (an edge with itself included) grouped by relative
    pose. Every member carries an isometry from its class's representative,
    fitted and checked against the end points; over ground the fit keeps every
    height. Pairs that share a coarse key but no isometry become separate classes.

    ``isometries=False`` decides membership by the six end-point distances
    alone (the same classes, as an isometry exists exactly when they agree)
    and gives every member an identity in place of its isometry: the hint
    needs only who repeats whom, and the fits were most of its time."""
    keys = _PoseKeys(edges)
    if isometries:
        fit = _fit_keeping_heights if over_ground else _fit
    else:
        check = _congruent(keys, over_ground)
    groups: dict = {}
    for i in range(len(edges)):
        for j in range(i, len(edges)):
            sig, swapped, fa, fb = _signature(keys, edges, i, j, over_ground)
            first, second = (j, i) if swapped else (i, j)
            groups.setdefault(sig, []).append((first, second, fa, fb))
    classes = []
    for members in groups.values():
        local: list[tuple[PairClass, list, bool, bool]] = []
        for i, j, fa, fb in members:
            if isometries:
                pts = [*_ends(edges[i], fa), *_ends(edges[j], fb)]
            else:
                pts = (2 * i + fa, 2 * i + (not fa), 2 * j + fb, 2 * j + (not fb))
            for cls, rep_pts, rfa, rfb in local:
                if isometries:
                    iso = fit(rep_pts, pts)
                else:
                    iso = _IDENTITY if check(rep_pts, pts) else None
                if iso is not None:
                    cls.members.append((i, j, iso, fa != rfa, fb != rfb))
                    break
            else:
                cls = PairClass(
                    rep=(i, j), entries=_block_entries(edges[i], edges[j], i == j)
                )
                cls.members.append(
                    (i, j, Isometry(np.eye(3), np.zeros(3)), False, False)
                )
                local.append((cls, pts, fa, fb))
        classes += [c for c, *_ in local]
    return classes


# --- segment-level counts ---------------------------------------------------------


def _canonical_rows(segs, over_ground):
    """One integer row per unordered segment pair: the lowest of its eight
    readings (pair order, and each segment's direction) of the six end-point
    distances, rounded to TOL, plus the four heights over ground."""
    S = np.array([[a, b] for a, b in segs])  # (N, 2, 3)
    n = len(S)
    I, J = np.triu_indices(n)
    variants = []
    for A, B in ((I, J), (J, I)):
        for fa, fb in itertools.product((0, 1), repeat=2):
            pts = [S[A, fa], S[A, 1 - fa], S[B, fb], S[B, 1 - fb]]
            cols = [
                np.rint(np.linalg.norm(u - v, axis=1) / TOL)
                for u, v in itertools.combinations(pts, 2)
            ]
            if over_ground:
                cols += [np.rint(p[:, 2] / TOL) for p in pts]
            variants.append(np.stack(cols, axis=1).astype(np.int64))
    V = np.stack(variants, axis=1)  # (P, 8, k)
    alive = np.ones(V.shape[:2], bool)
    for col in range(V.shape[2]):
        vals = np.where(alive, V[:, :, col], np.iinfo(np.int64).max)
        alive &= vals == vals.min(axis=1, keepdims=True)
    pick = alive.argmax(axis=1)
    return V[np.arange(len(V)), pick]


def segment_pair_counts(edges, planes=(), over_ground=False) -> dict:
    """Distinct segment pairs, unordered: all of them, under the mirror
    ``planes`` (the group they generate), and under any repeat (distances
    rounded to TOL, so this is a count at that resolution)."""
    segs = [s for e in edges for s in e.segments()]
    n = len(segs)
    out = {"segments": n, "pairs": n * (n + 1) // 2}
    if planes:
        idx = _segment_index(edges)
        flat = {
            (e, s): k
            for k, (e, s) in enumerate(
                (e, s) for e, edge in enumerate(edges) for s in range(edge.n)
            )
        }
        perms = []
        for p in planes:
            perm = []
            for a, b in segs:
                hit = _find_segment(idx, p.reflect(a), p.reflect(b))
                perm.append(flat[hit])
            perms.append(perm)
        group = [list(range(n))]
        while True:
            new = []
            for g in group:
                for m in perms:
                    h = [m[g[k]] for k in range(n)]
                    if h not in group and h not in new:
                        new.append(h)
            if not new:
                break
            group += new
        G = np.array(group)  # (|G|, n)
        I, J = np.triu_indices(n)
        codes = []
        for g in G:
            a, b = g[I], g[J]
            codes.append(np.minimum(a, b) * n + np.maximum(a, b))
        orbit_min = np.min(np.stack(codes), axis=0)
        out["mirrors"] = int(len(np.unique(orbit_min)))
    out["repeat"] = int(len(np.unique(_canonical_rows(segs, over_ground), axis=0)))
    return out


# --- the whole analysis -------------------------------------------------------------


@dataclass
class Structure:
    edges: list
    planes: list
    classes_free: list
    classes_ground: list
    counts: dict | None = None
    counts_ground: dict | None = None
    note: str | None = None

    def block_entries(self, over_ground=False) -> tuple[int, int]:
        """(segment-pair entries in all edge-pair blocks, entries in one block
        per class): the fill a block-level reuse would compute."""
        classes = self.classes_ground if over_ground else self.classes_free
        total = sum(c.entries * len(c.members) for c in classes)
        return total, sum(c.entries for c in classes)


def analyze(builder, pairs=False, engine="momwire:bspline") -> Structure:
    """Everything :func:`report` prints, on the mesh ``engine`` would solve.
    ``pairs`` adds the segment-level counts (vectorised; quadratic in segments)."""
    edges, note = edges_of(builder, engine)
    planes = mirror_planes(edges)
    s = Structure(
        edges,
        planes,
        edge_pair_classes(edges, False),
        edge_pair_classes(edges, True),
        note=note,
    )
    if pairs:
        s.counts = segment_pair_counts(edges, planes, False)
        s.counts_ground = segment_pair_counts(
            edges, [p for p in planes if p.vertical], True
        )
    return s


def report(s: Structure) -> str:
    n_seg = sum(e.n for e in s.edges)
    lines = [
        f"{len(s.edges)} straight edges, {n_seg} segments"
        + (f" ({s.note})" if s.note else "")
    ]
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
        "Over ground assumes the same ground everywhere horizontally (no radial screen, no second medium)."
    )
    lines.append(
        "Read-only: nothing here changes a solve (AK#2165; the reuse itself is momwire#1809)."
    )
    return "\n".join(lines)
