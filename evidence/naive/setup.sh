#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v naive >/dev/null || { echo "install the CLI: npm i -g @usenaive-sdk/cli"; exit 1; }
command -v jq >/dev/null || { echo "needs jq"; exit 1; }
: "${EVIDENCE_AGENT_NAME:?set EVIDENCE_AGENT_NAME to the agent name the coordinator uses for the evidence step}"
naive whoami >/dev/null
echo "1/4 bundle"
rm -f /tmp/claimos-evidence.zip
zip -qr /tmp/claimos-evidence.zip find/taxfind find/pyproject.toml evidence/claimevidence evidence/pyproject.toml \
  -x '*/__pycache__/*' '*.egg-info/*'
FID=$(naive file upload --file /tmp/claimos-evidence.zip --name claimos-evidence.zip --title "Claim OS Find + Evidence code" | jq -r .id)
echo "    file: $FID"
echo "2/4 skill"
naive skill push --slug claimos-evidence --file evidence/naive/SKILL.md --description "Run and read the Claim OS Evidence program" >/dev/null
echo "3/4 agent"
work=$(mktemp -d)
mkdir -p "$work/naive"
sed "s/__EVIDENCE_FILE_ID__/$FID/g" evidence/naive/evidence.system.md > "$work/naive/evidence.system.md"
sed "s/__EVIDENCE_AGENT_NAME__/$EVIDENCE_AGENT_NAME/g" evidence/naive/evidence.agent.yaml > "$work/naive/evidence.agent.yaml"
(cd "$work" && naive agent apply -f naive/) | jq -c '.data[] | {name, id, version, action}'
echo "4/4 verify"
AID=$(naive agent list --limit 100 | jq -r --arg n "$EVIDENCE_AGENT_NAME" '.data[] | select(.name==$n) | .id' | head -1)
naive agent show "$AID" | jq -c --arg f "$FID" '{id, version: .current_version, uses_bundle: (.system | contains($f)), tools: [.tools.configs | to_entries[] | select(.value.enabled) | .key]}'
