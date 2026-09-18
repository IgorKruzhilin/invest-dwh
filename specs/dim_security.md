# dim_security

## Purpose

Give the site one row per security with its names and the price
precision, and give the fact its dimension. The site shows
`short_name` next to a position and rounds a price with
`price_decimals`. Today the site takes both from `mv_last_price`;
this table replaces that part of it.

The dimension keeps history. When a user asks why the site showed a name
or a price with two decimals on some day, we must be able to answer.
Nothing else in the project can answer it: the source is reloaded in
full every night and keeps only the current state.

## Grain

**One row per exchange, security and version.**
Key: `exchange | sec_id | valid_from`.

A version is the state of the attributes of one security between two
changes in the source. A change opens a new version and closes the old
one. At any moment every security has exactly one open version,
`valid_to = '9999-12-31'`. The site reads only open versions.

The listing in staging has one row per board and security, 713 rows for
TQBR on 10.09.2026. Today TQBR is the only board, so one row in staging
is one open version here. Delisted securities stay: the fact has their
prices, and a dimension must cover every key of its fact.

Board is an attribute, not part of the key, the same choice as in
`fct_price_daily`. A security is loaded from one main board. If a second
board of the same security appears in the listing, the test on one open
version per security goes red, and the model must pick the main board by
a rule.

## Inputs

| Input | Role |
|---|---|
| `stg_moex_listing` | one row per board and security, names, decimals, first and last trade date on the board |
| `int_moex_listing` | the same rows with `listing_till_date` mapped to `9999-12-31` for a listed security, see rule 2 |
| `snap_moex_listing` | dbt snapshot of `int_moex_listing`, one row per version, the history lives here |

The chain is `stg_moex_listing` -> `int_moex_listing` -> `snap_moex_listing`
-> `dim_security`. The snapshot is the only object in the project that
cannot be rebuilt from GCS. See "Protecting the history".

## Columns

| Column | Definition |
|---|---|
| `security_key` | `exchange \| sec_id \| valid_from`, surrogate key of the version |
| `exchange` | exchange code, `MOEX` for now. Part of the key |
| `sec_id` | ticker, local to the exchange. Joins to `fct_price_daily.sec_id` |
| `board` | main board of the security, `TQBR` for now. Attribute, not key |
| `short_name` | short name of the security, what the site shows |
| `full_name` | full legal name of the issue |
| `price_decimals` | number of decimal places in the price on the board. The site rounds with it |
| `listing_from_date` | first trade date on the board, from the source |
| `listing_till_date` | `9999-12-31` while the security is on the board, else the last trade date on the board from the source. See rule 2 |
| `valid_from` | timestamp when this version was first seen by the snapshot |
| `valid_to` | timestamp when the next version was seen, or `9999-12-31` for the open version |
| `extracted_at` | when the extract script wrote the listing file that produced this version |
| `updated_at` | when dbt last wrote this row, `current_timestamp()` of the run |

There is no `is_current` and no `is_listed` flag. Both are one filter:
`valid_to = '9999-12-31'` and `listing_till_date = '9999-12-31'`.
A sentinel date instead of `null` keeps range joins and filters plain,
`valid_from <= t and t < valid_to`, with no `coalesce` in every query.

## Rules

1. **The history is a dbt snapshot, strategy `check`.** The source has no
   change timestamp, `extracted_at` is the time of the load and changes
   every night, so the `timestamp` strategy would open 713 versions per
   night. The `check` strategy compares the tracked columns:
   `board`, `short_name`, `full_name`, `price_decimals`,
   `listing_from_date`, `listing_till_date`. A change in any of them
   opens a version. `extracted_at` is in the snapshot but is not
   tracked: it says which load produced the version and stays as it was.
2. **`listing_till_date` is `9999-12-31` for a listed security.** In the
   source the last trade date of a listed security moves every trading
   day. Tracked as it is, it would open 506 versions a day. So
   `int_moex_listing` maps it: a security whose source date equals
   `max(listing_till_date) over ()` is on the board today and gets the
   sentinel. Delisting is then one version: the sentinel turns into the
   real last date. The source has no listed flag, this is a hypothesis
   about the source, and the acceptance query checks it: the count of
   listed securities must equal the count of rows in `stg_moex_history`
   on the last trade day, 506 on 10.09.2026. If they differ, the rule
   changes, not the number. The run date is not used on purpose:
   `listing_till_date >= today - N` breaks on every holiday longer
   than N, the maximum follows the board's own calendar.
