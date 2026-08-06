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
import { useSolveChannel } from "../components/session/useSolveChannel";
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

function mount(controlsRef: { current: SolveRequest | null }) {
  return renderHook(() =>
    useSolveChannel({
      active: true,
      controlsRef,
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
