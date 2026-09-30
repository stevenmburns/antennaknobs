// AK#1803: the Tools menu's "Download NEC-4 .nec" item, beside NEC-2 and
// NEC-5. Mounted through the real <DesignSession>, so the pin is on the click
// reaching /export_nec with dialect "nec4", not on the menu in isolation. The
// item is offered unconditionally: writing a NEC-4 deck needs no binary.
import { describe, it, expect, afterEach, onTestFinished, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { mountReady } from "./designSessionHarness";
import { NEC_FALLBACK_EXT } from "../components/session/sessionActions";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the NEC-4 download", () => {
  it("posts dialect nec4 and saves the server's .nec4.nec file", async () => {
    const bodies: Record<string, unknown>[] = [];
    // jsdom has no object URLs; the save itself is the anchor click below.
    const urls = {
      create: URL.createObjectURL,
      revoke: URL.revokeObjectURL,
    };
    URL.createObjectURL = () => "blob:deck";
    URL.revokeObjectURL = () => {};
    onTestFinished(() => {
      URL.createObjectURL = urls.create;
      URL.revokeObjectURL = urls.revoke;
    });
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    await mountReady({
      routes: {
        "/export_nec": (_url, init) => {
          bodies.push(JSON.parse(String(init?.body)));
          return new Response("EN\n", {
            status: 200,
            headers: {
              "Content-Disposition":
                'attachment; filename="harness_design.nec4.nec"',
            },
          });
        },
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tools menu" }));
    fireEvent.click(
      screen.getByRole("menuitem", { name: "Download NEC-4 .nec" }),
    );
    await waitFor(() => expect(saved).toEqual(["harness_design.nec4.nec"]));
    expect(bodies).toHaveLength(1);
    expect(bodies[0].dialect).toBe("nec4");
  });

  it("sits between the NEC-2 and NEC-5 items", async () => {
    await mountReady();
    fireEvent.click(screen.getByRole("button", { name: "Tools menu" }));
    const names = screen
      .getAllByRole("menuitem")
      .map((b) => b.textContent ?? "")
      .filter((t) => t.startsWith("Download NEC"));
    expect(names).toEqual([
      "Download NEC-2 .nec",
      "Download NEC-4 .nec",
      "Download NEC-5 .nec",
    ]);
  });

  it("falls back to distinct extensions for all three dialects", () => {
    expect(NEC_FALLBACK_EXT).toEqual({
      nec2: ".nec",
      nec4: ".nec4.nec",
      nec5: ".nec5.nec",
    });
  });
});