3. **A row that disappears from the source closes its version.** By
   default a dbt snapshot ignores deleted rows and their version stays
   open forever, like a `merge` with no `when not matched by source`.
   The snapshot sets `hard_deletes: invalidate`, so the version is closed
   with `valid_to` = time of the run. A security with no open version
   makes the test on one open version red, and the run stops before
   the export. That is on purpose: the listing covers the whole history
   of the board, so a vanished row is a change in the source that a
   human must look at, not a case to hide with a `left join` in the fact.
4. **Every security of the fact is here.** A `relationships` test from
   `fct_price_daily.sec_id` to `dim_security.sec_id` runs on the whole
   fact, not on the reload window: the two columns are clustered and the
   test reads a few megabytes. Together with rule 3 it means every
   security of the fact has exactly one open version.
5. **The dimension is rebuilt from the snapshot every run.** It is a
   `table`, about 700 rows plus versions, no incremental, no partition,
   no cluster. The snapshot holds the state, the model only renames
   and adds the key. `dbt --full-refresh` rebuilds the model and does
   not touch the snapshot: dbt ignores the flag for snapshots.
6. **The history starts on the day of the first snapshot.** `valid_from`
   of the first version is the time of that run, not
   `listing_from_date`. The question "what did the site show" is
   answered from that day on.
7. **Naming.** Exchange specific names stay in staging, the dimension
   uses neutral ones: `short_name`, `full_name`, `price_decimals`.
   The snapshot meta columns are renamed to `valid_from`, `valid_to`,
   `version_id`, `snapshot_updated_at` with `snapshot_meta_column_names`.

## Protecting the history

The snapshot table `snap.snap_moex_listing` is the only state in the
project that is not in git and not in GCS. Three layers of protection:

1. **Own dataset `snap`.** Everything in `dm` and `stg` can be dropped
   and rebuilt from GCS. Nothing in `snap` can. The split makes the rule
   visible: a `drop` in `dm` is a rebuild, a `drop` in `snap` is a loss.
   BigQuery keeps seven days of time travel on the table as the last
   safety net.
2. **Before any change of the snapshot yml, a BigQuery table snapshot.**
   `bq cp --snapshot snap.snap_moex_listing snap.snap_moex_listing_bak_YYYYMMDD`
   is zero copy and costs nothing until the tables diverge. Do it before
   a change of `check_cols`, `unique_key`, `strategy` or the meta column
   names. Delete the backup after the change is proved.
3. **Adding a tracked column is a migration, not an edit.** dbt adds a
   new column to the snapshot table with `null` in every old row. If the
   column goes straight into `check_cols`, the next run sees `null`
   against a value in every row and opens 713 new versions in one night:
   the history is not lost, but every security gets a false change on
   that date. The order that avoids it:
   1. take the backup from step 2;
   2. add the column to `int_moex_listing` and to the snapshot query,
      not to `check_cols`, run the snapshot: the column appears, old rows
      hold `null`;
   3. `update` the open versions with the current value from
      `int_moex_listing`. Closed versions keep `null`: we do not know
      the value they had, and a guess is worse than a `null`;
   4. add the column to `check_cols`, run the snapshot, prove that the
      count of versions did not change.

Removing a column from the query does not remove it from the table,
dbt never drops a snapshot column. Leave it and write why in the yml.

## Out of scope

- ISIN, lot size, issuer, security type. The listing endpoint has none of
  them. They come with the ISS `securities` endpoint and a new extract,
  when a consumer needs them. ISIN is the global id and the first need is
  the second exchange. Adding them is the migration above.
- Currency. It is an attribute of a price, not of a security, and it
  lives in the fact.
- Boards other than TQBR and exchanges other than MOEX. The key is ready,
  the sources are not.
- History before the first snapshot run. See rule 6.

## Rejected options

- **Type 1, overwrite in place.** The first version of this spec. It was
  rejected when the site became the consumer: the site shows the name
  and rounds with `price_decimals`, and "why did it show that on that
  day" has no answer without versions. The cost is one snapshot and one
  dataset that must never be dropped.
- **Track `listing_till_date` as the source gives it.** 506 new versions
  every trading day, the history turns into noise. Rule 2 maps it to a
  sentinel instead.
- **`is_listed` and `is_current` flags.** Both are one comparison with
  the sentinel. A flag next to the date it is derived from is a second
  copy of the same fact.
- **A hand-written SCD2 as an incremental model with `merge`.** More
  code than the snapshot and the same table. The snapshot is the dbt
  tool for this and the project has not used it yet.
- **Wide table, names inside the fact.** One join on 700 rows costs the
  site nothing, and a rename would rewrite 875 thousand fact rows.
