# fct_price_daily

## Purpose

Give the site one price per security per trade day, and a number that
turns a lot quantity from one date into another date. The site computes
the value of a portfolio from this table and its own lots. BigQuery does
the shared, expensive part once. The site does the cheap, per user part.

## Grain

**One row per exchange, security and trade day.**
Key: `exchange | sec_id | trade_date`.

Today the only exchange is MOEX and the only board is TQBR. One row in
staging for board TQBR is one row here. On a day without an official
price `close_price` is null. See rule 1.

This is a periodic snapshot fact: keys `exchange`, `sec_id` and
`trade_date`, measures `close_price` and `split_cum_factor`.
`dim_security` from the listing is its dimension. See `CONVENTIONS.md`
for the marts layer.

The exchange is in the key from day one, because the same ticker on two
exchanges is two different prices in two currencies. The ticker stays
local to its exchange. The global id is ISIN, it belongs to
`dim_security` when a source for it exists.

Board is an attribute, not part of the key. A security is loaded from
one main board only. If a second board of the same security appears in
the history, the `unique` test on the key goes red, and the model must
filter it out.

## Inputs

| Input | Role |
|---|---|
| `stg_moex_history` | price per security and day, board TQBR only |
| `stg_moex_splits` | split events: `sec_id`, `trade_date`, `split_before`, `split_after` |

## Columns

| Column | Definition |
|---|---|
| `price_key` | `exchange \| sec_id \| trade_date`, surrogate key |
| `exchange` | exchange code, `MOEX` for now. Part of the key |
| `board` | board on the exchange, `TQBR` for now. Attribute, not key |
| `sec_id` | ticker, local to the exchange |
| `trade_date` | trade day, taken from `dt` in staging (the GCS path) |
| `currency` | ISO code of the price currency. MOEX gives `SUR` for roubles, mapped to `RUB` here |
| `close_price` | official close price as the exchange defines it. For MOEX this is `legal_close_price` in staging, not `close_price` (the last trade). Null when the exchange gave none |
| `split_cum_factor` | product of `split_after / split_before` over all splits of the security with split date **not later than** `trade_date`. Equals 1 when there are no splits yet |
| `extracted_at` | when the extract script wrote the source file to GCS, from staging |
| `updated_at` | when dbt last wrote this row, `current_timestamp()` of the run. See rule 8 |

## Rules

1. **Why MOEX `legal_close_price` and not MOEX `close_price`.** Trading
   stops for a few days before a split. On those days the last trade
   price is null and `volume` is 0, but the official close keeps the
   last official price. With the last trade price the value of
   a portfolio would have holes exactly around splits. The fact calls
   this column `close_price`, the exchange specific name stays in
   staging.

   The official close is null in about 2 percent of staging rows
   (16 951 of 875 357 on 09.09.2026). Checked: these are illiquid
   securities on days without trades, `close_price` is null there too,
   and the exchange stopped listing most of them on TQBR in 2023.

   **The fact stores what the exchange gave.** No price means null,
   not zero and not the last known price. Both would be invented
   numbers, and zero breaks the future invariant tests on prices. What
   a missing price means for a position is a rule of the consumer, see
   rule 3. One row in 2021 has trades but no official price. It is
   a known single case and stays null.
2. **No adjusted price in this table.** A price series "in today's units"
   changes back in time on every new split. `split_cum_factor` for a past
   date does not change when a future split appears. So the model can be
   incremental by date.
3. **How the site uses the factor.** For a lot opened on `d0` with
   quantity `qty0`, the quantity on date `d` is
   `qty0 * K(d) / K(d0)`, where `K` is `split_cum_factor`. Splits before
   `d0` are in both numbers and cancel out. `K(d0)` and the price on
   a trade day are an exact match on `sec_id` and `trade_date`. Only when
   `d0` is not a trade day (a lot opened on a weekend) the site takes the
   last row not later than `d0`.

   **Missing price is a site rule, not a warehouse rule.** Decision of
   Igor, 09.09.2026: no price means the position cannot be valued fairly,
   the security is illiquid, the position is valued at zero on that day.
   The site does `coalesce(close_price, 0)`. The fact keeps null,
   so the rule can change later (for example carry for 30 days) without
   touching this model. Side effect to know: a security with one quiet
   day makes the portfolio chart dip to zero and back.
4. **Split date.** The date in the splits source is the first trade day
   at the new price. Checked on PLZL: 26.03.2025 is 19 011.5,
   27.03.2025 is 1 867.6, split date is 27.03.2025. So the factor
   changes **on** the split date, and prices before it are old units.
5. **Product in SQL.** BigQuery has no product aggregate. Use
   `exp(sum(ln(split_after / split_before)))` and round to 6 decimals,
   or the result is 9.999999 instead of 10. This lives in a macro,
   because the same factor is needed in the acceptance test.
6. **Incremental.** Materialized as `incremental` with `merge` on
   `price_key`. Partition by `trade_date`, the only partition column
   BigQuery allows. Cluster by `exchange`, then `sec_id`: a second
   exchange cannot be a partition, so it is the first cluster column.
   Filters must name the exchange before the ticker, clustering prunes
   by the prefix of the cluster list. Each run
   rebuilds a window of the last N days (default 7) to cover late files.
   The window bounds are put into the SQL as literals, not as a subquery:
   a subquery bound does not prune partitions in BigQuery. The bound
   comes from the macro `window_start()`: the `window_start` variable
   from Airflow when it is set, else `max(trade_date) - N days` from
   the table itself through `run_query`.

   `merge` needs the bound too. Without `incremental_predicates` the
   merge compares new rows with the whole target table. The predicate
   is set in `config()` from the variable directly, not from the macro:
   `config()` is evaluated at parse time, where `run_query` cannot run.
   So a manual run without the variable prunes the source but reads
   the whole target. A run from Airflow always sets the variable and
   prunes both sides. Measured on 10.09.2026 with 875 863 rows in the
   target: the merge without the variable scanned 25.8 MiB, with the
   variable 0.5 MiB. So a run by hand also sets the variable, always.
