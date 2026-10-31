#!/bin/bash
# Export the 22–31 Oct 2026 incident logs (V3 #28) before Railway retention
# ages them out. Run once `railway whoami` shows an account.
#   scripts/export_railway_logs.sh [since] [until]
set -u
SINCE="${1:-2026-10-22T00:00:00Z}"
UNTIL="${2:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
OUT="$(git rev-parse --show-toplevel)/logs/incident_2026-10-22"
mkdir -p "$OUT"
railway whoami >/dev/null 2>&1 || { echo "railway CLI is logged out — run: railway login"; exit 1; }
for svc in financial-news-platform api impartial-heart web; do
  echo "exporting $svc $SINCE → $UNTIL"
  railway logs --service "$svc" --since "$SINCE" --until "$UNTIL" > "$OUT/$svc.log" 2>"$OUT/$svc.err" || true
  wc -l < "$OUT/$svc.log" | xargs echo "  lines:"
done
grep -h "E_DIAG" "$OUT"/*.log > "$OUT/E_DIAG.log" 2>/dev/null || true
grep -hE "✗|Traceback|credit balance|Limit Reach|HTTP 429" "$OUT/financial-news-platform.log" > "$OUT/failures.log" 2>/dev/null || true
echo "E_DIAG lines: $(wc -l < "$OUT/E_DIAG.log")  | failure lines: $(wc -l < "$OUT/failures.log")"
echo "done → $OUT (commit these files; they are the incident record)"
