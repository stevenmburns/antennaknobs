// The Smith chart's target circle and admittance grid reach the chart
// through the real session, not only through a fixture that hands the chart
// its props: the solve reply's `smith_target` lands on the stage chart (and
// a reply without one draws none), and the stage chart's Y button turns the
// admittance grid on, persists it with the view prefs, and the thumbnail
// draws it too without offering a button.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { invveeShape } from "./fixtures/solveShapes";
import { mountReady, untilDom } from "./designSessionHarness";
import { VIEW_PREFS_KEY } from "../components/session/useViewPrefs";

vi.setConfig({ testTimeout: 30_000 });

let extra: Record<string, unknown> = {};

class EchoWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = EchoWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Record<string, unknown>;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    const reply = {
      ...invveeShape,
      feeds: undefined,
      geometry: req.geometry,
      _seq: req._seq,
      z0_ohms: 50,
      ...extra,
    };
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(reply) } as MessageEvent), 0);
  }
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", EchoWebSocket);
});
afterEach(() => {
  vi.unstubAllGlobals();
  extra = {};
});

const stageSmith = () => document.querySelector<HTMLElement>(".grid-cell canvas.smith");

describe("Smith chart target and admittance grid through the session", () => {
  it("draws the solve's smith_target on the stage chart", async () => {
    extra = { plane: "lc", planes: ["rig", "lc", "tuner"], smith_target: "g" };
    await mountReady({ layout: "grid", pinned: ["smith", "antenna"] });
    const chart = await untilDom(() => (stageSmith()?.dataset.target === "g" ? stageSmith() : null));
    expect(chart).toBeTruthy();
  });

  it("draws no target when the solve declares none", async () => {
    extra = { plane: "rig", planes: ["rig", "lc", "tuner"] };
    await mountReady({ layout: "grid", pinned: ["smith", "antenna"] });
    // The reply has landed once the readout offers its planes.
    await untilDom(() => document.querySelector('option[value="lc"]'));
    expect(stageSmith()!.dataset.target).toBe("");
  });

  it("turns the admittance grid on from the stage chart and keeps it", async () => {
    await mountReady({ layout: "grid", pinned: ["smith", "antenna"] });
    const stage = () => stageSmith()!;
    expect(stage().dataset.ygrid).toBe("0");
    fireEvent.click(screen.getByRole("button", { name: "Admittance grid" }));
    expect(stage().dataset.ygrid).toBe("1");
    expect(JSON.parse(localStorage.getItem(VIEW_PREFS_KEY) ?? "{}").smithYGrid).toBe(true);
  });
});
