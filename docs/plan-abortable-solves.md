# Plan: fast cooperative abort of in-flight momwire solves

Status: **not started.** Scoped 2026-07-04. Follow-up to
`plan-ws-latest-wins.md`, whose item 3 deferred exactly this: "No preemption
of a stale in-flight solve … the engine can't be interrupted without
cooperative checks." With latest-wins squashing merged (PR #226), a stale
solve no longer ships its payload — but it still runs to completion,
occupying a threadpool worker and delaying the superseding solve by the full
remainder of the doomed one. Goal: when a newer knob value arrives, the
in-flight momwire solve dies within ~one LAPACK-call's worth of time
(tens of ms), not seconds.

Scope: momwire only (we own the code). PyNEC gets a start-gate check but no
mid-solve abort — its solve is one opaque native call.

## The mechanism in one paragraph

A `CancelToken` — a single int32 in shared memory — is created per solve on
the caller side and threaded down through `MomwireEngine` into the solver.
The `/ws` reader task flips it the moment a superseding request lands in the
mailbox (and on disconnect). The solver polls it at every cheap seam:
Python-level phase boundaries and sweep/ACA/GMRES loops check
`token.cancelled` and raise `momwire.SolveAborted`; the long C++ kernels
receive the flag's raw address and poll it per outer-loop iteration without
touching the GIL. The caller catches `SolveAborted`, stores nothing in the
solve cache, sends nothing, and moves on to the queued request.

Why a shared flag and not a Python callback: the C++ kernels run under
OpenMP; calling back into Python per row would reacquire the GIL and
serialize the parallel region. A relaxed load of an aligned int32 costs ~1 ns
and is safe from any thread.

## Critical prerequisite: the C++ kernels never release the GIL

`momwire/src/momwire/_accelerators.cpp` contains no `gil_scoped_release`
anywhere (verified by grep). Consequences:

1. **Cancellation of C++ phases is impossible today even in principle**:
   while `sinusoidal_field_tensor` or `assemble_Z_general` runs, the pybind11
   call holds the GIL, so the asyncio event loop is frozen — the `/ws` reader
   task cannot even *receive* the superseding knob message, let alone set a
   flag.
2. **The server event loop stalls for every connection during every C++
   fill.** This is a live latency bug independent of this plan (masked so far
   because typical fills are short and the hosted instance is single-user).

So Phase 0 is: add `py::call_guard<py::gil_scoped_release>` (or explicit
scoped release) to every long-running exported kernel. Rules for the audit:
argument conversion happens before `call_guard` releases, and return-value
conversion after it reacquires, so signatures are safe as-is; the audit must
confirm each kernel body touches only raw buffers (no `py::` API, no numpy
allocation) between release and reacquire — allocate output arrays before
releasing. This phase is a standalone win and ships on its own.

Note: `scipy.linalg.solve` already releases the GIL inside LAPACK, so the LU
never freezes the loop — it is merely uninterruptible, which sets the floor
on abort latency (~20 ms at N=160, per the PR #13 numbers in momwire's
`NEXT_STEPS.md`).

## Design

### momwire: `CancelToken` + `SolveAborted` (new module `_cancel.py`)

```python
class SolveAborted(Exception):
    """Solve was cancelled via CancelToken; no result was produced."""

class CancelToken:
    def __init__(self):
        self._flag = np.zeros(1, dtype=np.int32)
    def cancel(self):            # any thread; idempotent
        self._flag[0] = 1
    @property
    def cancelled(self):
        return bool(self._flag[0])
    def raise_if_cancelled(self):
        if self._flag[0]:
            raise SolveAborted()
    @property
    def ptr(self):               # raw address for the C++ kernels
        return self._flag.ctypes.data
```

Exported from `momwire/__init__.py`. The token owns the flag's memory; the
solver holds the token, so pointer lifetime is covered for the duration of
any kernel call. A relaxed racy read is fine — the only transition is 0→1
and a missed read costs one extra poll interval. (If we want rigor, the C++
side reads via `std::atomic_ref<int32_t>`; check the standard the extension
builds with.)

### momwire: solver API

`cancel: CancelToken | None = None` keyword on the **solver constructors**
(SinusoidalSolver, TriangularSolver, BSplineSolver → inherited by
HMatrixSolver / ArrayBlockSolver), stored as `self._cancel`. Constructor
injection rather than per-method kwargs keeps every `compute_*` signature
unchanged and covers internal cross-calls for free. A private helper:

```python
def _checkpoint(self):
    if self._cancel is not None:
        self._cancel.raise_if_cancelled()
```

Default `None` → checkpoints are a single `is not None` test; zero cost for
existing users. No behavior change unless a token is passed, so this is a
backward-compatible minor version bump.

### momwire: Python-level checkpoint placement (Phase 1)

