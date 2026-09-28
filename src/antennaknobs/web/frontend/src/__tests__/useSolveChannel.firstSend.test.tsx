// The send path's one precondition (issue #768): `controlsRef` is null until
// the component decides what to solve, and a send it cannot fill is DEFERRED
// rather than faked.
//
// This became reachable when controlsRef stopped being seeded with an eager
// `useRef(buildRequest())` — that spelling rebuilt a whole SolveRequest on
// every render to discard it. The seed also meant `onopen` had something to
// send even when the solve effect had deliberately withheld a solve (an
// antenna switch whose preview has not landed), so removing it makes the
// gate authoritative. Nothing else in the suite drives the socket: the
// DesignSession harness mounts with an InertWebSocket that never opens.
import { renderHook, act } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import {
  RECONNECT_BASE_MS,
  RECONNECT_MAX_MS,
  useSolveChannel,
} from "../components/session/useSolveChannel";
import type { SolveRequest } from "../lib/api";

class FakeWebSocket {
  static OPEN = 1;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  static last: FakeWebSocket | null = null;
  constructor() {
    FakeWebSocket.last = this;
  }
  send(payload: string) {
    this.sent.push(payload);
  }
  close() {}
  /** What the browser does when the server accepts the connection. */
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
}

// requestSolve coalesces a burst into one send per animation frame. The stub
// QUEUES the callback and returns a handle, rather than running it inline:
// requestSolve stores that handle as its throttle flag, so a stub that ran the
// callback first would let the callback's own `= null` be overwritten by the
// returned handle and wedge the throttle shut for every later send. Real rAF
// never does that; running frames explicitly keeps the test honest about it.
const frames: FrameRequestCallback[] = [];
const flushFrame = () => {
  const pending = frames.splice(0);
  pending.forEach((cb) => cb(0));
};
const realRaf = globalThis.requestAnimationFrame;
const realWs = globalThis.WebSocket;

const withheldRef = { current: false };

function mount(
  controlsRef: { current: SolveRequest | null },
  withheld: { current: boolean } = withheldRef,
) {
  return renderHook(() =>
    useSolveChannel({
      active: true,
      controlsRef,
      withheldRef: withheld,
      geometryRef: { current: "dipoles.probe" },
      previewSigRef: { current: null },
      setResult: () => {},
      setSolveError: () => {},
    }),
  );
}

describe("useSolveChannel first send", () => {
  beforeEach(() => {
    FakeWebSocket.last = null;
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    frames.length = 0;
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      frames.push(cb)) as typeof requestAnimationFrame;
  });

  afterEach(() => {
    globalThis.WebSocket = realWs;
    globalThis.requestAnimationFrame = realRaf;
    vi.restoreAllMocks();
  });

  it("sends nothing when the socket opens before anything is decided", () => {
    const controlsRef: { current: SolveRequest | null } = { current: null };
    mount(controlsRef);

    // onopen calls requestSolve unconditionally. With nothing decided there is
    // no request to send, and inventing one would solve a design the component
    // is deliberately holding back.
    act(() => FakeWebSocket.last!.open());
    act(() => flushFrame());

    expect(FakeWebSocket.last!.sent).toEqual([]);
  });

  it("sends once a request has been decided, and stamps it with a seq", () => {
    const controlsRef: { current: SolveRequest | null } = { current: null };
    const { result } = mount(controlsRef);
    act(() => FakeWebSocket.last!.open());
    act(() => flushFrame()); // the onopen send, deferred — nothing decided yet

    controlsRef.current = { geometry: "dipoles.probe" } as SolveRequest;
    act(() => result.current.requestSolve());
    act(() => flushFrame());

    expect(FakeWebSocket.last!.sent).toHaveLength(1);
    const payload = JSON.parse(FakeWebSocket.last!.sent[0]);
    expect(payload.geometry).toBe("dipoles.probe");
    // The latest-wins protocol is what the deferral must not disturb: a
    // deferred send must not burn a sequence number, or the watermark would
    // run ahead of what was actually put on the wire.
    expect(payload._seq).toBe(1);
  });
});

// --------------------------------------------------------------------------
// A refusal that lands between scheduling and sending must win
// --------------------------------------------------------------------------
//
// Sending is deferred to the next animation frame so a knob drag coalesces to
// one message. The decision to solve is therefore made at SCHEDULE time and
// the send happens later — and in that gap the design can change under the
// request. A browser trace of the switch-design path showed the gate fire, be
// cleared a tick later, and a refused solve go out ~24 ms after scheduling.
//
// The frames array here is the whole point: it holds the callback so the test
// can decide what happens BEFORE the frame runs, which is the window that
// cannot be reached by asserting on rendered output.

