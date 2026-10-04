#!/usr/bin/env bash
# Post-deploy fleet-convergence check for a Fly app (issue #403).
#
# A green `flyctl deploy` does NOT prove the fleet converged: flyd can revert
# a machine's update several seconds AFTER flyctl declares it healthy (the
# revert restores the old image, whose app also passes health checks). One
# machine of the simulator pair silently rejected every deploy for three
# releases this way — the edge then load-balanced users between two app
# versions, and a page could even fetch new index.html from one machine and
# 404 its hashed asset on the other.
#
# Usage: verify_fly_fleet.sh <fly-app-name> <public-base-url>
# Needs: flyctl (authed via FLY_API_TOKEN), jq, curl.
# FLEET_SETTLE_SECONDS overrides the post-deploy settle wait (default 30).
# tests/test_verify_fly_fleet.py runs this script against a fake flyctl and
# curl; it never talks to Fly.
set -euo pipefail

app=$1
url=${2%/}

# Let any pending flyd revert land before we look (observed ~6-10 s after
# "Machine ... is now in a good state").
sleep "${FLEET_SETTLE_SECONDS:-30}"

want=$(flyctl releases -a "$app" --json | jq -r '.[0].ImageRef')
tag=${want##*:}
machines=$(flyctl machines list -a "$app" --json)

echo "release image: $want"
jq -r '.[] | "machine \(.id) region=\(.region) state=\(.state) image=\(.image_ref.tag)"' <<<"$machines"

# Which machines count as converged (AK#405, for a fleet whose idle regions
# suspend). A rolling deploy updates EVERY machine's image, including one that
# is not running: a stopped machine is updated and stays stopped, and a
# suspended one is updated and left stopped, its memory snapshot discarded
# because it belongs to the old image. Fly:
#   https://fly.io/docs/reference/suspend-resume/ ("deployments rebuild the
#     machine image, which invalidates the old snapshot" -- a cold start next)
#   https://community.fly.io/t/dashboard-fly-toml-not-updating-after-deploy-machines-still-stopping-instead-of-suspending/27115
#     (Fly staff, 2026-02-12: "Stopped Machines stay stopped, and ones in
#     the suspended state transition to stopped")
# So a machine converged if it is ON the release image, whatever its state
# among started / stopped / suspended (or on the way between them). The image
# is the test, not the state: a reverted machine (#403) is back on the OLD
# image, running or not, and fails here either way. A machine in any other
# state (failed, replacing, destroying, created) has not settled and fails.
#
# .image_ref is the image the machine is ACTUALLY on (post-revert it differs
# from .config.image, which only records what the update requested).
settled='["started","stopped","suspended","starting","stopping","suspending"]'
bad=$(jq -r --arg tag "$tag" --argjson settled "$settled" '
  .[] | select(.image_ref.tag != $tag or (.state as $s | $settled | index($s) | not))
  | "\(.id) (\(.region)): state=\(.state) image=\(.image_ref.tag)"' <<<"$machines")
if [ "$(jq 'length' <<<"$machines")" -eq 0 ]; then
  echo "::error::fleet did not converge: the app lists no machines"
  exit 1
fi
if [ -n "$bad" ]; then
  echo "::error::fleet did not converge on $tag; these machines are not on it, or have not settled (flyd revert? see issue #403 -- replace the stuck machine with 'fly machine clone' + 'fly machine destroy', then re-run this workflow):"
  echo "$bad"
  exit 1
fi

# Edge smoke: the page and the hashed asset it references must be servable
# end to end through the load balancer. Sampled a few times so a skewed
# fleet (should the count ever grow past one machine) can't hide behind a
# lucky first request.
for _ in 1 2 3 4; do
  page=$(curl -fsS "$url/")
  asset=$(grep -oE '(assets|_astro)/[A-Za-z0-9._@-]+\.(js|css)' <<<"$page" | head -1 || true)
  if [ -n "$asset" ]; then
    curl -fsS -o /dev/null "$url/$asset" \
      || { echo "::error::$url/ references $asset but fetching it failed"; exit 1; }
  fi
done
echo "fleet converged on $tag and $url serves consistently"
