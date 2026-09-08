# invest-dwh

Analytics pipeline for a personal investment portfolio.
Data source: MOEX ISS API. Stack: GCS, BigQuery, dbt, Airflow.

Work in progress.

## Layers

| Layer | Where | What |
|---|---|---|
| Raw | `bq/`, GCS | External tables over Parquet files. One object per trade day for the history, one object for each reference table |
| Staging | `dbt/models/staging` | One model per source, names and types only |
| Marts | not there yet | Business layer |

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

## Rules of the code

See `CONVENTIONS.md`.
