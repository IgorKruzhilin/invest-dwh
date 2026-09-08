-- Raw layer: external table over the Parquet file in GCS.
-- No data is copied. BigQuery reads the file at query time.
-- Partition columns market and board come from the object path.
-- There is no dt in the path: the listing has no date interval, every load
-- rewrites the same object in full.
-- Rerun is safe: CREATE OR REPLACE.

CREATE OR REPLACE EXTERNAL TABLE `raw.moex_listing`
WITH PARTITION COLUMNS
OPTIONS (
  format = 'PARQUET',
  uris = ['gs://invest-dwh-raw/moex/listing/*.parquet'],
  hive_partition_uri_prefix = 'gs://invest-dwh-raw/moex/listing',
  require_hive_partition_filter = false
);
