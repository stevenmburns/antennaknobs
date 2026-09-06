import {
  useEffect,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import type { SolveRequest, SolveResponse } from "../../lib/api";
import {
  cutsWsSend,
  flushCutsWsPending,
  resolveCutsWsMessage,
  setCutsWsSend,
  type CutsWsMessage,
} from "../charts/cuts";

// Match the page's scheme: a wss:// upgrade is required on HTTPS pages (e.g. the
// deployed site behind Fly's force_https), where browsers block insecure ws://
// as mixed content. Plain ws:// only works on http:// (local dev).
const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;

// Busy-chrome reveal thresholds (see the effect below). Module scope, not
// component scope: they're literal constants that never change between
// renders, so hoisting them out of the hook body — rather than adding them
// to the effect's dep array — is a no-op for behavior and lets
// react-hooks/exhaustive-deps see the effect's dependencies as complete
// (#736).
const BUSY_DWELL_MS = 1000;
const BUSY_MIN_VISIBLE_MS = 400;

// The /ws solve channel: the socket itself, the latest-wins `_seq` protocol,
// the busy-chrome dwell, and the two imperative entry points the component
// drives it with (#642 seam 5b-3). Lifted whole out of DesignSession so the
// per-socket `cutsSender` identity guard, the seq watermarks that must survive
// StrictMode/HMR teardown, and the literal `[active]` / `[solving]` dep arrays
// all move unchanged.
//
// `controlsRef` stays owned by the component: the solve effect writes the
// latest request into it and this hook only ever reads `.current`, so a
// reconnect resends whatever the component last decided to solve. It is null
// until the component has decided anything (issue #768) — a send with nothing
// to send is deferred, not faked.
export function useSolveChannel({
  active,
  controlsRef,
  withheldRef,
  geometryRef,
  previewSigRef,
  setResult,
  setSolveError,
}: {
  active: boolean;
  controlsRef: MutableRefObject<SolveRequest | null>;
  /** Is a solve currently REFUSED? Checked at SEND time, not only when a send
   *  is scheduled (#1006 review).
   *
   *  Sending is deferred to the next animation frame to coalesce knob drags,
   *  and `onopen` resends on reconnect — so between deciding to solve and
   *  actually solving, the design can change under the request. A browser
   *  trace of the switch-design path showed exactly that window: the gate
   *  fired, was cleared a tick later, and a refused solve went out ~24 ms
   *  after being scheduled.
   *
   *  A ref rather than a value because this hook's senders are closures
   *  captured per socket; a value would be the one from whichever render
   *  created them. */
  withheldRef: MutableRefObject<boolean>;
  geometryRef: MutableRefObject<string>;
  previewSigRef: MutableRefObject<string | null>;
  setResult: (r: SolveResponse | null) => void;
  setSolveError: (e: string | null) => void;
}) {
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [rttMs, setRttMs] = useState<number | null>(null);
  // True whenever a main solve is outstanding (in flight or queued) — i.e. the
  // displayed analysis isn't current yet. `showBusy` is the *debounced* view of
  // it: the progress bar / panel dimming only appear once a solve outlasts
  // ~300 ms, so fast updates (cache hits, small designs) snap in cleanly
  // without a flash of busy chrome.
  const [solving, setSolving] = useState(false);
  const [showBusy, setShowBusy] = useState(false);

  // Timestamp (performance.now) when the busy chrome last became visible, so
  // the reveal effect can enforce a minimum-visible window. null = not shown.
  const shownAtRef = useRef<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  // Latest-wins /ws protocol counters. Every knob change is sent eagerly with a
  // monotonic `_seq`; the server keeps only the freshest queued request and may
  // skip-send superseded results, so the client orders and prunes by `_seq`. A
  // solve is outstanding iff more has been sent than received. These live in
  // refs so they survive StrictMode/HMR socket teardown — the counter must
  // never rewind below what's already been received.
  const seqRef = useRef(0); // last _seq assigned (monotonic, never reset)
  const lastSentSeqRef = useRef(0); // highest _seq put on the wire
  const lastReceivedSeqRef = useRef(0); // highest _seq received or implicitly acked
  const canceledThroughSeqRef = useRef(0); // drop rendering for _seq <= this
  const sentAtRef = useRef<Map<number, number>>(new Map()); // _seq → send time (RTT)
  const solveRafRef = useRef<number | null>(null); // trailing-edge rAF throttle handle

  // Cancel an IN-FLIGHT solve: stop waiting and discard its result. Purely
  // client-side — nothing goes on the wire — so the server does keep computing
  // *this* one and it cancels the wait, not the computation.
  //
  // The old reason given here, that "a running MoM solve can't be interrupted",
  // is not true: the server's /ws reader trips a cancel token the moment a NEWER
  // request lands (or the socket closes), and the engine polls it at phase
  // boundaries and solver-internal seams, so a fresh knob change really does
  // preempt the solve in flight. A bare cancel doesn't, only because it sends no
  // newer request to trigger that.
  function cancelSolve() {
    if (lastSentSeqRef.current <= lastReceivedSeqRef.current) return; // nothing in flight
    // Mark every seq sent so far as cancelled: onmessage will advance the
    // received watermark for these but drop their results. A newer knob change
    // bumps lastSentSeq past this and solves again.
    canceledThroughSeqRef.current = lastSentSeqRef.current;
    syncSolving();
  }

  // Mirror the seq counters into `solving` state so the UI can react. Called
  // wherever the sent / received / cancel watermarks move. A solve reads as
  // running when more has been sent than received — unless everything
  // outstanding was cancelled (lastSentSeq hasn't advanced past the cancel
  // watermark), in which case the wait is over even though a doomed response
  // is still coming.
  function syncSolving() {
    setSolving(
      lastSentSeqRef.current > lastReceivedSeqRef.current &&
        lastSentSeqRef.current > canceledThroughSeqRef.current,
    );
  }

  // Busy-chrome reveal with two guards:
  //  - dwell: only show once a solve has been outstanding >BUSY_DWELL_MS. 1 s
  //    is the classic "flow of thought" threshold — below it users tolerate the
  //    wait without feedback; at/above it the bar reassures them it's working.
  //    A solve that finishes sooner clears the timer in cleanup, so the bar
  //    never flips on for quick updates.
  //  - min-visible: once shown, keep it up at least BUSY_MIN_VISIBLE_MS so a
  //    solve that lands just past the dwell can't make it sub-perceptibly
  //    flash.
  useEffect(() => {
    if (solving) {
      const t = window.setTimeout(() => {
        shownAtRef.current = performance.now();
        setShowBusy(true);
      }, BUSY_DWELL_MS);
      return () => window.clearTimeout(t);
    }
    // Solve finished. If the bar never showed (fast solve), hide immediately;
    // otherwise hold it for the remainder of the minimum-visible window.
    if (shownAtRef.current === null) {
      setShowBusy(false);
      return;
    }
    const remaining =
      BUSY_MIN_VISIBLE_MS - (performance.now() - shownAtRef.current);
    if (remaining <= 0) {
      shownAtRef.current = null;
      setShowBusy(false);
      return;
    }
    const t = window.setTimeout(() => {
      shownAtRef.current = null;
      setShowBusy(false);
    }, remaining);
    return () => window.clearTimeout(t);
  }, [solving]);

  // The progress bar (`showBusy`) honors the min-visible window so it can't
  // flash, but the *dimming* and the "solving…" label mean "what you're
  // looking at is stale" — so they must clear the instant the result lands,
  // even while the bar lingers out its minimum. `solving` flips false
  // immediately on result-land, so `showBusy && solving` is exactly that: dim
  // only after the dwell (showBusy) AND while genuinely still solving.
  const stale = showBusy && solving;

  function requestSolve() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Can't send now. onopen resends controlsRef.current on (re)connect, so
      // the latest state is solved as soon as the socket comes up.
      return;
    }
    // Trailing-edge rAF throttle: coalesce a burst of knob changes within one
    // animation frame to a single send of the latest controls. Bounds upload to
    // ≤~60 msg/s during a drag and keeps localhost message churn near what the
    // old one-in-flight gate produced; the server's latest-wins mailbox squashes
    // whatever still piles up. The freshest value always wins within the frame.
    if (solveRafRef.current !== null) return;
    solveRafRef.current = requestAnimationFrame(() => {
      solveRafRef.current = null;
      const sock = wsRef.current;
      if (!sock || sock.readyState !== WebSocket.OPEN) return;
      // Nothing decided to solve yet (issue #768). onopen calls requestSolve
      // unconditionally, and on a first connect it can win the race against
      // the solve effect that fills this — so deferring here is the same
      // "can't send now" the closed-socket branch above takes, not a new
      // failure mode: the solve effect sends as soon as it has a request.
      const controls = controlsRef.current;
      if (!controls) return;
      // REVALIDATE AT THE MOMENT OF SENDING. The decision to solve was made
      // when this frame was scheduled; the design may have changed since, and
      // a refusal that lands in that gap must win.
      if (withheldRef.current) return;
      const seq = ++seqRef.current;
      lastSentSeqRef.current = seq;
      sentAtRef.current.set(seq, performance.now());
      sock.send(JSON.stringify({ ...controls, _seq: seq }));
      // Keep the preview signature current so that toggling Live *off* right
      // after a solve doesn't see a stale signature and needlessly refetch the
      // wireframe / drop the just-solved result — the solved geometry already
      // matches these controls.
      previewSigRef.current = JSON.stringify(controls);
      syncSolving();
    });
  }

  useEffect(() => {
    if (!active) return;
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    // This socket's cuts sender (issue #551). A stable identity per socket
    // so the close/cleanup handlers only deregister their OWN sender — a
    // stale socket's late onclose must not tear down the transport a newer
    // socket just registered.
    const cutsSender = (msg: string): boolean => {
      if (ws.readyState !== WebSocket.OPEN) return false;
      ws.send(msg);
      return true;
    };
    const dropCutsSender = () => {
      if (cutsWsSend === cutsSender) setCutsWsSend(null);
      flushCutsWsPending();
    };
    ws.onopen = () => {
      setStatus("open");
      setCutsWsSend(cutsSender);
      // A prior socket's in-flight responses can never arrive on this new one.
      // Treat everything sent so far as received so `solving` can't stick true,
      // drop stale RTT timers, then send fresh current state. StrictMode and HMR
      // both tear the socket down + recreate it; the seq counters survive in
      // refs, so they must never rewind below what's already been received.
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      sentAtRef.current.clear();
      // Deliberately unguarded: `requestSolve` schedules the same frame the
      // send-time check below guards, so a reconnect while refused schedules
      // a frame that then declines to send. A second check here would be
      // unreachable — mutating it away leaves every test green — and one gate
      // at the boundary is easier to reason about than two that must agree.
      requestSolve();
    };
    ws.onclose = () => {
      setStatus("closed");
      dropCutsSender();
      // No solve can progress while disconnected — collapse the outstanding
      // count so the busy bar can't spin under a "closed" status (reconnect
      // re-arms it via onopen).
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onerror = () => {
      setStatus("closed");
      dropCutsSender();
      lastReceivedSeqRef.current = lastSentSeqRef.current;
      setSolving(false);
    };
    ws.onmessage = (ev) => {
      const data: SolveResponse & Partial<CutsWsMessage> = JSON.parse(ev.data);
      if (data._kind === "cuts") {
        // Cuts sidecar response (issue #551) — never a solve; route it
        // before any _seq/solving bookkeeping.
        resolveCutsWsMessage(data as CutsWsMessage);
        return;
      }
      const seq = data._seq ?? 0;
      // One socket delivers in order, and the server may skip-send superseded
      // results — so a higher `_seq` implicitly acknowledges every lower one.
      // Ignore a straggler/duplicate at or below the received watermark.
      if (seq <= lastReceivedSeqRef.current) {
        syncSolving();
        return;
      }
      lastReceivedSeqRef.current = seq;
      // RTT from this seq's send; prune every acked entry (≤ seq) from the map —
      // seqs skipped server-side never get their own response, so a single
      // higher-seq arrival clears the whole run of them.
      const sentAt = sentAtRef.current;
      const t0 = sentAt.get(seq);
      if (t0 !== undefined) setRttMs(performance.now() - t0);
      for (const k of sentAt.keys()) {
        if (k <= seq) sentAt.delete(k);
      }
      // Cancelled through this seq: the user bailed on it (and everything
      // before). The watermark advanced above so `solving` can clear; just drop
      // the result rather than rendering it.
      if (seq <= canceledThroughSeqRef.current) {
        syncSolving();
        return;
      }
      // Drop a response for an antenna the user already switched away from: a
      // slow in-flight solve for the previous selection must not stomp the new
      // antenna's geometry preview (and briefly show the wrong antenna).
      const staleGeom = !!data.geometry && data.geometry !== geometryRef.current;
      if (!staleGeom) {
        if (data.error) {
          // A solve that raised (e.g. a user design's build_wires) — show the
          // message and clear stale plot data rather than rendering an empty
          // result on top of the last antenna.
          setSolveError(data.error);
          setResult(null);
        } else {
          setSolveError(null);
          setResult(data);
        }
      }
      syncSolving();
    };
    return () => {
      if (solveRafRef.current !== null) {
        cancelAnimationFrame(solveRafRef.current);
        solveRafRef.current = null;
      }
      dropCutsSender(); // ws.close() fires onclose async; don't leave a dead sender up
      ws.close();
    };
    // Deliberately scoped to [active] alone — the socket's lifecycle, not the
    // request state. geometryRef/controlsRef/previewSigRef are refs (read via
    // .current for whatever is freshest when the callback fires, never to
    // react to identity); setResult/setSolveError are the parent's useState
    // setters, stable for the session; requestSolve is a plain, unmemoized
    // closure but only ever touches refs and setState setters itself, so a
    // "stale" closure from an earlier render behaves identically to a fresh
    // one. Reconnecting the WebSocket on every knob change (which listing any
    // of these would cause) would drop every in-flight solve.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return {
    status,
    rttMs,
    solving,
    showBusy,
    stale,
    requestSolve,
    cancelSolve,
    seqRef,
  };
}
