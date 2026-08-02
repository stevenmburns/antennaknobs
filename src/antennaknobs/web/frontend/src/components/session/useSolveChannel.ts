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

// The /ws solve channel: the socket itself, the latest-wins `_seq` protocol,
// the busy-chrome dwell, and the two imperative entry points the component
// drives it with (#642 seam 5b-3). Lifted whole out of DesignSession so the
// per-socket `cutsSender` identity guard, the seq watermarks that must survive
// StrictMode/HMR teardown, and the literal `[active]` / `[solving]` dep arrays
// all move unchanged.
//
// `controlsRef` stays owned by the component: the solve effect writes the
// latest request into it and this hook only ever reads `.current`, so a
// reconnect resends whatever the component last decided to solve.
export function useSolveChannel({
  active,
  controlsRef,
  geometryRef,
  previewSigRef,
  setResult,
  setSolveError,
}: {
  active: boolean;
  controlsRef: MutableRefObject<SolveRequest>;
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

  // Cancel an IN-FLIGHT solve: stop waiting and discard its result. The server
  // keeps computing (its /ws loop is sequential and a running MoM solve can't be
  // interrupted), so this cancels the wait, not the computation.
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
  const BUSY_DWELL_MS = 1000;
  const BUSY_MIN_VISIBLE_MS = 400;
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
      const seq = ++seqRef.current;
      lastSentSeqRef.current = seq;
      sentAtRef.current.set(seq, performance.now());
      sock.send(JSON.stringify({ ...controlsRef.current, _seq: seq }));
      // Keep the preview signature current so that toggling Live *off* right
      // after a solve doesn't see a stale signature and needlessly refetch the
      // wireframe / drop the just-solved result — the solved geometry already
      // matches these controls.
      previewSigRef.current = JSON.stringify(controlsRef.current);
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
