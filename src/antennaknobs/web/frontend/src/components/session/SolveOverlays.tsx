import {
  BACKEND_LABEL,
  normalizeBackend,
  RESTRICTED_BACKEND_REASON,
  type Backend,
} from "../../lib/backends";

export function SolveOverlays({
  showBusy,
  solving,
  onCancelSolve,
  solverWarning,
  backendDisallowed,
  backend,
  requiredBackends,
  onSwitchBackend,
  onPause,
  recommendedBackend,
  onSolveAnyway,
  solveError,
}: {
  showBusy: boolean;
  solving: boolean;
  onCancelSolve: () => void;
  solverWarning: boolean;
  backendDisallowed: boolean;
  backend: Backend;
  requiredBackends: string[] | null;
  onSwitchBackend: (target: Backend) => void;
  onPause: () => void;
  recommendedBackend: Backend | null;
  onSolveAnyway: () => void;
  solveError: string | null;
}) {
  return (
    <>
        {/* Indeterminate progress bar: appears once a solve outlasts the dwell
            and lingers out its min-visible window (showBusy), so it never
            flashes — the dim/label (stale) clear earlier, when the result lands. */}
        <div className={`solve-bar${showBusy ? " active" : ""}`} aria-hidden />
        {showBusy && solving && (
          <button
            type="button"
            className="solve-cancel"
            onClick={onCancelSolve}
            title="Stop waiting for this solve (the server still finishes it)"
          >
            Cancel solve
          </button>
        )}
        {solverWarning && backendDisallowed && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver unavailable for this design"
          >
            <span className="solver-suggest-title">
              {BACKEND_LABEL[backend]} can't run this design
            </span>
            <span className="solver-suggest-sub">
              {RESTRICTED_BACKEND_REASON} Switch to{" "}
              {(requiredBackends ?? [])
                .map((r) => normalizeBackend(r))
                .filter((r): r is Backend => r !== null)
                .map((r) => BACKEND_LABEL[r])
                .join(" / ") || "a supported solver"}{" "}
              to solve it, or pause to keep editing.
            </span>
            <div className="solver-suggest-actions">
              {(() => {
                const target = normalizeBackend(requiredBackends?.[0]);
                return target ? (
                  <button
                    type="button"
                    className="solver-suggest-primary"
                    onClick={() => {
                      onSwitchBackend(target);
                    }}
                  >
                    Switch to {BACKEND_LABEL[target]}
                  </button>
                ) : null;
              })()}
              <button
                type="button"
                className="solver-suggest-secondary"
                onClick={onPause}
                title="Stop auto-solving so you can keep editing; click Live to resume."
              >
                Pause simulation
              </button>
            </div>
          </div>
        )}
        {solverWarning && !backendDisallowed && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver mismatch"
          >
            <span className="solver-suggest-title">
              {BACKEND_LABEL[backend]} is a poor match for this design
            </span>
            <span className="solver-suggest-sub">
              {recommendedBackend === "sinusoidal"
                ? "This mesh is benchmark-sized — B-spline-family solvers take minutes per solve here (and concurrent solves can exhaust memory). The sinusoidal solver or PyNEC answers in seconds. "
                : backend === "arrayblock" || backend === "hmatrix"
                  ? "This accelerator is overkill on a single-element design — a dense solver (e.g. B-spline) is faster here. "
                  : "This is a large array — a dense solver can be very slow. Array-block is far faster. "}
              Change the solver in the gear menu, solve anyway, or pause to keep
              editing.
            </span>
            <div className="solver-suggest-actions">
              <button
                type="button"
                className="solver-suggest-primary"
                onClick={onSolveAnyway}
              >
                Solve anyway
              </button>
              <button
                type="button"
                className="solver-suggest-secondary"
                onClick={onPause}
                title="Stop auto-solving so you can keep editing; click Live to resume."
              >
                Pause simulation
              </button>
            </div>
          </div>
        )}
        {solveError && (
          <div className="solve-error" role="alert">
            <span className="solve-error-title">This design failed to solve</span>
            <code className="solve-error-message">{solveError}</code>
            <span className="solve-error-hint">
              Fix the design and adjust a control to retry. For user designs see
              CLAUDE.md in your designs folder.
            </span>
          </div>
        )}
    </>
  );
}
