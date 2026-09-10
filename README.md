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

CI builds every model on a pull request into the dataset `ci`. It enters GCP
through Workload Identity Federation as the service account `ci-dbt`, so no
key is stored on GitHub. The pool, the provider, the account, its roles and
the dataset are made by hand with `gcloud` and `bq`, the commands are in
`.github/README.md`. The repository variables `GCP_PROJECT`,
`GCP_WIF_PROVIDER` and `GCP_CI_SERVICE_ACCOUNT` point the workflow at them.

## Rules of the code

See `CONVENTIONS.md`.
