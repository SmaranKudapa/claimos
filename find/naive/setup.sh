#!/usr/bin/env bash
# One-time setup of the Find agent on Naive. Run from the repo root after `naive login`.
#   QUALIFY_AGENT=agt_...  ./naive/setup.sh
#   demo:  QUALIFY_AGENT=agt_... COUNTIES=Lee INCLUDE_CLOSED=1 ./naive/setup.sh
# Optional: TAXFIND_GIT=https://github.com/<team>/taxappeal-find  (else the code is uploaded as a zip)
set -euo pipefail
command -v naive >/dev/null || { echo "install the CLI: npm i -g @usenaive-sdk/cli"; exit 1; }
command -v jq >/dev/null || { echo "needs jq (Mac: brew install jq)"; exit 1; }
: "${QUALIFY_AGENT:?set QUALIFY_AGENT to the Qualify agent id (agt_...) - Find posts cards to its board}"

naive whoami >/dev/null
naive plan show >/dev/null || { echo "your org needs a plan: naive plan show / naive plan set"; exit 1; }

echo "1/5 skill"
naive skill push --slug taxfind-find --file naive/SKILL.md --description "Run and read the taxfind Find program" >/dev/null

echo "2/5 code"
if [ -z "${TAXFIND_GIT:-}" ]; then
  rm -f /tmp/taxappeal-find.zip
  # code only: no data, no run outputs, no secrets
  (cd .. && zip -qr /tmp/taxappeal-find.zip "$(basename "$OLDPWD")" -x '*/data/*' '*/output/*' '*/.git/*' '*/__pycache__/*' \
     '*.egg-info/*' '*/.env' '*/.venv/*' '*/.pytest_cache/*' '*_matched.csv')
  naive file upload --file /tmp/taxappeal-find.zip --name taxappeal-find.zip --title "taxfind code" >/dev/null
fi

echo "3/5 agent"
naive agent apply -f naive/ >/dev/null
AGENT_ID=$(naive agent list | jq -r '.data[] | select(.name=="find") | .id' | head -1)
[ -n "$AGENT_ID" ] && [ "$AGENT_ID" != "null" ] || { echo "could not find the 'find' agent after apply"; exit 1; }
echo "    find agent: $AGENT_ID"

echo "4/5 secrets (injected for their host only; the value never enters the transcript)"
VAULT_ID=$(naive vault list | jq -r '.data[]? | select(.display_name=="find-secrets") | .id' | head -1)
[ -n "$VAULT_ID" ] || VAULT_ID=$(naive vault create --name find-secrets | jq -r .id)
if [ -n "${APIFY_TOKEN:-}" ]; then
  printf '%s' "$APIFY_TOKEN" | naive vault set "$VAULT_ID" --env APIFY_TOKEN --host api.apify.com >/dev/null \
    || echo "    (could not store APIFY_TOKEN - add it to the find-secrets vault in the dashboard)"
fi
if [ -n "${FIND_NAIVE_KEY:-}" ]; then   # a scoped key the program uses to post cards and run data tools
  printf '%s' "$FIND_NAIVE_KEY" | naive vault set "$VAULT_ID" --env NAIVE_API_KEY --host api.vetta.sh >/dev/null \
    || echo "    (could not store NAIVE_API_KEY - the agent will post cards with board_write instead)"
fi

echo "5/5 schedule: every 6 hours at :17, America/New_York"
# Demo options: COUNTIES=Lee runs just those counties (the first statewide pass downloads ~1 GB and takes
# ~25 min); INCLUDE_CLOSED=1 posts cards even though the 2026 filing window has closed.
PROMPT="Run your Find pass now."
[ -n "${COUNTIES:-}" ] && PROMPT="$PROMPT This time run: taxfind run --counties $COUNTIES --handoff board${INCLUDE_CLOSED:+ --include-closed}."
PROMPT="$PROMPT Environment: FIND_DATA_DIR=\$HOME/find-data NAIVE_QUALIFY_BOARD=$QUALIFY_AGENT ${INCLUDE_CLOSED:+FIND_HANDOFF_INCLUDE_CLOSED=1 }${TAXFIND_GIT:+TAXFIND_GIT=$TAXFIND_GIT}"
naive deploy create --agent "$AGENT_ID" --cron "17 */6 * * *" --timezone America/New_York \
  --prompt "$PROMPT" --budget-usd 3 --window immediate | jq '{id, cron, next_run_at}'

echo "done. Trigger a pass now with: naive deploy run <deployment id>"
