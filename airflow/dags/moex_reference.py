"""
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
    description="",
    start_date=pendulum.datetime(2026, 9, 8, tz="UTC"),
    schedule=CronTriggerTimetable("5 0 * * *", timezone="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["moex", "dbt"],
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
    )

    [extract_listing, extract_splits] >> dbt_build
