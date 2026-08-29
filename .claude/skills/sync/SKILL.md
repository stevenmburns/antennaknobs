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
   cd momwire && ../.venv/bin/python setup.py build_ext --inplace
   ```
   If it prints `c++ ...` lines, the extensions were stale and are now
   rebuilt; if it only prints `copying`, they were already current. Either way
   the tree ends correct, which a check that merely *reports* does not
   guarantee.

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

   With `ccache` wired (`CC="ccache gcc" CXX="ccache g++"`, or just
   `make build` from `momwire/`), a real edit costs 12–28 s instead of ~48 s:
   setuptools recompiles *every* source in a stale extension, so ccache is
   what makes the untouched TUs free.

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