- **`left join` in the fact to survive a missing security.** Hides
  a source change. Rules 3 and 4 make it a red test instead.
- **`hard_deletes: new_record`.** It inserts an extra row with
  `dbt_is_deleted = true` for a vanished security. We want the run to
  stop, not a new kind of row for the site to filter.

## Acceptance

Grain, run in BigQuery after `dbt build`:

```sql
select count(*) n, count(distinct security_key) k
from `dm.dim_security`
```

`n` must equal `k`. On the first run both equal `count(*)` of
`stg_moex_listing`, 713 on 10.09.2026: one version per security.

One open version per security:

```sql
select
	count(distinct concat(exchange, '|', sec_id)) securities
	, countif(valid_to = timestamp '9999-12-31') open_versions
from `dm.dim_security`
```

The two numbers must be equal.

Fact coverage, the star holds. Run once at acceptance; every night the
same check is the `relationships` test below:

```sql
select count(distinct f.sec_id) missing
from
	`dm.fct_price_daily` f
	left join `dm.dim_security` d
		on d.exchange = f.exchange
		and d.sec_id = f.sec_id
		and d.valid_to = timestamp '9999-12-31'
where
	d.sec_id is null
```

`missing` must be 0.

Rule 2, the sentinel against the history:

```sql
select
	(select countif(listing_till_date = date '9999-12-31')
	 from `dm.dim_security`
	 where valid_to = timestamp '9999-12-31') listed
	, (select count(*) from `stg.stg_moex_history`
	   where dt = (select max(dt) from `stg.stg_moex_history`)) traded
```

The two numbers must be equal, 506 on 10.09.2026. A gap means a security
on the board without a row in the history that day, or the reverse, and
rule 2 must be revisited with the rows that differ.

Idempotency: run `dbt build --select int_moex_listing+` twice in a row.
The count of versions and `sum(price_decimals)` do not change. The
second run of the snapshot must report zero new rows.

Rule 3, proved by hand once: delete one row from the listing file in
GCS, run the snapshot, see the version closed and the test red, put the
file back, run again, see a new open version for that security and the
test green. This is the only way to test the setting without waiting for
the source to change.

Tests that must be green:

- `unique` and `not_null` on `security_key`
- `not_null` on `exchange`, `sec_id`, `board`, `short_name`,
  `price_decimals`, `listing_from_date`, `listing_till_date`,
  `valid_from`, `valid_to`, `extracted_at`, `updated_at`. `full_name`
  may be null, the source does not promise it
- `accepted_values` on `exchange`: `MOEX`, and on `board`: `TQBR`. Both
  lists grow with the first new source, on purpose
- `relationships` on `fct_price_daily.sec_id` to `dim_security.sec_id`,
  in the fact's yml, on the whole fact, not on the window
- singular `assert_security_has_one_open_version`: for every
  `exchange, sec_id` the count of rows with `valid_to = '9999-12-31'`
  is exactly one. Zero is a vanished row, rule 3. Two is a second board
  or a broken key. Severity `error`: the run stops
- singular `assert_versions_do_not_overlap`: for every security,
  `valid_to` of a version equals `valid_from` of the next one
- singular `assert_listing_interval_is_ordered`:
  `listing_from_date <= listing_till_date` for every row

Tests run on the whole table, it is small.

The dimension has its own DAG, `moex_dim`, not a task in `moex_marts`.
The fact has two inputs and needs the day lock of two sensors. The
dimension has one input, so it needs no lock at all: `moex_dim` is
scheduled on the Asset that `dbt_build` of `moex_reference` emits, with
no sensor and no cron offset. One task, `dbt_build` with
`--select int_moex_listing+`: the intermediate model, the snapshot, the
dimension and their tests. The selector does not start at the staging
view, that layer belongs to `moex_reference`. `dbt build` runs the
snapshot before the model by itself. The export to the site comes as the next task in the
same DAG. A red fact does not stop the names on the site, and a red
dimension does not stop the prices; the status of a `moex_dim` run is
the status of the dimension and nothing else. A rerun of
`moex_reference` by hand emits the Asset again and refreshes the
dimension and the site with it. Both DAGs use the `dbt` pool of size
one, so their dbt runs never overlap.

An Asset run has no data interval. The dimension does not need one:
the snapshot compares the source with its own last state, not with
a date. In CI the snapshot is built from scratch in the `ci` dataset
and expires with it after seven days; CI never sees history and does
not need it.

The export to the site takes only open versions of listed securities:
`valid_to = '9999-12-31' and listing_till_date = '9999-12-31'`. The
history stays in BigQuery.

Numbers to write in the pull request: rows, versions, run time, bytes
scanned.
