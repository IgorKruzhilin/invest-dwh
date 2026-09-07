FROM astrocrpublic.azurecr.io/runtime:3.3-7

# dbt goes into its own virtualenv on purpose.
# Airflow and dbt both pin google and protobuf libraries, and the pins clash.
# A separate venv keeps them apart. The DAG calls dbt by full path.
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir "dbt-bigquery>=1.9"

# The dbt project is mounted read-only, so build artifacts must go elsewhere.
ENV DBT_TARGET_PATH=/tmp/dbt_target
ENV DBT_LOG_PATH=/tmp/dbt_logs
ENV DBT_PROFILES_DIR=/usr/local/airflow/.dbt