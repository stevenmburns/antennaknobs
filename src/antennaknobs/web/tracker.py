"""Hold an electrical target while the user drags a knob (issue #1220).

This is numerical CONTINUATION, not optimisation, and the distinction is the
whole design. The user drags knob A; the tracker moves the optimize-marked
knobs to keep the objective satisfied. With the tangent from the last solve,
the implicit function theorem predicts where the held knobs go for free, and
the tick's ordinary display solve -- which the app owes the user anyway --
usually confirms it.

## The cost model

A tick costs ONE solve no matter what: the app must show Z at the new knob
position. So the number that matters is EXTRA solves. Measured in #1202, over
`beams.moxon` and a buried vertical, holding |X| <= 1 ohm:

    16-tick drag   67 % of ticks free    0.40 extra/tick
    31-tick        90 %                  0.13
    61-tick        97 %                  0.05

Finer drags track BETTER, and a real drag is fine -- the send path is a
trailing-edge rAF throttle at ~60 msg/s, so a one-second drag is ~60 ticks.

## The guard (#1216, and every clause was measured)

- LATCH ON HOLDABILITY, not on the fold. Near a saddle-node the residual curve
  GRAZES zero, so the objective stays holdable well past the point where the
  root formally vanishes -- 15 ticks past it on the coupled-pair deck. Latching
  at the fold stops a run the user would not have noticed anything wrong with.
  The latch is: the corrector could not reach tolerance within its cap.
- ARM ONLY ONCE A TANGENT EXISTS. On the first tick the drag partial is still
  unknown, so the "prediction" is *do not move* and its error fires any
  threshold. This bit the two-knob case immediately (demote at tick 1, latch at
  tick 2) once the ratio test below stopped implicitly suppressing it.
- DEMOTE ON PREDICTION ERROR IS SCALAR ONLY. It exists to stop the thrash when
  a scalar root folds. In the two-knob case there is no fold to protect against
  -- det(J) stays healthy right to the box edge -- and a two-component
  prediction error routinely exceeds half the tolerance on a HEALTHY stretch,
  so enabling it there fires ~35 ticks early.
- RATE-LIMIT BY DRAG DISTANCE, NEVER TICKS. Four separate per-tick quantities
  failed to survive a change of drag resolution during the study.
- COMMIT ON A COMPLETED SOLVE ONLY. The server preempts an in-flight solve the
  moment a newer request lands, so a corrector can be cancelled mid-flight;
  `tick()` therefore mutates nothing until every solve it needed has returned.
"""

from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np

from .optimize import _feed_zs, _newton_root2, _residual_vec, _secant_root

# How close the objective has to stay while dragging, in ohms. This is a
# USER-FACING tolerance and deliberately not `optimize._ROOT_FTOL`, which is
# where a root FIND stops converging (1e-3). 1.0 is what #1202 measured
# against.
TRACK_TOL = 1.0
MAX_CORR = 3
DEMOTE_FRAC = 0.5  # scalar only: prediction error over this x tolerance
PROBE_FRAC = 0.02  # rate limit, as a fraction of the dragged knob's range
HIST = 8  # pre-freeze history depth, for re-acquire on reversal

# Objective -> exactly how many optimize-marked knobs it needs. `swr` is absent
# on purpose: it is a minimisation, not a root, so there is nothing to hold.
TRACKER_OBJECTIVES = {"resonance": 1, "match_z0": 2}


def refusal(objective: str, n_free: int) -> str | None:
    """Why the mode cannot be entered, or None if it can.

    Never guesses. A count that does not match is a refusal with the count in
    it, because "it did nothing" is the failure mode this exists to avoid.
    """
    if objective not in TRACKER_OBJECTIVES:
        return (
            f"“{objective}” is not a target that can be held — it is a "
            "minimisation, not a root. Choose Resonance or Match Z₀."
        )
    want = TRACKER_OBJECTIVES[objective]
    if n_free != want:
        knob = "knob" if want == 1 else "knobs"
        return (
            f"Holding this target needs exactly {want} optimise-marked {knob}; "
            f"{n_free} {'is' if n_free == 1 else 'are'} marked."
        )
    return None


