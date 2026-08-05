import { type MobileScreen, type View } from "../../lib/view";
import { ViewSheet } from "./ViewPicker";

// The mobile carousel's page indicator: one dot per screen — the user's pinned
// views in pin order plus the trailing Info page (#700 unit 4) — followed by
// the "⋯" overflow affordance that opens the roster as a bottom sheet.
//
// Its own component (rather than inline in DesignSession's mobile branch) so
// the dot-count ↔ page-count contract is testable without mounting a whole
// session: an extra or missing dot is precisely how a bad index mapping shows
// itself. `screens` comes from the caller because the carousel tree renders
// the very same list — one derivation, two consumers, no way to disagree.
export function MobileDots({
  screens,
  index,
  goToScreen,
  view,
  pinned,
  newIds,
  togglePin,
  movePin,
  markRosterSeen,
}: {
  screens: MobileScreen[];
  index: number;
  goToScreen: (i: number) => void;
  view: View;
  pinned: View[];
  newIds: Set<View>;
  togglePin: (v: View) => void;
  movePin: (id: View, direction: -1 | 1) => void;
  markRosterSeen: () => void;
}) {
  return (
    <div className="mobile-dots" aria-label="Output screens">
      {screens.map((s, i) => (
        <button
          key={s.id}
          type="button"
          className={i === index ? "active" : ""}
          aria-label={`Show ${s.label}`}
          title={s.label}
          onClick={() => goToScreen(i)}
        />
      ))}
      {/* Not a dot: it addresses no page, it changes WHICH pages exist. It
          rides this row anyway because the dots are the page set. */}
      <ViewSheet
        view={view}
        pinned={pinned}
        newIds={newIds}
        togglePin={togglePin}
        movePin={movePin}
        markRosterSeen={markRosterSeen}
      />
    </div>
  );
}
