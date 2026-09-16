// AK#1539: the Files view's SimNEC tab. The .ssn export was a Python command,
// which is no export at all for someone whose entire interface is the packaged
// workbench window. The circuit arrives from POST /design_ssn beside the
// design's source and the engine's deck, with the same Copy and Download.
//
// The server builds the file from the request (that side is
// tests/test_design_ssn_1539.py); what is pinned here is the pane: a tab that
// is always offered, the filename the download carries, and a design SimNEC
// cannot represent showing the exporter's reason instead of nothing.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { FilesPanel, type FilesViewData } from "../components/results/FilesPanel";

const SOURCE = {
  available: true as const,
  geometry: "dipoles.invvee",
  filename: "invvee.py",
  language: "python",
  text: "class Builder:\n    pass\n",
};
const SSN = {
  available: true as const,
  geometry: "dipoles.invvee",
  filename: "dipoles_invvee.ssn",
  language: "ssn",
  text: '<?xml version="1.0"?>\n<SimNEC1p0>\n</SimNEC1p0>\n',
};

function data(over: Partial<FilesViewData> = {}): FilesViewData {
  return {
    geometry: "dipoles.invvee",
    engine: null,
    solved: true,
    source: SOURCE,
    ssn: SSN,
    engineIo: null,
    stale: false,
    ...over,
  };
}

const mount = (d: FilesViewData) =>
  render(<FilesPanel data={d} size={180} fill={true} />).container;

function clickTab(c: HTMLElement, label: RegExp) {
  const tab = [...c.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find((b) =>
    label.test(b.textContent ?? ""),
  );
  if (!tab) throw new Error(`no tab ${label}`);
  fireEvent.click(tab);
}

const text = (c: HTMLElement) => c.querySelector("pre.files-text")?.textContent ?? null;

let saved: string[];

beforeEach(() => {
  saved = [];
  URL.createObjectURL = vi.fn(() => "blob:files");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.download);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the SimNEC tab", () => {
  it("shows the circuit the server wrote", () => {
    const c = mount(data());
    clickTab(c, /^SimNEC$/);
    expect(text(c)).toBe(SSN.text);
  });

  it("downloads it under the design's .ssn name", () => {
    const c = mount(data());
    clickTab(c, /^SimNEC$/);
    const download = [...c.querySelectorAll<HTMLButtonElement>(".files-action")].find(
      (b) => b.textContent === "Download",
    );
    fireEvent.click(download!);
    expect(saved).toEqual(["dipoles_invvee.ssn"]);
  });

  it("is offered whatever solver ran — the file needs no engine", () => {
    // The deck and output tabs depend on a binary having run; this one is
    // written from the design, so a momwire solve has it too.
    const c = mount(data({ engine: null, engineIo: null }));
    clickTab(c, /^SimNEC$/);
    expect(text(c)).toBe(SSN.text);
  });

  it("says the exporter's reason for a design SimNEC cannot carry", () => {
    const c = mount(
      data({
        ssn: {
          available: false,
          geometry: "dipoles.invvee",
          reason: "distributed (finite-gap) feed port: no SimNEC spelling",
        },
      }),
    );
    clickTab(c, /^SimNEC$/);
    expect(text(c)).toBeNull();
    expect(c.textContent).toMatch(/distributed/);
  });

  it("waits rather than claiming there is none, before it arrives", () => {
    const c = mount(data({ ssn: null }));
    clickTab(c, /^SimNEC$/);
    expect(c.textContent).toMatch(/Writing the SimNEC circuit/);
  });

  it("leaves the source tab the one it opens on", () => {
    expect(text(mount(data()))).toBe(SOURCE.text);
  });
});
