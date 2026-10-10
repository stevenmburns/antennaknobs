// Opened decks (AC6LA, QRZ 1005128 #40/#42): a visitor's own .nec / .ssn / .maa
// / .ez, studied in the workbench with nothing installed, and shared by its link.
//
// The deck travels as its TEXT, never parsed here -- an EZNEC .ez, which is
// binary, as its BYTES (AK#1958). The browser compresses it
// (CompressionStream "deflate-raw", base64url) into the page's address,
// `?deck=<z>&name=<file name>`, and POSTs it to /deck, which parses it with the
// same importer `@path` uses and answers with the design key
// (`deck.<hash12>`) and the catalog record. Every later request for that
// design carries the deck again (`_deck`) so a server that has never seen it
// — a restart, a second machine, an evicted entry — rebuilds it on the spot:
// the link is the whole state. `withDeck` adds it; `ensureDeckTransport`
// wraps `fetch` so every POST naming a deck carries it without each of the
// workbench's two dozen request sites knowing decks exist, and the /ws solve
// channel calls `withDeck` itself.
//
// React-free, so the link grammar and the store are tested alone.

import type { ExampleDescriptor } from "./params";
import { apiFetch } from "./pin";

export const DECK_NS = "deck.";

/** The longest compressed deck a shareable link carries (~8 KB). Past it the
 *  deck still opens in this tab; the page says the link cannot share it. */
export const MAX_SHARE_CHARS = 8000;

/** The NEC dialects a reader may choose to read a deck in (the server's
 *  `nec_import.parse_nec(dialect=...)`); absent means detect. */
export const DIALECTS = ["nec2", "nec4", "nec5"] as const;
export type Dialect = (typeof DIALECTS)[number];
export const DIALECT_LABEL: Record<Dialect, string> = { nec2: "NEC-2", nec4: "NEC-4", nec5: "NEC-5" };

export const isDialect = (v: unknown): v is Dialect =>
  typeof v === "string" && (DIALECTS as readonly string[]).includes(v);

/** `dialect`: the reader's choice, absent to let the server detect it. */
export type DeckPayload = { name: string; z: string; dialect?: Dialect };

/** What /deck says the deck was read as, and why. */
export type DeckDialect = {
  read_as: Dialect;
  reason: string;
  /** What detection alone reads it as (null: detection refuses it). */
  detected: Dialect | null;
  chosen: Dialect | null;
};

export type OpenedDeck = DeckPayload & {
  key: string;
  example: ExampleDescriptor;
  readAs?: DeckDialect | null;
};

export const isDeck = (g: unknown): g is string =>
  typeof g === "string" && g.startsWith(DECK_NS);

/** Whether a deck's compressed form fits a link someone can share. */
export const shareable = (d: DeckPayload): boolean => d.z.length <= MAX_SHARE_CHARS;

// --- The store (module-level: every tab of the page shares it) -------------

const decks = new Map<string, OpenedDeck>();
const listeners = new Set<() => void>();
let snapshot: readonly OpenedDeck[] = [];

export function subscribeDecks(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Every deck opened in this page, oldest first (a stable snapshot for
 *  useSyncExternalStore). */
export function openedDecks(): readonly OpenedDeck[] {
  return snapshot;
}

export function deckFor(key: string): OpenedDeck | undefined {
  return decks.get(key);
}

export function rememberDeck(d: OpenedDeck): void {
  decks.set(d.key, d);
  snapshot = [...decks.values()];
  ensureDeckTransport();
  for (const fn of listeners) fn();
}

/** Tests only: forget every deck. */
export function clearDecks(): void {
  decks.clear();
  snapshot = [];
  for (const fn of listeners) fn();
}

// --- Compression -----------------------------------------------------------

function toBase64Url(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function drain(stream: ReadableStream<Uint8Array>): Promise<Uint8Array> {
  const reader = stream.getReader();
  const parts: Uint8Array[] = [];
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    n += value.length;
  }
  const out = new Uint8Array(n);
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

/** A deck's text as the link carries it: deflate-raw, base64url. */
export async function compressDeck(text: string): Promise<string> {
  return compressBytes(new TextEncoder().encode(text));
}

/** A file's bytes as the link carries them (a binary .ez, AK#1958): the same
 *  deflate-raw + base64url as a text deck, with no text encoding between. The
 *  server reads an .ez's payload as bytes. */
export async function compressBytes(bytes: Uint8Array): Promise<string> {
  const input = new ReadableStream<BufferSource>({
    start(c) {
      // A copy backed by a plain ArrayBuffer, which BufferSource requires.
      c.enqueue(new Uint8Array(bytes));
      c.close();
    },
  });
  return toBase64Url(await drain(input.pipeThrough(new CompressionStream("deflate-raw"))));
}

// --- The server ------------------------------------------------------------

/** What /deck refused, in its words, and its kind ("refused", "rate", ...). */
export class DeckOpenError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly deckStatus: string | null,
  ) {
    super(message);
  }
}

