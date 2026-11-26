import math
from contextlib import contextmanager
from itertools import pairwise, product

import numpy as np

from .wire_catalog import Wire, as_wire

# shared_seams joins endpoints within this fraction of the block's size (its
# largest coordinate, at least 1 m). A seam a rotation leaves behind is a few
# ulps of the coordinate, about 1e-16 relative per transform, and stays under
# 1e-12 through MAX_NESTING levels and 256 accumulated passes; 1e-9 is three
# orders above that and, at a 1 m scale, five orders below the thinnest
# catalog wire's radius, so no two ends a designer meant apart are joined.
SEAM_TOL = 1e-9


class Transform:
    def __init__(self, A=np.eye(4)):
        self.A = A

    @staticmethod
    def inverse(tr):
        return Transform(np.linalg.inv(tr.A))

    @staticmethod
    def translate(x, y, z):
        return Transform(
            np.array([[1, 0, 0, x], [0, 1, 0, y], [0, 0, 1, z], [0, 0, 0, 1]])
        )

    @staticmethod
    def scale(sx=1, sy=1, sz=1):
        """Scale each axis; a -1 mirrors that axis."""
        return Transform(
            np.array([[sx, 0, 0, 0], [0, sy, 0, 0], [0, 0, sz, 0], [0, 0, 0, 1]])
        )

    @staticmethod
    def mirrorYZ():
        """Reflect across the YZ plane (x -> -x)."""
        return Transform.scale(sx=-1)

    @staticmethod
    def mirrorXZ():
        """Reflect across the XZ plane (y -> -y)."""
        return Transform.scale(sy=-1)

    @staticmethod
    def mirrorXY():
        """Reflect across the XY plane (z -> -z)."""
        return Transform.scale(sz=-1)

    @staticmethod
    def rotX(theta_degrees):
        c = np.cos(np.pi / 180 * theta_degrees)
        s = np.sin(np.pi / 180 * theta_degrees)
        return Transform(
            np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]])
        )

    @staticmethod
    def rotY(theta_degrees):
        c = np.cos(np.pi / 180 * theta_degrees)
        s = np.sin(np.pi / 180 * theta_degrees)
        return Transform(
            np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]])
        )

    @staticmethod
    def rotZ(theta_degrees):
        c = np.cos(np.pi / 180 * theta_degrees)
        s = np.sin(np.pi / 180 * theta_degrees)
        return Transform(
            np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        )

    def hit(self, coords):
        v = np.array(coords + (1,))
        V = self.A.dot(v)
        return V[0], V[1], V[2]

    def premult(self, other):
        return Transform(other.A @ self.A)

    def postmult(self, other):
        return Transform(self.A @ other.A)


