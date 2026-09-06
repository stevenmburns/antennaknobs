"""The methods under test, all counting DISTINCT SOLVES the same way.

Every method routes its solves through a `Tracer`, which keys on the exact
parameter tuple (the #1176 memo's rule) and records, for each *new* tuple, the
running distinct-solve count and the Z it produced. "Solves to tolerance" is
then the count at the FIRST traced solve meeting tolerance -- the same question
asked of every arm, including Nelder-Mead, which otherwise runs on to its own
convergence criterion rather than to ours.
"""

from __future__ import annotations

import numpy as np


class Budget(Exception):
    pass


class Tracer:
    def __init__(self, deck, budget):
        self.deck = deck
        self.budget = budget
        self.seen: dict[tuple, complex] = {}
        self.trace: list[tuple[int, tuple, complex]] = []

    def z(self, x):
        key = tuple(round(float(v), 12) for v in x)
        if key in self.seen:
            return self.seen[key]
        if len(self.seen) >= self.budget:
            raise Budget()
        zz = self.deck.z(key)
        self.seen[key] = zz
        self.trace.append((len(self.seen), key, zz))
        return zz

    @property
    def n(self):
        return len(self.seen)

    def first_within(self, tol, z0, case):
        """Distinct solves at which tolerance was first met, or None."""
        for n, _x, z in self.trace:
            v = abs(z.imag) if case == "resonance" else abs(z - z0)
            if v <= tol:
                return n
        return None

    def best(self, z0, case):
        vals = [
            (abs(z.imag) if case == "resonance" else abs(z - z0))
            for _n, _x, z in self.trace
        ]
        i = int(np.argmin(vals))
        return vals[i], self.trace[i][1]

    def path(self):
        return [x for _n, x, _z in self.trace]


# --------------------------------------------------------------------------
# Nelder-Mead: the SHIPPED code path, so the comparison is against production
# --------------------------------------------------------------------------
def run_nm(deck, x0, case, budget, *, seed=False):
    from antennaknobs.web.optimize import optimize

    tr = Tracer(deck, budget)
    names = deck.knobs

    def solve_fn(req):
        z = tr.z([req[n] for n in names])
        return {"z_in_re": z.real, "z_in_im": z.imag, "z0_ohms": deck.z0}

    base = {n: float(v) for n, v in zip(names, x0, strict=True)}
    free = [
        {"name": n, "min": lo, "max": hi}
        for n, (lo, hi) in zip(names, deck.box, strict=True)
    ]
    try:
        optimize(
            base,
            free,
            case,
            solve_fn=solve_fn,
            max_evals=budget * 4,
            seed_surrogate=seed,
        )
    except Budget:
        pass
    return tr


# --------------------------------------------------------------------------
# Case 2: one knob, X = 0. A scalar root.
# --------------------------------------------------------------------------
def run_secant(deck, x0, budget, *, span=0.02, idx=0):
    """Secant on X(knob), seeded with two points a `span` apart. One new solve
    per step -- the previous iterate is reused, which is why this beats a
    Newton FD derivative (2 solves/step) on the same problem."""
    tr = Tracer(deck, budget)
    lo, hi = deck.box[idx]
    base = list(x0)

    def X(v):
        b = list(base)
        b[idx] = min(max(v, lo), hi)
        return tr.z(b).imag

    a = float(x0[idx])
    b = min(max(a + span, lo), hi)
    try:
        fa, fb = X(a), X(b)
        for _ in range(budget):
            if fb == fa:
                break
            c = b - fb * (b - a) / (fb - fa)
            c = min(max(c, lo), hi)
            if abs(c - b) < 1e-12:
                break
            a, fa = b, fb
            b, fb = c, X(c)
            if abs(fb) < 1e-9:
                break
    except Budget:
        pass
    return tr


def run_brent(deck, x0, budget, *, idx=0, n_bracket=5):
    """Bracket X = 0 by scanning the box, then bisect/secant inside it.
    The scan is the honest cost of NOT having a start near the root."""
    tr = Tracer(deck, budget)
    lo, hi = deck.box[idx]
    base = list(x0)

    def X(v):
        b = list(base)
        b[idx] = min(max(v, lo), hi)
        return tr.z(b).imag

    try:
        vs = list(np.linspace(lo, hi, n_bracket))
        fs = [X(v) for v in vs]
        br = None
        for i in range(len(vs) - 1):
            if fs[i] * fs[i + 1] < 0:
                br = (vs[i], fs[i], vs[i + 1], fs[i + 1])
                break
        if br is not None:
            a, fa, b, fb = br
            for _ in range(budget):
                c = b - fb * (b - a) / (fb - fa)  # secant inside bracket
                if not (min(a, b) < c < max(a, b)):
                    c = 0.5 * (a + b)  # fall back to bisection
                fc = X(c)
                if abs(fc) < 1e-9 or abs(b - a) < 1e-12:
                    break
                if fa * fc < 0:
                    b, fb = c, fc
                else:
                    a, fa = c, fc
    except Budget:
        pass
    return tr


