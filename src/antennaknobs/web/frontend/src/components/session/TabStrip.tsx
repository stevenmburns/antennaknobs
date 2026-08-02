import { useContext, useEffect, useState } from "react";
import { SessionsContext } from "./contexts";

// The session tab strip, atop each session's sidebar. Global state comes from
// SessionsContext, so every mounted session renders an identical strip. Tabs
// are labelled "D1", "D2", … to stay compact for many designs; the full
// design/solver/segs/ground summary is on hover.
export function TabStrip() {
  const { sessions, activeId, add, close, setActive, summaries } =
    useContext(SessionsContext);
  // The session whose close (×) was clicked and is awaiting confirmation, plus
  // the viewport coords of that × so the popover can anchor to it. Closing a
  // session discards its unsaved knob state, so we guard it behind this popover
  // rather than closing on the first click. The popover is position:fixed (not
  // absolute) because .tab-strip is an overflow:auto scroll container that would
  // otherwise clip it against the top/left edge.
  const [confirm, setConfirm] = useState<
    { id: number; x: number; y: number } | null
  >(null);
  const confirmId = confirm?.id ?? null;

  // Dismiss the confirm popover on Escape or an outside click. Clicks on any
  // tab-close × are excluded so switching the popover to another tab (or
  // reopening it) doesn't fight this dismiss handler.
  useEffect(() => {
    if (confirmId === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setConfirm(null);
    };
    const onDoc = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (!t.closest(".tab-close-confirm") && !t.closest(".tab-close")) {
        setConfirm(null);
      }
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [confirmId]);

  return (
    <div className="tab-strip" role="tablist" aria-label="Design sessions">
      {sessions.map((s) => (
        <div
          key={s.id}
          className={`tab ${s.id === activeId ? "active" : ""}`}
        >
          <button
            type="button"
            role="tab"
            aria-selected={s.id === activeId}
            className="tab-btn"
            onClick={() => setActive(s.id)}
            title={summaries[s.id] ?? `Design ${s.id}`}
          >
            D{s.id}
          </button>
          {sessions.length > 1 && (
            <button
              type="button"
              className="tab-close"
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                setConfirm({ id: s.id, x: r.left, y: r.bottom });
              }}
              aria-label={`Close design ${s.id}`}
              title={`Close design ${s.id}`}
              aria-haspopup="dialog"
              aria-expanded={confirmId === s.id}
            >
              ×
            </button>
          )}
        </div>
      ))}
      <button
        type="button"
        className="tab-add"
        onClick={add}
        aria-label="New design"
        title="New design"
      >
        +
      </button>
      {confirm !== null &&
        sessions.some((s) => s.id === confirm.id) && (
          <div
            className="tab-close-confirm"
            role="dialog"
            aria-label={`Close design ${confirm.id}?`}
            style={{ left: confirm.x, top: confirm.y + 6 }}
          >
            <span className="tab-close-confirm-msg">
              Close design {confirm.id}?
            </span>
            <div className="tab-close-confirm-actions">
              <button
                type="button"
                className="tab-close-confirm-cancel"
                autoFocus
                onClick={() => setConfirm(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="tab-close-confirm-ok"
                onClick={() => {
                  close(confirm.id);
                  setConfirm(null);
                }}
              >
                Close
              </button>
            </div>
          </div>
        )}
    </div>
  );
}
