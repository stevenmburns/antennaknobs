// Opened decks through the real app shell (AC6LA, QRZ 1005128 #40): a file
// opened from the picker becomes the tab's design and the page's link
// carries it; a ?deck= link reproduces the design in a fresh page; a deck
// too long for a link says so; and the hosted server's busy and budget
// answers reach the user in its own words.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import type { ExampleDescriptor } from "../lib/params";
import { clearDecks, compressDeck } from "../lib/decks";
import { invveeShape } from "./fixtures/solveShapes";
import { HARNESS_EXAMPLE, mountDesignSession, sessionReady } from "./designSessionHarness";

vi.setConfig({ testTimeout: 20_000 });

const KEY = "deck.0123456789ab";
const DECK_EXAMPLE: ExampleDescriptor = { ...HARNESS_EXAMPLE, name: KEY, label: "mydeck" };
const DECK_TEXT = "CM test\nCE\nGW 1 11 0 -5 10 0 5 10 0.001\nGE 0\nEX 0 1 6 0 1 0\nEN\n";

type Body = Record<string, unknown>;
const sent: Body[] = [];
let reply: (req: Body) => Body = (req) => ({
  ...invveeShape,
  feeds: undefined,
  geometry: req.geometry,
  _seq: req._seq,
  z0_ohms: 50,
});

// A socket that answers every solve with `reply`, and records what it got.
class StubWebSocket {
  static OPEN = 1;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    setTimeout(() => {
      this.readyState = StubWebSocket.OPEN;
      this.onopen?.();
    }, 0);
  }
  send(payload: string) {
    const req = JSON.parse(payload) as Body;
    if (!("geometry" in req) || typeof req._seq !== "number") return;
    sent.push(req);
    const out = reply(req);
    setTimeout(() => this.onmessage?.({ data: JSON.stringify(out) } as MessageEvent), 0);
  }
  close() {}
}

const json = (body: unknown, status = 200) =>
  ({ ok: status < 400, status, json: async () => body }) as unknown as Response;

function mount(url: string, extra: Body = {}) {
  const opened: Body[] = [];
  const geometry: Body[] = [];
  mountDesignSession({
    url,
    examples: [HARNESS_EXAMPLE],
    routes: {
      "/deck": (_u: string, init?: RequestInit) => {
        opened.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return json({ key: KEY, example: DECK_EXAMPLE, limits: {}, ...extra });
      },
      "/geometry": (_u: string, init?: RequestInit) => {
        geometry.push(JSON.parse(String(init?.body ?? "{}")) as Body);
        return json({ wires: [] });
      },
    },
  });
  return { opened, geometry };
}

const query = () => new URLSearchParams(window.location.search);
const ready = () => document.querySelector<HTMLElement>(".app[data-ready]")?.dataset.ready ?? "";

function openFile(text: string, name = "mydeck.nec") {
  const input = screen.getByLabelText("open an antenna model (.nec, .ssn, .maa, .ez or .py)") as HTMLInputElement;
  const file = new File([text], name);
  // jsdom's File may lack text(); the product reads the file through it.
  if (typeof (file as Blob).text !== "function") {
    Object.defineProperty(file, "text", { value: async () => text });
  }
  fireEvent.change(input, { target: { files: [file] } });
}

beforeEach(() => {
  sent.length = 0;
  vi.stubGlobal("WebSocket", StubWebSocket);
});
afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
  reply = (req) => ({ ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 });
});

