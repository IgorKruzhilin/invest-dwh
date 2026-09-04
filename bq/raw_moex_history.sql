-- Raw layer: external table over Parquet files in GCS.
-- No data is copied. BigQuery reads the files at query time.
-- Partition columns market, board, dt come from the object path.
-- The key is dt, not tradedate: it must not clash with the TRADEDATE column in the files.
-- Rerun is safe: CREATE OR REPLACE.

CREATE OR REPLACE EXTERNAL TABLE `raw.moex_history`
WITH PARTITION COLUMNS
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://invest-dwh-raw/moex/history/*.parquet'],
  hive_partition_uri_prefix = 'gs://invest-dwh-raw/moex/history',
  require_hive_partition_filter = false
);
