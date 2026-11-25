from contextlib import contextmanager
from itertools import pairwise

import numpy as np

from .wire_catalog import Wire, as_wire


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
