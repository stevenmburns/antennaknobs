import { useSyncExternalStore } from "react";

// A chart header folded down to one icon (Steve's phone review, 2026-10-11):
// on a phone, and on a desktop at 175 %, the sweep controls wrap to several
// rows and take half the page above the chart. Folded, a header keeps its
// toggle, a one-line summary of what it sweeps, and Run / Stop (with the
// progress count), which is what a user glances at while the chart fills.
//
// ONE choice for every chart header (knob sweep, frequency sweep, pattern),
// so switching charts never unfolds a header the user folded. Until the user
// picks, it follows the window: folded below FOLD_MEDIA_QUERY's width. The
// pick is remembered in this browser (a per-viewer convenience, so
// localStorage, distrusted on read like every stored choice here).

export const FOLD_STORAGE_KEY = "antennaknobs.chartHeaderFolded";
/** Narrow enough that the header wraps: a phone, or 1920 px at 175 %. */
export const FOLD_MEDIA_QUERY = "(max-width: 1100px)";

const listeners = new Set<() => void>();
// This page's pick, once made; before it, the stored one or the width.
let memo: boolean | null = null;

function stored(): boolean | null {
  try {
    const raw = localStorage.getItem(FOLD_STORAGE_KEY);
    return raw === "1" ? true : raw === "0" ? false : null;
  } catch {
    return null;
  }
}

function byWidth(): boolean {
  try {
    return window.matchMedia(FOLD_MEDIA_QUERY).matches;
  } catch {
    return false;
  }
}

function snapshot(): boolean {
  return stored() ?? byWidth();
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  let mql: MediaQueryList | null = null;
  try {
    mql = window.matchMedia(FOLD_MEDIA_QUERY);
    mql.addEventListener("change", onChange);
  } catch {
    mql = null;
  }
  return () => {
    listeners.delete(onChange);
    mql?.removeEventListener("change", onChange);
  };
}

export function setHeaderFolded(folded: boolean) {
  // Held here as well as stored, so a refused write (a private window)
  // still lasts until the page reloads.
  memo = folded;
  try {
    localStorage.setItem(FOLD_STORAGE_KEY, folded ? "1" : "0");
  } catch {
    // the memo holds it
  }
  for (const l of listeners) l();
}

/** Whether chart headers are folded, and the setter they share. */
export function useHeaderFold(): [boolean, (folded: boolean) => void] {
  const folded = useSyncExternalStore(subscribe, () => memo ?? snapshot());
  return [folded, setHeaderFolded];
}

/** The fold's toggle: first in a header's row, folded or not. Folded, it
 *  carries the header's summary, so the chart still says what it shows. */
export function FoldToggle({
  folded,
  onFolded,
  summary,
}: {
  folded: boolean;
  onFolded: (folded: boolean) => void;
  /** What the folded header sweeps, in a few words. */
  summary: string;
}) {
  return (
    <button
      type="button"
      className={folded ? "chart-fold is-folded" : "chart-fold"}
      aria-expanded={!folded}
      aria-label={
        folded ? "Show the chart's controls" : "Fold the chart's controls"
      }
      title={
        folded
          ? `Show the controls (${summary})`
          : "Fold the controls to one line"
      }
      onClick={() => onFolded(!folded)}
    >
      <span className="chart-fold-icon" aria-hidden="true">
        {folded ? "⚙" : "▴"}
      </span>
      {folded && <span className="chart-fold-summary">{summary}</span>}
      {/* Folded, the summary alone read as a caption rather than a control
          (AC6LA, QRZ 1003328 #214, AK#2093): the cue says it opens. */}
      {folded && (
        <span className="chart-fold-cue" aria-hidden="true">
          ▾ controls
        </span>
      )}
    </button>
  );
}

/** Tests only: hold the fold at `folded`, or (null) forget this page's
 *  pick, so the stored one or the width decides again. */
export function resetHeaderFoldForTests(folded: boolean | null = null) {
  memo = folded;
}