describe("opening a deck", () => {
  it("opens the file as the tab's design, and the link carries it", async () => {
    const { opened, geometry } = mount("/");
    await sessionReady(document.body);
    openFile(DECK_TEXT);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened).toHaveLength(1);
    expect(opened[0]).toEqual({ name: "mydeck.nec", z: await compressDeck(DECK_TEXT) });
    await waitFor(() => expect(query().get("deck")).toBe(opened[0].z), { timeout: 5000 });
    expect(query().get("name")).toBe("mydeck.nec");
    expect(query().get("design")).toBeNull();
    // The picker shows the deck by its file name, extension included (AK#2071).
    expect((screen.getByRole("combobox", { name: "antenna" }) as HTMLInputElement).value).toBe("mydeck.nec");
    // Every request for it carries the deck, so a server that never saw it
    // rebuilds it: the preview's POST and the live solve's message alike.
    const deckPreview = geometry.find((b) => b.geometry === KEY);
    expect(deckPreview?._deck).toEqual(opened[0]);
    await waitFor(() => expect(sent.some((m) => m.geometry === KEY)).toBe(true), { timeout: 5000 });
    expect(sent.find((m) => m.geometry === KEY)?._deck).toEqual(opened[0]);
  });

  it("a ?deck= link opens the same design in a fresh page", async () => {
    const z = await compressDeck(DECK_TEXT);
    const { opened } = mount(`/?deck=${z}&name=mydeck.nec`);
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened[0]).toEqual({ name: "mydeck.nec", z });
    expect(query().get("deck")).toBe(z);
    expect(screen.queryByRole("alert", { name: "Link problems" })).toBeNull();
  });

  it("a link's analyses ride to /deck, stay in the link, and every request carries them (AK#2045)", async () => {
    const z = await compressDeck(DECK_TEXT);
    const analyses = await compressDeck('[an.Analysis("half", an.Sweep("sy_half", 4, 6))]');
    const { opened, geometry } = mount(`/?deck=${z}&name=mydeck.nec&analyses=${analyses}`, {
      analyses: 1,
      analyses_refusal: null,
    });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened[0]).toEqual({ name: "mydeck.nec", z, analyses });
    await waitFor(() => expect(query().get("analyses")).toBe(analyses), { timeout: 5000 });
    expect(query().get("deck")).toBe(z);
    const deckPreview = geometry.find((b) => b.geometry === KEY);
    expect(deckPreview?._deck).toEqual({ name: "mydeck.nec", z, analyses });
    expect(screen.queryByRole("alert", { name: "Link problems" })).toBeNull();
  });

  it("a link's knob ranges ride to /deck and every request; its values set the panel (AK#2045)", async () => {
    const z = await compressDeck(DECK_TEXT);
    // The deck as the server answers it: the link's range is its knob's own.
    const example: ExampleDescriptor = {
      ...DECK_EXAMPLE,
      param_schema: [
        {
          name: "sy_half",
          label: "half",
          default: 5.1,
          kind: "float",
          min: 4,
          max: 6,
          step: 0.002,
          precision: 3,
          unit: null,
          visible_when: null,
          auto_range: false,
        },
      ],
    };
    const { opened, geometry } = mount(`/?deck=${z}&name=mydeck.nec&knobs=sy_half:5.5:4:6`, {
      example,
      ranges_refusal: null,
    });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened[0]).toEqual({ name: "mydeck.nec", z, ranges: "sy_half:4:6" });
    await waitFor(() => expect(query().get("knobs")).toBe("sy_half:5.5:4:6"), { timeout: 5000 });
    expect(geometry.find((b) => b.geometry === KEY)?._deck).toEqual({ name: "mydeck.nec", z, ranges: "sy_half:4:6" });
    await waitFor(() => expect(sent.some((m) => m.geometry === KEY && m.sy_half === 5.5)).toBe(true), {
      timeout: 5000,
    });
    expect(sent.find((m) => m.geometry === KEY)?._deck).toEqual({ name: "mydeck.nec", z, ranges: "sy_half:4:6" });
    expect(screen.queryByRole("alert", { name: "Link problems" })).toBeNull();
  });

  it("knob ranges the server does not take are named, and the deck opens anyway", async () => {
    const z = await compressDeck(DECK_TEXT);
    mount(`/?deck=${z}&name=mydeck.nec&knobs=nope:1:0:2`, {
      ranges_refusal: "the link gives nope a range, and this deck has no knob 'nope'",
    });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    const n = await screen.findByRole("alert", { name: "Link problems" }, { timeout: 5000 });
    expect(n.textContent).toContain("knobs: the link gives nope a range");
    expect(n.textContent).toContain(`this design has no knob "nope"`);
  });

  it("analyses the server refuses are named, and the deck opens anyway", async () => {
    const z = await compressDeck(DECK_TEXT);
    mount(`/?deck=${z}&name=mydeck.nec&analyses=AAAA`, {
      analyses: 0,
      analyses_refusal: "the link's analyses were not read: refused: Name 'os'",
    });
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    const n = await screen.findByRole("alert", { name: "Link problems" }, { timeout: 5000 });
    expect(n.textContent).toContain("refused: Name 'os'");
  });

  it("a deck too long for a link opens, and says the link cannot share it", async () => {
    // Incompressible text: its compressed form is well over the link's 8 KB.
    let text = "CM ";
    let x = 12345;
    for (let i = 0; i < 24_000; i++) {
      x = (x * 48271) % 2147483647; // MINSTD: no period deflate can find
      text += String.fromCharCode(33 + (x % 90));
    }
    mount("/");
    await sessionReady(document.body);
    openFile(text, "huge.nec");
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    const note = await screen.findByRole("status", { name: "Deck link" }, { timeout: 5000 });
    expect(note.textContent).toContain("too long to share in a link");
    expect(note.textContent).toContain("huge.nec");
    await waitFor(() => expect(query().get("design")).toBe(KEY), { timeout: 5000 });
    expect(query().get("deck")).toBeNull();
  });

  it("a deck the server refuses says why, and the tab stays where it was", async () => {
    mountDesignSession({
      url: "/",
      examples: [HARNESS_EXAMPLE],
      routes: {
        "/deck": () =>
          json(
            { detail: "huge.nec, line 3: GR card: this deck builds 30000 segments (the limit is 3000)" },
            422,
          ),
      },
    });
    await sessionReady(document.body);
    openFile(DECK_TEXT, "huge.nec");
    const n = await screen.findByRole("alert", { name: "Deck problem" }, { timeout: 5000 });
    expect(n.textContent).toContain("the limit is 3000");
    expect(ready()).toMatch(/^dipoles\.probe#/);
  });
});

