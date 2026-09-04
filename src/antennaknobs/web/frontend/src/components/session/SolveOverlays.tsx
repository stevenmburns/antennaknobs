import {
  normalizeBackend,
  RESTRICTED_BACKEND_REASON,
  type BackendConstraint,
  type BackendEntry,
  type BackendRoster,
} from "../../lib/backends";

export function SolveOverlays({
  showBusy,
  solving,
  onCancelSolve,
  solverWarning,
  backendDisallowed,
  optionRefusal,
  backend,
  roster,
  requiredBackends,
  aliases,
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
  /** The design-dependent refusal for the current slot, or null (#1006 G2-5).
   *  Separate from `backendDisallowed`: that one says the SOLVER cannot run
   *  this design at all and the fix is a different solver; this one says the
   *  solver can, but not with the OPTION currently set — so the fix is the
   *  option, and offering a solver switch would be the wrong advice. */
  optionRefusal: BackendConstraint | null;
  backend: BackendEntry;
  /** The served roster (#628) — needed to resolve `requires_backends` names
   *  (which may include the retired "triangular") into offerable entries. */
  roster: BackendRoster;
  requiredBackends: string[] | null;
  /** Retired backend names, served (#1006 G2-6) — a design's
   *  `requires_backends` may still carry one. */
  aliases: Record<string, string>;
  onSwitchBackend: (target: BackendEntry) => void;
  onPause: () => void;
  recommendedBackend: BackendEntry | null;
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
        {solverWarning && !backendDisallowed && optionRefusal && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver option unavailable for this design"
          >
            <span className="solver-suggest-title">
              {backend.label} can't run this design with that option
            </span>
            {/* momwire's OWN sentence, carried through the roster payload and
                rendered verbatim. Not paraphrased here: the refusal prose is
                the thing that tells a user which of the two knobs to move,
                and a summary of it would go stale the moment momwire's did. */}
            <span className="solver-suggest-sub">
              {optionRefusal.reason}
              {optionRefusal.condition
                ? ` (applies here because the design has ${optionRefusal.condition}.)`
                : ""}{" "}
              ({optionRefusal.issue})
            </span>
            <div className="solver-suggest-actions">
              {/* No "Solve anyway": momwire raises on this combination, so an
                  override would buy an error dialog rather than a result. */}
              <button
                type="button"
                className="solver-suggest-secondary"
                onClick={onPause}
                title="Stop auto-solving so you can keep editing; click Live to resume."
              >
                Pause solving
              </button>
            </div>
          </div>
        )}
        {solverWarning && backendDisallowed && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver unavailable for this design"
          >
            <span className="solver-suggest-title">
              {backend.label} can't run this design
            </span>
            <span className="solver-suggest-sub">
              {RESTRICTED_BACKEND_REASON} Switch to{" "}
              {(requiredBackends ?? [])
                .map((r) => normalizeBackend(r, roster, aliases))
                .filter((r): r is BackendEntry => r !== null)
                .map((r) => r.label)
                .join(" / ") || "a supported solver"}{" "}
              to solve it, or pause to keep editing.
            </span>
            <div className="solver-suggest-actions">
              {(() => {
                const target = normalizeBackend(requiredBackends?.[0], roster, aliases);
                return target ? (
                  <button
                    type="button"
                    className="solver-suggest-primary"
                    onClick={() => {
                      onSwitchBackend(target);
                    }}
                  >
                    Switch to {target.label}
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
        {/* The SOFT mismatch: a performance mismatch the user may override.
            Excluded while a HARD refusal is showing — `backendDisallowed` (the
            solver cannot run this design) or `optionRefusal` (momwire refuses
            these options on this deck). Without the second exclusion both
            overlays rendered, soft on top, and its "Solve anyway" offered an
            override for a combination that RAISES. An override button is a
            promise that the solve can proceed. */}
        {solverWarning && !backendDisallowed && !optionRefusal && (
          <div
            className="solver-suggest"
            role="alertdialog"
            aria-label="Solver mismatch"
          >
            <span className="solver-suggest-title">
              {backend.label} is a poor match for this design
            </span>
            <span className="solver-suggest-sub">
              {/* Which mismatch this is, read off the roster's capability
                  flags rather than solver names (#628). */}
              {recommendedBackend && !recommendedBackend.accelerator
                ? "This mesh is benchmark-sized — B-spline-family solvers take minutes per solve here (and concurrent solves can exhaust memory). The sinusoidal solver or PyNEC answers in seconds. "
                : backend.accelerator
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