def run_newton1(deck, x0, budget, *, idx=0, h=5e-4):
    """Newton on X with a forward-difference derivative: TWO solves per step,
    because the perturbed point is never reused."""
    tr = Tracer(deck, budget)
    lo, hi = deck.box[idx]
    base = list(x0)

    def X(v):
        b = list(base)
        b[idx] = min(max(v, lo), hi)
        return tr.z(b).imag

    v = float(x0[idx])
    try:
        for _ in range(budget):
            f = X(v)
            if abs(f) < 1e-9:
                break
            d = (X(v + h) - f) / h
            if d == 0:
                break
            step = -f / d
            v = min(max(v + step, lo), hi)
            if abs(step) < 1e-12:
                break
    except Budget:
        pass
    return tr


# --------------------------------------------------------------------------
# Case 1: two knobs, Z = Z0. A two-component root.
# --------------------------------------------------------------------------
def _F(z, z0):
    return np.array([z.real - z0, z.imag])


def run_newton2(deck, x0, budget, *, h=None, broyden=False, damp=True):
    """Newton (or Broyden) on F = (R - R0, X).

    Jacobian by forward differences: the base point is REUSED from the previous
    step, so a fresh Jacobian costs 2 solves on two knobs, not 3. Broyden then
    costs 1 solve per step after the first Jacobian, at the price of a stale J.
    Steps are clipped into the box and (with `damp`) halved while the residual
    norm fails to fall -- each halving is one more solve.
    """
    tr = Tracer(deck, budget)
    box = deck.box
    z0 = deck.z0
    if h is None:
        h = [0.002 * (hi - lo) for lo, hi in box]

    def clip(x):
        return np.array(
            [min(max(v, lo), hi) for v, (lo, hi) in zip(x, box, strict=True)]
        )

    x = clip(np.array([float(v) for v in x0]))
    try:

        def jac(x, F):
            """Forward differences, flipped to BACKWARD at an upper bound.

            A naive forward difference is degenerate on the boundary: at the
            box corner every perturbation clips back onto the corner, the
            Jacobian comes out identically zero and the solve dies with a
            singular matrix. Measured on moxon from the far start -- the step
            overshoots to the corner and Newton stops after 4 solves. Choosing
            the direction that stays inside the box is the whole fix.
            """
            J = np.zeros((2, 2))
            for j in range(2):
                lo_j, hi_j = box[j]
                step = h[j] if x[j] + h[j] <= hi_j else -h[j]
                if x[j] + step < lo_j:
                    step = h[j]
                xp = x.copy()
                xp[j] = min(max(xp[j] + step, lo_j), hi_j)
                dh = xp[j] - x[j]
                J[:, j] = (_F(tr.z(xp), z0) - F) / (dh if dh else h[j])
            return J

        F = _F(tr.z(x), z0)
        J = jac(x, F)
        for _ in range(budget):
            if np.linalg.norm(F) < 1e-9:
                break
            try:
                step = np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                break
            t = 1.0
            while True:
                xn = clip(x + t * step)
                Fn = _F(tr.z(xn), z0)
                if not damp or np.linalg.norm(Fn) < np.linalg.norm(F) or t < 0.06:
                    break
                t *= 0.5
            dx, dF = xn - x, Fn - F
            x, F = xn, Fn
            if broyden:
                if np.dot(dx, dx) > 0:
                    J = J + np.outer(dF - J @ dx, dx) / np.dot(dx, dx)
            else:
                J = jac(x, F)
            if np.linalg.norm(dx) < 1e-12:
                break
    except Budget:
        pass
    return tr


def run_hybrid(deck, x0, budget, *, n_seed=6, broyden=True, seed_state=0):
    """The #1176 surrogate seed for a START, then a root-finder for the FINISH.

    The seed is what makes the far start survivable; the root-finder is what
    makes the endgame cheap. Neither half does the other's job well.
    """
    rng = np.random.default_rng(seed_state)
    tr = Tracer(deck, budget)
    box = deck.box
    z0 = deck.z0
    best = (float("inf"), tuple(float(v) for v in x0))
    try:
        # Latin-ish sample of the box, plus the caller's own start.
        pts = [tuple(float(v) for v in x0)]
        for k in range(n_seed):
            u = (rng.random(2) + k) / n_seed
            rng.shuffle(u)
            pts.append(
                tuple(lo + ui * (hi - lo) for ui, (lo, hi) in zip(u, box, strict=True))
            )
        for p in pts:
            v = abs(tr.z(p) - z0)
            if v < best[0]:
                best = (v, p)
    except Budget:
        return tr
    tr2 = run_newton2(deck, best[1], budget - tr.n, broyden=broyden)
    # splice: the seed's solves then the root-finder's, renumbered
    for _n, x, z in tr2.trace:
        if x not in tr.seen:
            tr.seen[x] = z
            tr.trace.append((len(tr.seen), x, z))
    return tr