describe("the hosted server's answers for an opened deck", () => {
  it.each([
    ["busy", "The server is busy with another opened deck (for up to 48 s more). Try again in a minute"],
    ["budget", "This deck took longer than the hosted server's 60 s solve budget, so the solve was stopped"],
  ])("a %s answer on the live solve is shown in its words", async (status, message) => {
    reply = (req) =>
      req.geometry === KEY
        ? { geometry: req.geometry, _seq: req._seq, error: message, deck_status: status }
        : { ...invveeShape, feeds: undefined, geometry: req.geometry, _seq: req._seq, z0_ohms: 50 };
    mount("/");
    await sessionReady(document.body);
    openFile(DECK_TEXT);
    await waitFor(
      () => expect(document.querySelector(".solve-error-message")?.textContent).toBe(message),
      { timeout: 5000 },
    );
  });
});

describe("the dialect an opened deck is read in", () => {
  const NEC5_KEY = "deck.nec5nec5nec5";
  const record = (chosen: "nec2" | "nec5" | null) => ({
    read_as: chosen ?? "nec2",
    reason: chosen ? "chosen by the reader" : "no NEC-5 marker found",
    detected: "nec2",
    chosen,
  });
  function mountDialects(url: string) {
    const opened: Body[] = [];
    mountDesignSession({
      url,
      examples: [HARNESS_EXAMPLE],
      routes: {
        "/deck": (_u: string, init?: RequestInit) => {
          const body = JSON.parse(String(init?.body ?? "{}")) as Body;
          opened.push(body);
          const nec5 = body.dialect === "nec5";
          const key = nec5 ? NEC5_KEY : KEY;
          return json({
            key,
            example: { ...DECK_EXAMPLE, name: key },
            dialect: record(nec5 ? "nec5" : null),
            limits: {},
          });
        },
        "/geometry": () => json({ wires: [] }),
      },
    });
    return opened;
  }

  it("re-opens the deck read as the reader chooses, and the link carries the choice", async () => {
    const opened = mountDialects("/");
    await sessionReady(document.body);
    openFile(DECK_TEXT);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    const select = (await screen.findByLabelText("read the deck as", {}, { timeout: 5000 })) as HTMLSelectElement;
    expect(select.value).toBe("auto");
    expect(select.options[0].textContent).toBe("auto (NEC-2)");
    expect(query().get("dialect")).toBeNull();
    fireEvent.change(select, { target: { value: "nec5" } });
    await waitFor(() => expect(ready()).toMatch(/^deck\.nec5nec5nec5#/), { timeout: 5000 });
    expect(opened[1]).toEqual({ name: "mydeck.nec", z: opened[0].z, dialect: "nec5" });
    await waitFor(() => expect(query().get("dialect")).toBe("nec5"), { timeout: 5000 });
    expect(query().get("deck")).toBe(opened[0].z);
    // Every request for the NEC-5 reading carries the choice with the deck.
    await waitFor(() => expect(sent.some((m) => m.geometry === NEC5_KEY)).toBe(true), { timeout: 5000 });
    expect(sent.find((m) => m.geometry === NEC5_KEY)?._deck).toEqual(opened[1]);
    // Back to detection: the link drops the choice again.
    fireEvent.change(screen.getByLabelText("read the deck as"), { target: { value: "auto" } });
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened[2]).toEqual({ name: "mydeck.nec", z: opened[0].z });
    await waitFor(() => expect(query().get("dialect")).toBeNull(), { timeout: 5000 });
  });

  it("a link with &dialect= opens the deck read that way", async () => {
    const z = await compressDeck(DECK_TEXT);
    const opened = mountDialects(`/?deck=${z}&name=mydeck.nec&dialect=nec5`);
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.nec5nec5nec5#/), { timeout: 5000 });
    expect(opened[0]).toEqual({ name: "mydeck.nec", z, dialect: "nec5" });
    const select = (await screen.findByLabelText("read the deck as", {}, { timeout: 5000 })) as HTMLSelectElement;
    expect(select.value).toBe("nec5");
  });
});

describe("a deck knob's Whole numbers box (AK#2297)", () => {
  const DECIMAL_KEY = "deck.decimaldecim";
  const knob = (whole: boolean | null | undefined, extra: Record<string, unknown> = {}) => ({
    name: "sy_n",
    label: "n",
    default: whole === false ? 7.0 : 7,
    kind: whole === false ? "float" : "int",
    min: 4,
    max: 11,
    step: whole === false ? 0.001 : 1,
    precision: whole === false ? 3 : 0,
    unit: null,
    visible_when: null,
    auto_range: true,
    ...(whole === undefined ? {} : { whole_numbers: whole }),
    ...extra,
  });
  const half = {
    name: "sy_half",
    label: "half",
    default: 5.1,
    kind: "float",
    min: 2.55,
    max: 7.65,
    step: 0.001,
    precision: 3,
    unit: null,
    visible_when: null,
    auto_range: true,
    whole_numbers: null,
  };
  function mountSwitch(url = "/") {
    const opened: Body[] = [];
    mountDesignSession({
      url,
      examples: [HARNESS_EXAMPLE],
      routes: {
        "/deck": (_u: string, init?: RequestInit) => {
          const body = JSON.parse(String(init?.body ?? "{}")) as Body;
          opened.push(body);
          const decimal = Array.isArray(body.decimal_knobs) && body.decimal_knobs.includes("sy_n");
          const key = decimal ? DECIMAL_KEY : KEY;
          return json({
            key,
            example: { ...DECK_EXAMPLE, name: key, param_schema: [knob(!decimal), half] },
            limits: {},
          });
        },
        "/geometry": () => json({ wires: [] }),
      },
    });
    return opened;
  }
  const menuBox = () => screen.queryByRole("checkbox", { name: "Whole numbers" }) as HTMLInputElement | null;

  it("is offered only on a switchable knob, and toggling it re-opens the deck with the list", async () => {
    const opened = mountSwitch();
    await sessionReady(document.body);
    openFile(DECK_TEXT);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    // A real knob the import never made whole-number: no box.
    fireEvent.contextMenu(await screen.findByRole("slider", { name: "half" }, { timeout: 5000 }));
    expect(screen.getByText("Turn step")).toBeTruthy();
    expect(menuBox()).toBeNull();
    fireEvent.click(document.body.querySelector(".knob-menu-backdrop") as HTMLElement);
    // A knob moved off its default keeps its value through the re-open.
    fireEvent.keyDown(screen.getByRole("slider", { name: "half" }), { key: "ArrowUp" });
    await waitFor(() => expect(sent.some((m) => m.geometry === KEY && m.sy_half !== 5.1)).toBe(true), {
      timeout: 5000,
    });
    const moved = sent.filter((m) => m.geometry === KEY).at(-1)!.sy_half;
    // The whole-number knob: ticked; unticking sends the list.
    fireEvent.contextMenu(screen.getByRole("slider", { name: "n" }));
    expect(menuBox()!.checked).toBe(true);
    fireEvent.click(menuBox()!);
    await waitFor(() => expect(ready()).toMatch(/^deck\.decimaldecim#/), { timeout: 5000 });
    expect(opened[1]).toEqual({ name: "mydeck.nec", z: opened[0].z, decimal_knobs: ["sy_n"] });
    await waitFor(() => expect(query().get("decimal")).toBe("sy_n"), { timeout: 5000 });
    await waitFor(() => expect(sent.some((m) => m.geometry === DECIMAL_KEY)).toBe(true), { timeout: 5000 });
    expect(sent.find((m) => m.geometry === DECIMAL_KEY)?._deck).toEqual(opened[1]);
    expect(sent.find((m) => m.geometry === DECIMAL_KEY)?.sy_half).toBe(moved);
    // And back: the box is unticked now, ticking it drops the list.
    fireEvent.contextMenu(screen.getByRole("slider", { name: "n" }));
    expect(menuBox()!.checked).toBe(false);
    fireEvent.click(menuBox()!);
    await waitFor(() => expect(ready()).toMatch(/^deck\.0123456789ab#/), { timeout: 5000 });
    expect(opened[2]).toEqual({ name: "mydeck.nec", z: opened[0].z });
    await waitFor(() => expect(query().get("decimal")).toBeNull(), { timeout: 5000 });
  });

  it("a link with &decimal= opens the deck with the knob read as decimals", async () => {
    const z = await compressDeck(DECK_TEXT);
    const opened = mountSwitch(`/?deck=${z}&name=mydeck.nec&decimal=sy_n`);
    await sessionReady(document.body);
    await waitFor(() => expect(ready()).toMatch(/^deck\.decimaldecim#/), { timeout: 5000 });
    expect(opened[0]).toEqual({ name: "mydeck.nec", z, decimal_knobs: ["sy_n"] });
  });

  it("a catalog design's int param is not offered the box", async () => {
    const catalog: ExampleDescriptor = {
      ...HARNESS_EXAMPLE,
      param_schema: [knob(undefined, { name: "n_dir", label: "n_dir" })],
    } as ExampleDescriptor;
    mountDesignSession({ url: "/", examples: [catalog] });
    await sessionReady(document.body);
    fireEvent.contextMenu(await screen.findByRole("slider", { name: "n_dir" }, { timeout: 5000 }));
    expect(screen.getByText("Turn step")).toBeTruthy();
    expect(menuBox()).toBeNull();
  });
});