7. **Late split.** A split published after its date changes `K` for
   rows from the split date on. Rows before the split date do not
   change. If the split date is before the window, the rows between the
   split date and the window keep a stale factor, and the model never
   sees it. The singular test in Acceptance does. The fix is not a full
   refresh: rerun the model with `window_start` set to the split date,
   the window bound as a literal pays off here a second time.
8. **`updated_at` says when the row was touched, not when it changed.**
   Every nightly run rewrites the whole window, so `updated_at` moves
   on rows whose values did not change. A conditional merge that skips
   equal rows is not in dbt-bigquery out of the box and is not worth
   a custom merge. The site shows `max(updated_at)` as "data updated
   at", it replaces `mv_last_price.last_update`.

## Out of scope

- Intraday prices. The table gives yesterday's close. The last price
  during the day is a job for the application, not for the warehouse.
- Corrections other than splits: change of face value, denomination.
  The splits source does not have them and Oracle history starts in 2024.
- Lots and portfolios. Nothing user specific is in this table.
- Boards other than TQBR and exchanges other than MOEX. The key and
  the columns are ready for them, the sources are not. FX rates, ISIN
  and a trade calendar per exchange come with the first foreign
  security, not before.

## Rejected options

- **Adjusted price column.** Rewrites history on every split, breaks
  the incremental by date. Rule 2.
- **`insert_overwrite` instead of `merge`.** Would also work on BigQuery
  and is closer to a Hive partition overwrite. Kept `merge` to have one
  real `merge` in the project. Can be measured against each other later.
- **Carry the last known price forward.** The exchange does it during
  a halt, so it looked natural. Rejected: the last price can be years
  old (KSGR had 2 148 empty days in a row), the incremental model would
  have to read itself, and it is still an invented number.
- **Zero price on a day without trades.** Also invented, and it breaks
  the invariant tests on prices. Zero is the valuation rule of the site,
  not a fact. Rule 3.
- **Face value history from Oracle as the correction source.** It starts
  in 2024, the MOEX splits source starts in 12.2018 and covers more.

## Acceptance

Grain, run in BigQuery after `dbt build`:

```sql
select count(*) as n, count(distinct price_key) as k
from `dm.fct_price_daily`
```

`n` must equal `k`. Then the same on one day and one security with
a split, PLZL around 27.03.2025: factor is 1 before and 10 from that day.

Row count: equal to `count(*)` of staging for board TQBR, no row is
lost or added. Null prices: equal to the null count in staging,
16 951 on 09.09.2026.

Parity of full and incremental: run `--full-refresh`, save `count(*)`,
`sum(close_price)` and `sum(split_cum_factor)`. Run the model
incrementally for the last window. The three numbers do not change.
`updated_at` is not compared, it differs by design (rule 8).

Idempotency: run the DAG for the same interval twice, `n` and `k` do not
change.

Tests that must be green:

- `unique` and `not_null` on `price_key`
- `not_null` on `exchange`, `sec_id`, `trade_date`, `currency`,
  `extracted_at`, `updated_at`. Not on `close_price`, null is a valid
  value here
- `accepted_values` on `exchange`: `MOEX`, and on `currency`: `RUB`.
  Both lists grow with the first new source, on purpose
- `split_cum_factor > 0`
- singular `assert_null_price_means_no_trades`: a null price only on
  a day with `volume = 0`. Severity `warn`, because of the one known
  row in 2021
- singular `assert_split_factor_matches_source`. It compares what past
  runs stored with what the splits source says today, same macro, newer
  data. Shape: take the securities that have a split (55), recompute `K`
  for every row of the fact of those securities from `stg_moex_splits`,
  return rows where `abs(stored - recomputed) > 1e-6`. Not `!=`, the
  factor is a float. The cluster by `exchange, sec_id` keeps the scan to those
  securities. A red row shows `sec_id` and the first bad `trade_date`,
  that date is the late split, see rule 7. Second, cheap part: securities
  without a split must have `K = 1`, this one runs on the window

**Tests run on the window, not on the whole table.** Generic tests get
`config: where: "trade_date >= '{{ var('window_start') }}'"`, the same
variable that bounds the model. `unique` on the window is enough:
`price_key` contains `trade_date`, so two rows with one key share
a date and are both inside the window. Singular tests use the same
variable as a literal, not the macro: inside a test `this` is the test
itself, not the fact. Two exceptions: the split factor test
reads all dates for the securities that have splits (55 of them, the
cluster by `exchange, sec_id` keeps it small), because a late split changes rows
outside the window. And after a full refresh, or after a rerun with an
old `window_start`, the tests run once without the variable over the
whole table, by hand. There is no weekly full run: the rows outside the
window are not touched by the nightly merge, so the window tests would
find nothing new there.

Numbers to write in the pull request: rows, bytes scanned by a full
build, bytes scanned by an incremental run, run time of both.
