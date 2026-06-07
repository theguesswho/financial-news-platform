"""
Daily Score Archiver — archives V2 scores for all stocks into daily_scores table.

Runs once per day (scheduled task) to:
1. Calculate V2 mismatch scores for all stocks
2. Store them in daily_scores table with today's date
3. Enable tracking of "Most Changed This Week" and historical score trends

Idempotent: checks if scores for today already exist before inserting.
"""
from datetime import datetime, date
from pathlib import Path
import os
import sys
import json

# Add project root to path
root = Path(__file__).parent.parent
sys.path.insert(0, str(root))

from dotenv import load_dotenv
load_dotenv(root / ".env", override=True)

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from db.session import get_session
from db.models import Fundamentals, DailyScore, EodPrice
from pipeline.score import compute_v2_score, compute_v2_score_with_breakdown


def archive_daily_scores() -> dict:
    """
    Archive V2 scores for all stocks with fundamentals into daily_scores table.

    Returns dict with:
      - stored: number of scores archived
      - skipped: number of stocks with insufficient data
      - today: the date scores were archived for
      - errors: list of error messages
    """
    session = get_session()
    today = date.today()

    try:
        # Check if we already have scores for today
        existing_count = session.query(DailyScore).filter_by(date=today).count()
        if existing_count > 0:
            print(f"✓ Scores for {today} already archived ({existing_count} stocks)")
            return {
                "stored": existing_count,
                "skipped": 0,
                "today": today.isoformat(),
                "errors": [],
                "note": "Already archived today"
            }

        # Get all stocks with fundamentals
        all_funds = session.query(Fundamentals).all()
        print(f"\n🔄 Archiving V2 scores for {len(all_funds)} stocks...")

        stored = 0
        skipped = 0
        errors = []

        for fund in all_funds:
            try:
                # Calculate V2 score
                v2_score = compute_v2_score(fund, session)

                # If score is 0, it means insufficient data
                if v2_score == 0.0 and not fund.market_cap:
                    skipped += 1
                    continue

                # Also calculate component scores for richer history
                breakdown = compute_v2_score_with_breakdown(fund, session)

                # Create DailyScore record
                daily_score = DailyScore(
                    symbol=fund.symbol,
                    date=today,
                    v2_score=round(float(v2_score), 4),
                    quality_score=round(float(breakdown.get("quality_score", 0)), 4),
                    value_score=round(float(breakdown.get("value_score", 0)), 4),
                    trajectory_score=round(float(breakdown.get("trajectory_score", 0)), 4),
                )

                session.add(daily_score)
                session.flush()
                stored += 1

            except Exception as e:
                error_msg = f"{fund.symbol}: {str(e)}"
                errors.append(error_msg)
                skipped += 1
                session.rollback()
                continue

        # Commit all scores
        session.commit()

        print(f"✓ Stored {stored} scores, skipped {skipped} stocks")
        if errors:
            print(f"⚠ {len(errors)} errors encountered")

        return {
            "stored": stored,
            "skipped": skipped,
            "today": today.isoformat(),
            "errors": errors[:5],  # Return first 5 errors
            "status": "success"
        }

    except Exception as e:
        print(f"✗ Archive failed: {e}")
        session.rollback()
        return {
            "stored": 0,
            "skipped": 0,
            "today": today.isoformat(),
            "errors": [str(e)],
            "status": "failed"
        }
    finally:
        session.close()


def get_most_changed_this_week() -> list[dict]:
    """
    Query most changed stocks (by V2 score) this week.
    Requires at least daily scores for 5 days this week.

    Returns list of dicts with:
      - symbol
      - current_score (today's)
      - week_ago_score
      - change
      - change_pct
    """
    session = get_session()
    today = date.today()
    week_ago = date(today.year, today.month, max(1, today.day - 7))

    try:
        # Get all symbols with scores this week
        symbols_with_scores = session.query(DailyScore.symbol).filter(
            and_(
                DailyScore.date >= week_ago,
                DailyScore.date <= today
            )
        ).distinct().all()

        results = []
        for (symbol,) in symbols_with_scores:
            # Get most recent score (today or closest)
            recent = session.query(DailyScore).filter_by(symbol=symbol).order_by(
                desc(DailyScore.date)
            ).first()

            # Get score from a week ago (or closest)
            week_old = session.query(DailyScore).filter(
                and_(
                    DailyScore.symbol == symbol,
                    DailyScore.date <= week_ago
                )
            ).order_by(desc(DailyScore.date)).first()

            if recent and week_old:
                change = float(recent.v2_score) - float(week_old.v2_score)
                change_pct = (change / float(week_old.v2_score)) * 100 if week_old.v2_score else 0

                results.append({
                    "symbol": symbol,
                    "current_score": float(recent.v2_score),
                    "week_ago_score": float(week_old.v2_score),
                    "change": round(change, 4),
                    "change_pct": round(change_pct, 1),
                    "current_date": recent.date.isoformat(),
                })

        # Sort by absolute change
        results = sorted(results, key=lambda x: abs(x["change"]), reverse=True)
        return results[:20]  # Top 20 most changed

    finally:
        session.close()


if __name__ == "__main__":
    result = archive_daily_scores()
    print(f"\n📊 Daily Score Archive Complete")
    print(f"   Stored: {result['stored']}")
    print(f"   Skipped: {result['skipped']}")
    print(f"   Date: {result['today']}")

    if result.get("errors"):
        print(f"   Errors: {len(result['errors'])}")
        for err in result['errors'][:3]:
            print(f"     - {err}")

    # Show most changed
    print(f"\n📈 Most Changed This Week:")
    most_changed = get_most_changed_this_week()
    for i, stock in enumerate(most_changed[:5], 1):
        direction = "↑" if stock["change"] > 0 else "↓"
        print(f"   {i}. {stock['symbol']:6} {stock['current_score']:.3f} (was {stock['week_ago_score']:.3f}) {direction} {stock['change_pct']:+.1f}%")