| Seam | Location | Granularity |
|---|---|---|
| Phase boundaries in `compute_impedance` | `triangular.py:660`, `sinusoidal.py:922`, `bspline.py:1368` — after geometry, after J-block build, after assemble, before LU | per phase |
| Sweep k-loops in `compute_impedance_swept` | `triangular.py:991`, `sinusoidal.py:1013`, `bspline.py:1608` — top of each frequency iteration | per frequency |
| ACA rank-building loop | `_aca.py:156` — top of each rank iteration | per rank (~4–8 per block) |
| H-matrix matvec block loop | `hmatrix.py:230` — checked per near/far block; this also covers GMRES, since scipy's GMRES calls our matvec every iteration | per block per iteration |
| Enrichment two-pass | `bspline.py` auto-enrichment — between passes | per pass |

Phase 1 alone already makes the *slow* cases abortable — multi-frequency
sweeps, and the H-matrix/array solvers (the "tens-of-seconds array solves"
the latest-wins plan called painful) — because their time is spread across
many loop iterations. What it does not cover is a single-frequency solve
dominated by one bulk C++ fill call; that needs Phase 2.

### momwire: C++ kernel polling (Phase 2)

Add a trailing `uintptr_t cancel_flag = 0` parameter (0 = no cancellation,
fully backward compatible) to the long kernels:

`sinusoidal_field_tensor`, `seg_seg_quad_batch_3d`,
`seg_seg_reg_quad_batch_1d`, `assemble_Z`, `assemble_Z_general`,
`assemble_Z_bspline`, `bspline_assemble_offedge_block`.

Inside each, poll once per **outer** iteration (per source row / per k
slab — row cost dwarfs a flag load, so overhead is unmeasurable). OpenMP
forbids `break` from a `omp for`, so use the standard drain pattern:

```cpp
const volatile int32_t* cancel =
    reinterpret_cast<const volatile int32_t*>(cancel_flag);
std::atomic<bool> aborted{false};
#pragma omp parallel for
for (int i = 0; i < n; ++i) {
    if (aborted.load(std::memory_order_relaxed)) continue;   // drain
    if (cancel && *cancel) { aborted.store(true); continue; }
    // ... row work ...
}
if (aborted) throw AbortedError{};
```

Remaining iterations become no-ops and the loop drains in microseconds.
Define `struct AbortedError {}` and register it once with
`py::register_exception<AbortedError>(m, "AcceleratorAborted")`; the Python
wrappers in `_accel.py` translate it to `momwire.SolveAborted` (or we map it
directly to the shared exception type). `_accel.py` threads
`self._cancel.ptr if self._cancel else 0` into each call.

Abort-latency floor after Phase 2 ≈ max(one dense LU, one outer row of
fill) ≈ the LU. The array solvers avoid the dense LU (GMRES + per-block
checks), leaving their sparse-LU preconditioner factorization as the only
uninterruptible stretch.

### antennaknobs caller (Phase 3)

Thread the token explicitly (no smuggling through the req dict — it must
never reach the cache key or serialization):

- `web/server.py:695 solve(req)` → `solve(req, cancel=None)`; same for
  `_solve_uncached` (`server.py:680`). **Cache-hit path checks nothing** —
  hits are O(1) and never worth aborting. On `SolveAborted`, the cache-store
  line is skipped (the exception propagates before the store, but add a test
  pinning it).
- `web/adapter.py:1002 momwire_solve(req)` → accept `cancel`, pass to
  `_make_momwire_engine`, which passes it to `MomwireEngine`.
- `engines/momwire.py MomwireEngine.__init__` gains `cancel=None`, forwards
  it into every solver construction (`_solved_excited` at line 237,
  `impedance_sweep` at 271, the network-Y path), and calls
  `cancel.raise_if_cancelled()` between its own phases — `impedance()` /
  `current_distribution()` / `far_field()` — so a cancel landing between
  engine phases doesn't wait for the next solver-internal checkpoint.
  An aborted solve leaves no partial state behind because `_solved_excited`
  assigns its instance cache only after `compute_impedance` returns —
  exception propagation guarantees it; test pins it.

`/ws` handler (`server.py:1246–1322`) — the two changes:

```python
current = {"token": None}          # shared cell, reader + solver loop

async def reader():
    while True:
        req = json.loads(await ws.receive_text())
        mailbox[:] = [req]
        if current["token"] is not None:
            current["token"].cancel()      # <-- preempt in-flight solve
        newer.set()
    # finally: closed.set(); also cancel() — disconnect kills the solve too

# solver loop:
req = mailbox.pop()
token = momwire.CancelToken()
current["token"] = token           # publish BEFORE dispatch (see race note)
try:
    result = await run_in_threadpool(solve, req, cancel=token)
except momwire.SolveAborted:
    continue                       # superseded: no send, no error banner
except Exception as exc:
    ...existing error-response path...
finally:
    current["token"] = None
```

