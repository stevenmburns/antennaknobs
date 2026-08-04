import { useRef, useState } from "react";
import { VIEWS, type View } from "../../lib/view";
import { PIN_CAP, pinBlockedReason } from "./useViewPrefs";

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
  markRosterSeen,
}: {
  view: View;
  setView: (v: View) => void;
  pinned: View[];
  newIds: Set<View>;
  togglePin: (v: View) => void;
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
            {VIEWS.map((v) => {
              const isPinned = pinned.includes(v.id);
              const blocked = pinBlockedReason(pinned, v.id);
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
                    onClick={() => {
                      setView(v.id);
                      setOpen(false);
                    }}
                  >
                    <span>{v.label}</span>
                    {badged.has(v.id) && (
                      <span className="view-picker-new">NEW</span>
                    )}
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
                    aria-label={
                      isPinned ? `Unpin ${v.label}` : `Pin ${v.label}`
                    }
                    onClick={() => togglePin(v.id)}
                  >
                    <span />
                  </button>
                </div>
              );
            })}
            <div className="view-picker-note">
              Row = show · dot = keep in rail · max {PIN_CAP} pinned
            </div>
          </div>
        </>
      )}
    </div>
  );
}
