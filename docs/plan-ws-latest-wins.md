# Plan: eager-send + server-side latest-wins squash for the /ws solve pipeline

Status: **not started.** Scoped 2026-07-04 from an audit of the stale-knob
squashing mechanisms. Goal: cut the tail latency of a knob change → rendered
charts on the hosted (fly.io) instance, where client↔server RTT is real
(~tens of ms), without regressing the localhost path (RTT ≈ 0).

## Motivation — what the audit found

Today the client enforces **one in-flight request + a latest-wins pending
slot** (`web/frontend/src/App.tsx:3326-3340`, refs at `App.tsx:2371-2372`).
The server `/ws` loop is strictly serial: receive → `run_in_threadpool(solve)`
→ send (`web/server.py:1016-1049`). This already squashes intermediate knob
values client-side — the server never sees a backlog. Three costs remain:

1. **One full round-trip of hold-back per superseded change.** The pending
   request isn't sent until the previous response has fully downloaded and
   been `JSON.parse`d. Tail latency for the final knob value =
   remainder of in-flight solve + response download + parse + request upload
   + solve(final) + response download. The upload leg and the
   response-processing dependency are pure waste on the fly path.
2. **Superseded results are fully shipped and rendered.** When controls
   changed mid-solve, the doomed payload (wires + interleaved sample-current
   arrays — the big part) still travels back and gets parsed before the
   pending request fires (`App.tsx:3368-3406`).
