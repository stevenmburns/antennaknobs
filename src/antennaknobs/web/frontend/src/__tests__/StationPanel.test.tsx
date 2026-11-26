// The Station view (src/components/results/StationPanel.tsx): one POST
// renders both rails, and switching between A and B is a display switch over
// that response, never another request (the antenna is solved once, server
// side, per request).
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SolveRequest } from "../lib/api";

const calls: { path: string; body: unknown }[] = [];

vi.mock("../lib/pin", () => ({
  apiFetch: vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as unknown) : null;
    calls.push({ path, body });
    const json = path.endsWith("/palette") ? PALETTE : renderFor(body as RenderBody);
    return new Response(JSON.stringify(json), { status: 200 });
  }),
}));

import { StationPanel } from "../components/results/StationPanel";

type RenderBody = { rails: ({ items: unknown[] } | null)[] };

const PALETTE = { palette: { coax: { label: "RG-8X 30.48 m", kind: "cable" } }, cables: [] };
const COAX = { version: 1, rig: "rig", items: [{ kind: "cable", cable: "RG-8X", length_m: 30.48 }] };

function rail(name: string, swr: number, chain: unknown) {
  return {
    chain,
    python: `# rail ${name}\nclass Builder(Antenna): ...`,
    changed: [],
    chips: [],
    nodes: ["rig", "feed"],
    advisories: [],
    z_re: 40 + swr,
    z_im: -3,
    swr,
    loss_db: 0.5,
    p_ant_w: 89,
    probes: [{ node: "rig", at: "rig", z_re: 40 + swr, z_im: -3, swr }],
    budget: [],
    tuner: [],
    tuner_advisories: [],
    svg: `<svg data-rail="${name}"></svg>`,
    svg_reason: null,
  };
}

function renderFor(body: RenderBody) {
  const rails = body.rails.map((c, i) =>
    i === 0 ? rail("A", 1.5, c ?? COAX) : rail("B", 2.5, c ?? COAX),
  );
  return {
    antenna: { design: "dipoles.example", module: "m", feed: "feed", form: "wire", balanced: null, replaced: 0, freq_mhz: 14.2, z_ref: 50 },
    starting_chain: COAX,
    rails,
    antenna_solves: 1,
    ms: 3,
  };
}

const station = {
  geometry: "dipoles.example",
  buildRequest: (): SolveRequest => ({ geometry: "dipoles.example", solver: "momwire" }) as SolveRequest,
};

beforeEach(() => {
  calls.length = 0;
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
}

describe("StationPanel", () => {
  it("draws a placeholder in a thumbnail and asks for nothing", () => {
    render(<StationPanel station={null} size={96} fill={false} />);
    expect(screen.getByText("Station rail")).not.toBeNull();
    expect(calls).toHaveLength(0);
  });

  it("renders both rails in one request and switches between them without another", async () => {
    render(<StationPanel station={station} size={600} fill={true} />);
    await settle();
    expect(screen.getByLabelText("Generated Python").textContent).toContain("# rail A");
    fireEvent.click(screen.getByText("+ B (a copy of A)"));
    await settle();
    const renders = calls.filter((c) => c.path === "/station/render");
    expect(renders).toHaveLength(2);
    expect((renders[1].body as RenderBody).rails).toHaveLength(2);
    expect(screen.getByLabelText("Rails compared")).not.toBeNull();
    expect(screen.getByLabelText("Generated Python").textContent).toContain("# rail B");

    const before = calls.length;
    fireEvent.click(screen.getByRole("tab", { name: "Rail A" }));
    await settle();
    expect(screen.getByLabelText("Generated Python").textContent).toContain("# rail A");
    fireEvent.click(screen.getByRole("tab", { name: "Rail B" }));
    await settle();
    expect(screen.getByLabelText("Generated Python").textContent).toContain("# rail B");
    expect(calls.length).toBe(before);
  });

  it("does not re-post the frozen chains the server answered with", async () => {
    render(<StationPanel station={station} size={600} fill={true} />);
    await settle();
    await settle();
    expect(calls.filter((c) => c.path === "/station/render")).toHaveLength(1);
  });
});
