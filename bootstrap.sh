#!/usr/bin/env bash
# Bring a fresh machine to a working state for this project.
#
# It does: the python venv, the GCS bucket, the BigQuery datasets, the
# external tables of the raw layer, the dbt profile that lives outside the
# repo, and the Airflow pool that keeps one dbt process at a time.
#
# It does not: install the tools and load any data. Install first: git,
# python3-venv, docker, docker-buildx, gcloud, astro CLI. Load data with the
# extract scripts or with an Airflow backfill.
#
# Safe to run again: every step either replaces the object or checks first.
#
# Usage:
#     bash bootstrap.sh

set -euo pipefail

PROJECT="project-6feb8749-c55b-4db3-af0"
BUCKET="invest-dwh-raw"
LOCATION="US"
REPO="$(cd "$(dirname "$0")" && pwd)"

echo "== python venv"
python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install --quiet --upgrade pip
"$REPO/.venv/bin/pip" install --quiet -r "$REPO/requirements.txt"

echo "== gcloud project"
gcloud config set project "$PROJECT" --quiet

echo "== GCS bucket"
if gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
	echo "bucket gs://$BUCKET is already there"
else
	gcloud storage buckets create "gs://$BUCKET" --location="$LOCATION"
fi

echo "== BigQuery datasets"
# -f exits with 0 when the dataset is already there
bq --location="$LOCATION" mk -f --dataset "$PROJECT:raw"
bq --location="$LOCATION" mk -f --dataset "$PROJECT:stg"

echo "== external tables of the raw layer"
# BigQuery reads the schema and the partitions from the files, so a table
# over an empty prefix cannot be created. On a new machine load the data
# first with the extract scripts, then run this script again.
missing_data=0
for f in "$REPO"/bq/*.sql; do
	echo "   $f"
	if ! bq query --use_legacy_sql=false < "$f"; then
		echo "   failed. Is there any file in GCS for this table yet?"
		missing_data=1
	fi
done

echo "== dbt profile, it lives outside the repo on purpose"
mkdir -p "$HOME/.dbt"
if [ -f "$HOME/.dbt/profiles.yml" ]; then
	echo "profile is already there, left as it is"
else
	cat > "$HOME/.dbt/profiles.yml" <<EOF
invest_dwh:
  target: dev
  outputs:
    dev:
      type: bigquery
      # oauth means the service account of the machine, there is no key file
      method: oauth
      project: $PROJECT
      dataset: stg
      location: $LOCATION
      threads: 4
      maximum_bytes_billed: 1000000000
EOF
fi

echo "== check the connection"
"$REPO/.venv/bin/dbt" debug --project-dir "$REPO/dbt"

if [ "$missing_data" = "1" ]; then
	echo "== some external tables were not created"
	echo "Load the data and run this script again:"
	echo "    .venv/bin/python extract/moex_listing.py"
	echo "    .venv/bin/python extract/moex_splits.py"
	echo "    .venv/bin/python extract/moex_history.py 2026-09-01 2026-09-07"
fi

echo "== Airflow pool"
# The pool lives in the Airflow database, not in this repo, so it has to be
# created again on every new machine. Both dbt tasks run in it, and that is
# what keeps two dbt processes from meeting on a 4 GB box.
if (cd "$REPO/airflow" && astro dev run pools set dbt 1 "one dbt process at a time"); then
	echo "pool dbt is set"
else
	echo "could not set the pool. Start Airflow first:"
	echo "    cd $REPO/airflow && astro dev start"
	echo "then run this script again"
fi

echo "== done"