describe("a refusal between scheduling and sending", () => {
  beforeEach(() => {
    FakeWebSocket.last = null;
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    frames.length = 0;
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      frames.push(cb)) as typeof requestAnimationFrame;
  });
  afterEach(() => {
    globalThis.WebSocket = realWs;
    globalThis.requestAnimationFrame = realRaf;
  });

  it("does not send when the solve is refused after the frame is scheduled", () => {
    const controlsRef = {
      current: { geometry: "x" } as unknown as SolveRequest,
    };
    const withheld = { current: false };
    const { result } = mount(controlsRef, withheld);
    FakeWebSocket.last!.open();

    result.current.requestSolve();
    expect(frames).toHaveLength(1);

    // The gate fires in the gap — exactly what the browser trace showed.
    withheld.current = true;
    frames.forEach((f) => f(0));

    expect(FakeWebSocket.last!.sent).toHaveLength(0);
  });

  it("still sends when nothing refused it", () => {
    // The other half: without this, "never send" would satisfy the test above
    // and the app would simply stop solving.
    const controlsRef = {
      current: { geometry: "x" } as unknown as SolveRequest,
    };
    const withheld = { current: false };
    const { result } = mount(controlsRef, withheld);
    FakeWebSocket.last!.open();

    result.current.requestSolve();
    frames.forEach((f) => f(0));

    expect(FakeWebSocket.last!.sent).toHaveLength(1);
  });

  it("does not resend on reconnect while refused", () => {
    // `onopen` resends the current request unconditionally. A reconnect must
    // not become the thing that fires a solve the gate already turned down.
    const controlsRef = {
      current: { geometry: "x" } as unknown as SolveRequest,
    };
    const withheld = { current: true };
    mount(controlsRef, withheld);
    FakeWebSocket.last!.open();
    frames.forEach((f) => f(0));
    expect(FakeWebSocket.last!.sent).toHaveLength(0);
  });
});

// --------------------------------------------------------------------------
// Cancel reaches the server (AK#1712)
// --------------------------------------------------------------------------
//
// "Cancel solve" used to be purely client-side: it dropped the result and
// sent nothing, so the server ran a cold Sommerfeld fill to completion many
// minutes after the button. The server can only stop what it is told about.

describe("cancelSolve", () => {
  beforeEach(() => {
    FakeWebSocket.last = null;
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket;
    frames.length = 0;
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      frames.push(cb)) as typeof requestAnimationFrame;
  });
  afterEach(() => {
    globalThis.WebSocket = realWs;
    globalThis.requestAnimationFrame = realRaf;
  });

  it("sends a session cancel with a fresh generation", () => {
    const controlsRef = {
      current: { geometry: "x", _session: "tab-1" } as unknown as SolveRequest,
    };
    const { result } = mount(controlsRef);
    act(() => FakeWebSocket.last!.open());
    act(() => flushFrame()); // the onopen send: seq 1, in flight
    expect(result.current.solving).toBe(true);

    act(() => result.current.cancelSolve());

    const sent = FakeWebSocket.last!.sent.map((m) => JSON.parse(m));
    expect(sent).toHaveLength(2);
    expect(sent[1]).toEqual({ _kind: "cancel", _session: "tab-1", _seq: 2 });
    // The client stops waiting at once, as before.
    expect(result.current.solving).toBe(false);

    // The next solve is newer than the cancel, so the server's lane (whose
    // generation the cancel advanced) runs it rather than calling it stale.
    act(() => result.current.requestSolve());
    act(() => flushFrame());
    const next = JSON.parse(FakeWebSocket.last!.sent[2]);
    expect(next._seq).toBe(3);
    expect(result.current.solving).toBe(true);
  });
});

// --------------------------------------------------------------------------
// A dropped socket reconnects, and the gap is marked stale (AK#1783)
// --------------------------------------------------------------------------
//
// Before: onclose set "closed" and stopped. Nothing re-created the socket, so
// on the hosted app a drop left the page drawing its last result against
// knobs the server never saw, until a reload (Steve's folded inverted vee: the
// Z-vs-parameter dots sat at length_factor 0.955 while the knob read 1.007).

