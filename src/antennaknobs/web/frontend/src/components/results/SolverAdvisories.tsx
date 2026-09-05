// Solver advisories from one solve (antennaknobs#1144).
//
// momwire raises `UserWarning` subclasses during a solve, composed from
// measured rows and carrying real numbers about THIS deck. Nothing caught
// them and the UI showed none of them, so #1143 shipped a static note as a
// stand-in that could only quote class figures, never the deck's own.
//
// THEY ARE ADVISORY, NOT ERRORS, and the rendering has to say so out loud.
// Nothing was refused and nothing was remeshed — a deck the solver declines
// raises instead and never produces a result at all. A user who reads a note
// about mesh convergence as a failure will go looking for a broken antenna.
// Hence the muted styling of `.design-note` rather than the alarm styling of
// `.examples-error`, and hence the explicit "Advisory" label.
//
// RANKING (measured, antennaknobs#1144):
//
//   RazorFarMeshClass    fires on EVERY razor-2p solve, by momwire's design —
//                        it measured that no solve-free predictor of the error
//                        correlates, so there is no honest threshold and the
//                        advisory is unconditional.
//   SurfaceRadialHeight  fires only on decks inside the sensitive band, and
//                        quotes that deck's own h and h/a.
//   CoarseCrossingNode   deck-conditional; not reachable from the shipped
//                        catalog decks measured, which grade their node mesh.
//
// So the unconditional one is collapsed to a count the user can expand, and
// everything else is shown in full and never count-suppressed. An advisory
// that appears every single time trains the eye to skip the whole channel,
// which would take the deck-specific ones down with it.
//
// UNKNOWN CATEGORIES ARE SHOWN IN FULL. The collapse list is a presentation
// choice about one known-unconditional advisory, not a filter on what counts
// as an advisory — that lives in the engine and keys on the module, with no
// list at all. A category momwire adds later therefore shows until someone
// decides otherwise: over-showing is visible and gets fixed, quiet
// suppression is neither.
import { useState } from "react";

/** Advisories that fire on every solve of their backend and so would drown
 *  the rest. Presentation only — see the header. */
const UNCONDITIONAL = new Set(["RazorFarMeshClass"]);

export type Advisory = { category: string; text: string };

export function SolverAdvisories({
  advisories,
  className,
}: {
  advisories?: Advisory[] | null | undefined;
  className?: string | undefined;
}) {
  const [showAll, setShowAll] = useState(false);
  const items = advisories ?? [];
  if (items.length === 0) return null;

  const shown = items.filter((a) => !UNCONDITIONAL.has(a.category));
  const collapsed = items.filter((a) => UNCONDITIONAL.has(a.category));

  return (
    <div className={`solver-advisories${className ? " " + className : ""}`}>
      {shown.map((a) => (
        <div className="solver-advisory" key={`${a.category}:${a.text}`}>
          <span className="solver-advisory-tag">Advisory</span> {a.text}
        </div>
      ))}
      {collapsed.length > 0 && (
        <div className="solver-advisory solver-advisory-collapsed">
          <button
            type="button"
            className="solver-advisory-toggle"
            aria-expanded={showAll}
            onClick={() => setShowAll((v) => !v)}
          >
            {showAll
              ? "Hide convergence advisory"
              : `${collapsed.length} convergence advisory${
                  collapsed.length === 1 ? "" : " notes"
                } for this backend`}
          </button>
          {showAll &&
            collapsed.map((a) => (
              <div className="solver-advisory-body" key={`${a.category}:${a.text}`}>
                {a.text}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
