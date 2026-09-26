// AK#1517: /capabilities' `version_label` renders under the brand. Mounted
// through the real <DesignSession> (designSessionHarness.tsx) rather than
// SessionGearMenu in isolation, since the interesting fact is the served
// string reaching the DOM through useCapabilities -> DesignSessionBody ->
// SessionGearMenu unchanged.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { mountReady } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the served version label", () => {
  it("renders under the brand when the server sends one", async () => {
    await mountReady({ versionLabel: "v0.77.0 · momwire v0.55.0" });
    expect(screen.getByText("v0.77.0 · momwire v0.55.0")).not.toBeNull();
  });

  it("renders no label, and does not crash, for a server predating it", async () => {
    // The session loading its design at all proves it mounted past the
    // capabilities gate rather than erroring on the missing field.
    const { container } = await mountReady();
    expect(container.querySelector(".brand")).not.toBeNull();
    expect(container.querySelector(".version-label")).toBeNull();
  });
});
