// NEC-4.2's Sommerfeld ground card as a per-slot choice: GN 2 (stock) or GN 3.
//
// The choice is an ordinary served knob (`sommerfeld`, exposed by the nec42
// roster row alone), so what is pinned here is the three places it can go
// missing: the gear menu (shown on that slot only), the request (the slot's
// options ride `model_options`, which only momwire slots sent before), and the
// slot's chip, so a pin or a legend names the ground that produced its number.
import { describe, it, expect, afterEach, onTestFinished, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BackendConfigModal } from "../components/backend/BackendConfigModal";
import {
  backendDisplayLabel,
  defaultOptsFor,
  modelOptionsForRequest,
  type BackendOpts,
} from "../lib/backends";
import {
  ROSTER_WITH_NEC42,
  ROSTER_WITH_NEC5,
  SERVED_ROSTER,
  SERVED_VOCAB,
  entry,
} from "./backendFixtures";
import { mountReady } from "./designSessionHarness";
import { SERVED_OPTION_SPECS } from "./optionSpecFixtures";

const HINT =
  "GN 3 is NEC-4.2's newer Sommerfeld evaluation; it can differ from GN 2 by around an ohm on buried designs.";

const nec42 = entry("nec42", ROSTER_WITH_NEC42);

function gn3Opts(): BackendOpts {
  const base = defaultOptsFor(nec42, SERVED_OPTION_SPECS);
  return { ...base, model: { ...base.model, sommerfeld: "GN 3" } };
}

describe("the option and its label", () => {
  it("defaults to GN 2, which the request carries and the chip leaves unsaid", () => {
    const opts = defaultOptsFor(nec42, SERVED_OPTION_SPECS);
    expect(opts.model).toEqual({ sommerfeld: "GN 2" });
    expect(modelOptionsForRequest(nec42, opts, SERVED_OPTION_SPECS)).toEqual({
      sommerfeld: "GN 2",
    });
    expect(backendDisplayLabel(nec42, opts)).toBe("NEC-4.2");
  });

  it("names GN 3 on the chip and sends it", () => {
    expect(backendDisplayLabel(nec42, gn3Opts())).toBe("NEC-4.2 (GN 3)");
    expect(modelOptionsForRequest(nec42, gn3Opts(), SERVED_OPTION_SPECS)).toEqual({
      sommerfeld: "GN 3",
    });
  });

  it("no other backend sends or labels it", () => {
    for (const b of ROSTER_WITH_NEC5) {
      if (b.kind === "nec42") continue;
      const opts = defaultOptsFor(b, SERVED_OPTION_SPECS);
      // A stray value in the map must not leak into a backend that does not
      // list the kwarg.
      const stray = { ...opts, model: { ...opts.model, sommerfeld: "GN 3" } };
      expect(modelOptionsForRequest(b, stray, SERVED_OPTION_SPECS)).not.toHaveProperty(
        "sommerfeld",
      );
      expect(backendDisplayLabel(b, stray)).not.toContain("GN 3");
    }
  });

  it("leaves NEC-2 and NEC-5 requests empty, as before", () => {
    for (const name of ["nec5", "pynec"]) {
      const b = entry(name, ROSTER_WITH_NEC5);
      expect(
        modelOptionsForRequest(b, defaultOptsFor(b, SERVED_OPTION_SPECS), SERVED_OPTION_SPECS),
      ).toEqual({});
    }
  });
});

describe("the gear menu", () => {
  function renderModal(backendName: string, opts?: BackendOpts) {
    const backend = entry(backendName, ROSTER_WITH_NEC42);
    const onPatch = vi.fn();
    render(
      <BackendConfigModal
        slot="A"
        backend={backend}
        backends={ROSTER_WITH_NEC42}
        requiredBackends={null}
        design={{}}
        restrictionReason={null}
        specs={SERVED_OPTION_SPECS}
        vocab={SERVED_VOCAB}
        designRefusalNote={null}
        suggestConvergedFeed={false}
        opts={opts ?? defaultOptsFor(backend, SERVED_OPTION_SPECS)}
        onChangeBackend={vi.fn()}
        onPatch={onPatch}
        onReset={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    return { onPatch, user: userEvent.setup() };
  }

  it("shows the choice and its hint on the NEC-4.2 slot", () => {
    renderModal("nec42");
    const select = screen.getByRole("combobox", { name: /Sommerfeld ground/ });
    expect(select).toHaveProperty("value", "GN 2");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "GN 2",
      "GN 3",
    ]);
    expect(screen.getByText(HINT)).toBeTruthy();
    // ...and the placeholder that says there is nothing to set is gone.
    expect(screen.queryByText(/has no extra solver knobs/)).toBeNull();
  });

  it("patches the slot's options when GN 3 is picked", async () => {
    const { onPatch, user } = renderModal("nec42");
    await user.selectOptions(screen.getByRole("combobox", { name: /Sommerfeld ground/ }), "GN 3");
    expect(onPatch).toHaveBeenCalledWith({ model: { sommerfeld: "GN 3" } });
  });

  it.each(SERVED_ROSTER.map((b) => b.name))("does not show it on %s", (name) => {
    renderModal(name);
    expect(screen.queryByRole("combobox", { name: /Sommerfeld ground/ })).toBeNull();
    expect(screen.queryByText(HINT)).toBeNull();
  });
});