class TransformStack:
    def __init__(self):
        self.stack = [Transform()]
        self.wires = []
        # A callable ``tracer(kind, stack)`` told after every push ("push",
        # the new top is in place) and every emit ("emit", the wire is
        # appended). Left None by designs; an editor sets it to learn which
        # statement ran under which frame (docs/design/block-builder.md).
        self.tracer = None
        # The ``wire_spec`` blocks open around the current statement,
        # innermost last; see :meth:`wire_spec`.
        self._specs = []

    def push(self, tr):
        self.stack.append(self.stack[-1].postmult(tr))
        if self.tracer is not None:
            self.tracer("push", self)

    def pop(self):
        self.stack.pop()

    def hit(self, v):
        return self.stack[-1].hit(v)

    def emit(self, raw_w):
        """Append ``raw_w`` (a ``Wire`` or a plain wire tuple) to ``wires``
        with both endpoints under the current transform."""
        w = as_wire(raw_w)
        if w.spec is None and self._specs:
            w = w._replace(spec=self._specs[-1])
        self.wires.append(w._replace(p0=self.hit(w.p0), p1=self.hit(w.p1)))
        if self.tracer is not None:
            self.tracer("emit", self)

    @contextmanager
    def push_pop_tr(self, tr: Transform):
        """``push(tr)`` for the ``with`` block, popped on the way out even if
        the block raises."""
        self.push(tr)
        try:
            yield
        finally:
            self.pop()

    @contextmanager
    def wire_spec(self, spec):
        """Make ``spec`` (a ``WireSpec``) the default for every wire emitted
        inside the ``with`` block. Nested blocks stack, innermost wins, and
        ``wire_spec(None)`` restores the design default inside it. A wire
        given its own ``spec=`` keeps it, the precedence ``Wire`` defines;
        the spec is never scaled by a transform, since it is the wire stock,
        not geometry."""
        self._specs.append(spec)
        try:
            yield
        finally:
            self._specs.pop()

    @contextmanager
    def shared_seams(self):
        """Join the seams of the wires emitted inside the ``with`` block: an
        endpoint within SEAM_TOL of one emitted earlier in the block takes
        that earlier point exactly. So the copies a mirror or a rotation
        makes meet where their author meant them to, not an ulp apart, and
        the first copy is never moved. Wires emitted before the block are
        left alone: a join stays inside the block that made it."""
        start = len(self.wires)
        yield
        self._join_seams(start)

    def _join_seams(self, start):
        new = self.wires[start:]
        coords = [float(c) for w in new for p in (w.p0, w.p1) for c in p]
        if not coords or not all(math.isfinite(c) for c in coords):
            return
        tol = SEAM_TOL * max(1.0, max(abs(c) for c in coords))
        # Cells one tolerance wide: a point within tol (per coordinate) of
        # another lies in the same cell or one of its 26 neighbours.
        cells = {}

        def join(p):
            key = tuple(math.floor(float(c) / tol) for c in p)
            for d in product((-1, 0, 1), repeat=3):
                near = (key[0] + d[0], key[1] + d[1], key[2] + d[2])
                for q in cells.get(near, ()):
                    if all(
                        abs(float(a) - float(b)) <= tol
                        for a, b in zip(p, q, strict=True)
                    ):
                        return q
            cells.setdefault(key, []).append(p)
            return p

        for i, w in enumerate(new, start):
            p0, p1 = join(w.p0), join(w.p1)
            if p0 is not w.p0 or p1 is not w.p1:
                self.wires[i] = w._replace(p0=p0, p1=p1)

    def path(self, points, *, closed=False, ex=None, ex_segment=None, **fields):
        """Emit one wire per consecutive pair of ``points``, under the current
        transform, and return them.

        The wires share their endpoints exactly, because each point is hit
        once per wire by the same transform and the same input: two wires
        that meet at a point of the path cannot leave a gap. ``closed=True``
        adds the segment from the last point back to the first.

        ``ex`` puts the excitation on every segment, or on the one at index
        ``ex_segment`` (so ``st.path([D, B], ex=1 + 0j)`` is the feed wire of
        a hentenna, and ``st.path(loop, closed=True, ex=1 + 0j, ex_segment=0)``
        feeds the first side of a loop). Any other ``Wire`` field
        (``n_seg``, ``name``, ``spec``...) is given to every segment.
        """
        pts = list(points)
        if len(pts) < 2:
            raise ValueError("a path needs at least two points")
        if closed:
            pts.append(pts[0])
        n = len(pts) - 1
        if ex_segment is not None and not -n <= ex_segment < n:
            raise ValueError(f"ex_segment {ex_segment} is outside the path's {n} wires")
        out = []
        for i, (a, b) in enumerate(pairwise(pts)):
            fed = ex is not None and (ex_segment is None or i == ex_segment % n)
            w = Wire(a, b, ex=ex if fed else None, **fields)
            self.emit(w)
            out.append(self.wires[-1])
        return out

    def wire_x(self, x0, x1, *, y=0, z=0, **fields):
        """A wire along the current frame's X axis, from ``x0`` to ``x1``, at
        ``y`` and ``z`` (default on the axis). Like ``emit``, under the
        current transform; returns the wire. So a dipole arm is
        ``st.wire_x(0, arm)`` and not ``Wire((0, 0, 0), (arm, 0, 0))``."""
        return self._axis_wire((x0, y, z), (x1, y, z), fields)

    def wire_y(self, y0, y1, *, x=0, z=0, **fields):
        """:meth:`wire_x` along Y, from ``y0`` to ``y1`` at ``x`` and ``z``."""
        return self._axis_wire((x, y0, z), (x, y1, z), fields)

    def wire_z(self, z0, z1, *, x=0, y=0, **fields):
        """:meth:`wire_x` along Z, from ``z0`` to ``z1`` at ``x`` and ``y``."""
        return self._axis_wire((x, y, z0), (x, y, z1), fields)

    def _axis_wire(self, p0, p1, fields):
        self.emit(Wire(p0, p1, **fields))
        return self.wires[-1]
