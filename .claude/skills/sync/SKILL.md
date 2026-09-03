---
name: sync
description: Update antennaknobs and the momwire submodule to origin/main, verify both are installed editable, and rebuild momwire's C++ extension if stale
---

# Sync antennaknobs + momwire to origin

Bring both repos to their origin/main tips, keep the `.venv` editable installs
honest, and make sure momwire's compiled accelerator matches its sources.

**Dev model reminder**: the momwire submodule is deliberately run on branch
`main` (the dev tip), NOT detached at the commit antennaknobs pins. Never run
`git submodule update` here — it would detach momwire at the stale pinned
commit. The pin only moves during the release ritual (see the `release` skill).

## Steps

1. **Pull antennaknobs** (from the repo root):
   ```
   git fetch origin && git pull --ff-only
   ```
   `fetch` also fetches the momwire submodule's remote.

2. **Pull momwire** (in `momwire/`): confirm it is on branch `main` (not
   detached), then:
   ```
   git pull --ff-only
   ```
   If either pull cannot fast-forward, stop and report — do not merge or
   rebase without being asked.

   **Confirm the submodule is initialized first — the branch check cannot.**
   An uninitialized `momwire/` is an empty directory with no `.git`, so git
   walks *up* to the parent and every command run inside it answers about
   antennaknobs instead: `git rev-parse --abbrev-ref HEAD` prints `main`,
   `git rev-parse HEAD` prints the antennaknobs commit, and `git remote -v`
   points at `antennaknobs.git`. All three are exactly what a correctly
   checked-out submodule sitting on the dev tip looks like, so the
   confirm-it-is-on-`main` step above passes, the `git pull --ff-only` below
   fast-forwards the **parent** a second time, and the sync reports success
   having never touched momwire. Measured 2026-09-02 on a fresh clone.

   ```
   git submodule status   # a leading "-" means never initialized
   ```
   `test -e momwire/.git` answers the same question. If it is uninitialized
   this is a bootstrap rather than a sync, and the dev-model warning above
   needs care: `git submodule update --init momwire` is the way in, but it
   leaves momwire **detached at the recorded pin**, so it is only half the
   job. Follow it with `git checkout main && git pull --ff-only` inside
   `momwire/` to land on the dev tip.

3. **Expect a dirty submodule pointer.** After both pulls, `git status` in
   antennaknobs usually shows `M momwire` because the momwire tip is ahead of
   the recorded pin. That is the normal dev-model state — leave it uncommitted.

4. **Verify editable installs**: `.venv/bin/pip show antennaknobs momwire`
   must report `Editable project location` as the repo root and
   `<root>/momwire` respectively. If either is missing or non-editable,
   reinstall it with `.venv/bin/pip install -e <path> --no-deps`.

