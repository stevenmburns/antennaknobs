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
//
// PLAIN WORDS FIRST (AK#1981). momwire writes its advisories for its own
// maintainers: issue numbers, solver internals, 0-based wire indices. Jeff
// G8HUL called one "totally incomprehensible", and the server now adds a
// `summary` for the categories it can read (`advisory_words.py`): what it is
// about in the deck's terms, roughly what it is worth, what to do. The
// summary leads and momwire's text sits behind "Details". An advisory with no
// summary (an unknown category, or a sentence the server could not read)
// shows its text in full, as before.
import { useState } from "react";

/** Advisories that fire on every solve of their backend and so would drown
 *  the rest. Presentation only — see the header. */
const UNCONDITIONAL = new Set(["RazorFarMeshClass"]);

export type Advisory = { category: string; text: string; summary?: string };

/** Above this many distinct advisories the list folds behind one
 *  "Advisories (N)" line (AK#2291). */
const GROUP_FOLD_ABOVE = 3;

function keyOf(a: Advisory): string {
  return `${a.category}\u0000${a.text}\u0000${a.summary ?? ""}`;
}

/** Each distinct advisory once, in first-seen order, with how many times the
 *  list carried it (AK#2291). THIS is the one place duplicates collapse: the
 *  server serves every advisory it raised, and every advisory list the app
 *  shows (a solve's, a sweep's, a map's) renders through this component. A
 *  count keeps every occurrence visible, so nothing is dropped, and React
 *  never sees two children under one key. */
function counted(items: readonly Advisory[]): { a: Advisory; n: number }[] {
  const byKey = new Map<string, { a: Advisory; n: number }>();
  for (const a of items) {
    const k = keyOf(a);
    const hit = byKey.get(k);
    if (hit) hit.n += 1;
    else byKey.set(k, { a, n: 1 });
  }
  return [...byKey.values()];
}

function Times({ n }: { n: number }) {
  return n > 1 ? <span className="solver-advisory-count">{` (×${n})`}</span> : null;
}

/** One advisory's words: the summary with momwire's text behind a toggle,
 *  or the text alone when there is no summary. */
function AdvisoryWords({ a }: { a: Advisory }) {
  const [open, setOpen] = useState(false);
  if (!a.summary) return <>{a.text}</>;
  return (
    <>
      {a.summary}{" "}
      <button
        type="button"
        className="solver-advisory-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide details" : "Details"}
      </button>
      {open && <div className="solver-advisory-body">{a.text}</div>}
    </>
  );
}

export function SolverAdvisories({
  advisories,
  className,
}: {
  advisories?: Advisory[] | null | undefined;
  className?: string | undefined;
}) {
  const [showAll, setShowAll] = useState(false);
  const [groupOpen, setGroupOpen] = useState<boolean | null>(null);
  const items = counted(advisories ?? []);
  if (items.length === 0) return null;

  const shown = items.filter(({ a }) => !UNCONDITIONAL.has(a.category));
  const collapsed = items.filter(({ a }) => UNCONDITIONAL.has(a.category));
  // A long list folds behind one header line (AK#2291); a short one shows
  // as it always has, with no header to learn to skip.
  const folds = items.length > GROUP_FOLD_ABOVE;
  const open = !folds || (groupOpen ?? false);

  return (
    <div className={`solver-advisories${className ? " " + className : ""}`}>
      {folds && (
        <button
          type="button"
          className="solver-advisory-toggle solver-advisories-header"
          aria-expanded={open}
          onClick={() => setGroupOpen(!open)}
        >
          {`Advisories (${items.length})`}
        </button>
      )}
      {open && shown.map(({ a, n }) => (
        <div className="solver-advisory" key={keyOf(a)}>
          <span className="solver-advisory-tag">Advisory</span> <AdvisoryWords a={a} />
          <Times n={n} />
        </div>
      ))}
      {open && collapsed.length > 0 && (
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
            collapsed.map(({ a, n }) => (
              <div className="solver-advisory-body" key={keyOf(a)}>
                <AdvisoryWords a={a} />
                <Times n={n} />
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
