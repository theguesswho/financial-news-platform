"""
Batch deep dive runner — generates (or refreshes) deep dives for all stocks
currently on the home page leaderboard.

Run manually:  python -m pipeline.deep_dive_batch
Scheduled:     called from weekly_deep_refresh() in scheduler.py

Only generates for stocks at Watch tier or above (same gate as the home page).
Skips stocks whose cached memo is still valid (no new filing since last run).
"""
import time
from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv(override=True)


def run_batch(engine, force: bool = False) -> dict:
    from pipeline.hidden_gem_scorer import score_all_stocks
    from pipeline.deep_dive import generate_deep_dive, create_table

    create_table(engine)

    def tier_for(s):
        if s > 0.58: return "Strong Buy"
        if s > 0.46: return "Buy"
        if s > 0.34: return "Watch"
        return None

    gems   = score_all_stocks(engine)
    stocks = sorted(
        [g for g in gems if tier_for(g["hidden_gem_score"]) is not None],
        key=lambda g: -g["hidden_gem_score"],
    )

    print(f"  Running deep dives for {len(stocks)} home-page stocks…\n")

    results   = {"generated": 0, "cached": 0, "errors": 0, "buffett": []}
    DELAY     = 1.5  # seconds between API calls to avoid rate limits

    for i, g in enumerate(stocks, 1):
        sym = g["symbol"]
        try:
            memo = generate_deep_dive(engine, sym, force=force)
            tier = memo.get("buffett_tier", "")
            rat  = memo.get("buffett_rationale", "")

            cached_note = ""
            if memo.get("_meta", {}).get("generated_at"):
                # If generated_at matches a very recent time it was just created;
                # otherwise it came from cache. Simplest proxy: check generate call itself.
                pass

            icon = {"Buffett Stock": "🏆", "Potential Buffett": "⭐", "No Buffett": "–"}.get(tier, "?")
            print(f"  [{i:2d}/{len(stocks)}] {sym:<6}  {icon} {tier:<18}  {rat[:70]}")

            if tier == "Buffett Stock":
                results["buffett"].append(sym)
            results["generated"] += 1

        except Exception as exc:
            print(f"  [{i:2d}/{len(stocks)}] {sym:<6}  ERROR: {exc}")
            results["errors"] += 1

        if i < len(stocks):
            time.sleep(DELAY)

    print(f"\n  Done — {results['generated']} memos, {results['errors']} errors")
    if results["buffett"]:
        print(f"  🏆 Buffett Stocks: {', '.join(results['buffett'])}")
    else:
        print("  No stocks reached Buffett Stock tier")

    return results


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from pipeline.hidden_gem_scorer import get_engine
    engine  = get_engine()
    force   = "--force" in sys.argv
    run_batch(engine, force=force)
