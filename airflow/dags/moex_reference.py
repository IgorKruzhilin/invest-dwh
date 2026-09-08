"""Daily reload of the MOEX reference tables: the board listing and splits.

The reference has no data interval. ISS answers with the whole table at
once, so every run rewrites the same object in full, and the timetable is a
trigger one: this DAG runs at a moment, it does not process a period. That
is also why the reference does not live in moex_daily. A backfill of one
year of trade history would pull the same reference 365 times.

dbt is here for the tests, not for the views. Staging models are views over
external tables, so a new file is visible at once. The tests are the value:
they say that a ticker still has one interval on the board and that a split
factor is still above zero. The DAG that changes the data checks it.

The selector has no + on purpose. A mart has more than one source, so it
must be built in one place that sits below all of its inputs, not by every
loader that touches one of them.

The pool dbt keeps one dbt process at a time on this small machine. It
lives in the Airflow database, not in this repo, so bootstrap.sh creates it
again on a new machine.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.timetables.trigger import CronTriggerTimetable

DBT = "/usr/local/airflow/dbt_venv/bin/dbt"
DBT_PROJECT = "/usr/local/airflow/dbt"
LISTING = "/usr/local/airflow/extract/moex_listing.py"
SPLITS = "/usr/local/airflow/extract/moex_splits.py"

with DAG(
    dag_id="moex_reference",
    description="MOEX reference: board listing and splits, full reload",
    start_date=pendulum.datetime(2026, 9, 8, tz="UTC"),
    schedule=CronTriggerTimetable("5 0 * * *", timezone="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["moex", "reference", "dbt"],
) as dag:

    extract_listing = BashOperator(
        task_id="extract_listing",
        bash_command=f"python {LISTING}",
    )

    extract_splits = BashOperator(
        task_id="extract_splits",
        bash_command=f"python {SPLITS}",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"{DBT} build --project-dir {DBT_PROJECT} "
            "--select stg_moex_listing stg_moex_splits"
        ),
        # Own folder for the dbt artifacts. Two dbt runs must not share
        # manifest.json and the partial parse cache. env replaces the whole
        # environment, so append_env keeps PATH and everything else.
        env={
            "DBT_TARGET_PATH": "/tmp/dbt_target/moex_reference",
            "DBT_LOG_PATH": "/tmp/dbt_logs/moex_reference",
        },
        append_env=True,
        pool="dbt",
    )

    [extract_listing, extract_splits] >> dbt_build
