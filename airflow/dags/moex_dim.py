"""dim_security: the type 2 dimension of securities, built from the listing.

One input, so no day lock and no sensor. The DAG runs when moex_reference
emits the Asset stg_moex_listing, that is after its dbt_build is green.
A rerun of moex_reference by hand emits it again and refreshes the
dimension. The run has no data interval and needs none: the snapshot
compares the listing with its own last state, not with a date.

The build has three nodes: int_moex_listing, the snapshot
snap_moex_listing that keeps the versions, and dim_security that is
rebuilt from it. The selector starts at int_moex_listing, not at the
staging view: the staging layer belongs to moex_reference. The snapshot
is the only table of the project that cannot be rebuilt from GCS; the
rules are in CONVENTIONS.md, section Snapshots.

The export of the open versions to the site is the next task here.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import DAG, Asset
from airflow.providers.standard.operators.bash import BashOperator

DBT = "/usr/local/airflow/dbt_venv/bin/dbt"
DBT_PROJECT = "/usr/local/airflow/dbt"

with DAG(
    dag_id="moex_dim",
    description="dim_security: snapshot the board listing, then build the dimension",
    start_date=pendulum.datetime(2026, 9, 18, tz="UTC"),
    schedule=[Asset(name="stg_moex_listing")],
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["moex", "dbt"],
) as dag:

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"{DBT} build --project-dir {DBT_PROJECT} "
            "--select int_moex_listing+"
        ),
        # Own folder for the dbt artifacts, and one dbt process at a time on
        # the machine. See moex_reference for the reason.
        env={
            "DBT_TARGET_PATH": "/tmp/dbt_target/moex_dim",
            "DBT_LOG_PATH": "/tmp/dbt_logs/moex_dim",
        },
        append_env=True,
        pool="dbt",
    )
