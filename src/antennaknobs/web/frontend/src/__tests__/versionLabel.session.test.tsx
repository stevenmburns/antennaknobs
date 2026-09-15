// AK#1517: /capabilities' `version_label` renders under the brand. Mounted
// through the real <DesignSession> (designSessionHarness.tsx) rather than
// SessionGearMenu in isolation, since the interesting fact is the served
// string reaching the DOM through useCapabilities -> DesignSessionBody ->
// SessionGearMenu unchanged.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { mountDesignSession } from "./designSessionHarness";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the served version label", () => {
  it("renders under the brand when the server sends one", async () => {
    mountDesignSession({ versionLabel: "v0.77.0 · momwire 0.55.0" });
    await waitFor(() =>
      expect(
        screen.getByText("v0.77.0 · momwire 0.55.0"),
      ).not.toBeNull(),
    );
  });

  it("renders no label, and does not crash, for a server predating it", async () => {
    const { container } = mountDesignSession();
    // The catalog resolving at all proves the session mounted past the
    // capabilities gate rather than erroring on the missing field.
    await waitFor(() =>
      expect(container.querySelector(".brand")).not.toBeNull(),
    );
    expect(container.querySelector(".version-label")).toBeNull();
  });
});
