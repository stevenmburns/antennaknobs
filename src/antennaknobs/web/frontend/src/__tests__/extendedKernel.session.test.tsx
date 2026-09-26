// The extended thin-wire kernel, end to end through a real <DesignSession>
// (issue #849 unit 3). The unit pins live in backends.test.ts (the predicate),
// modelOptions.test.ts (the wire key) and BackendConfigModal.test.tsx (the
// row); what those cannot show is the thing the toggle exists for — TWO SLOTS,
// same basis, one with the kernel and one without, each sending its own
// request and each saying so on its own chip.
//
// The wire body is read off the /geometry preview POST, which is buildRequest()
// verbatim, the same seam newBackend.test.tsx uses.
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { mountReady } from "./designSessionHarness";

let geometryPosts: Record<string, unknown>[] = [];

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

/** model_options of the most recent request the session built. */
function lastModelOptions(): Record<string, unknown> {
  return (geometryPosts.at(-1)?.model_options ?? {}) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Mount the session through the harness, wait until its design has loaded
 *  (sessionReady, AK#1762: every slot click below is then past the
 *  design-load path), and park the live solve so every request refresh goes
 *  out over POST /geometry — synchronously, from the effect the click's act
 *  flushes, which is why every check below is a plain read. */
async function mountSession() {
  geometryPosts = [];
  const user = userEvent.setup();
  await mountReady({
    routes: {
      "/geometry": (_url: string, init?: RequestInit) => {
        geometryPosts.push(JSON.parse(String(init?.body ?? "{}")));
        return jsonResponse({ wires: [] });
      },
    },
  });
  await user.click(screen.getByRole("button", { name: "Live" }));
  return user;
}

async function toggleExtendedKernel(user: ReturnType<typeof userEvent.setup>, slot: string) {
  await user.click(screen.getByRole("button", { name: `Slot ${slot} options` }));
  await user.click(screen.getByRole("checkbox", { name: /extended kernel \(EK\)/ }));
  await user.click(screen.getByRole("button", { name: "Close" }));
}

describe("the extended-kernel toggle, slot by slot (#849)", () => {
  it("arms one slot's request and leaves the other's alone", async () => {
    const user = await mountSession();

    // Baseline: the stock A slot (B-spline d=2, N=15) sends no kernel key.
    expect(geometryPosts.length).toBeGreaterThan(0);
    expect(lastModelOptions()).not.toHaveProperty("extended_kernel");

    // Arm slot A.
    await toggleExtendedKernel(user, "A");
    expect(lastModelOptions()).toHaveProperty("extended_kernel", true);
    // The rest of the request is untouched: same basis, same mesh — which is
    // what makes the A/B difference readable as the kernel and nothing else.
    expect(geometryPosts.at(-1)?.momwire_model).toBe("bspline");
    expect(geometryPosts.at(-1)?.n_per_wire).toBe(15);
    expect(lastModelOptions().degree).toBe(2);

    // Slot B is a separate configuration and never saw the toggle.
    await user.click(screen.getByRole("tab", { name: /Solver slot B/ }));
        expect(geometryPosts.at(-1)?.n_per_wire).toBe(20); // B is d=1 @ N=20
    expect(lastModelOptions()).not.toHaveProperty("extended_kernel");

    // …and coming back to A restores it: the flag is per-slot state, not a
    // session-wide mode.
    await user.click(screen.getByRole("tab", { name: /Solver slot A/ }));
    expect(lastModelOptions()).toHaveProperty("extended_kernel", true);
  });

  it('says "+EK" on the armed slot\'s chip and nowhere else', async () => {
    const user = await mountSession();
    // Both b-spline slots start unaffixed.
    expect(screen.getByRole("tab", { name: /Solver slot A: B-spline d=2, N=15/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Solver slot B: B-spline d=1, N=20/ })).toBeTruthy();

    await toggleExtendedKernel(user, "A");

    expect(
      screen.getByRole("tab", { name: /Solver slot A: B-spline d=2 \+EK, N=15/ }),
    ).toBeTruthy();
    // B is untouched — the affix marks a slot, not the session.
    expect(screen.getByRole("tab", { name: /Solver slot B: B-spline d=1, N=20/ })).toBeTruthy();
  });

  it("drops the flag when the slot's backend changes under it", async () => {
    const user = await mountSession();
    await toggleExtendedKernel(user, "A");
    expect(lastModelOptions()).toHaveProperty("extended_kernel", true);

    // Swapping the backend resets that slot's model kwargs to the new
    // backend's defaults, the kernel among them — a new basis never inherits
    // an armed flag it wasn't configured with. (Sin-Galerkin serves EK since
    // momwire 0.27.0, so the box arrives live and unchecked rather than
    // greyed out.)
    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    await user.click(screen.getByRole("tab", { name: "Sin-Galerkin" }));
    const box = screen.getByRole("checkbox", { name: /extended kernel \(EK\)/ });
    expect(box).toHaveProperty("disabled", false);
    expect(box).toHaveProperty("checked", false);
    await user.click(screen.getByRole("button", { name: "Close" }));

        expect(geometryPosts.at(-1)?.momwire_model).toBe("sinusoidal-galerkin");
    expect(lastModelOptions()).not.toHaveProperty("extended_kernel");
  });
});
