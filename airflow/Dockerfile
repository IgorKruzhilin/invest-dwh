FROM astrocrpublic.azurecr.io/runtime:3.3-7

# dbt goes into its own virtualenv on purpose.
# Airflow and dbt both pin google and protobuf libraries, and the pins clash.
# A separate venv keeps them apart. The DAG calls dbt by full path.
# The versions are the same as in requirements.txt, CI must run the same dbt.
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir "dbt-core==1.12.3" "dbt-bigquery==1.12.0"

# The dbt project is mounted read-only, so build artifacts must go elsewhere.
ENV DBT_TARGET_PATH=/tmp/dbt_target
ENV DBT_LOG_PATH=/tmp/dbt_logs
ENV DBT_PROFILES_DIR=/usr/local/airflow/.dbt