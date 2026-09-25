// AK#1739: the header's Help link. Mounted through the real <DesignSession>
// so the pin is on the link reaching the header, not on SessionGearMenu in
// isolation. The URL itself is lib/help.ts's one decision; this test pins
// the contract around it (new tab, no opener, a label) and that the button
// takes its URL from there rather than carrying its own.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mountDesignSession } from "./designSessionHarness";
import { DOCS_ORIGIN, helpUrl } from "../lib/help";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the header Help link", () => {
  it("opens the workbench guide on the docs site in a new tab, without an opener", async () => {
    mountDesignSession();
    const link = await waitFor(() =>
      screen.getByRole("link", { name: /^Help/ }),
    );
    expect(link.getAttribute("href")).toBe(helpUrl());
    expect(link.getAttribute("target")).toBe("_blank");
    const rel = (link.getAttribute("rel") ?? "").split(/\s+/);
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
    // It sits with the other header actions, beside the theme toggle.
    expect(link.closest(".header-actions")).not.toBeNull();
  });

  it("points at the workbench page on antennaknobs.dev", () => {
    // The page is site/src/content/docs/reference/web.md; the trailing slash
    // matters (the bare path is a 301).
    expect(helpUrl()).toBe(`${DOCS_ORIGIN}/reference/web/`);
    expect(DOCS_ORIGIN).toBe("https://antennaknobs.dev");
  });
});
