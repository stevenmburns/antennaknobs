---
name: release
description: Cut an antennaknobs release — release PR ritual (version bump + site refresh), tag, and the three deploy pipelines
---

# Cut an antennaknobs release

antennaknobs deploys **from release tags, not from every merge**: cutting a
release publishes to PyPI AND deploys the same tagged commit to the hosted
simulator and the docs site (both on Fly.io). The version number always names
exactly what is running.

## If this release adopts a new momwire

Do the momwire-pin upgrade first (its own PR, or the first commit of the
release PR). Three places, one commit — all of them, every time:

1. `pyproject.toml` → `momwire==X.Y.Z` (EXACT pin, never a floor)
2. `Dockerfile` → `pip install "momwire==X.Y.Z"`
3. The `momwire` submodule pointer → checkout the release's bump commit,
   `git add momwire`. CI won't catch a stale pointer (`--remote`); a fresh
   dev clone silently loses its editable momwire to the PyPI wheel
   (learned in PRs #268/#270 — see the README's drift check).

Wait for PyPI to serve the momwire version before opening the PR (the
wheel-smoke job races the publish, ~9 min after the momwire tag). If the
upgrade changes solver behavior on an unqualified request path, latency-smoke
the defaults; expensive models stay opt-in (the 0.6.0 near-miss).

## Release PR ritual

Cut the release via a PR (precedent: v0.18.0 PR #265, v0.19.0 PR #269), not a
direct push. In one commit, `chore: release vX.Y.Z (<theme>)`:

1. Bump `version = "X.Y.Z"` in `pyproject.toml`.
2. Refresh the **what's-new Card** in `site/src/content/docs/index.mdx`
   (version + highlights — a stale "new" box is worse than none).
3. **De-stale the docs site**: if solver/ground/CLI behavior changed since the
   last release, sweep `site/src/content/docs/` for pages describing the old
   behavior (`solver.md`, `web.md`, `cli.md`, the concepts pages). `site/` is
   NOT touched by feature PRs and is easy to forget — v0.19.0 found six stale
   pages this way.
4. Build the site (`cd site && npm run build`) — it must pass before the PR.

Merge with `/merge-pr` (rebase, CI green first).

## Tag and verify

1. On the merged main: `git tag vX.Y.Z && git push origin vX.Y.Z`.
2. The tag fires THREE pipelines — watch all of them to completion:
   - `publish` → PyPI (Trusted Publishing) + auto-created GitHub release
     (generated notes from PR titles; do NOT `gh release create` manually)
   - `Deploy simulator to Fly.io`
   - `Deploy docs site to Fly.io`
3. Verify: PyPI serves X.Y.Z
   (`curl -s https://pypi.org/pypi/antennaknobs/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"`)
   and `gh release view vX.Y.Z` lists the expected PRs.

For off-cycle docs-page fixes without a release:
`gh workflow run deploy-docs.yml --ref main`.