5. **Rebuild the accelerators.** Do not hand-roll a staleness check — just
   run the build. `build_ext` already decides per extension, via
   `newer_group(sources + depends, ext_path)`, and it is a **no-op when
   nothing changed**: measured 0 compile invocations in 0.20 s even without
   ccache.
   ```
   cd momwire && make build
   ```
   If it prints `c++ ...` lines, the extensions were stale and are now
   rebuilt; if it only prints `copying`, they were already current. With a
   working toolchain the tree ends correct either way, which a check that
   merely *reports* does not guarantee.

   **Use `make build`, not bare `setup.py build_ext --inplace`.** The two are
   not equivalent, and the difference is exactly the fail-open below:
   `make build` sets **`MOMWIRE_REQUIRE_ACCEL=1`**, which `setup.py:70` reads
   to **re-raise** the `CompileError` instead of warning and falling back. Its
   own comment says why — *"a DEVELOPMENT build wants the opposite … so a
   broken toolchain fails the lane instead of exiting 0 and leaving a stale
   in-place `.so`"* (#716 review). `make build` also wires ccache only when it
   is actually on `PATH` (`CCACHE := $(shell command -v ccache)`), so it
   cannot be broken by naming a compiler wrapper that is not installed.

   Prior versions of this step recommended the bare `setup.py` invocation,
   which opts out of that guard while the paragraphs below explain at length
   why its exit code cannot be trusted. Measured 2026-09-03: exporting
   `CXX="ccache g++"` on a box **without** ccache printed six convincing
   `ccache g++ ...` lines for `_accelerators`, failed it with
   `CompileError(FileNotFoundError(2, 'No such file or directory'))` — the
   missing wrapper, not any compile error — then exited **0** and left the
   previous day's `.so` in place. A sync that reported success over stale
   binaries. Under `make build` that mistake is impossible in two independent
   ways.

   **Compile lines are not proof of a rebuild, and the exit status is proof
   of nothing** — unless `MOMWIRE_REQUIRE_ACCEL=1` is set, which is the whole
   reason step 5 goes through `make build`. Without it `setup.py` catches a
   per-extension `CompileError` and falls back to pure-Python mode with a
   `UserWarning`, so a build in which every translation unit failed still
   prints a screen of `c++ ...` lines and then
   exits **0**. Measured 2026-09-02: with the CPython development headers
   absent, all five `_accelerators` TUs died on `fatal error: Python.h: No
   such file or directory`, the run exited 0, and **no `.so` was produced** —
   byte for byte the same exit code as a good build. The warning scrolls past
   in the compiler noise.

   So step 7 is load-bearing rather than ceremonial: importing each extension
   is the only check here that separates an accelerated tree from a silently
   pure-Python one. `ls momwire/src/momwire/*.cpython-*.so` is the cheap first
   look — zero files means the fallback fired.

   **Why not an mtime check.** Two were tried here and both were wrong, for
   reasons worth recording so a third is not attempted:

   * *One `.cpp` per `.so`* — false since momwire#687. `_accelerators` is
     built from FIVE sources (`_accelerators.cpp` plus four `_accel_*.cpp`
     section TUs) into one binary, so the four section TUs have no
     same-named `.so` and a name-matching check reports them `MISSING`.
   * *Compare every source against the OLDEST `.so`* — permanently red.
     `build_ext` relinks only the extensions whose own sources changed, so
     the two `.so` mtimes legitimately diverge; any source newer than the
     least-recently-relinked extension then reports `STALE` forever, even
     with everything correctly built.

   The mapping that would make an mtime check correct is the `sources=` and
   `depends=` lists in `setup.py` — which is precisely what `build_ext`
   consults. Reimplementing it is how you get a second source of truth that
   drifts, the momwire#568 stale-`.so` lesson in a new spelling.

   With `ccache` wired — which `make build` does for you — a real edit costs
   12–28 s instead of ~48 s: setuptools recompiles *every* source in a stale
   extension, so ccache is what makes the untouched TUs free.

   Do **not** wire it by hand with `CC=`/`CXX=` just to get that speedup.
   `make build` already skips ccache when it is absent, whereas naming it
   yourself on a box that lacks it is the silent-fallback bite above. ccache
   is **not** preinstalled on every dev box here, and `sudo` may want a
   password; a static build from the ccache GitHub release dropped in
   `~/.local/bin` needs neither. Confirm a wired build actually cached with
   `make ccache-stats` (or `ccache -s`) rather than by reading compile lines
   — on 2026-09-03 a cold run measured 6 misses / 29 s and the warm rerun
   6 hits / 0.8 s.

6. **Refresh version metadata if needed**: if either `pyproject.toml` version
   changed in the pull, `importlib.metadata` still reports the old number
   until the editable install is refreshed:
   ```
   .venv/bin/pip install -e . --no-deps -q
   .venv/bin/pip install -e ./momwire --no-deps -q
   ```

7. **Verify**: with `.venv/bin/python`, import `antennaknobs`, `momwire`, and
   **every built extension** — one per `.so`, not one per source file:
   `ls momwire/src/momwire/*.cpython-*.so` names them (today
   `momwire._accelerators` and `momwire._near_interface_accel`). Check each
   `__file__` resolves into the source trees (not site-packages) and that
   `importlib.metadata` versions match the pyproject versions.

   Beware that other `_accelerators*.so` can exist on disk without being the
   live one: `setup.py build_ext` leaves a copy under `momwire/build/`, and any
   sibling venv or agent worktree carries its own. None of those is on
   `sys.path`, so trust the imported `__file__` over a bare `find` — and do not
   delete anything as part of a sync, which is a read-and-rebuild operation.

Report: old → new commit for each repo, whether step 5 actually rebuilt
anything (compile lines printed vs `copying` only), and the final installed
versions.
