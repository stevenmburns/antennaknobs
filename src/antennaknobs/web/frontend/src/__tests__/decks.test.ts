// Opened decks (lib/decks.ts): the link grammar, the compression the link
// carries, and the transport that adds the deck to every request for it.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MAX_SHARE_CHARS,
  clearDecks,
  compressDeck,
  decodeMaaBytes,
  ensureDeckTransport,
  isBinaryDesign,
  openDeckFile,
  readDesignFile,
  rememberDeck,
  withDeck,
  withDeckBody,
  type OpenedDeck,
} from "../lib/decks";
import { linkSearch, parseDeepLink } from "../lib/deepLink";
import { HARNESS_EXAMPLE } from "./designSessionHarness";

const KEY = "deck.0123456789ab";
const deck = (z: string, name = "my dipole.nec"): OpenedDeck => ({
  key: KEY,
  name,
  z,
  example: { ...HARNESS_EXAMPLE, name: KEY, label: "my dipole" },
});

async function inflate(z: string): Promise<string> {
  const b64 = z.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  const out = new Response(bytes).body!.pipeThrough(new DecompressionStream("deflate-raw"));
  return await new Response(out).text();
}

afterEach(() => {
  clearDecks();
  vi.unstubAllGlobals();
});

describe("the deck's compressed form", () => {
  it("round-trips through deflate-raw base64url, with no padding or unsafe characters", async () => {
    const text = "CM test\nCE\nGW 1 11 0 -5 10 0 5 10 0.001\nGE 0\nEX 0 1 6 0 1 0\nEN\n";
    const z = await compressDeck(text);
    expect(z).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(await inflate(z)).toBe(text);
  });
});

describe("the link carries the deck", () => {
  it("writes ?deck=&name= in place of design= when the deck fits", () => {
    const s = linkSearch("", {
      design: KEY,
      variant: null,
      analysis: null,
      view: null,
      deck: deck("abc_-123"),
    });
    const q = new URLSearchParams(s);
    expect(q.get("deck")).toBe("abc_-123");
    expect(q.get("name")).toBe("my dipole.nec");
    expect(q.get("design")).toBeNull();
    expect(s).toContain("name=my%20dipole.nec");
  });

  it("falls back to the key when the deck is too long to share", () => {
    const s = linkSearch("?deck=old&name=old.nec", {
      design: KEY,
      variant: null,
      analysis: null,
      view: null,
      deck: deck("x".repeat(MAX_SHARE_CHARS + 1)),
    });
    const q = new URLSearchParams(s);
    expect(q.get("design")).toBe(KEY);
    expect(q.get("deck")).toBeNull();
    expect(q.get("name")).toBeNull();
  });

  it("writes &dialect= beside the deck when one is chosen, and reads it back", () => {
    const s = linkSearch("", {
      design: KEY,
      variant: null,
      analysis: null,
      view: null,
      deck: { ...deck("abc_-123"), dialect: "nec4" },
    });
    expect(new URLSearchParams(s).get("dialect")).toBe("nec4");
    expect(parseDeepLink(s)!.deck).toEqual({ z: "abc_-123", name: "my dipole.nec", dialect: "nec4" });
    // Detected: no dialect in the link; an unknown one is dropped.
    const auto = linkSearch("?dialect=nec5", { design: KEY, variant: null, analysis: null, view: null, deck: deck("abc") });
    expect(new URLSearchParams(auto).get("dialect")).toBeNull();
    expect(parseDeepLink("?deck=abc&name=a.nec&dialect=nec7")!.deck).toEqual({ z: "abc", name: "a.nec" });
  });

  it("every request for a deck read in a chosen dialect carries the choice", () => {
    rememberDeck({ ...deck("abc"), dialect: "nec2" });
    expect(withDeck({ geometry: KEY })).toEqual({
      geometry: KEY,
      _deck: { name: "my dipole.nec", z: "abc", dialect: "nec2" },
    });
  });

  it("parses a deck link", () => {
    const link = parseDeepLink("?deck=abc_-123&name=my%20dipole.nec&view=Smith")!;
    expect(link.deck).toEqual({ z: "abc_-123", name: "my dipole.nec" });
    expect(link.design).toBeNull();
    expect(link.view).toBe("Smith");
    expect(parseDeepLink("?deck=abc")!.deck).toEqual({ z: "abc", name: "deck.nec" });
  });
});

