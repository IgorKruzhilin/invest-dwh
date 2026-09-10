# CI setup in GCP

The workflow `workflows/ci.yml` has three jobs. `parse` and `dags` need
nothing outside the repository. `build` runs `dbt build` on a pull
request in the dataset `ci` and needs an identity in GCP. This file has
the commands that make that identity, once per project. They run on
a machine with `gcloud` logged in as the project owner.

## Why Workload Identity Federation and not a key

A service account key is a file that never expires. It would live in
GitHub Secrets and would need rotation. With Workload Identity
Federation GitHub signs a short lived OIDC token for every run, and GCP
swaps it for an access token of the service account. Nothing to store,
nothing to rotate. The pool below trusts only tokens from this
repository.

## Commands

```
PROJECT=project-6feb8749-c55b-4db3-af0
REPO=IgorKruzhilin/invest-dwh
SA=ci-dbt@$PROJECT.iam.gserviceaccount.com

# 1. The service account for CI. Not the one of the server.
gcloud iam service-accounts create ci-dbt \
  --project $PROJECT \
  --display-name "dbt build from GitHub Actions"

# 2. The pool and the OIDC provider that trusts GitHub for this repository.
gcloud iam workload-identity-pools create github \
  --project $PROJECT --location global \
  --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github \
  --project $PROJECT --location global \
  --workload-identity-pool github \
  --issuer-uri "https://token.actions.githubusercontent.com" \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository == '$REPO'"

# 3. Let tokens of this repository act as the service account.
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format "value(projectNumber)")

gcloud iam service-accounts add-iam-policy-binding $SA \
  --project $PROJECT \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

# 4. The least rights that a build needs.
#    Jobs on the project, read raw and the bucket behind its external
#    tables, write only the dataset ci.
gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:$SA" --role roles/bigquery.jobUser

#    Rights on a dataset go through SQL. bq add-iam-policy-binding on
#    a dataset answers "requires allowlisting".
echo "grant \`roles/bigquery.dataViewer\` on schema \`$PROJECT\`.raw to 'serviceAccount:$SA'" \
  | bq query --use_legacy_sql=false

gcloud storage buckets add-iam-policy-binding gs://invest-dwh-raw \
  --member "serviceAccount:$SA" --role roles/storage.objectViewer

# 5. The dataset ci, made by hand so the account needs no right to
#    create datasets. Tables expire after 7 days, the dataset cleans itself.
bq mk --dataset --location US --default_table_expiration 604800 "$PROJECT:ci"

echo "grant \`roles/bigquery.dataEditor\` on schema \`$PROJECT\`.ci to 'serviceAccount:$SA'" \
  | bq query --use_legacy_sql=false

# 6. The provider name for the workflow.
echo "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github"
```

## Repository variables

Settings, Secrets and variables, Actions, tab Variables. They are names,
not credentials, so they are variables and not secrets.

| Variable | Value |
|---|---|
| `GCP_PROJECT` | the project id |
| `GCP_WIF_PROVIDER` | the line printed by step 6 |
| `GCP_CI_SERVICE_ACCOUNT` | `ci-dbt@<project>.iam.gserviceaccount.com` |

## Check

Open a pull request. The job `build` must be green, and `bq ls ci` must
show the staging views and `fct_price_daily`. `dm` must not change:
`select max(updated_at) from dm.fct_price_daily` gives the time of the
last night run, not the time of the pull request.