Ordering note: the token is published to the shared cell before the
threadpool dispatch, so a reader that fires in the gap cancels a
not-yet-started solve — which then raises `SolveAborted` at its first
checkpoint. No lost-wakeup window. The `SolveAborted` catch must precede the
generic `except Exception` branch, which would otherwise ship it to the
client as a solve-error banner.

The skip-send guard (`if mailbox: continue`) stays — it covers a solve that
completes in the sliver between mailbox refill and flag observation.

PyNEC (`web/pynec_backend.py`, `engines/pynec.py`): start-gate only —
`cancel.raise_if_cancelled()` before dispatching the native solve. A queued
stale PyNEC request dies for free; an in-flight one runs to completion, as
today.

### `/sweep` and `/converge` (Phase 4, optional)

Both already check `is_disconnected()` between chunks (`server.py:791, 876`).
Adding in-chunk cancellation needs a watcher task per request that polls
`is_disconnected()` and flips a token shared with the chunk's solve. Worth it
only if the per-chunk `_CHUNK_TARGET_MS` (500 ms) granularity is actually
hurting; defer until observed.

## What was rejected

- **Subprocess-per-solve + SIGKILL.** The only way to preempt LAPACK too,
  but it forfeits the in-process solve cache and warm engine state, adds
  serialization of the large current arrays on every solve, and complicates
  fly.io memory headroom. The cooperative floor (~one LU) is far below human
  slider-perception threshold; not worth it.
- **`PyThreadState_SetAsyncExc` injection.** Cannot interrupt native code,
  can vanish at interpreter discretion, and leaves the solver's internal
  state undefined mid-phase. Cooperative checks are deterministic.
- **Token via `req["_cancel"]`.** Would leak into the solve-cache key
  machinery and JSON paths; explicit parameters keep it out by construction.

## Phasing / PR plan

Phases 0–2 land as PRs in the **momwire repo**; 3–4 in antennaknobs with a
submodule-pointer bump. Each is independently shippable and useful:

| Phase | Repo | Content | Standalone value |
|---|---|---|---|
| 0 | momwire | GIL release on long C++ kernels (+ audit no Python API in released regions) | server event loop stops stalling during fills |
| 1 | momwire | `CancelToken`, `SolveAborted`, Python checkpoints (phases, k-loops, ACA, matvec) | sweeps & array solvers abortable |
| 2 | momwire | `cancel_flag` polling in C++ kernels, `AcceleratorAborted` mapping | single-frequency fills abortable; floor ≈ one LU |
| 3 | antennaknobs | token threading; `/ws` cancel-on-squash + cancel-on-disconnect; `SolveAborted` handling; cache-store guard; PyNEC start-gate; submodule bump | end-to-end preemption on knob drag |
| 4 | antennaknobs | `/sweep`/`/converge` in-chunk cancel via disconnect watcher | finer than 500 ms chunk granularity |

Phase 3 works end-to-end after Phase 1 alone (Phase 2 just tightens the
latency), so the merge order 0 → 1 → 3 → 2 is also viable if we want the UX
win sooner.

## Testing

momwire:

- Pre-cancelled token → `compute_impedance` raises `SolveAborted` before any
  J-block work (assert via elapsed time or a mocked kernel).
- Timer thread cancels mid-`compute_impedance_swept` over ~40 frequencies →
  raises, elapsed ≪ full-sweep time.
- Phase 2: tripped flag passed straight to each C++ kernel → raises within
  a small multiple of one row's cost.
- No-token path: benchmark fill with `cancel=None` vs. before-series —
  overhead indistinguishable (it's one `is not None` per checkpoint).
- Aborted solve leaves no instance-cache residue: cancel mid-solve, clear
  the token, re-run `compute_impedance` → result matches a fresh solver.
- Phase 0: kernel releases GIL — spawn a thread that acquires the GIL
  (increments a Python counter) while a large fill runs; assert it makes
  progress.

antennaknobs:

- WS test: send request A (slow design), then B immediately; assert the A
  solve raised `SolveAborted` (instrument via a counter monkeypatched into
  the engine), only B's response is sent, `_seq` echoes B.
- Disconnect mid-solve → solve aborts (threadpool worker freed promptly).
- `SolveAborted` never reaches the solve cache and never produces an
  error-banner response.
- Existing power-balance / norm-check tests unchanged (no-token path).

## Open questions

- Which C++ standard does the extension build with? (`std::atomic_ref` needs
  C++20; `volatile` read is the fallback and fine in practice.)
- Does any kernel body currently allocate numpy outputs mid-computation?
  The Phase 0 audit answers this; if so, hoist allocations before the GIL
  release.
- `impedance_sweep` multi-RHS path (`triangular.py:753`) does one big LU —
  after Phase 2 that single call is the longest uninterruptible stretch for
  sweeps; acceptable, but note it in profiling.
