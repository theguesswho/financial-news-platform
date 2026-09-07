# Freeze evidence — V3 #20 (growth block → FMP) + #21 (historical_metrics repair)

Snapshots (snapshot.py = real scorer: score_all_stocks + compute_p3_universe + compute_gap_score, plus fundamentals/historical_metrics rows):
- snap_before.json  2026-09-06 21:18 SGT — historical_metrics dead, growth on Yahoo
- snap_mid.json     2026-09-06 21:44 SGT — after #21 refresh only (same evening; = #21 alone)
- snap_mid2.json    2026-09-07 18:15 SGT — after the 06:00 UTC daily (prices/Yahoo drift), before the FMP re-home
- snap_after.json   2026-09-07 19:23 SGT — after #21 + #20 (= #20 alone vs mid2)
- snap_after_s44_1917.json — the earlier session's after-snapshot, kept for reference

DIFF_20260907.txt — diff3.py output (membership, tier flips, growth multipliers, historical_metrics → value/gap moves).
hm_refresh.log / growth_rehome*.log — the live-DB runs (#21 refresh 2026-09-06; #20 re-home 2026-09-07, run 1 hit a Railway proxy drop at ~530, run 2 completed 828 written / 3 FMP-empty / 0 errors).