// The wire, through a real session: the /geometry preview POST is
// buildRequest() verbatim (extendedKernel.session.test.tsx uses the same seam).
describe("the request, through a session", () => {
  let posts: Record<string, unknown>[] = [];
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function mountWithNec42() {
    posts = [];
    const user = userEvent.setup();
    await mountReady({
      roster: ROSTER_WITH_NEC42,
      routes: {
        "/geometry": (_url: string, init?: RequestInit) => {
          posts.push(JSON.parse(String(init?.body ?? "{}")));
          return {
            ok: true,
            status: 200,
            json: async () => ({ wires: [] }),
            text: async () => "{}",
          } as unknown as Response;
        },
      },
    });
    await user.click(screen.getByRole("button", { name: "Live" }));
    return user;
  }

  it("carries GN 3 with the NEC-4.2 slot's options and names it on the chip", async () => {
    const user = await mountWithNec42();
    // The stock slot is momwire: it sends momwire options, never the card.
    expect(posts.at(-1)?.model_options).not.toHaveProperty("sommerfeld");

    await user.click(screen.getByRole("button", { name: "Slot A options" }));
    await user.click(screen.getByRole("tab", { name: "NEC-4.2" }));
    expect(posts.at(-1)?.solver).toBe("nec42");
    expect(posts.at(-1)?.momwire_model).toBeUndefined();
    expect(posts.at(-1)?.model_options).toEqual({ sommerfeld: "GN 2" });

    await user.selectOptions(screen.getByRole("combobox", { name: /Sommerfeld ground/ }), "GN 3");
    expect(posts.at(-1)?.model_options).toEqual({ sommerfeld: "GN 3" });
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByRole("tab", { name: /Solver slot A: NEC-4\.2 \(GN 3\)/ })).toBeTruthy();
  });
});

// The Download NEC-4 deck is the NEC-4.2 slot's, wherever the active slot is.
describe("the NEC-4 download", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("carries the NEC-4.2 slot's choice even when a momwire slot is active", async () => {
    const bodies: Record<string, unknown>[] = [];
    const urls = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };
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
    const user = userEvent.setup();
    await mountReady({
      roster: ROSTER_WITH_NEC42,
      routes: {
        "/export_nec": (_url, init) => {
          bodies.push(JSON.parse(String(init?.body)));
          return new Response("EN\n", {
            status: 200,
            headers: { "Content-Disposition": 'attachment; filename="d.nec4.nec"' },
          });
        },
      },
    });
    // Slot B becomes NEC-4.2 on GN 3; slot A, a momwire slot, is active again.
    await user.click(screen.getByRole("tab", { name: /Solver slot B/ }));
    await user.click(screen.getByRole("button", { name: "Slot B options" }));
    await user.click(screen.getByRole("tab", { name: "NEC-4.2" }));
    await user.selectOptions(screen.getByRole("combobox", { name: /Sommerfeld ground/ }), "GN 3");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("tab", { name: /Solver slot A/ }));

    fireEvent.click(screen.getByRole("button", { name: "Tools menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Download NEC-4 .nec" }));
    await waitFor(() => expect(saved).toEqual(["d.nec4.nec"]));
    expect(bodies[0]?.dialect).toBe("nec4");
    expect(bodies[0]?.model_options).toMatchObject({ sommerfeld: "GN 3" });

    // ...and the NEC-2 and NEC-5 downloads are not touched by it.
    fireEvent.click(screen.getByRole("button", { name: "Tools menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Download NEC-2 .nec" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]?.model_options).not.toHaveProperty("sommerfeld");
  });
});
