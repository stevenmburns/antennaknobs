from contextlib import contextmanager

import numpy as np

from .wire_catalog import as_wire


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

    def push(self, tr):
        self.stack.append(self.stack[-1].postmult(tr))

    def pop(self):
        self.stack.pop()

    def hit(self, v):
        return self.stack[-1].hit(v)

    def emit(self, raw_w):
        """Append ``raw_w`` (a ``Wire`` or a plain wire tuple) to ``wires``
        with both endpoints under the current transform."""
        w = as_wire(raw_w)
        self.wires.append(w._replace(p0=self.hit(w.p0), p1=self.hit(w.p1)))

    @contextmanager
    def push_pop_tr(self, tr: Transform):
        """``push(tr)`` for the ``with`` block, popped on the way out even if
        the block raises."""
        self.push(tr)
        try:
            yield
        finally:
            self.pop()
