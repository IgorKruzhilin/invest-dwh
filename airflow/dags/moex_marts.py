"""MOEX marts: fct_price_daily today, dim_security later.

A mart has more than one input, so it is built here, below both loaders,
not inside one of them. The loaders keep their own schedules and know
nothing about this DAG. This DAG runs by cron after them and waits for
both with ExternalTaskSensor on the same logical date. This is the day
lock: the mart for day D needs the history of day D and the reference
of the same night, not any two runs that happen to be there.

An AND of assets was rejected. It fires on the first pair of events, and
after one failed night the pairs shift by a day and stay shifted: the
mart would read the splits of the day before, every night, in silence.

The sensors match runs by logical date, so the offsets below depend on
the loader crons. moex_daily runs at 00:00 with a day interval, so its
logical date is 30 minutes before ours. moex_reference runs at 00:05 on
a trigger timetable, so its logical date is the trigger time, 23:35 after
ours. A new cron in a loader means a new offset here.

A skipped day in moex_daily, a weekend, skips the sensor and the mart.
A failed loader fails the sensor at once, and the mart is red, not stale.
"""
from datetime import timedelta

import pendulum
import nothing_here
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.timetables.interval import CronDataIntervalTimetable

DBT = "/usr/local/airflow/dbt_venv/bin/dbt"
DBT_PROJECT = "/usr/local/airflow/dbt"


def reference_run(dt):
    """Logical date of the moex_reference run of the same night."""
    return dt + timedelta(hours=23, minutes=35)


with DAG(
    dag_id="moex_marts",
    description="MOEX marts: wait for the history and the reference of the day, then dbt",
    # Same start as moex_daily. Airflow creates no task for a run whose
    # interval ends before start_date, so a later date would block a rerun
    # for a past day. catchup=False keeps old days from running by itself.
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    schedule=CronDataIntervalTimetable("30 0 * * *", timezone="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["moex", "dbt"],
) as dag:

    sensor_args = {
        "allowed_states": ["success"],
        "skipped_states": ["skipped"],
        "failed_states": ["failed"],
        # reschedule frees the worker slot between pokes
        "mode": "reschedule",
        "poke_interval": 300,
        "timeout": 3 * 60 * 60,
    }

    wait_history = ExternalTaskSensor(
        task_id="wait_history",
        external_dag_id="moex_daily",
        external_task_id="dbt_build",
        execution_delta=timedelta(minutes=30),
        **sensor_args,
    )

    wait_reference = ExternalTaskSensor(
        task_id="wait_reference",
        external_dag_id="moex_reference",
        external_task_id="dbt_build",
        execution_date_fn=reference_run,
        **sensor_args,
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"{DBT} build --project-dir {DBT_PROJECT} "
            "--select fct_price_daily "
            # The window starts 6 days before the trade day of the run.
            "--vars '{\"window_start\": \"{{ macros.ds_add(data_interval_start | ds, -6) }}\"}'"
        ),
        # Own folder for the dbt artifacts, and one dbt process at a time on
        # the machine. See moex_reference for the reason.
        env={
            "DBT_TARGET_PATH": "/tmp/dbt_target/moex_marts",
            "DBT_LOG_PATH": "/tmp/dbt_logs/moex_marts",
        },
        append_env=True,
        pool="dbt",
    )

    [wait_history, wait_reference] >> dbt_build
