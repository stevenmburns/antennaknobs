// Pins the Files view (src/components/results/FilesPanel.tsx, AK#1428): the
// Source tab shows the design's file, the Deck and Output tabs show exactly the
// texts an external engine ran on and printed, labelled with the engine's
// served name, and a solve that ran no binary says so instead of showing a deck
// nothing was given.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render } from "@testing-library/react";
import { FilesPanel, type FilesViewData } from "../components/results/FilesPanel";

const SOURCE = {
  available: true as const,
  geometry: "dipoles.invvee",
  filename: "invvee.py",
  language: "python",
  text: "class Builder:\n    pass\n",
};
const RUN = { deck: "CM the deck\nEN\n", printout: "THE PRINTOUT\n", cached: false };

function data(over: Partial<FilesViewData> = {}): FilesViewData {
  return {
    geometry: "dipoles.invvee",
    engine: "Engine-A",
    solved: true,
    source: SOURCE,
    engineIo: {
      available: true,
      solver: "enga",
      label: "Engine-A",
      solve_id: "s1",
      runs: [RUN],
    },
    stale: false,
    ...over,
  };
}

function mount(d: FilesViewData | null, fill = true) {
  return render(<FilesPanel data={d} size={180} fill={fill} />).container;
}

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

describe("tabs", () => {
  it("opens on the source tab, named for the file", () => {
    const c = mount(data());
    expect(text(c)).toBe(SOURCE.text);
    const selected = c.querySelector('[role="tab"][aria-selected="true"]');
    expect(selected?.textContent).toBe("invvee.py");
  });

  it("shows the run's deck and printout byte for byte, under the served engine name", () => {
    const c = mount(data());
    clickTab(c, /^Engine-A deck$/);
    expect(text(c)).toBe(RUN.deck);
    clickTab(c, /^Engine-A output$/);
    expect(text(c)).toBe(RUN.printout);
  });
});

describe("a solve that ran no binary", () => {
  it("the deck and output tabs say no deck ran, and show no text", () => {
    const c = mount(data({ engine: null, engineIo: null }));
    clickTab(c, /deck/);
    expect(text(c)).toBeNull();
    expect(c.textContent).toMatch(/runs no external program/);
    clickTab(c, /output/);
    expect(text(c)).toBeNull();
  });

  it("before any solve, the engine tabs wait rather than claim no engine", () => {
    const c = mount(data({ engine: null, engineIo: null, solved: false }));
    clickTab(c, /deck/);
    expect(c.textContent).toMatch(/Waiting for a solve/);
  });

  it("the source tab still works", () => {
    expect(text(mount(data({ engine: null, engineIo: null })))).toBe(SOURCE.text);
  });

  it("a design with no file says so", () => {
    const c = mount(data({ source: { available: false, geometry: "dipoles.invvee" } }));
    expect(text(c)).toBeNull();
    expect(c.textContent).toMatch(/no source file/);
  });
});

describe("runs", () => {
  it("offers a picker when a solve took several runs, with each run's note", () => {
    const second = { deck: "CM second\nEN\n", printout: "SECOND\n", cached: false, note: "re-run" };
    const c = mount(
      data({
        engineIo: { available: true, solver: "enga", label: "Engine-A", runs: [RUN, second] },
      }),
    );
    clickTab(c, /deck/);
    const picker = c.querySelector("select.files-run") as HTMLSelectElement;
    expect(picker).not.toBeNull();
    expect(text(c)).toBe(RUN.deck);
    fireEvent.change(picker, { target: { value: "1" } });
    expect(text(c)).toBe(second.deck);
    expect(c.querySelector(".files-note")?.textContent).toBe("re-run");
  });

  it("no picker for a single run", () => {
    const c = mount(data());
    clickTab(c, /deck/);
    expect(c.querySelector("select.files-run")).toBeNull();
  });

  it("a failed re-run shows the error AND what the binary printed", () => {
    const c = mount(
      data({
        engineIo: {
          available: true,
          solver: "enga",
          label: "Engine-A",
          runs: [RUN],
          error: "the engine said no",
        },
      }),
    );
    clickTab(c, /output/);
    expect(c.querySelector(".files-error")?.textContent).toBe("the engine said no");
    expect(text(c)).toBe(RUN.printout);
  });

  it("dims the engine texts of an earlier solve, never the source", () => {
    const c = mount(data({ stale: true }));
    expect(c.querySelector("pre.files-text.stale")).toBeNull();
    expect(c.textContent).not.toMatch(/previous solve/);
    clickTab(c, /deck/);
    expect(c.querySelector("pre.files-text.stale")).not.toBeNull();
    // Dimming alone was easy to miss; the pane says it in words.
    expect(c.textContent).toMatch(/From the previous solve/);
  });
});

describe("copy and download", () => {
  it("downloads each tab under a name that says what it is", () => {
    const c = mount(data());
    const download = () =>
      fireEvent.click([...c.querySelectorAll("button")].find((b) => b.textContent === "Download")!);
    download();
    clickTab(c, /deck/);
    download();
    clickTab(c, /output/);
    download();
    expect(saved).toEqual(["invvee.py", "dipoles_invvee_enga.nec", "dipoles_invvee_enga.out"]);
  });

  it("copies the text on screen", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const c = mount(data());
    clickTab(c, /output/);
    await act(async () => {
      fireEvent.click([...c.querySelectorAll("button")].find((b) => b.textContent === "Copy")!);
    });
    expect(writeText).toHaveBeenCalledWith(RUN.printout);
  });
});

describe("sizing", () => {
  it("the rail's thumbnail, handed no texts, carries a label", () => {
    const c = mount(null, false);
    expect(c.querySelector(".files-thumb")).not.toBeNull();
    expect(text(c)).toBeNull();
  });

  // `fill` is layout, not "stage": a stage that does not fill still gets the
  // whole panel, in a size×size box, never the thumbnail's label.
  it("a non-filling stage with texts gets the panel in a sized box", () => {
    const c = mount(data(), false);
    const box = c.querySelector(".files-box") as HTMLElement;
    expect(box).not.toBeNull();
    expect(box.style.width).toBe("180px");
    expect(text(c)).toBe(SOURCE.text);
    expect(c.querySelector(".files-thumb")).toBeNull();
  });
});
