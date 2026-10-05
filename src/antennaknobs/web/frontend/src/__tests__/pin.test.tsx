// Session pinning across a fleet of machines (AK#405).
//
// Off Fly nothing is pinned and every request is exactly what it was before.
// On Fly the page pins to one machine: an opened deck's /deck, its /ws live
// solves and its /param_sweep must all reach the machine that holds the
// deck's parse and the session's lane; a machine that goes away drops the pin
// and the page re-pins wherever its retry lands.
import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  apiFetch,
  dropFailedPin,
  machinePin,
  noteChannelMachine,
  PIN_HEADER,
  pinnedWsUrl,
  resetMachinePin,
} from "../lib/pin";
import { useSolveChannel } from "../components/session/useSolveChannel";

type Seen = { url: string; init?: RequestInit | undefined; args: number; machine: string };

function headerOf(init: RequestInit | undefined, name: string): string | null {
  return init?.headers ? new Headers(init.headers).get(name) : null;
}

// A two-machine fleet behind a simulated Fly edge. Unpinned requests spill
// between machines (alternating, as a saturated nearest machine does); a
// pinned one goes where `fly-force-instance-id` says, and to a destroyed
// machine it fails at the transport level, as the browser sees a dead route.
// Each machine keeps its own opened-deck cache, as the server does.
function fleet(ids: string[]) {
  const alive = new Set(ids);
  const decks: Record<string, Set<string>> = Object.fromEntries(ids.map((m) => [m, new Set()]));
  const seen: Seen[] = [];
  let spill = 0;
  const fetchStub = vi.fn(async (...a: [string, RequestInit?]) => {
    const [url, init] = a;
    const forced = headerOf(init, PIN_HEADER);
    let machine: string;
    if (forced !== null) {
      if (!alive.has(forced)) throw new TypeError("Failed to fetch");
      machine = forced;
    } else {
      const up = ids.filter((m) => alive.has(m));
      machine = up[spill++ % up.length];
    }
    seen.push({ url, init, args: a.length, machine });
    let status = 200;
    if (url === "/deck") decks[machine].add("deck.0123456789ab");
    if (url === "/param_sweep" && !decks[machine].has("deck.0123456789ab")) status = 409;
    return new Response("{}", { status, headers: { "x-ak-machine": machine } });
  });
  vi.stubGlobal("fetch", fetchStub);
  return { seen, destroy: (m: string) => alive.delete(m) };
}

beforeEach(() => {
  resetMachinePin();
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetMachinePin();
});

describe("off Fly", () => {
  it("never pins, and calls fetch with exactly the caller's arguments", async () => {
    const stub = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", stub);
    await apiFetch("/examples");
    const init = { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" };
    await apiFetch("/sweep", init);
    expect(stub.mock.calls[0]).toEqual(["/examples"]);
    expect(stub.mock.calls[1][0]).toBe("/sweep");
    expect(stub.mock.calls[1][1]).toBe(init); // the same object, untouched
    expect(machinePin()).toBeNull();
    expect(pinnedWsUrl("ws://localhost:8000/ws")).toBe("ws://localhost:8000/ws");
  });

  it("tolerates a response with no headers at all (test doubles)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true }) as unknown as Response));
    await apiFetch("/examples");
    expect(machinePin()).toBeNull();
  });
});

