// "Keep as study" on the pinned-pattern compare table (AK#1757 step 7 unit
// 4): the table's actions carry the button, disabled with why when the pins
// cannot be kept, and it opens the keep (DesignSession's patternPinsKeep,
// lib/keep.ts; its body is tested in keep.test.ts).
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import type { PinnedPattern } from "../components/charts/types";
import { CompareOverlay } from "../components/results/StageOverlays";
import type { SolveResponse } from "../lib/api";

const pin = (id: string): PinnedPattern => ({
  id,
  label: `pin ${id}`,
  result: {} as SolveResponse,
  metrics: null,
  enabled: true,
  colorIdx: 0,
  req: { geometry: "g" },
});

function overlay(props: { onKeepPins?: () => void; keepPinsBlocked?: string | null }) {
  return render(
    <CompareOverlay
      pinCurrentPattern={() => {}}
      setCompareCollapsed={() => {}}
      result={null}
      pinnedPatterns={[pin("a"), pin("b")]}
      compareCollapsed={false}
      clearPins={() => {}}
      liveMetrics={null}
      currentExample={undefined}
      geometry="g"
      measFreq={14.2}
      removePin={() => {}}
      togglePin={() => {}}
      cutLabel={null}
      {...props}
    />,
  );
}

const keepButton = () =>
  screen.getByRole("button", { name: "Keep the shown pinned patterns as a study" }) as HTMLButtonElement;

describe("keep pinned patterns as a study", () => {
  it("opens the keep from the table's actions", () => {
    const onKeepPins = vi.fn();
    overlay({ onKeepPins, keepPinsBlocked: null });
    expect(keepButton().disabled).toBe(false);
    fireEvent.click(keepButton());
    expect(onKeepPins).toHaveBeenCalledTimes(1);
  });

  it("is disabled with why when the pins cannot be kept, and absent without a keep", () => {
    const { unmount } = overlay({ onKeepPins: () => {}, keepPinsBlocked: "No shown pin to keep: show one" });
    expect(keepButton().disabled).toBe(true);
    expect(keepButton().title).toBe("No shown pin to keep: show one");
    unmount();
    overlay({});
    expect(screen.queryByRole("button", { name: "Keep the shown pinned patterns as a study" })).toBeNull();
  });
});
