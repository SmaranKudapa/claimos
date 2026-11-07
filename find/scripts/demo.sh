#!/usr/bin/env bash
# Hackathon demo: one full Find cycle on one county, end to end, no keys needed.
#   ./scripts/demo.sh            (Lee County)
#   ./scripts/demo.sh Collier
# With APIFY_TOKEN / NAIVE_API_KEY set, it uses real Zillow/Redfin lookups and real board cards.
set -euo pipefail
COUNTY="${1:-Lee}"
export FIND_DATA_DIR="${FIND_DATA_DIR:-./data}"

if [ -z "${APIFY_TOKEN:-}" ] && [ -z "${NAIVE_REAL_ESTATE_TOOL:-}" ]; then
  PROVIDERS=mock;  echo "no APIFY_TOKEN / NAIVE_REAL_ESTATE_TOOL: home values are MOCK (labelled 'mock' in every record)"
else
  PROVIDERS="${FIND_AVM_PROVIDERS:-naive,apify_zillow,apify_redfin}"
fi
DRY=""; [ -z "${NAIVE_API_KEY:-}" ] && { DRY="--dry-run"; echo "no NAIVE_API_KEY: board cards go to $FIND_DATA_DIR/naive_outbox.jsonl"; }
export NAIVE_QUALIFY_BOARD="${NAIVE_QUALIFY_BOARD:-agt_qualify_demo}"

echo; echo "== 1. what the state has published"; taxfind sources | grep -i -E "^[0-9]{2}  $COUNTY " || true
echo; echo "== 2. one Find cycle: ingest -> detect -> owners -> second opinion -> store -> hand off"
taxfind run --counties "$COUNTY" --avm-providers "$PROVIDERS" --max-avm 50 --handoff board --include-closed $DRY | tee /tmp/find_demo.json
RUN=$(grep -o -m1 '^\[[A-Z]*-[0-9TZ]*\]' /tmp/find_demo.json | tr -d '[]')
OUT="$FIND_DATA_DIR/out/$RUN"
echo; echo "== 3. top 5 cases handed to Qualify"
python3 - "$OUT/candidates.jsonl" <<'EOF'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
rows = sorted((r for r in rows if r["tier"] in ("strong", "possible")), key=lambda r: -r["estimate"]["annual_savings"])
for r in rows[:5]:
    p, e, s = r["property"], r["estimate"], r["signals"]
    print(f"  {p['address']}{' #'+p['unit'] if p.get('unit') else ''}, {p['city']}  {p['use']:<13} "
          f"county ${r['values']['just_value']:>10,.0f} -> ${e['defensible_value']:>10,.0f}  "
          f"~${e['annual_savings']:>6,.0f}/yr  neighbors {s['neighbor_ratio']:.2f}  sales {s['sales_ratio']:.2f}  check {r['avm_check']}")
print(f"  ... {len(rows):,} strong/possible cases in this county")
EOF
echo; echo "== 4. second opinion (Zillow/Redfin/Naive or mock) and hand-off"
python3 -c "
import json; s=json.load(open('$OUT/summary.json'))
for c in s['counties']:
    a=c.get('avm',{}); print('  looked up', a.get('looked_up',0), 'from cache', a.get('from_cache',0), 'checks', a.get('checks'), 'providers', a.get('providers'), 'spend \$%.2f' % a.get('spend_usd',0))
print('  hand-off:', s.get('handoff'))
"
echo; echo "== 5. self-check on sales the screen never saw"
python3 -c "
import json; s=json.load(open('$OUT/summary.json'))
for c in s['counties']:
    h=c['holdout']; f=h['flagged_sold_below_value']; o=h['others_sold_below_value']
    print(f\"  {c['county']}: status {h['status']}; flagged homes that sold went below county value {f:.0%} of the time vs {o:.0%} for the rest (n={h['flagged_sold']})\" if f is not None and o else f\"  {c['county']}: {h['status']} (too few later sales)\")
"
echo; echo "== 6. files: $OUT/candidates.csv  $OUT/candidates.jsonl  $OUT/summary.json"
[ -n "$DRY" ] && echo "   Naive requests that would have been sent: $(wc -l < "$FIND_DATA_DIR/naive_outbox.jsonl") (see naive_outbox.jsonl)"
