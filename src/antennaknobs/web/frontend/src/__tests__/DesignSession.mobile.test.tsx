// The wiring MobileCarousel.test.tsx cannot see: that the REAL session's
// mobile tree derives its carousel pages and its dots from the same pinned
// list (#700 unit 4). One mount, three facts — page count, page identity, and
// the "⋯" affordance's presence — because everything about how those pages
// behave is already pinned at the hook and component level.
//
// Mounting itself (the fetch stub, view-prefs seeding, matchMedia flip to the
// phone breakpoint) now lives in designSessionHarness.tsx (#718) — this file
// supplied that recipe originally, so the only change here is calling it.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { VIEW_META, type View } from "../lib/view";
import { mountReady } from "./designSessionHarness";

const PINNED: View[] = ["zparam", "antenna", "files"];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the session's mobile tree", () => {
  it("carries one carousel page and one dot per pinned view, plus Info", async () => {
    const { container } = await mountReady({ mobile: true, pinned: PINNED });
    expect(container.querySelector(".mobile-carousel")).not.toBeNull();

    // Pages: the pinned views in pin order, then the Info screen — NOT the
    // registry, which is four views longer here.
    const pages = container.querySelectorAll(".mobile-screen");
    expect(pages).toHaveLength(PINNED.length + 1);
    expect(pages[pages.length - 1].classList).toContain("mobile-screen-info");

    // Dots: the same list, from the same derivation.
    expect(
      screen.getAllByRole("button", { name: /^Show / }).map((b) => b.getAttribute("title")),
    ).toEqual([...PINNED.map((id) => VIEW_META[id].label), "Info"]);

    // The roster the pages were drawn from is one tap away.
    expect(screen.getByRole("button", { name: "All views" })).toBeTruthy();
  });
});