3. **No preemption of a stale in-flight solve** — acknowledged at
   `App.tsx:2080-2082` ("cancels the WAIT, not the computation"). Fine at
   10–100 ms; painful on tens-of-seconds array solves. (Optional phase; the
   engine can't be interrupted without cooperative checks.)

The fix inverts the squash point: **client sends every change eagerly with a
sequence number; the server keeps only the newest queued request (a size-1
latest-wins mailbox), solves that when free, and skips sending results it
already knows are superseded.** The final knob value is then already waiting
at the server when the current solve finishes, and doomed payloads never
travel.

Groundwork that already exists:

- `_CACHE_KEY_BLOCKLIST` (`web/server.py:463-468`) already excludes
  `_request_id` / `_client_ts` from the solve-cache key — the seq field slots
  in with one line.
- The send-guard structure (`web/server.py:1042-1047`, connected-state check
  before `send_text`) is where the "superseded → skip send" check goes.

## Design

### Wire protocol

- Client adds `_seq` (monotonic int, per App instance, never reset — survives
  reconnects) and keeps/adds `_client_ts` to every /ws solve request.
- Server echoes `_seq` verbatim in every response, **including error
  responses** (the `except` branch at `web/server.py:1025-1032`).
- Add `_seq` to `_CACHE_KEY_BLOCKLIST` so it can't shred the cache hit rate.

Compatibility note: new-client + old-server would pile up (client no longer
gates in-flight, old server solves every message serially). Not a real
deployment state — the fly image bundles frontend + server, and dev runs both
from the checkout — but don't split the two halves across separate deploys.

### Server: `/ws` handler rewrite (`web/server.py:1016-1049`)

Replace the serial receive→solve→send loop with a reader task + solver loop
sharing a latest-wins mailbox:

```python
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    mailbox: list[dict] = []          # size-1, newest only
    newer = asyncio.Event()           # "mailbox refilled"
    closed = asyncio.Event()

    async def reader():
        try:
            while True:
                req = json.loads(await ws.receive_text())
                mailbox[:] = [req]    # overwrite: squash anything unsolved
                newer.set()
        except WebSocketDisconnect:
            closed.set()
            newer.set()               # wake the solver so it can exit

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            await newer.wait()
            if closed.is_set():
                return
            newer.clear()
            req = mailbox.pop()
            try:
                result = await run_in_threadpool(solve, req)
            except Exception as exc:
                result = {"geometry": req.get("geometry"),
                          "error": user_designs.format_solve_error(exc)}
            result["_seq"] = req.get("_seq")
            # Superseded while solving? Skip the send — the newer request's
            # response will carry a higher _seq and the client renders
            # monotonically. Saves the full doomed payload on the wire.
            if mailbox:
                continue
            if ws.client_state != WebSocketState.CONNECTED or closed.is_set():
                return
            try:
                await ws.send_text(json.dumps(result))
            except (WebSocketDisconnect, RuntimeError):
                return
    finally:
        reader_task.cancel()
```

Details to get right:

- The reader task must be the **only** receiver on the socket (starlette
  requires single-reader).
- Keep the existing behaviors: error responses don't tear down the socket;
  send is skipped when the client already disconnected.
- Cache-hit responses mutate `solve_ms` (`web/server.py:514-523`) — the
  `_seq` stamp goes on the (deep)copied result, never the cached entry.

### Client: `App.tsx` solve path

- `requestSolve()` (`App.tsx:3326-3340`): drop the `inFlightRef` gate for
  sends. When the socket is OPEN, always send immediately with
  `_seq: ++seqRef.current`; record `sentAt.set(seq, performance.now())` for
  RTT. When not OPEN, keep the current "stash in pendingRef, flush onopen"
  behavior.
- **Send throttle (localhost-neutrality guard):** coalesce sends to one per
  animation frame (a trailing-edge rAF throttle inside `requestSolve`).
  During a drag this bounds upload to ≤60 msg/s of ~1 KB requests, and on
  localhost keeps message churn near what the old gate produced. Latest value
  always wins within the frame.
- Replace `inFlightRef`/`pendingRef` bookkeeping with two counters:
  `lastSentSeq`, `lastRenderedSeq` (or `lastReceivedSeq`).
  - `solving` ⇔ `lastSentSeq > lastReceivedSeq` (replaces `syncSolving()`,
    `App.tsx:3272-3277`).
  - `onmessage`: drop any response with `_seq <= lastReceivedSeq` (belt and
    suspenders — one socket delivers in order anyway); keep the existing
    geometry-mismatch drop (`App.tsx:3387`) for antenna switches; then
    `setResult`, update RTT from `sentAt`, and prune `sentAt` entries ≤ seq.
    Note responses may be *skipped* server-side — a higher `_seq` response
    implicitly acknowledges all lower seqs; treat it as such everywhere
    (RTT map pruning, solving state).
  - `cancelSolve()` (`App.tsx:2287-2292`): set `canceledThroughSeq =
    lastSentSeq`; onmessage drops rendering for `_seq <=
    canceledThroughSeq` but still updates `lastReceivedSeq`.
  - `onopen` (`App.tsx:3346-3355`): set `lastReceivedSeq = lastSentSeq`
    (nothing from a dead socket can arrive), then send a fresh request —
    same recovery the current code does with `inFlightRef = false`.
  - `onclose`/`onerror`: same as today, plus `lastReceivedSeq = lastSentSeq`
    so `solving` can't stick true.
- Sweep/converge hold-off polls (`App.tsx:2998`, `App.tsx:3127`) test
  `inFlightRef.current || pendingRef.current` — replace with the same
  `lastSentSeq > lastReceivedSeq` predicate (extract a helper).

### Optional phase: skip stale post-processing / cooperative preempt

Cheap variant: thread a `superseded: Callable[[], bool]` (closure over
`bool(mailbox)`; safe to read from the worker thread) into the ws-path solve
and check it between the impedance/currents solve and
`_attach_derived_em_fields` + `_compute_directivity_norm`
(`web/server.py:493-507`). If superseded, return a sentinel; the ws loop just
continues. **Do not cache partial results** — only fully post-processed
results may enter `_SOLVE_CACHE`. Full mid-solve preemption (checks between
matrix fill / LU inside the engines) is out of scope here.

### Optional phase: serialization

`json.dumps` of a large result runs on the event loop once per response and
`solve()` pays a `deepcopy` per cache hit. If profiling shows it matters
(multi-tab hosted use): swap to `orjson` for dumps, or cache the serialized
string. Second-order; skip unless measured.

## Phases

1. **Server mailbox + `_seq` echo + skip-send** (server.py only, protocol is
   additive — old client still works against it since `_seq` is optional).
   Tests below land here.
2. **Client eager-send + seq counters + rAF throttle** (App.tsx). Remove
   `inFlightRef`/`pendingRef`/`solveCanceledRef` in favor of seq counters.
3. *(Optional)* post-processing skip for superseded requests.
4. *(Optional)* serialization work, only if profiled.

Phases 1+2 are one PR (they're only correct together — see compatibility
note); 3 and 4 separate follow-ups.

## Tests (`tests/test_web_server.py`)

Existing ws tests to keep green: round-trip (`:947`), two-sequential-requests
(`:965`), disconnect-during-solve (`:988`), error-keeps-socket-alive
(`:1036`).

New, with `solve` monkeypatched to count calls and optionally block on an
event so requests genuinely queue:

- **Squash:** hold the first solve, send requests seq 1..5, release. Assert
  solve ran exactly twice (seq 1 and seq 5) and the only responses carry
  `_seq` 1 and 5 — no responses for 2–4 (skip-send) unless 1's send already
  left before 5 arrived, in which case exactly {1, 5}.
- **Seq echo:** response `_seq` equals request `_seq`, including on the error
  path (a request whose solve raises).
- **Skip-send:** with a newer request queued before send, the older result
  never appears on the socket.
- **Cache key:** `_seq`/`_client_ts` variations hit the same cache entry
  (extend the blocklist tests at `:1159-1249`).
- **Disconnect:** client drops mid-solve → handler returns cleanly, reader
  task cancelled, no stray exceptions.

Frontend has no unit-test rig for App.tsx; verify by hand (below).

## Verification (the fly-vs-localhost tradeoff, measured)

- **Localhost:** run the app, scrub a knob on a mid-weight design; compare
  solve cadence and the RTT/solve-time HUD before vs after. Expect: identical
  solve counts (squash point moved, not tightened), no added jank.
- **Simulated fly:** Chrome DevTools network throttling (add ~80 ms RTT),
  scrub, measure time from last knob tick to final chart paint. Expect:
  roughly one RTT + one response-parse less per superseded change; doomed
  payloads absent from the WS frame log.
- **Hosted smoke test** after deploy: scrub on the fly instance, confirm
  final value renders and `solving` clears.

## Risks / edge cases

- `solving` stuck true if a response is skipped and no newer one ever sends
  (e.g. newest request errors → error response still carries `_seq`, so this
  resolves; make sure *every* path echoes `_seq`).
- StrictMode/HMR socket teardown: the seq counters live in refs that survive
  remounts of the effect but the counter must never reset below
  `lastReceivedSeq` — keep `seqRef` at module/App scope, not inside the
  effect.
- Multiple design-session tabs: each session has its own socket/handler; the
  mailbox is per-connection, so no cross-tab interaction. Inactive sessions
  already close their socket (`active` gate).
- The `/ws` handler change must not alter response *shape* other than adding
  `_seq` — the pinned-pattern snapshots and result schema readers consume it.
