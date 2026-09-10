# invest-dwh

A small data warehouse for a personal investment portfolio, built on
GCP. The source is the MOEX ISS API, the exchange of Moscow. The old
version of this tracker ran on Oracle with Python scripts. This project
moves it to a cloud stack: GCS, BigQuery, dbt, Airflow, GitHub Actions.

The warehouse has a real consumer: the site of the portfolio reads the
marts. The stack is new to the author, so every decision keeps its
reason in the repository. Every mart starts from a spec, every number
below was measured, not estimated.

## Architecture

Three layers, medallion style, all in one BigQuery project.

| Layer | Dataset | What it is | Who writes it |
|---|---|---|---|
| Raw | `raw` | External tables over Parquet files in GCS. The history has one object per trade day, partitioned by market, board and day in the path. Each reference table is one object, rewritten in full | the extract scripts in `extract/`, run by Airflow |
| Staging | `stg` | One view per source. Names and types only, no business logic | dbt |
| Marts | `dm` | The star: facts and dimensions. Every model has a spec in `specs/` | dbt |

Raw data stays in GCS. BigQuery reads the Parquet files in place through
external tables, so the storage is one copy and one bill. A query reads
only the columns it needs: the full build of the fact scans 27.9 MiB from
about 190 MB of files.

### The night in Airflow

Three DAGs, in `airflow/dags/`. The loaders know nothing about the marts.

| DAG | Schedule, UTC | What it does |
|---|---|---|
| `moex_daily` | 00:00, one run per trade day | loads one day of trade history into GCS, then runs the staging model and its tests |
| `moex_reference` | 00:05 | reloads the board listing and the splits in full, then runs their tests |
| `moex_marts` | 00:30 | waits for both loaders of the same night with `ExternalTaskSensor`, then builds and tests the marts |

The date always comes from the Airflow data interval, never from the
clock. A rerun of the same day overwrites the same GCS object and
rebuilds the same partition, so a second run adds no rows. This was
checked: the DAG ran twice for one day, the count and the number of
distinct keys did not change.

The marts wait with sensors on the logical date and not with an AND of
assets. An AND of assets fires on the first pair of events, and after
one failed night the pairs shift by a day for good: the mart would read
the splits of the day before, every night, in silence. The reason is in
`CONVENTIONS.md`.

### The star

`fct_price_daily` is a periodic snapshot fact. One row per exchange,
security and trade day. It holds the official close price and the
cumulative split factor, the number that turns a lot quantity from one
date into another. `dim_security` is its dimension: one row per exchange
and security, the names and the price precision from the board listing.

The grain is proved by a query, not by a promise:

```sql
select count(*) as n, count(distinct price_key) as k
from `dm.fct_price_daily`
```

875 863 rows, 875 863 keys, equal to the row count of the staging view.

The fact is incremental: `merge` on the key, partitioned by trade day,
clustered by exchange and security. Every night rebuilds a window of the
last 7 days, the bound is a literal in the SQL so BigQuery prunes the
partitions on both sides of the merge. Measured: the full build scans
27.9 MiB in 42 s, the nightly incremental run 0.5 MiB in 9 s. The same
run without the window variable scans 25.8 MiB, because the merge then
compares against the whole target. A full build and an incremental run
give the same table: the count, the sum of prices and the sum of factors
are equal.

The specs are in `specs/`. They say the grain in words, the rules, the
edge cases, what was rejected and why, and the queries that accept the
model.

### Data quality

Tests are the invariants of the data, not a comparison with the old
system. Generic tests in the yml files: unique and not null on every
key, accepted values on the exchange and the currency. Singular tests in
`dbt/tests/`:

- the split factor stored by past runs must match the splits source of
  today, recomputed with the same macro. A late split changes rows
  before the window, and only this test sees it
- a null price only on a day without trades. One row is known, CIAN on
  its first trade day after the IPO, so this test warns
- the split factor of the fact and the split ratios of the source are
  above zero

The tests run on the same window as the model, through one variable.
On a pull request they run on the whole table.

### CI

`.github/workflows/ci.yml`, on every pull request, three jobs:

- `parse`: `dbt parse` with a dummy profile, no cloud
- `dags`: the Astro DAG test inside the Astro Runtime image, the same
  image the server runs. It fails on an import error, a DAG without
  tags or with retries below two
- `build`: `dbt build --full-refresh` of the whole project into the
  dataset `ci`. CI enters GCP through Workload Identity Federation as
  a service account of its own. No key is stored anywhere. The account
  can write only `ci` and read only `raw` and the bucket. Checked: after
  a CI run `max(updated_at)` of the production fact did not move

The build takes about 70 s. CI runs on pull requests only: a merge
commit is the head of a pull request that was already checked.

## Decisions

Short form. The long form with the numbers is in the specs and in
`CONVENTIONS.md`.

- **No Spark.** The whole history is under 1 GB of Parquet, the old
  Oracle base was about 10 GB. A distributed engine for data that fits
  in memory is a wrong tool, and the first question about it would show
  that. Spark comes back with tick data, if ever.
- **No Terraform yet.** One project, one bucket, three datasets, one VM.
  `bootstrap.sh` is enough today.
- **External tables, not loading into BigQuery.** One copy of the raw
  data, in GCS, in open Parquet. The price is a scan of the files on
  every read, and the numbers above show that this price is small.
- **`merge`, not `insert_overwrite`.** Both work on BigQuery. `merge` was
  kept to have one real merge in the project, the two can be measured
  against each other later.
- **The fact stores what the exchange gave.** A missing close price
  stays null. Zero and the last known price are both invented numbers.
  What a missing price means for a position is a rule of the consumer.
- **No adjusted price column.** It rewrites history on every split and
  breaks the incremental by date. The split factor for a past date never
  changes.
- **No snapshot of the listing.** The source already carries the
  interval of board membership, and nobody reads the history of names.
  A snapshot for its own sake is a demo, not a model.
- **Sensors, not an AND of assets, for a mart with two inputs.** See
  the night above.
- **No key in CI.** Workload Identity Federation instead. Nothing to
  store, nothing to rotate.

## Status

Done: the raw layer, staging, `fct_price_daily`, three DAGs, CI with
a real build.

Next: `dim_security` (spec written), export of the marts to the
database of the site, an Iceberg table on the raw layer with a
measurement of files and read time before and after.

## Setup on a new machine

Install first: git, python3-venv, docker, docker-buildx, gcloud, astro CLI.
Then:

```
git clone <this repo> ~/invest-dwh
cd ~/invest-dwh/airflow && astro dev start
cd ~/invest-dwh && bash bootstrap.sh
```

`bootstrap.sh` makes the venv, the bucket, the datasets, the external tables,
the dbt profile in `~/.dbt`, and the Airflow pool `dbt`. It loads no data.

State that is not in this repo: the dbt profile and the Airflow pool. Both are
made again by `bootstrap.sh`.

CI builds every model on a pull request into the dataset `ci`. It enters GCP
through Workload Identity Federation as the service account `ci-dbt`, so no
key is stored on GitHub. The pool, the provider, the account, its roles and
the dataset are made by hand with `gcloud` and `bq`, the commands are in
`.github/README.md`. The repository variables `GCP_PROJECT`,
`GCP_WIF_PROVIDER` and `GCP_CI_SERVICE_ACCOUNT` point the workflow at them.

## Rules of the code

See `CONVENTIONS.md`.
