# Conventions

Rules for this repository. They keep the code the same everywhere and make
review easy. If a rule does not fit a case, change the rule here first.

## Layers and naming

| Layer | Prefix | What it is | Materialization |
|---|---|---|---|
| Raw | `raw.*` | External tables over files in GCS. DDL by hand in `bq/`, dbt does not build them | external |
| Staging | `stg_*` | One source per model, one row in equals one row out. Only names and types change | view |
| Intermediate | `int_*` | Steps that need a name of their own | view or ephemeral |
| Snapshot | `snap_*` | History of a source as type 2 versions, built by `dbt snapshot`. Dataset `snap`, the only state that cannot be rebuilt from GCS | snapshot |
| Marts | `fct_*`, `dim_*` | Business layer, a star schema | table or incremental |

Names are singular and follow the grain. The file name is the model name.

The marts layer is a star schema, decided 2026-09-09. The first marts are
a periodic snapshot fact `fct_price_daily` (one row per security and
trade day) and a dimension `dim_security` (one row per security and
version, type 2). A wide denormalized table was the other option. It was rejected
because the consumer, the site, does one join on `sec_id` and there is
nothing to denormalize. The portfolio mart is not built in BigQuery: the
site computes portfolio value from `fct_price_daily` and its own lots,
so the marts layer stays small. Tables exported to the site keep the
same names there, one dictionary for both sides.

Marts are source neutral. The source is a column, not a part of the
table name: `stg_moex_history` feeds `fct_price_daily`, not
`fct_moex_price_daily`. Keys of marts include `exchange` from day one,
because a second exchange is planned and the same ticker on two
exchanges is two different securities. Prices carry a `currency` column.
Exchange specific column names stay in staging, marts use neutral names
with the mapping written in the spec.

## Every model must have

- a row in `_models.yml` with a `description` that states the **grain**
- a `description` for each key column
- tests on the key: `unique` and `not_null`
- the grain proved by a query before commit: `count(*)` against
  `count(distinct key)`

The grain lives in the yml file only. Do not repeat it in a SQL comment.

Column descriptions live on the model, not on the source. A source entry
says where the data comes from, what one row is, and how the file is
written. Two copies of the same description drift apart.

## Spec before a mart

Every mart model starts from a one page spec in `specs/<name>.md`. Staging
models have no spec: their grain repeats the source.

The spec has six parts:

1. **Purpose.** What question the mart answers.
2. **Grain.** One row is what. Say it in words before writing SQL.
3. **Inputs.** Sources and upstream models.
4. **Rules.** Business logic, edge cases, how we treat missing data.
5. **Out of scope.** What this model does not do.
6. **Acceptance.** The query that proves the grain and the tests that
   must be green.

A mart also declares `contract: enforced` in the yml file. Staging models
do not.

## SQL style

1. Lower case everywhere. Keep the case only where it matters: string
   literals like `'TQBR'`, and dataset and table names, which are case
   sensitive in BigQuery. Column names are not.
2. Commas go at the start of the line, then one space: `, sec_id`.
3. Give an alias only when the name changes. Never write `as`.
4. Indent with a tab. One tab per level.
5. Write a CTE when it has something to name. Do not add empty CTEs for
   symmetry.
6. Always list the columns. Never write `select *`.
7. Refer to tables only through `{{ ref() }}` and `{{ source() }}`.
8. One table after `from` stays on the same line. More than one table
   starts on a new line.
9. Join conditions go under `on`, with `and` at the start of the line.
10. One condition per line in `where`, with `and` at the start of the line.
    More than one condition starts on a new line.

Example:

```sql
select
	f.history_key
	, f.dt
	, f.sec_id
	, f.close_price
	, d.name security_name
from
	{{ ref('stg_moex_history') }} f
	left join {{ ref('stg_moex_listing') }} d
		on d.sec_id = f.sec_id
		and f.dt between d.history_from and d.history_till
where
	f.board = 'TQBR'
	and f.close_price is not null
```

## Tests

- Generic tests go in the yml file next to the model.
- Singular tests go in `dbt/tests/`. The name says the rule, for example
  `assert_dt_matches_trade_date.sql`.
- Every data bug we find gets a test, not only a fix.

## Open intervals

An open interval ends with the sentinel `9999-12-31`, never with `null`:
`valid_to` of the current version, `listing_till_date` of a listed
security. A range filter is then `valid_from <= t and t < valid_to` with
no `coalesce`, and "current" is one comparison, so there is no
`is_current` flag next to the date it would repeat.

