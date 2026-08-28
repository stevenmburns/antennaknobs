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

5. **Rebuild the accelerators if stale.** momwire builds *more than one*
   extension — `setup.py` declares `momwire._accelerators` and
   `momwire._near_interface_accel` today, and has grown the list before — so
   check every one rather than a named binary. Each extension also has a
   `depends=` list of `*_inline.h` headers, and a header edit alone makes a
   `.so` stale with its `.cpp` untouched.

   Run this from the repo root; it derives the extension list from what is on
   disk, so a third extension is covered with no edit here:
   ```bash
   cd momwire/src/momwire && stale=0
   for cpp in *.cpp; do
     base=${cpp%.cpp}
     so=$(ls "${base}".cpython-*.so 2>/dev/null | head -1)
     if [ -z "$so" ]; then echo "MISSING  $base"; stale=1; continue; fi
     newer=$(find . -maxdepth 1 \( -name '*.h' -o -name "$cpp" \) -newer "$so" -printf '%f ' 2>/dev/null)
     if [ -n "$newer" ]; then echo "STALE    $base  <- $newer"; stale=1; else echo "current  $base"; fi
   done
   [ $stale -eq 1 ] && echo "REBUILD NEEDED" || echo "all extensions current"
   ```
   It compares every header against every `.so`, which is deliberately
   conservative: the two `depends=` lists differ, so a shared-header edit may
   rebuild one extension unnecessarily. That is much cheaper than shipping a
   stale binary.

   If anything reports `STALE` or `MISSING`, rebuild in place — one command
   builds every extension:
   ```
   cd momwire && ../.venv/bin/python setup.py build_ext --inplace
   ```

6. **Refresh version metadata if needed**: if either `pyproject.toml` version
   changed in the pull, `importlib.metadata` still reports the old number
   until the editable install is refreshed:
   ```
   .venv/bin/pip install -e . --no-deps -q
   .venv/bin/pip install -e ./momwire --no-deps -q
   ```

7. **Verify**: with `.venv/bin/python`, import `antennaknobs`, `momwire`, and
   **every** extension found in step 5 (`momwire._accelerators`,
   `momwire._near_interface_accel`, ...); check each `__file__` resolves into
   the source trees (not site-packages) and that `importlib.metadata` versions
   match the pyproject versions.

   Beware that other `_accelerators*.so` can exist on disk without being the
   live one: `setup.py build_ext` leaves a copy under `momwire/build/`, and any
   sibling venv or agent worktree carries its own. None of those is on
   `sys.path`, so trust the imported `__file__` over a bare `find` — and do not
   delete anything as part of a sync, which is a read-and-rebuild operation.

Report: old → new commit for each repo, the per-extension status from step 5
(and whether anything was rebuilt), and the final installed versions.
