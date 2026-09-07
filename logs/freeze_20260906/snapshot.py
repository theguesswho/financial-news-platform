import sys, json, os
sys.path.insert(0, "/Users/eha/Desktop/financial-news-platform")
from dotenv import load_dotenv
load_dotenv("/Users/eha/Desktop/financial-news-platform/.env", override=True)
from pipeline.hidden_gem_scorer import get_engine, score_all_stocks, compute_gap_score
from pipeline.quality_v3 import compute_p3_universe
from sqlalchemy import text
tag = sys.argv[1]
eng = get_engine()
res = score_all_stocks(eng)
p3 = compute_p3_universe(eng)
gap = compute_gap_score(eng)
with eng.connect() as c:
    fund = {r[0]: dict(zip(["rev","earn","fcf","gm","om","roe","de","fetched_at","qt"], r[1:]))
            for r in c.execute(text("SELECT symbol, revenue_growth_yoy, earnings_growth_yoy, fcf_growth_yoy, gross_margin, operating_margin, roe, debt_to_equity, fetched_at, quarterly_trends FROM fundamentals")).fetchall()}
    hm = {r[0]: {"maxdate": str(r[1]), "n": r[2], "rev_ttm": r[3]} for r in c.execute(text("""
        SELECT symbol, MAX(date), COUNT(*), (SELECT SUM(revenue) FROM (SELECT revenue FROM historical_metrics h2 WHERE h2.symbol=h.symbol AND revenue IS NOT NULL AND revenue>0 ORDER BY date DESC LIMIT 4) q)
        FROM historical_metrics h GROUP BY symbol""")).fetchall()}
def _j(o):
    from decimal import Decimal
    import datetime
    if isinstance(o, Decimal): return float(o)
    if isinstance(o, (datetime.date, datetime.datetime)): return str(o)
    return str(o)
json.dump({"results": res, "p3": p3, "gap": gap, "fund": fund, "hm": hm}, open(f"{os.path.dirname(__file__)}/snap_{tag}.json","w"), default=_j)
print("saved", tag, len(res))