class Tracker:
    """Per-session continuation state. Never shared between sessions: it is a
    linearisation about one point, so sharing it would answer one user's drag
    with another's tangent."""

    def __init__(
        self,
        base_req: dict,
        free: list[dict],
        objective: str,
        *,
        solve_fn: Callable[[dict], dict],
        tol: float = TRACK_TOL,
    ):
        why = refusal(objective, len(free))
        if why:
            raise ValueError(why)
        self.base = dict(base_req)
        self.names = [f["name"] for f in free]
        self.box = [(float(f["min"]), float(f["max"])) for f in free]
        self.objective = objective
        self.solve_fn = solve_fn
        self.tol = float(tol)
        self.n = len(free)
        self.x = np.array(
            [
                min(max(float(base_req.get(nm, 0.5 * (lo + hi))), lo), hi)
                for nm, (lo, hi) in zip(self.names, self.box, strict=True)
            ]
        )
        self.lo = np.array([b[0] for b in self.box])
        self.hi = np.array([b[1] for b in self.box])
        self.h = np.maximum((self.hi - self.lo) * 0.002, 1e-12)
        self.J = None  # d(residual)/d(held knobs)
        # d(residual)/d(dragged knob). THIS is what the tangent needs, not a
        # finite difference of the held knob across ticks: on a tick where the
        # prediction does not move, that difference is identically zero and
        # yields a tangent of zero, which then predicts "never move" forever
        # and reads to the guard as a fold. The implicit function theorem wants
        #     dx/da = -J^-1 . dF/da
        # so the residual's drag partial is the thing to carry.
        self.dFda = None
        self.F = None  # residual at the committed point
        self.mode = "idle"
        self.last_good = None
        self.frozen = None
        self.hist: deque = deque(maxlen=HIST)
        self.drag_name = None
        self.drag_value = None
        self.last_da = 0.0
        self.probe_at = None
        self.drag_span = None
        self.freeze_dir = 0.0  # direction of travel when the guard fired
        self.n_solves = 0

    # -- solving -----------------------------------------------------------
    def _F(self, x, drag_value):
        req = dict(self.base)
        for nm, v in zip(self.names, x, strict=True):
            req[nm] = float(v)
        if self.drag_name is not None:
            req[self.drag_name] = float(drag_value)
        out = self.solve_fn(req)
        self.n_solves += 1
        if self.objective == "match_z0":
            v = _residual_vec(out)
            return None if v is None else np.asarray(v, dtype=float)
        zs = _feed_zs(out)
        return None if len(zs) != 1 else np.array([zs[0].imag])

    def _clip(self, x):
        return np.minimum(np.maximum(x, self.lo), self.hi)

    def _jac(self, x, F, drag_value):
        """Forward differences, flipped INWARD at a bound. A plain forward
        difference is degenerate on the boundary -- every perturbation clips
        back onto it and the Jacobian comes out identically zero."""
        J = np.zeros((self.n, self.n))
        for j in range(self.n):
            step = self.h[j] if x[j] + self.h[j] <= self.hi[j] else -self.h[j]
            if x[j] + step < self.lo[j]:
                step = self.h[j]
            xp = x.copy()
            xp[j] = min(max(xp[j] + step, self.lo[j]), self.hi[j])
            d = xp[j] - x[j]
            Fp = self._F(xp, drag_value)
            if Fp is None:
                return None
            J[:, j] = (Fp - F) / (d if d else self.h[j])
        return J

    # -- public ------------------------------------------------------------
    def start(
        self, drag_name: str, drag_value: float, drag_span: float | None = None
    ) -> dict:
        """Enter the mode: a fresh root find from the current point (rule 4).

        `drag_span` is the dragged knob's full range. It is what the demote
        stage's rate limit is measured against -- a fraction of the knob's
        TRAVEL, never a tick count, because every per-tick quantity in the
        #1202 study failed to survive a change of drag resolution. Without it
        the demote stage stays OFF: it is worth 1-2 ticks of early warning
        against the risk of firing tens of ticks early when mis-scaled, and the
        holdability latch (which needs no calibration) is what actually catches
        the failure.
        """
        self.drag_name = drag_name
        self.drag_value = float(drag_value)
        self.drag_span = float(drag_span) if drag_span else None
        self.n_solves = 0
        budget = 40

        def probe1(v):
            F = self._F(np.array([v]), self.drag_value)
            return None if F is None else float(F[0])

        def probe2(x):
            return self._F(np.asarray(x, float), self.drag_value)

        if self.n == 1:
            xr, ok, why = _secant_root(
                probe1, float(self.x[0]), self.lo[0], self.hi[0], budget
            )
            x = np.array([xr])
        else:
            xr, ok, why = _newton_root2(probe2, list(self.x), self.box, budget)
            x = np.asarray(xr, float)
        F = self._F(x, self.drag_value)
        if F is None:
            return self._state(
                "refused",
                "This design's response has several "
                "feed points, so there is no single target to hold.",
            )
        res = float(np.linalg.norm(F))
        self.x = self._clip(x)
        self.J = self._jac(self.x, F, self.drag_value)
        self.F = F
        self.dFda = None  # no tangent yet: the guard is unarmed
        self.hist.clear()
        if res <= self.tol:
            self.last_good = self.x.copy()
            self.hist.appendleft(self.x.copy())
            self.mode = "tracking"
        else:
            self.mode = "latched"
            self.frozen = self.x.copy()
        self.probe_at = self.drag_value
        return self._state(self.mode, None, residual=res)

    def tick(self, drag_value: float) -> dict:
        """One drag event. Mutates nothing until every solve has returned, so a
        preempted solve leaves the tracker exactly as it was."""
        a = float(drag_value)
        da = a - (self.drag_value if self.drag_value is not None else a)
        # "Reversing" is a STATE, not a single tick. The sign flips once, but
        # the residual at the frozen knobs is still out of tolerance then --
        # we only just latched because the target was unreachable. So the
        # re-acquire has to stay armed for the whole way back, not get one
        # chance on the tick the direction changed.
        if da != 0.0 and self.freeze_dir:
            reversed_ = (da * self.freeze_dir) < 0
        else:
            reversed_ = False

        if self.mode in ("frozen", "latched"):
            return self._tick_held(a, da, reversed_)

        # --- predict (free), then the tick's display solve -----------------
        x_pred = self.x.copy()
        if self.dFda is not None and self.J is not None and da:
            try:
                step = np.linalg.solve(self.J, -self.dFda * da)
                x_pred = self._clip(self.x + step)
            except np.linalg.LinAlgError:
                pass
        F = self._F(x_pred, a)
        if F is None:
            return self._state(
                "refused",
                "This design's response has several "
                "feed points, so there is no single target to hold.",
            )
        pred_err = float(np.linalg.norm(F))
        xx, ff = x_pred, F
        corr = 0
        J = self.J
        while np.linalg.norm(ff) > self.tol and corr < MAX_CORR:
            if J is None:
                J = self._jac(xx, ff, a)
                if J is None:
                    break
            try:
                s = (
                    np.linalg.solve(J, -ff)
                    if self.n > 1
                    else np.array([-ff[0] / J[0, 0]])
                )
            except (np.linalg.LinAlgError, ZeroDivisionError):
                break
            xn = self._clip(xx + s)
            if np.linalg.norm(xn - xx) < 1e-12:
                break
            fn = self._F(xn, a)
            if fn is None:
                break
            corr += 1
            dx, dF = xn - xx, fn - ff
            if dx @ dx > 0:
                J = J + np.outer(dF - J @ dx, dx) / (dx @ dx)
            xx, ff = xn, fn
        res = float(np.linalg.norm(ff))

        # --- the guard, in order ------------------------------------------
        armed = self.dFda is not None
        # Rate-limited by DRAG DISTANCE, never ticks, and only when the knob's
        # range is known well enough to measure a distance against.
        probe_due = self.drag_span is not None and (
            self.probe_at is None
            or abs(a - self.probe_at) >= PROBE_FRAC * self.drag_span
        )
        if (
            armed
            and self.n == 1  # SCALAR ONLY
            and pred_err > DEMOTE_FRAC * self.tol
            and probe_due
        ):
            # Demote: stop stepping, keep displaying. Not a declaration that
            # the branch is dead -- the latch does that.
            self.frozen = (self.last_good if self.last_good is not None else xx).copy()
            self.mode = "frozen"
            self.freeze_dir = float(np.sign(da)) or self.freeze_dir
            self.drag_value, self.last_da, self.probe_at = a, da, a
            return self._state("frozen", None, residual=res)
        if res > self.tol:
            self.frozen = (self.last_good if self.last_good is not None else xx).copy()
            self.mode = "latched"
            self.freeze_dir = float(np.sign(da)) or self.freeze_dir
            self.drag_value, self.last_da = a, da
            return self._state("latched", self._lost(), residual=res)

        # --- commit (everything below this line only runs on a full tick) --
        if da and self.F is not None and J is not None:
            # dF/da from what this tick already paid for: the residual moved by
            # the drag AND by whatever the corrector did, so subtract the part
            # the Jacobian explains.
            self.dFda = (ff - self.F - J @ (xx - self.x)) / da
        self.J = J
        self.F = ff
        self.x = xx
        self.last_good = xx.copy()
        self.hist.appendleft(xx.copy())
        self.drag_value, self.last_da = a, da
        return self._state(
            "tracking", None, residual=res, corr=corr, pred_ok=pred_err <= self.tol
        )

    def _tick_held(self, a, da, reversed_):
        """Frozen or latched: the display solve at the frozen knobs is free, and
        on a drag REVERSAL it is what re-acquires."""
        F = self._F(self.frozen, a)
        if F is None:
            return self._state(self.mode, None)
        res = float(np.linalg.norm(F))
        if self.mode == "frozen" and res > self.tol:
            self.mode = "latched"
            self.drag_value, self.last_da = a, da
            return self._state("latched", self._lost(), residual=res)
        if reversed_ and res <= self.tol and self.hist:
            # Re-acquire PROMPTLY, seeded from pre-freeze history. Promptness is
            # what keeps the branch identity right: the roots have only just
            # reappeared and are still nearly coincident, so the old seed picks
            # the branch the user was on. Seeding from the frozen point instead,
            # further out where the branches have separated, silently switches.
            seed = np.asarray(self.hist[-1], float)
            if self.n == 1:

                def p1(v):
                    G = self._F(np.array([v]), a)
                    return None if G is None else float(G[0])

                xr, ok, _ = _secant_root(p1, float(seed[0]), self.lo[0], self.hi[0], 20)
                cand = np.array([xr])
            else:

                def p2(x):
                    return self._F(np.asarray(x, float), a)

                xr, ok, _ = _newton_root2(p2, list(seed), self.box, 20)
                cand = np.asarray(xr, float)
            G = self._F(cand, a)
            if G is not None and float(np.linalg.norm(G)) <= self.tol:
                self.x = self._clip(cand)
                self.J = self._jac(self.x, G, a)
                self.F = G
                self.dFda = None  # tangent is stale; re-arm
                self.last_good = self.x.copy()
                self.mode = "tracking"
                self.frozen = None
                self.freeze_dir = 0.0
                self.drag_value, self.last_da, self.probe_at = a, da, a
                return self._state("tracking", None, residual=float(np.linalg.norm(G)))
        self.drag_value, self.last_da = a, da
        return self._state(
            self.mode, self._lost() if self.mode == "latched" else None, residual=res
        )

    def _lost(self) -> str:
        what = "resonance" if self.objective == "resonance" else "match"
        return f"the {what} you are holding disappears here"

    def _state(self, status, message, *, residual=None, corr=0, pred_ok=None) -> dict:
        vals = self.frozen if self.mode in ("frozen", "latched") else self.x
        return {
            "status": status,
            "message": message,
            "params": {nm: float(v) for nm, v in zip(self.names, vals, strict=True)},
            "residual": residual,
            "n_solves": self.n_solves,
            "correctors": corr,
            "predicted_ok": pred_ok,
        }