/** Open a deck on the server: its key and catalog record, remembered. */
export async function openDeck(payload: DeckPayload): Promise<OpenedDeck> {
  const resp = await apiFetch("/deck", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let body: {
    key?: string;
    example?: ExampleDescriptor;
    dialect?: DeckDialect | null;
    detail?: string;
    deck_status?: string;
  } = {};
  try {
    body = await resp.json();
  } catch {
    /* no JSON: the status says it */
  }
  if (!resp.ok || !body.key || !body.example) {
    throw new DeckOpenError(
      body.detail ?? `Could not open ${payload.name} (${resp.status}).`,
      resp.status,
      body.deck_status ?? null,
    );
  }
  const d: OpenedDeck = { ...payload, key: body.key, example: body.example, readAs: body.dialect ?? null };
  rememberDeck(d);
  return d;
}

/** An MMANA-GAL `.maa` file's text from its bytes. MMANA writes ASCII or
 *  cp1251 (Cyrillic headers and comments, never UTF-8), so the bytes are read
 *  as UTF-8 when they are valid UTF-8 and as windows-1251 otherwise -- the
 *  server's `maa_import.decode_maa` rule. Read as UTF-8 regardless, a Cyrillic
 *  `с` in a position (`w1с`, which MMANA accepts) would arrive as U+FFFD. */
export function decodeMaaBytes(bytes: Uint8Array): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1251").decode(bytes);
  }
}

/** A chosen design file's text: a `.maa` through `decodeMaaBytes`, every
 *  other file as UTF-8. */
export async function readDesignFile(file: File): Promise<string> {
  if (/\.maa$/i.test(file.name) && typeof file.arrayBuffer === "function") {
    return decodeMaaBytes(new Uint8Array(await file.arrayBuffer()));
  }
  return file.text();
}

/** Whether a file name is an EZNEC .ez model, which travels as bytes. */
export const isBinaryDesign = (name: string): boolean => /\.ez$/i.test(name);

/** Read a chosen file and open it: the browser reads the text (an .ez's
 *  bytes), nothing parses it here. */
export async function openDeckFile(file: File): Promise<OpenedDeck> {
  if (isBinaryDesign(file.name)) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return openDeck({ name: file.name, z: await compressBytes(bytes) });
  }
  const text = await readDesignFile(file);
  return openDeck({ name: file.name, z: await compressDeck(text) });
}

// --- Carrying the deck on every request ------------------------------------

/** What a request carries to rebuild a deck: its name, text and the
 *  dialect it was chosen to be read in (none when detected). */
export function deckPayload(d: DeckPayload): DeckPayload {
  return d.dialect ? { name: d.name, z: d.z, dialect: d.dialect } : { name: d.name, z: d.z };
}

/** `body` with its design's deck added as `_deck`, when it names an opened
 *  deck this page holds; `body` itself otherwise. */
export function withDeck<T extends Record<string, unknown>>(body: T): T {
  const g = body.geometry;
  if (!isDeck(g) || "_deck" in body) return body;
  const d = decks.get(g);
  return d ? { ...body, _deck: deckPayload(d) } : body;
}

/** A JSON request body string with `_deck` added (see `withDeck`); any
 *  other body is returned as it was. */
export function withDeckBody(body: unknown): unknown {
  if (typeof body !== "string" || !body.includes(`"${DECK_NS}`)) return body;
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return body;
    const out = withDeck(parsed as Record<string, unknown>);
    return out === parsed ? body : JSON.stringify(out);
  } catch {
    return body;
  }
}

const WRAPPED = Symbol.for("antennaknobs.deckFetch");

/** Wrap the page's `fetch` (once) so a POST naming an opened deck carries
 *  it. Idempotent; re-wraps a `fetch` someone replaced since. */
export function ensureDeckTransport(): void {
  const current = globalThis.fetch as typeof fetch & { [WRAPPED]?: true };
  if (typeof current !== "function" || current[WRAPPED]) return;
  const wrapped = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (init && init.body !== undefined && decks.size > 0) {
      const body = withDeckBody(init.body);
      if (body !== init.body) init = { ...init, body: body as BodyInit };
    }
    return current(input, init);
  }) as typeof fetch & { [WRAPPED]?: true };
  wrapped[WRAPPED] = true;
  globalThis.fetch = wrapped;
}
