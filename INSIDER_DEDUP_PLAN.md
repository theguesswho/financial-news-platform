# insider_trades — duplicate fix (design, 3 Nov 2026)

Status: **designed and harness-tested on branch `insider-dedup-swap`; NOT
approved, NOT run on prod, NOT on main.** Merging the branch into main and
pushing IS the run: the swap executes at the first scheduler start-up after
the push (db/migrate.py). Edmund decides when.

## 1. Is it a scoring change? No.

Every reader of `insider_trades`, traced in code on 3 Nov:

| Reader | What it does with the rows | Feeds a score, band, verdict or ledger? |
|---|---|---|
| pipeline/brief.py | 14-day cluster buys (`COUNT(*)` labelled "insiders", `SUM(total_value)`), notable buys and sells | No — the brief is an output; nothing in the pipeline reads `daily_briefs` content back (only the sentinel's MAX(date)) |
| api/routers/stocks.py | stock page: per person per day `SUM(shares)`, `SUM(total_value)` | No — product display |
| ui/Home.py, ui/pages/4_Insiders.py, 5_Stock_Detail.py | Streamlit lab views | No |
| pipeline/freshness_sentinel.py | `MAX(created_at)` | No |

Not readers: the scorer (hidden_gem_scorer, score.py, quality_v3), the
assessor's context (qual_assessor.get_stock_context), the narrative ledger
and checkpoints, the session report, the wire (api/routers/wire.py says
"insiders stay off"). deep_dive.py uses Yahoo's `heldPercentInsiders`, a
different field. So no before/after board is needed and the freeze ritual
does not apply. If a future change makes insider data a scoring input, that
change carries the ritual.

## 2. The numbers (prod, read-only, 3 Nov 2026)

| | |
|---|---|
| Rows | 2,136,629 (424 MB) |
| Real trades (full trade key = whole row) | 22,522 |
| Distinct under the model's old five-column key | 21,249 — it would merge 1,273 real same-day lots of equal size |
| Rows with a blank in the key | 274 |
| Duplicate copies | 2,114,107, first written 1 Jun 2026 (the table's first day) |
| Ids | not unique: 21,003 distinct ids among the 22,522 first copies (the July migration reset the sequence) |
| Indexes / primary key / constraints | none (only NOT NULL) |
| Copies written per day | ~17,500 while two schedulers ran; ~8,400 since 2 Nov |

Trade key: `symbol, person_name, transaction_date, transaction_type, shares,
price_per_share, shares_owned_after, form4_url`, unique NULLS NOT DISTINCT.

## 3. The swap (db/migrate.py `_insider_dedup_swap`)

1. Drop any leftover `insider_trades_dedup_new` (ours, from an interrupted try).
2. Build `insider_trades_dedup_new` from one REPEATABLE READ snapshot: the
   first copy of each trade, ids renumbered 1..N in first-seen order (no
   reader uses the id; the sequence stands at 2,249,905, far above).
   Only reads the live table — readers and the writer are never blocked.
3. On the copy: primary key, unique trade key, (symbol, transaction_date)
   index, ANALYZE.
4. Swap in one transaction with `lock_timeout = 3s`, up to 5 tries 10 s apart:
   LOCK ACCESS EXCLUSIVE; copy rows written since the snapshot (ON CONFLICT
   DO NOTHING); rename live → `insider_trades_pre_dedup_<yyyymmdd>`; rename
   copy → `insider_trades`; move the sequence's ownership to the new table.
   A queued exclusive lock blocks every reader behind it (the 09-14 lesson),
   so the wait is capped at 3 s per try.
5. If the lock never comes: drop the copy, raise; the live table is
   untouched and the step is named as failed in the start-up log; it
   retries at the next start-up.

Measured on the throwaway cluster at prod scale (2,137,500 rows): copy and
keys 5.3 s without any lock; exclusive lock 0.13 s. Prod disk is slower;
budget ~30 s for the copy, still lock-free.

Code that ships with it: `pipeline/insider.py` inserts one statement per
filing with ON CONFLICT DO NOTHING (an already-stored trade is a no-op; the
"added" count is real). `db/models.py` carries the same key and index.
Companion, droppable commit: the brief's cluster line counts distinct people
(`COUNT(DISTINCT person_name)`), not rows.

Proof: `scripts/test_insider_swap.py` 16/16 — one row per real trade, none
lost (blanks compared as equal), rollback copy complete, keys present,
sequence owned and above every id, brief-style sums equal true sums (30x too
high before on the test data), a trade written mid-build is carried over and
its duplicate skipped, the writer adds only new trades, a long reader makes
the swap give up cleanly (a reader arriving meanwhile waited 2.1 s), the
same swap then succeeds, the documented rollback restores the table and
stops the step from re-running, DDL lint clean.

## 4. Running it (when Edmund says)

- Window: no scheduler slot within 10 min (deploy gate), Edmund at the
  Railway dashboard. Merge `insider-dedup-swap` into main, push.
- Healthy: deploy log `migrate: insider_trades swapped: {...}` with
  `trades_kept` ≈ 22.5k and `lock_s` < 1, then `migrate: N checked, 1 applied`.
- Read-back: `SELECT COUNT(*)` ≈ trades on record; the unique key exists;
  `/health/platform` 200; a stock page with insider rows renders; next
  06:00 step 3 note shows a small "N insider records added", not ~8,400.
- Space: the rollback copy holds 424 MB until dropped — drop only on
  Edmund's word after a week of clean runs:
  `DROP TABLE insider_trades_pre_dedup_<yyyymmdd>;`

Rollback (any time before that drop):

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
ALTER TABLE insider_trades RENAME TO insider_trades_dedup_rolledback;
ALTER TABLE insider_trades_pre_dedup_<yyyymmdd> RENAME TO insider_trades;
ALTER SEQUENCE insider_trades_id_seq OWNED BY insider_trades.id;
COMMIT;
```

The presence of `insider_trades_dedup_rolledback` stops the swap from
re-running at the next start-up. Trades written to the new table between
swap and rollback are in `insider_trades_dedup_rolledback` and can be copied
back with ON CONFLICT DO NOTHING if wanted.

## 5. Not in this fix (separate decisions)

- Incremental Form 4 fetch (only filings newer than the last stored one,
  full 90-day sweep weekly) — the runtime fix for the 101-minute step.
- The writer's "individuals only" name filter lets corporate 10% holders
  through: the CRBG and DVA items below were Nippon Life Insurance Co and
  Berkshire Hathaway Inc. Whether those belong in an "insider" signal is a
  methodology call.
- The brief model named CRBG "Chubb" (2 Nov) and "Cimpress" (1 Nov):
  the brief is given tickers without company names.

## 6. Note to readers (DRAFT — not published)

> **Correction: insider buying and selling figures (June – November 2026)**
>
> Our daily brief and the insider section of each company page overstated
> insider trading totals from June until [fix date]. A storage fault saved
> each Form 4 trade many times — a trade from three weeks earlier could be
> counted 20 times or more — and our totals added up every copy. The trades
> themselves were real; their number, their dollar value and the count of
> people involved were inflated — by more than ten times for recent activity.
>
> Examples. On 31 Oct, 1 Nov and 2 Nov the brief led with Corebridge
> Financial (CRBG): "83", "110" and "119 insiders" buying USD 616 million,
> 826 million and 897 million. In fact it was one filer, Nippon Life
> Insurance Co, a large shareholder rather than an executive, making
> 9 purchases worth USD 70.3 million in total. Those items also named the
> company wrongly, as "Chubb" and "Cimpress". The 1 Nov brief also reported
> a USD 345 million drawdown at DaVita (DVA); it was a single sale of
> USD 69.0 million by Berkshire Hathaway Inc.
>
> Insider figures never entered our scores, tiers or written assessments, so
> no rating changes. The stored data has been corrected, insider buying is
> now counted once per trade, and a "cluster" now means two or more
> different people. We are sorry for the error.

(Numbers re-derived 3 Nov from the rows each brief saw, counting each real
trade once. Fill in the fix date when it runs.)
