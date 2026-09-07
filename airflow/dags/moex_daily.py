"""Daily MOEX pipeline: extract one trade day into GCS, then run dbt.

The date always comes from the Airflow data interval, never from now().
Rerunning the same interval overwrites the same GCS object and rebuilds
the same partition, so a second run adds no duplicates.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.timetables.interval import CronDataIntervalTimetable

DBT = "/usr/local/airflow/dbt_venv/bin/dbt"
DBT_PROJECT = "/usr/local/airflow/dbt"
EXTRACT = "/usr/local/airflow/extract/moex_history.py"

with DAG(
    dag_id="moex_daily",
    description="MOEX daily trade history: GCS raw layer, then dbt models",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    schedule=CronDataIntervalTimetable("0 0 * * *", timezone="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["moex", "dbt"],
) as dag:

    extract = BashOperator(
        task_id="extract",
        bash_command=(
            f"python {EXTRACT} "
            "{{ data_interval_start | ds }} {{ data_interval_start | ds }}"
        ),
        skip_on_exit_code=99,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{DBT} build --project-dir {DBT_PROJECT}",
    )

    extract >> dbt_build