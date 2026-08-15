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

5. **Rebuild the accelerator if stale**: compare mtimes of
   `momwire/src/momwire/_accelerators.cpp` and the
   `_accelerators.cpython-*.so` next to it. If the `.cpp` is newer (or the
   `.so` is missing), rebuild in place:
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
   `momwire._accelerators`; check each `__file__` resolves into the source
   trees (not site-packages) and that `importlib.metadata` versions match the
   pyproject versions.

Report: old → new commit for each repo, whether the `.so` was rebuilt, and
the final installed versions.
