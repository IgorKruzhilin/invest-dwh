-- Raw layer: external table over the Parquet file in GCS.
-- No data is copied. BigQuery reads the file at query time.
-- Partition column engine comes from the object path. The source is one
-- table for the whole engine, it is not split by market or board.
-- There is no dt in the path: the reference has no date interval, every
-- load rewrites the same object in full.
-- Rerun is safe: CREATE OR REPLACE.

CREATE OR REPLACE EXTERNAL TABLE `raw.moex_splits`
WITH PARTITION COLUMNS
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://invest-dwh-raw/moex/splits/*.parquet'],
  hive_partition_uri_prefix = 'gs://invest-dwh-raw/moex/splits',
  require_hive_partition_filter = false
);
