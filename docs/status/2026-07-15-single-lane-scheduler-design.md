# Single-lane solve scheduler (#382): design decisions

Status note pinning the decisions before code. The issue's four principles —
one active solve per session, latest intent wins, cancel means stop
computing, admission by cost — each get one mechanism, below.

## The primitive: a per-session `SolveLane`, acquired per compute step

A `SolveLane` is a priority-ordered, generation-aware async turnstile
(`web/lane.py`). Every solve-producing compute — the live `/ws` solve, each
`/sweep` chunk, each `/converge` point, `/norm_check`, `/pattern`,
`/pattern_metrics` — runs inside `async with lane.turn(kind, gen) as token:`
and dispatches to the threadpool with that token. Holding the lane is the
*only* way to compute, so "no two computations concurrently per session" is
enforced structurally, not by cooperating heuristics.

Turns are granted by `(priority, arrival)`: live = 0, norm-check/pattern =
1, sweep/converge = 2. A batch acquires the lane **per chunk/point**, not
per stream — so a live solve queued during a sweep runs at the very next
chunk boundary instead of after 41 points, and cancellation of the running
chunk (below) bounds even that wait.

Rejected alternative: a queue of whole jobs with one worker task. The
streaming endpoints must yield NDJSON as points complete, which would force
result plumbing from a detached worker back through per-job channels;
turn-per-step keeps each endpoint's code shape (async generator) intact and
gets lane-yielding between chunks for free.

## Sessions: client-minted id, lanes on demand, sessionless = unmanaged

Each App instance (one per workbench tab — A/B compare tabs are separate
sessions) mints a `_session` UUID and stamps it on every WS payload and
batch POST. The server keeps `lanes: dict[str, SolveLane]`, created on
first use and dropped when idle (no runner, no waiters — checked on turn
exit; disconnect-only sessions can't leak lanes).

A request with no `_session` (curl, scripts, tests that don't care) gets a
fresh private lane for that request: admission still applies, serialization
doesn't. Cross-session coupling is explicitly out of scope — hosted safety
against N sessions is the admission model's job, not the lane's.

## Latest intent wins: one generation counter, all job kinds

The client already stamps live solves with a monotonic `_seq`; batch
requests now carry the same counter's value at issue time as `_gen`
(`_seq` and `_gen` unify server-side). The lane tracks the highest
generation seen. Entering a turn with a newer generation:

- **cancels the running turn** (trips its CancelToken) if it is older —
  a knob drag kills the in-flight benchmark sweep chunk at its next solver
  checkpoint, and
- **supersedes queued waiters** that are older *and of a batch kind* —
  they raise `Superseded`, their generators end their streams.

Same-kind arrivals supersede each other regardless of generation (the
client re-issued the sweep; the old stream is already abandoned). The live
`/ws` reader keeps its existing direct token-trip on newer messages — the
lane token replaces `current["token"]`, one cancellation channel, two
trippers.

## Cancel means stop computing

Every turn's CancelToken reaches the solver: `momwire_sweep` and
`_solve_z_only` grow the `cancel=` parameter `momwire_solve` already has
(threaded to `_make_momwire_engine`); `_norm_check` passes it to its inner
`solve()`. PyNEC keeps its start-gate-only contract (no mid-solve abort in
native code) — admission bounds it instead.

Disconnects trip the same token: each HTTP turn runs a watcher task polling
`request.is_disconnected()` (~250 ms) for the duration of the turn, so an
abandoned tab stops a minutes-long chunk at the next checkpoint — today's
between-chunk checks only fire after the damage. The WS reader's
disconnect path already trips the token.

## Admission by cost: one mapping, every kind

`web/cost.py` owns the single mapping `admit(kind, req, points) →
run | warn | refuse` built on the existing `count_basis` estimate. It
consolidates today's three parallel inventions: the hosted matrix caps
(`_check_solve_size` becomes a thin wrapper, refuse), the hosted
point-count caps (refuse, cost × points), and the poor-match recommendation
(`est_basis > 3000` dense ⇒ warn — the same condition the frontend's
withhold gate computes independently today).

`warn` is enforced server-side for batches: a warned batch request runs
only if it carries `_approved: true`, which the client sets exactly when
the user clicks "Solve anyway" on the existing gate. The gate's UX is
unchanged; the server stops trusting the client to hold batches back.

## Client: effects declare intent, polling loops die

`runSweep`/`runConverge`/`runNormCheck` lose their 200 ms
`solvePending() || solveWithheld()` re-poll loops — they fire after their
debounce and the lane orders them (live wins by priority, so norm-check
still lands on the live solve's cache entry). The withhold gate becomes
plain state consulted once at effect time (approval flips state, effects
re-run) instead of a ref polled on a timer. `solvePending()` reduces to UI
state (`solving` indicator); per-endpoint AbortControllers stay — an
aborted fetch is how the server learns to cancel.

## Testing

Lane unit tests use fake async jobs (no solver): concurrency-never ≥ 2
(instrumented counter), priority order, generation supersession of running
+ queued, same-kind supersession, sessionless isolation, idle cleanup.
Endpoint tests monkeypatch a slow event-gated fake solver under
`TestClient`: `/ws` + `/sweep` never overlap, a dropped stream trips the
token within one checkpoint, warned batches 403 without `_approved`. Cost
model gets a pure mapping table test. Everything event-driven — no sleeps
near the suite's 2 s budget.