describe("on a two-machine fleet", () => {
  it("an opened deck's /deck, the channel's machine and /param_sweep all reach one machine", async () => {
    const f = fleet(["a1", "b2"]);
    // Page load: the first answer pins the page.
    await apiFetch("/capabilities");
    expect(machinePin()).toBe("a1");
    // Every later request is forced there, however the edge would spill it.
    await apiFetch("/examples");
    await apiFetch("/deck", { method: "POST", body: "{}" });
    expect(pinnedWsUrl("wss://app/ws")).toBe("wss://app/ws?fly_instance=a1");
    const sweep = await apiFetch("/param_sweep", { method: "POST", body: "{}" });
    expect(sweep.status).toBe(200); // the deck's parse is on this machine
    expect(f.seen.map((s) => s.machine)).toEqual(["a1", "a1", "a1", "a1"]);
    expect(f.seen.slice(1).every((s) => headerOf(s.init, PIN_HEADER) === "a1")).toBe(true);
  });

  it("the live channel's machine is the session's: HTTP follows it", async () => {
    const f = fleet(["a1", "b2"]);
    await apiFetch("/capabilities"); // a1 answered first...
    noteChannelMachine("b2"); // ...but the unpinned /ws landed on b2
    await apiFetch("/deck", { method: "POST", body: "{}" });
    await apiFetch("/param_sweep", { method: "POST", body: "{}" });
    expect(f.seen.slice(1).map((s) => s.machine)).toEqual(["b2", "b2"]);
  });

  it("a destroyed machine: the request retries unpinned and the page re-pins", async () => {
    const f = fleet(["a1", "b2"]);
    await apiFetch("/capabilities");
    expect(machinePin()).toBe("a1");
    f.destroy("a1");
    const r = await apiFetch("/deck", { method: "POST", body: "{}" });
    expect(r.status).toBe(200);
    expect(machinePin()).toBe("b2");
    // The retry went out unpinned; everything after is pinned to b2, where
    // the deck was re-opened, so the sweep finds it.
    const retry = f.seen[f.seen.length - 1];
    expect(headerOf(retry.init, PIN_HEADER)).toBeNull();
    const sweep = await apiFetch("/param_sweep", { method: "POST", body: "{}" });
    expect(sweep.status).toBe(200);
    expect(f.seen[f.seen.length - 1].machine).toBe("b2");
  });

  it("a proxy error with no machine header is a gone machine too", async () => {
    resetMachinePin();
    noteChannelMachine("a1");
    const stub = vi
      .fn()
      .mockResolvedValueOnce(new Response("no route", { status: 502 }))
      .mockResolvedValueOnce(new Response("{}", { status: 200, headers: { "x-ak-machine": "b2" } }));
    vi.stubGlobal("fetch", stub);
    const r = await apiFetch("/sweep", { method: "POST" });
    expect(r.status).toBe(200);
    expect(stub).toHaveBeenCalledTimes(2);
    expect(machinePin()).toBe("b2");
  });

  it("the app's own 503 (a busy deck slot) is an answer, not a failover", async () => {
    noteChannelMachine("a1");
    const stub = vi.fn(
      async () => new Response("{}", { status: 503, headers: { "x-ak-machine": "a1" } }),
    );
    vi.stubGlobal("fetch", stub);
    const r = await apiFetch("/sweep", { method: "POST" });
    expect(r.status).toBe(503);
    expect(stub).toHaveBeenCalledTimes(1);
    expect(machinePin()).toBe("a1");
  });

  it("an abort is the caller's, never retried", async () => {
    noteChannelMachine("a1");
    const stub = vi.fn(async () => {
      throw new DOMException("aborted", "AbortError");
    });
    vi.stubGlobal("fetch", stub);
    await expect(apiFetch("/sweep", { method: "POST" })).rejects.toThrow("aborted");
    expect(stub).toHaveBeenCalledTimes(1);
    expect(machinePin()).toBe("a1");
  });

  it("a failed channel drops only the pin it tried", () => {
    noteChannelMachine("a1");
    dropFailedPin("zz");
    expect(machinePin()).toBe("a1");
    dropFailedPin("a1");
    expect(machinePin()).toBeNull();
  });
});

// The /ws side, through the real hook with a fake socket.
class FakeWebSocket {
  static OPEN = 1;
  static all: FakeWebSocket[] = [];
  readyState = 0;
  url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeWebSocket.all.push(this);
  }
  send() {}
  close() {
    this.closed = true;
    this.onclose?.();
  }
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  message(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}

describe("the /ws channel", () => {
  const realWs = globalThis.WebSocket;
  beforeEach(() => {
    FakeWebSocket.all = [];
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    vi.useFakeTimers();
  });
  afterEach(() => {
    globalThis.WebSocket = realWs;
    vi.useRealTimers();
  });

  function mount() {
    return renderHook(() =>
      useSolveChannel({
        active: true,
        controlsRef: { current: null },
        withheldRef: { current: false },
        geometryRef: { current: "dipoles.probe" },
        previewSigRef: { current: null },
        setResult: () => {},
        setSolveError: () => {},
      }),
    );
  }

  it("off Fly: the plain URL, and no message changes anything", () => {
    mount();
    const ws = FakeWebSocket.all[0];
    expect(ws.url).toMatch(/\/ws$/);
    act(() => ws.open());
    expect(machinePin()).toBeNull();
  });

  it("its first message pins the page; a reconnect asks for that machine", () => {
    mount();
    const first = FakeWebSocket.all[0];
    act(() => {
      first.open();
      first.message({ _kind: "machine", id: "a1" });
    });
    expect(machinePin()).toBe("a1");
    act(() => first.close());
    act(() => vi.advanceTimersByTime(600));
    const second = FakeWebSocket.all[1];
    expect(second.url).toMatch(/\/ws\?fly_instance=a1$/);
  });

  it("a pinned socket that never opens drops the pin; the next goes unpinned", () => {
    noteChannelMachine("a1");
    mount();
    const pinnedTry = FakeWebSocket.all[0];
    expect(pinnedTry.url).toMatch(/fly_instance=a1$/);
    act(() => pinnedTry.onerror?.());
    expect(machinePin()).toBeNull();
    act(() => vi.advanceTimersByTime(600));
    const next = FakeWebSocket.all[1];
    expect(next.url).toMatch(/\/ws$/);
    act(() => {
      next.open();
      next.message({ _kind: "machine", id: "b2" });
    });
    expect(machinePin()).toBe("b2");
  });

  it("re-pinned elsewhere by a failed-over request, the socket follows", async () => {
    mount();
    const first = FakeWebSocket.all[0];
    act(() => {
      first.open();
      first.message({ _kind: "machine", id: "a1" });
    });
    // An HTTP request to a1 fails at the transport; its retry lands on b2.
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce(new Response("{}", { headers: { "x-ak-machine": "b2" } })),
    );
    await act(async () => {
      await apiFetch("/param_sweep", { method: "POST" });
    });
    expect(machinePin()).toBe("b2");
    expect(first.closed).toBe(true);
    act(() => vi.advanceTimersByTime(600));
    expect(FakeWebSocket.all[1].url).toMatch(/fly_instance=b2$/);
  });
});