describe("every request for an opened deck carries it", () => {
  it("withDeck adds the deck to a request naming it, and to nothing else", () => {
    rememberDeck(deck("zzz"));
    expect(withDeck({ geometry: KEY, a: 1 })).toEqual({
      geometry: KEY,
      a: 1,
      _deck: { name: "my dipole.nec", z: "zzz" },
    });
    const other = { geometry: "dipoles.invvee" };
    expect(withDeck(other)).toBe(other);
    const unknown = { geometry: "deck.ffffffffffff" };
    expect(withDeck(unknown)).toBe(unknown);
    expect(withDeckBody("not json")).toBe("not json");
  });

  it("the fetch transport adds it to a POST body", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
      seen.push(String(init?.body));
      return new Response("{}");
    });
    rememberDeck(deck("zzz")); // installs the transport over the stub
    ensureDeckTransport(); // idempotent
    await fetch("/sweep", { method: "POST", body: JSON.stringify({ geometry: KEY, freqs_mhz: [14] }) });
    await fetch("/sweep", { method: "POST", body: JSON.stringify({ geometry: "dipoles.invvee" }) });
    expect(JSON.parse(seen[0])._deck).toEqual({ name: "my dipole.nec", z: "zzz" });
    expect(JSON.parse(seen[1])._deck).toBeUndefined();
  });
});

// AK#1897: an MMANA-GAL .maa is ASCII or cp1251, never UTF-8. The browser must
// hand the server the Cyrillic it means -- a `w1с` position (Cyrillic с, which
// MMANA accepts) read as UTF-8 would arrive as U+FFFD and be refused.
describe("reading an MMANA .maa", () => {
  // "* Провода *" then a source line `w1с` with a Cyrillic с, in cp1251.
  const cp1251 = Uint8Array.from([
    0x2a, 0x20, 0xcf, 0xf0, 0xee, 0xe2, 0xee, 0xe4, 0xe0, 0x20, 0x2a, 0x0a, 0x77, 0x31, 0xf1, 0x0a,
  ]);

  it("decodes cp1251 when the bytes are not UTF-8", () => {
    expect(decodeMaaBytes(cp1251)).toBe("* Провода *\nw1с\n");
  });

  it("keeps ASCII and UTF-8 as they are", () => {
    expect(decodeMaaBytes(new TextEncoder().encode("w1c, 0.0, 1.0\n"))).toBe("w1c, 0.0, 1.0\n");
    expect(decodeMaaBytes(new TextEncoder().encode("Диполь\n"))).toBe("Диполь\n");
  });

  it("reads a .maa file through the decoder and any other file as UTF-8", async () => {
    const maa = new File([cp1251], "DP20.MAA");
    // jsdom's File may lack arrayBuffer(); the product reads a .maa's bytes through it.
    if (typeof (maa as Blob).arrayBuffer !== "function") {
      Object.defineProperty(maa, "arrayBuffer", { value: async () => cp1251.slice().buffer });
    }
    expect(await readDesignFile(maa)).toBe("* Провода *\nw1с\n");
    const nec = new File(["GW 1 3 0 0 0 0 0 1 0.001\n"], "d.nec");
    // jsdom's File may lack text(); the product reads a .nec through it.
    if (typeof (nec as Blob).text !== "function") {
      Object.defineProperty(nec, "text", { value: async () => "GW 1 3 0 0 0 0 0 1 0.001\n" });
    }
    expect(await readDesignFile(nec)).toBe("GW 1 3 0 0 0 0 0 1 0.001\n");
  });
});

// AK#1958: an EZNEC .ez is binary. It must reach the server byte for byte --
// read as text, every byte >= 0x80 would be replaced and the model lost.
describe("opening an EZNEC .ez", () => {
  const ezBytes = Uint8Array.from([0x00, 0x7f, 0x80, 0x9f, 0xa0, 0xff, 0x18, 0x05, 0x45, 0x43, 0x00]);

  async function inflateBytes(z: string): Promise<Uint8Array> {
    const b64 = z.replace(/-/g, "+").replace(/_/g, "/");
    const bin = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
    const packed = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const out = new Response(packed).body!.pipeThrough(new DecompressionStream("deflate-raw"));
    return new Uint8Array(await new Response(out).arrayBuffer());
  }

  it("names .ez (any case) as binary and nothing else", () => {
    expect(isBinaryDesign("model.ez")).toBe(true);
    expect(isBinaryDesign("MODEL.EZ")).toBe(true);
    expect(isBinaryDesign("model.nec")).toBe(false);
    expect(isBinaryDesign("model.ez.nec")).toBe(false);
  });

  it("posts the file's bytes, compressed, with no text decoding between", async () => {
    const file = new File([ezBytes], "loop.ez");
    if (typeof (file as Blob).arrayBuffer !== "function") {
      Object.defineProperty(file, "arrayBuffer", { value: async () => ezBytes.slice().buffer });
    }
    let posted: { name: string; z: string } | null = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: unknown, init?: RequestInit) => {
        posted = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({ key: KEY, example: { ...HARNESS_EXAMPLE, name: KEY, label: "loop" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }),
    );
    const opened = await openDeckFile(file);
    expect(posted).not.toBeNull();
    expect(posted!.name).toBe("loop.ez");
    expect(Array.from(await inflateBytes(posted!.z))).toEqual(Array.from(ezBytes));
    expect(opened.key).toBe(KEY);
  });
});
