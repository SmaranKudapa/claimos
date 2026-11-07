#!/usr/bin/env bash
# Everything after `naive login`, in one go:  bash naive/go.sh
# Optional: QUALIFY_AGENT=agt_... (default: your org's orchestrator), APIFY_TOKEN=..., COUNTIES=Lee
set -euo pipefail
cd "$(dirname "$0")/.."
chmod +x naive/setup.sh scripts/demo.sh 2>/dev/null || true

echo "== checking login"
naive whoami >/dev/null || { echo "not logged in: printf '%s' \"YOUR_KEY\" | naive login"; exit 1; }

if [ -z "${QUALIFY_AGENT:-}" ]; then
  QUALIFY_AGENT=$(naive agent list | jq -r '.data[] | select(.metadata.role=="orchestrator") | .id' | head -1)
  [ -n "$QUALIFY_AGENT" ] && [ "$QUALIFY_AGENT" != "null" ] || { echo "no Qualify/orchestrator agent found; set QUALIFY_AGENT=agt_..."; exit 1; }
  echo "== no Qualify agent given: cards go to the orchestrator's board ($QUALIFY_AGENT)"
fi

echo "== setting up the Find agent"
QUALIFY_AGENT="$QUALIFY_AGENT" COUNTIES="${COUNTIES:-Lee}" INCLUDE_CLOSED=1 ./naive/setup.sh

AGENT_ID=$(naive agent list | jq -r '.data[] | select(.name=="find") | .id' | head -1)
DEP_ID=$(naive deploy list | jq -r --arg a "$AGENT_ID" '[.data[] | select(.agent_id==$a)] | .[0].id')
echo "== find agent: $AGENT_ID   deployment: $DEP_ID"

echo "== starting a run now"
naive deploy run "$DEP_ID" | jq '{id, status}' || true

cat <<EOF

Done. Watch it with:
  naive session list --agent $AGENT_ID
  naive agent spend $AGENT_ID
EOF
