"""
Single source of truth for tier thresholds (V2 #6 — duplication caused the
134-vs-44 board bug in v1).

v2 cutoffs are calibrated from the v2 score distribution at cutover
(2026-07-22) targeting a board of ~40-50 of ~600 like v1's. Recalibrate here
and ONLY here.
"""

# Calibrated 2026-07-22 on the first full v2 distribution (universe 605):
# score #10 = 0.460, #30 = 0.359, #45 = 0.340 → ~10 Strong Buy / ~29 Buy+ /
# ~45 on board, matching v1's board size.
STRONG_BUY = 0.46
BUY        = 0.36
WATCH      = 0.34


def fmt10(score, dp: int = 1) -> str:
    """Display convention (user 2026-08-01): scores render on a 10-point
    scale — 0.588 shows as 5.9. Internal math stays 0–1; this is the ONLY
    place the transform lives."""
    if score is None:
        return "—"
    return f"{float(score) * 10:.{dp}f}"


def tier_for(score):
    if score is None:
        return None
    s = float(score)
    if s > STRONG_BUY: return "Strong Buy"
    if s > BUY:        return "Buy"
    if s > WATCH:      return "Watch"
    return None
