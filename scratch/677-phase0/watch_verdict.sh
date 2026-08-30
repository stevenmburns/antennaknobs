#!/bin/bash
# #677 phase-0 verdict watcher: wait for PR 721 to merge, then for the
# merge commit's ci.yml run on main, then report test-slow + dump artifact.
R=stevenmburns/momwire
deadline=$((SECONDS + 4500))

while [ $SECONDS -lt $deadline ]; do
  state=$(gh pr view 721 -R $R --json state --jq .state)
  [ "$state" = "MERGED" ] && break
  [ "$state" = "CLOSED" ] && { echo "VERDICT: PR 721 CLOSED without merge"; exit 1; }
  sleep 60
done
[ "$state" != "MERGED" ] && { echo "VERDICT: timeout waiting for merge (state=$state)"; exit 1; }
sha=$(gh pr view 721 -R $R --json mergeCommit --jq .mergeCommit.oid)
echo "merged as $sha"

run=""
while [ $SECONDS -lt $deadline ]; do
  run=$(gh run list -R $R --branch main --workflow ci.yml --commit "$sha" --json databaseId,status,conclusion --jq '.[0] // empty | "\(.databaseId) \(.status) \(.conclusion)"')
  if [ -n "$run" ]; then
    id=$(echo "$run" | cut -d' ' -f1)
    status=$(echo "$run" | cut -d' ' -f2)
    [ "$status" = "completed" ] && break
  fi
  sleep 120
done
[ -z "$run" ] && { echo "VERDICT: no ci run appeared for $sha (skip-directive check!)"; exit 1; }
[ "$status" != "completed" ] && { echo "VERDICT: timeout; run $id still $status"; exit 1; }

echo "run $id: $(gh run view "$id" -R $R --json conclusion --jq .conclusion)"
gh run view "$id" -R $R --json jobs --jq '.jobs[] | select(.name | test("slow|integration")) | "\(.name): \(.conclusion)"'
arts=$(gh api repos/$R/actions/runs/$id/artifacts --jq '[.artifacts[].name] | join(",")')
if [[ "$arts" == *677* ]]; then
  echo "VERDICT: DUMPS CAPTURED AGAIN — the divergence is NOT fully fixed. Artifacts: $arts"
else
  echo "VERDICT: clean — no 677 dumps on the strict gate's first main run"
fi
