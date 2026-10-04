// Opened decks (lib/decks.ts): the link grammar, the compression the link
// carries, and the transport that adds the deck to every request for it.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MAX_SHARE_CHARS,
  clearDecks,
  compressDeck,
  ensureDeckTransport,
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
