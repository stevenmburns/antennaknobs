// Session pinning across a fleet of machines (AK#405).
//
// With more than one Fly machine, the edge routes each request to the
// nearest healthy one, and a page's requests need not share it. Three things
// assume they do: the lane rule (one solve at a time per session, held per
// machine), an opened deck's parse (cached in one machine's memory), and the
// per-machine limits. So the page pins itself to one machine:
//
// - On Fly every response says which machine answered (`X-AK-Machine`), and
//   the /ws channel's first message names its machine.
// - The /ws channel is the session's anchor: whatever machine it reached is
//   the pin (`noteChannelMachine`). Before it has spoken, the first HTTP
//   response's machine is adopted.
// - A pinned request carries `fly-force-instance-id`, which Fly's proxy
//   routes to that machine; a pinned /ws asks for it in its URL
//   (`?fly_instance=`), since a browser cannot set a WebSocket header, and
//   the server replays the upgrade there.
// - A pinned request that fails at the transport level (the fetch rejects,
//   or the proxy answers 502/503/504 with no machine header: the machine is
//   gone) drops the pin and is retried once unpinned; whichever machine
//   answers is adopted. A pinned /ws that never opens drops the pin too, so
//   its reconnect goes wherever the edge sends it and re-pins from there.
//
// Off Fly no response names a machine, so nothing is ever pinned: no header,
// no URL parameter, and every request is exactly what it was before.

export const MACHINE_HEADER = "x-ak-machine";
export const PIN_HEADER = "fly-force-instance-id";
export const WS_PIN_PARAM = "fly_instance";

let pinned: string | null = null;
const listeners = new Set<(pin: string | null) => void>();

function setPin(next: string | null): void {
  if (next === pinned) return;
  pinned = next;
  for (const l of [...listeners]) l(next);
}

/** The machine this page is pinned to, or null (always null off Fly). */
export function machinePin(): string | null {
  return pinned;
}

/** Called with the new pin whenever it changes. Returns the unsubscribe. */
export function onMachinePinChange(listener: (pin: string | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Test seam: forget the pin and every listener. */
export function resetMachinePin(): void {
  pinned = null;
  listeners.clear();
}

/** The /ws channel reached `id`: it is the session's machine. */
export function noteChannelMachine(id: unknown): void {
  if (typeof id === "string" && id) setPin(id);
}

/** A pinned /ws to `id` never opened: unless something re-pinned meanwhile,
 *  drop the pin so the reconnect goes wherever the edge sends it. */
export function dropFailedPin(id: string | null): void {
  if (id !== null && pinned === id) setPin(null);
}

/** The /ws URL for the current pin: `base` itself when unpinned. */
export function pinnedWsUrl(base: string): string {
  if (pinned === null) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}${WS_PIN_PARAM}=${encodeURIComponent(pinned)}`;
}

function answeringMachine(resp: Response | undefined): string | null {
  // Test doubles often carry no headers at all.
  const h = resp?.headers;
  const id = h && typeof h.get === "function" ? h.get(MACHINE_HEADER) : null;
  return id || null;
}

function isAbort(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    (err as { name?: unknown }).name === "AbortError"
  );
}

// A pinned request answered by the proxy rather than the app: the machine
// it was pinned to is gone (destroyed, or its region down).
function proxyFailure(resp: Response): boolean {
  return (
    (resp.status === 502 || resp.status === 503 || resp.status === 504) &&
    answeringMachine(resp) === null
  );
}

function adopt(resp: Response): Response {
  const id = answeringMachine(resp);
  if (id !== null && pinned === null) setPin(id);
  return resp;
}

function withPin(init: RequestInit | undefined, pin: string): RequestInit {
  const headers = new Headers(init?.headers);
  headers.set(PIN_HEADER, pin);
  return { ...init, headers };
}

// After a pinned request failed: the pin is dropped (unless something has
// re-pinned meanwhile, whose machine the retry then goes to), and the one
// retry adopts whichever machine answers it.
async function retry(input: string, init: RequestInit | undefined, failed: string) {
  if (pinned === failed) setPin(null);
  const now = pinned;
  if (now !== null) return fetch(input, withPin(init, now));
  return adopt(await plainFetch(input, init));
}

// Exactly the arguments the caller gave: no `undefined` second argument for
// a bare GET, so an unpinned call is indistinguishable from plain `fetch`.
function plainFetch(input: string, init: RequestInit | undefined): Promise<Response> {
  return init === undefined ? fetch(input) : fetch(input, init);
}

/** `fetch`, pinned to this page's machine when it has one (see the header).
 *  Unpinned, it calls `fetch(input, init)` with exactly the arguments given. */
export async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const pin = pinned;
  if (pin === null) return adopt(await plainFetch(input, init));
  let resp: Response;
  try {
    resp = await fetch(input, withPin(init, pin));
  } catch (err) {
    if (isAbort(err) || init?.signal?.aborted) throw err;
    return retry(input, init, pin);
  }
  return proxyFailure(resp) ? retry(input, init, pin) : resp;
}