## Snapshots

- A snapshot is defined in a yml file in `dbt/snapshots/` over a `ref`,
  never with SQL of its own. The mapping of columns lives in an `int_*`
  model above it.
- Strategy `check` with an explicit list of `check_cols`. Never `all`:
  a new column would then open a version for every row.
- `hard_deletes: invalidate`. A row that disappears from the source
  closes its version. By default dbt leaves it open forever.
- `dbt_valid_to_current` is the sentinel above, and the meta columns are
  renamed with `snapshot_meta_column_names` to `valid_from`,
  `valid_to`, `version_id`, `snapshot_updated_at`.
- A snapshot table is never dropped and never rebuilt. `--full-refresh`
  does not touch it, dbt ignores the flag for snapshots. Before any
  change of the snapshot yml, take a BigQuery table snapshot:
  `bq cp --snapshot snap.<name> snap.<name>_bak_YYYYMMDD`. Delete the
  backup after the change is proved.
- A new tracked column is a migration in four steps: backup, add the
  column to the query only, `update` the open versions from the source,
  then add it to `check_cols` and prove that the count of versions did
  not change. The order is written in `specs/dim_security.md`.
- A column removed from the query stays in the table. dbt never drops
  a snapshot column. Write why in the yml.

## Incremental models

- Use `incremental` only with a `unique_key` and the `merge` strategy.
- Always set `partition_by` on the date and `cluster_by` on the security.
- The reload window is a project variable, not a number in the model.

## Extract scripts

- Never call `datetime.now()` in the logic. The interval comes from the
  arguments.
- The path in GCS is the same for the same input. A second run overwrites
  the same object.
- If nothing was written for the whole interval, exit with code 99, not 0.
- Dependencies are `requests` and `pyarrow` only.
- Keep the code simple and flat, like the scripts we already have. No
  classes, no frameworks.

## Airflow

- No business logic in a DAG. It only orders the work.
- The date comes from `data_interval_start`.
- Paths inside the container are constants at the top of the file.
- Set `retries`, `max_active_runs` and `tags` in the DAG. CI checks the
  tags and `retries >= 2` on every DAG file.
- Do not create Connections or Variables while the machine service account
  and plain constants are enough.
- No network or database calls at the top level of a DAG file. The file is
  parsed every few seconds.
- Always pass `--max-active-runs 1` to a backfill. Two runs at the same time
  write the same objects.
- A DAG with one upstream DAG is scheduled on the Asset that the
  upstream task emits with `outlets`. No sensor, no cron offset, and a
  rerun of the upstream by hand refreshes the consumer too. An Asset run
  has no data interval, so this fits only a consumer that needs no date.
- A DAG with more than one upstream DAG waits for them with
  `ExternalTaskSensor` on the same logical date. The loaders stay
  independent and know nothing about the consumer. Do not schedule the
  consumer on an AND of assets: it fires on the first pair of events, and
  after one failed night the pairs shift by a day for good.
- The export to the site is a task in the DAG that builds the object,
  right after its `dbt_build`. It runs only when the build is green and
  is skipped with it. One DAG per object means one export per DAG.
- Do not change the timetable of a live DAG. The timetable defines what
  `logical_date` means, so old runs sit on the dates the new schedule needs.
  The next run is then skipped without any error in the log. Use a new
  `dag_id`, or clear the runs of the transition day by hand.

## Git and CI

- One branch per change. Merge through a pull request. Push to `main`
  directly when the change cannot change the SQL we send to BigQuery:
  markdown files, descriptions in a yml file, comments in the code. CI runs
  on `main` too, so a broken yml is still caught.
- CI must be green before a merge, and the diff is read before a merge.
  A green pipeline is not a review.
- Commit messages: imperative, first line up to 50 characters.
- These files never go to git: `profiles.yml`, keys, `.env`, `target/`,
  `logs/`.

## Documents

- `README.md` describes the project: layers, the stack and the reason for
  every tool, and the options we rejected.
- `specs/<name>.md` holds the spec of one mart.
- The yml file next to a model holds its grain and column descriptions.
- Write down the options we rejected and why, so we do not return to them.

## Definition of done for a change

1. `dbt build` is green.
2. The grain is proved by a query.
3. The numbers are measured and written in the pull request: rows, bytes
   scanned, run time.
4. A new decision and its reason are written in `README.md`, or in the spec
   when it belongs to one mart.
5. The change is in `main` and CI is green.
