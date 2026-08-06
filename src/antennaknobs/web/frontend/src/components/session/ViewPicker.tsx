import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { VIEWS, type View } from "../../lib/view";
import { PIN_CAP, pinBlockedReason } from "./useViewPrefs";

// The roster listing both containers share: same rows, same pin dots, same
// NEW badges, whole registry in registry order. Only the NAME button's gesture
// differs between them, which is what `onRowClick`/`rowBlocked` parameterize.
//
// `rowBlocked` is undefined on desktop, where a row is always clickable (it
// shows a view, and showing can't be refused). Undefined props render as
// absent attributes, so the popover's DOM is byte-identical to what it was
// before the sheet existed — the picker tests pin that.
function ViewRosterRows({
  view,
  pinned,
  badged,
  onRowClick,
  togglePin,
  movePin,
  rowBlocked,
}: {
  view: View;
  pinned: View[];
  badged: Set<View>;
  onRowClick: (v: View) => void;
  togglePin: (v: View) => void;
  movePin: (id: View, direction: -1 | 1) => void;
  rowBlocked?: (v: View) => string | null;
}) {
  return (
    <>
      {VIEWS.map((v) => {
        const pinIndex = pinned.indexOf(v.id);
        const isPinned = pinIndex >= 0;
        const blocked = pinBlockedReason(pinned, v.id);
        const rowStop = rowBlocked ? rowBlocked(v.id) : null;
        return (
          <div
            key={v.id}
            className={`view-picker-row${isPinned ? " pinned" : " unpinned"}${
              v.id === view ? " active" : ""
            }`}
          >
            <button
              type="button"
              className="view-picker-name"
              role="menuitem"
              aria-current={v.id === view}
              disabled={rowBlocked ? rowStop !== null : undefined}
              title={rowBlocked ? (rowStop ?? undefined) : undefined}
              onClick={() => onRowClick(v.id)}
            >
              <span>{v.label}</span>
              {badged.has(v.id) && <span className="view-picker-new">NEW</span>}
            </button>
            <button
              type="button"
              className="view-picker-dot"
              aria-pressed={isPinned}
              disabled={blocked !== null}
              title={
                blocked ??
                (isPinned
                  ? `Unpin ${v.label} from the rail`
                  : `Pin ${v.label} to the rail`)
              }
              aria-label={isPinned ? `Unpin ${v.label}` : `Pin ${v.label}`}
              onClick={() => togglePin(v.id)}
            >
              <span />
            </button>
            {/* Issue #714: reorder buttons. Unpinned rows get none — there is
                no rail/grid/carousel position to move, and pinning already
                has its own "where it lands" rule (the end). stopPropagation
                is defensive: this row has no click handler of its own today,
                but the buttons sit between two that do, and a future row
                gesture must not inherit a click meant for one of these. */}
            {isPinned && (
              <div className="view-picker-move">
                <button
                  type="button"
                  className="view-picker-move-btn"
                  disabled={pinIndex === 0}
                  aria-label={`Move ${v.label} earlier`}
                  title={`Move ${v.label} earlier`}
                  onClick={(e) => {
                    e.stopPropagation();
                    movePin(v.id, -1);
                  }}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="view-picker-move-btn"
                  disabled={pinIndex === pinned.length - 1}
                  aria-label={`Move ${v.label} later`}
                  title={`Move ${v.label} later`}
                  onClick={(e) => {
                    e.stopPropagation();
                    movePin(v.id, 1);
                  }}
                >
                  ▼
                </button>
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

// The overflow affordance: a fixed-height "All views ⌄ +N" button at the foot
// of the thumbstrip opening a popover over the WHOLE roster in registry order
// (unit 2 of docs/plan-view-rail-scaling.md). Two gestures per row, on purpose:
//
//   row click  → show that view (a peek if it is unpinned — no pin spent) and
//                close, because you asked to look at something.
//   dot click  → pin/unpin only. It neither switches the view nor closes: the
//                point of curating is doing several in a row.
//
// Popover mechanics copy SessionGearMenu (transparent backdrop catches the
// outside click); the row idiom is the instrument-panel channel-enable row the
// plan's survey settled on — every view listed, each with a visible on/off pin.
export function ViewPicker({
  view,
  setView,
  pinned,
  newIds,
  togglePin,
  movePin,
  markRosterSeen,
}: {
  view: View;
  setView: (v: View) => void;
  pinned: View[];
  newIds: Set<View>;
  togglePin: (v: View) => void;
  movePin: (id: View, direction: -1 | 1) => void;
  markRosterSeen: () => void;
}) {
  const [open, setOpen] = useState(false);
  // The popover is position:FIXED and placed from a measurement, not
  // position:absolute inside the strip: .thumbstrip is overflow:hidden by
  // design (thumbs are scaled to fit and must never scroll), which would clip
  // an absolutely-positioned child. Fixed elements escape that clip. Measured
  // at open only — the stage layout doesn't scroll, and the backdrop swallows
  // everything until the popover closes.
  const wrapRef = useRef<HTMLDivElement>(null);
  const [anchor, setAnchor] = useState({ left: 0, bottom: 0 });
  // The badges shown while the popover is open are snapshotted as it opens.
  // Opening MARKS the roster seen — that is what "since you last looked"
  // means — so rendering `newIds` live would blank every badge in the same
  // frame the user opened the picker to read them.
  const [badged, setBadged] = useState<Set<View>>(new Set());

  const toggleOpen = () => {
    setOpen((was) => {
      if (!was) {
        const r = wrapRef.current?.getBoundingClientRect();
        // Opens to the RIGHT of its button and grows upward from the strip's
        // foot: the rail hugs the window's left edge, and the short columns
        // this whole feature exists for have no room below.
        if (r) setAnchor({ left: r.right + 6, bottom: window.innerHeight - r.bottom });
        setBadged(new Set(newIds));
        markRosterSeen();
      }
      return !was;
    });
  };

  const unpinnedCount = VIEWS.length - pinned.length;

  return (
    <div className="view-picker-wrap" ref={wrapRef}>
      <button
        type="button"
        className="view-picker-btn"
        onClick={toggleOpen}
        title="Every output view — pin the ones you want resident in the rail"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        All views ⌄
        {unpinnedCount > 0 && (
          <span className="view-picker-count">+{unpinnedCount}</span>
        )}
      </button>
      {open && (
        <>
          <div
            className="view-picker-backdrop"
            onClick={() => setOpen(false)}
          />
          <div
            className="view-picker"
            role="menu"
            style={{ left: anchor.left, bottom: anchor.bottom }}
          >
            <ViewRosterRows
              view={view}
              pinned={pinned}
              badged={badged}
              togglePin={togglePin}
              movePin={movePin}
              onRowClick={(v) => {
                setView(v);
                setOpen(false);
              }}
            />
            <div className="view-picker-note">
              Row = show · dot = keep in rail · max {PIN_CAP} pinned
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// The mobile half of the same affordance (#700 unit 4): a "⋯" button riding
// the dots row that opens the SAME roster as a bottom sheet. It renders its
// own trigger, exactly as ViewPicker does, so opening — and therefore marking
// the roster seen and snapshotting the NEW badges — has one implementation.
//
// The row gesture is the one real difference: here a row tap PINS/unpins,
// like the desktop pin dot, and there is NO peek. A peeked page would be a
// carousel page with no pin behind it, breaking the "pages = pinned + Info"
// mapping (and every index compare in useMobileCarousel) for one gesture's
// worth of convenience — the plan spells this out. So both row and dot toggle,
// and both are inert for the same reason at the cap and at the floor of one.
export function ViewSheet({
  view,
  pinned,
  newIds,
  togglePin,
  movePin,
  markRosterSeen,
}: {
  view: View;
  pinned: View[];
  newIds: Set<View>;
  togglePin: (v: View) => void;
  movePin: (id: View, direction: -1 | 1) => void;
  markRosterSeen: () => void;
}) {
  const [open, setOpen] = useState(false);
  // Snapshotted as the sheet opens, for the same reason as the popover's:
  // opening is what marks the roster seen, so live `newIds` would blank every
  // badge in the frame the user opened the sheet to read them.
  const [badged, setBadged] = useState<Set<View>>(new Set());

  const toggleOpen = () => {
    setOpen((was) => {
      if (!was) {
        setBadged(new Set(newIds));
        markRosterSeen();
      }
      return !was;
    });
  };

  return (
    <>
      <button
        type="button"
        className="mobile-dots-more"
        onClick={toggleOpen}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="All views"
        title="Every output view — tap one to add or remove its page"
      >
        ⋯
      </button>
      {open &&
        // PORTALED to <body>, not rendered in place: this component lives
        // inside .mobile-dots, whose translateX(-50%) centering makes it a
        // CONTAINING BLOCK for fixed-position descendants (any transformed
        // ancestor is — CSS transforms spec). Rendered in place, the sheet
        // and its backdrop were "fixed" relative to the dots strip: the
        // sheet clipped to a sliver and the tap-to-dismiss backdrop covered
        // almost nothing of the screen it was supposed to catch.
        createPortal(
          <>
            <div
              className="view-sheet-backdrop"
              onClick={() => setOpen(false)}
            />
            {/* No anchor measurement, unlike the popover: the sheet is pinned
                to the viewport's bottom edge, which is also the only place a
                phone can put a list this tall within thumb reach. */}
            <div className="view-sheet" role="menu" aria-label="All views">
              {/* An explicit close: the backdrop only exists ABOVE the sheet,
                  and a tall roster leaves little of it — dismissal must not
                  depend on how much screen the list happened to spare. */}
              <div className="view-sheet-head">
                <span className="view-sheet-title">Views</span>
                <button
                  type="button"
                  className="view-sheet-close"
                  aria-label="Close"
                  title="Close"
                  onClick={() => setOpen(false)}
                >
                  ✕
                </button>
              </div>
              <ViewRosterRows
                view={view}
                pinned={pinned}
                badged={badged}
                togglePin={togglePin}
                movePin={movePin}
                // Curating is a run of gestures — the sheet does NOT close on
                // a tap, so several pages can be added or dropped in one
                // visit.
                onRowClick={togglePin}
                rowBlocked={(id) => pinBlockedReason(pinned, id)}
              />
              <div className="view-picker-note">
                Tap a view to add or remove its page · max {PIN_CAP} pages
              </div>
            </div>
          </>,
          document.body,
        )}
    </>
  );
}