describe("reconnect after a drop", () => {
  const sockets: FakeWebSocket[] = [];
  beforeEach(() => {
    sockets.length = 0;
    FakeWebSocket.last = null;
    class Tracked extends FakeWebSocket {
      constructor() {
        super();
        sockets.push(this);
      }
    }
    globalThis.WebSocket = Tracked as unknown as typeof WebSocket;
    frames.length = 0;
    globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      frames.push(cb)) as typeof requestAnimationFrame;
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  });
  afterEach(() => {
    vi.useRealTimers();
    globalThis.WebSocket = realWs;
    globalThis.requestAnimationFrame = realRaf;
  });

  const drop = (ws: FakeWebSocket) => {
    ws.readyState = 3;
    // A failed socket fires both; the second must not schedule a second retry.
    ws.onerror?.();
    ws.onclose?.();
  };

  it("opens a new socket after the backoff, and resends the latest controls", () => {
    const controlsRef = {
      current: { geometry: "x" } as unknown as SolveRequest,
    };
    const { result } = mount(controlsRef);
    act(() => sockets[0].open());
    act(() => flushFrame());
    expect(sockets[0].sent).toHaveLength(1);

    act(() => drop(sockets[0]));
    expect(result.current.status).toBe("closed");
    expect(sockets).toHaveLength(1);

    // The knob moves while the socket is down: nothing can be sent.
    controlsRef.current = {
      geometry: "x",
      length_factor: 1.007,
    } as unknown as SolveRequest;
    act(() => result.current.requestSolve());
    expect(result.current.waiting).toBe(true);
    expect(result.current.stale).toBe(true);

    act(() => vi.advanceTimersByTime(RECONNECT_BASE_MS - 1));
    expect(sockets).toHaveLength(1);
    act(() => vi.advanceTimersByTime(1));
    expect(sockets).toHaveLength(2); // exactly one retry, though both events fired

    act(() => sockets[1].open());
    act(() => flushFrame());
    expect(result.current.status).toBe("open");
    expect(result.current.waiting).toBe(false);
    const resent = JSON.parse(sockets[1].sent[0]);
    expect(resent.length_factor).toBe(1.007);
  });

  it("backs off, doubling to the cap, and resets once a socket opens", () => {
    mount({ current: { geometry: "x" } as unknown as SolveRequest });
    act(() => sockets[0].open());
    const waits: number[] = [];
    for (let i = 0; i < 7; i++) {
      const n = sockets.length;
      act(() => drop(sockets[n - 1]));
      let t = 0;
      while (sockets.length === n) {
        act(() => vi.advanceTimersByTime(100));
        t += 100;
      }
      waits.push(t);
    }
    expect(waits).toEqual([
      500,
      1000,
      2000,
      4000,
      8000,
      RECONNECT_MAX_MS,
      RECONNECT_MAX_MS,
    ]);

    act(() => sockets[sockets.length - 1].open());
    const n = sockets.length;
    act(() => drop(sockets[n - 1]));
    act(() => vi.advanceTimersByTime(RECONNECT_BASE_MS));
    expect(sockets).toHaveLength(n + 1);
  });

  it("a solve in flight when the socket drops leaves the page waiting", () => {
    const { result } = mount({
      current: { geometry: "x" } as unknown as SolveRequest,
    });
    act(() => sockets[0].open());
    act(() => flushFrame()); // seq 1 in flight
    act(() => drop(sockets[0]));
    expect(result.current.solving).toBe(false);
    expect(result.current.waiting).toBe(true);
  });

  it("a drop with nothing outstanding is not stale: the result is still current", () => {
    const { result } = mount({
      current: { geometry: "x" } as unknown as SolveRequest,
    });
    act(() => sockets[0].open());
    act(() => flushFrame());
    act(() =>
      sockets[0].onmessage?.({
        data: JSON.stringify({ _seq: 1, geometry: "dipoles.probe" }),
      } as MessageEvent),
    );
    act(() => drop(sockets[0]));
    expect(result.current.waiting).toBe(false);
    expect(result.current.stale).toBe(false);
  });

  it("unmounting closes the socket and schedules no reconnect", () => {
    const { unmount } = mount({
      current: { geometry: "x" } as unknown as SolveRequest,
    });
    act(() => sockets[0].open());
    unmount();
    act(() => drop(sockets[0])); // the browser's async onclose after close()
    act(() => vi.advanceTimersByTime(RECONNECT_MAX_MS * 2));
    expect(sockets).toHaveLength(1);
  });
});
