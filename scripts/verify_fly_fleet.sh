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
jq -r '.[] | "machine \(.id) state=\(.state) image=\(.image_ref.tag)"' <<<"$machines"

# .image_ref is the image the machine is ACTUALLY running (post-revert it
# differs from .config.image, which only records what the update requested).
if ! jq -e --arg tag "$tag" 'length > 0 and all(.[]; .image_ref.tag == $tag)' \
    <<<"$machines" >/dev/null; then
  echo "::error::fleet did not converge: a machine is not running $tag (flyd revert? see issue #403 — replace the stuck machine with 'fly machine clone' + 'fly machine destroy', then re-run this workflow)"
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
